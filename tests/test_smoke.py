# -*- coding: utf-8 -*-
"""Smoke test — chạy sau mỗi lần sửa và ngay sau khi cài trên máy mới.

KHÔNG phải bộ test đầy đủ. Mục tiêu hẹp: bắt những thứ mà nếu hỏng thì app vô
dụng, và bắt lại đúng các lỗi ĐÃ TỪNG xảy ra trong dự án — vì lỗi đã xảy ra một
lần thì hay quay lại:

  * hardcode đường dẫn máy dev  (SFX rỗng trên máy khác, im lặng)
  * mốc so với chính nó lại báo có thay đổi  (chỉ số độ phải sửa nói dối)
  * model dự phòng không tồn tại  (cơ chế xoay model thành vô dụng)
  * tham số tool sai hoa/dấu -> trả rỗng thay vì lỗi  (agent bịa số liệu)
  * việc phá huỷ tự chạy không hỏi  (mất draft editor vừa sửa)

Chạy: python -m pytest -q tests
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "shorts"))

import assetlib                                   # noqa: E402


# ─────────────── nền tảng ───────────────

def test_import_moi_module():
    """Mọi module chính phải import được — bắt lỗi cú pháp và import vòng."""
    import agent, app, asset_restore, audio_balance, capcut_inventory  # noqa: F401
    import capcut_auto, capcut_build, draft_diff, draft_scan           # noqa: F401


def test_thu_muc_du_lieu_tu_tao(tmp_path, monkeypatch):
    monkeypatch.setattr(assetlib, "ROOT", tmp_path)
    tao = assetlib.khoi_tao()
    assert set(tao) == set(assetlib.THU_MUC_DU_LIEU)
    for r in assetlib.THU_MUC_DU_LIEU:
        assert (tmp_path / r).is_dir()


def test_do_capcut_khong_crash_khi_chua_cai(monkeypatch):
    """Máy chưa cài CapCut vẫn phải trả đường dẫn dùng được, found=False."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("CAPCUT_DRAFTS_ROOT", raising=False)
    d = assetlib.find_capcut(refresh=True)
    assert d["found"] is False and isinstance(d["draft"], Path)
    assetlib.find_capcut(refresh=True)             # trả lại trạng thái thật


def test_khong_con_hardcode_may_dev():
    """Đường dẫn máy dev chỉ được xuất hiện như NGUỒN PHỤ, không phải nguồn duy nhất."""
    xau = ("Users/Acer", "Users\\\\Acer")
    for f in list(ROOT.glob("*.py")) + list((ROOT / "shorts").glob("*.py")):
        t = f.read_text(encoding="utf-8", errors="replace")
        for dong in t.splitlines():
            if dong.strip().startswith("#") or '"""' in dong:
                continue
            assert not any(x in dong for x in xau), f"{f.name}: còn hardcode -> {dong.strip()[:70]}"


# ─────────────── SFX: lỗi hỏng im lặng đã từng gặp ───────────────

def test_sfx_co_san_khong_can_thu_muc_may_dev():
    kho = assetlib.sfx_kho("Z:/thu-muc-khong-ton-tai")
    assert len(kho) >= 20, "kho SFX mặc định phải đi theo app"
    assert all(Path(p).exists() for p in kho.values())


# ─────────────── chỉ số độ phải sửa ───────────────

def test_van_tay_so_voi_chinh_no_phai_bang_khong():
    """Bug đã gặp: ghép caption bằng dict khoá theo chữ -> caption trùng chữ bị so
    nhầm dòng -> so mốc với chính nó vẫn ra 'đổi giờ 18 dòng'."""
    import draft_diff as dd
    goc = {"caption": [{"t": "cùng một câu", "s": i * 1_000_000, "d": 900_000} for i in range(30)],
           "video": [{"s": 0, "d": 5_000_000}], "am_luong": {"a.mp3": 0.5}, "tong_dai": 5_000_000}
    s = dd._so_van_tay(goc, goc)
    assert s["caption"] == {"tong": 30, "sua_hoac_them": 0, "bo": 0, "doi_gio": 0}
    assert dd._diem(s, 0, 0) == 0.0


def test_diem_phai_sua_tang_theo_muc_do_sua():
    import copy

    import draft_diff as dd
    goc = {"caption": [{"t": f"câu {i}", "s": i * 1_000_000, "d": 900_000} for i in range(20)],
           "video": [{"s": 0, "d": 5_000_000}], "am_luong": {"a.mp3": 0.5}, "tong_dai": 5_000_000}
    nhe = copy.deepcopy(goc); nhe["caption"][0]["t"] = "đã sửa"
    nang = copy.deepcopy(goc); nang["caption"] = nang["caption"][:3]
    d_nhe = dd._diem(dd._so_van_tay(goc, nhe), 0, 0)
    d_nang = dd._diem(dd._so_van_tay(goc, nang), 0, 0)
    assert 0 < d_nhe < d_nang <= 1.0


# ─────────────── agent ───────────────

def test_registry_tool_hop_le():
    import agent
    assert len(agent.TOOLS) >= 10
    for t in agent.TOOLS.values():
        assert t.kieu in ("doc", "nen", "nguy_hiem")
        assert t.mo_ta.strip() and t.tham_so.get("type") == "object"
        if t.kieu == "nguy_hiem":
            assert t.canh_bao.strip(), f"{t.ten}: việc phá huỷ phải có cảnh báo"


def test_thieu_tham_so_tra_loi_co_cau_truc():
    """Không được ném TypeError của Python vào mặt model."""
    import agent
    r = agent.goi_tool("xem_editor_sua_gi", {})
    assert r.get("thieu") == ["draft"] and "goi_y" in r


def test_chuan_hoa_tham_so_hoa_dau():
    """Bug đã gặp: owner='Đan' -> lọc ra RỖNG mà không báo lỗi -> agent nói
    'Đan chưa có tài nguyên nào'. Sai sự thật, không bắt được."""
    import agent
    ds = agent._ds_editor()
    if "dan" not in ds:
        pytest.skip("máy này chưa có editor 'dan' trong kho")
    r = agent.goi_tool("kho_tai_nguyen", {"owner": "Đan"})
    assert "loi" not in r and r["tong_theo_bo_loc"] > 0


def test_gia_tri_sai_tra_kem_lua_chon_hop_le():
    import agent
    r = agent.goi_tool("kho_tai_nguyen", {"owner": "KhongCoAi"})
    assert "gia_tri_hop_le" in r and r["gia_tri_hop_le"]


def test_viec_pha_huy_khong_tu_chay():
    """Agent chỉ được ĐỀ XUẤT; chạy thật phải qua nút xác nhận.

    Dùng dự án CÓ THẬT: chuẩn hoá tham số chạy TRƯỚC cổng xác nhận (đúng thứ tự —
    tham số sai thì báo sai tham số, không đề xuất một việc vô nghĩa)."""
    import agent
    ds = agent._ds_du_an()
    if not ds:
        pytest.skip("máy này chưa có dự án nào đã phân tích")
    r = agent.goi_tool("dung_draft", {"project": ds[0], "topic": 1})
    assert r.get("can_xac_nhan") is True and r.get("canh_bao")


def test_cat_boi_canh_giu_loi_nguoi_dung_bo_du_lieu_tool():
    """Ngân sách token: hy sinh dữ liệu tool (gọi lại được), giữ lời người dùng."""
    import agent
    ss = "test_smoke_ctx"
    agent.reset(ss)
    c = agent._init_db(); c.execute("DELETE FROM chat_summary WHERE session=?", (ss,))
    c.commit(); c.close()
    try:
        for i in range(15):
            agent._save(ss, "user", f"câu hỏi {i}")
            agent._save_tool(ss, "kho_tai_nguyen", {}, {"x": "y" * 400})
        ls = agent.dung_lich_su(ss, ngan_sach=1200)
        assert sum(1 for m in ls if m["role"] == "user") == 15
        assert any(m["content"].startswith("[đã tra") for m in ls)
        assert sum(agent.uoc_token(m["content"]) for m in ls) <= 1200 * 1.1
    finally:
        agent.reset(ss)


# ─────────────── gọi Gemini ───────────────

def test_chuoi_model_du_phong_khong_rong():
    """Bug đã gặp: chuỗi dự phòng chứa model 404 -> 404 không phải lỗi quá tải nên
    vòng thử lại bỏ qua, cả cơ chế dự phòng thành vô dụng."""
    import gemini_util
    assert gemini_util.FALLBACKS and gemini_util.FALLBACKS_CHAT
    assert gemini_util.FALLBACKS_CHAT[0].endswith("-lite"), \
        "chuỗi chat phải ưu tiên model RPD cao"


@pytest.mark.skipif(not assetlib.load_env() and not __import__("os").environ.get("GEMINI_API_KEY"),
                    reason="chưa có GEMINI_API_KEY")
