# -*- coding: utf-8 -*-
"""audio_balance.py — Tự cân bằng âm lượng cho draft CapCut theo chuẩn EBU R128 / LUFS.

Nguyên tắc (xem docs/APP_DESIGN.md mục 4):
  - Đo bằng LUFS (ITU-R BS.1770) chứ không dùng peak thô, vì LUFS bám cảm nhận tai người.
  - Giọng nói = mốc neo -14 LUFS (chuẩn nền tảng short: TikTok/YouTube/Reels).
  - SFX đặt hơi dưới giọng để nhấn mà không giật mình.
  - Nhạc nền phải thấp hơn giọng ~16 dB (nghiên cứu speech intelligibility: SNR ~+15 dB
    là nghe rõ gần tối đa; nghe điện thoại môi trường ồn nên chọn cận trên).

KHÔNG re-encode — chỉ ghi `volume` (hệ số nhân tuyến tính) vào draft, giữ nguyên
khả năng chỉnh tay trong CapCut.

  python audio_balance.py 1107_short04_v6 --dry
  python audio_balance.py 1107_short04_v6
"""
import argparse, json, math, re, shutil, subprocess, sys, time
from pathlib import Path

import assetlib

# ---- mục tiêu (dB LUFS) — chỉnh ở đây là đổi toàn bộ gu trộn tiếng ----
TARGET = {
    "voice": -14.0,   # giọng nói: mốc neo
    "sfx":   -16.0,   # hiệu ứng: dưới giọng 2 dB
    "music": -30.0,   # nhạc nền khi có giọng: dưới giọng ~16 dB
    "broll": -20.0,   # b-roll còn tiếng: lùi hẳn sau giọng
}
VOL_MAX = 10.0        # CapCut chặn hệ số nhân ở 10x (~ +20 dB)
DRAFT_ROOT = assetlib.draft_root()      # dò từ chính cấu hình CapCut trên máy đang chạy


def db_to_vol(gain_db: float) -> float:
    """dB -> hệ số nhân tuyến tính của CapCut. volume = 10^(dB/20)."""
    return max(0.0, min(VOL_MAX, 10 ** (gain_db / 20.0)))


def vol_to_db(v: float) -> float:
    return 20 * math.log10(v) if v > 0 else -120.0


# ---------------- đo LUFS ----------------

def _lufs_cache_get(key):
    c = assetlib.conn()
    c.execute("CREATE TABLE IF NOT EXISTS lufs(k TEXT PRIMARY KEY, i REAL, tp REAL, dur REAL, ts REAL)")
    r = c.execute("SELECT * FROM lufs WHERE k=?", (key,)).fetchone()
    c.close()
    return dict(r) if r else None


def _lufs_cache_put(key, i, tp, dur):
    c = assetlib.conn()
    c.execute("CREATE TABLE IF NOT EXISTS lufs(k TEXT PRIMARY KEY, i REAL, tp REAL, dur REAL, ts REAL)")
    c.execute("INSERT OR REPLACE INTO lufs VALUES(?,?,?,?,?)", (key, i, tp, dur, time.time()))
    c.commit()
    c.close()


def measure(path: Path) -> dict | None:
    """Đo độ to tích hợp (LUFS) + true peak của 1 file. Có cache trong library.db.

    File ngắn (SFX vài trăm ms) thì LUFS tích hợp không đáng tin do cơ chế gating của
    R128 -> rơi về đo mức trung bình/đỉnh bằng volumedetect."""
    p = Path(path)
    if not p.exists():
        return None
    key = f"{p}|{p.stat().st_mtime_ns}|{p.stat().st_size}"
    hit = _lufs_cache_get(key)
    if hit:
        return hit

    def run(args):
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                              errors="replace").stderr or ""

    out = run(["ffmpeg", "-hide_banner", "-i", str(p), "-af",
               "loudnorm=I=-14:TP=-1:print_format=json", "-f", "null", "-"])
    i = tp = None
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", out, re.S)
    if m:
        try:
            j = json.loads(m.group(0))
            i = float(j.get("input_i"))
            tp = float(j.get("input_tp"))
        except (ValueError, TypeError):
            i = tp = None
    # không đo được (file quá ngắn / im lặng) -> dùng mean/max volume
    if i is None or not math.isfinite(i) or i < -60:
        out2 = run(["ffmpeg", "-hide_banner", "-i", str(p), "-af", "volumedetect", "-f", "null", "-"])
        mm = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", out2)
        mx = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", out2)
        if mm:
            # mean_volume là RMS thô; xấp xỉ LUFS bằng cách bù ~ -3 dB
            i = float(mm.group(1)) - 3.0
        if mx:
            tp = float(mx.group(1))
    if i is None:
        return None
    dur = 0.0
    md = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if md:
        dur = int(md.group(1)) * 3600 + int(md.group(2)) * 60 + float(md.group(3))
    _lufs_cache_put(key, i, tp if tp is not None else -1.0, dur)
    return {"i": i, "tp": tp if tp is not None else -1.0, "dur": dur}


