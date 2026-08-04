# -*- coding: utf-8 -*-
"""projects.py — DỰ ÁN cấp app và các QUY TRÌNH dựng video.

VÌ SAO CÓ TẦNG NÀY: trước đây "dự án" chỉ là thư mục làm việc suy ra từ tên file
record. Không có chỗ nào ghi người dùng đang làm gì với nó — quy trình nào, chọn
tài nguyên ra sao, tên gọi cho dễ nhớ — nên màn hình chính không có gì để hiện
ngoài một danh sách thư mục. Tầng này giữ phần "ý định của người dùng", còn thư
mục làm việc vẫn là khoá kỹ thuật mà draft và cache bám vào.

MỘT DỰ ÁN = MỘT FILE RECORD -> NHIỀU CAPCUT PROJECT.
"""
import json
import time
from pathlib import Path

import assetlib

# ─────────────────── QUY TRÌNH ───────────────────
# Thêm quy trình mới = thêm một dòng ở đây. Cái nào chưa xong thì `san_sang: False`
# — hiện thẻ mờ kèm chữ "sắp có" chứ KHÔNG ẩn đi: người dùng cần thấy app sẽ đi
# tới đâu, và biết thứ họ đang tìm chưa có thay vì đi tìm mòn mỏi.
QUY_TRINH = [
    {
        "ma": "record_ai",
        "ten": "Record AI Editor",
        "mo_ta": "Buổi ghi hình dài → AI tìm chủ đề → dựng nhiều short thành dự án CapCut sửa được.",
        "icon": "🎙️",
        "san_sang": True,
    },
    {
        "ma": "eq_gym",
        "ten": "EQ Gym AI Editor",
        "mo_ta": "Kịch bản có sẵn (bảng lưu ý CapCut) + thư mục clip/slide + 1 file giọng đọc → ráp thành dự án CapCut.",
        "icon": "🏋️",
        "san_sang": True,
    },
    {
        "ma": "koc_ai",
        "ten": "KOC AI Editor",
        "mo_ta": "Video KOC/review sản phẩm: bám kịch bản, chèn cảnh sản phẩm đúng nhịp.",
        "icon": "🛍️",
        "san_sang": False,
    },
    {
        "ma": "cartoon_ai",
        "ten": "Cartoon AI Editor",
        "mo_ta": "Kịch bản → phân cảnh hoạt hình → dựng timeline.",
        "icon": "🎨",
        "san_sang": False,
    },
    {
        "ma": "podcast_ai",
        "ten": "Podcast AI Editor",
        "mo_ta": "Podcast dài → trích đoạn hay → audiogram dọc có caption.",
        "icon": "🎧",
        "san_sang": False,
    },
]

QT_THEO_MA = {q["ma"]: q for q in QUY_TRINH}


# ─────────────────── CẤU HÌNH TÀI NGUYÊN ───────────────────
# Hai tầng, đúng như người dùng yêu cầu:
#   1. LỚP bật/tắt — quyết định draft có lớp đó hay không.
#   2. DANH SÁCH TRẮNG từng file — trong lớp đã bật, chỉ được dùng những file này.
# Danh sách trắng rỗng nghĩa là "cả kho", KHÔNG phải "không có gì": mặc định phải là
# hành vi cũ, nếu không người dùng cũ nâng cấp lên là draft đột nhiên mất hết SFX.
LOP_MAC_DINH = {
    "caption": True,
    "hook": True,
    "sfx": True,
    "emoji": True,
    "broll": True,
    "card_chot": True,
    "nhac_nen": True,
}


# Quy trình EQ Gym cần BA đường dẫn, không phải một file record như quy trình cũ.
# Để trong cau_hinh (JSON) thay vì thêm cột: mỗi quy trình sau này lại cần bộ tham
# số khác nhau, thêm cột cho từng cái là bảng phình mãi không dừng.
EQGYM_MAC_DINH = {
    "kich_ban": "",      # bảng lưu ý CapCut (.xlsx/.xls) hoặc CSV kịch bản
    "nguon": "",         # thư mục chứa clip + slide (tìm cả thư mục con)
    "voice": "",         # MỘT file giọng đọc cho cả bài
    "tu_dong_can": True,  # bóc lời rồi căn từng cảnh vào giọng; tắt = xếp theo thứ tự
}


