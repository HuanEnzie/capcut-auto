# -*- coding: utf-8 -*-
"""assetlib.py — Kho tài nguyên 2 tầng cho app: assets/default (app) + assets/user (editor).

Chống trùng lặp bằng 2 khoá:
  - resource_id : CapCut cấp, ổn định (sticker / hiệu ứng chữ / transition)
  - sha256      : nội dung file (SFX / stock / ảnh / font) — cùng file ở 2 máy 2 đường dẫn
Manifest: library.db (sqlite trong stdlib, không cần cài thêm).

  python assetlib.py --stats
"""
import argparse, hashlib, os, re, shutil, sqlite3, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
DB = ROOT / "library.db"


def load_env(path: Path = None) -> int:
    """Nạp API key từ file .env cạnh mã nguồn.

    Ở đây (chứ không ở app.py) vì mọi lối vào đều import assetlib: app web,
    build_short_draft chạy dòng lệnh, các script kho. Không dùng python-dotenv
    để bản đóng gói khỏi thêm phụ thuộc.

    Biến ĐÃ có trong môi trường được giữ nguyên — chạy kèm `set KEY=...` vẫn đè
    được file, tiện khi cần thử key khác mà không sửa .env.
    """
    p = path or ROOT / ".env"
    if not p.exists():
        return 0
    n = 0
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


load_env()


# ─────────────────── DÒ CAPCUT TRÊN MÁY NGƯỜI DÙNG ───────────────────
# Trước đây mỗi module tự đoán đường dẫn theo một kiểu, ba chỗ hardcode thẳng
# "C:/Users/Acer/..." — máy khác chạy là sai ngay. Gom về một chỗ duy nhất.
#
# Nguồn chuẩn là chính CapCut: nó ghi thư mục draft vào
#   <CapCut>/User Data/Config/globalSetting  ->  currentCustomDraftPath=...
# Đọc khoá đó mới bắt được trường hợp người dùng ĐỔI thư mục draft sang ổ khác
# trong Cài đặt của CapCut — đoán theo %LOCALAPPDATA% thì trượt.

# CapCut quốc tế và Jianying (bản Trung) cùng cấu trúc, chỉ khác tên thư mục.
_CAPCUT_DIRS = ("CapCut", "JianyingPro", "CapCut Pro")
_DRAFT_LEAF = ("User Data", "Projects", "com.lveditor.draft")


def _capcut_homes():
    """Các thư mục dữ liệu CapCut có thể có trên máy này."""
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("APPDATA")):
        if not base:
            continue
        for name in _CAPCUT_DIRS:
            p = Path(base) / name
            if (p / "User Data").is_dir():
                yield p


def _draft_path_from_settings(home: Path):
    """Đọc currentCustomDraftPath trong globalSetting (file INI, giá trị escape \\\\)."""
    f = home / "User Data" / "Config" / "globalSetting"
    if not f.is_file():
        return None
    try:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("currentCustomDraftPath="):
                raw = line.split("=", 1)[1].strip().strip('"').replace("\\\\", "\\")
                p = Path(raw)
                if p.is_dir():
                    return p
    except OSError:
        pass
    return None


def find_capcut(refresh: bool = False) -> dict:
    """Dò CapCut. Trả {draft, cache, home, found, source} — luôn có đường dẫn để
    module khác dùng được ngay cả khi máy chưa cài (khi đó found=False)."""
    if not refresh and getattr(find_capcut, "_cache", None):
        return find_capcut._cache

    env = os.environ.get("CAPCUT_DRAFTS_ROOT")          # ưu tiên: người dùng chỉ định
    out = None
    if env and Path(env).is_dir():
        home = Path(env).parents[2] if len(Path(env).parents) >= 3 else None
        out = {"draft": Path(env), "home": home, "found": True, "source": "CAPCUT_DRAFTS_ROOT"}
    else:
        for home in _capcut_homes():
            p = _draft_path_from_settings(home)          # CapCut tự khai báo
            if p:
                out = {"draft": p, "home": home, "found": True, "source": "globalSetting"}
                break
            p = home.joinpath(*_DRAFT_LEAF)              # vị trí mặc định
            if p.is_dir():
                out = {"draft": p, "home": home, "found": True, "source": "mặc định"}
                break
    if out is None:                                      # chưa cài: vẫn trả đường dẫn đoán
        home = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut"
        out = {"draft": home.joinpath(*_DRAFT_LEAF), "home": home,
               "found": False, "source": "không tìm thấy CapCut"}
    out["cache"] = (out["home"] or Path()) / "User Data" / "Cache"
    find_capcut._cache = out
    return out


