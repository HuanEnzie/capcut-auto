# -*- coding: utf-8 -*-
"""Read-only: bóc tách cấu trúc transition / caption / audio để thiết kế pipeline."""
import json, sys, os
base = r"C:\Users\Acer\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft"

def load(name):
    return json.load(open(os.path.join(base, name, "draft_content.json"), encoding="utf-8"))

def short(obj, n=600):
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + " …"

# ---- TRANSITIONS (từ 282new) ----
c = load("282new")
trans = c["materials"].get("transitions", [])
print("### 282new transitions:", len(trans))
if trans:
    print("  material ví dụ:", short(trans[0]))
# tìm segment nào tham chiếu transition này
tids = {t["id"] for t in trans}
for tr in c["tracks"]:
    if tr["type"] != "video":
        continue
    print(f"\n  video track: {len(tr['segments'])} segments")
    for i, seg in enumerate(tr["segments"][:4]):
        refs = seg.get("extra_material_refs", [])
        has_tr = [r for r in refs if r in tids]
        print(f"   seg[{i}] target={seg['target_timerange']} #refs={len(refs)} transition_ref={has_tr}")
    break

# ---- CAPTION + AUDIO (từ 0720) ----
c = load("0720")
print("\n### 0720 tracks:")
for tr in c["tracks"]:
    print(f"  - {tr['type']:<8} segments={len(tr['segments'])}")

texts = c["materials"].get("texts", [])
print("\n### 0720 text material [4] (một caption 'đầy đủ'):")
m = texts[4]
print("  keys:", sorted(m.keys())[:40])
print("  content:", short(m.get("content"), 400))
print("  words:", short(m.get("words"), 500))
for k in ("font_size", "text_color", "alignment", "type"):
    print(f"  {k}:", m.get(k))

# text track segment tương ứng
for tr in c["tracks"]:
    if tr["type"] == "text":
        print("\n### text-track segments (5 đầu):")
        for i, seg in enumerate(tr["segments"][:5]):
            print(f"   seg[{i}] mat={seg['material_id'][:8]} target={seg['target_timerange']} clip.transform={seg.get('clip',{}).get('transform')}")
        break

# audio
for tr in c["tracks"]:
    if tr["type"] == "audio":
        seg = tr["segments"][0]
        aid = seg["material_id"]
        amat = next((a for a in c["materials"].get("audios", []) if a["id"] == aid), None)
        print("\n### audio seg[0]:", seg["target_timerange"], "| source:", seg.get("source_timerange"))
        print("   audio material:", short(amat, 400))
        break
