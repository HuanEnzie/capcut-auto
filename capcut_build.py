# -*- coding: utf-8 -*-
"""
capcut_build.py — Dựng 1 CapCut draft từ 1 folder (clip nhỏ + voice).

Pipeline: clip -> video track (khớp độ dài voice) + Slide Zoom transition giữa các clip
          voice -> audio track
          voice -> faster-whisper (vi) -> caption text track (giống 0720: trắng, giữa, đáy)

Lấy cấu trúc JSON chuẩn 9.0.0 từ 2 draft "donor" có sẵn:
  - 282new : video segment + helper materials + transition "Slide Zoom"
  - 0720   : text material trắng (kiểu caption) + audio material

CÁCH DÙNG:
  python capcut_build.py "E:\\E Download\\DrStone" --name "DrStone_AUTO" --yes
  python capcut_build.py "<folder>" --name "<draft>" --model small --yes
"""
import argparse, copy, csv, difflib, json, os, re, subprocess, sys, uuid
from pathlib import Path

import assetlib

DRAFTS_ROOT = assetlib.draft_root()     # dò CapCut (env CAPCUT_DRAFTS_ROOT vẫn đè được)
DONOR_VIDEO = "282new"   # nguồn video-segment + transition
DONOR_TEXT = "0720"      # nguồn text material + audio
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_DUMP = dict(ensure_ascii=False, separators=(",", ":"))

def uid():
    return str(uuid.uuid4()).upper()

# Draft MẪU (donor) mà builder clone cấu trúc ra. Trước đây chỉ đọc từ thư mục
# CapCut của máy dev -> máy khác build chạy hết 10 phút rồi mới chết ở dòng cuối
# vì không có '282new'. Giờ đóng gói kèm app trong assets/donor/.
DONOR_DIR = assetlib.ROOT / "assets" / "donor"


def _duong_dan_mau(name: str) -> Path:
    for p in (DONOR_DIR / name, DRAFTS_ROOT / name):
        if (p / "draft_content.json").is_file():
            return p
    raise FileNotFoundError(
        f"Không thấy draft mẫu '{name}'. Nó phải nằm trong assets/donor/{name}/ "
        f"(đi kèm app) hoặc trong thư mục draft của CapCut.")


def _doi_cache_ve_may_nay(s: str) -> str:
    """Draft mẫu giữ đường dẫn cache CapCut của MÁY LÀM RA NÓ. Chép sang máy khác
    là trỏ vào thư mục không tồn tại -> CapCut đòi chọn lại file. Đổi phần gốc
    sang cache của máy đang chạy; gói nào thiếu thì asset_restore --restore cài."""
    moi = str(assetlib.cache_root()).replace("\\", "/")
    s = re.sub(r"[A-Za-z]:/[^\"]*?/User Data/Cache/", moi + "/", s)
    s = re.sub(r"[A-Za-z]:\\\\\\\\[^\"]*?\\\\\\\\User Data\\\\\\\\Cache\\\\\\\\",
               moi.replace("/", "\\\\\\\\") + "\\\\\\\\", s)
    return s


def kiem_tra_draft_mau(*names) -> None:
    """Gọi NGAY ĐẦU build. Thiếu draft mẫu thì báo luôn, đừng để chạy xong
    transcribe + Gemini + render rồi mới chết."""
    for n in names:
        _duong_dan_mau(n)


def load_draft(name):
    p = _duong_dan_mau(name) / "draft_content.json"
    return json.loads(_doi_cache_ve_may_nay(p.read_text(encoding="utf-8", errors="replace")))

def find_mat(content, mid):
    """Trả về (tên_mảng, material) chứa id này trong donor."""
    for arr_name, arr in content["materials"].items():
        if isinstance(arr, list):
            for m in arr:
                if isinstance(m, dict) and m.get("id") == mid:
                    return arr_name, m
    return None, None

