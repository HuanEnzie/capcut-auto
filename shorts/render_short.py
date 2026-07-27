# -*- coding: utf-8 -*-
"""
render_short.py — Giai đoạn 3 (bản MP4): topics.json -> các short 9:16.

Mỗi chủ đề: cắt các đoạn từ recording gốc -> reframe 9:16 (nền mờ + video giữa)
-> caption (từ transcript) + băng tiêu đề trên -> MP4.

- Snap điểm cắt về ranh giới CÂU lấy từ transcript (không tin thẳng số LLM).
- Caption remap về timeline output.
- Gộp nhiều đoạn rời cùng chủ đề (concat).

CÁCH DÙNG:
  python render_short.py work/1107                # render tất cả chủ đề
  python render_short.py work/1107 --only 4       # chỉ chủ đề số 4
  python render_short.py work/1107 --pad 0.3 --transition 0.4
"""
import argparse, json, os, re, subprocess, sys
from pathlib import Path

from caption_fix import fix_captions

W, H, FPS = 1080, 1920, 30


def slug(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s).strip().replace(" ", "_")
    return (s[:40] or "short")


def ass_time(sec: float) -> str:
    cs = max(0, int(round(sec * 100))); h = cs // 360000; cs %= 360000
    m = cs // 6000; cs %= 6000; s = cs // 100; cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _gap_after(i: int, segs: list) -> float:
    return (segs[i + 1]["start"] - segs[i]["end"]) if i + 1 < len(segs) else 999.0


def snap(s0: float, s1: float, segs: list, window: float = 4.0) -> tuple:
    """Snap biên cắt về KHOẢNG LẶNG tự nhiên gần nhất (tránh cắt giữa câu).
    - END: mở rộng tới segment-end có khoảng lặng sau lớn nhất trong [s1-1, s1+window].
    - START: lùi về segment-start có khoảng lặng trước lớn nhất trong [s0-window, s0+1]."""
    n = len(segs)
    end_i = min(range(n), key=lambda i: abs(segs[i]["end"] - s1))
    best = -1.0
    for i in range(n):
        e = segs[i]["end"]
        if s1 - 1.0 <= e <= s1 + window:
            g = _gap_after(i, segs)
            if g > best:
                best, end_i = g, i
    start_i = min(range(n), key=lambda i: abs(segs[i]["start"] - s0))
    best = -1.0
    for i in range(n):
        st = segs[i]["start"]
        if s0 - window <= st <= s0 + 1.0:
            g = _gap_after(i - 1, segs) if i > 0 else 999.0
            if g > best:
                best, start_i = g, i
    start, end = segs[start_i]["start"], segs[end_i]["end"]
    if end <= start:
        end = s1
    return start, end


def tighten_cuts(cuts: list, segs: list, max_gap: float = 0.8, keep: float = 0.15,
                 max_pieces: int = 80) -> tuple:
    """Bỏ các khoảng LẶNG dài trong từng đoạn cắt -> nhịp gọn, không bị 'chết' vài giây.

    Tách 1 đoạn thành nhiều đoạn nhỏ nhảy qua chỗ im. Pipeline vốn đã nối nhiều cut và
    remap thời gian bằng src_to_out(), nên caption/SFX/emoji/B-roll tự khớp lại theo.
    Giữ lại `keep` giây ở hai mép cho đỡ cụt hơi (jump-cut nghe gắt).
    Trả (cuts_mới, số_khoảng_bỏ, tổng_giây_rút_gọn)."""
    out, n_gaps, saved = [], 0, 0.0
    for (c0, c1) in cuts:
        inside = [s for s in segs if s["end"] > c0 and s["start"] < c1]
        inside.sort(key=lambda s: s["start"])
        if not inside:
            out.append((c0, c1))
            continue
        start = c0
        for i in range(len(inside) - 1):
            gap = inside[i + 1]["start"] - inside[i]["end"]
            if gap <= max_gap:
                continue
            end = min(c1, inside[i]["end"] + keep)
            if end > start + 0.25:
                out.append((start, end))
                n_gaps += 1
                saved += gap - 2 * keep
            start = max(c0, inside[i + 1]["start"] - keep)
        if c1 > start + 0.25:
            out.append((start, c1))
    # quá vụn thì ffmpeg phải render/nối rất nhiều mảnh -> nới ngưỡng cho đỡ chậm
    if len(out) > max_pieces and max_gap < 3.0:
        return tighten_cuts(cuts, segs, max_gap + 0.5, keep, max_pieces)
    return out, n_gaps, saved