def test_model_trong_chuoi_du_phong_deu_ton_tai():
    import os

    from google import genai

    import gemini_util
    cl = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    co = {m.name.replace("models/", "") for m in cl.models.list()}
    thieu = [m for m in set(gemini_util.FALLBACKS + gemini_util.FALLBACKS_CHAT) if m not in co]
    assert not thieu, f"model không tồn tại với key này: {thieu}"


# ─────────────── API ───────────────

def test_api_khong_lo_key():
    """Màn hình Cài đặt chỉ được trả key dạng che."""
    import app
    d = app.api_settings()
    for n in d["nha_cung_cap"]:
        assert "…" in n["che"] or n["che"] in ("", "đã có")
        assert len(n["che"]) < 20


def test_api_chinh_tra_ve_duoc():
    import app
    assert "drafts" in app.api_drafts()
    assert "projects" in app.api_projects()
    assert "stats" in app.api_inventory(limit=1)
    ov = app.api_overview()
    assert {"projects", "todo", "capcut"} <= set(ov)


def test_mo_thu_muc_chan_di_ra_ngoai():
    import app
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        app.api_draft_open("khong-ton-tai-dau")


def test_pick_khong_goi_python_dash_c(monkeypatch):
    """Bắt lại lỗi 30/07: /api/pick gọi `sys.executable -c <code>` để mở tkinter.

    Ở bản .exe đóng gói, sys.executable CHÍNH LÀ CapCutAuto.exe — nó không hiểu cờ
    `-c`, nên lệnh đó vô tình mở thêm một bản app thứ hai (tranh cổng 8765 với bản
    gốc, chết ngay, và dòng chào "App: ..." của nó bị nhặt nhầm làm đường dẫn vừa
    chọn). Phải gọi qua cờ `--pick` để tiến trình con chạy đúng nhánh tkinter."""
    import app
    goi = {}

    def gia_run(lenh, **kw):
        goi["lenh"] = lenh
        class R: stdout = "C:/gia/duong/dan\n"; stderr = ""
        return R()

    monkeypatch.setattr(app.subprocess, "run", gia_run)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    app.api_pick(kieu="thu_muc")
    assert goi["lenh"] == [sys.executable, "--pick", "thu_muc"], \
        "đóng gói: gọi lại CHÍNH .exe kèm --pick, không phải -c"

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    app.api_pick(kieu="file")
    assert goi["lenh"] == [sys.executable, app.__file__, "--pick", "file"], \
        "chạy nguồn: phải kèm đường dẫn app.py thì python.exe mới biết chạy gì"

    for lenh in (goi["lenh"],):
        assert "-c" not in lenh, "lỡ quay lại cách gọi -c là tái phát đúng lỗi 30/07"


def test_giao_dien_khong_dung_hop_thoai_trinh_duyet():
    """docs/UI.md mục 5: alert/confirm/prompt bị cấm."""
    t = (ROOT / "ui.html").read_text(encoding="utf-8")
    for cam in ("alert(", "confirm(", "prompt("):
        for dong in t.splitlines():
            truoc = dong.split(cam)[0]
            la_ghi_chu = "//" in truoc or "/*" in truoc or dong.strip().startswith(("*", "/*"))
            if cam in dong and "confirmBox" not in dong and not la_ghi_chu:
                pytest.fail(f"ui.html còn dùng {cam} -> {dong.strip()[:60]}")


# ─────────────── draft mẫu (donor) — lỗi bắt được trên máy trạm 26/07 ───────────────

def test_draft_mau_di_theo_app():
    """Bug đã gặp: donor '282new' chỉ nằm trong thư mục CapCut của máy dev. Máy khác
    build chạy hết 10 phút rồi mới chết ở dòng cuối vì FileNotFoundError."""
    import capcut_build as cb
    for ten in {cb.DONOR_VIDEO, "282new"}:
        p = cb.DONOR_DIR / ten
        if p.is_dir():
            assert (p / "draft_content.json").is_file()
            return
    pytest.fail("không có draft mẫu nào trong assets/donor/ — máy mới sẽ không build được")


def test_draft_mau_doi_duong_dan_cache_ve_may_dang_chay(monkeypatch):
    """Draft mẫu giữ đường dẫn cache của máy làm ra nó -> máy khác mở là CapCut
    đòi chọn lại file."""
    import json as _j
    import capcut_build as cb
    monkeypatch.setattr(assetlib, "cache_root",
                        lambda: Path(r"C:/May/Khac/CapCut/User Data/Cache"))
    s = _j.dumps(cb.load_draft("282new"), ensure_ascii=False)
    assert "May/Khac" in s, "không đổi đường dẫn cache sang máy đang chạy"
    assert "Users/Acer" not in s.replace("\\", "/"), "còn sót đường dẫn máy dev"


def test_bao_ngay_khi_thieu_draft_mau():
    import capcut_build as cb
    with pytest.raises(FileNotFoundError):
        cb.kiem_tra_draft_mau("khong-co-draft-mau-nay")


# ─────────────── EQ Gym AI Editor — dựng draft theo kịch bản CSV ───────────────

def test_doc_kich_ban_csv_doc_dung_cot(tmp_path):
    import capcut_build as cb
    p = tmp_path / "kich_ban.csv"
    p.write_text(
        "Scene,Duration,Prompt,VO,Img1Name,Img1Data\n"
        'C01,10,"prompt dài dòng, có phẩy",Xin chào các bạn,nv_hana.png,AAAA\n'
        'C02,8.5,khác,Hôm nay chúng ta học EQ,nv_vy.png,BBBB\n',
        encoding="utf-8-sig")
    canh = cb.doc_kich_ban_csv(p)
    assert [c["scene"] for c in canh] == ["C01", "C02"], "phải giữ ĐÚNG thứ tự dòng — đó là thứ tự timeline"
    assert canh[0]["duration_s"] == 10.0
    assert canh[1]["duration_s"] == 8.5
    assert canh[0]["vo"] == "Xin chào các bạn"


