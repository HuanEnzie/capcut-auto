# -*- coding: utf-8 -*-
"""agent.py — chế độ AGENT: chat bằng tiếng Việt, tự gọi tool của pipeline.

Khác chế độ THỦ CÔNG: ở đây ra lệnh tự do, agent tự chọn tool, tự hỏi lại khi
thiếu thông tin, và NHỚ ngữ cảnh giữa các lượt (SQLite trên máy).

KIẾN TRÚC — vì sao KHÔNG có intent classifier đứng trước:

  Khai báo tool ĐÃ LÀ bộ định tuyến, do chính model làm sau khi đọc cả ngữ cảnh.
  Dựng thêm một vòng phân loại bằng LLM là thêm một lượt gọi (chậm hơn, thêm cơ
  hội 503) và thêm một kiểu hỏng TỆ HƠN: phân loại sai thì tool đúng không còn
  trong tầm với, model buộc phải bịa — đúng cái ảo giác mà nó định chống.

  Đo bằng count_tokens của Gemini trên chính app này: system prompt + toàn bộ khai
  báo tool = ~1.467 token cố định mỗi lượt, trên cửa sổ 1 triệu. Chưa có gì để mà
  "chia để trị".

  Cách mở rộng khi tool nhiều lên: nạp sẵn nhóm cốt lõi + một tool TRA TOOL
  (`tim_tool`). Model tự tra khi cần thứ ngoài tầm với, tool tìm được sẽ được
  nạp vào lượt sau. Đây đúng cách Claude Code làm việc với hàng trăm tool.

  Ba thứ thật sự chống ảo giác nằm ở đường ống, không nằm ở prompt:
    1. kiểm tra + CHUẨN HOÁ tham số ("Đan" -> "dan"), sai thì trả kèm giá trị hợp lệ
    2. lưu tool đã gọi + dữ liệu tool trả về vào lịch sử (lượt sau còn nhớ)
    3. việc phá huỷ không tự chạy — trả về đề xuất để người dùng bấm xác nhận

TRÍ NHỚ hai tầng (API stateless, mỗi lượt phải gửi lại tất cả -> phải có ngân sách):
  Tầng 1 `memory`  — điều bền vững, XUYÊN cuộc, không bao giờ nén, bơm vào system prompt
  Tầng 2 transcript — cắt theo TOKEN. Dữ liệu tool cũ thu thành dấu vết (lấy lại được
                      bằng cách gọi tool lần nữa); lời người dùng giữ đến cùng.
  Quá ngưỡng thì nén phần cũ thành tóm tắt — kích hoạt bằng CODE, không để model tự gọi.
"""
import json, re, sqlite3, time, unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import assetlib, asset_restore, audio_balance, draft_diff, draft_scan

ROOT = assetlib.ROOT
WORK = ROOT / "shorts" / "work"

SYS = """Bạn là trợ lý dựng short video từ recording dài, làm việc với đội editor người Việt.
Trả lời NGẮN GỌN bằng tiếng Việt, giọng đồng nghiệp, không khách sáo.

Quy trình sản phẩm: record dài -> bóc lời + trích chủ đề -> người dùng CHỌN chủ đề
-> dựng draft CapCut theo GU của editor -> editor sửa trong CapCut -> đồng bộ về kho
để lần sau hợp gu hơn -> cân bằng âm thanh.

Nguyên tắc:
- CHƯA gọi tool thì KHÔNG được nêu số liệu, tên draft, tên chủ đề. Không có dữ liệu
  thì nói thẳng là chưa biết rồi gọi tool, đừng suy đoán.
- Thiếu thông tin (chủ đề nào, gu editor nào) thì HỎI, đừng đoán bừa.
- Tool trả về {"loi": ...} kèm "gia_tri_hop_le" thì chọn lại trong danh sách đó,
  đừng thử đi thử lại cùng một giá trị sai.
- Cần một việc mà chưa thấy tool phù hợp: gọi tim_tool để tra, đừng bảo là không làm được.
- Việc nặng chạy nền: báo đã khởi động và bảo người dùng xem mục Tiến trình.
- Việc có thể mất dữ liệu sẽ trả về {"can_xac_nhan": true}: nói rõ hậu quả và bảo
  người dùng bấm nút xác nhận, KHÔNG khẳng định là đã làm xong.
- Biết thêm điều BỀN VỮNG (editor thích gì, đã chốt cách làm nào) thì gọi ghi_nho một
  câu ngắn. Đừng ghi số liệu tra được bằng tool — số liệu đổi, tra lại là có."""


# ═══════════════════════ REGISTRY ═══════════════════════
# Thêm tool = viết một hàm + một decorator. Khai báo gửi cho model sinh thẳng từ
# đây, nên KHÔNG phải sửa prompt, và tool mới lập tức nằm trong tầm với của agent.

@dataclass
class Tool:
    ten: str
    mo_ta: str
    nhom: str                       # du_an | draft | kho | am_thanh | he_thong
    kieu: str                       # doc | nen | nguy_hiem
    tham_so: dict
    fn: Callable
    chuan_hoa: dict = field(default_factory=dict)   # tên tham số -> hàm chuẩn hoá
    canh_bao: str = ""              # chỉ cho kieu=nguy_hiem: hậu quả nếu chạy

    def khai_bao(self) -> dict:
        return {"name": self.ten, "description": self.mo_ta, "parameters": self.tham_so}


TOOLS: dict[str, Tool] = {}
NHOM_COT_LOI = {"du_an", "draft", "kho", "am_thanh", "he_thong"}
NGUONG_NAP_HET = 20        # <= ngần này tool thì nạp hết, chưa cần tra cứu gì


def tool(ten, mo_ta, nhom, kieu="doc", tham_so=None, chuan_hoa=None, canh_bao=""):
    def deco(fn):
        TOOLS[ten] = Tool(ten, mo_ta, nhom, kieu,
                          tham_so or {"type": "object", "properties": {}},
                          fn, chuan_hoa or {}, canh_bao)
        return fn
    return deco


