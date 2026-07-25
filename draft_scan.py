# -*- coding: utf-8 -*-
"""draft_scan.py — Đọc draft CapCut, bóc TOÀN BỘ tài nguyên (sticker/hiệu ứng chữ/SFX/
stock/font/transition/animation) và nạp vào kho (assetlib).

  python draft_scan.py --list 0715                 # xem draft dùng gì
  python draft_scan.py --harvest 0715 --owner dan  # nạp vào kho người dùng
  python draft_scan.py --harvest-all --owner dan   # nạp tất cả draft của editor
"""
import argparse, json, sys
from pathlib import Path

import assetlib

DRAFT_ROOT = assetlib.draft_root()      # dò từ chính cấu hình CapCut trên máy đang chạy

# bucket trong materials -> kind trong kho
BUCKET_KIND = {
    "stickers": "sticker", "text_templates": "text_template", "audios": "audio",
    "videos": "video", "images": "image", "transitions": "transition",
    "video_effects": "effect", "effects": "effect", "material_animations": "animation",
    "fonts": "font",
}
# media nguồn của chính pipeline -> không phải "gu editor", bỏ qua khi harvest
SKIP_NAME_HINT = ("reframe_", "voice", "draft_cover")
# video chỉ harvest khi là STOCK (b-roll tải về), không ôm footage gốc của dự án
STOCK_HINT = ("broll", "stock", "pexels")


def draft_dir(name: str) -> Path:
    p = Path(name)
    return p if p.is_absolute() or p.exists() else DRAFT_ROOT / name


def scan(draft: str) -> list[dict]:
    """Trả list tài nguyên: {kind, resource_id, name, category, path, bucket, has_file}."""
    d = draft_dir(draft)
    f = d / "draft_content.json"
    if not f.exists():
        sys.exit(f"Không thấy {f}")
    data = json.loads(f.read_text(encoding="utf-8"))
    out = []
    for bucket, items in (data.get("materials") or {}).items():
        if not isinstance(items, list):
            continue
        kind = BUCKET_KIND.get(bucket)
        if not kind:
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            rid = it.get("resource_id") or it.get("effect_id") or it.get("sticker_id")
            name = it.get("name") or it.get("material_name") or it.get("text") or ""
            path = it.get("path") or it.get("font_path") or ""
            # loại material_animations không có id/tên thì bỏ (chỉ là tham chiếu rỗng)
            if not rid and not path and not name:
                continue
            p = Path(path) if path else None
            out.append({
                "bucket": bucket, "kind": kind,
                "resource_id": str(rid) if rid else None,
                "name": str(name)[:80], "category": it.get("category_name") or "",
                "path": str(p) if p else "", "has_file": bool(p and p.exists()),
                "type": it.get("type") or "",
            })
    # font nằm trong texts (không phải bucket riêng)
    for t in (data.get("materials") or {}).get("texts", []) or []:
        fp = t.get("font_path") or ""
        if fp:
            p = Path(fp)
            out.append({"bucket": "texts", "kind": "font",
                        "resource_id": str(t.get("font_resource_id") or "") or None,
                        "name": t.get("font_name") or p.stem, "category": "font",
                        "path": str(p), "has_file": p.exists(), "type": "font"})
    return out


def harvest(draft: str, owner: str, origin="user", with_video=False) -> dict:
    """Nạp tài nguyên của draft vào kho. Trả thống kê new/dup/skip."""
    res = scan(draft)
    st = {"new": 0, "dup": 0, "skip": 0}
    for r in res:
        nm = (r["name"] or "") + " " + (r["path"] or "")
        if any(h in nm for h in SKIP_NAME_HINT):
            st["skip"] += 1
            continue
        if not r["resource_id"] and not r["has_file"]:
            st["skip"] += 1
            continue
        # footage gốc của dự án không phải tài nguyên tái dùng -> bỏ
        if r["kind"] == "video" and not with_video and not any(h in nm.lower() for h in STOCK_HINT):
            st["skip"] += 1
            continue
        _, status = assetlib.add(
            r["kind"], name=r["name"], category=r["category"],
            src_path=r["path"] if r["has_file"] else None,
            resource_id=r["resource_id"], origin=origin, owner=owner,
            draft=Path(draft).name)
        st[status] += 1
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", metavar="DRAFT")
    ap.add_argument("--harvest", metavar="DRAFT")
    ap.add_argument("--harvest-all", action="store_true")
    ap.add_argument("--owner", default="shared")
    ap.add_argument("--origin", default="user", choices=["user", "default"])
    ap.add_argument("--with-video", action="store_true", help="ôm cả footage gốc (mặc định bỏ)")
    a = ap.parse_args()

    if a.list:
        res = scan(a.list)
        print(f"{'kind':15}{'resource_id':22}{'file':6} name")
        for r in sorted(res, key=lambda x: x["kind"]):
            print(f"{r['kind']:15}{str(r['resource_id'] or '-'):22}"
                  f"{'có' if r['has_file'] else '-':6} {r['name']}  [{r['category']}]")
        print(f"\nTổng {len(res)} tài nguyên, {sum(1 for r in res if r['has_file'])} có file local")
        return

    targets = []
    if a.harvest:
        targets = [a.harvest]
    elif a.harvest_all:
        targets = [p.name for p in DRAFT_ROOT.iterdir()
                   if p.is_dir() and (p / "draft_content.json").exists()]
    else:
        ap.error("cần --list / --harvest / --harvest-all")

    tot = {"new": 0, "dup": 0, "skip": 0}
    for t in targets:
        st = harvest(t, a.owner, a.origin, a.with_video)
        for k in tot:
            tot[k] += st[k]
        print(f"  {t:22} mới={st['new']:3}  trùng(bỏ qua)={st['dup']:3}  skip={st['skip']:3}")
    print(f"\nTổng: {tot['new']} mới, {tot['dup']} trùng đã chống duplicate, {tot['skip']} bỏ qua")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