def test_doc_kich_ban_csv_thieu_cot_bat_buoc_bao_ro(tmp_path):
    """Thiếu cột Duration/VO thì phải báo NGAY lúc đọc CSV, không phải lúc dựng
    draft giữa chừng mới lộ ra thiếu gì."""
    import capcut_build as cb
    p = tmp_path / "thieu_cot.csv"
    p.write_text("Scene,Prompt\nC01,abc\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="thiếu cột"):
        cb.doc_kich_ban_csv(p)


def test_doc_kich_ban_csv_duration_khong_hop_le_bao_ro(tmp_path):
    import capcut_build as cb
    p = tmp_path / "duration_hong.csv"
    p.write_text("Scene,Duration,VO\nC01,0,chào\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Duration"):
        cb.doc_kich_ban_csv(p)


def test_tim_nguon_canh_khop_dung_ten_truoc_ten_co_hau_to(tmp_path):
    """Nhiều file cùng khớp tiền tố Scene (C01.mp4 và C01_v2.mp4) thì phải ưu tiên
    tên TRÙNG KHỚP TUYỆT ĐỐI — người dùng chủ động chọn bản chính bằng cách đặt tên
    đúng, không đoán bản nào 'mới hơn' hộ họ."""
    import capcut_build as cb
    (tmp_path / "C01_v2.mp4").write_bytes(b"x")
    (tmp_path / "C01.mp4").write_bytes(b"x")
    got = cb.tim_nguon_canh("C01", tmp_path)
    assert got.name == "C01.mp4"


def test_tim_nguon_canh_khong_phan_biet_hoa_thuong(tmp_path):
    import capcut_build as cb
    (tmp_path / "c01.png").write_bytes(b"x")
    got = cb.tim_nguon_canh("C01", tmp_path)
    assert got.name == "c01.png"


def test_tim_nguon_canh_khong_co_thi_tra_ve_none(tmp_path):
    """Không tìm thấy trả None (không ném lỗi ở đây) — build_from_csv gom hết các
    scene thiếu rồi báo MỘT LƯỢT, thay vì dừng ngay ở scene đầu tiên thiếu."""
    import capcut_build as cb
    assert cb.tim_nguon_canh("C99", tmp_path) is None


def _gia_words(cau: str, bat_dau_s: float, moi_chu_s: float = 0.5):
    """Biến một câu thành list word-timestamp giả giống faster-whisper trả về."""
    ra = []
    t = bat_dau_s
    for w in cau.split():
        ra.append({"w": " " + w, "s": int(t * 1000), "e": int((t + moi_chu_s) * 1000)})
        t += moi_chu_s
    return ra


def test_khop_canh_vao_voice_khong_theo_thu_tu_csv():
    """Bắt lại phát hiện 03/08 trên dữ liệu EQ Gym thật: voice đọc C01..C15 rồi
    NHẢY sang C18..C21 rồi mới quay lại C16,C17 — kịch bản CSV được xếp lại SAU khi
    thu tiếng. Ghép tuần tự theo thứ tự CSV là toàn bộ nửa sau lệch hẳn."""
    import capcut_build as cb
    canh = [
        {"scene": "C1", "vo": "hôm nay chúng ta bắt đầu buổi tập cảm xúc"},
        {"scene": "C2", "vo": "phần kết xin cảm ơn các bạn đã lắng nghe"},
        {"scene": "C3", "vo": "bài học thứ hai nói về sự kiên nhẫn mỗi ngày"},
    ]
    # voice đọc theo thứ tự C1 -> C3 -> C2 (khác CSV)
    words = (_gia_words(canh[0]["vo"], 0)
             + _gia_words(canh[2]["vo"], 10)
             + _gia_words(canh[1]["vo"], 20))
    da = cb._khop_canh_vao_voice(canh, words)
    assert len(da) == 3, "phải khớp được cả 3 cảnh"
    thu_tu = sorted(range(3), key=lambda i: da[i][0])
    assert [canh[i]["scene"] for i in thu_tu] == ["C1", "C3", "C2"], \
        "phải xếp theo thứ tự VOICE đọc, không phải thứ tự dòng CSV"


def test_khop_canh_canh_gan_trung_loi_khong_cuop_cho_nhau():
    """Bắt lại lỗi thật: C18 và C23 của EQ Gym cùng kết bằng 'để làm chủ bản thân,
    kết nối người khác và sống đúng với điều quan trọng nhất'. Chấm điểm độc lập thì
    cả hai cùng đòi một chỗ và cảnh khớp YẾU hơn cướp mất chỗ của cảnh khớp chắc —
    nên phải giành chỗ theo độ tin cậy (best-first) rồi che vùng đã giành."""
    import capcut_build as cb
    chung = "để làm chủ bản thân kết nối người khác và sống đúng với điều quan trọng nhất"
    canh = [
        {"scene": "A", "vo": "mở đầu hành trình ba mươi ngày " + chung},
        {"scene": "B", "vo": "tóm lại toàn bộ chương trình " + chung},
    ]
    words = (_gia_words(canh[0]["vo"], 0) + _gia_words("một đoạn khác xen giữa", 30)
             + _gia_words(canh[1]["vo"], 40))
    da = cb._khop_canh_vao_voice(canh, words)
    assert len(da) == 2, "hai cảnh gần trùng lời vẫn phải ra hai vị trí khác nhau"
    assert da[0][0] < da[1][0], "cảnh đọc trước phải nằm trước trên timeline"
    assert not (da[0][0] <= da[1][0] < da[0][1]), "hai cảnh không được chồng vùng"


def test_khop_canh_bo_qua_canh_khong_co_trong_voice():
    """Voice không đọc cảnh nào thì cảnh đó KHÔNG được bịa chỗ — trả về thiếu để
    tầng trên báo tên và bỏ khỏi timeline (luật cứng #2: không hỏng im lặng)."""
    import capcut_build as cb
    canh = [
        {"scene": "A", "vo": "một hai ba bốn năm sáu bảy tám chín mười"},
        {"scene": "B", "vo": "hoàn toàn không xuất hiện trong bản thu tiếng này"},
    ]
    words = _gia_words(canh[0]["vo"], 0)
    da = cb._khop_canh_vao_voice(canh, words)
    assert 0 in da and 1 not in da, "cảnh không có trong voice phải bị bỏ, không đoán bừa"


def test_doc_kich_ban_xls_lay_du_ca_slide(tmp_path):
    """Bảng 'lưu ý CapCut' (.xls) mới là bản thiết kế thật: nó có đủ 28 dòng theo
    đúng thứ tự dựng, trong đó xen 5 SLIDE CHỮ im lặng mà file CSV (chỉ có 23 cảnh
    AI-gen) KHÔNG hề nhắc tới. Dựng thiếu slide là hỏng cả bố cục bài."""
    import zipfile
    import capcut_build as cb
    xlsx = tmp_path / "luu_y.xlsx"
    hang = [
        ("STT", "Loại", "ID", "Dài (s)", "VO", "", "File ảnh cần chèn"),
        ("1", "RENDER", "C01", "10", "xin chào các bạn", "", ""),
        ("2", "SLIDE", "S1", "3", "(KHÔNG LỜI — slide chữ)", "", "slides/S1.png"),
        ("3", "RENDER", "C02", "8", "hôm nay học gì", "", ""),
    ]
    def o_xml(r, c, v):
        return (f'<c r="{chr(65+c)}{r}" t="inlineStr"><is><t>'
                f'{v.replace("&","&amp;").replace("<","&lt;")}</t></is></c>')
    rows = "".join(f'<row r="{i+1}">' + "".join(o_xml(i + 1, j, v) for j, v in enumerate(h))
                   + "</row>" for i, h in enumerate(hang))
    sheet = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
             f'spreadsheetml/2006/main"><sheetData>{rows}</sheetData></worksheet>')
    with zipfile.ZipFile(xlsx, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)

    canh = cb.doc_kich_ban(xlsx)
    assert [c["scene"] for c in canh] == ["C01", "S1", "C02"], "phải giữ đúng thứ tự dựng"
    assert canh[1]["loai"] == "slide" and canh[1]["anh"] == "slides/S1.png"
    assert canh[1]["vo"] == "", \
        "ô VO của slide là ghi chú '(KHÔNG LỜI...)', không phải câu để đi tìm trong bản thu"
    assert canh[0]["loai"] == "render" and canh[0]["duration_s"] == 10


def test_doc_kich_ban_xls_phan_biet_clip_nhep_moi_va_cam(tmp_path):
    """Bảng bài 2 ghi rõ hai loại clip trong cột 'Hướng dẫn CapCut', và đây là thứ
    quyết định cách dựng khác hẳn nhau: 'CÓ TIẾNG — Yuki nhép môi' phải bám khẩu
    hình (tốc độ chỉ nhích quanh 1.0), còn 'CÂM HOÀN TOÀN' thì cắt bớt thoải mái."""
    import zipfile
    import capcut_build as cb
    hang = [
        ("STT", "Loại", "ID", "Dài (s)", "VO", "", "", "Hướng dẫn CapCut"),
        ("1", "RENDER", "2-01", "8", "xin chào", "", "", "CÓ TIẾNG — Yuki nhép môi, MP3 bám nhịp"),
        ("2", "RENDER", "2-02", "6", "cảnh minh hoạ", "", "", "CÂM HOÀN TOÀN — MP3 co giãn tự do"),
        ("3", "SLIDE", "S1", "3", "(KHÔNG LỜI)", "", "slides/S1.png", "Thẻ tĩnh 3 giây"),
    ]
    def o_xml(r, c, v):
        return (f'<c r="{chr(65+c)}{r}" t="inlineStr"><is><t>'
                f'{v.replace("&","&amp;").replace("<","&lt;")}</t></is></c>')
    rows = "".join(f'<row r="{i+1}">' + "".join(o_xml(i + 1, j, v) for j, v in enumerate(h))
                   + "</row>" for i, h in enumerate(hang))
    xlsx = tmp_path / "b.xlsx"
    with zipfile.ZipFile(xlsx, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml",
                   '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
                   f'spreadsheetml/2006/main"><sheetData>{rows}</sheetData></worksheet>')
    canh = {c["scene"]: c for c in cb.doc_kich_ban(xlsx)}
    assert canh["2-01"]["nhep_moi"] is True
    assert canh["2-02"]["nhep_moi"] is False
    assert canh["S1"]["nhep_moi"] is False, "slide không có miệng nào để khớp"


def test_doc_overlay_xls_lay_the_tieu_de_de_len_clip(tmp_path):
    """Bài 12 có 9 ảnh slide nhưng bảng chính CHỈ dùng 2 làm đoạn riêng; 7 cái còn
    lại là THẺ TIÊU ĐỀ đè 2 giây lên đầu clip ("KHÔNG dựng thành đoạn chữ tĩnh
    riêng"). Bảng chính để trống cột ảnh cho các dòng đó — cặp file ↔ clip chỉ có ở
    sheet phụ. Bỏ qua sheet phụ là mất trắng 7 thẻ chuyển khối của bài."""
    import zipfile
    import capcut_build as cb
    def sheet(hang):
        def o(r, c, v):
            return (f'<c r="{chr(65+c)}{r}" t="inlineStr"><is><t>'
                    f'{v.replace("&","&amp;").replace("<","&lt;")}</t></is></c>')
        rows = "".join(f'<row r="{i+1}">' + "".join(o(i + 1, j, v) for j, v in enumerate(h))
                       + "</row>" for i, h in enumerate(hang))
        return ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
                f'spreadsheetml/2006/main"><sheetData>{rows}</sheetData></worksheet>')
    xlsx = tmp_path / "b.xlsx"
    with zipfile.ZipFile(xlsx, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet([
            ("STT", "Loại", "ID", "Dài (s)", "VO", "", "", "HD"),
            ("1", "RENDER", "12-03", "6", "abc", "", "", "CÂM"),
        ]))
        z.writestr("xl/worksheets/sheet2.xml", sheet([
            ("File", "Nguồn", "Dùng cho"),
            ("slides/SLIDE_03_11-bai-hoc.png", "Claude dựng",
             "OVERLAY 2 giây lên đầu clip 12-03 — overlay lên clip mở khối"),
            ("slides/SLIDE_01_canvas.png", "Claude dựng",
             "Đoạn SL-01 — slide riêng, im lặng 5 giây"),
        ]))
    ov = cb.doc_overlay_xls(xlsx)
    assert ov == {"12-03": ("slides/SLIDE_03_11-bai-hoc.png", 2.0)}, \
        "chỉ lấy dòng OVERLAY, bỏ qua slide dựng thành đoạn riêng"
    assert cb.doc_overlay_xls(tmp_path / "khong-co.csv") == {}, "CSV thì không có sheet phụ"