# ─────────── chuẩn hoá tham số: chỗ ảo giác hay chui vào nhất ───────────
# Người Việt gõ "Đan", DB lưu "dan" -> lọc ra RỖNG mà KHÔNG có lỗi nào, model đọc
# số 0 rồi tự tin trả lời "Đan chưa có tài nguyên nào". Sai sự thật, không bắt được.

def _khong_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").strip().lower()


def _khop(gia_tri, danh_sach):
    """Khớp dần: đúng hệt -> không phân biệt hoa/dấu -> chứa trong. Không ra thì None."""
    v = str(gia_tri or "").strip()
    if not v:
        return None
    if v in danh_sach:
        return v
    kd = _khong_dau(v)
    for x in danh_sach:
        if _khong_dau(x) == kd:
            return x
    hits = [x for x in danh_sach if kd and kd in _khong_dau(x)]
    return hits[0] if len(hits) == 1 else None


def _ds_editor():
    c = assetlib.conn()
    out = [r[0] for r in c.execute(
        "SELECT DISTINCT owner FROM assets WHERE owner IS NOT NULL AND owner!=''").fetchall()]
    c.close()
    return out + ["shared"]


def _ds_draft():
    root = draft_scan.DRAFT_ROOT
    return [p.name for p in root.iterdir()
            if p.is_dir() and (p / "draft_content.json").exists()] if root.is_dir() else []


def _ds_du_an():
    return [p.name for p in WORK.iterdir() if (p / "topics.json").exists()] if WORK.is_dir() else []


CH_EDITOR = ("editor", _ds_editor)
CH_DRAFT = ("draft", _ds_draft)
CH_DU_AN = ("dự án", _ds_du_an)


# ═══════════════════════ TOOL ═══════════════════════

@tool("liet_ke_du_an", "Liệt kê record ĐÃ phân tích và danh sách chủ đề kèm điểm của từng cái.",
      nhom="du_an")
def _projects():
    out = []
    if WORK.exists():
        for p in sorted(WORK.iterdir()):
            tj = p / "topics.json"
            if not (p.is_dir() and tj.exists()):
                continue
            try:
                t = json.loads(tj.read_text(encoding="utf-8"))
            except ValueError:
                continue
            out.append({"project": p.name, "topics": [
                {"so": i + 1, "tieu_de": x.get("title", ""), "diem": x.get("total_score"),
                 "giay": round(sum(s["end_sec"] - s["start_sec"] for s in x["segments"]))}
                for i, x in enumerate(t.get("topics", []))]})
    return {"du_an": out}


@tool("liet_ke_file_record",
      "Liệt kê file record thô trong một thư mục (thời lượng, ước tính thời gian xử lý, "
      "có hình hay chỉ có tiếng). Dùng khi người dùng muốn phân tích record MỚI.",
      nhom="du_an",
      tham_so={"type": "object", "properties": {
          "dir": {"type": "string", "description": "thư mục chứa record, bỏ trống = mặc định"}}})
def _recordings(dir: str = ""):
    import app as _app
    return _app.api_browse(dir or "")


@tool("liet_ke_draft", "Liệt kê draft CapCut đã dựng, kèm trạng thái đang mở trong CapCut "
      "và đã chụp mốc chưa.", nhom="draft")
def _drafts():
    root = draft_scan.DRAFT_ROOT
    out = []
    if root.exists():
        for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:25]:
            if (p / "draft_content.json").exists():
                out.append({"ten": p.name, "dang_mo_trong_capcut": (p / ".locked").exists(),
                            "co_moc": (draft_diff.SNAP_DIR / f"{p.name}.json").exists()})
    return {"draft": out}


@tool("kho_tai_nguyen",
      "Xem kho tài nguyên đã học từ editor (font/sticker/hiệu ứng chữ/SFX), ai dùng nhiều cái gì.",
      nhom="kho",
      tham_so={"type": "object", "properties": {
          "kind": {"type": "string", "description": "sticker|font|text_template|audio|effect|transition"},
          "owner": {"type": "string", "description": "tên editor, vd dan|nguyen|shared"}}},
      chuan_hoa={"owner": CH_EDITOR})
def _assets(kind: str = "", owner: str = "", limit: int = 15):
    c = assetlib.conn()
    w, args = [], []
    if kind:
        w.append("kind=?"); args.append(kind)
    if owner:
        w.append("owner=?"); args.append(owner)
    where = (" WHERE " + " AND ".join(w)) if w else ""
    rows = [dict(r) for r in c.execute(
        "SELECT kind,name,category,owner,use_count,drop_count FROM assets" + where +
        " ORDER BY use_count DESC LIMIT ?", args + [min(limit, 40)]).fetchall()]
    # tổng phải theo ĐÚNG bộ lọc, không thì hỏi 'ai nhiều hơn' sẽ ra số giống nhau -> trả lời sai
    tot = dict(c.execute("SELECT COUNT(*) n, COALESCE(SUM(size),0) sz FROM assets" + where,
                         args).fetchone())
    by_owner = [dict(r) for r in c.execute(
        "SELECT owner, COUNT(*) n, COALESCE(SUM(use_count),0) luot FROM assets"
        + ((" WHERE kind=?") if kind else "") + " GROUP BY owner ORDER BY n DESC",
        ([kind] if kind else [])).fetchall()]
    c.close()
    return {"tong_theo_bo_loc": tot["n"], "MB": round(tot["sz"] / 1e6, 1),
            "theo_tung_editor": by_owner, "tai_nguyen": rows}


@tool("tai_nguyen_co_san_tren_may",
      "Kiểm kê tài nguyên CapCut CÓ SẴN trên máy (đã tải nhưng có thể chưa dùng): tổng số, "
      "dung lượng, theo loại, và bao nhiêu gói tải về chưa đụng tới.", nhom="kho")
