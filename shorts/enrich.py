# -*- coding: utf-8 -*-
"""
enrich.py — "Bộ não AI" cho short: Gemini đọc 1 đoạn + kho SFX -> quyết định:
  - hook  : khoảnh khắc ấn tượng nhất để MỞ ĐẦU (start/end + câu)
  - emojis: chèn icon phù hợp ngữ cảnh ở thời điểm nào (sec, emoji)
  - sfx   : chèn hiệu ứng âm thanh (chọn từ kho có sẵn) ở từ/câu ấn tượng / chuyển cảnh

Cache enrich_NN.json. CẦN GEMINI_API_KEY.
  python enrich.py work/1107 --only 4
"""
import argparse, json, os, sys
from pathlib import Path
from pydantic import BaseModel

SFX_DIR = "E:/E Download/meme"


class Hook(BaseModel):
    start_sec: float
    end_sec: float
    line: str
    reason: str

class EmojiCue(BaseModel):
    sec: float
    emoji: str
    reason: str

class SfxCue(BaseModel):
    sec: float
    file: str      # phải khớp tên file trong kho
    reason: str

class BrollCue(BaseModel):
    start_sec: float
    end_sec: float
    query: str     # từ khoá TIẾNG ANH để tìm video/ảnh stock trên Pexels
    reason: str

class Enrich(BaseModel):
    theme: str     # 1 câu: mood/tông cảm xúc + góc kể của short (mỏ neo cho B-roll)
    hook: Hook
    emojis: list[EmojiCue]
    sfx: list[SfxCue]
    broll: list[BrollCue]


def topic_lines(topic, transcript, fixed):
    segs = transcript["segments"]
    out = []
    for s in topic["segments"]:
        a, b = s["start_sec"], s["end_sec"]
        for seg in segs:
            if seg["end"] > a - 2 and seg["start"] < b + 2:
                txt = fixed.get(str(seg["id"]), seg["text"]).strip()
                out.append((int(seg["start"]), txt))
    return out