def cau_hinh_mac_dinh() -> dict:
    return {"lop": dict(LOP_MAC_DINH), "chon": {"sfx": [], "sticker": [], "font": []},
            "eqgym": dict(EQGYM_MAC_DINH)}


def _chuan_hoa(c) -> dict:
    """Cấu hình cũ/thiếu khoá vẫn phải chạy — thiếu thì lấy mặc định, đừng ném."""
    goc = cau_hinh_mac_dinh()
    if not isinstance(c, dict):
        return goc
    lop = dict(goc["lop"])
    lop.update({k: bool(v) for k, v in (c.get("lop") or {}).items() if k in goc["lop"]})
    chon = dict(goc["chon"])
    for k in chon:
        v = (c.get("chon") or {}).get(k)
        if isinstance(v, list):
            chon[k] = [str(x) for x in v]
    eq = dict(goc["eqgym"])
    for k, v in (c.get("eqgym") or {}).items():
        if k in eq:
            eq[k] = bool(v) if isinstance(eq[k], bool) else str(v)
    return {"lop": lop, "chon": chon, "eqgym": eq}


# ─────────────────── CRUD ───────────────────

def _bo_unique_work_dir() -> bool:
    """Gỡ ràng buộc UNIQUE(work_dir) khỏi bảng đã tạo từ bản trước.

    Bản đầu đặt UNIQUE vì tưởng một record chỉ thuộc một dự án. Sai: người dùng cần
    dựng lại cùng buổi ghi hình theo hướng khác. SQLite không DROP CONSTRAINT được
    nên phải dựng lại bảng — làm một lần, tự nhận ra qua sqlite_master."""
    c = assetlib.conn()
    try:
        r = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='projects'").fetchone()
        if not r or "UNIQUE" not in (r["sql"] or "").upper():
            return False
        c.executescript("""
            PRAGMA foreign_keys=off;
            BEGIN;
            CREATE TABLE projects_moi(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ten TEXT NOT NULL, quy_trinh TEXT NOT NULL,
              record_path TEXT, work_dir TEXT, editor TEXT DEFAULT 'shared',
              cau_hinh TEXT, ghi_chu TEXT, tao_luc REAL, sua_luc REAL);
            INSERT INTO projects_moi
              SELECT id,ten,quy_trinh,record_path,work_dir,editor,cau_hinh,ghi_chu,tao_luc,sua_luc
              FROM projects;
            DROP TABLE projects;
            ALTER TABLE projects_moi RENAME TO projects;
            CREATE INDEX IF NOT EXISTS ix_proj_work ON projects(work_dir);
            COMMIT;
            PRAGMA foreign_keys=on;
        """)
        return True
    finally:
        c.close()


_bo_unique_work_dir()


def _dong(r) -> dict:
    d = dict(r)
    try:
        d["cau_hinh"] = _chuan_hoa(json.loads(d.get("cau_hinh") or "{}"))
    except ValueError:
        d["cau_hinh"] = cau_hinh_mac_dinh()
    q = QT_THEO_MA.get(d.get("quy_trinh")) or {}
    d["quy_trinh_ten"] = q.get("ten", d.get("quy_trinh"))
    d["quy_trinh_icon"] = q.get("icon", "📁")
    return d


def liet_ke() -> list:
    c = assetlib.conn()
    rows = [_dong(r) for r in c.execute(
        "SELECT * FROM projects ORDER BY COALESCE(sua_luc, tao_luc) DESC").fetchall()]
    c.close()
    return rows


def lay(pid: int) -> dict | None:
    c = assetlib.conn()
    r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    c.close()
    return _dong(r) if r else None