def sfx_kho(extra_dir: str = "") -> dict:
    """Tên hiển thị -> đường dẫn file SFX. Gộp thư mục chỉ định + KHO đã học.

    Trước đây hai chỗ hardcode thẳng 'E:/E Download/meme' (máy dev). Máy khác không
    có thư mục đó thì danh sách SFX rỗng -> AI không chọn được gì -> draft dựng ra
    KHÔNG CÓ SFX NÀO mà chẳng báo lỗi. Hỏng im lặng, tệ hơn là crash.

    Thứ tự nguồn: tham số -> CAPCUT_SFX_DIR -> kho assets/**/sfx (đi theo app).
    """
    ra = {}
    for f in sorted(ASSETS.rglob("sfx/*.mp3")):        # kho học từ draft, đi theo app
        ten = re.sub(r"^[0-9a-f]{8,16}_", "", f.name)  # bỏ tiền tố băm khi lưu kho
        ra.setdefault(ten, f)
    for d in (extra_dir, os.environ.get("CAPCUT_SFX_DIR", "")):
        if d and Path(d).is_dir():
            for f in sorted(Path(d).glob("*.mp3")):
                ra[f.name] = f                          # thư mục chỉ định được ưu tiên
    return ra


def draft_root() -> Path:
    return find_capcut()["draft"]


def cache_root() -> Path:
    return find_capcut()["cache"]