def enrich_topic(work: Path, idx: int, model: str) -> dict:
    cache = work / f"enrich_{idx:02d}.json"
    if cache.exists():
        print("  [enrich] dùng cache"); return json.loads(cache.read_text(encoding="utf-8"))
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        sys.exit("Thiếu GEMINI_API_KEY")

    topics = json.loads((work / "topics.json").read_text(encoding="utf-8"))
    from transcribe import load_transcript
    tr = load_transcript(work)
    fixed = json.loads((work / "captions_fixed.json").read_text(encoding="utf-8")) if (work / "captions_fixed.json").exists() else {}
    topic = topics["topics"][idx - 1]
    lines = topic_lines(topic, tr, fixed)
    sfx_files = [p.name for p in Path(SFX_DIR).glob("*.mp3")] if Path(SFX_DIR).exists() else []

    body = f"CHỦ ĐỀ SHORT: {topic.get('title','')}\n"
    body += f"TÓM TẮT: {topic.get('summary','')}\n"
    body += f"GÓC HOOK: {topic.get('hook','')}\n\n"
    body += "TRANSCRIPT (giây | câu):\n" + "\n".join(f"{s}| {t}" for s, t in lines)
    body += "\n\nKHO SFX (chỉ được chọn đúng tên trong list này):\n" + "\n".join(sfx_files)

    sys_prompt = f"""Bạn là editor video ngắn (short) chuyên nghiệp cho nội dung tiếng Việt.
Cho CHỦ ĐỀ/TÓM TẮT + 1 đoạn transcript (có mốc giây) và kho hiệu ứng âm thanh (SFX) có sẵn. Hãy quyết định:

0) theme: TRƯỚC TIÊN, đọc cả đoạn và chốt trong 1 CÂU cái mood/tông cảm xúc + góc kể của short này (vd "câu chuyện cảnh tỉnh, hơi hài, về nỗi loay hoay chạy theo công cụ AI mới"). Đây là MỎ NEO — mọi B-roll phải phục vụ đúng mood/câu chuyện này, không lạc tông.

1) hook: chọn KHOẢNH KHẮC ẤN TƯỢNG NHẤT trong đoạn để MỞ ĐẦU short (2-5 giây) — câu gây sốc/tò mò/gợi mở nhất để giữ người xem không lướt. Trả start_sec/end_sec (theo mốc trong transcript) + câu (line) + lý do.
NGUYÊN TẮC GIỮ CHÂN: video ngắn phải liên tục có kích thích, không để người xem "ổn định" — nhịp do SFX + B-roll gánh; emoji chỉ là điểm nhấn thưa.

2) emojis: THƯA THỚT — chỉ ~MỖI 10-15 GIÂY một icon (tổng khoảng 5-8 cái cho cả đoạn), CHỈ tại điểm cảm xúc/nhấn mạnh RÕ RÀNG nhất (vd 🤯 sốc, 💡 insight lớn, 🔥 cao trào, 💰 tiền, ✅/❌ đúng/sai). Đừng lạm dụng. Mỗi cái: sec, emoji (1 ký tự), reason.
3) sfx: GIỮ NHỊP — khoảng MỖI 4-6 GIÂY, ở TỪ/CÂU nhấn, câu chốt, chuyển ý. Chọn file HỢP TÔNG NỘI DUNG (đây là chia sẻ chuyên môn về AI/kinh doanh, giọng nghiêm túc pha vui): ưu tiên whoosh/boom/vine-boom/ding/pop/nhấn/chuyển cảnh. TRÁNH SFX thô tục/vô nghĩa/quá trẻ trâu (fart, chửi bậy, tiếng bậy bạ) trừ khi khoảnh khắc thực sự hài đúng chỗ. Đa dạng, không lặp file liền nhau. Mỗi cái: sec, file (đúng tên trong kho), reason.
4) broll: 4-8 đoạn chèn VIDEO STOCK để đỡ nhàm. QUAN TRỌNG — B-ROLL BÁM MOOD & CÂU CHUYỆN, KHÔNG minh hoạ danh từ theo từng câu:
   - SAI (quá literal): nghe "nhân sự" → 'office paperwork HR'; nghe "AI" → 'robot'. Kiểu này ra stock quảng cáo văn phòng sáo rỗng, LẠC TÔNG với short.
   - ĐÚNG: chọn hình theo CẢM XÚC/HÀNH ĐỘNG của phân cảnh trong mạch chuyện (vd đoạn nói loay hoay đổi hết công cụ này tới công cụ khác → 'person overwhelmed by multiple screens', 'hand scrolling phone fast', 'frustrated working late on laptop'; đoạn insight/khuyên nhủ → 'person confident walking city', 'focused typing laptop close up').
   - Ưu tiên clip NĂNG ĐỘNG, HIỆN ĐẠI, GẦN GŨI (người thật, chuyển động, cảm xúc) hợp nhịp short-form; TRÁNH cliché doanh nghiệp (bắt tay, họp bàn tròn, biểu đồ generic).
   - Mỗi cái: start_sec, end_sec (mỗi đoạn 2-4 giây), query (TỪ KHOÁ TIẾNG ANH ngắn, thiên về cảm xúc/hành động), reason (nêu rõ nó phục vụ mood/câu chuyện thế nào).

Emoji/SFX phải khớp nội dung tại thời điểm đó; B-roll phải khớp MOOD (theme) toàn short. Hook chọn loại mạnh nhất. Trả lời tiếng Việt (riêng broll.query bằng tiếng Anh)."""

    from google import genai
    from google.genai import types
    client = genai.Client()
    print(f"  [enrich] Gemini '{model}' phân tích {len(lines)} câu, {len(sfx_files)} SFX...")
    import gemini_util                      # tự thử lại + xoay model khi 503/quá tải
    resp, _used = gemini_util.generate(
        client, model, contents=body,
        config=types.GenerateContentConfig(
            system_instruction=sys_prompt, response_mime_type="application/json",
            response_schema=Enrich, max_output_tokens=16000),
    )
    data = resp.parsed.model_dump()
    # lọc SFX không khớp file
    valid = set(sfx_files)
    data["sfx"] = [s for s in data["sfx"] if s["file"] in valid]
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--only", type=int, required=True)
    ap.add_argument("--model", default="gemini-3.5-flash")
    a = ap.parse_args()
    d = enrich_topic(Path(a.work).resolve(), a.only, a.model)
    print(f"\n=== THEME (mỏ neo B-roll) ===\n  {d.get('theme','')}")
    print("\n=== HOOK ===")
    h = d["hook"]; print(f"  {h['start_sec']}-{h['end_sec']}s: \"{h['line']}\"\n  → {h['reason']}")
    print("\n=== EMOJI ===")
    for e in d["emojis"]:
        print(f"  {e['sec']}s {e['emoji']}  ({e['reason']})")
    print("\n=== SFX ===")
    for s in d["sfx"]:
        print(f"  {s['sec']}s {s['file']}  ({s['reason']})")
    print("\n=== B-ROLL ===")
    for b in d.get("broll", []):
        print(f"  {b['start_sec']}-{b['end_sec']}s  [{b['query']}]  ({b['reason']})")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
