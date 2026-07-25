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


def build_system_prompt(p: dict) -> str:
    crit_lines = "\n".join(
        f"- {k} (trọng số {v['weight']}): {v['desc']}" for k, v in p["criteria"].items())
    lo, hi = p.get("target_duration", [60, 180])
    standalone = ("Mỗi chủ đề PHẢI tự đứng vững khi tách khỏi ngữ cảnh (người xem chưa nghe phần trước vẫn hiểu)."
                  if p.get("standalone_required") else "")
    return f"""Bạn là biên tập viên video chuyên cắt các khoảnh khắc đáng làm video ngắn (short) từ bản ghi dài.
Loại nội dung: {p['name']}. Ngôn ngữ: {p.get('language','Tiếng Việt')}.

NHIỆM VỤ: đọc transcript (mỗi dòng bắt đầu bằng số giây), tìm các CHỦ ĐỀ đáng làm short.
- Mỗi chủ đề dài khoảng {lo}-{hi} giây khi ghép lại.
- Một chủ đề có thể gồm NHIỀU đoạn rời rạc trong buổi (ngắt quãng rồi quay lại) — gộp chúng vào `segments`.
- {standalone}
- start_sec/end_sec lấy theo số giây ở đầu dòng transcript (ước lượng đủ tốt, hệ thống sẽ tự canh lại về ranh giới câu).

CHẤM ĐIỂM: với mỗi chủ đề, chấm TỪNG tiêu chí sau theo thang 1-10 (dùng ĐÚNG tên key), điền vào `scores`:
{crit_lines}

Chỉ giữ chủ đề thực sự đáng làm short. `title` ngắn gọn hấp dẫn (dùng làm tên video). `hook` là câu mở đầu gây tò mò. Trả lời hoàn toàn bằng tiếng Việt."""


def format_transcript(transcript: dict) -> str:
    # nén: mỗi segment 1 dòng "start| text" (start làm tròn giây) để tiết kiệm token
    lines = []
    for s in transcript["segments"]:
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
    # nạp transcript đúng thứ tự ưu tiên (bóc kỹ > bản đầy đủ cũ > khảo sát).
    # KHÔNG dùng sorted(glob)[-1]: xếp chữ cái thì "survey" đứng cuối -> chọn nhầm.
    from transcribe import load_transcript
    try:
        transcript = load_transcript(work)
    except FileNotFoundError:
        sys.exit(f"Không thấy transcript trong {work} (chạy transcribe.py trước)")
    profile = load_profile(profile_path)

    sys_prompt = build_system_prompt(profile)
    body = format_transcript(transcript)
    print(f"Transcript: {transcript['n_segments']} segment, {transcript['duration_sec']/60:.0f} phút")
    print(f"Profile   : {profile['name']} ({len(profile['criteria'])} tiêu chí)")
    print(f"Prompt body: ~{len(body):,} ký tự (~{len(body)//4:,} token thô ước lượng)")

    if dry:
        print("\n[DRY] 400 ký tự đầu của transcript đã format:\n" + body[:400])
        print("\n[DRY] Không gọi API. Bỏ --dry để chạy thật (cần GEMINI_API_KEY).")
        return

    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        sys.exit("Thiếu GEMINI_API_KEY (hoặc GOOGLE_API_KEY) trong env.")

    from google import genai
    from google.genai import types
    client = genai.Client()

    # đo token thật + ước tính (giá đổi thường xuyên -> chỉ in token)
    try:
        tk = client.models.count_tokens(model=model, contents=body).total_tokens
        print(f"Token input (đo thật): {tk:,}")
    except Exception as e:
        print(f"(count_tokens bỏ qua: {e})")

    print(f"Gọi Gemini '{model}' (structured output)...")
    import gemini_util                      # tự thử lại + xoay model khi 503/quá tải
    resp, _used = gemini_util.generate(
        client, model, contents=body,
        config=types.GenerateContentConfig(
            system_instruction=sys_prompt,
            response_mime_type="application/json",
            response_schema=TopicList,
            max_output_tokens=32000,
        ),
    )
    result: TopicList = resp.parsed

    # tính điểm tổng + lọc + xếp hạng
    topics = []
    for t in result.topics:
        d = t.model_dump()
        d["total_score"] = compute_total(d["scores"], profile)
        topics.append(d)
    topics.sort(key=lambda x: x["total_score"], reverse=True)
    min_score = profile.get("min_total_score", 0)
    kept = [t for t in topics if t["total_score"] >= min_score]

    out = {"source": transcript["source"], "model": model,
           "profile": profile["name"], "n_topics": len(kept),
           "topics": kept, "topics_below_threshold": len(topics) - len(kept)}
    cache = work / "topics.json"
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {len(kept)} chủ đề (bỏ {len(topics)-len(kept)} dưới ngưỡng {min_score}) -> {cache.name}\n")
    for i, t in enumerate(kept, 1):
        dur = sum(s["end_sec"] - s["start_sec"] for s in t["segments"])
        print(f"  {i}. [{t['total_score']:.1f}] {t['title']}  ({len(t['segments'])} đoạn, {dur:.0f}s)")


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
