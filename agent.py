# -*- coding: utf-8 -*-
"""agent.py — chế độ AGENT: chat bằng tiếng Việt, tự gọi tool của pipeline.

Khác chế độ THỦ CÔNG (4 tab bấm nút): ở đây ra lệnh tự do, agent tự chọn tool,
tự hỏi lại khi thiếu thông tin, và NHỚ ngữ cảnh giữa các lượt (lưu SQLite trên máy).

Việc chạy lâu (phân tích record, dựng draft) đẩy sang job nền — agent chỉ khởi động
rồi báo lại, không ngồi chờ chẹn cả phiên chat.
"""
import json, time
from pathlib import Path

import assetlib, asset_restore, audio_balance, draft_diff, draft_scan

ROOT = assetlib.ROOT
WORK = ROOT / "shorts" / "work"

SYS = """Bạn là trợ lý dựng short video từ recording dài, làm việc với đội editor người Việt.
Trả lời NGẮN GỌN bằng tiếng Việt, giọng đồng nghiệp, không khách sáo.

Quy trình sản phẩm: record dài -> bóc lời + trích chủ đề -> người dùng CHỌN chủ đề
-> dựng draft CapCut theo GU của editor (Đan/Nguyên) -> editor sửa trong CapCut
-> đồng bộ về kho để lần sau hợp gu hơn -> cân bằng âm thanh.

Nguyên tắc:
- Cần thông tin còn thiếu (chọn chủ đề nào, gu editor nào) thì HỎI, đừng đoán bừa.
- Trước khi làm việc nặng (phân tích record, dựng draft) hãy nói rõ sẽ mất bao lâu.
- Việc nặng chạy nền: báo đã khởi động và bảo người dùng xem mục Tiến trình.
- Dẫn số liệu thật lấy từ tool, không bịa tên draft/chủ đề.
- Ghi/sửa draft yêu cầu ĐÓNG draft đó trong CapCut trước (không thì báo lỗi .locked)."""


# ───────────────────────── TOOLS ─────────────────────────
# Mỗi tool: (mô tả, schema tham số, hàm). Hàm nhận **kwargs, trả dict/JSON-able.

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


def _recordings(dir: str = ""):
    import app as _app                       # dùng lại logic quét file của chế độ thủ công
    return _app.api_browse(dir or "")


def _drafts():
    root = draft_scan.DRAFT_ROOT
    out = []
    if root.exists():
        for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:25]:
            if (p / "draft_content.json").exists():
                out.append({"ten": p.name, "dang_mo_trong_capcut": (p / ".locked").exists(),
                            "co_moc": (draft_diff.SNAP_DIR / f"{p.name}.json").exists()})
    return {"draft": out}


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


def _diff(draft: str):
    try:
        d = draft_diff.diff(draft)
    except SystemExit as e:
        return {"loi": str(e)}
    strip = lambda arr: [{"loai": r["kind"], "ten": r["name"]} for r in arr]
    return {"them": strip(d["added"]), "go_bo": strip(d["removed"]), "giu": len(d["kept"])}


def _snapshot(draft: str):
    draft_diff.snapshot(draft)
    return {"ok": True, "ghi_chu": f"đã chụp mốc '{draft}'"}


def _sync(draft: str, editor: str = "shared"):
    try:
        return draft_diff.sync(draft, editor)
    except SystemExit as e:
        return {"loi": str(e)}


def _audio_report(draft: str):
    import app as _app
    try:
        r = _app.api_audio_report(draft)
    except Exception as e:
        return {"loi": str(e)[:120]}
    return {"nguon": r["rows"][:12], "muc_tieu": r["target"]}


def _restore():
    return {"da_cai": asset_restore.restore()}