def _inventory():
    import capcut_inventory as ci
    s = ci.stats()
    return {"tong_goi": s["n_assets"], "MB": round(s["size"] / 1e6),
            "da_dung": s["n_used"], "co_san_chua_dung": s["n_unused"],
            "MB_chua_dung": round(s["size_unused"] / 1e6),
            "theo_loai": s["by_kind"],
            "ghi_chu": "phần lớn do CapCut tự tải khi duyệt panel, không phải người dùng bấm tải"}


@tool("xem_editor_sua_gi", "So sánh draft với mốc đã chụp để biết editor đã THÊM/GỠ tài nguyên nào.",
      nhom="draft",
      tham_so={"type": "object", "properties": {"draft": {"type": "string"}}, "required": ["draft"]},
      chuan_hoa={"draft": CH_DRAFT})
def _diff(draft: str):
    try:
        d = draft_diff.diff(draft)
    except SystemExit as e:
        return {"loi": str(e)}
    strip = lambda arr: [{"loai": r["kind"], "ten": r["name"]} for r in arr]
    return {"them": strip(d["added"]), "go_bo": strip(d["removed"]), "giu": len(d["kept"])}


@tool("chup_moc_draft", "Chụp mốc tài nguyên của draft (làm NGAY sau khi dựng, để sau này so sánh).",
      nhom="draft",
      tham_so={"type": "object", "properties": {"draft": {"type": "string"}}, "required": ["draft"]},
      chuan_hoa={"draft": CH_DRAFT})
def _snapshot(draft: str):
    draft_diff.snapshot(draft)
    return {"ok": True, "ghi_chu": f"đã chụp mốc '{draft}'"}


@tool("dong_bo_ve_kho", "Nạp tài nguyên editor vừa thêm vào kho của editor đó, và hạ điểm cái bị gỡ.",
      nhom="kho",
      tham_so={"type": "object", "properties": {
          "draft": {"type": "string"}, "editor": {"type": "string"}}, "required": ["draft"]},
      chuan_hoa={"draft": CH_DRAFT, "editor": CH_EDITOR})
def _sync(draft: str, editor: str = "shared"):
    try:
        return draft_diff.sync(draft, editor)
    except SystemExit as e:
        return {"loi": str(e)}


@tool("do_am_luong", "Đo LUFS từng nguồn tiếng trong draft (giọng/SFX/nhạc) và mức cần chỉnh. Chỉ ĐỌC.",
      nhom="am_thanh",
      tham_so={"type": "object", "properties": {"draft": {"type": "string"}}, "required": ["draft"]},
      chuan_hoa={"draft": CH_DRAFT})
def _audio_report(draft: str):
    import app as _app
    try:
        r = _app.api_audio_report(draft)
    except Exception as e:
        return {"loi": str(e)[:120]}
    return {"nguon": r["rows"][:12], "muc_tieu": r["target"]}


@tool("cai_tai_nguyen_vao_capcut",
      "Cài các gói sticker/hiệu ứng từ kho vào CapCut của máy này (dùng khi máy mới thiếu).",
      nhom="he_thong")
def _restore():
    return {"da_cai": asset_restore.restore()}


@tool("phan_tich_record",
      "Phân tích một file record MỚI: bóc lời bằng GPU rồi trích chủ đề. Chạy nền. "
      "Nhớ báo trước thời gian ước tính lấy từ liet_ke_file_record.",
      nhom="du_an", kieu="nen",
      tham_so={"type": "object", "properties": {
          "path": {"type": "string", "description": "đường dẫn đầy đủ tới file record"},
          "asr": {"type": "string", "description": "small (nhanh, mặc định) hoặc medium"}},
       "required": ["path"]})
def _ingest(path: str, asr: str = "small", run_job=None):
    import app as _app
    if not Path(path).exists():
        return {"loi": f"không thấy file: {path}"}
    r = _app.api_ingest(path=path, asr=asr or "small")
    return {"da_khoi_dong": True, "job": r["job"], "ghi_chu": "xem mục Tiến trình"}


@tool("dung_draft", "Dựng draft CapCut cho MỘT chủ đề theo gu một editor. Chạy nền, vài phút.",
      nhom="du_an", kieu="nguy_hiem",
      canh_bao="Nếu chủ đề đó đã dựng với cùng gu editor, draft cũ sẽ bị GHI ĐÈ — "
               "mọi thứ editor đã sửa tay trong CapCut sẽ mất.",
      tham_so={"type": "object", "properties": {
          "project": {"type": "string", "description": "tên dự án, vd 1107"},
          "topic": {"type": "integer", "description": "số thứ tự chủ đề"},
          "editor": {"type": "string", "description": "gu editor, vd dan|nguyen|shared"}},
       "required": ["project", "topic"]},
      chuan_hoa={"project": CH_DU_AN, "editor": CH_EDITOR})
def _generate(project: str, topic: int, editor: str = "shared", run_job=None):
    import app as _app
    if not (WORK / project / "topics.json").exists():
        return {"loi": f"dự án '{project}' chưa được phân tích"}
    r = _app.api_generate(proj=project, topic=int(topic), editor=editor)
    return {"da_khoi_dong": True, "job": r["job"], "draft": r["draft"]}


@tool("can_bang_am_thanh", "Ghi âm lượng đã cân bằng vào draft (đóng draft trong CapCut trước).",
      nhom="am_thanh", kieu="nguy_hiem",
      canh_bao="Ghi thẳng vào file draft (có backup .prebalance.bak). Draft phải đang đóng.",
      tham_so={"type": "object", "properties": {"draft": {"type": "string"}}, "required": ["draft"]},
      chuan_hoa={"draft": CH_DRAFT})
def _balance(draft: str, run_job=None):
    import app as _app
    r = _app.api_balance(name=draft, dry=False)
    return {"da_khoi_dong": True, "job": r["job"]}


