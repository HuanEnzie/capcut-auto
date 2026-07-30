# -*- coding: utf-8 -*-
"""
transcribe.py — Giai đoạn 1: recording dài -> transcript.json (có cache).

Luồng: probe -> tách audio 16kHz mono -> faster-whisper (GPU) -> transcript.json
Mọi bước cache lại: chạy lại chỉ làm phần còn thiếu.

CÁCH DÙNG:
  python transcribe.py "E:\\E Download\\Recap\\1107.mp4"
  python transcribe.py "<video>" --model small --device cuda
  python transcribe.py "<video>" --model medium        # chuẩn hơn, chậm hơn

Đầu ra trong: shorts/work/<ten-file>/
  audio.wav               (16kHz mono)
  transcript.<model>.json (segments + words + timestamp)   ← CACHE
  transcript.<model>.txt  (đọc được, có [mm:ss])
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from cuda_setup import enable_cuda

# assetlib.ROOT (không phải __file__) — đóng gói .exe thì __file__ trỏ vào bên trong
# gói nội bộ, ghi transcript cache vào đó là mất khi cập nhật bản mới. Import muộn
# (không phải ở đầu file như thường lệ) để giữ đúng thứ tự bootstrap: script này còn
# chạy độc lập (`python transcribe.py ...`) trước khi shorts/ được thêm vào sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import assetlib

WORK_ROOT = assetlib.ROOT / "shorts" / "work"

# Trần luồng cho CTranslate2 — xem đo đạc trong _luong_cpu(). Vượt trần là sập cứng
# (stack overflow trong ctranslate2.dll), không phải chậm đi.
TRAN_LUONG = 4


def slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", Path(name).stem).strip("_")
    return s or "recording"


TOC_DO = WORK_ROOT / "toc_do_asr.json"


def ghi_toc_do(rtf: float, model_name: str, device: str) -> None:
    """Nhớ tốc độ bóc lời ĐO ĐƯỢC TRÊN MÁY NÀY, để giao diện ước lượng bằng số thật."""
    if rtf and rtf > 0:
        try:
            WORK_ROOT.mkdir(parents=True, exist_ok=True)
            TOC_DO.write_text(json.dumps(
                {"realtime_factor": rtf, "model": model_name, "device": device},
                ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass                                # ước lượng đẹp hơn không đáng để gãy build


def toc_do_asr() -> tuple:
    """(hệ số realtime, có phải số đo thật của máy này không).

    Chưa chạy lần nào thì đoán DÈ DẶT. Thà báo lâu hơn thực tế còn hơn hứa 2 phút rồi
    bắt người ta ngồi 4 phút — con số cũ (30x) là đo trên GPU máy dev, máy chạy CPU
    thấp hơn nhiều lần."""
    try:
        d = json.loads(TOC_DO.read_text(encoding="utf-8"))
        if d.get("realtime_factor", 0) > 0:
            return float(d["realtime_factor"]), True
    except (OSError, ValueError):
        pass
    return 10.0, False


class NguonKhongKhop(RuntimeError):
    """Thư mục làm việc đang giữ cache của MỘT record KHÁC.

    Có lớp riêng để tầng trên báo đúng nguyên nhân, vì hậu quả rất khó nhận ra:
    không crash, không lỗi, chỉ ra draft trộn nội dung hai record."""


def _khoa_nguon(source: str, d: Path) -> None:
    """Ghi/đối chiếu danh tính record của thư mục làm việc.

    VÌ SAO CẦN: `slug()` chỉ lấy TÊN file, bỏ hết đường dẫn — hai record khác nhau
    cùng tên 'test.mp4' dùng chung một thư mục. Mọi cache trong đó (audio.wav,
    transcript, reframe) lại tái dùng chỉ vì file tồn tại, nên record mới lặng lẽ
    thừa hưởng dữ liệu của record cũ và draft dựng ra bị TRỘN. Đổi cách đặt tên thư
    mục thì hỏng mọi draft cũ (draft giữ đường dẫn tuyệt đối vào đây), nên thay vì
    đổi tên, ta đặt một cửa kiểm.

    Định danh lấy theo KÍCH THƯỚC BYTE chứ không theo đường dẫn: người dùng dời hay
    đổi tên thư mục chứa record là chuyện thường, còn hai record khác nhau trùng
    kích thước tới từng byte thì gần như không xảy ra.
    """
    p = Path(source)
    try:
        cn = {"path": str(p.resolve()).replace("\\", "/"), "size": p.stat().st_size}
    except OSError:
        return                                  # nguồn không đọc được: để tầng trên báo
    f = d / "nguon.json"
    if not f.exists():
        # Thư mục có sẵn cache từ trước mà chưa có dấu -> nhận luôn record này làm chủ.
        f.write_text(json.dumps(cn, ensure_ascii=False), encoding="utf-8")
        return
    try:
        cu = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        f.write_text(json.dumps(cn, ensure_ascii=False), encoding="utf-8")
        return
    if cu.get("size") == cn["size"]:
        if cu.get("path") != cn["path"]:        # cùng file, chỉ dời chỗ -> cập nhật im lặng
            f.write_text(json.dumps(cn, ensure_ascii=False), encoding="utf-8")
        return
    raise NguonKhongKhop(
        f"Thư mục làm việc '{d.name}' đang giữ dữ liệu của một record KHÁC.\n"
        f"  đang có : {cu.get('path')}  ({cu.get('size'):,} byte)\n"
        f"  bạn đưa : {cn['path']}  ({cn['size']:,} byte)\n"
        f"Hai file trùng tên nên dùng chung thư mục — chạy tiếp sẽ ra draft TRỘN nội "
        f"dung hai record. Cách xử lý: đổi tên file record cho khác đi, hoặc xoá thư "
        f"mục '{d}' nếu không cần dữ liệu cũ.")


def work_dir(source: str, ten: str = "") -> Path:
    """Thư mục làm việc. `ten` để CALLER tự đặt tên thay vì suy từ tên file.

    Cần vì một record có thể được dựng ở NHIỀU dự án, mỗi dự án phải phân tích lại
    từ đầu — dùng chung thư mục thì dự án thứ hai thừa hưởng luôn chủ đề và cache của
    dự án thứ nhất, tức là chẳng làm lại gì cả."""
    d = WORK_ROOT / (ten or slug(source))
    d.mkdir(parents=True, exist_ok=True)
    _khoa_nguon(source, d)
    return d


def probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def extract_audio(source: str, wav: Path) -> Path:
    """Tách audio -> 16kHz mono wav (chuẩn cho whisper). Cache."""
    if wav.exists() and wav.stat().st_size > 0:
        print(f"  [audio] dùng cache: {wav.name}")
        return wav
    print("  [audio] tách audio 16kHz mono...")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source), "-vn",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
        check=True, capture_output=True)
    return wav


def fmt_ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


# Windows không cho tạo symlink nếu chưa bật Developer Mode / không chạy admin ->
# huggingface_hub NÉM LỖI khi tải model Whisper lần đầu (WinError 1314), tức app
# chết ngay lần chạy đầu trên máy mới. Máy dev không lộ vì model đã nằm sẵn trong
# cache. Ép hub chép file thay vì tạo symlink.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _luong_cpu() -> int:
    """Số luồng cho CTranslate2 — mặc định là SỐ NHÂN THẬT, không phải số luồng
    luận lý. Đo trên máy 8 luồng / 4 nhân (file 8 phút, batched):

        small  4 luồng 58,8s   |  8 luồng 71,2s   (chậm hơn 21%)
        base   4 luồng 21,3s   |  8 luồng 25,0s   (chậm hơn 17%)
        tiny   4 luồng 12,8s   |  8 luồng 14,2s   (chậm hơn 11%)

    Nhồi thêm luồng vào batched inference là hại, không lợi. Đặt CT2_THREADS để đè.

    TRẦN 4 LUỒNG — đo 27/07/2026 trên máy trạm i7-12700 (12 nhân / 20 luồng), file
    58 phút, model small, batched + VAD:

        9 luồng  -> SẬP: python.exe chết trong ctranslate2.dll, 0xC00000FD
                    (stack overflow). File 5 phút thì thoát, từ 10 phút là sập.
        4 luồng  -> chạy trọn, 230s (15,0x realtime)   ← nhanh nhất
        1 luồng  -> chạy trọn, 474s (7,3x realtime)

    Nên trần này KHÔNG đánh đổi tốc độ lấy ổn định: cấu hình cũ vừa sập vừa chậm hơn.
    Máy dev (4 nhân / 8 luồng) vẫn ra 3 như trước, trần không đụng tới.

    Công thức cũ `cpu_count()//2 - 1` tự nhận là "số nhân thật", nhưng chỉ đúng khi
    MỌI nhân đều siêu phân luồng. CPU nhân lai (P-core có HT + E-core không HT) phá
    giả định đó: 12 nhân thật mà ra 9. Đó là lý do lỗi chỉ lộ trên máy thứ hai.
    """
    v = os.environ.get("CT2_THREADS")
    if v and v.isdigit() and int(v) > 0:
        return int(v)
    try:
        import multiprocessing as mp
        # CHỪA LẠI MỘT NHÂN cho web server. Ăn hết nhân thật thì uvicorn không kịp
        # trả lời /api/jobs, trình duyệt tưởng mất kết nối trong lúc đang bóc lời —
        # đúng lúc người dùng nhìn chằm chằm vào thanh tiến trình.
        return max(1, min(TRAN_LUONG, mp.cpu_count() // 2 - 1))
    except (ImportError, NotImplementedError):
        return 3


def transcribe(source: str, model_name: str = "small", device: str = "cuda",
               ten: str = "") -> dict:
    wd = work_dir(source, ten)
    cache = wd / f"transcript.{model_name}.json"
    if cache.exists():
        print(f"  [asr] dùng cache: {cache.name}")
        return json.loads(cache.read_text(encoding="utf-8"))

    wav = extract_audio(source, wd / "audio.wav")
    dur = probe_duration(source)

    if device == "cuda":
        enable_cuda()
    from faster_whisper import WhisperModel

    print(f"  [asr] nạp model '{model_name}' trên {device}...")
    ct = "int8_float16" if device == "cuda" else "int8"
    try:
        model = WhisperModel(model_name, device=device, compute_type=ct,
                             cpu_threads=_luong_cpu())
    except Exception as e:
        print(f"  [asr] {device} lỗi ({e}); chuyển sang CPU")
        device, ct = "cpu", "int8"
        model = WhisperModel(model_name, device=device, compute_type=ct,
                             cpu_threads=_luong_cpu())

    print(f"  [asr] transcribe {fmt_ts(dur)} (word-timestamps, VAD)...")
    t0 = time.time()
    segments, info = model.transcribe(
        str(wav), language="vi", word_timestamps=True, vad_filter=True)

    seg_list = []
    for seg in segments:
        words = [{"w": w.word, "start": round(w.start, 3), "end": round(w.end, 3)}
                 for w in (seg.words or [])]
        seg_list.append({"id": len(seg_list), "start": round(seg.start, 3),
                         "end": round(seg.end, 3), "text": seg.text.strip(), "words": words})
        if len(seg_list) % 50 == 0:
            print(f"      {len(seg_list)} segment... ({fmt_ts(seg.end)}/{fmt_ts(dur)})")

    dt = time.time() - t0
    data = {
        "source": str(source), "duration_sec": round(dur, 1),
        "language": info.language, "language_prob": round(info.language_probability, 3),
        "model": model_name, "device": device,
        "n_segments": len(seg_list),
        "transcribe_sec": round(dt, 1),
        "realtime_factor": round(dur / dt, 1) if dt else 0,
        "segments": seg_list,
    }
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # bản đọc được
    txt = wd / f"transcript.{model_name}.txt"
    with open(txt, "w", encoding="utf-8") as f:
        for s in seg_list:
            f.write(f"[{fmt_ts(s['start'])}] {s['text']}\n")

    print(f"  [asr] XONG: {len(seg_list)} segment trong {fmt_ts(dt)} "
          f"({data['realtime_factor']}x realtime)")
    print(f"        -> {cache}")
    print(f"        -> {txt}")
    return data


# ══════════ HAI TẦNG: khảo sát nhanh cả file → bóc kỹ riêng đoạn được chọn ══════════
# Lý do: mặc định của faster-whisper rất đắt (beam 5, best_of 5, 6 mức temperature
# fallback, condition_on_previous_text=True gây trôi/lặp trên file dài → kích hoạt
# fallback). Đo thực tế: GPU chỉ dùng 1.4/4 GB, utilization 51-87% -> GPU bị BỎ ĐÓI,
# không phải nghẽn tính toán. Tầng 1 bật batched + greedy để nhồi GPU; tầng 2 mới
# xài cấu hình đắt tiền, nhưng chỉ trên 1-3 phút audio.

def transcribe_survey(source: str, model_name: str = "small", device: str = "cuda",
                      ten: str = "") -> dict:
    """TẦNG 1 — khảo sát cả file, chỉ cần đủ tốt để Gemini tìm chủ đề.
    Không lấy mốc từng từ (đắt, chỉ caption cuối mới cần)."""
    wd = work_dir(source, ten)
    cache = wd / "transcript.survey.json"
    if cache.exists():
        print("  [asr-survey] dùng cache")
        return json.loads(cache.read_text(encoding="utf-8"))

    wav = extract_audio(source, wd / "audio.wav")
    dur = probe_duration(source)
    if device == "cuda":
        enable_cuda()
    from faster_whisper import WhisperModel, BatchedInferencePipeline

    ct = "int8_float16" if device == "cuda" else "int8"
    try:
        base = WhisperModel(model_name, device=device, compute_type=ct, cpu_threads=_luong_cpu())
    except Exception as e:
        print(f"  [asr-survey] {device} lỗi ({e}); chuyển CPU")
        device, ct = "cpu", "int8"
        base = WhisperModel(model_name, device=device, compute_type=ct, cpu_threads=_luong_cpu())
    model = BatchedInferencePipeline(model=base)

    print(f"  [asr-survey] khảo sát {fmt_ts(dur)} — batched, greedy, không mốc từ...")
    t0 = time.time()
    segments, info = model.transcribe(
        str(wav), language="vi", batch_size=16, beam_size=1,
        condition_on_previous_text=False, temperature=0.0,
        word_timestamps=False, vad_filter=True)

    seg_list = []
    for seg in segments:
        seg_list.append({"id": len(seg_list), "start": round(seg.start, 3),
                         "end": round(seg.end, 3), "text": seg.text.strip(), "words": []})
        if len(seg_list) % 100 == 0:
            print(f"      {len(seg_list)} segment... ({fmt_ts(seg.end)}/{fmt_ts(dur)})")

    dt = time.time() - t0
    data = {"source": str(source), "duration_sec": round(dur, 1), "language": info.language,
            "model": model_name, "device": device, "pass": "survey",
            "n_segments": len(seg_list), "transcribe_sec": round(dt, 1),
            "realtime_factor": round(dur / dt, 1) if dt else 0, "segments": seg_list}
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    ghi_toc_do(data["realtime_factor"], model_name, device)
    print(f"  [asr-survey] XONG {len(seg_list)} segment trong {fmt_ts(dt)} "
          f"({data['realtime_factor']}x realtime)")
    return data


def refine_range(source: str, t0: float, t1: float, model_name: str = "medium",
                 device: str = "cuda", pad: float = 8.0, ten: str = "") -> dict:
    """TẦNG 2 — bóc KỸ chỉ đoạn [t0,t1] (model to + mốc từng từ + beam 5),
    rồi trộn vào transcript.fine.json. Mốc thời gian giữ TUYỆT ĐỐI theo file gốc."""
    wd = work_dir(source, ten)
    fine_p = wd / "transcript.fine.json"
    a, b = max(0.0, t0 - pad), t1 + pad

    fine = json.loads(fine_p.read_text(encoding="utf-8")) if fine_p.exists() else None
    if fine:
        done = fine.get("refined", [])
        if any(x[0] <= a and b <= x[1] for x in done):
            print(f"  [asr-fine] đoạn {int(a)}-{int(b)}s đã bóc kỹ, dùng cache")
            return fine

    survey = transcribe_survey(source, "small", device)
    wav = extract_audio(source, wd / "audio.wav")
    if device == "cuda":
        enable_cuda()
    from faster_whisper import WhisperModel

    ct = "int8_float16" if device == "cuda" else "int8"
    try:
        m = WhisperModel(model_name, device=device, compute_type=ct)
    except Exception as e:
        print(f"  [asr-fine] {model_name}/{device} lỗi ({e}); lùi về small/cpu")
        model_name, device, ct = "small", "cpu", "int8"
        m = WhisperModel(model_name, device=device, compute_type=ct)

    print(f"  [asr-fine] bóc kỹ {fmt_ts(a)}-{fmt_ts(b)} bằng '{model_name}' (có mốc từ)...")
    ts = time.time()
    segments, _ = m.transcribe(str(wav), language="vi", word_timestamps=True,
                               vad_filter=True, beam_size=5,
                               clip_timestamps=[a, b])
    fine_segs = []
    for seg in segments:
        words = [{"w": w.word, "start": round(w.start, 3), "end": round(w.end, 3)}
                 for w in (seg.words or [])]
        fine_segs.append({"start": round(seg.start, 3), "end": round(seg.end, 3),
                          "text": seg.text.strip(), "words": words})
    print(f"  [asr-fine] {len(fine_segs)} segment trong {time.time() - ts:.0f}s")

    # trộn: giữ segment khảo sát NGOÀI khoảng, thay bằng bản kỹ TRONG khoảng
    base_segs = (fine or survey)["segments"]
    merged = [s for s in base_segs if s["end"] <= a or s["start"] >= b] + fine_segs
    merged.sort(key=lambda s: s["start"])
    for i, s in enumerate(merged):
        s["id"] = i

    out = dict(survey)
    out["segments"] = merged
    out["n_segments"] = len(merged)
    out["pass"] = "fine"
    out["refined"] = (fine.get("refined", []) if fine else []) + [[a, b]]
    fine_p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def load_transcript(work: Path, prefer_fine=True) -> dict:
    """Nạp transcript phù hợp: ưu tiên bản bóc kỹ, rồi bản cũ đầy đủ, cuối cùng bản khảo sát."""
    order = ["transcript.fine.json"] if prefer_fine else []
    legacy = sorted(p for p in work.glob("transcript.*.json")
                    if p.name not in ("transcript.fine.json", "transcript.survey.json"))
    order += [p.name for p in legacy] + ["transcript.survey.json"]
    for name in order:
        p = work / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Không có transcript nào trong {work}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--model", default="small", help="tiny/base/small/medium/large-v3")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    a = ap.parse_args()
    if not Path(a.source).exists():
        sys.exit(f"Không thấy file: {a.source}")
    print(f"Nguồn: {a.source}")
    transcribe(a.source, a.model, a.device)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