TOOLS = {
    "liet_ke_du_an": (
        "Liệt kê các record ĐÃ phân tích và danh sách chủ đề kèm điểm của từng cái.",
        {"type": "object", "properties": {}}, _projects),
    "liet_ke_file_record": (
        "Liệt kê file record thô trong một thư mục (kèm thời lượng, ước tính thời gian xử lý, "
        "có hình hay chỉ có tiếng). Dùng khi người dùng muốn phân tích record MỚI.",
        {"type": "object", "properties": {
            "dir": {"type": "string", "description": "thư mục chứa record, bỏ trống = mặc định"}}},
        _recordings),
    "liet_ke_draft": (
        "Liệt kê draft CapCut đã dựng, kèm trạng thái đang mở trong CapCut và đã chụp mốc chưa.",
        {"type": "object", "properties": {}}, _drafts),
    "kho_tai_nguyen": (
        "Xem kho tài nguyên đã học từ editor (font/sticker/hiệu ứng chữ/SFX), ai dùng nhiều cái gì.",
        {"type": "object", "properties": {
            "kind": {"type": "string", "description": "sticker|font|text_template|audio|effect|transition"},
            "owner": {"type": "string", "description": "dan|nguyen|shared"}}}, _assets),
    "xem_editor_sua_gi": (
        "So sánh draft với mốc đã chụp để biết editor đã THÊM/GỠ tài nguyên nào.",
        {"type": "object", "properties": {"draft": {"type": "string"}}, "required": ["draft"]}, _diff),
    "chup_moc_draft": (
        "Chụp mốc tài nguyên của draft (làm NGAY sau khi dựng, để sau này so sánh).",
        {"type": "object", "properties": {"draft": {"type": "string"}}, "required": ["draft"]}, _snapshot),
    "dong_bo_ve_kho": (
        "Nạp tài nguyên editor vừa thêm vào kho của editor đó, và hạ điểm cái bị gỡ.",
        {"type": "object", "properties": {
            "draft": {"type": "string"}, "editor": {"type": "string"}}, "required": ["draft"]}, _sync),
    "do_am_luong": (
        "Đo LUFS từng nguồn tiếng trong draft (giọng/SFX/nhạc) và mức cần chỉnh. Chỉ ĐỌC.",
        {"type": "object", "properties": {"draft": {"type": "string"}}, "required": ["draft"]},
        _audio_report),
    "cai_tai_nguyen_vao_capcut": (
        "Cài các gói sticker/hiệu ứng từ kho vào CapCut của máy này (dùng khi máy mới thiếu).",
        {"type": "object", "properties": {}}, _restore),
}

# tool chạy LÂU -> đẩy job nền, cần app truyền hàm chạy job vào
SLOW_TOOLS = {
    "phan_tich_record": (
        "Phân tích một file record MỚI: bóc lời bằng GPU rồi trích chủ đề. Chạy nền. "
        "Nhớ báo trước thời gian ước tính lấy từ liet_ke_file_record.",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "đường dẫn đầy đủ tới file record"},
            "asr": {"type": "string", "description": "small (nhanh, mặc định) hoặc medium"}},
         "required": ["path"]}),
    "dung_draft": (
        "Dựng draft CapCut cho MỘT chủ đề theo gu một editor. Chạy nền, vài phút.",
        {"type": "object", "properties": {
            "project": {"type": "string", "description": "tên dự án, vd 1107"},
            "topic": {"type": "integer", "description": "số thứ tự chủ đề"},
            "editor": {"type": "string", "description": "dan|nguyen|shared"}},
         "required": ["project", "topic"]}),
    "can_bang_am_thanh": (
        "Ghi âm lượng đã cân bằng vào draft (đóng draft trong CapCut trước). Chạy nền.",
        {"type": "object", "properties": {"draft": {"type": "string"}}, "required": ["draft"]}),
}


# ───────────────────────── trí nhớ ─────────────────────────

def _init_db():
    c = assetlib.conn()
    c.execute("CREATE TABLE IF NOT EXISTS chat("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, role TEXT,"
              " content TEXT, ts REAL)")
    c.commit()
    return c


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


