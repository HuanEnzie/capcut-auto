# -*- coding: utf-8 -*-
"""Bóc rõ cụm caption của 0720: segment <-> text_template_subtitle <-> text material."""
import json, os
base = r"C:\Users\Acer\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft"
c = json.load(open(os.path.join(base, "0720", "draft_content.json"), encoding="utf-8"))

def mat_by_id(mid):
    for arr in c["materials"].values():
        if isinstance(arr, list):
            for m in arr:
                if isinstance(m, dict) and m.get("id") == mid:
                    return m
    return None

def short(o, n=500):
    s = json.dumps(o, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + " …"

ttrack = next(t for t in c["tracks"] if t["type"] == "text")
seg = ttrack["segments"][0]
print("### TEXT SEGMENT[0] full:")
print(short(seg, 1200))
print()
print("material_id ->", seg["material_id"][:8])
prim = mat_by_id(seg["material_id"])
print("PRIMARY material type =", prim.get("type"))
print("  primary full:", short(prim, 900))
print()
print("### extra_material_refs -> loại material:")
for rid in seg.get("extra_material_refs", []):
    m = mat_by_id(rid)
    print(f"  {rid[:8]} -> type={m.get('type') if m else 'NOT FOUND'}",
          "| có content?" , (m and 'content' in m), "| có words?", (m and 'words' in m))

# Tìm material 'text' thật (có content) liên kết với caption đầu tiên
print()
print("### Các material type='text' (2 cái đầu) — content+words:")
n=0
for m in c["materials"].get("texts", []):
    if m.get("type")=="text" and 'content' in m:
        print(f"  id={m['id'][:8]} content={short(m.get('content'),150)}")
        n+=1
        if n>=2: break

# đếm loại material trong texts[]
from collections import Counter
print()
print("### Phân loại materials.texts:", Counter(m.get('type') for m in c['materials'].get('texts',[])))
# text_template_subtitle count
print("### materials keys có 'subtitle'/'template':", [k for k in c['materials'] if 'sub' in k.lower() or 'templ' in k.lower()])
