# -*- coding: utf-8 -*-
"""
build_short_draft.py — GD3b: ráp 1 short thành DRAFT CapCut giàu yếu tố.

Kiến trúc: nền reframe (bake bằng ffmpeg, reframe_NN.mp4) + overlay CHỈNH ĐƯỢC trong CapCut:
  video base (reframe.mp4) + caption động (template 0720) + hook + sticker + SFX + entrance animation.

Tái dùng: capcut_build (caption template + helper), render_short (snap/reframe), caption_fix (Gemini).
Donor: 282new (video-seg + animation + sticker), 0720 (caption template + audio).

CÁCH DÙNG:
  set GEMINI_API_KEY=...
  python build_short_draft.py work/1107 --only 4          # tạo reframe (nếu thiếu) + draft
  python build_short_draft.py work/1107 --only 4 --dry    # chỉ kiểm tra integrity
"""
import argparse, copy, hashlib, json, subprocess, sys, time, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # để import capcut_build
import capcut_build as cb
import assetlib
import gemini_util
from render_short import snap, reframe_cut, captions_for_cuts, tighten_cuts, append_tail
from caption_fix import fix_captions
from enrich import enrich_topic

DRAFTS = cb.DRAFTS_ROOT
DONOR_V, DONOR_T = "282new", "282new"   # 282new có đủ: video-seg, caption template, audio, animation, sticker
SFX_DEFAULT = "E:/E Download/meme"   # thư mục chứa SFX; AI chọn file phù hợp
TAIL_SEC = 2.4                       # đuôi kết (chỗ thở + nền cho card chốt)
CTA = "Theo dõi để xem thêm"


def probe_dur(p) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nokey=1:noprint_wrappers=1", str(p)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def integrity(c) -> int:
    ids = set()
    for arr in c["materials"].values():
        if isinstance(arr, list):
            for m in arr:
                if isinstance(m, dict) and "id" in m:
                    ids.add(m["id"])
    dangling = 0
    for t in c["tracks"]:
        for s in t["segments"]:
            for r in [s["material_id"]] + s.get("extra_material_refs", []):
                if r not in ids:
                    dangling += 1
    for sub in c["materials"].get("text_templates", []):
        for tir in sub.get("text_info_resources", []):
            if tir.get("text_material_id") not in ids:
                dangling += 1
    return dangling


def _cache_path(row):
    """Đường dẫn gói effect/sticker HỢP LỆ trên máy hiện tại (từ kho -> cache CapCut)."""
    import asset_restore
    rel = asset_restore.cache_rel(row["src_path"] or "")
    if rel:
        p = asset_restore.CACHE_ROOT / rel
        if p.exists():
            return str(p).replace("\\", "/")
    # fallback: src gốc (đúng trên chính máy đã harvest)
    sp = row["src_path"]
    return sp.replace("\\", "/") if sp and Path(sp).exists() else None


def ensure_fine(work: Path, topic: dict, asr_model="medium", device="cuda") -> dict:
    """TẦNG 2 — caption cần mốc TỪNG TỪ, mà bản khảo sát (tầng 1) không có.
    Bóc kỹ lại CHỈ các đoạn của chủ đề này bằng model to. Nhanh vì chỉ vài phút audio,
    và caption còn đẹp hơn cách cũ (cũ dùng small cho cả file, giờ medium cho đoạn cần)."""
    import transcribe as trm
    tr = trm.load_transcript(work)

    def has_words(t, a, b):
        return any(s.get("words") for s in t["segments"] if s["end"] > a and s["start"] < b)

    src = tr["source"]
    for s in topic["segments"]:
        a, b = s["start_sec"], s["end_sec"]
        if not has_words(tr, a, b):
            # ten=work.name: dự án dùng lại record của dự án khác có thư mục riêng,
            # suy tên từ file record là ghi nhầm sang thư mục của dự án kia.
            tr = trm.refine_range(src, a, b, asr_model, device, ten=work.name)
    return tr


