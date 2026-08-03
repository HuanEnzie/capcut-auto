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
            canh.append({"scene": scene, "loai": "render", "duration_s": dur,
                         "vo": (row.get("VO") or "").strip(), "anh": None})
    if not canh:
        raise RuntimeError(f"CSV không có dòng nào có Scene: {csv_path}")
    return canh


def doc_kich_ban_xls(path) -> list:
    """Đọc bản 'lưu ý CapCut' (.xls/.xlsx) — ĐÂY MỚI LÀ BẢN THIẾT KẾ THẬT của video.

    Hơn hẳn file CSV ở chỗ: CSV chỉ có 23 cảnh AI-gen, còn bảng này có đủ 28 dòng
    theo ĐÚNG thứ tự dựng, trong đó xen 5 SLIDE CHỮ im lặng (S1..S5) mà CSV không
    hề nhắc tới — dựng thiếu là hỏng cả bố cục bài.

    Cột: STT | Loại (RENDER/SLIDE) | ID | Dài (s) | VO | Màn hình hiện gì |
         File ảnh cần chèn | Hướng dẫn CapCut

    Đọc thẳng XML trong file (zipfile + ElementTree của thư viện chuẩn) thay vì
    thêm openpyxl: chỉ cần vài cột đầu, không đáng thêm một phụ thuộc phải cài
    trên mọi máy và phải gói vào bản .exe."""
    import zipfile
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(path)
    chung = []
    if "xl/sharedStrings.xml" in z.namelist():
        r = ET.fromstring(z.read("xl/sharedStrings.xml"))
        chung = ["".join(t.text or "" for t in si.iter(ns + "t")) for si in r.findall(ns + "si")]
    sh = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    hang = []
    for row in sh.iter(ns + "row"):
        o = {}
        for cell in row.findall(ns + "c"):
            cot = re.match(r"([A-Z]+)", cell.get("r") or "A")
            cot = cot.group(1) if cot else "A"
            v = cell.find(ns + "v")
            if cell.get("t") == "s" and v is not None:
                txt = chung[int(v.text)] if int(v.text) < len(chung) else ""
            else:
                txt = "".join(t.text or "" for t in cell.iter(ns + "t")) or (v.text if v is not None else "")
            o[cot] = (txt or "").strip()
        if o:
            hang.append(o)

    canh = []
    for o in hang:
        loai, ma = (o.get("B") or "").upper(), (o.get("C") or "").strip()
        if loai not in ("RENDER", "SLIDE") or not ma:
            continue                       # bỏ dòng tiêu đề / dòng trống
        try:
            dur = float(o.get("D") or 0)
        except ValueError:
            dur = 0
        if dur <= 0:
            raise RuntimeError(f"Dòng ID '{ma}': cột 'Dài (s)' không hợp lệ ({o.get('D')!r}).")
        canh.append({
            "scene": ma,
            "loai": "slide" if loai == "SLIDE" else "render",
            "duration_s": dur,
            # Slide KHÔNG có lời — ô VO của nó là ghi chú '(KHÔNG LỜI — ...)', không
            # phải câu để đọc. Nhận nhầm là bước khớp giọng đi tìm một câu không tồn
            # tại trong bản thu.
            "vo": "" if loai == "SLIDE" else (o.get("E") or "").strip(),
            "anh": (o.get("G") or "").strip() or None,
        })
    if not canh:
        raise RuntimeError(f"Không đọc được dòng RENDER/SLIDE nào trong {path}")
    return canh


def doc_kich_ban(path) -> list:
    """Đọc kịch bản, tự nhận .csv hay .xls/.xlsx."""
    return (doc_kich_ban_xls(path) if str(path).lower().endswith((".xls", ".xlsx"))
            else doc_kich_ban_csv(path))