def test_kho_tram_lay_dung_muc_va_khong_dung_lai(tmp_path):
    """Clip trám đánh số theo MỤC (1-x, 2-x...) vì mỗi slide đóng lại một mục —
    lấy đúng mục thì cảnh trám còn ăn nhập bối cảnh. Và không được dùng lại một
    clip: lặp đúng một cảnh B-roll trong cùng bài là người xem nhận ra ngay."""
    import subprocess as sp
    import shutil
    import capcut_build as cb
    if not shutil.which("ffmpeg"):
        pytest.skip("máy này không có ffmpeg")
    for ten in ("1-1", "2-1", "2-2"):
        sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                "testsrc=size=64x64:rate=10:duration=3", "-an", str(tmp_path / f"{ten}.mp4")],
               check=True, capture_output=True)
    kho = cb._doc_kho_tram(tmp_path)
    assert set(kho) == {1, 2} and len(kho[2]) == 2

    da = set()
    a = cb._lay_clip_tram(kho, 2, 1_000_000, da)
    assert a.stem.startswith("2-"), "phải ưu tiên clip cùng mục"
    b = cb._lay_clip_tram(kho, 2, 1_000_000, da)
    assert b != a, "không được trả lại clip đã dùng"
    c = cb._lay_clip_tram(kho, 2, 1_000_000, da)
    assert c is not None and c.stem.startswith("1-"), "hết clip cùng mục thì lan sang mục khác"
    assert cb._lay_clip_tram(kho, 2, 1_000_000, da) is None, "hết sạch thì trả None để quay về giữ khung"
    assert cb._lay_clip_tram(kho, 1, 99_000_000, set()) is None, "clip ngắn hơn chỗ hụt thì bỏ qua"


def test_tim_nguon_canh_theo_ten_anh_bo_phan_thu_muc(tmp_path):
    """Bảng ghi 'slides/SLIDE_1_....png' theo cấu trúc dự định, còn thực tế người
    dùng để phẳng cùng một chỗ — phải tìm theo TÊN FILE, bỏ phần thư mục."""
    import capcut_build as cb
    (tmp_path / "SLIDE_1_tai-sao.png").write_bytes(b"x")
    got = cb.tim_nguon_canh("S1", tmp_path, "slides/SLIDE_1_tai-sao.png")
    assert got is not None and got.name == "SLIDE_1_tai-sao.png"


def _dung_bai_thu(tmp_path, cb, hang, so_giay_voice=6.0, **kw):
    """Dựng một draft tí hon từ bảng kịch bản cho sẵn — dùng chung cho các bài test
    cần soi timeline thật thay vì suy luận."""
    import subprocess as sp
    import zipfile
    src = tmp_path / "src"; src.mkdir(exist_ok=True)
    for h in hang[1:]:
        ma, loai = h[2], h[1]
        if loai == "SLIDE":
            sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64",
                    "-frames:v", "1", str(src / f"{ma}.png")], check=True, capture_output=True)
        else:
            sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    f"testsrc=size=64x64:rate=10:duration={h[3]}", "-an",
                    str(src / f"{ma}.mp4")], check=True, capture_output=True)
    voice = tmp_path / "v.mp3"
    sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
            f"sine=frequency=440:duration={so_giay_voice}", str(voice)],
           check=True, capture_output=True)

    def o_xml(r, c, v):
        return (f'<c r="{chr(65+c)}{r}" t="inlineStr"><is><t>'
                f'{str(v).replace("&","&amp;").replace("<","&lt;")}</t></is></c>')
    rows = "".join(f'<row r="{i+1}">' + "".join(o_xml(i + 1, j, v) for j, v in enumerate(h))
                   + "</row>" for i, h in enumerate(hang))
    xlsx = tmp_path / "kb.xlsx"
    with zipfile.ZipFile(xlsx, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml",
                   '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
                   f'spreadsheetml/2006/main"><sheetData>{rows}</sheetData></worksheet>')
    out = tmp_path / "drafts"; out.mkdir(exist_ok=True)
    cb.DRAFTS_ROOT = out
    cb.build_from_csv(xlsx, src, voice, "T", do_write=True, **kw)
    return json.loads((out / "T" / "draft_content.json").read_text(encoding="utf-8"))


def test_hai_slide_lien_ke_khong_chong_lan_hinh(tmp_path, monkeypatch):
    """Bắt lại lỗi 03/08 trên bài 2 thật: IMG01 và S6 nằm SÁT NHAU, xử lý riêng lẻ
    thì CẢ HAI cùng đòi một khoảng tiếng giữa hai cụm clip -> cộng đôi, hình chồng
    lấn 1,4 giây trên timeline."""
    import shutil
    import capcut_build as cb
    if not shutil.which("ffmpeg"):
        pytest.skip("máy này không có ffmpeg")
    try:
        cb.kiem_tra_draft_mau(cb.DONOR_VIDEO)
    except FileNotFoundError:
        pytest.skip("không có draft mẫu")
    # Giả lập kết quả bóc lời: C01 đọc ở 0-3s, NGHỈ 0,5s, C02 đọc ở 3,5-6,5s.
    # Phải đi qua đúng nhánh đồng bộ giọng thì mới chạm được logic chia slide —
    # nhánh xếp theo cột Duration không có chỗ nào để lỗi này lộ ra.
    def gia_asr(path, model="small"):
        def w(t, tu):
            return {"w": " " + tu, "s": int(t * 1000), "e": int((t + 0.9) * 1000)}
        return [{"text": "một hai ba", "start_ms": 0, "end_ms": 3000,
                 "words": [w(0, "một"), w(1, "hai"), w(2, "ba")]},
                {"text": "bốn năm sáu", "start_ms": 3500, "end_ms": 6500,
                 "words": [w(3.5, "bốn"), w(4.5, "năm"), w(5.5, "sáu")]}]
    monkeypatch.setattr(cb, "transcribe", gia_asr)
    goc = cb.DRAFTS_ROOT
    try:
        d = _dung_bai_thu(tmp_path, cb, [
            ("STT", "Loại", "ID", "Dài (s)", "VO", "", "File ảnh cần chèn", "HD"),
            ("1", "RENDER", "C01", "3", "một hai ba", "", "", "CÓ TIẾNG"),
            ("2", "SLIDE", "S1", "2", "(KHÔNG LỜI)", "", "", "thẻ tĩnh"),
            ("3", "SLIDE", "S2", "2", "(KHÔNG LỜI)", "", "", "thẻ tĩnh"),
            ("4", "RENDER", "C02", "3", "bốn năm sáu", "", "", "CÂM HOÀN TOÀN"),
        ])
    finally:
        cb.DRAFTS_ROOT = goc
    vt = next(t for t in d["tracks"] if t["type"] == "video")
    segs = sorted(vt["segments"], key=lambda s: s["target_timerange"]["start"])
    for a, b in zip(segs, segs[1:]):
        het = a["target_timerange"]["start"] + a["target_timerange"]["duration"]
        assert abs(het - b["target_timerange"]["start"]) <= 1000, \
            "hai slide liền kề làm hình chồng lấn/hở — mỗi khoảng tiếng chỉ được tính MỘT lần"