# ---------------------------------------------------------------- ffprobe
def probe(path):
    """Trả về dict(duration_us, width, height, has_audio)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, encoding="utf-8").stdout
    j = json.loads(out)
    dur = float(j.get("format", {}).get("duration", 0))
    w = h = 0
    has_audio = False
    for s in j.get("streams", []):
        if s.get("codec_type") == "video" and not w:
            w, h = s.get("width", 0), s.get("height", 0)
        if s.get("codec_type") == "audio":
            has_audio = True
    return dict(duration_us=int(dur * 1_000_000), width=w, height=h, has_audio=has_audio)

# ---------------------------------------------------------------- whisper
_MODEL_CACHE = {}

def get_model(model_name):
    """Nạp WhisperModel 1 lần rồi cache (dùng lại cho cả 100 folder)."""
    if model_name not in _MODEL_CACHE:
        from faster_whisper import WhisperModel
        print(f"  [caption] nạp model '{model_name}' (lần đầu có thể lâu)...")
        _MODEL_CACHE[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _MODEL_CACHE[model_name]

def transcribe(voice_path, model_name="small"):
    """Trả về list caption: [{text, start_ms, end_ms, words:[{w,s,e}]}]. [] nếu lỗi."""
    try:
        model = get_model(model_name)
    except Exception as e:
        print("  [caption] faster-whisper không nạp được:", e)
        return []
    try:
        segments, info = model.transcribe(
            str(voice_path), language="vi", word_timestamps=True,
            vad_filter=True)
        caps = []
        for seg in segments:
            words = [{"w": w.word, "s": int(w.start * 1000), "e": int(w.end * 1000)}
                     for w in (seg.words or [])]
            caps.append({"text": seg.text.strip(),
                         "start_ms": int(seg.start * 1000),
                         "end_ms": int(seg.end * 1000),
                         "words": words})
        print(f"  [caption] {len(caps)} dòng, ngôn ngữ={info.language} ({info.language_probability:.2f})")
        return caps
    except Exception as e:
        print("  [caption] LỖI khi transcribe:", e)
        return []

# ---------------------------------------------------------------- text material trắng
def pick_white_text_material(donor):
    """Chọn 1 material type='text' màu trắng (#ffffffff) làm khuôn style caption."""
    best = None
    for m in donor["materials"].get("texts", []):
        if m.get("type") != "text":
            continue
        if m.get("text_color") == "#ffffffff":
            return m
        best = best or m
    return best

def _norm(w):
    return re.sub(r"[^\w]", "", w.lower())

def align_script(wwords, script_text):
    """Căn chữ KỊCH BẢN (đúng chính tả) lên timing từ Whisper.
    Trả về list [{w,s,e}] dùng chữ kịch bản + thời gian của giọng đọc."""
    sw = script_text.split()
    if not sw or not wwords:
        return wwords
    a = [_norm(x["w"]) for x in wwords]
    b = [_norm(x) for x in sw]
    times = [None] * len(sw)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                times[j1 + k] = (wwords[i1 + k]["s"], wwords[i1 + k]["e"])
        else:
            # nội suy timing cho các chữ kịch bản trong khoảng i1..i2
            s = wwords[i1]["s"] if i1 < len(wwords) else (wwords[-1]["e"] if wwords else 0)
            e = wwords[i2 - 1]["e"] if i2 > i1 and i2 - 1 < len(wwords) else s
            n = max(1, j2 - j1)
            for idx, k in enumerate(range(j1, j2)):
                times[k] = (int(s + (e - s) * idx / n), int(s + (e - s) * (idx + 1) / n))
    # điền chỗ trống bằng hàng xóm
    for k in range(len(times)):
        if times[k] is None:
            prev = times[k - 1][1] if k > 0 and times[k - 1] else 0
            times[k] = (prev, prev)
    # thêm dấu cách đầu mỗi chữ (giống Whisper) để khi ghép lại có khoảng trắng đúng
    return [{"w": " " + sw[k], "s": times[k][0], "e": times[k][1]} for k in range(len(sw))]

def rechunk(caps, max_chars=18, max_words=5, max_gap_ms=450):
    """Gộp toàn bộ word-timestamp rồi cắt lại thành cụm NGẮN, không chồng thời gian.
    Cắt khi: vượt số ký tự/số chữ, gặp khoảng lặng, hoặc sau dấu câu."""
    words = []
    for c in caps:
        for w in c["words"]:
            if w["w"].strip():
                words.append(w)
    if not words:
        return caps  # không có word-level -> giữ nguyên
    out, cur = [], []

    def cur_text():
        return "".join(x["w"] for x in cur).strip()

    def flush():
        t = cur_text()
        if t:
            out.append({"text": t, "start_ms": cur[0]["s"],
                        "end_ms": cur[-1]["e"], "words": list(cur)})

    for w in words:
        if cur:
            gap = w["s"] - cur[-1]["e"]
            would = len((cur_text() + " " + w["w"]).strip())
            after_punct = cur_text().endswith((".", "!", "?", ",", ";", ":"))
            if would > max_chars or len(cur) >= max_words or gap > max_gap_ms or after_punct:
                flush(); cur = []
        cur.append(w)
    flush()
    # chống chồng lấn: mỗi cụm hiện tới sát cụm sau (linger tối đa 0.5s), không chồng, không nhấp nháy
    for i in range(len(out) - 1):
        nxt = out[i + 1]["start_ms"]
        out[i]["end_ms"] = min(nxt, max(out[i]["end_ms"], out[i]["start_ms"]) + 500)
        if out[i]["end_ms"] < out[i]["start_ms"] + 120:
            out[i]["end_ms"] = min(nxt, out[i]["start_ms"] + 120)
    return out

def make_caption_content(text):
    return json.dumps({"text": text,
                       "styles": [{"size": 12,
                                   "fill": {"content": {"render_type": "solid",
                                                        "solid": {"color": [1, 1, 1]}}},
                                   "range": [0, len(text)]}]}, **_DUMP)

def make_words(cap):
    st, en, tx = [], [], []
    base = cap["start_ms"]
    for w in cap["words"]:
        st.append(max(0, w["s"] - base)); en.append(max(0, w["e"] - base)); tx.append(w["w"])
    if not tx:  # không có word-level -> 1 cụm
        st, en, tx = [0], [cap["end_ms"] - cap["start_ms"]], [cap["text"]]
    return {"start_time": st, "end_time": en, "text": tx}

# ---------------------------------------------------------------- caption TEMPLATE (giống 0720)
def set_content_text(content_json, new_text):
    """Giữ style, chỉ thay .text + range trong chuỗi content (JSON lồng)."""
    try:
        inner = json.loads(content_json)
    except Exception:
        inner = {"text": new_text, "styles": [{"range": [0, len(new_text)]}]}
    inner["text"] = new_text
    for st in inner.get("styles", []):
        st["range"] = [0, len(new_text)]
    return json.dumps(inner, **_DUMP)

def make_word_info(cap):
    base = cap["start_ms"]
    words = [{"text": w["w"], "start_time": max(0, w["s"] - base),
              "end_time": max(0, w["e"] - base)} for w in cap["words"]]
    if not words:
        words = [{"text": cap["text"], "start_time": 0,
                  "end_time": cap["end_ms"] - cap["start_ms"]}]
    return {"text": cap["text"], "start_time": cap["start_ms"],
            "end_time": cap["end_ms"], "words": words, "keyword_ranges": []}

def _walk_replace(obj, id_map):
    """Đệ quy thay mọi chuỗi id có trong id_map (giữ liên kết khi clone)."""
    if isinstance(obj, dict):
        return {k: _walk_replace(v, id_map) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_replace(v, id_map) for v in obj]
    if isinstance(obj, str) and obj in id_map:
        return id_map[obj]
    return obj

def extract_caption_unit(donor):
    """Lấy 1 cụm caption-template thật từ donor (segment + subtitle tpl + text mats + anim)."""
    ttrack = next(t for t in donor["tracks"] if t["type"] == "text")
    seg = None
    for s in ttrack["segments"]:
        _, m = find_mat(donor, s["material_id"])
        if m and m.get("type") == "text_template_subtitle":
            seg = s; sub = m; break
    if seg is None:
        return None
    subarr, _ = find_mat(donor, seg["material_id"])
    # gom toàn bộ material thuộc cụm + mảng của chúng
    bundle = {}   # id -> (array, obj)
    bundle[sub["id"]] = (subarr, sub)
    for tir in sub.get("text_info_resources", []):
        a, m = find_mat(donor, tir.get("text_material_id"))
        if m:
            bundle[m["id"]] = (a, m)
        for r in tir.get("extra_material_refs", []):
            a2, m2 = find_mat(donor, r)
            if m2:
                bundle[m2["id"]] = (a2, m2)
    for r in seg.get("extra_material_refs", []):
        a, m = find_mat(donor, r)
        if m:
            bundle[m["id"]] = (a, m)
    return {"seg": seg, "sub_id": sub["id"], "subarr": subarr, "bundle": bundle}

def gen_template_caption(unit, cap):
    """Trả về (segment, [(array,material),...]) cho 1 caption dùng template."""
    # remap mọi id trong cụm (sub, text mats, anim, segment, text_info_resources.id)
    id_map = {}
    for oid in unit["bundle"]:
        id_map[oid] = uid()
    id_map[unit["seg"]["id"]] = uid()
    for tir in unit["bundle"][unit["sub_id"]][1].get("text_info_resources", []):
        if tir.get("id"):
            id_map[tir["id"]] = uid()

    seg = _walk_replace(copy.deepcopy(unit["seg"]), id_map)
    mats = []
    for oid, (arr, obj) in unit["bundle"].items():
        mats.append((arr, _walk_replace(copy.deepcopy(obj), id_map)))

    text = cap["text"]
    dur_us = max(120000, (cap["end_ms"] - cap["start_ms"]) * 1000)
    wi = make_word_info(cap)
    words_arr = make_words(cap)

    # sửa subtitle template + các text material
    for arr, m in mats:
        if m.get("type") == "text_template_subtitle":
            m["origin_word_info"] = copy.deepcopy(wi)
            m["current_word_info"] = copy.deepcopy(wi)
            merge = ""; ranges = []; off = 0
            for tir in m.get("text_info_resources", []):
                tir.setdefault("attach_info", {})
                tir["attach_info"]["duration"] = dur_us
                tir["attach_info"]["start_time"] = 0
                tir["word_index"] = [0, len(wi["words"])]
                merge += text
                blen = len(text.encode("utf-8"))
                ranges.append({"location": off, "length": blen, "source_type": "unknown"})
                off += blen
            m["merge_content"] = merge
            m["material_text_ranges"] = ranges
        elif m.get("type") == "text":
            m["content"] = set_content_text(m.get("content", ""), text)
            m["words"] = copy.deepcopy(words_arr)

    seg["target_timerange"] = {"start": cap["start_ms"] * 1000, "duration": dur_us}
    seg["source_timerange"] = None
    return seg, mats

# ---------------------------------------------------------------- BUILD
def build(folder, out_name, model_name, do_write, caption_mode="template",
          cap_chars=18, cap_words=5, script_path=None, mute_clips=True):
    folder = Path(folder)
    clips = sorted([p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXTS],
                   key=lambda p: p.name)
    voices = [p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXTS]
    if not clips:
        raise RuntimeError(f"Không có clip video trong {folder}")
    if not voices:
        raise RuntimeError(f"Không có file voice trong {folder}")
    voice = voices[0]
    print(f"Folder : {folder}")
    print(f"Clips  : {len(clips)} -> {[c.name for c in clips]}")
    print(f"Voice  : {voice.name}")

    vinfo = probe(voice)
    V = vinfo["duration_us"]
    N = len(clips)
    print(f"Voice dài {V/1e6:.2f}s -> mỗi clip ~{V/N/1e6:.2f}s")

    # ---- donors ----
    dv = load_draft(DONOR_VIDEO)
    dt = load_draft(DONOR_TEXT)
    vtrack_src = next(t for t in dv["tracks"] if t["type"] == "video")
    seg_tpl = vtrack_src["segments"][0]
    # bản đồ id->(array,material) cho segment mẫu
    ref_units = []  # [(array, material_obj)] theo đúng thứ tự extra_material_refs
    prim_arr, prim_mat = find_mat(dv, seg_tpl["material_id"])
    for rid in seg_tpl["extra_material_refs"]:
        a, m = find_mat(dv, rid)
        ref_units.append((a, m))
    trans_tpl = dv["materials"]["transitions"][0]
    text_tpl = pick_white_text_material(dt)
    ttrack_src = next(t for t in dt["tracks"] if t["type"] == "text")
    tseg_tpl = ttrack_src["segments"][0]
    atrack_src = next(t for t in dt["tracks"] if t["type"] == "audio")
    aseg_tpl = atrack_src["segments"][0]
    _, amat_tpl = find_mat(dt, aseg_tpl["material_id"])

    # ---- skeleton ----
    c = copy.deepcopy(dv)
    c["tracks"] = []
    for k in list(c["materials"].keys()):
        if isinstance(c["materials"][k], list):
            c["materials"][k] = []
    for k in list(c.get("keyframes", {}).keys()):
        if isinstance(c["keyframes"][k], list):
            c["keyframes"][k] = []
    c["id"] = uid()
    c["name"] = out_name
    c["duration"] = V

    def add_mat(arr, obj):
        c["materials"].setdefault(arr, []).append(obj)

    # ---- VIDEO TRACK ----
    vtrack = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in vtrack_src.items()}
    vtrack["id"] = uid()
    start = 0
    for i, clip in enumerate(clips):
        ci = probe(clip)
        slice_us = (V - start) if i == N - 1 else V // N
        seg = copy.deepcopy(seg_tpl)
        seg["id"] = uid()
        # primary video material
        vm = copy.deepcopy(prim_mat)
        vm["id"] = uid()
        vm["path"] = str(clip).replace("\\", "/")
        vm["material_name"] = clip.stem
        vm["duration"] = ci["duration_us"]
        if ci["width"]:
            vm["width"], vm["height"] = ci["width"], ci["height"]
        vm["has_audio"] = ci["has_audio"]
        add_mat(prim_arr, vm)
        seg["material_id"] = vm["id"]
        # helper materials (clone theo thứ tự) + chèn transition ở index 2 nếu i>0
        newrefs = []
        for idx, (arr, m) in enumerate(ref_units):
            if m is None:
                continue
            nm = copy.deepcopy(m)
            nm["id"] = uid()
            # speed material: set theo tốc độ khớp
            if arr == "speeds":
                pass  # set dưới sau khi tính speed
            add_mat(arr, nm)
            newrefs.append((arr, nm))
        # tính timing/speed
        native = ci["duration_us"]
        if native >= slice_us:
            src_dur = slice_us; speed = 1.0
        else:
            src_dur = native; speed = round(native / slice_us, 6) if slice_us else 1.0
        seg["source_timerange"] = {"start": 0, "duration": src_dur}
        seg["target_timerange"] = {"start": start, "duration": slice_us}
        seg["speed"] = speed
        if mute_clips:
            seg["volume"] = 0.0          # tắt tiếng gốc của clip, chỉ để voiceover
            seg["last_nonzero_volume"] = 0.0
        for arr, nm in newrefs:
            if arr == "speeds":
                nm["speed"] = speed
                if "curve_speed" in nm:
                    nm["curve_speed"] = None
        ref_ids = [nm["id"] for _, nm in newrefs]
        # transition giữa clip trước và clip này
        if i > 0:
            tr = copy.deepcopy(trans_tpl)
            tr["id"] = uid()
            add_mat("transitions", tr)
            ref_ids.insert(2, tr["id"])
        seg["extra_material_refs"] = ref_ids
        seg["render_index"] = i
        vtrack["segments"].append(seg)
        start += slice_us
    c["tracks"].append(vtrack)

    # ---- AUDIO TRACK ----
    atrack = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in atrack_src.items()}
    atrack["id"] = uid()
    am = copy.deepcopy(amat_tpl)
    am["id"] = uid()
    am["path"] = str(voice).replace("\\", "/")
    am["name"] = voice.name
    am["duration"] = V
    add_mat("audios", am)
    aseg = copy.deepcopy(aseg_tpl)
    aseg["id"] = uid()
    aseg["material_id"] = am["id"]
    aseg["extra_material_refs"] = []
    aseg["source_timerange"] = {"start": 0, "duration": V}
    aseg["target_timerange"] = {"start": 0, "duration": V}
    atrack["segments"].append(aseg)
    c["tracks"].append(atrack)

    # ---- CAPTION TRACK ----
    # kịch bản: --script hoặc tự tìm file .txt trong folder
    script_text = None
    sp = Path(script_path) if script_path else next(iter(folder.glob("*.txt")), None)
    if sp and Path(sp).exists():
        script_text = Path(sp).read_text(encoding="utf-8").strip()
        print(f"  [caption] dùng kịch bản: {Path(sp).name} ({len(script_text)} ký tự)")

    caps = transcribe(voice, model_name)
    if caps and script_text:
        wwords = [w for cp in caps for w in cp["words"] if w["w"].strip()]
        aligned = align_script(wwords, script_text)
        caps = [{"text": script_text, "start_ms": aligned[0]["s"] if aligned else 0,
                 "end_ms": aligned[-1]["e"] if aligned else 0, "words": aligned}]
        print(f"  [caption] căn kịch bản lên timing: {len(aligned)} chữ")
    if caps:
        n0 = len(caps)
        caps = rechunk(caps, cap_chars, cap_words)
        print(f"  [caption] cắt lại: {n0} câu -> {len(caps)} cụm ngắn (<= {cap_chars} ký tự)")
    unit = extract_caption_unit(dt) if caption_mode == "template" else None
    if caps and caption_mode == "template" and unit is None:
        print("  [caption] Donor không có caption-template -> chuyển sang text thường.")
        caption_mode = "plain"
    if caps:
        ttrack = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in ttrack_src.items()}
        ttrack["id"] = uid()
        for cap in caps:
            if caption_mode == "template":
                ts, mats = gen_template_caption(unit, cap)
                for arr, m in mats:
                    add_mat(arr, m)
                ttrack["segments"].append(ts)
            else:
                tm = copy.deepcopy(text_tpl)
                tm["id"] = uid()
                tm["content"] = make_caption_content(cap["text"])
                tm["words"] = make_words(cap)
                add_mat("texts", tm)
                ts = copy.deepcopy(tseg_tpl)
                ts["id"] = uid()
                ts["material_id"] = tm["id"]
                ts["extra_material_refs"] = []
                ts["template_id"] = ""
                ts["clip"] = {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0,
                              "transform": {"x": 0.0, "y": -0.56},
                              "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0}
                dur = max(120000, (cap["end_ms"] - cap["start_ms"]) * 1000)
                ts["source_timerange"] = None
                ts["target_timerange"] = {"start": cap["start_ms"] * 1000, "duration": dur}
                ttrack["segments"].append(ts)
        c["tracks"].append(ttrack)
        print(f"  [caption] chế độ = {caption_mode}")
    else:
        print("  [caption] Bỏ qua caption (không có kết quả).")

    # ---- WRITE ----
    print(f"\nTổng: {len(vtrack['segments'])} clip, {len(caps)} caption, "
          f"video dài {V/1e6:.2f}s")
    if not do_write:
        print("[DRY-RUN] Chưa ghi. Thêm --yes để tạo draft thật.")
        return
    out_dir = DRAFTS_ROOT / out_name
    if out_dir.exists():
        raise RuntimeError(f"Draft đã tồn tại: {out_dir}")
    out_dir.mkdir(parents=True)
    with open(out_dir / "draft_content.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(c, **_DUMP))
    # draft_meta_info.json tối thiểu (dựa donor 0720)
    meta = copy.deepcopy(json.loads((_duong_dan_mau(DONOR_TEXT) / "draft_meta_info.json")
                                    .read_text(encoding="utf-8", errors="replace")))
    meta["draft_id"] = uid()
    meta["draft_name"] = out_name
    meta["draft_fold_path"] = str(out_dir).replace("\\", "/")
    meta["draft_materials"] = []
    meta["tm_duration"] = V
    with open(out_dir / "draft_meta_info.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, **_DUMP))
    print(f"\n✅ Đã tạo draft: {out_dir}")
    print("   Mở CapCut để kiểm tra (draft sẽ được tự nhận vào danh sách).")


# ══════════════════════ EQ GYM AI EDITOR — dựng theo kịch bản CSV ══════════════════════
# Khác build() ở trên (folder tự suy thứ tự + voice chia đều): ở đây có SẴN kịch bản
# đúng nghĩa — mỗi dòng CSV là MỘT cảnh, ĐÚNG THỨ TỰ DÒNG trên timeline, dài ĐÚNG số
# giây khai trong cột Duration, lời đọc ĐÚNG cột VO. Không suy, không đoán, không ASR
# lại — dữ liệu đã có sẵn và chính xác hơn bất kỳ suy luận nào từ audio thật.
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
CSV_COT_BAT_BUOC = {"Scene", "Duration", "VO"}


def doc_kich_ban_csv(csv_path) -> list:
    """Đọc CSV kịch bản. Cột Prompt/Img*Name/Img*Data (nếu có) là dữ liệu cho bước
    TẠO VIDEO BẰNG AI ở NGOÀI app này (Img*Data là ảnh tham chiếu mã hoá base64,
    có dòng nặng vài chục KB) — cố tình KHÔNG đọc tới, khỏi tải hàng MB vô ích.

    Duration=0 hoặc không đọc được số thì DỪNG NGAY — cảnh không có độ dài thì
    không thể xếp lên timeline, và lỗi đó phải lộ ra lúc đọc CSV, không phải lúc
    ffmpeg ghép clip thất bại với thông báo khó hiểu."""
    canh = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        thieu = CSV_COT_BAT_BUOC - set(r.fieldnames or [])
        if thieu:
            raise RuntimeError(
                f"CSV thiếu cột bắt buộc: {', '.join(sorted(thieu))}. "
                f"Cột hiện có: {', '.join(r.fieldnames or [])}")
        for i, row in enumerate(r, 1):
            scene = (row.get("Scene") or "").strip()
            if not scene:
                continue
            try:
                dur = float(row.get("Duration") or 0)
            except ValueError:
                dur = 0
            if dur <= 0:
                raise RuntimeError(
                    f"Dòng {i} (Scene '{scene}'): Duration không hợp lệ "
                    f"({row.get('Duration')!r}) — phải là số giây > 0.")
            canh.append({"scene": scene, "duration_s": dur, "vo": (row.get("VO") or "").strip()})
    if not canh:
        raise RuntimeError(f"CSV không có dòng nào có Scene: {csv_path}")
    return canh


def tim_nguon_canh(scene: str, source_dir) -> Path:
    """Tìm file trong source_dir có TÊN BẮT ĐẦU bằng đúng mã Scene, không phân biệt
    hoa/thường — Scene 'C01' khớp C01.mp4, c01_v2.mov, C01.png. Nhiều file cùng
    khớp thì ưu tiên tên TRÙNG KHỚP TUYỆT ĐỐI (C01.mp4) trước file có hậu tố
    (C01_v2.mp4), để người dùng chủ động chọn bản nào là bản chính bằng cách đặt
    tên đúng — không đoán bản nào "mới hơn" hộ họ."""
    exts = VIDEO_EXTS | IMAGE_EXTS
    ung_vien = sorted(p for p in Path(source_dir).iterdir()
                      if p.is_file() and p.suffix.lower() in exts
                      and p.stem.lower().startswith(scene.lower()))
    if not ung_vien:
        return None
    khop_dung = [p for p in ung_vien if p.stem.lower() == scene.lower()]
    return (khop_dung or ung_vien)[0]


def _anh_thanh_clip_tinh(img_path: Path, dur_s: float, cache_dir: Path) -> Path:
    """Ảnh slide -> clip video tĩnh đúng thời lượng (ffmpeg), rồi đi chung một
    đường dựng video-track với clip AI-gen thật ở dưới.

    VÌ SAO không tự chế material type="photo" của CapCut: dự án CHƯA có draft mẫu
    nào chứa loại material đó để soi đúng cấu trúc JSON thật — bịa theo trí nhớ là
    rủi ro hỏng draft mà CapCut không báo lỗi rõ ràng (mở lên thấy trắng hoặc app
    treo). ffmpeg thì đã được đo và tin cậy trong toàn bộ pipeline sẵn có."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{img_path.stem}_tinh_{dur_s:.2f}s.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(img_path), "-t", f"{dur_s:.3f}",
         "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,fps=30", "-pix_fmt", "yuv420p", "-an", str(out)],
        check=True, capture_output=True)
    return out


def build_from_csv(csv_path, source_dir, voice_path, out_name, do_write=True,
                    caption_mode="template", cap_chars=18, cap_words=5) -> dict:
    """Dựng 1 draft CapCut ĐÚNG theo kịch bản CSV (quy trình EQ Gym AI Editor).

    Khác build(): timing từng cảnh lấy từ cột Duration (không chia đều theo voice),
    caption lấy thẳng từ cột VO (không ASR lại — kịch bản đã đúng sẵn), và MỘT file
    voice DUY NHẤT chạy xuyên suốt toàn bộ timeline làm audio track.

    Thiếu nguồn cho scene nào -> DỪNG NGAY, liệt kê đủ tên scene thiếu MỘT LƯỢT
    (luật cứng #2: không hỏng im lặng) — không dựng draft cụt cảnh rồi để người
    dùng tự phát hiện khi mở CapCut lên."""
    csv_path, source_dir, voice_path = Path(csv_path), Path(source_dir), Path(voice_path)
    # CHỈ cần DONOR_VIDEO ("282new", đã đóng gói kèm app) — KHÔNG dùng DONOR_TEXT
    # ("0720") như build() gốc. "0720" chỉ tồn tại trên đúng máy dev làm ra nó, chưa
    # từng được đóng gói (khác 282new — cái đã bị lỗi y hệt này một lần, xem
    # test_draft_mau_di_theo_app). shorts/build_short_draft.py (luồng chính) đã tự
    # vá đúng lỗi này từ trước bằng cách dùng 282new cho CẢ HAI vai trò — nó có đủ
    # video-seg lẫn caption template. Dùng lại đúng cách đã chứng minh chạy được.
    kiem_tra_draft_mau(DONOR_VIDEO)
    if not voice_path.exists():
        raise RuntimeError(f"Không thấy file voice: {voice_path}")
    canh_list = doc_kich_ban_csv(csv_path)

    thieu, nguon = [], {}
    for c in canh_list:
        p = tim_nguon_canh(c["scene"], source_dir)
        if p is None:
            thieu.append(c["scene"])
        else:
            nguon[c["scene"]] = p
    if thieu:
        raise RuntimeError(
            f"Thiếu file nguồn cho {len(thieu)}/{len(canh_list)} cảnh: {', '.join(thieu)}. "
            f"Tên file trong '{source_dir}' phải bắt đầu bằng đúng mã Scene (vd C01.mp4).")

    print(f"Kịch bản : {len(canh_list)} cảnh, tổng khai báo {sum(c['duration_s'] for c in canh_list):.1f}s")
    print(f"Voice    : {voice_path.name}")

    cache_dir = voice_path.parent / ".eqgym_cache"
    for c in canh_list:
        p = nguon[c["scene"]]
        if p.suffix.lower() in IMAGE_EXTS:
            print(f"  [{c['scene']}] ảnh slide -> clip tĩnh {c['duration_s']:.1f}s...")
            nguon[c["scene"]] = _anh_thanh_clip_tinh(p, c["duration_s"], cache_dir)

    vinfo = probe(voice_path)
    V = vinfo["duration_us"]

    # ---- donor (chỉ 282new — xem giải thích ở kiem_tra_draft_mau phía trên) ----
    dv = load_draft(DONOR_VIDEO)
    dt = dv
    vtrack_src = next(t for t in dv["tracks"] if t["type"] == "video")
    seg_tpl = vtrack_src["segments"][0]
    ref_units = []
    prim_arr, prim_mat = find_mat(dv, seg_tpl["material_id"])
    for rid in seg_tpl["extra_material_refs"]:
        a, m = find_mat(dv, rid)
        ref_units.append((a, m))
    trans_tpl = dv["materials"]["transitions"][0]
    atrack_src = next(t for t in dt["tracks"] if t["type"] == "audio")
    aseg_tpl = atrack_src["segments"][0]
    _, amat_tpl = find_mat(dt, aseg_tpl["material_id"])

    c = copy.deepcopy(dv)
    c["tracks"] = []
    for k in list(c["materials"].keys()):
        if isinstance(c["materials"][k], list):
            c["materials"][k] = []
    for k in list(c.get("keyframes", {}).keys()):
        if isinstance(c["keyframes"][k], list):
            c["keyframes"][k] = []
    c["id"] = uid()
    c["name"] = out_name
    c["duration"] = V

    def add_mat(arr, obj):
        c["materials"].setdefault(arr, []).append(obj)

    # ---- VIDEO TRACK — timing ĐÚNG Duration từng cảnh, không chia đều ----
    vtrack = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in vtrack_src.items()}
    vtrack["id"] = uid()
    start = 0
    for i, cnh in enumerate(canh_list):
        clip = nguon[cnh["scene"]]
        ci = probe(clip)
        slice_us = int(round(cnh["duration_s"] * 1_000_000))
        seg = copy.deepcopy(seg_tpl)
        seg["id"] = uid()
        vm = copy.deepcopy(prim_mat)
        vm["id"] = uid()
        vm["path"] = str(clip).replace("\\", "/")
        vm["material_name"] = f"{cnh['scene']} — {clip.stem}"
        vm["duration"] = ci["duration_us"]
        if ci["width"]:
            vm["width"], vm["height"] = ci["width"], ci["height"]
        vm["has_audio"] = ci["has_audio"]
        add_mat(prim_arr, vm)
        seg["material_id"] = vm["id"]
        newrefs = []
        for arr, m in ref_units:
            if m is None:
                continue
            nm = copy.deepcopy(m)
            nm["id"] = uid()
            add_mat(arr, nm)
            newrefs.append((arr, nm))
        native = ci["duration_us"]
        if native >= slice_us:
            src_dur = slice_us; speed = 1.0
        else:
            # Clip AI-gen ngắn hơn Duration khai báo trong CSV — kéo giãn tốc độ để
            # lấp đủ chỗ, thay vì để hở khoảng đen giữa hai cảnh trên timeline.
            src_dur = native; speed = round(native / slice_us, 6) if slice_us else 1.0
        seg["source_timerange"] = {"start": 0, "duration": src_dur}
        seg["target_timerange"] = {"start": start, "duration": slice_us}
        seg["speed"] = speed
        seg["volume"] = 0.0            # tắt tiếng gốc clip — chỉ dùng voiceover chung
        seg["last_nonzero_volume"] = 0.0
        for arr, nm in newrefs:
            if arr == "speeds":
                nm["speed"] = speed
                if "curve_speed" in nm:
                    nm["curve_speed"] = None
        ref_ids = [nm["id"] for _, nm in newrefs]
        if i > 0:
            tr = copy.deepcopy(trans_tpl)
            tr["id"] = uid()
            add_mat("transitions", tr)
            ref_ids.insert(2, tr["id"])
        seg["extra_material_refs"] = ref_ids
        seg["render_index"] = i
        vtrack["segments"].append(seg)
        start += slice_us
    c["tracks"].append(vtrack)
    # Tổng Duration khai báo trong CSV có thể lệch với độ dài voice thật (VD kịch
    # bản ước lượng 8-10s/cảnh nhưng giọng đọc thật nhanh/chậm hơn) — KHÔNG tự co
    # giãn để che lệch: báo rõ số giây lệch, người dùng tự quyết sửa CSV hay thu
    # lại voice, giấu đi là hỏng im lặng.
    if abs(start - V) > 500_000:
        print(f"⚠️  Tổng Duration các cảnh ({start/1e6:.1f}s) lệch với voice thật "
              f"({V/1e6:.1f}s) — {'thiếu' if start < V else 'thừa'} khoảng "
              f"{abs(start-V)/1e6:.1f}s so với giọng đọc.")

    # ---- AUDIO TRACK — một voice chung cho toàn bộ timeline ----
    atrack = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in atrack_src.items()}
    atrack["id"] = uid()
    am = copy.deepcopy(amat_tpl)
    am["id"] = uid()
    am["path"] = str(voice_path).replace("\\", "/")
    am["name"] = voice_path.name
    am["duration"] = V
    add_mat("audios", am)
    aseg = copy.deepcopy(aseg_tpl)
    aseg["id"] = uid()
    aseg["material_id"] = am["id"]
    aseg["extra_material_refs"] = []
    aseg["source_timerange"] = {"start": 0, "duration": V}
    aseg["target_timerange"] = {"start": 0, "duration": V}
    atrack["segments"].append(aseg)
    c["tracks"].append(atrack)

    # ---- CAPTION TRACK — lấy THẲNG từ cột VO, mốc theo Duration tích luỹ ----
    # Không word-level timing thật (không ASR) -> mỗi cảnh là MỘT khối caption
    # nguyên câu, hiện suốt cảnh đó; rechunk() vẫn cắt bớt nếu câu quá dài.
    caps = []
    t0 = 0
    for cnh in canh_list:
        dur_ms = int(round(cnh["duration_s"] * 1000))
        if cnh["vo"]:
            caps.append({"text": cnh["vo"], "start_ms": t0, "end_ms": t0 + dur_ms, "words": []})
        t0 += dur_ms
    if caps:
        n0 = len(caps)
        caps = rechunk(caps, cap_chars, cap_words)
        print(f"  [caption] {n0} cảnh có lời -> {len(caps)} cụm ngắn (<= {cap_chars} ký tự)")
    unit = extract_caption_unit(dt) if caption_mode == "template" else None
    if caps and caption_mode == "template" and unit is None:
        print("  [caption] Donor không có caption-template -> chuyển sang text thường.")
        caption_mode = "plain"
    text_tpl = pick_white_text_material(dt) if caption_mode != "template" else None
    ttrack_src = next(t for t in dt["tracks"] if t["type"] == "text")
    tseg_tpl = ttrack_src["segments"][0]
    if caps:
        ttrack = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in ttrack_src.items()}
        ttrack["id"] = uid()
        for cap in caps:
            if caption_mode == "template":
                ts, mats = gen_template_caption(unit, cap)
                for arr, m in mats:
                    add_mat(arr, m)
                ttrack["segments"].append(ts)
            else:
                tm = copy.deepcopy(text_tpl)
                tm["id"] = uid()
                tm["content"] = make_caption_content(cap["text"])
                tm["words"] = make_words(cap)
                add_mat("texts", tm)
                ts = copy.deepcopy(tseg_tpl)
                ts["id"] = uid()
                ts["material_id"] = tm["id"]
                ts["extra_material_refs"] = []
                ts["template_id"] = ""
                ts["clip"] = {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0,
                              "transform": {"x": 0.0, "y": -0.56},
                              "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0}
                dur = max(120000, (cap["end_ms"] - cap["start_ms"]) * 1000)
                ts["source_timerange"] = None
                ts["target_timerange"] = {"start": cap["start_ms"] * 1000, "duration": dur}
                ttrack["segments"].append(ts)
        c["tracks"].append(ttrack)
        print(f"  [caption] chế độ = {caption_mode}")
    else:
        print("  [caption] Không có lời thoại nào trong cột VO — bỏ qua caption.")

    print(f"\nTổng: {len(vtrack['segments'])} cảnh, {len(caps)} caption, video dài {V/1e6:.2f}s")
    ket_qua = {"scenes": len(canh_list), "captions": len(caps), "duration_s": round(V / 1e6, 1)}
    if not do_write:
        print("[DRY-RUN] Chưa ghi. Truyền do_write=True để tạo draft thật.")
        return ket_qua

    out_dir = DRAFTS_ROOT / out_name
    if out_dir.exists():
        raise RuntimeError(f"Draft đã tồn tại: {out_dir}")
    out_dir.mkdir(parents=True)
    with open(out_dir / "draft_content.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(c, **_DUMP))
    meta = copy.deepcopy(json.loads((_duong_dan_mau(DONOR_VIDEO) / "draft_meta_info.json")
                                    .read_text(encoding="utf-8", errors="replace")))
    meta["draft_id"] = uid()
    meta["draft_name"] = out_name
    meta["draft_fold_path"] = str(out_dir).replace("\\", "/")
    meta["draft_materials"] = []
    meta["tm_duration"] = V
    with open(out_dir / "draft_meta_info.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, **_DUMP))
    print(f"\n✅ Đã tạo draft: {out_dir}")
    print("   Mở CapCut để kiểm tra (draft sẽ được tự nhận vào danh sách).")
    ket_qua["draft"] = out_name
    return ket_qua


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", help="thư mục chứa clip+voice (bỏ qua nếu dùng --eqgym-csv)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--model", default="small", help="whisper model: tiny/base/small/medium")
    ap.add_argument("--caption", default="template", choices=["template", "plain"],
                    help="template = giống 0720 (mặc định); plain = text trắng đơn giản")
    ap.add_argument("--cap-chars", type=int, default=18, help="số ký tự tối đa mỗi cụm caption")
    ap.add_argument("--cap-words", type=int, default=5, help="số chữ tối đa mỗi cụm caption")
    ap.add_argument("--script", default=None, help="file .txt kịch bản (mặc định tự tìm .txt trong folder)")
    ap.add_argument("--keep-clip-audio", action="store_true", help="GIỮ tiếng gốc của clip (mặc định tắt)")
    # EQ Gym AI Editor: dựng theo kịch bản CSV thay vì suy từ thư mục.
    ap.add_argument("--eqgym-csv", default=None, help="file CSV kịch bản (cột Scene,Duration,VO)")
    ap.add_argument("--eqgym-source", default=None, help="thư mục chứa video/ảnh đã tạo, tên khớp mã Scene")
    ap.add_argument("--eqgym-voice", default=None, help="file voiceover DUY NHẤT cho toàn bộ video")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    try:
        if a.eqgym_csv:
            if not (a.eqgym_source and a.eqgym_voice):
                sys.exit("--eqgym-csv cần đi kèm --eqgym-source và --eqgym-voice")
            build_from_csv(a.eqgym_csv, a.eqgym_source, a.eqgym_voice, a.name, a.yes,
                           a.caption, a.cap_chars, a.cap_words)
        else:
            if not a.folder:
                sys.exit("Thiếu tham số folder (hoặc dùng --eqgym-csv cho quy trình EQ Gym)")
            build(a.folder, a.name, a.model, a.yes, a.caption, a.cap_chars, a.cap_words,
                  a.script, not a.keep_clip_audio)
    except RuntimeError as e:
        sys.exit(str(e))

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