def lay_theo_work(work_dir: str) -> dict | None:
    c = assetlib.conn()
    r = c.execute("SELECT * FROM projects WHERE work_dir=?", (work_dir,)).fetchone()
    c.close()
    return _dong(r) if r else None


def tao(ten: str, quy_trinh: str, record_path: str = "", work_dir: str = "",
        editor: str = "shared", cau_hinh: dict = None) -> dict:
    q = QT_THEO_MA.get(quy_trinh)
    if not q:
        raise ValueError(f"Không có quy trình '{quy_trinh}'")
    if not q["san_sang"]:
        raise ValueError(f"Quy trình '{q['ten']}' chưa ra mắt")
    if not (ten or "").strip():
        raise ValueError("Dự án phải có tên")
    now = time.time()
    c = assetlib.conn()
    cur = c.execute(
        "INSERT INTO projects(ten,quy_trinh,record_path,work_dir,editor,cau_hinh,tao_luc,sua_luc)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (ten.strip(), quy_trinh, record_path or None, work_dir or None, editor,
         json.dumps(_chuan_hoa(cau_hinh), ensure_ascii=False), now, now))
    c.commit()
    pid = cur.lastrowid
    c.close()
    return lay(pid)


def sua(pid: int, **truong) -> dict:
    """Chỉ cho sửa các trường AN TOÀN. `work_dir` KHÔNG nằm trong danh sách: draft
    CapCut và cache đều bám theo nó, đổi là hỏng dự án đã dựng."""
    cho_phep = {"ten", "editor", "ghi_chu", "record_path", "cau_hinh"}
    dat, gt = [], []
    for k, v in truong.items():
        if k not in cho_phep or v is None:
            continue
        if k == "cau_hinh":
            v = json.dumps(_chuan_hoa(v), ensure_ascii=False)
        if k == "ten" and not str(v).strip():
            raise ValueError("Tên dự án không được rỗng")
        dat.append(f"{k}=?"); gt.append(v)
    if not dat:
        return lay(pid)
    dat.append("sua_luc=?"); gt.append(time.time()); gt.append(pid)
    c = assetlib.conn()
    c.execute(f"UPDATE projects SET {', '.join(dat)} WHERE id=?", gt)
    c.commit(); c.close()
    return lay(pid)


def xoa(pid: int) -> dict:
    """Chỉ bỏ dự án khỏi danh sách. KHÔNG đụng tới thư mục làm việc hay draft CapCut —
    xoá dữ liệu thật phải là một hành động riêng, nói rõ mất gì (luật cứng #4)."""
    p = lay(pid)
    if not p:
        raise ValueError("Không thấy dự án")
    c = assetlib.conn()
    c.execute("DELETE FROM projects WHERE id=?", (pid,))
    c.commit(); c.close()
    return {"da_xoa": p["ten"], "giu_lai": {"work_dir": p.get("work_dir")}}


# ─────────────────── GẮN VỚI DỮ LIỆU CÓ SẴN ───────────────────

def nhan_du_an_cu(work_root: Path) -> int:
    """Gom thư mục làm việc đã có vào bảng projects.

    Máy đang chạy dở (như máy trạm lúc nghiệm thu) đã có sẵn thư mục làm việc và
    draft. Nâng cấp mà bỏ rơi chúng thì màn hình chính trống trơn trong khi dữ liệu
    vẫn nằm trên đĩa — người dùng tưởng mất hết."""
    if not work_root.is_dir():
        return 0
    them = 0
    for d in sorted(work_root.iterdir()):
        if not d.is_dir() or lay_theo_work(d.name):
            continue
        nguon = ""
        for ten in ("nguon.json", "topics.json"):
            f = d / ten
            if f.is_file():
                try:
                    j = json.loads(f.read_text(encoding="utf-8"))
                    nguon = j.get("path") or j.get("source") or ""
                    if nguon:
                        break
                except (OSError, ValueError):
                    pass
        try:
            tao(d.name, "record_ai", record_path=nguon, work_dir=d.name)
            them += 1
        except ValueError:
            pass
    return them