def test_voice_khong_mang_metadata_nhac_online(tmp_path, monkeypatch):
    """Bắt lại lỗi người dùng thật báo: 'import sai voice'. Donor 282new lấy audio
    từ kho NHẠC ONLINE của CapCut; giữ nguyên music_id/category_name thì CapCut coi
    file voice là bài nhạc đó, tự phân giải lại về cache của nó và ĐÈ MẤT đường dẫn
    thật. Kèm theo: âm lượng donor chỉ ~26% (nhạc nền) trong khi voice là tiếng
    chính, phải 100%."""
    import shutil
    import capcut_build as cb
    if not shutil.which("ffmpeg"):
        pytest.skip("máy này không có ffmpeg")
    try:
        cb.kiem_tra_draft_mau(cb.DONOR_VIDEO)
    except FileNotFoundError:
        pytest.skip("không có draft mẫu")

    src = tmp_path / "src"; src.mkdir()
    import subprocess as sp
    sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=2",
            "-an", str(src / "C01.mp4")], check=True, capture_output=True)
    voice = tmp_path / "voice.mp3"
    sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            str(voice)], check=True, capture_output=True)
    (tmp_path / "kb.csv").write_text("Scene,Duration,VO\nC01,3,xin chào\n", encoding="utf-8")

    monkeypatch.setattr(cb, "DRAFTS_ROOT", tmp_path / "drafts")
    (tmp_path / "drafts").mkdir()
    # dong_bo_voice=False: test này soi metadata audio, không cần chạy ASR (chậm)
    cb.build_from_csv(tmp_path / "kb.csv", src, voice, "T", do_write=True,
                      dong_bo_voice=False)

    d = json.loads((tmp_path / "drafts" / "T" / "draft_content.json").read_text(encoding="utf-8"))
    am = d["materials"]["audios"][0]
    assert am["type"] == "extract_music", "phải là file local, không phải nhạc online"
    assert am["category_name"] == "local"
    assert not am.get("request_id"), "còn request_id của nhạc online -> CapCut đè mất path"
    assert am["path"].endswith("voice.mp3")
    aseg = next(t for t in d["tracks"] if t["type"] == "audio")["segments"][0]
    assert aseg["volume"] == 1.0, "voice là tiếng chính, không được để mức nhạc nền"
    assert not d["materials"].get("transitions"), \
        "mặc định KHÔNG chèn chuyển cảnh — donor chỉ có 1 kiểu, lặp lại nhìn máy móc"
    assert not any(t["type"] == "text" for t in d["tracks"]), \
        "mặc định KHÔNG thêm caption — video EQ Gym đã có chữ vẽ sẵn trong hình"


def test_chuoi_structured_output_co_model_han_ngach_cao():
    """Bug đã gặp: chuỗi structured output toàn model RPD 20 -> cạn giữa chừng,
    build chết ở phút thứ mười."""
    import gemini_util
    assert any(m.endswith("-lite") for m in gemini_util.FALLBACKS), \
        "phải có model RPD cao ở cuối chuỗi để hạ cánh mềm khi cạn hạn ngạch"


# ─────────────── lỗi bắt được trên máy trạm 27/07 ───────────────

def test_luong_cpu_khong_vuot_tran(monkeypatch):
    """Bug đã gặp: máy 12 nhân/20 luồng ra 9 luồng -> ctranslate2.dll SẬP CỨNG
    (0xC00000FD stack overflow) trên file dài, kéo theo cả web server. Đo được:
    4 luồng chạy trọn 58 phút và còn NHANH HƠN 9 luồng."""
    import multiprocessing as mp
    import transcribe
    monkeypatch.delenv("CT2_THREADS", raising=False)
    for so_luong in (4, 8, 12, 20, 32, 128):
        monkeypatch.setattr(mp, "cpu_count", lambda n=so_luong: n)
        v = transcribe._luong_cpu()
        assert 1 <= v <= transcribe.TRAN_LUONG, \
            f"cpu_count={so_luong} -> {v} luồng, vượt trần {transcribe.TRAN_LUONG} là sập cứng"


def test_transcribe_survey_lui_cpu_khi_cuda_loi_giua_chung(monkeypatch, tmp_path):
    """Bắt lại lỗi 30/07 do người dùng thật báo (RuntimeError: Library cublas64_12.dll
    is not found or cannot be loaded, nổ ra SAU dòng '[asr-survey] khảo sát...', tức
    GIỮA CHỪNG lúc transcribe() đang chạy, không phải lúc WhisperModel() khởi tạo).

    Bản cũ chỉ bọc try/except quanh WhisperModel(...) — DLL CUDA nạp LƯỜI lúc tính
    toán thật nên lỗi né được vùng bắt, job chết cứng dù tưởng đã có đường lùi CPU.
    Test giả lập đúng hình dạng lỗi thật: khởi tạo model KHÔNG lỗi, chỉ lỗi khi BẮT
    ĐẦU DUYỆT segment (tương đương lúc cuBLAS mới thật sự được nạp)."""
    import faster_whisper
    import transcribe
    monkeypatch.setattr(transcribe, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(transcribe, "extract_audio", lambda src, dst: dst)
    monkeypatch.setattr(transcribe, "probe_duration", lambda src: 10.0)
    monkeypatch.setattr(transcribe, "enable_cuda", lambda: None)
    monkeypatch.setattr(transcribe, "ghi_toc_do", lambda *a, **k: None)

    class FakeSeg:
        def __init__(self, i):
            self.start, self.end, self.text = float(i), float(i + 1), f"đoạn {i}"

    class GiaSegments:
        def __init__(self, device):
            self.device = device

        def __iter__(self):
            if self.device == "cuda":
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            for i in range(3):
                yield FakeSeg(i)

    class FakeInfo:
        language = "vi"

    class FakeBatchedPipeline:
        def __init__(self, model):
            self._device = model.device

        def transcribe(self, *a, **kw):
            return GiaSegments(self._device), FakeInfo()

    class FakeWhisperModel:
        def __init__(self, model_name, device, compute_type, cpu_threads=None):
            self.device = device          # KHÔNG lỗi ở đây — đúng như thật

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeWhisperModel)
    monkeypatch.setattr(faster_whisper, "BatchedInferencePipeline", FakeBatchedPipeline)

    data = transcribe.transcribe_survey(str(tmp_path / "video.mp4"), device="cuda")
    assert data["device"] == "cpu", \
        "phải lùi hẳn về CPU khi cuda lỗi GIỮA CHỪNG batch, không riêng lúc khởi tạo"
    assert data["n_segments"] == 3


def test_toc_do_asr_tra_ve_device_that_su_da_chay(monkeypatch, tmp_path):
    """UI cần gợi ý chọn model nhẹ hơn KHI BIẾT máy sẽ chạy CPU (người dùng thật đề
    nghị, GTX 1650 thiếu DLL CUDA nên luôn lùi CPU) — dựa vào device THẬT của lần đo
    gần nhất (transcribe.toc_do_asr() giờ trả 3 giá trị, không phải 2), không tự dò
    CUDA thêm lúc tải trang (tốn thời gian, có thể treo trên máy driver hỏng)."""
    import transcribe
    monkeypatch.setattr(transcribe, "TOC_DO", tmp_path / "toc_do_asr.json")

    rtf, da_do, device = transcribe.toc_do_asr()
    assert da_do is False and device is None, "chưa đo lần nào thì không được bịa device"

    transcribe.ghi_toc_do(4.2, "small", "cpu")
    rtf, da_do, device = transcribe.toc_do_asr()
    assert da_do is True and device == "cpu", \
        "phải đọc lại đúng device THẬT của lần đo gần nhất, không phải device người dùng chọn"


def test_work_dir_bat_duoc_record_khac_trung_ten(tmp_path, monkeypatch):
    """Bug đã gặp: slug() chỉ lấy TÊN file nên hai record khác nhau cùng tên
    'test.mp4' dùng chung thư mục làm việc; cache tái dùng lẫn nhau -> draft TRỘN
    nội dung hai record, không lỗi, không cảnh báo."""
    import transcribe
    monkeypatch.setattr(transcribe, "WORK_ROOT", tmp_path / "work")

    a = tmp_path / "mayA"; a.mkdir()
    (a / "test.mp4").write_bytes(b"x" * 1000)
    b = tmp_path / "mayB"; b.mkdir()
    (b / "test.mp4").write_bytes(b"y" * 2000)          # record KHÁC, cùng tên

    d1 = transcribe.work_dir(str(a / "test.mp4"))
    d2_se_trung = transcribe.WORK_ROOT / transcribe.slug(str(b / "test.mp4"))
    assert d1 == d2_se_trung, "tiền đề của bug: hai record cùng tên trỏ cùng thư mục"

    with pytest.raises(transcribe.NguonKhongKhop):
        transcribe.work_dir(str(b / "test.mp4"))


def test_work_dir_cho_phep_doi_record_di_cho(tmp_path, monkeypatch):
    """Cùng một file dời sang thư mục khác thì KHÔNG được chặn — người dùng dời
    record là chuyện thường, chặn nhầm còn khó chịu hơn."""
    import transcribe
    monkeypatch.setattr(transcribe, "WORK_ROOT", tmp_path / "work")
    a = tmp_path / "cho_cu"; a.mkdir()
    (a / "rec.mp4").write_bytes(b"z" * 4096)
    transcribe.work_dir(str(a / "rec.mp4"))

    b = tmp_path / "cho_moi"; b.mkdir()
    (b / "rec.mp4").write_bytes(b"z" * 4096)           # cùng kích thước = cùng file
    transcribe.work_dir(str(b / "rec.mp4"))            # không được ném