def tim_nguon_canh(scene: str, source_dir, ten_goi_y: str = None) -> Path:
    """Tìm file trong source_dir có TÊN BẮT ĐẦU bằng đúng mã Scene, không phân biệt
    hoa/thường — Scene 'C01' khớp C01.mp4, c01_v2.mov, C01.png. Nhiều file cùng
    khớp thì ưu tiên tên TRÙNG KHỚP TUYỆT ĐỐI (C01.mp4) trước file có hậu tố
    (C01_v2.mp4), để người dùng chủ động chọn bản nào là bản chính bằng cách đặt
    tên đúng — không đoán bản nào "mới hơn" hộ họ.

    `ten_goi_y` — cột 'File ảnh cần chèn' của bảng lưu ý CapCut, dạng
    'slides/SLIDE_1_....png'. Tìm theo TÊN FILE thôi, bỏ phần thư mục: bảng ghi
    đường dẫn theo cấu trúc dự định, còn thực tế người dùng để phẳng cùng một chỗ.
    Tìm cả trong thư mục con để hai kiểu sắp xếp đều chạy."""
    src = Path(source_dir)
    if ten_goi_y:
        ten = Path(ten_goi_y.replace("\\", "/")).name
        ung = [p for p in src.rglob(ten) if p.is_file()]
        if ung:
            return ung[0]
        # Không thấy đúng tên -> thử theo phần đầu tên file (bỏ đuôi), phòng khi
        # người dùng đổi tên nhẹ. Vẫn không thấy thì rơi xuống cách tìm theo mã.
        goc = Path(ten).stem.lower()
        ung = sorted(p for p in src.rglob("*")
                     if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                     and p.stem.lower() == goc)
        if ung:
            return ung[0]
    exts = VIDEO_EXTS | IMAGE_EXTS
    ung_vien = sorted(p for p in src.iterdir()
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


def _diem_noi(path) -> tuple:
    """(giây bắt đầu nói, giây kết thúc nói) trong một clip — đo bằng ffmpeg silencedetect.

    VÌ SAO CẦN: clip AI-gen đo được có 0,17-0,70 giây LẶNG ở đầu trước khi miệng bắt
    đầu mấp máy (đo trên 5 clip thật của EQ Gym). Nếu cứ đặt cả clip vào đúng ô thời
    gian của giọng đọc, phần lặng đầu đó đẩy toàn bộ khẩu hình trễ đi ngần ấy — nửa
    giây lệch môi là nhìn ra ngay. Cắt bỏ lặng đầu rồi mới kéo giãn thì miệng bám
    đúng chỗ giọng thật bắt đầu."""
    out = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "silencedetect=noise=-35dB:d=0.15",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    dur = probe(path)["duration_us"] / 1e6
    # Lặng bắt đầu ngay từ giây 0 -> clip mở đầu bằng khoảng lặng, tiếng nói bắt đầu
    # ở chỗ khoảng lặng đó kết thúc. Ngược lại thì nói ngay từ đầu.
    bat_dau = ends[0] if (starts and ends and starts[0] <= 0.05) else 0.0
    # Nhiều silence_start hơn silence_end -> khoảng lặng cuối chạy tới hết clip.
    ket_thuc = starts[-1] if len(starts) > len(ends) else dur
    if ket_thuc - bat_dau < 0.3:        # đo hỏng (clip lặng hết) -> dùng cả clip
        return 0.0, dur
    return bat_dau, ket_thuc


def _khop_canh_vao_voice(canh_list, words) -> dict:
    """Tìm MỖI cảnh nằm ở đâu trong file voice, dựa vào LỜI (cột VO) — trả về
    {chỉ số cảnh: (chữ_đầu, chữ_cuối, tỷ_lệ_khớp)}.

    KHÔNG giả định voice đọc đúng thứ tự CSV. Đo trên dữ liệu thật (EQ Gym BAI00):
    voice đọc C01..C15 rồi NHẢY sang C18,C19,C20,C21 rồi mới quay lại C16,C17 —
    kịch bản CSV đã được xếp lại sau khi thu tiếng. Cứ ghép tuần tự là toàn bộ nửa
    sau lệch hẳn.

    Cách làm — GIÀNH CHỖ THEO ĐỘ TIN CẬY: mỗi vòng, chấm điểm mọi cảnh chưa có chỗ,
    cho cảnh khớp chắc nhất giành trước rồi CHE vùng đó khỏi các vòng sau. Cần thế
    vì có cặp cảnh gần trùng lời (C18 và C23 cùng kết bằng 'để làm chủ bản thân,
    kết nối người khác và sống đúng với điều quan trọng nhất') — chấm độc lập thì
    cả hai cùng đòi một chỗ, cảnh khớp yếu hơn cướp mất chỗ của cảnh khớp chắc."""
    asr = [re.sub(r"[^\w]", "", w["w"].lower()) for w in words]
    che = [False] * len(asr)
    chua, da = list(range(len(canh_list))), {}

    def cham(vo_text, masked):
        sw = [x for x in (re.sub(r"[^\w]", "", t.lower()) for t in vo_text.split()) if x]
        if not sw:
            return None
        blocks = [b for b in difflib.SequenceMatcher(None, masked, sw, autojunk=False)
                  .get_matching_blocks() if b.size >= 3]
        if not blocks:
            return None
        # Gom khối khớp liền kề thành CỤM, lấy cụm dày nhất — một chữ phổ biến
        # ('của', 'là') khớp lạc ở đầu kia file sẽ kéo vùng ra dài vô nghĩa.
        cum, cur = [], [blocks[0]]
        for b in blocks[1:]:
            truoc = cur[-1]
            if b.a - (truoc.a + truoc.size) <= 25:
                cur.append(b)
            else:
                cum.append(cur)
                cur = [b]
        cum.append(cur)
        best = max(cum, key=lambda g: sum(x.size for x in g))
        return best[0].a, best[-1].a + best[-1].size, sum(x.size for x in best) / len(sw)

    while chua:
        masked = [f"\x00{i}" if che[i] else w for i, w in enumerate(asr)]
        ung = [(r[2], i, r) for i in chua for r in [cham(canh_list[i]["vo"], masked)] if r]
        if not ung:
            break
        _, i, (lo, hi, ty) = max(ung, key=lambda x: x[0])
        da[i] = (lo, hi, ty)
        for k in range(lo, min(hi, len(che))):
            che[k] = True
        chua.remove(i)
    return da


def build_from_csv(csv_path, source_dir, voice_path, out_name, do_write=True,
                    caption_mode="template", cap_chars=18, cap_words=5,
                    them_caption=False, chuyen_canh=False, dong_bo_voice=True,
                    model_asr="small") -> dict:
    """Dựng 1 draft CapCut từ kịch bản CSV (quy trình EQ Gym AI Editor).

    `dong_bo_voice=True` (mặc định) — GIỌNG ĐỌC LÀ GỐC THỜI GIAN, không phải cột
    Duration: bóc lời file voice, khớp lời từng cảnh vào đó để biết cảnh đó được
    đọc ở giây nào, rồi kéo giãn clip cho khẩu hình bám đúng chỗ. Cột Duration chỉ
    còn là ước lượng ban đầu cho bước tạo video bằng AI — đo trên dữ liệu thật thấy
    giọng đọc chậm hơn ước lượng đó 20-40%, và thứ tự đọc còn khác cả thứ tự CSV.

    `dong_bo_voice=False` — xếp thẳng theo cột Duration như bản đầu (nhanh, không
    cần bóc lời), chấp nhận hình và tiếng lệch nhau.

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
    canh_list = doc_kich_ban(csv_path)

    thieu, nguon = [], {}
    for c in canh_list:
        p = tim_nguon_canh(c["scene"], source_dir, c.get("anh"))
        if p is None:
            thieu.append(c["scene"] + (f" (cần {c['anh']})" if c.get("anh") else ""))
        else:
            nguon[c["scene"]] = p
    if thieu:
        # Thiếu ảnh slide thì BỎ dòng đó và báo tên, không dừng cả lượt dựng: bảng
        # lưu ý có thể trỏ tới ảnh chưa xuất (vd infographic tổng kết), trong khi
        # 27 dòng còn lại vẫn dựng được và vẫn đáng xem.
        canh_list = [c for c in canh_list if c["scene"] in nguon]
        print(f"⚠️  Thiếu file nguồn, BỎ QUA {len(thieu)} dòng: {', '.join(thieu)}")
        if not canh_list:
            raise RuntimeError("Không còn dòng nào có đủ file nguồn để dựng.")

    n_render = sum(1 for c in canh_list if c.get("loai", "render") == "render")
    n_slide = len(canh_list) - n_render
    print(f"Kịch bản : {len(canh_list)} dòng ({n_render} clip + {n_slide} slide), "
          f"tổng khai báo {sum(c['duration_s'] for c in canh_list):.1f}s")
    print(f"Voice    : {voice_path.name}")

    cache_dir = voice_path.parent / ".eqgym_cache"
    for c in canh_list:
        p = nguon[c["scene"]]
        if p.suffix.lower() in IMAGE_EXTS:
            print(f"  [{c['scene']}] ảnh -> clip tĩnh {c['duration_s']:.1f}s...")
            nguon[c["scene"]] = _anh_thanh_clip_tinh(p, c["duration_s"], cache_dir)

    vinfo = probe(voice_path)
    V = vinfo["duration_us"]

    # ---- XẾP TIMELINE ----
    # `lich`      : (dòng, giây_bắt_đầu, giây_kết_thúc, tỷ_lệ_khớp) theo thứ tự hình.
    # `audio_segs`: (giây_trong_voice_từ, đến, đặt_tại_giây_trên_timeline) — nhiều
    #               đoạn chứ không phải một mạch, vì SLIDE phải IM LẶNG: voice bị
    #               cắt ra và đẩy phần sau lùi lại đúng bằng thời lượng slide.
    lich, canh_yeu, audio_segs = [], [], []
    if dong_bo_voice:
        print(f"  [đồng bộ] bóc lời voice bằng model '{model_asr}' để lấy mốc từng chữ...")
        caps = transcribe(voice_path, model_asr)
        words = [w for cp in caps for w in cp["words"] if w["w"].strip()]
        if not words:
            print("  [đồng bộ] ⚠️ không bóc được lời nào — lùi về xếp theo cột Duration.")
            dong_bo_voice = False
        else:
            co_loi = [c for c in canh_list if c.get("loai", "render") == "render" and c["vo"]]
            da = _khop_canh_vao_voice(co_loi, words)
            vung = {}                     # mã cảnh -> (giây đầu, giây cuối) trong voice
            for i, (lo, hi, ty) in da.items():
                vung[co_loi[i]["scene"]] = (words[lo]["s"] / 1000,
                                            words[min(hi, len(words)) - 1]["e"] / 1000, ty)
            mat = [c["scene"] for c in co_loi if c["scene"] not in vung]
            if mat:
                # Không khớp được lời -> KHÔNG bịa chỗ. Báo tên để người dùng đối
                # chiếu; dòng đó bị bỏ khỏi timeline, nói rõ chứ không lặng lẽ.
                print(f"  [đồng bộ] ⚠️ {len(mat)} cảnh KHÔNG tìm thấy lời trong voice, "
                      f"bị bỏ khỏi timeline: {', '.join(mat)}")

            # Tách kịch bản thành chuỗi xen kẽ: slide đơn lẻ và CỤM clip liên tiếp.
            # Gom cụm vì giọng đọc trong cụm là một mạch liền, cắt giữa là mất chữ.
            muc, i = [], 0
            while i < len(canh_list):
                if canh_list[i].get("loai", "render") == "slide":
                    muc.append(("slide", canh_list[i])); i += 1
                else:
                    cum = []
                    while i < len(canh_list) and canh_list[i].get("loai", "render") == "render":
                        cum.append(canh_list[i]); i += 1
                    co = [x for x in cum if x["scene"] in vung]
                    if co:
                        co.sort(key=lambda x: vung[x["scene"]][0])
                        muc.append(("cum", co))

            # SLIDE ĂN ĐÚNG ĐOẠN TIẾNG NẰM GIỮA HAI CỤM. Đo trên voice.mp3 thật:
            # giọng CÓ đọc cả 4 tiêu đề slide ("Tại sao là EQ Gym?", "Lời kết"...),
            # dù bảng lưu ý ghi slide "im lặng". Nếu cứ để slide im theo bảng thì
            # phải vứt ~20 giây tiếng đó đi, và chỗ nối nghe cụt ngang. Cho slide
            # ôm đúng đoạn tiếng của nó thì không mất chữ nào, tiếng chạy liền một
            # mạch, và slide vẫn hiện đúng lúc tiêu đề được đọc.
            t = 0.0
            for k, (loai, noi_dung) in enumerate(muc):
                if loai == "slide":
                    truoc = next((m for m in reversed(muc[:k]) if m[0] == "cum"), None)
                    sau = next((m for m in muc[k + 1:] if m[0] == "cum"), None)
                    if truoc and sau:
                        dai = max(0.2, vung[sau[1][0]["scene"]][0]
                                  - max(vung[x["scene"]][1] for x in truoc[1]))
                    else:
                        dai = noi_dung["duration_s"]   # slide đầu/cuối: theo bảng
                    lich.append((noi_dung, t, t + dai, 1.0))
                    t += dai
                    continue
                co = noi_dung
                vs = vung[co[0]["scene"]][0]
                ve = max(vung[x["scene"]][1] for x in co)
                audio_segs.append((vs, ve, t))
                for j, x in enumerate(co):
                    b = vung[x["scene"]][0]
                    ke = vung[co[j + 1]["scene"]][0] if j + 1 < len(co) else ve
                    lich.append((x, t + (b - vs), t + (ke - vs), vung[x["scene"]][2]))
                    if vung[x["scene"]][2] < 0.5:
                        canh_yeu.append(x["scene"])
                t += (ve - vs)

            # Slide ôm trọn khoảng tiếng giữa hai cụm nên timeline giờ chạy ĐÚNG
            # NHỊP với file voice (cùng một độ lệch cho mọi đoạn). Khi đó chỉ cần
            # MỘT đoạn tiếng trải suốt: giọng chạy liền mạch, không mối nối nào
            # nghe cụt, và không mất câu nào — kể cả 4 tiêu đề slide mà giọng có
            # đọc (đo trên voice.mp3 thật) nhưng bảng lưu ý lại ghi là "im lặng".
            lech = {round(tl - vs, 2) for vs, _, tl in audio_segs}
            if len(lech) == 1:
                d0 = lech.pop()
                audio_segs = [(0.0, V / 1e6, max(0.0, d0))]
                if d0 < 0:      # voice bắt đầu trước mốc 0 của timeline -> cắt bớt đầu
                    audio_segs = [(-d0, V / 1e6, 0.0)]

            if canh_yeu:
                print(f"  [đồng bộ] ⚠️ khớp yếu (<50% chữ), vị trí có thể sai: {', '.join(canh_yeu)}")
            xep = [x[0]["scene"] for x in lich if x[0].get("loai", "render") == "render"]
            goc = [c["scene"] for c in canh_list
                   if c.get("loai", "render") == "render" and c["scene"] in set(xep)]
            if xep != goc:
                print(f"  [đồng bộ] ⚠️ VOICE ĐỌC KHÁC THỨ TỰ KỊCH BẢN — xếp hình theo voice: "
                      f"{' '.join(xep)}")
            print(f"  [đồng bộ] khớp {len(xep)}/{len(co_loi)} clip vào giọng đọc, "
                  f"chèn {sum(1 for x in lich if x[0].get('loai') == 'slide')} slide im lặng")
    if not dong_bo_voice:
        t = 0.0
        for cnh in canh_list:
            lich.append((cnh, t, t + cnh["duration_s"], 1.0))
            t += cnh["duration_s"]
        audio_segs = [(0.0, V / 1e6, 0.0)]

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

    # ---- VIDEO TRACK ----
    vtrack = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in vtrack_src.items()}
    vtrack["id"] = uid()
    for i, (cnh, sec_bd, sec_kt, ty_le) in enumerate(lich):
        clip = nguon[cnh["scene"]]
        ci = probe(clip)
        o_bd = int(round(sec_bd * 1_000_000))
        o_dai = max(200_000, int(round((sec_kt - sec_bd) * 1_000_000)))
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

        # Cắt bỏ khoảng LẶNG ĐẦU của clip rồi mới kéo giãn: phần còn lại (từ lúc
        # miệng bắt đầu mấp máy) trải đúng vào ô thời gian mà giọng thật đang đọc
        # cảnh này -> khẩu hình bám giọng. Xem _diem_noi() cho số đo thật.
        cat_dau = 0
        if dong_bo_voice and ci["has_audio"] and cnh.get("loai", "render") == "render":
            noi_bd, _ = _diem_noi(clip)
            cat_dau = int(noi_bd * 1_000_000)
        con_lai = max(1, ci["duration_us"] - cat_dau)
        src_dur = min(con_lai, o_dai)          # mặc định phát tốc độ thường
        speed = 1.0
        if con_lai < o_dai:
            # Clip ngắn hơn ô thời gian -> chậm lại cho vừa, thay vì để hở hình đen.
            src_dur, speed = con_lai, round(con_lai / o_dai, 6)
        seg["source_timerange"] = {"start": cat_dau, "duration": src_dur}
        seg["target_timerange"] = {"start": o_bd, "duration": o_dai}
        seg["speed"] = speed
        seg["volume"] = 0.0            # tắt tiếng AI của clip — chỉ dùng voiceover thật
        seg["last_nonzero_volume"] = 0.0
        for arr, nm in newrefs:
            if arr == "speeds":
                nm["speed"] = speed
                if "curve_speed" in nm:
                    nm["curve_speed"] = None
        ref_ids = [nm["id"] for _, nm in newrefs]
        if chuyen_canh and i > 0:
            # MẶC ĐỊNH TẮT. Donor chỉ có MỘT hiệu ứng (Slide Zoom) nên bật lên là 22
            # lần chuyển cảnh y hệt nhau — nhìn rất máy móc (người dùng thật báo).
            # Tệ hơn: transition trong CapCut ĂN thời lượng của hai segment kề nó,
            # làm xê dịch đúng cái mốc mà cả bước đồng bộ khẩu hình vừa canh xong.
            tr = copy.deepcopy(trans_tpl)
            tr["id"] = uid()
            add_mat("transitions", tr)
            ref_ids.insert(2, tr["id"])
        seg["extra_material_refs"] = ref_ids
        seg["render_index"] = i
        vtrack["segments"].append(seg)
    c["tracks"].append(vtrack)

    # ---- AUDIO TRACK — một voice chung cho toàn bộ timeline ----
    atrack = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in atrack_src.items()}
    atrack["id"] = uid()
    am = copy.deepcopy(amat_tpl)
    am["id"] = uid()
    am["path"] = str(voice_path).replace("\\", "/")
    am["name"] = voice_path.name
    am["duration"] = V
    # ĐỊA PHƯƠNG HOÁ — donor 282new lấy audio từ kho NHẠC ONLINE của CapCut. Giữ
    # nguyên music_id/category thì CapCut coi đây vẫn là bài nhạc đó, tự phân giải
    # lại về file cache của nó và ĐÈ MẤT đường dẫn voice thật (người dùng báo:
    # "import sai voice"). Cùng một lỗi shorts/build_short_draft.py đã vá cho SFX.
    am["type"] = "extract_music"
    am["category_name"] = "local"
    am["music_id"] = uid()
    for k in ("category_id", "request_id", "resource_id", "effect_id",
              "local_material_id", "remote_url", "intensifies_path"):
        if k in am:
            am[k] = ""
    am["source_platform"] = 0
    add_mat("audios", am)
    for vs, ve, tl in audio_segs:
        aseg = copy.deepcopy(aseg_tpl)
        aseg["id"] = uid()
        aseg["material_id"] = am["id"]
        aseg["extra_material_refs"] = []
        aseg["source_timerange"] = {"start": int(vs * 1e6),
                                    "duration": max(1000, int((ve - vs) * 1e6))}
        aseg["target_timerange"] = {"start": int(tl * 1e6),
                                    "duration": max(1000, int((ve - vs) * 1e6))}
        # Donor là NHẠC NỀN nên âm lượng chỉ ~26% — để nguyên thì giọng đọc bé xíu.
        # Đây là tiếng chính của video, phải 100%.
        aseg["volume"] = 1.0
        aseg["last_nonzero_volume"] = 1.0
        atrack["segments"].append(aseg)
    c["tracks"].append(atrack)

    # ---- CAPTION TRACK — MẶC ĐỊNH TẮT ----
    # Video EQ Gym đã có đồ hoạ/nhãn chữ do AI vẽ sẵn trong hình (xem cột Prompt:
    # "NO SUBTITLES (critical)"), thêm caption nữa là chữ chồng chữ. Bật lại bằng
    # them_caption=True nếu quy trình khác cần.
    caps = []
    if them_caption:
        t0 = 0
        for cnh, sec_bd, sec_kt, _ in lich:
            if cnh["vo"]:
                caps.append({"text": cnh["vo"], "start_ms": int(sec_bd * 1000),
                             "end_ms": int(sec_kt * 1000), "words": []})
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

    # Timeline dài hơn file voice đúng bằng tổng thời lượng các slide im lặng —
    # phải lấy mốc kết thúc THẬT của track hình, không phải độ dài voice.
    het = max((s["target_timerange"]["start"] + s["target_timerange"]["duration"])
              for s in vtrack["segments"])
    c["duration"] = het
    print(f"\nTổng: {len(vtrack['segments'])}/{len(canh_list)} dòng lên hình, "
          f"{len(caps)} caption, video dài {het/1e6:.2f}s (voice {V/1e6:.2f}s)")
    ket_qua = {"scenes": len(vtrack["segments"]), "scenes_csv": len(canh_list),
               "captions": len(caps), "duration_s": round(het / 1e6, 1),
               "bo_qua": [c["scene"] for c in canh_list
                          if c["scene"] not in {x[0]["scene"] for x in lich}],
               "khop_yeu": canh_yeu}
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
    meta["tm_duration"] = het
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
    ap.add_argument("--eqgym-caption", action="store_true",
                    help="thêm caption (mặc định TẮT — video đã có chữ vẽ sẵn trong hình)")
    ap.add_argument("--eqgym-transition", action="store_true",
                    help="thêm hiệu ứng chuyển cảnh (mặc định TẮT — donor chỉ có 1 kiểu, lặp lại nhìn máy móc)")
    ap.add_argument("--eqgym-khong-dong-bo", action="store_true",
                    help="xếp theo cột Duration thay vì bám giọng đọc (nhanh, không cần bóc lời)")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    try:
        if a.eqgym_csv:
            if not (a.eqgym_source and a.eqgym_voice):
                sys.exit("--eqgym-csv cần đi kèm --eqgym-source và --eqgym-voice")
            build_from_csv(a.eqgym_csv, a.eqgym_source, a.eqgym_voice, a.name, a.yes,
                           a.caption, a.cap_chars, a.cap_words,
                           them_caption=a.eqgym_caption, chuyen_canh=a.eqgym_transition,
                           dong_bo_voice=not a.eqgym_khong_dong_bo, model_asr=a.model)
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