@tool("ghi_nho",
      "Ghi lại một điều BỀN VỮNG để nhớ sang các cuộc trò chuyện sau: sở thích của editor, "
      "quyết định đã chốt, việc quan trọng đã làm. Chỉ ghi thứ còn đúng lâu dài — "
      "KHÔNG ghi số liệu tra được bằng tool (số liệu thay đổi, tra lại là có).",
      nhom="he_thong",
      tham_so={"type": "object", "properties": {
          "loai": {"type": "string", "description": "so_thich | quyet_dinh | su_kien"},
          "noi_dung": {"type": "string", "description": "một câu ngắn, cụ thể"},
          "ve": {"type": "string", "description": "chủ thể, vd 'dan', 'du_an:1107', bỏ trống nếu chung"}},
       "required": ["loai", "noi_dung"]})
def _ghi_nho(loai: str, noi_dung: str, ve: str = ""):
    if loai not in LOAI_NHO:
        return {"loi": f"loại không hợp lệ: {loai}", "gia_tri_hop_le": list(LOAI_NHO)}
    return nho(loai, noi_dung, ve)


@tool("doc_tri_nho", "Đọc lại những điều đã ghi nhớ từ các cuộc trò chuyện trước.",
      nhom="he_thong",
      tham_so={"type": "object", "properties": {
          "ve": {"type": "string", "description": "lọc theo chủ thể, vd 'dan'"},
          "loai": {"type": "string", "description": "so_thich | quyet_dinh | su_kien"}}})
def _doc_tri_nho(ve: str = "", loai: str = ""):
    return {"da_nho": doc_nho(ve, loai, limit=30)}


@tool("tim_tool",
      "Tra xem có tool nào làm được việc đang cần. Dùng khi việc người dùng yêu cầu không "
      "khớp tool nào đang có. Trả về tên + mô tả tool, sau đó gọi thẳng tool đó.",
      nhom="he_thong",
      tham_so={"type": "object", "properties": {
          "nhu_cau": {"type": "string", "description": "mô tả việc cần làm, vd 'dọn tài nguyên thừa'"}},
       "required": ["nhu_cau"]})
def _find_tool(nhu_cau: str):
    """Cách mở rộng thay cho intent classifier: model TỰ tra khi thiếu, không có
    bộ phân loại nào đứng trước để mà chọn sai."""
    tu = [t for t in _khong_dau(nhu_cau).split() if len(t) > 2]
    diem = []
    for t in TOOLS.values():
        kho = _khong_dau(t.ten + " " + t.mo_ta + " " + t.nhom)
        d = sum(1 for x in tu if x in kho)
        if d:
            diem.append((d, t))
    diem.sort(key=lambda x: -x[0])
    if not diem:
        return {"tim_thay": [], "ghi_chu": "không có tool nào khớp — nói thẳng với người dùng "
                                           "là app chưa làm được việc này"}
    return {"tim_thay": [{"ten": t.ten, "mo_ta": t.mo_ta, "nhom": t.nhom,
                          "can_xac_nhan_truoc_khi_chay": t.kieu == "nguy_hiem"}
                         for _, t in diem[:5]]}


# ═══════════════════════ GỌI TOOL ═══════════════════════

def goi_tool(ten: str, args: dict, run_job=None, cho_phep_nguy_hiem=False) -> dict:
    """Một cửa duy nhất: kiểm tra tham số -> chuẩn hoá -> chặn việc phá huỷ -> chạy.

    Lỗi trả về phải ĐỦ ĐỂ MODEL TỰ SỬA: thiếu gì, giá trị hợp lệ là gì. Trả nguyên
    một TypeError của Python cho model là bắt nó đoán."""
    t = TOOLS.get(ten)
    if not t:
        return {"loi": f"không có tool '{ten}'",
                "goi_y": "gọi tim_tool để tra tool phù hợp"}

    props = (t.tham_so or {}).get("properties", {})
    req = (t.tham_so or {}).get("required", [])
    args = {k: v for k, v in (args or {}).items() if k in props}     # bỏ tham số lạ

    thieu = [k for k in req if str(args.get(k, "")).strip() == ""]
    if thieu:
        return {"loi": "thiếu tham số bắt buộc", "thieu": thieu,
                "goi_y": f"hỏi người dùng, hoặc gọi tool liệt kê để lấy giá trị đúng"}

    for k, (nhan, lay_ds) in (t.chuan_hoa or {}).items():
        if k not in args or str(args[k]).strip() == "":
            continue
        ds = lay_ds()
        khop = _khop(args[k], ds)
        if khop is None:
            return {"loi": f"không có {nhan} tên '{args[k]}'", "gia_tri_hop_le": ds[:15],
                    "goi_y": "chọn lại đúng một giá trị trong gia_tri_hop_le"}
        args[k] = khop

    if t.kieu == "nguy_hiem" and not cho_phep_nguy_hiem:
        return {"can_xac_nhan": True, "hanh_dong": ten, "tham_so": args,
                "canh_bao": t.canh_bao,
                "ghi_chu": "CHƯA chạy. Nói rõ hậu quả rồi bảo người dùng bấm nút xác nhận."}

    try:
        if t.kieu in ("nen", "nguy_hiem"):
            if run_job is None:
                return {"loi": "chưa nối được job nền"}
            return t.fn(run_job=run_job, **args)
        return t.fn(**args)
    except TypeError as e:
        return {"loi": "gọi sai tham số", "chi_tiet": str(e)[:120],
                "tham_so_hop_le": list(props)}
    except Exception as e:
        return {"loi": f"{type(e).__name__}: {str(e)[:160]}"}


# ═══════════════════════ TRÍ NHỚ ═══════════════════════