def test_nghi_theo_tung_model_khong_theo_ca_key(monkeypatch):
    """Bug đã gặp 27/07: _NGHI khoá theo KEY. Gặp 429 ở model đầu chuỗi là cả key bị
    đánh dấu nghỉ -> 5 model dự phòng còn lại đều bị bỏ qua. Chuỗi dự phòng sinh ra để
    đổi model khi một model cạn, lại tự sập ngay ở lỗi cạn ĐẦU TIÊN. Hạn ngạch Google
    tính theo TỪNG MODEL: 2.5-flash cạn (RPD 20) không có nghĩa lite cạn (RPD 500)."""
    import gemini_util as g
    g._NGHI.clear()
    g._cho_nghi("key1", "gemini-2.5-flash", "429 RESOURCE_EXHAUSTED PerDay")
    assert g._dang_nghi("key1", "gemini-2.5-flash"), "model vừa 429 phải được cho nghỉ"
    assert not g._dang_nghi("key1", "gemini-3.5-flash-lite"), \
        "model KHÁC trên cùng key vẫn phải gọi được — nếu không chuỗi dự phòng vô dụng"
    g._NGHI.clear()


def test_cham_hinh_phat_hien_doan_dung_yen():
    """Ba short đầu tiên đều 'đúng' theo mọi chỉ số đang đo (dangling 0, caption đúng
    nhịp, file không thiếu) nhưng xem thì không dùng được: nguồn là bản ghi chia sẻ
    MÀN HÌNH. Đo 27/07 trên record thật: 46% thời lượng hình đứng yên, và đúng hai chủ
    đề người dùng chê nhất là hai cái tĩnh 94% và 89%."""
    import hinh_anh
    hinh = {"duration_sec": 100.0, "dung_yen": [[10.0, 20.0], [50.0, 5.0]]}

    # chủ đề rơi trọn vào đoạn đứng yên -> phạt kịch khung
    c = hinh_anh.cham(hinh, [(10.0, 30.0)])
    assert c["ty_le_tinh"] > 0.9 and c["he_so"] == 0.5

    # chủ đề ở vùng có chuyển động -> không phạt
    c = hinh_anh.cham(hinh, [(60.0, 90.0)])
    assert c["ty_le_tinh"] == 0.0 and c["he_so"] == 1.0

    # hệ số không bao giờ về 0: đoạn tĩnh vẫn cứu được bằng B-roll hoặc chữ to
    assert hinh_anh.cham({"dung_yen": [[0.0, 999.0]]}, [(0.0, 100.0)])["he_so"] >= 0.5

    # nguồn tĩnh nhiều thì phải CẢNH BÁO, đừng để người dùng dựng xong mới biết
    assert "ĐỨNG YÊN" in hinh_anh.nhan_xet_nguon({"ty_le_tinh": 0.46})
    assert hinh_anh.nhan_xet_nguon({"ty_le_tinh": 0.02}) == ""


def test_cong_tac_lop_co_tac_dung_len_build():
    """Bug đã gặp: giao diện có 7 công tắc lớp, lưu vào DB đầy đủ, mà build KHÔNG ĐỌC
    — bật tắt xong chẳng có gì xảy ra. Hỏng im lặng đúng kiểu luật cứng #2 cấm."""
    import inspect
    import build_short_draft as bsd
    src = inspect.getsource(bsd.build)
    assert "cau_hinh" in inspect.signature(bsd.build).parameters, "build phải nhận cấu hình"
    for lop in ("caption", "hook", "sfx", "emoji", "broll", "card_chot"):
        assert f'lop.get("{lop}"' in src, f"lớp '{lop}' chưa được nối vào build"


def test_hook_khong_phat_lai_hai_lan():
    """Bug đã gặp 27/07: hook được GHÉP THÊM lên đầu nhưng KHÔNG trừ khỏi thân, nên
    cùng một câu phát HAI LẦN. Đo bằng tương quan chéo trên file đã xuất: t2 trùng
    0,95 ở giây 23,4 · t3 trùng 0,89 ở giây 21,0 — hỏng video ngay đoạn đầu.
    Gemini chọn hook là 'khoảnh khắc ấn tượng nhất TRONG đoạn' nên hook GẦN NHƯ LUÔN
    nằm sẵn trong thân — đây là trường hợp thường, không phải ngoại lệ."""
    import build_short_draft as bsd

    # hook nằm GIỮA thân (đúng ca của t3: thân 1739-1826, hook 1753-1756)
    ra = bsd.tru_khoang([(1739.0, 1826.0)], (1753.0, 1756.0))
    assert (1739.0, 1753.0) in ra and (1756.0, 1826.0) in ra
    for a, b in ra:
        assert not (a < 1756.0 and b > 1753.0), f"khoảng {a}-{b} vẫn chứa hook"

    # hook ở SÁT ĐẦU thân (ca của t2: thân 2173-2241, hook 2175-2178)
    ra = bsd.tru_khoang([(2173.0, 2241.0)], (2175.0, 2178.0))
    assert all(not (a < 2178.0 and b > 2175.0) for a, b in ra)
    assert (2173.0, 2175.0) not in ra, "mảnh 2 giây là tiếng nấc, phải bỏ"

    # hook KHÔNG chạm thân thì giữ nguyên
    assert bsd.tru_khoang([(100.0, 200.0)], (10.0, 13.0)) == [(100.0, 200.0)]

    # hook trùm cả thân -> trả rỗng để caller biết mà giữ nguyên mạch
    assert bsd.tru_khoang([(50.0, 55.0)], (49.0, 56.0)) == []


def test_caption_khong_co_dong_qua_ngan():
    """Đo trên draft thật 27/07: 15/89 dòng dưới 0,3 giây, gần như toàn 'chữ mồ côi'
    ở cuối cue ('xa.', 'biết.', 'giờ') — chia thời lượng theo số ký tự nên dòng 3 ký
    tự chỉ được 3/90 thời lượng = 0,06 giây, chớp một cái là mất.

    Bài test ĐẦU TIÊN cho lỗi này chỉ soi mã nguồn (`'TOI_THIEU_GIAY' in src`) nên VẪN
    XANH trong khi hàm ném IndexError ở mọi lượt build. Test soi chữ không chứng minh
    được gì về hành vi — phải GỌI THẬT.

    Sàn thời lượng (dam_bao_san_thoi_luong) chạy SAU split_cue, không còn trong nó —
    xem test_san_thoi_luong_toan_cuc cho lý do."""
    import build_short_draft as bsd

    # trường hợp làm vỡ bản vá đầu: đúng 2 dòng, dòng cuối là chữ mồ côi
    ra = bsd.split_cue(0.0, 2.0, "Mình đi rất là xa.")
    assert ra, "không được trả rỗng"
    for a, b, t in ra:
        assert b > a, f"dòng {t!r} có thời lượng âm hoặc bằng 0"

    # cue dài: qua sàn thời lượng toàn cục thì mọi dòng phải đọc kịp, không mất chữ
    dai = ("Đầu tiên trong ít nhất hai tuần tới là phải hoàn thành hệ thống "
           "edit tự động để giảm tải khối lượng công việc rất là xa.")
    ra = bsd.dam_bao_san_thoi_luong(bsd.split_cue(0.0, 12.0, dai))
    ngan = [(b - a, t) for a, b, t in ra if b - a < 0.3]
    assert not ngan, f"còn dòng dưới 0,3 giây: {ngan[:3]}"
    assert " ".join(t for _, _, t in ra).split() == dai.split(), "ghép lại phải đủ chữ"

    # thời lượng cộng lại không được vượt quá cue gốc
    assert ra[0][0] >= -1e-9 and ra[-1][1] <= 12.0 + 1e-9

    # cue quá ngắn để chia: vẫn phải ra thứ dùng được, không được nổ
    assert bsd.split_cue(5.0, 5.2, "Ok.")


