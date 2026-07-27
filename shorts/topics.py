# -*- coding: utf-8 -*-
"""
topics.py — Giai đoạn 2: transcript.json + profile -> topics.json (Gemini).

- Structured output (Pydantic) -> response.parsed, không parse text tay.
- Tiêu chí chấm điểm nạp từ profile YAML (cắm-rút), điểm tổng do CODE tính.
- Cache topics.json; xếp hạng theo total_score; lọc dưới ngưỡng.

CẦN: biến môi trường GEMINI_API_KEY (hoặc GOOGLE_API_KEY).

CÁCH DÙNG:
  set GEMINI_API_KEY=...            (Windows CMD)
  python topics.py --list-models    # xem model hiện có (chọn 3.5 flash nếu có)
  python topics.py work/1107 --profile profiles/meeting.yaml --model gemini-2.5-flash
  python topics.py work/1107 --dry  # chỉ in prompt + ước lượng, không gọi API
"""
import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel

# ---------------- Schema (structured output) ----------------
class Segment(BaseModel):
    start_sec: float
    end_sec: float

class CriterionScore(BaseModel):
    name: str          # PHẢI khớp key tiêu chí trong profile
    score: int         # 1-10

class Topic(BaseModel):
    title: str                     # tiêu đề ngắn, dùng làm tên short
    segments: list[Segment]        # nhiều đoạn rời cùng chủ đề -> gộp
    summary: str                   # tóm tắt 1-2 câu
    scores: list[CriterionScore]
    hook: str                      # câu mở đầu gây chú ý
    reason: str                    # vì sao đáng làm short

class TopicList(BaseModel):
    topics: list[Topic]