# API là STATELESS: mỗi lượt phải gửi lại toàn bộ hội thoại. Nên bối cảnh không
# phải thứ "có sẵn" mà là thứ ta DỰNG LẠI mỗi lượt — và phải dựng có ngân sách.
#
# Đo trên chính app này (count_tokens của Gemini):
#   system prompt + 14 khai báo tool = 1.467 token cố định
#   một câu người dùng ~11-30 token, một KẾT QUẢ TOOL ~420 token
# -> thứ làm phình bối cảnh là DỮ LIỆU TOOL, không phải lời nói chuyện.
#
# Từ đó ra nguyên tắc cắt: dữ liệu tool LẤY LẠI ĐƯỢC (gọi tool lần nữa), lời người
# dùng thì KHÔNG. Nên cắt dữ liệu tool trước, giữ lời người dùng đến cùng.
CHU_TREN_TOKEN = 2.5        # đo được 2,50-3,31; lấy mức thấp nhất để không ước lượng thiếu
NGAN_SACH_LICH_SU = 6000    # token tối đa cho phần lịch sử mỗi lượt
GIU_NGUYEN_VAN = 8          # số dòng gần nhất luôn giữ nguyên văn, không đụng tới
NGUONG_NEN = 4000           # quá ngần này token thì nén phần cũ lại
TRI_NHO_BOM_VAO = 12        # số mẩu ký ức dài hạn bơm sẵn vào mỗi lượt

uoc_token = lambda s: int(len(str(s)) / CHU_TREN_TOKEN) + 1


def _init_db():
    c = assetlib.conn()
    c.execute("CREATE TABLE IF NOT EXISTS chat("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, role TEXT,"
              " content TEXT, ts REAL)")
    # nhật ký chọn tool: để sau này ĐO tỷ lệ chọn sai rồi mới quyết có cần router không
    c.execute("CREATE TABLE IF NOT EXISTS tool_log("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, tool TEXT,"
              " co_loi INTEGER, ts REAL)")
    # nhật ký từng LƯỢT chat: max_steps=6 là TRẦN chứ không phải mức tiêu thụ — vòng
    # lặp thoát ngay khi model ngừng gọi tool. Muốn chỉnh trần cho đúng thì phải biết
    # thực tế mỗi tin nhắn chạy mấy vòng, nên ghi lại thay vì đoán.
    c.execute("CREATE TABLE IF NOT EXISTS chat_log("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, vong INTEGER,"
              " so_tool INTEGER, model TEXT, ket_thuc TEXT, token_gui INTEGER, ts REAL)")
    # TẦNG 1 của trí nhớ: điều bền vững, XUYÊN cuộc trò chuyện, KHÔNG BAO GIỜ bị nén.
    # Tóm tắt bằng LLM giỏi giữ ý nhưng ăn mất '1107_t4_nguyen' và '-14 LUFS' —
    # nên thứ cần nhớ chính xác phải nằm riêng, có cấu trúc, truy vấn được.
    c.execute("CREATE TABLE IF NOT EXISTS memory("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, loai TEXT, ve TEXT, noi_dung TEXT,"
              " session TEXT, ts REAL, lan_nhac INTEGER DEFAULT 1)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_mem ON memory(loai, ve, noi_dung)")
    # Bản tóm tắt phần cũ để BẢNG RIÊNG, không chèn vào chat: chèn vào chat thì nó
    # mang id mới nhất, tức tóm tắt phần CŨ lại nằm CUỐI — đảo ngược trình tự.
    c.execute("CREATE TABLE IF NOT EXISTS chat_summary("
              "session TEXT PRIMARY KEY, content TEXT, den_id INTEGER, ts REAL)")
    c.commit()
    return c


# ─────────── TẦNG 1: trí nhớ dài hạn, xuyên cuộc ───────────

LOAI_NHO = ("so_thich", "quyet_dinh", "su_kien")


def nho(loai: str, noi_dung: str, ve: str = "", session: str = "") -> dict:
    c = _init_db()
    c.execute("INSERT INTO memory(loai,ve,noi_dung,session,ts) VALUES(?,?,?,?,?) "
              "ON CONFLICT(loai,ve,noi_dung) DO UPDATE SET ts=excluded.ts, lan_nhac=lan_nhac+1",
              (loai, ve or "", noi_dung.strip(), session, time.time()))
    c.commit(); c.close()
    return {"da_ghi_nho": noi_dung.strip(), "loai": loai, "ve": ve or "(chung)"}


def doc_nho(ve: str = "", loai: str = "", limit: int = 20) -> list:
    c = _init_db()
    w, a = [], []
    if ve:
        w.append("ve=?"); a.append(ve)
    if loai:
        w.append("loai=?"); a.append(loai)
    sql = "SELECT loai,ve,noi_dung,ts,lan_nhac FROM memory"
    if w:
        sql += " WHERE " + " AND ".join(w)
    rows = [dict(r) for r in c.execute(sql + " ORDER BY lan_nhac DESC, ts DESC LIMIT ?",
                                       a + [limit]).fetchall()]
    c.close()
    return rows


def _khoi_tri_nho(gioi_han_chu: int = 1200) -> str:
    """Bơm ký ức vào SYSTEM PROMPT chứ không vào lịch sử — để nó không bị cắt hay
    nén mất, và để agent không phải nhớ gọi tool mới nhớ ra."""
    ms = doc_nho(limit=TRI_NHO_BOM_VAO)
    if not ms:
        return ""
    dong = [f"- [{m['loai']}] " + (f"{m['ve']}: " if m["ve"] else "") + m["noi_dung"] for m in ms]
    khoi = "\n".join(dong)[:gioi_han_chu]
    return ("\n\nĐÃ BIẾT (nhớ từ các cuộc trò chuyện trước, dùng được ngay, "
            "không cần hỏi lại):\n" + khoi)


def history(session: str, limit: int = 40) -> list:
    c = _init_db()
    rows = c.execute("SELECT role, content, ts FROM chat WHERE session=? ORDER BY id DESC LIMIT ?",
                     (session, limit)).fetchall()
    c.close()
    return [dict(r) for r in reversed(rows)]


