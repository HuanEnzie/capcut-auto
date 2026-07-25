# -*- coding: utf-8 -*-
"""asset_restore.py — Cài tài nguyên từ kho vào ĐÚNG chỗ CapCut trên máy mới.

Vấn đề: sticker / hiệu ứng chữ / transition trong CapCut phải bấm tải trong app mới có,
nó nằm ở  <LOCALAPPDATA>/CapCut/User Data/Cache/{effect|artistEffect}/<resource_id>/<hash>/
Draft lại trỏ path TUYỆT ĐỐI vào đó -> máy mới mở draft là thiếu.

Cách xử lý: kho đã giữ nguyên GÓI EFFECT (cả thư mục), nên chỉ cần
  1) copy ngược gói vào đúng cache của máy hiện tại
  2) rewrite path trong draft sang đường dẫn máy hiện tại
=> không phải bấm tải thủ công trong CapCut.

  python asset_restore.py --check                  # máy này thiếu tài nguyên nào
  python asset_restore.py --restore                # cài hết từ kho vào cache
  python asset_restore.py --fix-draft 1107_short04 # sửa path trong 1 draft cho khớp máy này
"""
import argparse, json, os, shutil, sys
from pathlib import Path

import assetlib

CACHE_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "User Data" / "Cache"
DRAFT_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
MARK = "/user data/cache/"


def cache_rel(src_path: str) -> str | None:
    """Lấy phần đường dẫn TƯƠNG ĐỐI so với thư mục Cache, vd 'effect/<rid>/<hash>'.
    Đây là thứ giữ nguyên được giữa các máy (chỉ phần gốc LOCALAPPDATA là khác)."""
    if not src_path:
        return None
    s = src_path.replace("\\", "/")
    i = s.lower().find(MARK)
    return s[i + len(MARK):] if i >= 0 else None


def cacheable():
    """Các asset thuộc dạng phải-tải-trong-CapCut (có đường dẫn nằm trong Cache)."""
    c = assetlib.conn()
    rows = c.execute("SELECT * FROM assets WHERE src_path LIKE '%User Data/Cache/%'"
                     " OR src_path LIKE '%User Data\\Cache\\%'").fetchall()
    c.close()
    out = []
    for r in rows:
        rel = cache_rel(r["src_path"])
        if rel:
            out.append((r, rel))
    return out


def check():
    rows = cacheable()
    miss, have = [], []
    for r, rel in rows:
        (have if (CACHE_ROOT / rel).exists() else miss).append((r, rel))
    print(f"Cache CapCut: {CACHE_ROOT}")
    print(f"  đã có   : {len(have)}")
    print(f"  còn THIẾU: {len(miss)}")
    for r, rel in miss:
        inlib = "kho CÓ gói" if r["path_in_lib"] else "kho KHÔNG có gói -> phải tải tay"
        print(f"    - {r['kind']:14} {str(r['name'])[:40]:42} rid={r['resource_id']}  [{inlib}]")
    return have, miss


def restore(dry=False):
    """Copy gói effect từ kho vào cache CapCut của máy hiện tại."""
    rows = cacheable()
    n_ok = n_skip = n_nolib = 0
    for r, rel in rows:
        dest = CACHE_ROOT / rel
        if dest.exists():
            n_skip += 1
            continue
        if not r["path_in_lib"]:
            n_nolib += 1
            print(f"  ! không có gói trong kho: {r['name']} (rid={r['resource_id']})")
            continue
        src = assetlib.ROOT / r["path_in_lib"]
        if not src.exists():
            n_nolib += 1
            continue
        if dry:
            print(f"  [dry] {src.name} -> {dest}")
            n_ok += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            # dùng đường dẫn dài: gói effect CapCut dễ vượt MAX_PATH 260 của Windows
            if src.is_dir():
                shutil.copytree(assetlib.lp(src), assetlib.lp(dest))
            else:
                shutil.copy2(assetlib.lp(src), assetlib.lp(dest))
            n_ok += 1
            print(f"  + {r['kind']:14} {str(r['name'])[:44]}")
        except OSError as e:
            print(f"  ! lỗi copy {r['name']}: {e}")
    print(f"\nCài mới {n_ok}, đã có sẵn {n_skip}, thiếu gói trong kho {n_nolib}")
    return n_ok


def fix_draft(name: str):
    """Rewrite path tài nguyên trong draft cho khớp máy hiện tại (LOCALAPPDATA khác nhau)."""
    d = Path(name) if Path(name).exists() else DRAFT_ROOT / name
    f = d / "draft_content.json"
    if not f.exists():
        sys.exit(f"Không thấy {f}")
    if (d / ".locked").exists():
        sys.exit("Draft đang mở trong CapCut — đóng lại rồi chạy tiếp.")
    data = json.loads(f.read_text(encoding="utf-8"))
    n = 0
    for bucket, items in (data.get("materials") or {}).items():
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            p = it.get("path") or ""
            rel = cache_rel(p)
            if not rel:
                continue
            new = str(CACHE_ROOT / rel).replace("\\", "/")
            if new != p:
                it["path"] = new
                n += 1
    if n:
        shutil.copy2(f, f.with_suffix(".json.prefix.bak"))
        f.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Đã sửa {n} đường dẫn trong {d.name}")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--fix-draft", metavar="DRAFT")
    a = ap.parse_args()
    if a.check:
        check()
    elif a.restore:
        restore(a.dry)
    elif a.fix_draft:
        fix_draft(a.fix_draft)
    else:
        ap.error("cần --check / --restore / --fix-draft")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