# ---------------- phân loại & cân bằng ----------------

def plan_gain(meas: dict, role: str) -> float:
    """Độ khuếch đại cần thiết (dB) cho 1 nguồn, ĐÃ chặn trần true peak -1 dBTP.
    Dùng chung cho cả lúc ghi vào draft lẫn lúc hiển thị báo cáo — tránh 2 nơi tính lệch."""
    gain = TARGET[role] - meas["i"]
    tp = meas.get("tp")
    if tp is not None and tp > -50:
        gain = min(gain, -1.0 - tp)
    return gain


def classify(seg_kind: str, mat: dict, is_main_video: bool) -> str:
    """Đoán vai trò của 1 nguồn tiếng để chọn mục tiêu LUFS."""
    name = (mat.get("name") or mat.get("material_name") or "").lower()
    path = (mat.get("path") or "").lower()
    if seg_kind == "video":
        if is_main_video:
            return "voice"
        return "broll"
    if any(k in path or k in name for k in ("music", "nhac", "bgm", "beat")):
        return "music"
    return "sfx"


def balance(draft: str, dry=False, verbose=True) -> dict:
    d = Path(draft) if Path(draft).exists() else DRAFT_ROOT / draft
    f = d / "draft_content.json"
    if not f.exists():
        sys.exit(f"Không thấy {f}")
    if (d / ".locked").exists():
        sys.exit("Draft đang mở trong CapCut — đóng lại rồi chạy tiếp.")
    data = json.loads(f.read_text(encoding="utf-8"))

    mats = {}
    for bucket in ("videos", "audios"):
        for m in (data.get("materials") or {}).get(bucket, []) or []:
            mats[m["id"]] = m

    # video dài nhất = video chính (chứa giọng người nói)
    vid_dur = {}
    for t in data.get("tracks", []):
        if t.get("type") != "video":
            continue
        for s in t.get("segments", []):
            mid = s.get("material_id")
            if mid in mats:
                vid_dur[mid] = vid_dur.get(mid, 0) + (s.get("target_timerange") or {}).get("duration", 0)
    main_vid = max(vid_dur, key=vid_dur.get) if vid_dur else None

    rows, changed = [], 0
    for t in data.get("tracks", []):
        if t.get("type") not in ("video", "audio"):
            continue
        for s in t.get("segments", []):
            mat = mats.get(s.get("material_id"))
            if not mat:
                continue
            path = mat.get("path") or ""
            role = classify(t["type"], mat, mat.get("id") == main_vid)
            meas = measure(Path(path)) if path else None
            if not meas:
                continue
            gain = plan_gain(meas, role)
            vol = db_to_vol(gain)
            old = s.get("volume", 1.0)
            if abs(vol - old) > 1e-3:
                if not dry:
                    s["volume"] = vol
                changed += 1
            rows.append((role, Path(path).name[:38], meas["i"], gain, old, vol))

    if verbose:
        print(f"{'vai trò':8}{'nguồn':40}{'đo (LUFS)':>11}{'chỉnh (dB)':>12}{'volume':>9}")
        seen = set()
        for role, name, i, gain, old, vol in rows:
            if (role, name) in seen:
                continue
            seen.add((role, name))
            print(f"{role:8}{name:40}{i:>11.1f}{gain:>+12.1f}{vol:>9.2f}")

    if changed and not dry:
        shutil.copy2(f, f.with_suffix(".json.prebalance.bak"))
        f.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n{'[dry] ' if dry else ''}Đã cân bằng {changed} đoạn / {len(rows)} nguồn tiếng"
          f" ({len(set(r[1] for r in rows))} file khác nhau)")
    return {"changed": changed, "segments": len(rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    balance(a.draft, a.dry)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
