# -*- coding: utf-8 -*-
"""Bóc TOÀN BỘ 1 cụm caption-template của 0720 để hiểu text nằm ở đâu & có thay tự động được không."""
import json, os
base = r"C:\Users\Acer\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft"
c = json.load(open(os.path.join(base, "0720", "draft_content.json"), encoding="utf-8"))

def mat(mid):
    for arr_name, arr in c["materials"].items():
        if isinstance(arr, list):
            for m in arr:
                if isinstance(m, dict) and m.get("id") == mid:
                    return arr_name, m
    return None, None

def dump(o, indent=0, maxv=160):
    pad = "  " * indent
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)) and v:
                print(f"{pad}{k}:")
                dump(v, indent + 1, maxv)
            else:
                s = json.dumps(v, ensure_ascii=False)
                print(f"{pad}{k}: {s[:maxv]}")
    elif isinstance(o, list):
        print(f"{pad}[{len(o)} phần tử] vd:")
        if o:
            dump(o[0], indent + 1, maxv)

ttrack = next(t for t in c["tracks"] if t["type"] == "text")
seg = ttrack["segments"][0]
print("="*70)
print("TEXT SEGMENT[0]  material_id=%s  target=%s" % (seg["material_id"][:8], seg["target_timerange"]))
print("  caption_info:", json.dumps(seg.get("caption_info"), ensure_ascii=False)[:300])
an, subtpl = mat(seg["material_id"])
print("\n" + "="*70)
print("SUBTITLE TEMPLATE material (type=%s, mảng=%s):" % (subtpl.get("type"), an))
# in các key quan trọng
for k in ["id","name","effect_id","resource_id","type","text_info","subtitle_infos","texts",
          "text_infos","formula_id","combination_id","title_infos","group_id"]:
    if k in subtpl:
        print("  %s: %s" % (k, json.dumps(subtpl[k], ensure_ascii=False)[:400]))
print("\n  >>> TẤT CẢ key của subtitle template:")
print("     ", sorted(subtpl.keys()))
# tìm field nào chứa text hiển thị
print("\n  >>> Field nào chứa chuỗi text?")
def scan(o, path=""):
    if isinstance(o, dict):
        for k,v in o.items(): scan(v, path+"/"+k)
    elif isinstance(o, list):
        for i,v in enumerate(o): scan(v, path+f"[{i}]")
    elif isinstance(o, str) and len(o)>3 and any(ch.isalpha() for ch in o) and " " in o:
        if not o.startswith(("C:/","E:/","http","{\"")):
            print(f"     {path} = {o[:80]}")
scan(subtpl)

# subtitle template có tham chiếu text material không?
print("\n  >>> id nào trong subtitle template khớp material 'text'?")
text_ids = {m["id"] for m in c["materials"].get("texts", [])}
def scan_ids(o, path=""):
    if isinstance(o, dict):
        for k,v in o.items(): scan_ids(v, path+"/"+k)
    elif isinstance(o, list):
        for i,v in enumerate(o): scan_ids(v, path+f"[{i}]")
    elif isinstance(o, str) and o in text_ids:
        print(f"     {path} -> TEXT material {o[:8]}")
scan_ids(subtpl)
scan_ids(seg, "segment")
