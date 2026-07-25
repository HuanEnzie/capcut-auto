# -*- coding: utf-8 -*-
"""
capcut_batch.py — Dựng HÀNG LOẠT CapCut draft từ 1 thư mục cha chứa nhiều folder.

Mỗi folder con = 1 project: các clip nhỏ + 1 file voice (+ tùy chọn 1 file .txt kịch bản).
-> Sinh 1 draft/folder, tên draft = <prefix><tên folder>.

Model Whisper nạp 1 lần dùng chung cho cả loạt. Lỗi folder nào chỉ skip folder đó.

CÁCH DÙNG:
  # xem trước (dry-run), không ghi:
  python capcut_batch.py "E:\\E Download\\100_folders"
  # chạy thật:
  python capcut_batch.py "E:\\E Download\\100_folders" --yes --model small
  # tùy chọn:
  python capcut_batch.py "<cha>" --yes --prefix "AUTO_" --caption template --cap-chars 18 --limit 5

Lưu ý: ĐÓNG CapCut trước khi chạy. Draft đã tồn tại sẽ được BỎ QUA (chạy lại an toàn/resume).
"""
import argparse, sys, time, traceback
from pathlib import Path
import capcut_build as cb


def has_media(folder):
    clips = [p for p in folder.iterdir() if p.suffix.lower() in cb.VIDEO_EXTS]
    voices = [p for p in folder.iterdir() if p.suffix.lower() in cb.AUDIO_EXTS]
    return clips, voices


def safe_name(name):
    bad = '<>:"/\\|?*'
    return "".join(("_" if ch in bad else ch) for ch in name).strip() or "draft"


def main():
    ap = argparse.ArgumentParser(description="Batch dựng CapCut draft từ nhiều folder.")
    ap.add_argument("parent", help="thư mục cha chứa các folder con")
    ap.add_argument("--yes", action="store_true", help="ghi thật (mặc định dry-run)")
    ap.add_argument("--model", default="small")
    ap.add_argument("--caption", default="template", choices=["template", "plain"])
    ap.add_argument("--cap-chars", type=int, default=18)
    ap.add_argument("--cap-words", type=int, default=5)
    ap.add_argument("--prefix", default="", help="tiền tố tên draft, vd 'AUTO_'")
    ap.add_argument("--keep-clip-audio", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="chỉ xử lý N folder đầu (test)")
    ap.add_argument("--overwrite", action="store_true", help="ghi đè draft trùng tên (mặc định skip)")
    a = ap.parse_args()

    parent = Path(a.parent)
    if not parent.is_dir():
        sys.exit(f"Không thấy thư mục: {parent}")

    subs = sorted([p for p in parent.iterdir() if p.is_dir()], key=lambda p: p.name)
    if a.limit:
        subs = subs[: a.limit]
    print(f"Thư mục cha : {parent}")
    print(f"Số folder   : {len(subs)}  | model={a.model} | caption={a.caption} | "
          f"{'GHI THẬT' if a.yes else 'DRY-RUN'}\n")

    ok, skipped, failed = [], [], []
    t0 = time.time()
    for i, folder in enumerate(subs, 1):
        name = a.prefix + safe_name(folder.name)
        clips, voices = has_media(folder)
        tag = f"[{i}/{len(subs)}] {folder.name}"
        if not clips or not voices:
            print(f"{tag}  -> SKIP (thiếu {'clip' if not clips else 'voice'})")
            skipped.append((folder.name, "thiếu media"))
            continue
        out_dir = cb.DRAFTS_ROOT / name
        if out_dir.exists() and not a.overwrite:
            print(f"{tag}  -> SKIP (draft '{name}' đã tồn tại)")
            skipped.append((folder.name, "đã tồn tại"))
            continue
        print(f"{tag}  ({len(clips)} clip, voice={voices[0].name})")
        try:
            if a.overwrite and out_dir.exists():
                import shutil
                shutil.rmtree(out_dir)
            cb.build(str(folder), name, a.model, a.yes, a.caption,
                     a.cap_chars, a.cap_words, None, not a.keep_clip_audio)
            ok.append(name)
        except Exception as e:
            print(f"    !! LỖI: {e}")
            traceback.print_exc()
            failed.append((folder.name, str(e)))
        print()

    dt = time.time() - t0
    print("=" * 60)
    print(f"XONG trong {dt:.0f}s | ✅ {len(ok)}  ⏭️ skip {len(skipped)}  ❌ lỗi {len(failed)}")
    if skipped:
        print("\nBỏ qua:")
        for n, r in skipped:
            print(f"  - {n}: {r}")
    if failed:
        print("\nLỗi:")
        for n, r in failed:
            print(f"  - {n}: {r}")
    if not a.yes:
        print("\n[DRY-RUN] Chưa ghi draft nào. Thêm --yes để chạy thật.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