# ---------------- Profile & prompt ----------------
def load_profile(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def build_system_prompt(p: dict, tu_giay: float = 0, den_giay: float = 0,
                        can_it_nhat: int = 0) -> str:
    """Prompt hệ thống. `tu_giay`/`den_giay` là cửa sổ đang xét, `can_it_nhat` là số
    chủ đề tối thiểu cần tìm trong cửa sổ đó.

    VÌ SAO CÓ SỐ LƯỢNG TỐI THIỂU: bản đầu chỉ quy định ĐỘ DÀI mỗi chủ đề, không nói
    cần bao nhiêu cái. Model tự quyết và luôn chọn ít cho chắc — record 58 phút ra
    đúng 3 chủ đề, dùng 9,5% thời lượng, bỏ phí 52 phút. Nói rõ mật độ mong muốn thì
    nó mới quét hết.
    """
    crit_lines = "\n".join(
        f"- {k} (trọng số {v['weight']}): {v['desc']}" for k, v in p["criteria"].items())
    lo, hi = p.get("target_duration", [60, 180])
    standalone = ("Mỗi chủ đề PHẢI tự đứng vững khi tách khỏi ngữ cảnh (người xem chưa nghe phần trước vẫn hiểu)."
                  if p.get("standalone_required") else "")
    cua_so = ""
    if den_giay:
        cua_so = (f"\nĐOẠN ĐANG XÉT: giây {int(tu_giay)} đến {int(den_giay)} "
                  f"({(den_giay-tu_giay)/60:.0f} phút). CHỈ trả về chủ đề nằm trong đoạn này.\n"
                  f"Phải quét ĐỀU tới tận dòng CUỐI CÙNG — đừng dồn hết chủ đề vào phần đầu.")
    so_luong = ""
    if can_it_nhat:
        so_luong = (f"\nSỐ LƯỢNG: tìm ÍT NHẤT {can_it_nhat} chủ đề trong đoạn này. "
                    f"Thà đề xuất hơi nhiều rồi để người dùng loại, còn hơn bỏ sót — "
                    f"mỗi chủ đề đều có điểm nên cái yếu sẽ tự rơi xuống cuối.")
    return f"""Bạn là biên tập viên video chuyên cắt các khoảnh khắc đáng làm video ngắn (short) từ bản ghi dài.
Loại nội dung: {p['name']}. Ngôn ngữ: {p.get('language','Tiếng Việt')}.
{cua_so}{so_luong}

NHIỆM VỤ: đọc transcript (mỗi dòng bắt đầu bằng số giây), tìm các CHỦ ĐỀ đáng làm short.
- Mỗi chủ đề dài khoảng {lo}-{hi} giây khi ghép lại.
- Một chủ đề có thể gồm NHIỀU đoạn rời rạc (người nói ngắt quãng rồi quay lại ý đó) — gộp vào `segments`.
  Dạng này thường ra short HAY HƠN dạng một mạch liền, vì bỏ được phần lan man ở giữa. Hãy CHỦ ĐỘNG tìm nó.
- {standalone}
- start_sec/end_sec lấy theo số giây ở đầu dòng transcript (ước lượng đủ tốt, hệ thống sẽ tự canh lại về ranh giới câu).

CHẤM ĐIỂM: với mỗi chủ đề, chấm TỪNG tiêu chí sau theo thang 1-10 (dùng ĐÚNG tên key), điền vào `scores`:
{crit_lines}

`title` ngắn gọn hấp dẫn (dùng làm tên video). `hook` là câu mở đầu gây tò mò. Trả lời hoàn toàn bằng tiếng Việt."""


# ---------------- Chia cửa sổ ----------------
# VÌ SAO: nhồi cả transcript 1 tiếng vào MỘT lượt gọi thì model chú ý phần đầu rồi
# đuối dần. Đo trên record 58 phút: 20 phút CUỐI không sinh ra chủ đề nào, và tổng
# độ phủ chỉ 9,5%. Chia cửa sổ thì mỗi đoạn được chú ý đầy đủ, và mở rộng tuyến tính
# cho record 4 tiếng thay vì đụng trần ngữ cảnh.
CUA_SO_GIAY = 15 * 60        # mỗi cửa sổ 15 phút
CHONG_LAN_GIAY = 120         # chồng lấn 2 phút: chủ đề vắt qua ranh giới không bị cắt đôi
PHUT_MOI_CHU_DE = 4          # mật độ mong muốn -> số chủ đề tối thiểu mỗi cửa sổ


def chia_cua_so(dai: float, cua_so: float = CUA_SO_GIAY,
                chong_lan: float = CHONG_LAN_GIAY) -> list:
    """Cắt [0, dai] thành các cửa sổ chồng lấn. Cửa sổ cuối quá ngắn thì nhập vào
    cửa sổ trước — 30 giây đứng riêng thì không đủ ngữ cảnh để hiểu gì."""
    if dai <= cua_so:
        return [(0.0, dai)]
    ra, t = [], 0.0
    while t < dai:
        het = min(t + cua_so, dai)
        ra.append((t, het))
        if het >= dai:
            break
        t = het - chong_lan
    if len(ra) > 1 and ra[-1][1] - ra[-1][0] < cua_so * 0.4:
        a, _ = ra[-2]
        ra = ra[:-2] + [(a, dai)]
    return ra


def _trung_nhau(a: dict, b: dict) -> float:
    """Tỷ lệ chồng lấn thời gian giữa hai chủ đề (0-1 theo cái ngắn hơn)."""
    def khoang(t):
        return [(s["start_sec"], s["end_sec"]) for s in t.get("segments", [])]
    ta, tb = khoang(a), khoang(b)
    if not ta or not tb:
        return 0.0
    chung = 0.0
    for x0, x1 in ta:
        for y0, y1 in tb:
            chung += max(0.0, min(x1, y1) - max(x0, y0))
    da = sum(x1 - x0 for x0, x1 in ta)
    db = sum(y1 - y0 for y0, y1 in tb)
    nho = min(da, db)
    return chung / nho if nho > 0 else 0.0


def gop_chu_de(ds: list, nguong: float = 0.5) -> list:
    """Khử trùng chủ đề sinh ra từ hai cửa sổ chồng lấn.

    Trùng thì GIỮ CÁI ĐIỂM CAO HƠN chứ không gộp đoạn: gộp máy móc hai mô tả khác
    nhau về cùng một quãng ra tiêu đề lai, chẳng giống cái nào."""
    ds = sorted(ds, key=lambda t: -t.get("total_score", 0))
    giu = []
    for t in ds:
        if not any(_trung_nhau(t, g) >= nguong for g in giu):
            giu.append(t)
    return giu


def format_transcript(transcript: dict, tu: float = None, den: float = None) -> str:
    # nén: mỗi segment 1 dòng "start| text" (start làm tròn giây) để tiết kiệm token
    #
    # BỎ QUA dòng đã đánh dấu `bo` (thử mic, chào hỏi, lặp vô nghĩa): chúng làm loãng
    # nội dung khi model đi tìm chủ đề. Chỉ bỏ khỏi PROMPT, segment vẫn nằm nguyên
    # trong transcript — mốc thời gian là thứ dùng để cắt video, mất là hỏng.
    lines = []
    for s in transcript["segments"]:
        if s.get("bo"):
            continue
        if tu is not None and s["end"] <= tu:
            continue
        if den is not None and s["start"] >= den:
            continue
        lines.append(f"{int(s['start'])}| {s['text']}")
    return "\n".join(lines)


# ---------------- Tính điểm tổng (CODE tính, không để LLM tính) ----------------
def compute_total(topic_scores: list, profile: dict) -> float:
    weights = {k: v["weight"] for k, v in profile["criteria"].items()}
    total_w = sum(weights.values()) or 1
    s = 0.0
    for cs in topic_scores:
        w = weights.get(cs["name"], 0)
        s += cs["score"] * w
    return round(s / total_w, 2)   # thang ~1-10


# ---------------- Gemini ----------------
def list_models():
    from google import genai
    client = genai.Client()
    print("Các model khả dụng (lọc 'generateContent'):")
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            print(f"  {m.name}")


def extract_topics(work: Path, profile_path: str, model: str, dry: bool):
    # Nạp .env: chạy qua app thì assetlib đã nạp sẵn, nhưng chạy thẳng
    # `python topics.py work/...` thì chưa — và hàm này kiểm GEMINI_API_KEY TRƯỚC khi
    # gemini_util kịp nạp, nên dừng ngay với "thiếu key" dù .env có key.
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import assetlib
        assetlib.load_env()
    except ImportError:
        pass
    # nạp transcript đúng thứ tự ưu tiên (bóc kỹ > bản đầy đủ cũ > khảo sát).
    # KHÔNG dùng sorted(glob)[-1]: xếp chữ cái thì "survey" đứng cuối -> chọn nhầm.
    from transcribe import load_transcript
    try:
        transcript = load_transcript(work)
    except FileNotFoundError:
        sys.exit(f"Không thấy transcript trong {work} (chạy transcribe.py trước)")
    profile = load_profile(profile_path)

    dai = float(transcript.get("duration_sec") or 0)
    cua_so = chia_cua_so(dai)
    print(f"Transcript: {transcript['n_segments']} segment, {dai/60:.0f} phút")
    print(f"Profile   : {profile['name']} ({len(profile['criteria'])} tiêu chí)")
    print(f"Chia {len(cua_so)} cửa sổ (mỗi cửa sổ {CUA_SO_GIAY//60} phút, chồng lấn "
          f"{CHONG_LAN_GIAY//60} phút) — nhồi cả tiếng vào 1 lượt thì model bỏ sót phần cuối")

    if dry:
        b0 = format_transcript(transcript, *cua_so[0])
        print("\n[DRY] 400 ký tự đầu của cửa sổ 1:\n" + b0[:400])
        print("\n[DRY] Không gọi API. Bỏ --dry để chạy thật (cần GEMINI_API_KEY).")
        return

    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        sys.exit("Thiếu GEMINI_API_KEY (hoặc GOOGLE_API_KEY) trong env.")

    from google import genai
    from google.genai import types
    client = genai.Client()

    import gemini_util                      # tự thử lại + xoay model khi 503/quá tải
    tho = []
    for i, (a, b) in enumerate(cua_so, 1):
        body = format_transcript(transcript, a, b)
        if not body.strip():
            continue
        can = max(1, round((b - a) / 60 / PHUT_MOI_CHU_DE))
        sys_prompt = build_system_prompt(profile, a, b, can)
        print(f"  [cửa sổ {i}/{len(cua_so)}] {int(a)//60}:{int(a)%60:02d}-{int(b)//60}:{int(b)%60:02d}"
              f" · ~{len(body)//4:,} token · cần ≥{can} chủ đề...")
        try:
            resp, _used = gemini_util.generate(
                client, model, contents=body,
                config=types.GenerateContentConfig(
                    system_instruction=sys_prompt,
                    response_mime_type="application/json",
                    response_schema=TopicList,
                    max_output_tokens=32000,
                ),
            )
        except gemini_util.HetHanNgach:
            # Cạn hạn ngạch giữa chừng: giữ phần đã tìm được thay vì mất trắng. Nhưng
            # PHẢI BÁO — im lặng thì người dùng tưởng record chỉ có ngần đó chủ đề.
            print(f"  ⚠️ CẠN HẠN NGẠCH ở cửa sổ {i}/{len(cua_so)} — giữ {len(tho)} chủ đề "
                  f"đã tìm được, PHẦN TỪ {int(a)//60} PHÚT TRỞ ĐI CHƯA QUÉT. "
                  f"Chạy lại sau khi hạn ngạch reset để quét nốt.")
            break
        except RuntimeError as e:
            print(f"  ⚠️ cửa sổ {i} hỏng ({str(e)[:70]}) -> bỏ qua, quét tiếp")
            continue
        got = resp.parsed.topics if resp.parsed else []
        print(f"      -> {len(got)} chủ đề")
        for t in got:
            d = t.model_dump()
            d["total_score"] = compute_total(d["scores"], profile)
            d["cua_so"] = i
            tho.append(d)

    truoc_gop = len(tho)
    topics = gop_chu_de(tho)
    if truoc_gop != len(topics):
        print(f"\nGộp trùng ở vùng chồng lấn: {truoc_gop} -> {len(topics)} chủ đề")
    topics.sort(key=lambda x: x["total_score"], reverse=True)
    min_score = profile.get("min_total_score", 0)
    kept = [t for t in topics if t["total_score"] >= min_score]

    # ĐỘ PHỦ: bao nhiêu phần trăm record được dùng. Đây là chỉ số để biết chia cửa sổ
    # có ăn thua không — trước khi chia, record 58 phút chỉ dùng 9,5%, bỏ phí 52 phút.
    dung = sum(s["end_sec"] - s["start_sec"] for t in kept for s in t["segments"])
    phu = dung / dai * 100 if dai else 0
    nhieu_doan = sum(1 for t in kept if len(t["segments"]) > 1)

    out = {"source": transcript["source"], "model": model,
           "profile": profile["name"], "n_topics": len(kept),
           "topics": kept, "topics_below_threshold": len(topics) - len(kept),
           "do_phu_pct": round(phu, 1), "n_cua_so": len(cua_so),
           "n_nhieu_doan": nhieu_doan}
    cache = work / "topics.json"
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {len(kept)} chủ đề (bỏ {len(topics)-len(kept)} dưới ngưỡng {min_score}) -> {cache.name}")
    print(f"   độ phủ {phu:.1f}% record ({dung/60:.0f}/{dai/60:.0f} phút) · "
          f"{nhieu_doan}/{len(kept)} chủ đề ghép nhiều đoạn\n")
    for i, t in enumerate(kept, 1):
        dur = sum(s["end_sec"] - s["start_sec"] for s in t["segments"])
        dau = min(s["start_sec"] for s in t["segments"])
        print(f"  {i}. [{t['total_score']:.1f}] {t['title']}  "
              f"({len(t['segments'])} đoạn, {dur:.0f}s, từ {int(dau)//60}:{int(dau)%60:02d})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work", nargs="?", help="thư mục work/<recording> (chứa transcript.*.json)")
    ap.add_argument("--profile", default=str(Path(__file__).parent / "profiles" / "meeting.yaml"))
    ap.add_argument("--model", default="gemini-2.5-flash",
                    help="chạy --list-models để xem model 3.5 hiện có")
    ap.add_argument("--dry", action="store_true", help="chỉ in prompt + ước lượng, không gọi API")
    ap.add_argument("--list-models", action="store_true")
    a = ap.parse_args()

    if a.list_models:
        list_models(); return
    if not a.work:
        sys.exit("Thiếu đường dẫn work/<recording>")
    extract_topics(Path(a.work), a.profile, a.model, a.dry)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