def reset(session: str):
    c = _init_db()
    c.execute("DELETE FROM chat WHERE session=?", (session,))
    c.commit(); c.close()


# ───────────────────────── vòng lặp agent ─────────────────────────

def chat(session: str, user_text: str, model: str = "gemini-2.5-flash",
         run_job=None, max_steps: int = 6) -> dict:
    """Một lượt chat. Trả {reply, steps:[{tool,args,ket_qua}]}"""
    from google import genai
    from google.genai import types
    import sys as _s
    _s.path.insert(0, str(ROOT / "shorts"))
    import gemini_util

    decls = []
    for name, (desc, schema, _fn) in TOOLS.items():
        decls.append(types.FunctionDeclaration(name=name, description=desc, parameters=schema))
    for name, (desc, schema) in SLOW_TOOLS.items():
        decls.append(types.FunctionDeclaration(name=name, description=desc, parameters=schema))

    contents = []
    for m in history(session):
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
    _save(session, "user", user_text)

    client = genai.Client()
    cfg = types.GenerateContentConfig(
        system_instruction=SYS, tools=[types.Tool(function_declarations=decls)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=4000)

    steps = []
    for _ in range(max_steps):
        resp, _used = gemini_util.generate_raw(client, model, contents=contents, config=cfg)
        cand = (resp.candidates or [None])[0]
        if not cand or not cand.content or not cand.content.parts:
            break
        calls = [p.function_call for p in cand.content.parts if getattr(p, "function_call", None)]
        if not calls:
            reply = "".join(p.text for p in cand.content.parts if getattr(p, "text", None)) or "…"
            _save(session, "model", reply)
            return {"reply": reply, "steps": steps}

        contents.append(cand.content)
        parts = []
        for fc in calls:
            args = dict(fc.args or {})
            try:
                if fc.name in TOOLS:
                    out = TOOLS[fc.name][2](**args)
                elif fc.name in SLOW_TOOLS:
                    out = _start_slow(fc.name, args, run_job)
                else:
                    out = {"loi": f"không có tool '{fc.name}'"}
            except Exception as e:
                out = {"loi": f"{type(e).__name__}: {str(e)[:160]}"}
            steps.append({"tool": fc.name, "args": args, "ket_qua": out})
            parts.append(types.Part.from_function_response(name=fc.name, response={"result": out}))
        contents.append(types.Content(role="user", parts=parts))

    reply = "Tôi gọi tool hơi nhiều lượt mà chưa xong — bạn nói rõ hơn giúp nhé."
    _save(session, "model", reply)
    return {"reply": reply, "steps": steps}


def _start_slow(name: str, args: dict, run_job):
    """Khởi động việc nặng ở job nền; trả ngay để agent không ngồi chờ."""
    if run_job is None:
        return {"loi": "chưa nối được job nền"}
    import sys as _s
    _s.path.insert(0, str(ROOT / "shorts"))
    import build_short_draft as bsd
    import contextlib, io
    import app as _app

    if name == "phan_tich_record":
        path, asr = args.get("path", ""), args.get("asr") or "small"
        if not Path(path).exists():
            return {"loi": f"không thấy file: {path}"}
        r = _app.api_ingest(path=path, asr=asr)
        return {"da_khoi_dong": True, "job": r["job"], "ghi_chu": "xem mục Tiến trình"}

    if name == "dung_draft":
        proj, topic = args.get("project", ""), int(args.get("topic", 0))
        editor = args.get("editor") or "shared"
        if not (WORK / proj / "topics.json").exists():
            return {"loi": f"dự án '{proj}' chưa được phân tích"}
        r = _app.api_generate(proj=proj, topic=topic, editor=editor)
        return {"da_khoi_dong": True, "job": r["job"], "draft": r["draft"]}

    if name == "can_bang_am_thanh":
        r = _app.api_balance(name=args.get("draft", ""), dry=False)
        return {"da_khoi_dong": True, "job": r["job"]}

    return {"loi": f"tool nặng lạ: {name}"}