def khoa_cap(seg) -> str:
    """Khoá caption theo MỐC BẮT ĐẦU (mili-giây), KHÔNG theo id segment.

    LỖI ĐÃ TRẢ GIÁ 27/07: captions_fixed.json khoá theo `seg["id"]`, mà refine_range
    ĐÁNH SỐ LẠI TOÀN BỘ id mỗi lần trộn transcript. Sau một lượt làm sạch ghi lại
    transcript.fine.json, id đổi hết -> chữ đã sửa của một segment dài 30 giây (400 ký
    tự) bị gán vào segment 0,5 giây. split_cue chia 400 ký tự đó thành ~20 dòng, mỗi
    dòng được 0,05 GIÂY: caption nhấp nháy 20 lần/giây, không đọc nổi.
    Mốc thời gian thì không đổi khi trộn lại — đó mới là định danh đúng."""
    return str(int(round(seg["start"] * 1000)))


def captions_for_cuts(cuts: list, segs: list, fixed: dict = None) -> list:
    """Trả về [(out_start, out_end, text)] theo timeline output; dùng caption đã sửa nếu có."""
    fixed = fixed or {}
    cues, offset = [], 0.0
    for (c0, c1) in cuts:
        for seg in segs:
            if seg["end"] <= c0 or seg["start"] >= c1:
                continue
            st = max(seg["start"], c0) - c0 + offset
            en = min(seg["end"], c1) - c0 + offset
            # Ưu tiên chữ ĐÃ SẠCH nằm ngay trong segment (lam_sach_toan_bo ghi thẳng
            # vào `text`, giữ bản thô ở `text_goc`) — đó là nguồn không thể lệch.
            txt = (seg["text"] if seg.get("text_goc") is not None
                   else fixed.get(khoa_cap(seg), seg["text"])).strip()
            if txt and en > st:
                cues.append((st, en, txt))
        offset += (c1 - c0)
    return cues


def build_ass(title: str, cues: list) -> str:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Arial,72,&H0000E5FF,&H0000E5FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,5,0,8,80,80,120,1
Style: Cap,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    total = cues[-1][1] if cues else 0
    # tiêu đề hiện suốt clip, băng trên
    ev.append(f"Dialogue: 0,{ass_time(0)},{ass_time(total)},Title,,0,0,0,,{title}")
    for st, en, tx in cues:
        ev.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Cap,,0,0,0,,{tx}")
    return head + "\n".join(ev) + "\n"