def test_caption_khong_gan_nguyen_cau_cho_manh_bi_cat():
    """GỐC THẬT của lỗi nhấp nháy 8 dòng liên tiếp 0,05-0,13s (28/07, kênh 'Cộng đồng
    Học làm Sếp') — không phải do nói nhanh (nghi vấn ban đầu, SAI: đo lại thấy
    segment gốc dài tự nhiên 3,4 giây, hoàn toàn bình thường). Nguyên nhân thật:
    captions_for_cuts gán TRỌN VĂN BẢN segment cho mảnh thời gian còn SỐNG SÓT khi
    segment bị CẮT NGANG bởi ranh giới cut (hook tách ra, hoặc tighten_cuts bỏ
    khoảng lặng giữa câu). Câu 60 ký tự chỉ còn 0,4s sống sót (3s đầu nằm ngoài vùng
    cut) nhưng vẫn hiện TRỌN CÂU — split_cue chia domino xuống 0,05-0,13s/dòng.
    Tệ hơn cả nhấp nháy: có ca chữ hiện ra ứng với ÂM THANH ĐÃ BỊ CẮT KHỎI VIDEO,
    tức phụ đề nói cái không ai nghe thấy.

    Vá tại chính nguồn (captions_for_cuts + _chu_con_song_sot): dùng mốc TỪNG CHỮ để
    chỉ lấy đúng phần chữ nằm trong khoảng sống sót, không phải nguyên câu."""
    from render_short import captions_for_cuts

    # Segment dài tự nhiên 3,4s (đúng số đo thật), có mốc từng chữ, nhưng cut chỉ giữ
    # lại 0,4 giây CUỐI của nó — mô phỏng cut bắt đầu ở giữa câu.
    seg = {
        "start": 100.0, "end": 103.4,
        "text": "Em cũng sẽ tự nhìn nhận lại mình trong suốt giai đoạn qua.",
        "words": [
            {"w": " Em", "start": 100.0, "end": 100.2}, {"w": " cũng", "start": 100.2, "end": 100.4},
            {"w": " sẽ", "start": 100.4, "end": 100.6}, {"w": " tự", "start": 100.6, "end": 101.2},
            {"w": " nhìn", "start": 101.2, "end": 101.4}, {"w": " nhận", "start": 101.4, "end": 101.6},
            {"w": " lại", "start": 101.6, "end": 101.8}, {"w": " mình", "start": 101.8, "end": 102.0},
            {"w": " trong", "start": 102.0, "end": 102.6}, {"w": " suốt", "start": 102.6, "end": 102.8},
            {"w": " giai", "start": 102.8, "end": 103.0}, {"w": " đoạn", "start": 103.0, "end": 103.2},
            {"w": " qua.", "start": 103.2, "end": 103.4},
        ],
    }
    cues = captions_for_cuts([(103.0, 110.0)], [seg])   # chỉ 0,4s cuối segment nằm trong cut
    assert len(cues) == 1
    st, en, txt = cues[0]
    assert en - st <= 0.5, "cue phải khớp đúng thời lượng SỐNG SÓT, không phải cả câu"
    assert txt != seg["text"], "không được gán TRỌN CÂU cho mảnh thời gian bị cắt"
    assert "qua" in txt, "phải giữ đúng phần chữ tương ứng với thời gian còn sống sót"
    assert "Em" not in txt, "không được lẫn chữ thuộc phần ĐÃ BỊ CẮT KHỎI VIDEO"


def test_caption_khong_bi_cat_van_giu_nguyen_van():
    """Segment KHÔNG bị cắt ngang (nằm trọn trong một cut) thì đường đi cũ phải giữ
    nguyên — bản vá chỉ can thiệp đúng trường hợp bị cắt, không ảnh hưởng ca bình thường."""
    from render_short import captions_for_cuts
    seg = {"start": 10.0, "end": 12.0, "text": "Câu bình thường không bị cắt.", "words": []}
    assert captions_for_cuts([(5.0, 20.0)], [seg]) == \
        [(5.0, 7.0, "Câu bình thường không bị cắt.")]


def test_caption_khoa_theo_moc_thoi_gian_khong_theo_id():
    """Bug đã gặp 27/07 (lớp lỗi ĐỊNH DANH KHÔNG ỔN ĐỊNH, lần thứ ba): captions_fixed
    khoá theo seg['id'], mà refine_range đánh số lại TOÀN BỘ id mỗi lần trộn. Sau một
    lượt làm sạch, chữ của segment 30 giây (400 ký tự) dán vào segment 0,5 giây ->
    split_cue chia thành ~20 dòng, mỗi dòng 0,05 GIÂY, caption nhấp nháy không đọc nổi."""
    from render_short import captions_for_cuts, khoa_cap
    seg_ngan = {"id": 3, "start": 10.0, "end": 10.5, "text": "chữ thô"}
    assert khoa_cap(seg_ngan) == "10000", "khoá phải là mốc bắt đầu (ms), không phải id"

    # chữ đã sạch nằm TRONG segment thì phải thắng cache ngoài — không thể lệch
    seg_sach = {"id": 3, "start": 10.0, "end": 10.5,
                "text": "chữ đã sạch", "text_goc": "chữ thô"}
    cues = captions_for_cuts([(9.0, 12.0)], [seg_sach], {"3": "CHỮ DÀI CỦA SEGMENT KHÁC"})
    assert cues[0][2] == "chữ đã sạch", "cache khoá theo id không được đè chữ trong segment"

    # segment CHƯA sạch thì tra cache theo mốc, khoá id cũ phải trượt (không dán nhầm)
    cues2 = captions_for_cuts([(9.0, 12.0)], [seg_ngan], {"3": "CHỮ DÀI CỦA SEGMENT KHÁC"})
    assert cues2[0][2] == "chữ thô", "khoá id cũ vẫn dán được vào segment khác"


def test_cam_ai_doi_ten_rieng_khi_lam_sach():
    """Bug đã gặp 27/07: Whisper nghe 'nano bar na 2' (Nano Banana 2 — model ảnh của
    Google), AI 'sửa' thành 'Runway Gen-2' — đổi hẳn sang sản phẩm KHÁC. Gán cho diễn
    giả câu họ chưa từng nói là hỏng nặng hơn nhiều so với sai chính tả."""
    import caption_fix
    s = caption_fix.SYS
    assert "TÊN RIÊNG" in s.upper(), "prompt phải cấm đổi tên riêng"
    assert "GIỮ NGUYÊN" in s, "không nhận ra tên thì phải giữ nguyên chữ ASR nghe được"


def test_lam_sach_chia_lo_theo_ky_tu(monkeypatch):
    """Bug đã gặp: chia lô theo SỐ DÒNG (120) vốn chỉnh cho câu ngắn của bản bóc kỹ.
    Bản khảo sát mỗi dòng ~34 giây tiếng nói -> 100 dòng thành khối ~35k ký tự, output
    vượt giới hạn, resp.parsed về None, vòng dự phòng xoay hết model mà lần nào cũng
    cụt -> treo cứng."""
    import inspect
    import caption_fix
    src = inspect.getsource(caption_fix.lam_sach_toan_bo)
    assert "MAX_KY_TU" in src, "phải chia lô theo số ký tự, không theo số dòng"
    assert "text_goc" in src, "phải giữ bản thô để người dùng đối chiếu AI sửa gì"


def test_bo_dong_dem_khoi_prompt_nhung_giu_moc_thoi_gian():
    """Câu đệm ('ba ơi ba ơi ba ơi', 'alo alo') làm loãng nội dung khi tìm chủ đề.
    Bỏ khỏi PROMPT thì được, nhưng KHÔNG được xoá segment: mốc thời gian là thứ dùng
    để cắt video, mất là hỏng cả bản dựng."""
    import topics as tp
    tr = {"segments": [
        {"start": 0, "end": 5, "text": "Nội dung thật sự đáng làm short"},
        {"start": 5, "end": 8, "text": "Alo alo mọi người nghe rõ không", "bo": True},
        {"start": 8, "end": 12, "text": "Nội dung thứ hai"},
    ]}
    body = tp.format_transcript(tr)
    assert "Nội dung thật sự" in body and "Nội dung thứ hai" in body
    assert "Alo alo" not in body, "dòng đánh dấu bỏ vẫn lọt vào prompt"
    assert len(tr["segments"]) == 3, "KHÔNG được xoá segment — mất mốc là hỏng cắt video"


def test_chia_cua_so_phu_het_record():
    """Bug đã gặp: nhồi cả transcript 58 phút vào MỘT lượt gọi -> 20 phút CUỐI không
    sinh chủ đề nào, độ phủ 9,5%. Cửa sổ phải phủ kín [0, dài] và có chồng lấn để
    chủ đề vắt qua ranh giới không bị cắt đôi."""
    import topics as tp
    for dai in (300, 900, 3462, 4 * 3600):
        cs = tp.chia_cua_so(dai)
        assert cs[0][0] == 0, f"dài {dai}: không bắt đầu từ 0"
        assert abs(cs[-1][1] - dai) < 1, f"dài {dai}: bỏ sót phần cuối ({cs[-1][1]} != {dai})"
        for (a1, b1), (a2, b2) in zip(cs, cs[1:]):
            assert a2 < b1, f"dài {dai}: hai cửa sổ không chồng lấn -> mất chủ đề ở ranh giới"
    assert len(tp.chia_cua_so(3462)) >= 3, "record 58 phút phải chia nhiều hơn 1 cửa sổ"