def sessions(limit: int = 40) -> list:
    """Danh sách cuộc trò chuyện cho thanh bên. Tiêu đề lấy câu ĐẦU TIÊN người
    dùng gõ — người ta nhớ cuộc trò chuyện qua việc mình đã hỏi gì, không nhớ id."""
    c = _init_db()
    rows = c.execute(
        "SELECT session, COUNT(*) n, MAX(ts) last_ts,"
        "  (SELECT content FROM chat c2 WHERE c2.session=chat.session AND c2.role='user'"
        "   ORDER BY c2.id LIMIT 1) title "
        "FROM chat GROUP BY session ORDER BY last_ts DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def _save(session: str, role: str, content: str):
    c = _init_db()
    c.execute("INSERT INTO chat(session,role,content,ts) VALUES(?,?,?,?)",
              (session, role, content, time.time()))
    c.commit(); c.close()


def _log_luot(session, vong, so_tool, model, ket_thuc, token_gui):
    c = _init_db()
    c.execute("INSERT INTO chat_log(session,vong,so_tool,model,ket_thuc,token_gui,ts) "
              "VALUES(?,?,?,?,?,?,?)",
              (session, vong, so_tool, model, ket_thuc, token_gui, time.time()))
    c.commit(); c.close()


def thong_ke_luot(limit: int = 200) -> dict:
    """Thực tế mỗi tin nhắn chạy mấy vòng gọi API — số liệu để chốt max_steps."""
    c = _init_db()
    rows = [dict(r) for r in c.execute(
        "SELECT vong, so_tool, model, ket_thuc, token_gui FROM chat_log "
        "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    c.close()
    if not rows:
        return {"so_luot": 0, "ghi_chu": "chưa có dữ liệu — dùng agent vài lượt rồi xem lại"}
    phan_bo = {}
    for r in rows:
        phan_bo[r["vong"]] = phan_bo.get(r["vong"], 0) + 1
    v = sorted(r["vong"] for r in rows)
    return {"so_luot": len(rows),
            "vong_trung_binh": round(sum(v) / len(v), 2),
            "vong_p90": v[int(len(v) * 0.9) - 1] if v else 0,
            "vong_toi_da": max(v),
            "phan_bo_vong": dict(sorted(phan_bo.items())),
            "token_gui_tb": round(sum(r["token_gui"] or 0 for r in rows) / len(rows)),
            "ket_thuc": {k: sum(1 for r in rows if r["ket_thuc"] == k)
                         for k in {r["ket_thuc"] for r in rows}}}


def _log_tool(session: str, ten: str, ket_qua: dict):
    c = _init_db()
    c.execute("INSERT INTO tool_log(session,tool,co_loi,ts) VALUES(?,?,?,?)",
              (session, ten, int(isinstance(ket_qua, dict) and "loi" in ket_qua), time.time()))
    c.commit(); c.close()


MAX_TOOL_LUU = 900      # cắt bớt kết quả tool trước khi lưu, khỏi phình lịch sử


def _save_tool(session: str, ten: str, args: dict, ket_qua):
    """Lưu CẢ tool đã gọi lẫn dữ liệu nó trả về.

    Trước đây chỉ lưu câu người dùng + câu trả lời cuối, nên lượt sau model không
    còn thấy dữ liệu thật nó từng đọc và phải suy đoán — đó là nguồn ảo giác lớn
    nhất của agent, và nó nằm ở tầng lưu trữ chứ không phải tầng prompt."""
    txt = json.dumps(ket_qua, ensure_ascii=False, default=str)
    if len(txt) > MAX_TOOL_LUU:
        txt = txt[:MAX_TOOL_LUU] + f"… (cắt bớt, gọi lại {ten} nếu cần đủ)"
    _save(session, "tool", json.dumps({"tool": ten, "tham_so": args, "ket_qua": txt},
                                      ensure_ascii=False))


def reset(session: str):
    c = _init_db()
    c.execute("DELETE FROM chat WHERE session=?", (session,))
    c.commit(); c.close()


# ─────────── TẦNG 2: transcript thô — cắt theo TOKEN, không theo số dòng ───────────

def _stub_tool(noi_dung: str, ts: float) -> str:
    """Dữ liệu tool cũ thu về một dòng: giữ việc ĐÃ TRA GÌ, bỏ số liệu.

    Số liệu cũ nằm lại trong bối cảnh còn nguy hiểm hơn là mất: lượt 3 tra được
    '26 tài nguyên', tới lượt 30 kho đã đổi mà model vẫn thấy câu đó và trả lời
    theo số cũ. Bỏ số, giữ dấu vết + mốc giờ, và nói rõ muốn chắc thì tra lại."""
    try:
        ten = json.loads(noi_dung).get("tool", "tool")
    except (ValueError, TypeError):
        ten = "tool"
    gio = time.strftime("%H:%M %d/%m", time.localtime(ts or time.time()))
    return (f"[đã tra {ten} lúc {gio} — số liệu chi tiết đã bỏ khỏi bối cảnh, "
            f"gọi lại {ten} nếu cần con số chính xác]")


def _tom_tat(session: str):
    c = _init_db()
    r = c.execute("SELECT content, den_id FROM chat_summary WHERE session=?", (session,)).fetchone()
    c.close()
    return dict(r) if r else None


def _rows_cho_boi_canh(session: str, limit: int = 300) -> list:
    """Dòng thô CHƯA nằm trong bản tóm tắt."""
    tt = _tom_tat(session)
    c = _init_db()
    rows = [dict(r) for r in c.execute(
        "SELECT id, role, content, ts FROM chat WHERE session=? AND id>? ORDER BY id",
        (session, (tt or {}).get("den_id", 0))).fetchall()][-limit:]
    c.close()
    return rows


def dung_lich_su(session: str, ngan_sach: int = NGAN_SACH_LICH_SU) -> list:
    """Dựng lại lịch sử trong NGÂN SÁCH token. Thứ tự hy sinh:
       1. dữ liệu tool cũ  ->  thu thành một dòng dấu vết (lấy lại được bằng cách gọi lại)
       2. dòng cũ nhất     ->  bỏ hẳn (lẽ ra đã được nén thành tóm tắt trước đó)
       Lời người dùng trong GIU_NGUYEN_VAN dòng gần nhất: không bao giờ đụng.
    """
    rows = _rows_cho_boi_canh(session)
    n = len(rows)
    ra, tong = [], 0
    tt = _tom_tat(session)
    if tt:
        tong += uoc_token(tt["content"])
    for i in range(n - 1, -1, -1):                # đi ngược từ mới nhất
        r = rows[i]
        moi = (n - i) <= GIU_NGUYEN_VAN
        noi_dung = r["content"] if (moi or r["role"] != "tool") \
            else _stub_tool(r["content"], r["ts"])
        gia = uoc_token(noi_dung)
        if tong + gia > ngan_sach and not moi:
            break                                  # hết ngân sách, dừng ở đây
        ra.append({"role": r["role"], "content": noi_dung})
        tong += gia
    ra.reverse()
    if tt:      # tóm tắt phần cũ luôn đứng ĐẦU, đúng trình tự thời gian
        ra.insert(0, {"role": "summary", "content": tt["content"]})
    return ra


def _nen_neu_can(session: str, client, model: str) -> dict | None:
    """Nén phần CŨ thành một bản tóm tắt. Kích hoạt bằng CODE khi vượt ngưỡng,
    KHÔNG để model tự gọi: model sẽ quên gọi lúc cần hoặc gọi lúc không nên, mà
    cái mất là ngữ cảnh — không lấy lại được."""
    rows = _rows_cho_boi_canh(session)
    if len(rows) <= GIU_NGUYEN_VAN + 4:
        return None
    tho = sum(uoc_token(r["content"]) for r in rows)
    if tho <= NGUONG_NEN:
        return None

    cu = rows[:-GIU_NGUYEN_VAN]
    van = "\n".join(f"{r['role']}: {r['content'][:600]}" for r in cu)
    from google.genai import types
    import sys as _s
    _s.path.insert(0, str(ROOT / "shorts"))
    import gemini_util
    nhac = ("Tóm tắt đoạn hội thoại dưới đây thành tối đa 8 gạch đầu dòng tiếng Việt. "
            "BẮT BUỘC giữ nguyên tên dự án/draft/editor và các con số. Bỏ lời khách sáo, "
            "bỏ dữ liệu tool chi tiết (tra lại được). Nêu rõ việc đã làm và điều đã chốt. "
            "Trả lời thẳng bằng gạch đầu dòng, không mở bài.\n\n" + van)
    try:
        resp, _ = gemini_util.generate_raw(
            client, model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=nhac)])],
            # Gemini 2.5 tính CẢ token suy nghĩ vào max_output_tokens: để 800 thì phần
            # trả lời bị cắt cụt giữa câu. Tóm tắt không cần suy nghĩ -> tắt hẳn.
            config=types.GenerateContentConfig(
                max_output_tokens=1200,
                thinking_config=types.ThinkingConfig(thinking_budget=0)))
        tom = "".join(p.text for p in resp.candidates[0].content.parts if getattr(p, "text", None))
    except Exception:
        return None                                # nén hỏng thì cứ để nguyên, không phá gì

    # KHÔNG lưu bản tóm tắt tệ. Dự án này từng trả giá đúng kiểu lỗi đó: cache một
    # kết quả rỗng rồi mọi lần sau dùng lại (WORKFLOW mục 9.6). Ở đây còn nặng hơn —
    # tóm tắt hỏng thì bối cảnh cuộc trò chuyện hỏng vĩnh viễn, không lấy lại được.
    tom = tom.strip()
    ma_can_giu = set(re.findall(r"\b\d{3,4}_t\d+_\w+\b|\b\d{4}\b", van))
    giu_duoc = sum(1 for m in ma_can_giu if m in tom)
    if (len(tom) < 120 or tom.rstrip()[-1] not in ".!?\"')]}0123456789"
            or (ma_can_giu and giu_duoc == 0)):
        return {"bo_qua": "bản tóm tắt không đạt (cụt hoặc mất hết mã định danh) — giữ nguyên lịch sử thô",
                "dai": len(tom), "ma_giu_duoc": f"{giu_duoc}/{len(ma_can_giu)}"}

    cu_truoc = _tom_tat(session)
    noi_dung = "[tóm tắt phần đầu cuộc trò chuyện]\n" + tom.strip()
    if cu_truoc:      # nén lần hai: gộp vào bản cũ, không để hai bản rời nhau
        noi_dung = cu_truoc["content"] + "\n" + noi_dung
    c = _init_db()
    c.execute("INSERT INTO chat_summary(session,content,den_id,ts) VALUES(?,?,?,?) "
              "ON CONFLICT(session) DO UPDATE SET content=excluded.content, "
              "den_id=excluded.den_id, ts=excluded.ts",
              (session, noi_dung, cu[-1]["id"], time.time()))
    c.commit(); c.close()
    return {"da_nen": len(cu), "tu_token": tho, "den_id": cu[-1]["id"]}