def khoa_khoang_cat(nguon: str, cuts) -> str:
    """Khoá cache cho video nền + B-roll: băm NGUỒN + KHOẢNG CẮT.

    Tách riêng để test khoá được: đây là chỗ đã gây ra draft trộn nội dung hai lần
    phân tích (xem chú thích tại nơi gọi)."""
    return hashlib.sha1(json.dumps(
        {"nguon": str(nguon), "cat": [[round(a, 3), round(b, 3)] for a, b in cuts]},
        sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]


def build(work: Path, idx: int, sfx_path: str, model: str, dry: bool, name: str = None,
          editor: str = "shared"):
    topics = json.loads((work / "topics.json").read_text(encoding="utf-8"))
    topic = topics["topics"][idx - 1]
    tr = ensure_fine(work, topic)
    segs = tr["segments"]

    body_cuts = []
    for s in topic["segments"]:
        a, b = snap(s["start_sec"], s["end_sec"], segs)
        body_cuts.append((max(0, a - 0.4), b + 0.4))
    # cắt bỏ khoảng lặng dài -> giữ nhịp (short không được để chết vài giây)
    body_cuts, n_gaps, saved = tighten_cuts(body_cuts, segs)
    if n_gaps:
        print(f"  [nhịp] bỏ {n_gaps} khoảng lặng, rút gọn {saved:.1f}s")

    # AI enrichment: hook (cold-open) + emoji + sfx
    # Cạn hạn ngạch KHÔNG được giết cả lượt build: enrich là đồ tô điểm, còn phần
    # xương sống (video nền + caption) đã có đủ. Mất trắng sau khi đã bóc lời và
    # render xong thì đắt hơn nhiều so với một draft trơn kèm cảnh báo rõ.
    try:
        enr = enrich_topic(work, idx, model)
    except gemini_util.HetHanNgach as e:
        print(f"  [enrich] ⚠️ CẠN HẠN NGẠCH GEMINI — dựng draft TRƠN (không hook, "
              f"emoji, SFX, B-roll). Chạy lại sau khi hạn ngạch reset để có đủ lớp.")
        print(f"  [enrich]   {str(e).split('—')[0].strip()}")
        enr = None
    hook_dur = 0.0
    if enr and enr.get("hook"):
        ha, hb = snap(enr["hook"]["start_sec"], enr["hook"]["end_sec"], segs)
        hook_cut = (max(0, ha - 0.2), hb + 0.2)
        cuts = [hook_cut] + body_cuts            # cold-open: hook lên đầu
        hook_dur = hook_cut[1] - hook_cut[0]
    else:
        cuts = body_cuts

    def src_to_out(sec, snap_within=3.0):
        """map giây NGUỒN -> giây trong short (theo cuts, tính cold-open).

        Cue rơi vào KHOẢNG LẶNG vừa bị cắt thì DỜI về mép gần nhất còn giữ, không bỏ đi —
        bỏ thì mất SFX/emoji đúng những chỗ chuyển ý, lại hụt nhịp."""
        off, best = 0.0, None
        for (c0, c1) in cuts:
            if c0 <= sec <= c1:
                return off + (sec - c0)
            d = (c0 - sec) if sec < c0 else (sec - c1)
            cand = off + (0.0 if sec < c0 else (c1 - c0))
            if best is None or d < best[0]:
                best = (d, cand)
            off += (c1 - c0)
        if best and best[0] <= snap_within:
            return best[1]
        return None

    # reframe + broll dùng chung theo NỘI DUNG (không theo tên draft) -> Dan/Nguyên cùng
    # chủ đề tái dùng, tạo draft lần 2 nhanh. Chỉ render khi CHƯA có file (không đè ->
    # an toàn khi CapCut đang mở).
    #
    # KHOÁ PHẢI THEO KHOẢNG CẮT, KHÔNG THEO CHỈ SỐ CHỦ ĐỀ. Lỗi đã trả giá 27/07: bấm
    # "Phân tích" lại thì transcript lấy từ cache nhưng Gemini trả về danh sách chủ đề
    # KHÁC, nên "chủ đề 1" trỏ sang đoạn khác — mà file reframe_t1.mp4 cũ vẫn còn nên
    # được tái dùng. Kết quả: caption/SFX/B-roll dựng cho chủ đề mới, còn hình và tiếng
    # bên dưới là của chủ đề cũ. Draft trộn, không lỗi, không cảnh báo.
    # Băm khoảng cắt + nguồn: khoảng cắt đổi -> file khác; giống nhau -> vẫn dùng chung.
    base_tag = f"t{idx}_{khoa_khoang_cat(tr['source'], cuts)}"
    base = work / "shorts" / f"reframe_{base_tag}.mp4"
    if not base.exists():
        print(f"  [base] render {base.name}...")
        base.parent.mkdir(parents=True, exist_ok=True)
        if len(cuts) == 1:
            reframe_cut(tr["source"], cuts[0][0], cuts[0][1] - cuts[0][0], base)
        else:
            # cũng theo base_tag: thư mục tạm khoá theo chỉ số sẽ lẫn mảnh của lần
            # phân tích trước khi số mảnh lần này ít hơn.
            tmp = base.parent / f".tmp_{base_tag}"; tmp.mkdir(exist_ok=True); parts = []
            for j, (c0, c1) in enumerate(cuts):
                p = tmp / f"p{j}.mp4"; reframe_cut(tr["source"], c0, c1 - c0, p); parts.append(p)
            lst = tmp / "l.txt"; lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", str(base)], check=True, capture_output=True, cwd=tmp)
        # đuôi kết: chỗ thở + nền cho card chốt (cắt đúng lúc dứt lời nghe rất cụt)
        t_added = append_tail(base)
        if t_added:
            print(f"  [kết] nối đuôi {t_added:.1f}s (giữ khung cuối + tối dần)")
    dur_us = int(probe_dur(base) * 1_000_000)
    body_end_us = dur_us - int(TAIL_SEC * 1_000_000)     # mốc bắt đầu đuôi kết

    fixed = fix_captions(work, model)
    cues = captions_for_cuts(cuts, segs, fixed)

    cb.kiem_tra_draft_mau(DONOR_V, DONOR_T)   # thiếu thì báo NGAY, đừng chạy 10 phút rồi mới chết
    dv, dt = cb.load_draft(DONOR_V), cb.load_draft(DONOR_T)
    unit = cb.extract_caption_unit(dt)

    # skeleton
    c = copy.deepcopy(dv)
    c["tracks"] = []
    for k in list(c["materials"]):
        if isinstance(c["materials"][k], list):
            c["materials"][k] = []
    for k in list(c.get("keyframes", {})):
        if isinstance(c["keyframes"][k], list):
            c["keyframes"][k] = []
    c["id"] = cb.uid(); c["name"] = name or f"1107_short{idx:02d}"; c["duration"] = dur_us

    def add(arr, obj): c["materials"].setdefault(arr, []).append(obj)

    def mk_cap(text, st, en):
        return {"text": text, "start_ms": int(st * 1000), "end_ms": int(en * 1000),
                "words": [{"w": text, "s": int(st * 1000), "e": int(en * 1000)}]}

    # VIDEO track (reframe.mp4)
    vtrack_src = next(t for t in dv["tracks"] if t["type"] == "video")
    seg_tpl = vtrack_src["segments"][0]
    prim_arr, prim_mat = cb.find_mat(dv, seg_tpl["material_id"])
    vseg = copy.deepcopy(seg_tpl); vseg["id"] = cb.uid()
    vm = copy.deepcopy(prim_mat); vm["id"] = cb.uid()
    vm["path"] = str(base).replace("\\", "/"); vm["material_name"] = f"short{idx:02d}"
    vm["duration"] = dur_us; vm["width"] = 1080; vm["height"] = 1920; vm["has_audio"] = True
    add(prim_arr, vm); vseg["material_id"] = vm["id"]
    newrefs = []
    for rid in seg_tpl["extra_material_refs"]:
        arr, m = cb.find_mat(dv, rid)
        if m is None:
            continue
        nm = copy.deepcopy(m); nm["id"] = cb.uid()
        if arr == "speeds":
            nm["speed"] = 1.0; nm["curve_speed"] = None
        add(arr, nm); newrefs.append(nm["id"])
    anim_src = (dv["materials"].get("material_animations") or [None])[0]
    if anim_src:
        anim = copy.deepcopy(anim_src); anim["id"] = cb.uid()
        anim["animations"] = [a for a in anim.get("animations", []) if a.get("type") == "in"][:1]
        if anim["animations"]:
            add("material_animations", anim); newrefs.append(anim["id"])
    vseg["extra_material_refs"] = newrefs
    vseg["source_timerange"] = {"start": 0, "duration": dur_us}
    vseg["target_timerange"] = {"start": 0, "duration": dur_us}
    vseg["speed"] = 1.0; vseg["volume"] = 1.0; vseg["last_nonzero_volume"] = 1.0
    vseg["clip"] = {"scale": {"x": 1, "y": 1}, "rotation": 0, "transform": {"x": 0, "y": 0},
                    "flip": {"vertical": False, "horizontal": False}, "alpha": 1}
    vtrack = {k: (copy.deepcopy(v) if k != "segments" else [vseg]) for k, v in vtrack_src.items()}
    vtrack["id"] = cb.uid()
    c["tracks"].append(vtrack)

    # ---- B-ROLL: stock Pexels, overlay cutaway full-frame (ngay trên video chính, dưới caption) ----
    from pexels import fetch_broll
    broll_dir = work / "shorts" / "broll"
    broll_segs = []
    for i, b in enumerate(enr.get("broll", []) if enr else []):
        o = src_to_out(b["start_sec"])
        if o is None:
            continue
        cue_dur = max(1.5, min(b["end_sec"] - b["start_sec"], 4.0))
        broll_dir.mkdir(parents=True, exist_ok=True)
        bp = broll_dir / f"{base_tag}_broll{i}.mp4"
        if not bp.exists() and not fetch_broll(b["query"], bp, cue_dur):
            continue
        vdur = int(probe_dur(bp) * 1_000_000)
        st_us = int(o * 1_000_000)
        use = min(int(cue_dur * 1_000_000), vdur, dur_us - st_us)
        if use <= 0:
            continue
        bs = copy.deepcopy(seg_tpl); bs["id"] = cb.uid()
        bm = copy.deepcopy(prim_mat); bm["id"] = cb.uid()
        bm["path"] = str(bp).replace("\\", "/"); bm["material_name"] = f"broll{i}"
        bm["duration"] = vdur; bm["width"] = 1080; bm["height"] = 1920; bm["has_audio"] = False
        add(prim_arr, bm); bs["material_id"] = bm["id"]
        brefs = []
        for rid in seg_tpl["extra_material_refs"]:
            arr, m = cb.find_mat(dv, rid)
            if m is None:
                continue
            nm = copy.deepcopy(m); nm["id"] = cb.uid()
            if arr == "speeds":
                nm["speed"] = 1.0; nm["curve_speed"] = None
            add(arr, nm); brefs.append(nm["id"])
        bs["extra_material_refs"] = brefs
        bs["source_timerange"] = {"start": 0, "duration": use}
        bs["target_timerange"] = {"start": st_us, "duration": use}
        bs["speed"] = 1.0; bs["volume"] = 0.0; bs["last_nonzero_volume"] = 0.0
        bs["clip"] = {"scale": {"x": 1, "y": 1}, "rotation": 0, "transform": {"x": 0, "y": 0},
                      "flip": {"vertical": False, "horizontal": False}, "alpha": 1}
        broll_segs.append((st_us, st_us + use, bs))
    b_end, b_tracks = [], []
    for st_us, en_us, bs in sorted(broll_segs, key=lambda x: x[0]):
        ti = next((i for i in range(len(b_end)) if st_us >= b_end[i]), None)
        if ti is None:
            b_tracks.append([bs]); b_end.append(en_us)
        else:
            b_tracks[ti].append(bs); b_end[ti] = en_us
    for segs_ in b_tracks:
        bt = {k: (copy.deepcopy(v) if k != "segments" else segs_) for k, v in vtrack_src.items()}
        bt["id"] = cb.uid()
        c["tracks"].append(bt)
    if broll_segs:
        print(f"  [broll] chèn {len(broll_segs)} stock / {len(b_tracks)} track")

    # ================= P4: LẤY GU EDITOR TỪ KHO =================
    # Draft mới tự dùng font + nhãn dán của chính editor thay vì donor/stock generic.
    p4 = {"editor": editor, "font": None, "stickers": []}
    _font_row = assetlib.pick_one("font", editor)
    if _font_row and _font_row["path_in_lib"]:
        _fp = assetlib.ROOT / _font_row["path_in_lib"]
        if _fp.exists():
            p4["font"] = str(_fp).replace("\\", "/")
            p4["font_name"] = _font_row["name"]
    _sticker_rows = assetlib.pick("sticker", owner=editor, limit=6)

    # ---- TEXT THƯỜNG (nhẹ, không gây đứng hình như template) ----
    ttrack_src = next(t for t in dt["tracks"] if t["type"] == "text")
    text_style = cb.pick_white_text_material(dt)
    tseg_shape = ttrack_src["segments"][0]

    cap_anim_src = (dv["materials"].get("material_animations") or [None])[0]

    def add_text_track(items, y, scale, anim=False, x=0.0, positions=None, font=None):
        tr = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in ttrack_src.items()}
        tr["id"] = cb.uid()
        for i, (st, en, text) in enumerate(items):
            tm = copy.deepcopy(text_style); tm["id"] = cb.uid()
            tm["content"] = cb.make_caption_content(text)
            if font:                                    # P4: font theo gu editor
                tm["font_path"] = font
            tm["words"] = cb.make_words({"start_ms": int(st * 1000), "end_ms": int(en * 1000),
                                         "words": [{"w": text, "s": int(st * 1000), "e": int(en * 1000)}]})
            add("texts", tm)
            ts = copy.deepcopy(tseg_shape); ts["id"] = cb.uid()
            ts["material_id"] = tm["id"]; ts["extra_material_refs"] = []; ts["template_id"] = ""
            if anim and cap_anim_src:                       # "chạy chữ": animation vào cho caption
                an = copy.deepcopy(cap_anim_src); an["id"] = cb.uid()
                an["animations"] = [a for a in an.get("animations", []) if a.get("type") == "in"][:1]
                if an["animations"]:
                    an["animations"][0]["duration"] = 400000
                    add("material_animations", an); ts["extra_material_refs"] = [an["id"]]
            ts["source_timerange"] = None
            ts["target_timerange"] = {"start": int(st * 1_000_000),
                                      "duration": int(max(0.05, en - st) * 1_000_000)}
            px, py = positions[i % len(positions)] if positions else (x, y)
            ts["clip"] = {"scale": {"x": scale, "y": scale}, "rotation": 0,
                          "transform": {"x": px, "y": py},
                          "flip": {"vertical": False, "horizontal": False}, "alpha": 1}
            tr["segments"].append(ts)
        if tr["segments"]:
            c["tracks"].append(tr)

    def split_cue(st, en, text, max_chars=18):
        words = text.split(); lines, cur = [], ""
        for w in words:
            if cur and len(cur + " " + w) > max_chars:
                lines.append(cur); cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)
        total = sum(len(l) for l in lines) or 1
        out, t = [], st
        for l in lines:
            d = (en - st) * len(l) / total
            out.append((t, t + d, l)); t += d
        return out

    # CAPTION: text ngắn, không chồng, băng dưới
    short_cues = []
    for st, en, text in cues:
        short_cues.extend(split_cue(st, en, text))
    short_cues.sort(key=lambda x: x[0])
    for i in range(len(short_cues) - 1):           # clamp: không cho caption tràn sang cái sau
        st, en, tx = short_cues[i]
        nxt = short_cues[i + 1][0]
        if en > nxt:
            short_cues[i] = (st, nxt, tx)
    add_text_track(short_cues, y=-0.72, scale=1.1, anim=True, font=p4["font"])

    # EMOJI: AI chọn theo ngữ cảnh, nhỏ, rải góc (hook giờ là video cold-open nên bỏ banner)
    emo_items = []
    for e in (enr.get("emojis", []) if enr else []):
        o = src_to_out(e["sec"])
        if o is not None and o < dur_us / 1e6:
            emo_items.append((o, min(o + 1.4, dur_us / 1e6), e["emoji"]))
    emo_items.sort(key=lambda x: x[0])
    for i in range(len(emo_items) - 1):
        if emo_items[i][1] > emo_items[i + 1][0]:
            emo_items[i] = (emo_items[i][0], emo_items[i + 1][0], emo_items[i][2])

    # P4: STICKER THẬT của editor tại vài điểm nhấn (dài hơn emoji). Phần còn lại giữ emoji text.
    strack_src = next((t for t in dv["tracks"] if t["type"] == "sticker"), None)
    n_st = 0
    if strack_src and _sticker_rows and emo_items:
        sseg_tpl = strack_src["segments"][0]
        _, smat_tpl = cb.find_mat(dv, sseg_tpl["material_id"])
        strack = {k: (copy.deepcopy(v) if k != "segments" else []) for k, v in strack_src.items()}
        strack["id"] = cb.uid()
        STICK_POS = [(0.60, 0.30), (-0.60, 0.30), (0.60, -0.05), (-0.60, -0.05)]
        take = min(len(_sticker_rows), 4, len(emo_items))
        # chọn các điểm rải đều theo thời gian cho khỏi dồn cục
        step = max(1, len(emo_items) // take)
        picks = emo_items[::step][:take]
        for i, (o0, o1, _emo) in enumerate(picks):
            row = _sticker_rows[i % len(_sticker_rows)]
            cpath = _cache_path(row)
            if not cpath:
                continue
            sm = copy.deepcopy(smat_tpl); sm["id"] = cb.uid()
            sm["resource_id"] = row["resource_id"]; sm["sticker_id"] = row["resource_id"]
            sm["path"] = cpath; sm["name"] = row["name"]
            sm["category_name"] = row["category"] or "Trending"; sm["source_platform"] = 1
            # icon_url/preview_cover_url của DONOR làm timeline vẽ thumbnail SAI (khác video).
            # Blank -> CapCut vẽ thumbnail từ gói local (khớp video).
            sm["icon_url"] = ""; sm["preview_cover_url"] = ""; sm["request_id"] = ""
            add("stickers", sm)
            ss = copy.deepcopy(sseg_tpl); ss["id"] = cb.uid()
            ss["material_id"] = sm["id"]; ss["extra_material_refs"] = []
            ss["source_timerange"] = None
            ss["target_timerange"] = {"start": int(o0 * 1_000_000),
                                      "duration": int(max(1.6, o1 - o0 + 0.8) * 1_000_000)}
            px, py = STICK_POS[i % len(STICK_POS)]
            ss["clip"] = {"scale": {"x": 0.34, "y": 0.34}, "rotation": 0,
                          "transform": {"x": px, "y": py},
                          "flip": {"vertical": False, "horizontal": False}, "alpha": 1}
            strack["segments"].append(ss)
            assetlib.add("sticker", name=row["name"], resource_id=row["resource_id"],
                         origin="user", owner=editor, draft=(name or f"1107_short{idx:02d}"))
            n_st += 1
            p4["stickers"].append(row["name"])
        if strack["segments"]:
            c["tracks"].append(strack)
        picked_times = {p[0] for p in picks}
        emo_items = [e for e in emo_items if e[0] not in picked_times]   # tránh chồng emoji lên sticker

    EMOJI_POS = [(0.62, 0.55), (-0.62, 0.55), (0.62, 0.15), (-0.62, 0.15)]  # rải nhiều góc
    add_text_track(emo_items, y=0.55, scale=0.7, positions=EMOJI_POS)

    # CARD CHỐT trên đuôi kết: tiêu đề chủ đề + CTA. Không có nó thì hết lời là cụt ngang.
    if dur_us > body_end_us > 0:
        te0, te1 = body_end_us / 1e6, dur_us / 1e6

        def wrap(s, n=16):                     # bọc dòng cho khỏi TRÀN VIỀN
            out, cur = [], ""
            for w in s.split():
                if cur and len(cur + " " + w) > n:
                    out.append(cur); cur = w
                else:
                    cur = (cur + " " + w).strip()
            if cur:
                out.append(cur)
            return "\n".join(out[:4])

        title = (topic.get("title") or "").strip()
        if title:
            add_text_track([(te0 + 0.15, te1, wrap(title))], y=0.14, scale=1.25, font=p4["font"])
        add_text_track([(te0 + 0.5, te1, CTA)], y=-0.30, scale=0.8, font=p4["font"])
        print(f"  [kết] card chốt {te0:.1f}-{te1:.1f}s")
    if p4["font"] or n_st:
        print(f"  [P4] gu '{editor}': font={p4.get('font_name') or '—'} | "
              f"sticker kho={n_st} ({', '.join(p4['stickers'][:3])})")

    # SFX: AI chọn từ kho, đặt đúng giây; bin-pack vào ít track nhất (không chồng)
    atrack_src = next(t for t in dt["tracks"] if t["type"] == "audio")
    _, amat_src = cb.find_mat(dt, atrack_src["segments"][0]["material_id"])
    # SFX lấy từ KHO trước, thư mục chỉ định chỉ là nguồn phụ — máy khác không có
    # thư mục của máy dev thì vẫn phải ra được tiếng động.
    kho_sfx = assetlib.sfx_kho(sfx_path or "")
    if not kho_sfx:
        print("  [sfx] ⚠️ không có SFX nào để chèn (kho rỗng, không thấy thư mục SFX)")
    sfx_segs = []
    for s in sorted((enr.get("sfx", []) if enr else []), key=lambda x: x["sec"]):
        f = kho_sfx.get(s["file"]) or (Path(sfx_path) / s["file"] if sfx_path else None)
        o = src_to_out(s["sec"])
        if not f or not Path(f).exists() or o is None:
            continue
        f = Path(f)
        st_us = int(o * 1_000_000)
        sdur = int(probe_dur(f) * 1_000_000)
        use = min(sdur, dur_us - st_us)
        if use <= 0:
            continue
        am = copy.deepcopy(amat_src); am["id"] = cb.uid()
        am["path"] = str(f).replace("\\", "/"); am["name"] = f.name
        am["duration"] = sdur
        # QUAN TRỌNG: donor là nhạc ONLINE của CapCut. Nếu giữ nguyên music_id/category
        # thì CapCut coi cả 15 SFX là CÙNG một bài, phân giải lại về file cache của nó
        # và ĐÈ MẤT path local -> mọi SFX phát cùng 1 tiếng. Phải "địa phương hoá":
        am["type"] = "extract_music"          # dạng file local, như draft editor thật
        am["category_name"] = "local"
        am["music_id"] = str(uuid.uuid4())    # GUID riêng từng file
        for k in ("category_id", "request_id", "resource_id", "effect_id",
                  "local_material_id", "remote_url"):
            if k in am:
                am[k] = ""
        am["source_platform"] = 0
        add("audios", am)
        aseg = copy.deepcopy(atrack_src["segments"][0]); aseg["id"] = cb.uid()
        aseg["material_id"] = am["id"]; aseg["extra_material_refs"] = []
        aseg["source_timerange"] = {"start": 0, "duration": use}
        aseg["target_timerange"] = {"start": st_us, "duration": use}
        sfx_segs.append((st_us, st_us + use, aseg))
    tracks_end, tracks_segs = [], []
    for st_us, en_us, aseg in sfx_segs:
        ti = next((i for i in range(len(tracks_end)) if st_us >= tracks_end[i]), None)
        if ti is None:
            tracks_segs.append([aseg]); tracks_end.append(en_us)
        else:
            tracks_segs[ti].append(aseg); tracks_end[ti] = en_us
    for segs_ in tracks_segs:
        atrack = {k: (copy.deepcopy(v) if k != "segments" else segs_) for k, v in atrack_src.items()}
        atrack["id"] = cb.uid()
        c["tracks"].append(atrack)
    print(f"  [sfx] chèn {len(sfx_segs)} hiệu ứng / {len(tracks_segs)} track")

    dang = integrity(c)
    print(f"Tracks: {[(t['type'], len(t['segments'])) for t in c['tracks']]}")
    print(f"Materials: {sum(len(v) for v in c['materials'].values() if isinstance(v, list))} | dangling: {dang}")
    if dry or dang > 0:
        print("[DRY hoặc có lỗi] — không ghi draft.")
        return

    out = DRAFTS / c["name"]
    if (out / ".locked").exists():
        sys.exit(f"⚠️ Draft '{c['name']}' đang MỞ trong CapCut (.locked). Đóng nó trong CapCut "
                 f"(về màn hình danh sách) rồi chạy lại, HOẶC dùng --name để ghi ra draft tên khác.")
    out.mkdir(parents=True, exist_ok=True)   # ghi đè tại chỗ, không xoá thư mục (an toàn)
    (out / "draft_content.json").write_text(json.dumps(c, **cb._DUMP), encoding="utf-8")

    # draft_meta_info + draft_materials (để CapCut KHÔNG hỏi chọn lại đường dẫn)
    def dm_entry(path, metetype, d_us, w, h):
        now = int(time.time())
        return {"ai_group_type": "", "create_time": now, "duration": int(d_us), "enter_from": 0,
                "extra_info": Path(path).name, "file_Path": str(path).replace("\\", "/"),
                "height": int(h), "id": str(uuid.uuid4()), "import_time": now,
                "import_time_ms": now * 1_000_000, "item_source": 1, "material_color_tag": "",
                "md5": "", "metetype": metetype,
                "roughcut_time_range": {"duration": int(d_us), "start": 0},
                "sub_time_range": {"duration": -1, "start": -1}, "type": 0, "width": int(w)}

    regs = []
    for vm in c["materials"].get("videos", []):
        if vm.get("path"):
            regs.append(dm_entry(vm["path"], "video", vm.get("duration", dur_us),
                                 vm.get("width", 0), vm.get("height", 0)))
    for am in c["materials"].get("audios", []):
        if am.get("path"):
            regs.append(dm_entry(am["path"], "music", am.get("duration", 0), 0, 0))

    meta = json.loads((cb._duong_dan_mau(DONOR_T) / "draft_meta_info.json")
                      .read_text(encoding="utf-8", errors="replace"))
    groups = meta.get("draft_materials", []) or []
    for g in groups:
        if isinstance(g.get("value"), list):
            g["value"] = []
    g0 = next((g for g in groups if g.get("type") == 0), None)
    if g0 is None:
        g0 = {"type": 0, "value": []}; groups.insert(0, g0)
    g0["value"] = regs
    meta["draft_materials"] = groups
    meta["draft_id"] = cb.uid(); meta["draft_name"] = c["name"]
    meta["draft_fold_path"] = str(out).replace("\\", "/"); meta["tm_duration"] = dur_us
    # draft_root_path đi theo draft MẪU nên mang đường dẫn của máy làm ra nó
    # (C:\Users\Acer\...). Không gây hỏng ngay vì CapCut đọc thư mục thật, nhưng đó
    # là rác của máy khác nằm trong dữ liệu người dùng — lần thứ tư dính đúng kiểu
    # hardcode đường dẫn máy dev. Ghi đè bằng thư mục draft của máy đang chạy.
    meta["draft_root_path"] = str(cb.DRAFTS_ROOT)
    (out / "draft_meta_info.json").write_text(json.dumps(meta, **cb._DUMP), encoding="utf-8")
    print(f"\n✅ Draft CapCut: {out.name}  (mở CapCut để xem)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--only", type=int, required=True)
    ap.add_argument("--sfx", default=SFX_DEFAULT)
    ap.add_argument("--model", default="gemini-3.5-flash")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--name", default=None, help="tên draft (mặc định 1107_shortNN)")
    ap.add_argument("--editor", default="shared", help="dựng theo gu editor nào: dan/nguyen/shared")
    a = ap.parse_args()
    build(Path(a.work).resolve(), a.only, a.sfx, a.model, a.dry, a.name, a.editor)   # tuyệt đối -> CapCut không relink


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
