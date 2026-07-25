# -*- coding: utf-8 -*-
"""
ffmpeg_render.py — Render THẲNG ra MP4 (headless, không cần CapCut).
Ghép clip (khớp voice) + slide transition + voiceover + caption khắc chữ (ASS).
Look KHÁC template CapCut, nhưng tự động 100% + 1080x1920 nét thật.

  python ffmpeg_render.py "E:\\E Download\\DrStone\\1" 1 --model small
"""
import argparse, subprocess, sys
from pathlib import Path
import capcut_build as cb

W, H, FPS, TR = 1080, 1920, 30, 0.5   # canvas, fps, transition (giây)


def ass_time(ms):
    cs = int(round(ms / 10)); h = cs // 360000; cs %= 360000
    m = cs // 6000; cs %= 6000; s = cs // 100; cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(caps):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for c in caps:
        txt = c["text"].replace("\n", " ")
        ev.append(f"Dialogue: 0,{ass_time(c['start_ms'])},{ass_time(c['end_ms'])},Default,,0,0,0,,{txt}")
    return head + "\n".join(ev) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("name", nargs="?", default=None)
    ap.add_argument("--model", default="small")
    ap.add_argument("--transition", default="slideleft",
                    help="slideleft/smoothleft/circleopen/fade/zoomin...")
    a = ap.parse_args()

    folder = Path(a.folder)
    name = a.name or folder.name
    clips = sorted([p for p in folder.iterdir() if p.suffix.lower() in cb.VIDEO_EXTS],
                   key=lambda p: p.name)
    voice = next(p for p in folder.iterdir() if p.suffix.lower() in cb.AUDIO_EXTS)
    N = len(clips)
    V = cb.probe(voice)["duration_us"] / 1e6
    L = (V + (N - 1) * TR) / N          # độ dài mỗi clip để tổng (sau overlap) = V
    print(f"{N} clip, voice {V:.2f}s -> mỗi clip {L:.2f}s, transition {TR}s ({a.transition})")

    # caption (kịch bản .txt nếu có, không thì Whisper)
    sp = next(iter(folder.glob("*.txt")), None)
    caps = cb.transcribe(voice, a.model)
    if caps and sp:
        wwords = [w for cp in caps for w in cp["words"] if w["w"].strip()]
        aligned = cb.align_script(wwords, sp.read_text(encoding="utf-8").strip())
        caps = [{"text": "", "start_ms": 0, "end_ms": 0, "words": aligned}]
    caps = cb.rechunk(caps, 18, 5) if caps else []
    print(f"{len(caps)} cụm caption")

    renders = Path(__file__).parent / "renders"
    renders.mkdir(exist_ok=True)
    (renders / f"{name}.ass").write_text(build_ass(caps), encoding="utf-8")

    # filter_complex
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]
    inputs += ["-i", str(voice)]
    fc = []
    for i, c in enumerate(clips):
        native = cb.probe(c)["duration_us"] / 1e6
        factor = L / native if native else 1.0
        fc.append(f"[{i}:v]setpts={factor:.5f}*(PTS-STARTPTS),"
                  f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"setsar=1,fps={FPS},format=yuv420p[v{i}]")
    prev = "v0"
    for k in range(1, N):
        off = k * (L - TR)
        out = f"x{k}"
        fc.append(f"[{prev}][v{k}]xfade=transition={a.transition}:duration={TR}:offset={off:.4f}[{out}]")
        prev = out
    fc.append(f"[{prev}]subtitles={name}.ass[vout]")

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc),
           "-map", "[vout]", "-map", f"{N}:a", "-t", f"{V:.3f}",
           "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", f"{name}.mp4"]
    print("Đang render...")
    r = subprocess.run(cmd, cwd=renders)
    if r.returncode == 0:
        print(f"\n✅ Xong: {renders / (name + '.mp4')}")
    else:
        sys.exit("ffmpeg lỗi (xem log trên).")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