# ═══════════════════════ VÒNG LẶP AGENT ═══════════════════════

def _declarations(types, active: set):
    return [types.FunctionDeclaration(**TOOLS[n].khai_bao()) for n in active if n in TOOLS]


def _active_ban_dau() -> set:
    """Ít tool thì nạp hết cho nhanh. Nhiều lên thì nạp nhóm cốt lõi + tim_tool,
    model tự tra phần còn lại — không có bộ phân loại nào để mà chọn sai."""
    if len(TOOLS) <= NGUONG_NAP_HET:
        return set(TOOLS)
    return {n for n, t in TOOLS.items() if t.nhom in NHOM_COT_LOI or t.ten == "tim_tool"}


def chat(session: str, user_text: str, model: str = "gemini-2.5-flash",
         run_job=None, max_steps: int = 6) -> dict:
    """Một lượt chat. Trả {reply, steps, cho_xac_nhan}."""
    from google import genai
    from google.genai import types
    import sys as _s
    _s.path.insert(0, str(ROOT / "shorts"))
    import gemini_util

    contents = []
    for m in dung_lich_su(session):            # dựng trong ngân sách token, không lấy hết
        if m["role"] == "tool":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(
                text="[dữ liệu tool đã lấy ở lượt trước] " + m["content"])]))
        elif m["role"] == "summary":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(
                text="[bối cảnh đã nén của cuộc trò chuyện này]\n" + m["content"])]))
        else:
            contents.append(types.Content(role="user" if m["role"] == "user" else "model",
                                          parts=[types.Part.from_text(text=m["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
    _save(session, "user", user_text)

    client = genai.Client()
    active = _active_ban_dau()
    steps, cho_xac_nhan = [], None
    sys_prompt = SYS + _khoi_tri_nho()         # ký ức dài hạn đi kèm prompt, khỏi bị nén mất

    rong, vong, model_dung = 0, 0, model
    token_gui = sum(uoc_token(p.text) for ct in contents for p in ct.parts
                    if getattr(p, "text", None))
    for _ in range(max_steps):
        vong += 1
        cfg = types.GenerateContentConfig(
            system_instruction=sys_prompt,
            tools=[types.Tool(function_declarations=_declarations(types, active))],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=4000)
        try:
            resp, model_dung = gemini_util.generate_raw(
                client, model, contents=contents, config=cfg, chain=gemini_util.FALLBACKS_CHAT)
        except gemini_util.HetHanNgach as e:
            # Nói ĐÚNG nguyên nhân. Trước đây lỗi hạ tầng rơi vào câu "tôi gọi tool
            # hơi nhiều lượt" — người dùng đi sửa câu lệnh trong khi vấn đề là quota.
            reply = "Hết hạn ngạch Gemini rồi. " + str(e).split("—")[0].strip()
            _save(session, "model", reply)
            _log_luot(session, vong, len(steps), model_dung, "het_han_ngach", token_gui)
            return {"reply": reply, "steps": steps, "cho_xac_nhan": cho_xac_nhan,
                    "het_han_ngach": True}
        cand = (resp.candidates or [None])[0]
        if not cand or not cand.content or not cand.content.parts:
            # Gemini thỉnh thoảng trả candidate RỖNG. Trước đây break ngay -> người
            # dùng mất trắng cả lượt kèm câu "gọi tool nhiều quá" sai hoàn toàn.
            rong += 1
            if rong >= 2:
                reply = "Gemini trả về rỗng hai lần liền — bạn gửi lại câu vừa rồi giúp nhé."
                _save(session, "model", reply)
                _log_luot(session, vong, len(steps), model_dung, "rong", token_gui)
                return {"reply": reply, "steps": steps, "cho_xac_nhan": cho_xac_nhan}
            continue
        calls = [p.function_call for p in cand.content.parts if getattr(p, "function_call", None)]
        if not calls:
            reply = "".join(p.text for p in cand.content.parts if getattr(p, "text", None)) or "…"
            _save(session, "model", reply)
            _log_luot(session, vong, len(steps), model_dung, "tra_loi", token_gui)
            nen = _nen_neu_can(session, client, model)     # kích hoạt bằng CODE, không để model tự gọi
            return {"reply": reply, "steps": steps, "cho_xac_nhan": cho_xac_nhan, "da_nen": nen}

        contents.append(cand.content)
        parts = []
        for fc in calls:
            args = dict(fc.args or {})
            out = goi_tool(fc.name, args, run_job=run_job)
            _log_tool(session, fc.name, out)
            if isinstance(out, dict):
                if out.get("can_xac_nhan"):
                    cho_xac_nhan = {"hanh_dong": out["hanh_dong"], "tham_so": out["tham_so"],
                                    "canh_bao": out.get("canh_bao", "")}
                # tool tra cứu -> nạp thêm tool tìm được vào tầm với của lượt sau
                for m in out.get("tim_thay", []):
                    active.add(m["ten"])
            steps.append({"tool": fc.name, "args": args, "ket_qua": out})
            _save_tool(session, fc.name, args, out)
            parts.append(types.Part.from_function_response(name=fc.name, response={"result": out}))
        contents.append(types.Content(role="user", parts=parts))

    reply = "Tôi gọi tool hơi nhiều lượt mà chưa xong — bạn nói rõ hơn giúp nhé."
    _save(session, "model", reply)
    _log_luot(session, vong, len(steps), model_dung, "het_vong", token_gui)
    return {"reply": reply, "steps": steps, "cho_xac_nhan": cho_xac_nhan}


def xac_nhan(session: str, hanh_dong: str, tham_so: dict, run_job=None) -> dict:
    """Người dùng đã bấm nút -> giờ mới thật sự chạy việc phá huỷ."""
    t = TOOLS.get(hanh_dong)
    if not t or t.kieu != "nguy_hiem":
        return {"loi": "hành động này không cần xác nhận hoặc không tồn tại"}
    out = goi_tool(hanh_dong, tham_so, run_job=run_job, cho_phep_nguy_hiem=True)
    _log_tool(session, hanh_dong, out)
    _save_tool(session, hanh_dong, tham_so, out)
    ghi = f"Đã xác nhận và chạy: {hanh_dong}({json.dumps(tham_so, ensure_ascii=False)})"
    _save(session, "model", ghi)
    return {"ket_qua": out, "ghi_chu": ghi}


def thong_ke_tool(limit: int = 20) -> list:
    """Tool nào hay bị lỗi — số liệu để quyết định có cần router hay không."""
    c = _init_db()
    rows = [dict(r) for r in c.execute(
        "SELECT tool, COUNT(*) lan, SUM(co_loi) loi FROM tool_log "
        "GROUP BY tool ORDER BY lan DESC LIMIT ?", (limit,)).fetchall()]
    c.close()
    return rows