# thư mục con theo loại tài nguyên
KIND_DIR = {
    "sticker": "sticker", "text_template": "texteffect", "audio": "sfx",
    "video": "stock", "image": "stock", "font": "font",
    "transition": "transition", "effect": "effect", "animation": "animation",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL, resource_id TEXT, sha256 TEXT,
  name TEXT, category TEXT, path_in_lib TEXT, src_path TEXT, size INTEGER,
  origin TEXT NOT NULL,              -- default | user
  owner  TEXT,                       -- app | dan | nguyen | shared
  first_seen REAL, last_used REAL,
  use_count INTEGER DEFAULT 0,       -- số lần được dùng khi export
  drop_count INTEGER DEFAULT 0       -- số lần bị editor gỡ bỏ (tín hiệu âm)
);
CREATE INDEX IF NOT EXISTS ix_rid ON assets(resource_id);
CREATE INDEX IF NOT EXISTS ix_sha ON assets(sha256);
CREATE TABLE IF NOT EXISTS usage(
  asset_id INTEGER, draft TEXT, action TEXT, ts REAL
);
"""


def conn():
    ASSETS.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def lp(p) -> str:
    r"""Đường dẫn dài cho Windows. Gói effect của CapCut có tên file rất dài
    (vd alphaOutput_2021011219075...), cộng thư mục lồng nhau là vượt MAX_PATH 260
    -> WinError 3. Tiền tố \\?\ gỡ giới hạn này."""
    p = Path(p).resolve()
    s = str(p)
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s.replace("/", "\\")
    return s


def _size(p: Path) -> int:
    """Dung lượng thật — thư mục thì cộng dồn nội dung."""
    try:
        if p.is_dir():
            return sum(q.stat().st_size for q in p.rglob("*") if q.is_file())
        return p.stat().st_size
    except OSError:
        return 0


def _hash_file(p: Path, h):
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)


def sha256_file(p: Path, cap_mb=400) -> str | None:
    """Hash nội dung. Hỗ trợ CẢ THƯ MỤC vì sticker/hiệu ứng chữ của CapCut là
    gói effect (thư mục chứa config.json, singleImage.png, js/...), không phải file đơn.
    Bỏ qua thứ quá lớn (media nguồn) để khỏi tốn thời gian."""
    try:
        h = hashlib.sha256()
        if p.is_dir():
            files = sorted(q for q in p.rglob("*") if q.is_file())
            if sum(q.stat().st_size for q in files) > cap_mb * 1024 * 1024:
                return None
            for q in files:
                h.update(str(q.relative_to(p)).replace("\\", "/").encode())
                _hash_file(q, h)
        else:
            if p.stat().st_size > cap_mb * 1024 * 1024:
                return None
            _hash_file(p, h)
        return h.hexdigest()
    except OSError:
        return None


def find(c, resource_id=None, sha=None):
    """Tìm asset đã có -> chống duplicate. Ưu tiên resource_id, sau đó sha256."""
    if resource_id:
        r = c.execute("SELECT * FROM assets WHERE resource_id=?", (str(resource_id),)).fetchone()
        if r:
            return r
    if sha:
        r = c.execute("SELECT * FROM assets WHERE sha256=?", (sha,)).fetchone()
        if r:
            return r
    return None


def add(kind, *, name=None, category=None, src_path=None, resource_id=None,
        origin="user", owner="shared", draft=None, copy=True, cap_mb=400):
    """Nạp 1 tài nguyên vào kho. Trả (row, status) với status = new | dup.

    Đã có (trùng resource_id hoặc sha256) -> KHÔNG copy lần 2, chỉ ghi nhận lượt dùng.
    """
    c = conn()
    src = Path(src_path) if src_path else None
    sha = sha256_file(src, cap_mb) if (src and src.exists()) else None

    row = find(c, resource_id, sha)
    if row:
        c.execute("UPDATE assets SET use_count=use_count+1, last_used=? WHERE id=?",
                  (time.time(), row["id"]))
        if draft:
            c.execute("INSERT INTO usage VALUES(?,?,?,?)", (row["id"], draft, "reuse", time.time()))
        c.commit()
        out = c.execute("SELECT * FROM assets WHERE id=?", (row["id"],)).fetchone()
        c.close()
        return out, "dup"

    # mới -> copy file vào kho.
    # Không hash được (file quá lớn) và cũng không có resource_id => không dedup nổi
    # => chỉ ghi tham chiếu, KHÔNG copy, tránh phình kho + trùng lặp âm thầm.
    lib_rel = None
    if src and src.exists() and copy and (sha or resource_id):
        sub = KIND_DIR.get(kind, kind)
        dest_dir = ASSETS / ("default" if origin == "default" else "user") / (owner if origin != "default" else "") / sub
        dest_dir.mkdir(parents=True, exist_ok=True)
        stem = (name or src.stem or "asset").replace("/", "_").replace("\\", "_")[:60]
        suffix = "" if src.is_dir() else (src.suffix or "")
        dest = dest_dir / f"{(sha or str(resource_id) or '0')[:12]}_{stem}{suffix}"
        if not dest.exists():
            try:
                # gói effect là THƯ MỤC -> copytree; SFX/font/stock là file -> copy2
                if src.is_dir():
                    shutil.copytree(lp(src), lp(dest))
                else:
                    shutil.copy2(lp(src), lp(dest))
            except OSError:
                dest = None
        lib_rel = str(dest.relative_to(ROOT)).replace("\\", "/") if dest else None

    now = time.time()
    cur = c.execute(
        "INSERT INTO assets(kind,resource_id,sha256,name,category,path_in_lib,src_path,size,"
        "origin,owner,first_seen,last_used,use_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (kind, str(resource_id) if resource_id else None, sha, name, category, lib_rel,
         str(src) if src else None, _size(src) if (src and src.exists()) else None,
         origin, owner, now, now))
    aid = cur.lastrowid
    if draft:
        c.execute("INSERT INTO usage VALUES(?,?,?,?)", (aid, draft, "add", now))
    c.commit()
    out = c.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
    c.close()
    return out, "new"


def mark_dropped(resource_id=None, sha=None, draft=None):
    """Editor gỡ bỏ tài nguyên -> tín hiệu âm, hạ ưu tiên đề xuất lần sau."""
    c = conn()
    row = find(c, resource_id, sha)
    if row:
        c.execute("UPDATE assets SET drop_count=drop_count+1 WHERE id=?", (row["id"],))
        if draft:
            c.execute("INSERT INTO usage VALUES(?,?,?,?)", (row["id"], draft, "drop", time.time()))
        c.commit()
    c.close()
    return row


def pick(kind, owner=None, limit=20):
    """Lấy tài nguyên ưu tiên: kho user (đúng editor) > shared > default; điểm = dùng nhiều, ít bị gỡ."""
    c = conn()
    rows = c.execute(
        "SELECT * FROM assets WHERE kind=? ORDER BY "
        "  CASE WHEN owner=? THEN 0 WHEN origin='user' THEN 1 ELSE 2 END,"
        "  (use_count - drop_count*2) DESC, last_used DESC LIMIT ?",
        (kind, owner or "", limit)).fetchall()
    c.close()
    return rows


def pick_one(kind, owner=None):
    rows = pick(kind, owner=owner, limit=1)
    return rows[0] if rows else None


def stats():
    c = conn()
    rows = c.execute(
        "SELECT kind, origin, owner, COUNT(*) n, SUM(use_count) uses FROM assets "
        "GROUP BY kind, origin, owner ORDER BY n DESC").fetchall()
    total = c.execute("SELECT COUNT(*) n, SUM(size) sz FROM assets").fetchone()
    c.close()
    return rows, total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    rows, total = stats()
    print(f"{'kind':16}{'origin':9}{'owner':10}{'n':>5}{'uses':>7}")
    for r in rows:
        print(f"{r['kind']:16}{r['origin']:9}{str(r['owner'] or ''):10}{r['n']:>5}{str(r['uses'] or 0):>7}")
    sz = (total["sz"] or 0) / 1e6
    print(f"\nTổng: {total['n']} tài nguyên, {sz:.1f} MB")
