# -*- coding: utf-8 -*-
"""draft_diff.py — So sánh draft TA SINH RA với draft SAU KHI EDITOR SỬA.

Luồng:
  1. Lúc export xong  -> snapshot(draft)  : chụp lại "vân tay" tài nguyên
  2. Editor mở CapCut sửa, lưu lại
  3. sync(draft, owner) -> diff + nạp cái editor THÊM vào kho, đánh dấu cái bị GỠ

  python draft_diff.py --snapshot 1107_short04_v7
  python draft_diff.py --diff     1107_short04_v7
  python draft_diff.py --sync     1107_short04_v7 --owner dan
"""
import argparse, json, sys, time
from pathlib import Path

import assetlib, draft_scan

SNAP_DIR = assetlib.ROOT / "snapshots"


def _key(r: dict) -> str:
    """Khoá nhận dạng 1 tài nguyên trong draft."""
    return f"{r['kind']}|{r.get('resource_id') or ''}|{Path(r.get('path') or '').name or r.get('name','')}"


def snapshot(draft: str) -> Path:
    res = draft_scan.scan(draft)
    SNAP_DIR.mkdir(exist_ok=True)
    p = SNAP_DIR / f"{Path(draft).name}.json"
    p.write_text(json.dumps({"draft": Path(draft).name, "ts": time.time(),
                             "items": {_key(r): r for r in res}},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã chụp {len(res)} tài nguyên -> {p.name}")
    return p


def diff(draft: str) -> dict:
    p = SNAP_DIR / f"{Path(draft).name}.json"
    if not p.exists():
        sys.exit(f"Chưa có snapshot cho '{draft}' — chạy --snapshot ngay sau khi export.")
    before = json.loads(p.read_text(encoding="utf-8"))["items"]
    after = {_key(r): r for r in draft_scan.scan(draft)}
    added = [v for k, v in after.items() if k not in before]
    removed = [v for k, v in before.items() if k not in after]
    kept = [v for k, v in after.items() if k in before]
    return {"added": added, "removed": removed, "kept": kept}


def sync(draft: str, owner: str) -> dict:
    """Nạp tài nguyên editor THÊM vào kho; ghi nhận cái bị GỠ (tín hiệu âm)."""
    d = diff(draft)
    n_new = 0
    for r in d["added"]:
        nm = (r["name"] or "") + " " + (r["path"] or "")
        if any(h in nm for h in draft_scan.SKIP_NAME_HINT):
            continue
        if r["kind"] == "video" and not any(h in nm.lower() for h in draft_scan.STOCK_HINT):
            continue
        if not r["resource_id"] and not r["has_file"]:
            continue
        _, st = assetlib.add(r["kind"], name=r["name"], category=r["category"],
                             src_path=r["path"] if r["has_file"] else None,
                             resource_id=r["resource_id"], origin="user",
                             owner=owner, draft=Path(draft).name)
        n_new += (st == "new")
    for r in d["removed"]:
        assetlib.mark_dropped(resource_id=r.get("resource_id"), draft=Path(draft).name)
    # giữ nguyên cái editor GIỮ LẠI -> tín hiệu dương
    for r in d["kept"]:
        if r.get("resource_id"):
            assetlib.add(r["kind"], name=r["name"], category=r["category"],
                         src_path=r["path"] if r["has_file"] else None,
                         resource_id=r["resource_id"], origin="user", owner=owner,
                         draft=Path(draft).name)
    snapshot(draft)     # cập nhật mốc cho lần sau
    return {"added": len(d["added"]), "new_in_lib": n_new,
            "removed": len(d["removed"]), "kept": len(d["kept"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", metavar="DRAFT")
    ap.add_argument("--diff", metavar="DRAFT")
    ap.add_argument("--sync", metavar="DRAFT")
    ap.add_argument("--owner", default="shared")
    a = ap.parse_args()
    if a.snapshot:
        snapshot(a.snapshot)
    elif a.diff:
        d = diff(a.diff)
        for tag, items in (("THÊM", d["added"]), ("GỠ BỎ", d["removed"])):
            print(f"\n=== {tag} ({len(items)}) ===")
            for r in items:
                print(f"  {r['kind']:14} {str(r['name'])[:44]:46} rid={r.get('resource_id')}")
        print(f"\nGiữ nguyên: {len(d['kept'])}")
    elif a.sync:
        r = sync(a.sync, a.owner)
        print(f"Editor thêm {r['added']} ({r['new_in_lib']} mới vào kho), "
              f"gỡ {r['removed']}, giữ {r['kept']}")
    else:
        ap.error("cần --snapshot / --diff / --sync")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
