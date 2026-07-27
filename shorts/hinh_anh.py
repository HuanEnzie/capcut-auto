# -*- coding: utf-8 -*-
"""hinh_anh.py — Đo PHẦN HÌNH của record: đoạn nào đứng yên, đoạn nào có gì để xem.

VÌ SAO CÓ FILE NÀY: ba short đầu tiên dựng ra đều "đúng" theo mọi chỉ số đang đo —
dangling 0, caption đúng nhịp, file không thiếu — nhưng xem thì không dùng được, vì
nguồn là buổi họp chia sẻ MÀN HÌNH. Riêng short thứ ba có ~15 giây hình gần như đứng
yên. Không chỉ số nào trong app nhìn thấy điều đó, vì cả pipeline chỉ đọc CHỮ.

Đo bằng ffmpeg `freezedetect`, không cần AI. Đo được 27/07 trên 3 bản export:
    webcam nói chuyện : 0 giây đứng yên   · 471 lần đổi cảnh
    chia sẻ màn hình  : 13,7 và 15,1 giây · 136-139 lần đổi cảnh
Tách bạch rõ tới mức không cần ngưỡng tinh vi.

Quét cả record 58 phút mất 38 giây — rẻ hơn bóc lời nhiều lần, và quét MỘT LƯỢT rồi
chấm được mọi chủ đề nên không phải quét lại theo từng chủ đề.
"""
import json
import re
import subprocess
from pathlib import Path

TEN_FILE = "hinh.json"

# -50dB: gần như không đổi pixel nào. d=2: đứng yên từ 2 giây trở lên mới tính —
# dưới mức đó là người nói đang ngừng giữa câu, chuyện bình thường.
NGUONG_DB = -50
TOI_THIEU_GIAY = 2.0


def quet(source: str, wd: Path, im_lang: bool = False) -> dict:
    """Quét record, ghi hinh.json. Có cache — quét lại record 2 tiếng là phí."""
    f = wd / TEN_FILE
    if f.exists():
        try:
            cu = json.loads(f.read_text(encoding="utf-8"))
            if cu.get("source") == str(source):
                if not im_lang:
                    print("  [hình] dùng cache")
                return cu
        except (OSError, ValueError):
            pass

    if not im_lang:
        print(f"  [hình] quét đoạn đứng yên (ngưỡng {NGUONG_DB}dB, ≥{TOI_THIEU_GIAY:.0f}s)...")
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(source),
         "-vf", f"freezedetect=n={NGUONG_DB}dB:d={TOI_THIEU_GIAY}",
         "-map", "0:v", "-an", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace")

    dong = []
    dau = None
    for m in re.finditer(r"freeze_(start|duration|end):\s*([0-9.]+)", r.stderr):
        loai, gt = m.group(1), float(m.group(2))
        if loai == "start":
            dau = gt
        elif loai == "duration" and dau is not None:
            dong.append([round(dau, 2), round(gt, 2)])     # [bắt đầu, kéo dài]
            dau = None

    dai = _do_dai(source)
    tong_tinh = sum(d for _, d in dong)
    data = {"source": str(source), "duration_sec": dai,
            "dung_yen": dong, "tong_tinh_sec": round(tong_tinh, 1),
            "ty_le_tinh": round(tong_tinh / dai, 3) if dai else 0.0}
    try:
        wd.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    if not im_lang:
        print(f"  [hình] {len(dong)} đoạn đứng yên, tổng {tong_tinh/60:.1f} phút "
              f"= {data['ty_le_tinh']*100:.0f}% record")
    return data


def _do_dai(source: str) -> float:
    try:
        o = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(source)],
            capture_output=True, text=True, timeout=30).stdout.strip()
        return float(o)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def cham(hinh: dict, khoang: list) -> dict:
    """Chấm phần HÌNH cho một chủ đề, từ các khoảng thời gian của nó.

    Trả `he_so` để nhân vào điểm nội dung. KHÔNG để LLM chấm việc này: nó chỉ đọc
    transcript, không nhìn được video, nên sẽ bịa — đúng cái bẫy tiêu chí `data` đang
    mắc (điểm trung bình 2,2 vì chấm thứ gần như không tồn tại).
    """
    tong = sum(b - a for a, b in khoang) or 1.0
    tinh = 0.0
    for a, b in khoang:
        for f0, fd in hinh.get("dung_yen", []):
            tinh += max(0.0, min(b, f0 + fd) - max(a, f0))
    ty_le = tinh / tong
    # Đứng yên tới 40% thời lượng thì short coi như hỏng -> phạt tới một nửa điểm.
    # Không phạt về 0: đoạn tĩnh vẫn cứu được bằng B-roll hoặc chữ to.
    he_so = max(0.5, 1.0 - ty_le * 1.25)
    return {"tinh_sec": round(tinh, 1), "ty_le_tinh": round(ty_le, 3),
            "he_so": round(he_so, 3)}


def nhan_xet_nguon(hinh: dict) -> str:
    """Một câu nói cho người dùng biết nguồn này có hợp làm short không."""
    t = hinh.get("ty_le_tinh", 0)
    if t >= 0.25:
        return (f"Record này có {t*100:.0f}% thời lượng hình gần như ĐỨNG YÊN — "
                f"nhiều khả năng là bản ghi chia sẻ màn hình. Short dựng ra sẽ có "
                f"nhiều đoạn không có gì để nhìn.")
    if t >= 0.10:
        return (f"Có {t*100:.0f}% thời lượng hình đứng yên — nên tránh những chủ đề "
                f"rơi vào các đoạn đó.")
    return ""