def test_loc_chu_de_theo_hang_khong_theo_nguong_diem():
    """Bug đã gặp 27/07: ngưỡng tuyệt đối min_total_score=5.0 hoá ra đo ĐỘ RỘNG TAY
    CỦA MODEL chứ không đo chất lượng. Cùng record, cùng profile: flash chấm cao nhất
    7,6 -> bỏ 0/12; pro chấm cao nhất 6,9 -> bỏ 8/20. Đổi model là phải chỉnh tay lại,
    mà dự án còn định thêm nhà cung cấp ngoài Google."""
    import topics as tp
    # thang điểm THẤP (model chấm khắt) — không được vì thế mà mất hết chủ đề
    khat = [{"total_score": 6.9 - i * 0.1} for i in range(20)]
    giu, du = tp.loc_theo_hang(khat, 58 * 60)
    assert len(giu) >= 5, "model chấm khắt không được làm mất sạch chủ đề"
    assert len(giu) + len(du) == 20, "chủ đề dôi ra phải vào DỰ BỊ, không được vứt đi"

    # thang điểm CAO (model rộng tay) — cùng số lượng thì phải giữ y hệt
    rong = [{"total_score": 9.5 - i * 0.1} for i in range(20)]
    giu2, _ = tp.loc_theo_hang(rong, 58 * 60)
    assert len(giu) == len(giu2), "thang điểm khác nhau mà số giữ lại phải như nhau"

    # record ngắn thì giữ ít hơn, nhưng không bao giờ về 0
    giu3, _ = tp.loc_theo_hang(khat, 5 * 60)
    assert 0 < len(giu3) <= len(giu)


def test_gop_chu_de_khu_trung_o_vung_chong_lan():
    """Vùng chồng lấn sinh ra cùng một chủ đề hai lần — phải khử, và giữ bản ĐIỂM CAO."""
    import topics as tp
    a = {"title": "A", "total_score": 8.0, "segments": [{"start_sec": 100, "end_sec": 200}]}
    b = {"title": "A lần 2", "total_score": 5.0, "segments": [{"start_sec": 110, "end_sec": 205}]}
    c = {"title": "Khác hẳn", "total_score": 7.0, "segments": [{"start_sec": 900, "end_sec": 1000}]}
    ra = tp.gop_chu_de([b, a, c])
    assert len(ra) == 2, "không khử được bản trùng"
    assert any(t["title"] == "A" for t in ra), "phải giữ bản điểm cao hơn"
    assert not any(t["title"] == "A lần 2" for t in ra)


def test_prompt_co_rang_buoc_so_luong_chu_de():
    """Bug đã gặp: prompt chỉ quy định ĐỘ DÀI mỗi chủ đề, không nói cần BAO NHIÊU cái
    -> model tự chọn ít cho chắc, record 1 tiếng ra đúng 3 chủ đề."""
    import topics as tp
    p = tp.load_profile(str(ROOT / "shorts" / "profiles" / "meeting.yaml"))
    pr = tp.build_system_prompt(p, 0, 900, 4)
    assert "ÍT NHẤT 4" in pr, "phải nêu số chủ đề tối thiểu cho cửa sổ"
    assert "900" in pr or "15 phút" in pr, "phải nêu rõ cửa sổ đang xét"


def test_moi_du_an_co_thu_muc_lam_viec_rieng(tmp_path, monkeypatch):
    """Hai dự án dùng chung MỘT record phải phân tích RIÊNG. Dùng chung thư mục thì
    dự án thứ hai thừa hưởng transcript + chủ đề + video nền của dự án thứ nhất —
    tức là 'làm lại' mà chẳng làm lại gì."""
    import transcribe
    monkeypatch.setattr(transcribe, "WORK_ROOT", tmp_path / "work")
    rec = tmp_path / "test.mp4"
    rec.write_bytes(b"a" * 512)

    mac_dinh = transcribe.work_dir(str(rec))
    rieng = transcribe.work_dir(str(rec), ten="test_2")
    assert mac_dinh.name == "test"
    assert rieng.name == "test_2", "phải theo tên caller đưa, không suy từ tên file"
    assert mac_dinh != rieng


def test_khoa_video_nen_theo_khoang_cat_khong_theo_chi_so():
    """Bug đã gặp: reframe_t{N}.mp4 khoá theo CHỈ SỐ chủ đề. Phân tích lại ra danh
    sách chủ đề khác -> 'chủ đề 1' là đoạn khác, nhưng file cũ vẫn được tái dùng:
    caption/SFX của chủ đề MỚI phủ lên hình+tiếng của chủ đề CŨ."""
    import build_short_draft as bsd
    nguon = "C:/rec/test.mp4"
    cu = [(816.0, 972.0)]
    moi = [(890.0, 984.0)]
    assert bsd.khoa_khoang_cat(nguon, cu) != bsd.khoa_khoang_cat(nguon, moi), \
        "khoảng cắt đổi mà khoá không đổi -> tái dùng nhầm video nền"
    assert bsd.khoa_khoang_cat(nguon, cu) == bsd.khoa_khoang_cat(nguon, list(cu)), \
        "cùng khoảng cắt phải cùng khoá (2 editor cùng chủ đề vẫn dùng chung file)"
    assert bsd.khoa_khoang_cat("D:/khac/test.mp4", cu) != bsd.khoa_khoang_cat(nguon, cu), \
        "khác record mà cùng khoá -> lại trộn nội dung"


def test_khoa_enrich_theo_noi_dung_chu_de():
    """Cùng lỗi lớp trên, ở cache enrich: hook/emoji/SFX của chủ đề cũ dán vào mới."""
    import enrich
    a = {"title": "Chủ đề A", "segments": [{"start_sec": 10, "end_sec": 20}]}
    b = {"title": "Chủ đề B", "segments": [{"start_sec": 90, "end_sec": 99}]}
    assert enrich.khoa_chu_de(a) != enrich.khoa_chu_de(b)
    assert enrich.khoa_chu_de(a) == enrich.khoa_chu_de(dict(a))


def test_build_ha_canh_mem_khi_can_han_ngach(monkeypatch):
    """Bug đã gặp: HetHanNgach từ enrich ném xuyên qua build -> mất trắng cả lượt
    sau khi đã bóc lời và render. Enrich là đồ tô điểm, không phải xương sống."""
    import build_short_draft as bsd, gemini_util, inspect
    src = inspect.getsource(bsd.build)
    assert "HetHanNgach" in src, "build phải bắt HetHanNgach quanh enrich_topic"
    assert hasattr(gemini_util, "HetHanNgach")


def test_uoc_luong_thoi_gian_khong_hardcode_toc_do_may_dev():
    """Bug đã gặp: eta = dur/30/60 — hệ số 30x đo trên GPU máy dev, đóng cứng cho
    mọi máy. Máy chạy CPU đo được 14,5x -> hứa 2 phút, bắt ngồi 4 phút."""
    import inspect
    import app
    src = inspect.getsource(app.api_browse)
    assert "toc_do_asr" in src, "phải ước lượng theo tốc độ đo được trên máy đang chạy"
    assert "/ 30 / 60" not in src, "còn hardcode hệ số của máy dev"


def test_root_dung_thu_muc_chua_exe_khi_dong_goi(monkeypatch, tmp_path):
    """Bug đã gặp 30/07: assetlib.ROOT = Path(__file__).resolve().parent. Đóng gói
    PyInstaller (--onedir) thì __file__ trỏ vào bên trong _internal/ (gói nội bộ) —
    ghi library.db/.env/assets/user vào đó thì MẤT SẠCH mỗi lần cập nhật bản mới, và
    với --onefile thì mất NGAY LẬP TỨC lúc thoát app. Đo thật (chạy .exe từ thư mục
    tách biệt): library.db/snapshots/quarantine/renders/assets/user đều phải nằm
    CẠNH file .exe, không phải trong thư mục nội bộ của gói."""
    import importlib
    import assetlib

    gia_exe = tmp_path / "may_khac" / "CapCutAuto.exe"
    gia_exe.parent.mkdir(parents=True)
    gia_exe.write_bytes(b"")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(gia_exe))
    try:
        assert assetlib._goc() == gia_exe.parent, \
            "đóng gói thì ROOT phải là thư mục chứa .exe, không phải __file__"
    finally:
        # PHẢI undo() TRƯỚC reload — monkeypatch chỉ tự khôi phục sys.frozen SAU KHI
        # hàm test này kết thúc hoàn toàn (kể cả finally), nên reload ở đây mà không
        # undo trước sẽ đọc NGAY GIÁ TRỊ GIẢ, ghi ROOT sai vĩnh viễn cho mọi test sau
        # trong cùng lượt chạy — lỗi này tự bắt được khi chạy thật, không phải đoán.
        monkeypatch.undo()
        importlib.reload(assetlib)


def test_khong_frozen_van_giu_hanh_vi_cu():
    """Chạy dev (`python app.py`, không đóng gói) thì ROOT phải y hệt trước khi vá —
    bản vá cho .exe không được đổi hành vi khi KHÔNG đóng gói."""
    import assetlib
    assert not getattr(__import__("sys"), "frozen", False), \
        "test chạy trong dev, sys.frozen không được tự bật"
    assert assetlib.ROOT == assetlib.Path(assetlib.__file__).resolve().parent
