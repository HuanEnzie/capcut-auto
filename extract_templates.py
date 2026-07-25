# -*- coding: utf-8 -*-
"""Trích các mảnh template thật từ draft hiện có -> templates.json (để builder ghép lại).
Chạy 1 lần. Read-only với draft nguồn."""
import json, os

base = r"C:\Users\Acer\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft"
OUT = os.path.join(os.path.dirname(__file__), "templates.json")

def load(name):
    return json.load(open(os.path.join(base, name, "draft_content.json"), encoding="utf-8"))

def mat_by_id(content, mid):
    for arr in content["materials"].values():
        if isinstance(arr, list):
            for m in arr:
                if isinstance(m, dict) and m.get("id") == mid:
                    return m
    return None

tpl = {}

# ---------- Từ 282new: skeleton + video segment (+helpers) + transition ----------
c = load("282new")

# skeleton: mọi field top-level, nhưng rỗng tracks + materials rỗng từng mảng
skel = {}
for k, v in c.items():
    if k == "tracks":
        skel[k] = []
    elif k == "materials":
        skel[k] = {mk: ([] if isinstance(mv, list) else mv) for mk, mv in v.items()}
    elif k == "keyframes":
        skel[k] = {kk: ([] if isinstance(kv, list) else kv) for kk, kv in v.items()}
    else:
        skel[k] = v
tpl["skeleton"] = skel

vtrack = next(t for t in c["tracks"] if t["type"] == "video")
tpl["video_track_shell"] = {k: (v if k != "segments" else []) for k, v in vtrack.items()}

seg0 = vtrack["segments"][0]      # segment không transition
seg_tr = vtrack["segments"][1]    # segment có transition
tpl["video_segment"] = seg0
# gom toàn bộ material mà seg0 tham chiếu (primary + extra refs), theo type
refs = [seg0["material_id"]] + list(seg0.get("extra_material_refs", []))
helpers = {}
for rid in refs:
    m = mat_by_id(c, rid)
    if m:
        helpers.setdefault(m.get("type", "unknown"), []).append(m)
tpl["video_segment_materials"] = helpers  # {type: [material,...]}

# transition material (Slide Zoom) + cho biết ref nằm ở đâu trong extra_material_refs
trans = c["materials"]["transitions"][0]
tpl["transition_material"] = trans
tpl["segment_with_transition_refs"] = seg_tr.get("extra_material_refs", [])

# ---------- Từ 0720: text material + text segment + audio ----------
c2 = load("0720")
ttrack = next(t for t in c2["tracks"] if t["type"] == "text")
tpl["text_track_shell"] = {k: (v if k != "segments" else []) for k, v in ttrack.items()}
tseg = ttrack["segments"][0]
tpl["text_segment"] = tseg
tpl["text_material"] = mat_by_id(c2, tseg["material_id"])

atrack = next(t for t in c2["tracks"] if t["type"] == "audio")
tpl["audio_track_shell"] = {k: (v if k != "segments" else []) for k, v in atrack.items()}
aseg = atrack["segments"][0]
tpl["audio_segment"] = aseg
tpl["audio_material"] = mat_by_id(c2, aseg["material_id"])

json.dump(tpl, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
# In tóm tắt
print("Đã lưu templates.json")
print(" video_segment extra_refs:", len(seg0.get("extra_material_refs", [])), "helper types:", list(helpers.keys()))
print(" transition:", trans.get("name"), trans.get("resource_id"))
print(" text_material fields:", len(tpl["text_material"]))
print(" audio type:", tpl["audio_material"].get("type"))
print(" skeleton canvas:", skel.get("canvas_config"))
print(" text_segment clip:", tseg.get("clip", {}).get("transform"))
