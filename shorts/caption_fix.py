# -*- coding: utf-8 -*-
"""
caption_fix.py — Sửa lỗi chính tả caption tiếng Việt bằng Gemini.

Whisper small hay sai từ ("bối trường"->"môi trường"). Gemini đọc lại theo
ngữ cảnh, sửa chính tả + thêm dấu câu, GIỮ NGUYÊN số dòng/id và timing.

Chỉ sửa các dòng NẰM TRONG chủ đề đã chọn (ít, 1 request). Cache captions_fixed.json.

CẦN GEMINI_API_KEY. Gọi qua render_short (tự động) hoặc chạy riêng:
  python caption_fix.py work/1107 --model gemini-3.5-flash
"""
import argparse, json, os, sys
from pathlib import Path
from pydantic import BaseModel


class Line(BaseModel):
    id: int
    text: str

class Corrected(BaseModel):
    lines: list[Line]


SYS = """Bạn sửa lỗi bản ghi tự động (ASR) tiếng Việt để làm phụ đề.
- Sửa từ bị nhận dạng sai theo NGỮ CẢNH (vd 'bối trường'->'môi trường', 'dậy rỗ'->'đẩy rồi').
- Thêm dấu câu và viết hoa hợp lý cho dễ đọc.
- GIỮ NGUYÊN số dòng và đúng id của từng dòng; mỗi id vào 1 dòng tương ứng.
- KHÔNG dịch, KHÔNG gộp/tách dòng, KHÔNG thêm nội dung mới. Nếu dòng đã đúng thì giữ nguyên."""


def lines_in_topics(topics: dict, transcript: dict) -> list:
    segs = transcript["segments"]
    want = set()
    for t in topics["topics"]:
        for s in t["segments"]:
            a, b = s["start_sec"], s["end_sec"]
            for seg in segs:
                if seg["end"] > a - 5 and seg["start"] < b + 5:
                    want.add(seg["id"])
    return sorted(want)


def fix_captions(work: Path, model: str) -> dict:
    """Sửa chính tả ASR cho các dòng nằm trong chủ đề. Cache theo ID DÒNG, cộng dồn.

    Trước đây cache trả về nguyên khối: phân tích lại ra chủ đề khác thì những dòng
    MỚI không có trong cache vẫn bị coi như xong, caption rơi về text ASV thô mà
    không báo gì. Giờ chỉ gọi Gemini cho phần CÒN THIẾU rồi trộn vào cache.
    """
    cache = work / "captions_fixed.json"
    da_co: dict = {}
    if cache.exists():
        try:
            da_co = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            da_co = {}

    topics = json.loads((work / "topics.json").read_text(encoding="utf-8"))
    from transcribe import load_transcript
    transcript = load_transcript(work)      # phải là bản CÓ mốc từ, không phải survey
    id2seg = {s["id"]: s for s in transcript["segments"]}
    can = lines_in_topics(topics, transcript)
    if not can:
        return da_co
    ids = [i for i in can if str(i) not in da_co]
    if not ids:
        print(f"  [caption-fix] dùng cache ({len(can)} dòng)")
        return da_co
    if da_co:
        print(f"  [caption-fix] cache thiếu {len(ids)}/{len(can)} dòng (chủ đề đã đổi) "
              f"-> chỉ sửa phần thiếu")
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        print("  [caption-fix] thiếu GEMINI_API_KEY -> bỏ qua, dùng text gốc")
        return da_co
    from google import genai
    from google.genai import types
    client = genai.Client()

    # CHIA LÔ: record nhiều chủ đề (vd 4 tiếng -> 16 chủ đề -> 755 dòng) thì gửi một
    # lần là vượt giới hạn output, resp.parsed về None -> gãy cả build. Lô ~120 dòng.
    BATCH = 120
    fixed: dict[str, str] = {}
    n_batch = (len(ids) + BATCH - 1) // BATCH
    print(f"  [caption-fix] sửa {len(ids)} dòng bằng {model} ({n_batch} lô)...")
    for bi in range(n_batch):
        chunk = ids[bi * BATCH:(bi + 1) * BATCH]
        body = "\n".join(f"{i}| {id2seg[i]['text']}" for i in chunk)
        try:
            import gemini_util
            resp, _ = gemini_util.generate(
                client, model, contents=body,
                config=types.GenerateContentConfig(
                    system_instruction=SYS, response_mime_type="application/json",
                    response_schema=Corrected, max_output_tokens=32000),
            )
            fixed.update({str(l.id): l.text for l in resp.parsed.lines})
        except Exception as e:                 # 1 lô lỗi không được làm hỏng cả build
            print(f"    lô {bi + 1}/{n_batch} hỏng ({str(e)[:70]}) -> giữ text gốc")

    # KHÔNG cache kết quả tệ: ghi cache rỗng thì mọi lần build sau đều dùng lại nó
    # và caption vĩnh viễn không được sửa mà không báo gì.
    if len(fixed) >= max(1, len(ids) // 2):
        da_co.update(fixed)                    # cộng dồn, không đè phần đã sửa trước
        cache.write_text(json.dumps(da_co, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  [caption-fix] xong {len(fixed)}/{len(ids)} dòng -> {cache.name}")
    else:
        print(f"  [caption-fix] CHỈ sửa được {len(fixed)}/{len(ids)} dòng — "
              f"KHÔNG lưu cache để lần sau thử lại")
        da_co = {**da_co, **fixed}             # vẫn dùng cho lượt build này
    # Trả về TOÀN BỘ, không chỉ phần vừa sửa: caller lấy caption theo id dòng, trả
    # thiếu là những dòng sửa từ lần trước rơi ngược về text ASR thô.
    return da_co


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--model", default="gemini-3.5-flash")
    a = ap.parse_args()
    fixed = fix_captions(Path(a.work), a.model)
    # in vài dòng để xem
    for k in list(fixed)[:8]:
        print(f"  {k}: {fixed[k]}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
