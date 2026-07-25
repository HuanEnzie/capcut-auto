# -*- coding: utf-8 -*-
"""capcut_inventory.py — Kiểm kê tài nguyên CapCut CÓ SẴN trên máy này.

Kho (`assetlib`) chỉ biết tài nguyên ĐÃ DÙNG trong draft. Module này bù nửa còn
thiếu: quét thẳng cache của CapCut để biết trên máy đang có sẵn những gì, rồi
đối chiếu ba nguồn:

  cache CapCut  ->  có sẵn, dùng được ngay, không cần tải
  draft         ->  đã dùng thật, và CHỈ ở đây mới có tên hiển thị
  library.db    ->  kho gu đã học của từng editor

Đo trên máy dev: 319 gói tài nguyên (353 MB) nằm sẵn, app mới chạm tới 19.

  python capcut_inventory.py --scan          # quét lại, ghi vào library.db
  python capcut_inventory.py --stats         # số liệu tóm tắt
  python capcut_inventory.py --unused 20     # có sẵn mà chưa dùng
"""
import argparse, json, time
from pathlib import Path

import assetlib

# Gói trong cache KHÔNG ghi mình là loại gì. Suy từ file đặc trưng bên trong —
# đã đối chiếu với loại thật lấy từ draft để chọn dấu hiệu đáng tin:
#   extra.json có khoá "transition"  -> chắc chắn transition (kèm defaultDura)
#   effectStyle.json                 -> hiệu ứng chữ (fill/strokes/textable)
#   heycanInfo.json | final.gif      -> sticker
#   *faceu* | makeup.*               -> làm đẹp (CapCut tự tải bộ này lúc mở lần đầu)
# Chữ ký kiểu "main.scene + Quad.mesh" từng có vẻ là transition nhưng lẫn cả
# makeup -> đã bỏ. Không đoán được thì ghi "chưa rõ", KHÔNG bịa.
UNKNOWN = "chưa rõ"


def classify(pkg: Path) -> str:
    names = {f.name for f in pkg.rglob("*") if f.is_file()}
    ex = next(pkg.glob("*/extra.json"), None)
    if ex:
        try:
            if "transition" in json.loads(ex.read_text(encoding="utf-8", errors="replace")):
                return "transition"
        except (ValueError, OSError):
            pass
    if "effectStyle.json" in names:
        return "hiệu ứng chữ"
    if "template.js" in names or "main.js" in names:
        return "mẫu chữ"
    if "heycanInfo.json" in names or "final.gif" in names:
        return "sticker"
    if any("faceu" in n or n.startswith("makeup") for n in names):
        return "làm đẹp"
    if "filter.material" in names:
        return "filter"
    if "infoSticker.lua" in names:
        return "hiệu ứng"
    return UNKNOWN


# resource_id của tài nguyên thật là số 19 chữ số. ID ngắn (star/mirror/linear/
# rect) là module thuật toán nội bộ của CapCut — đếm chúng là "tài nguyên" thì
# thống kê sai ngay từ đầu.
def is_internal(rid: str) -> bool:
    return len(rid) < 13


SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory(
  resource_id TEXT PRIMARY KEY,
  cache_dir TEXT,            -- effect | artistEffect | '' (chỉ thấy trong draft)
  internal INTEGER,          -- 1 = module nội bộ của CapCut
  kind_guess TEXT,           -- suy từ gói
  kind_real TEXT,            -- loại thật lấy từ draft (chắc chắn hơn)
  name_internal TEXT, name_display TEXT,
  size INTEGER, mtime REAL,
  has_thumb INTEGER,         -- gói có ảnh sẵn không (đừng gọi ảnh cho gói không có)
  used_count INTEGER, used_drafts INTEGER, last_used REAL,
  in_lib INTEGER,
  scanned_at REAL
);
CREATE INDEX IF NOT EXISTS ix_inv_used ON inventory(used_count);
"""

# bucket trong draft materials -> tên loại hiển thị
BUCKET_VI = {
    "stickers": "sticker", "text_templates": "mẫu chữ", "transitions": "transition",
    "effects": "hiệu ứng", "video_effects": "hiệu ứng", "audios": "âm thanh",
    "material_animations": "hoạt ảnh", "filters": "filter", "fonts": "font",
}


THUMB_PRIORITY = ("singleImage.png", "final.gif", "cover_icon.png")
SAFE_ID = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def thumb_path(rid: str):
    """Ảnh đại diện của một gói trong cache, hoặc None.

    MỘT hàm duy nhất cho cả lúc quét (ghi cờ has_thumb) lẫn lúc phục vụ ảnh. Trước
    đó hai chỗ định nghĩa "có ảnh" khác nhau (rglob vs glob một tầng) nên bảng vẫn
    xin ảnh cho gói không có -> 404 hàng loạt.
    """
    if not rid or not set(rid) <= SAFE_ID:      # chặn ../ và tên lạ
        return None
    for d in ("effect", "artistEffect"):
        pkg = assetlib.cache_root() / d / rid
        if not pkg.is_dir():
            continue
        files = [f for f in pkg.rglob("*") if f.is_file()]
        for want in THUMB_PRIORITY:
            hit = next((f for f in files if f.name == want), None)
            if hit:
                return hit
        hit = next((f for f in sorted(files) if f.suffix.lower() in (".png", ".gif", ".webp")), None)
        if hit:
            return hit
    return None


def scan_cache() -> dict:
    """Gói tài nguyên đang nằm trong cache CapCut."""
    cc = assetlib.cache_root()
    out = {}
    for d in ("effect", "artistEffect"):
        base = cc / d
        if not base.is_dir():
            continue
        for pkg in base.iterdir():
            if not pkg.is_dir():
                continue
            files = [f for f in pkg.rglob("*") if f.is_file()]
            if not files:
                continue
            name = ""
            cfg = next(pkg.glob("*/config.json"), None)
            if cfg:
                try:
                    name = json.loads(cfg.read_text(encoding="utf-8", errors="replace")).get("name", "")
                except (ValueError, OSError):
                    pass
            out[pkg.name] = {
                "cache_dir": d, "internal": int(is_internal(pkg.name)),
                "kind_guess": UNKNOWN if is_internal(pkg.name) else classify(pkg),
                "name_internal": name,
                "size": sum(f.stat().st_size for f in files),
                "mtime": pkg.stat().st_mtime,
                # ghi sẵn để giao diện KHÔNG gọi ảnh cho gói không có ảnh —
                # 40 dòng bảng mà 22 cái trả 404 thì bẩn console, tốn request vô ích
                "has_thumb": int(thumb_path(pkg.name) is not None),
            }
    return out


def scan_drafts() -> dict:
    """Tài nguyên ĐÃ DÙNG trong draft — nguồn duy nhất có tên hiển thị thật."""
    dr = assetlib.draft_root()
    out = {}
    for p in sorted(dr.iterdir()) if dr.is_dir() else []:
        f = p / "draft_content.json"
        if not f.is_file():
            continue
        try:
            c = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (ValueError, OSError):
            continue
        mt = f.stat().st_mtime
        for bucket, items in (c.get("materials") or {}).items():
            if not isinstance(items, list):
                continue
            for m in items:
                rid = str(m.get("resource_id") or "")
                if not rid or rid == "0":
                    continue
                r = out.setdefault(rid, {"used_count": 0, "drafts": set(),
                                         "name_display": "", "kind_real": "", "last_used": 0})
                r["used_count"] += 1
                r["drafts"].add(p.name)
                r["last_used"] = max(r["last_used"], mt)
                if m.get("name") and not r["name_display"]:
                    r["name_display"] = m["name"]
                if not r["kind_real"]:
                    r["kind_real"] = BUCKET_VI.get(bucket, bucket)
    return out


def rebuild(log=print) -> dict:
    """Quét lại toàn bộ và ghi vào library.db. Vài giây, nên chạy trong job nền."""
    t0 = time.time()
    log("Quét cache CapCut…")
    cache = scan_cache()
    log(f"  {len(cache)} gói trong cache")
    log("Đối chiếu draft…")
    used = scan_drafts()
    log(f"  {len(used)} tài nguyên từng được dùng")

    c = assetlib.conn()
    c.executescript(SCHEMA)
    in_lib = {str(r[0]) for r in c.execute(
        "SELECT resource_id FROM assets WHERE resource_id IS NOT NULL").fetchall()}
    now = time.time()
    rows = []
    for rid in set(cache) | set(used):
        ca = cache.get(rid, {})
        us = used.get(rid, {})
        rows.append((
            rid, ca.get("cache_dir", ""), ca.get("internal", 0),
            ca.get("kind_guess", UNKNOWN), us.get("kind_real", ""),
            ca.get("name_internal", ""), us.get("name_display", ""),
            ca.get("size", 0), ca.get("mtime"), ca.get("has_thumb", 0),
            us.get("used_count", 0), len(us.get("drafts", ())), us.get("last_used"),
            int(rid in in_lib), now))
    c.execute("DROP TABLE IF EXISTS inventory")     # schema đổi -> dựng lại cho gọn
    c.executescript(SCHEMA)
    c.executemany("INSERT INTO inventory VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.close()
    log(f"Xong trong {time.time()-t0:.1f}s — {len(rows)} bản ghi")
    return stats()


def stats() -> dict:
    """Số liệu cho dashboard. Luôn TÁCH tài nguyên thật khỏi module nội bộ."""
    c = assetlib.conn()
    c.executescript(SCHEMA)
    q = lambda sql, *a: c.execute(sql, a).fetchone()
    real = "internal=0 AND cache_dir!=''"
    n_all, sz_all = q(f"SELECT COUNT(*), COALESCE(SUM(size),0) FROM inventory WHERE {real}")
    n_used, sz_used = q(f"SELECT COUNT(*), COALESCE(SUM(size),0) FROM inventory "
                        f"WHERE {real} AND used_count>0")
    n_int, sz_int = q("SELECT COUNT(*), COALESCE(SUM(size),0) FROM inventory WHERE internal=1")
    n_lib = q("SELECT COUNT(*) FROM inventory WHERE in_lib=1")[0]
    n_ghost = q("SELECT COUNT(*) FROM inventory WHERE cache_dir='' AND used_count>0")[0]
    by_kind = [dict(r) for r in c.execute(
        f"SELECT COALESCE(NULLIF(kind_real,''), kind_guess) kind, COUNT(*) n, "
        f"SUM(size) sz, SUM(used_count>0) used FROM inventory WHERE {real} "
        f"GROUP BY kind ORDER BY n DESC").fetchall()]
    scanned = q("SELECT MAX(scanned_at) FROM inventory")[0]
    c.close()
    return {"n_assets": n_all, "size": sz_all, "n_used": n_used, "size_used": sz_used,
            "n_unused": n_all - n_used, "size_unused": sz_all - sz_used,
            "n_internal": n_int, "size_internal": sz_int,
            "n_in_lib": n_lib, "n_online_only": n_ghost,
            "by_kind": by_kind, "scanned_at": scanned}


def rows(kind: str = "", used: str = "", q: str = "", limit: int = 60) -> list:
    """Bảng chi tiết. used: ''|'yes'|'no'. kind nhận nhiều loại, ngăn bằng dấu phẩy.

    Lọc phải làm ở ĐÂY chứ không phải ở giao diện: 144 gói "làm đẹp" chiếm hết
    top dung lượng, lấy 24 dòng đầu rồi mới lọc thì bảng gợi ý còn 4 dòng.
    """
    c = assetlib.conn()
    c.executescript(SCHEMA)
    sql = ["SELECT * FROM inventory WHERE internal=0"]
    args = []
    kinds = [k.strip() for k in kind.split(",") if k.strip()]
    if kinds:
        sql.append("AND COALESCE(NULLIF(kind_real,''), kind_guess) IN (%s)"
                   % ",".join("?" * len(kinds)))
        args += kinds
    if used == "yes":
        sql.append("AND used_count>0")
    elif used == "no":
        sql.append("AND used_count=0 AND cache_dir!=''")
    if q:
        sql.append("AND (name_display LIKE ? OR name_internal LIKE ? OR resource_id LIKE ?)")
        args += [f"%{q}%"] * 3
    sql.append("ORDER BY used_count DESC, size DESC LIMIT ?"); args.append(limit)
    out = [dict(r) for r in c.execute(" ".join(sql), args).fetchall()]
    c.close()
    return out


def _mb(n):
    return f"{(n or 0)/1e6:.0f} MB"


def main():
    ap = argparse.ArgumentParser(description="Kiểm kê tài nguyên CapCut trên máy này")
    ap.add_argument("--scan", action="store_true", help="quét lại và ghi vào library.db")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--unused", type=int, metavar="N", help="N gói có sẵn mà chưa dùng")
    a = ap.parse_args()
    if a.scan:
        rebuild()
    if a.stats or a.scan:
        s = stats()
        print(f"\nTài nguyên trên máy : {s['n_assets']} gói · {_mb(s['size'])}")
        print(f"  đã dùng trong draft: {s['n_used']} · {_mb(s['size_used'])}")
        print(f"  CÓ SẴN chưa dùng   : {s['n_unused']} · {_mb(s['size_unused'])}")
        print(f"  đã vào kho gu      : {s['n_in_lib']}")
        print(f"module nội bộ CapCut : {s['n_internal']} · {_mb(s['size_internal'])} (không tính là tài nguyên)")
        print("\nTheo loại:")
        for k in s["by_kind"]:
            print(f"  {(k['kind'] or '—'):<16} {k['n']:>4} gói  {_mb(k['sz']):>8}  dùng {k['used']}")
    if a.unused:
        print(f"\n{a.unused} gói có sẵn chưa dùng (to nhất trước):")
        for r in rows(used="no", limit=a.unused):
            nm = r["name_display"] or r["name_internal"] or r["resource_id"]
            print(f"  {_mb(r['size']):>8}  {r['kind_guess']:<14} {nm[:46]}")
    if not (a.scan or a.stats or a.unused):
        ap.print_help()


if __name__ == "__main__":
    main()