def has_video(src: str) -> bool:
    """Nguồn có luồng hình không? (record dạng .mp3 thì không -> phải dựng audiogram)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True).stdout.strip()
    return out.startswith("video")


def audiogram_cut(src: str, c0: float, dur: float, out: Path):
    """Nguồn CHỈ CÓ TIẾNG (podcast/ghi âm họp) -> dựng khung 9:16:
    nền gradient tối + sóng âm chạy giữa khung. Caption/sticker/B-roll do CapCut chồng lên sau."""
    wh = 420
    tmp = out.with_suffix(".wave.mp4")
    # PASS 1 — vẽ sóng ra file riêng.
    # Ghép showwaves thẳng trong 1 filtergraph (overlay/blend) bị mất tín hiệu sóng;
    # tách 2 pass thì chắc chắn chạy. Giọng nói rất nhỏ (~-30 LUFS) nên phải
    # khuếch đại + thang sqrt, để thang tuyến tính mặc định thì sóng phẳng lì.
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{c0:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
         "-filter_complex",
         f"[0:a]aformat=channel_layouts=mono,volume=14,"
         f"showwaves=s={W}x{wh}:mode=cline:scale=sqrt:colors=0xffffff:rate={FPS},"
         f"format=yuv420p[v]",
         "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", str(tmp)],
        check=True, capture_output=True)
    # PASS 2 — nền gradient chuyển động + chồng sóng (blend screen trong RGB:
    # nền đen của sóng tự trong suốt; blend trong YUV sẽ loạn màu).
    fc = (
        f"gradients=s={W}x{H}:c0=0x0b1220:c1=0x1e3a5f:c2=0x0d1117:"
        f"speed=0.008:d={dur:.3f}:r={FPS},format=gbrp[bg];"
        f"[1:v]pad={W}:{H}:0:{int((H - wh) / 2)}:black,format=gbrp[wv];"
        f"[bg][wv]blend=all_mode=screen:shortest=1,setsar=1,format=yuv420p[v]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{c0:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
         "-i", str(tmp), "-filter_complex", fc, "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(out)],
        check=True, capture_output=True)
    try:
        tmp.unlink()
    except OSError:
        pass


def reframe_cut(src: str, c0: float, dur: float, out: Path):
    """Cắt 1 đoạn + reframe 9:16 nền mờ + video giữa. Nguồn chỉ có tiếng -> audiogram."""
    if not has_video(src):
        return audiogram_cut(src, c0, dur, out)
    fc = (f"[0:v]split[a][b];"
          f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2[bg];"
          f"[b]scale={W}:-2[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS},format=yuv420p[v]")
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{c0:.3f}", "-i", src, "-t", f"{dur:.3f}",
         "-filter_complex", fc, "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(out)],
        check=True, capture_output=True)


def append_tail(base: Path, dur: float = 2.4, fade: float = 0.8) -> float:
    """Nối ĐUÔI KẾT vào cuối video nền: giữ khung hình cuối + tối dần, tiếng im.

    Short cắt đúng lúc dứt lời nghe rất cụt ('hụt hẫng'). Có đuôi này thì vừa có chỗ
    thở, vừa có nền để đặt card chốt/CTA. Trả về số giây đã nối thêm (0 nếu lỗi)."""
    tmp = base.parent / f".tail_{base.stem}"
    tmp.mkdir(exist_ok=True)
    png, tail, merged = tmp / "last.png", tmp / "tail.mp4", tmp / "merged.mp4"
    try:
        subprocess.run(["ffmpeg", "-y", "-sseof", "-0.5", "-i", str(base),
                        "-frames:v", "1", "-q:v", "2", str(png)],
                       check=True, capture_output=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-t", f"{dur:.2f}", "-i", str(png),
             "-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo",
             "-vf", f"scale={W}:{H},setsar=1,fps={FPS},"
                    f"fade=t=out:st={max(0, dur - fade):.2f}:d={fade:.2f},format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-shortest", str(tail)],
            check=True, capture_output=True)
        lst = tmp / "l.txt"
        lst.write_text(f"file '{base.resolve().as_posix()}'\nfile '{tail.resolve().as_posix()}'\n",
                       encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", str(merged)], check=True, capture_output=True)
        merged.replace(base)
        return dur
    except subprocess.CalledProcessError:
        return 0.0
    finally:
        for f in (png, tail):
            try:
                f.unlink()
            except OSError:
                pass


def render_topic(idx: int, topic: dict, transcript: dict, src: str, outdir: Path, pad: float,
                 fixed: dict = None):
    segs = transcript["segments"]
    cuts = []
    for s in topic["segments"]:
        a, b = snap(s["start_sec"], s["end_sec"], segs)
        a = max(0, a - pad); b = min(transcript["duration_sec"], b + pad)
        cuts.append((a, b))
    name = f"{idx:02d}_{slug(topic['title'])}"
    tmpdir = outdir / f".tmp_{idx}"; tmpdir.mkdir(parents=True, exist_ok=True)

    parts = []
    for j, (c0, c1) in enumerate(cuts):
        p = tmpdir / f"part{j}.mp4"
        reframe_cut(src, c0, c1 - c0, p)
        parts.append(p)

    # concat (nếu nhiều đoạn)
    body = tmpdir / "body.mp4"
    if len(parts) == 1:
        body = parts[0]
    else:
        lst = tmpdir / "list.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", str(body)], check=True, capture_output=True, cwd=tmpdir)

    # caption + tiêu đề (ASS)
    cues = captions_for_cuts(cuts, segs, fixed)
    ass = tmpdir / "cap.ass"
    ass.write_text(build_ass(topic["title"], cues), encoding="utf-8")
    out = outdir / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-y", "-i", body.name, "-vf", f"ass={ass.name}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-c:a", "copy", str(Path("..") / out.name)],
                   check=True, capture_output=True, cwd=tmpdir)

    dur = sum(c1 - c0 for c0, c1 in cuts)
    print(f"  ✅ #{idx} {out.name}  ({dur:.0f}s, {len(cuts)} đoạn, {len(cues)} caption)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--only", type=int, default=0, help="chỉ render chủ đề số N (1-based)")
    ap.add_argument("--pad", type=float, default=0.4, help="đệm trước/sau mỗi đoạn (giây)")
    ap.add_argument("--model", default="gemini-3.5-flash", help="model Gemini để sửa caption")
    ap.add_argument("--raw-caption", action="store_true", help="KHÔNG sửa caption (dùng text whisper thô)")
    a = ap.parse_args()

    work = Path(a.work)
    topics = json.loads((work / "topics.json").read_text(encoding="utf-8"))
    from transcribe import load_transcript
    transcript = load_transcript(work)
    src = transcript["source"]
    outdir = work / "shorts"; outdir.mkdir(exist_ok=True)

    fixed = {} if a.raw_caption else fix_captions(work, a.model)

    tops = topics["topics"]
    print(f"Nguồn: {src}\n{len(tops)} chủ đề -> {outdir}\n")
    for i, t in enumerate(tops, 1):
        if a.only and i != a.only:
            continue
        render_topic(i, t, transcript, src, outdir, a.pad, fixed)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
