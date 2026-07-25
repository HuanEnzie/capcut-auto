# Tài liệu kỹ thuật — Hệ thống tự động hoá sản xuất video

Phiên bản 0.1 · 2026-07-21 · Trạng thái: **bản thảo để chốt**

---

## 1. Bối cảnh & mục tiêu

**Sản phẩm chính (Hệ thống B):** từ **1 video recording 2–3 giờ** → tự động sinh **nhiều shorts** — giống Opus Clip nhưng **nâng cấp**, và **đầu ra là dự án CapCut** để người dùng tinh chỉnh (không phải video thành phẩm khoá cứng).

**Định vị:** không clone Opus Clip, mà làm **"Opus Clip cho người cần kiểm soát"** — AI chọn khoảnh khắc hay + dựng sẵn, nhưng giao lại **draft CapCut mở chỉnh được**. Đây là điểm khác biệt cốt lõi: 3 lời than phiền lớn nhất về Opus Clip đều là thế mạnh của hướng này (xem §2b).

| | Hệ thống A — **Batch Edit** (component) | Hệ thống B — **Long → Shorts** ⭐ SẢN PHẨM CHÍNH |
|---|---|---|
| Đầu vào | Folder = N clip ngắn + voice (+ kịch bản) | **1 recording 2–3 giờ** |
| Xử lý | Ghép clip khớp voice, transition, caption | Tìm khoảnh khắc hay, cắt, reframe, caption |
| Đầu ra | 1 draft CapCut / folder | **Nhiều draft CapCut** (1 draft / short) |
| Vai trò | ✅ Xong — tái dùng làm thư viện dựng draft | 🔨 Đang xây — mục tiêu chính |

**Nguyên tắc xuyên suốt:** mọi khâu nặng (transcribe) **cache lại kết quả** để thử nghiệm nhiều lần miễn phí.

## 2b. So với Opus Clip — bám sát & nâng cấp

| Tính năng | Opus Clip | Hệ thống này |
|---|---|---|
| Tìm khoảnh khắc hay (hook + payoff) | ✅ | ✅ LLM + profile theo loại nội dung |
| Điểm "viral" | ✅ model train trên hàng triệu video | ⚠️ **Điểm theo rubric** — không đoán viral bằng họ, nhưng **giải thích được & tuỳ biến** (xem §3.4) |
| Auto-reframe 9:16 | ✅ bám người nói (crop) | ✅ **nền mờ + video giữa** — tốt hơn cho họp/screen-share (§6.1); bám người nói là nâng cấp sau |
| Caption động | ✅ 97% EN, **yếu tiếng Việt** | ✅ **tiếng Việt tốt** (căn kịch bản + whisper vi) — điểm mạnh |
| Cắt filler / khoảng lặng | ✅ | 🔨 thêm (§6.2) — dùng word-timestamp |
| B-roll tự động | ✅ generative | ❌ ngoài phạm vi ban đầu |
| **Sửa được sau khi tạo** | ❌ **video khoá cứng** | ✅✅ **draft CapCut mở chỉnh** — MOAT chính |
| Chi phí | 💰 tính theo phút, hay treo | ✅ local, ~free, không treo |
| Gộp đoạn rời cùng chủ đề | ❌ chủ yếu đoạn liền | ✅ (§3.3) |

**Ba điểm nâng cấp thật sự** (không phải marketing): (1) đầu ra CapCut mở chỉnh, (2) chất lượng tiếng Việt, (3) tuỳ biến tiêu chí + gộp đoạn rời. **Không nên overclaim** khoản "đoán viral" — model của Opus train trên dữ liệu khổng lồ; điểm của ta là rubric giải thích được, giá trị khác chứ không hơn ở khoản dự đoán.

---

## 2. Kiến trúc tổng thể

```
                    ┌──────────────────────────────────────┐
                    │           LÕI DÙNG CHUNG (Python)    │
                    ├──────────────────────────────────────┤
   Hệ thống A ─────▶│ media/    ffprobe, ffmpeg (cắt/ghép) │
   (batch edit)     │ asr/      faster-whisper + GPU       │◀──── Hệ thống B
                    │ caption/  cắt cụm, căn kịch bản, ASS │      (long→shorts)
                    │ llm/      Gemini: chủ đề, tiêu đề    │
                    │ capcut/   đọc/ghi draft JSON v9.0.0  │
                    └────────────────┬─────────────────────┘
                                     │
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
        CLI (batch runner)   Draft CapCut          MP4 (ffmpeg)
                             (chỉnh tay)           (tự động 100%)
```

**Quyết định nền tảng:** lõi viết bằng **Python**. Lý do: toàn bộ chuỗi media/AI (faster-whisper, ffmpeg binding, thao tác JSON CapCut) đã có sẵn và đang chạy tốt bằng Python. Viết lại Node.js sẽ phải làm lại toàn bộ tầng ASR + media mà không được lợi gì. Nếu cần "App", bọc thêm **FastAPI + trang web tĩnh** ở trên lõi Python.

---

## 3. Tầng LLM — Gemini

### 3.1 Chọn model

⚠️ **Gemini 2.5 ngừng hoạt động 16/10/2026** → không xây hệ thống trên 2.5.

| Model | Context | Giá /1M (in/out) | Dùng cho |
|---|---|---|---|
| **Gemini 3.5 Flash** (khuyến nghị) | 1M | ~$1.50 / ~$9 | Trích chủ đề — cần suy luận trên transcript dài |
| Flash-Lite / bản rẻ hơn | 1M | thấp hơn | Việc máy móc: đặt tiêu đề, viết hook |

> **Bắt buộc kiểm chứng trước khi code:** gọi `client.models.list()` để lấy danh sách model **hiện hành thực tế** thay vì tin bảng giá trên blog. Model ID và giá đổi nhanh.

### 3.2 Xử lý ngữ cảnh dài

Transcript 3h tiếng Việt ước tính **60.000–120.000 token** → **lọt trọn trong context 1M**, gọi **1 lần duy nhất**, không chia chunk.

> Vì sao không chia chunk: chia nhỏ làm mất cái nhìn tổng thể, chủ đề bị cắt vụn và trùng lặp ở ranh giới. Chỉ chia chunk (có overlap + bước merge) nếu sau này gặp recording > 6–8 giờ.

### 3.3 Structured output

Dùng `response_schema` với Pydantic → `response.parsed` trả về object đã validate, **không parse text thủ công**:

```python
class Segment(BaseModel):
    start_sec: float
    end_sec: float
    note: str             # vì sao đoạn này thuộc chủ đề

class Topic(BaseModel):
    title: str                    # tiêu đề ngắn, dùng làm tên video
    segments: list[Segment]       # ⭐ NHIỀU đoạn rời → gộp thành 1 video
    summary: str                  # tóm tắt 1–2 câu
    scores: dict[str, int]        # điểm theo từng tiêu chí của profile (1–10)
    total_score: float            # điểm tổng đã nhân trọng số
    hook: str                     # câu mở đầu gây chú ý
    reason: str                   # vì sao chấm điểm vậy

class TopicList(BaseModel):
    topics: list[Topic]
```

Cấu hình: `response_mime_type="application/json"` + `response_schema=TopicList`.

> **Vì sao `segments` là list:** đã chốt gộp nhiều đoạn rời cùng chủ đề thành 1 video. Trong họp, một chủ đề thường bị ngắt quãng rồi quay lại — mô hình 1 chủ đề = 1 khoảng liên tục sẽ mất nội dung.

### 3.4 Content Profile — tiêu chí chấm điểm cắm-rút được ⭐

**Yêu cầu:** hệ thống phải phục vụ nhiều loại nội dung (họp, bài giảng, podcast, livestream…), mỗi loại có tiêu chí "đáng làm short" khác nhau. → **Không hard-code rubric vào prompt.**

Mỗi loại nội dung là một file profile:

```yaml
# profiles/meeting.yaml
name: "Họp / hội thảo"
target_duration: [60, 180]        # giây
criteria:                          # LLM chấm từng tiêu chí 1–10
  decision:
    weight: 3
    desc: "Đoạn chốt phương án, giao việc, kết luận"
  explanation:
    weight: 2
    desc: "Giải thích cách làm, chia sẻ kinh nghiệm — hữu ích độc lập"
  debate:
    weight: 2
    desc: "Tranh luận, quan điểm trái chiều"
  data:
    weight: 1
    desc: "Nêu số liệu, kết quả, mốc thời gian cụ thể"
standalone_required: true          # đoạn phải hiểu được khi tách khỏi ngữ cảnh
min_total_score: 5
```

- Prompt gửi Gemini được **lắp ráp từ profile** (mô tả tiêu chí + trọng số + độ dài mục tiêu).
- `Topic.scores` trả về điểm **theo đúng các key trong profile** → `total_score` tính bằng code (nhân trọng số), **không để LLM tự tính** (LLM tính số hay sai).
- Thêm loại nội dung mới = thêm 1 file YAML, **không sửa code**.

Đây là quyết định kiến trúc quan trọng nhất của tầng LLM: nó biến hệ thống từ "công cụ cắt họp" thành **nền tảng cắt video theo chủ đề cho mọi loại nội dung**.

### 3.5 Caching & Batch

| Kỹ thuật | Khi nào dùng | Lợi ích |
|---|---|---|
| **Context caching** (`client.caches.create()`) | Chạy **nhiều pass trên CÙNG transcript** (chia chủ đề → chấm điểm → viết hook) | Token cache rẻ hơn nhiều |
| **Batch API** (`client.batches.create()`) | Xử lý **nhiều recording**, không cần realtime | **−50% giá** |

Hai kỹ thuật **kết hợp được**: cache phần dùng chung rồi chạy batch trên đó.

### 3.6 Ước tính chi phí (cần đo lại bằng `count_tokens`)

Recording 3h, Gemini 3.5 Flash (~$1.50/$9):

| Khoản | Token | Chi phí |
|---|---|---|
| Input (transcript) | ~80.000 | ~$0.12 |
| Output (30–40 chủ đề) | ~6.000 | ~$0.05 |
| **1 recording** | | **~$0.17** (~4.500đ) |
| **1 recording (Batch −50%)** | | **~$0.09** (~2.300đ) |

→ **Chi phí LLM không phải nút thắt.** Nút thắt thật sự là **transcribe** (thời gian GPU).

---

## 4. Tầng ASR — faster-whisper

| Cấu hình | Thời gian transcribe 3h |
|---|---|
| CPU (i5-9300H, 4 nhân) | ~30–60 phút |
| **GPU (GTX 1650 4GB) + CUDA** | **~6–12 phút** ⭐ |

**Hành động:** cài thư viện CUDA (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) một lần → bật `device="cuda"`. Đây là cải thiện lớn nhất về hiệu năng của cả hệ thống.

- **Không cần diarization** (đã chốt) → bỏ pyannote, đơn giản hoá đáng kể.
- Model: `small` cho tốc độ, `medium` nếu cần chuẩn hơn (4GB VRAM chạy được `medium` với `int8_float16`).
- **Bắt buộc cache** `transcript.json` — transcribe 1 lần, thử cắt chủ đề bao nhiêu lần cũng miễn phí.
- **Đặt ASR sau interface** (`asr/base.py` với method `transcribe(audio) -> transcript`) để đổi engine không phải sửa pipeline.

### 4.1 Vì sao faster-whisper, không phải WhisperX

WhisperX **chạy trên** faster-whisper (dùng nó làm engine) + bồi thêm: forced alignment, batched inference, diarization. Cả 3 đều không đáng với setup hiện tại:

| Tính năng WhisperX | Với TV + GTX 1650 4GB |
|---|---|
| Forced alignment (timestamp từng chữ) | Tiếng Việt **không** trong danh sách hỗ trợ mặc định; phải tự tìm wav2vec2 fine-tuned + test, rủi ro chất lượng |
| Batched inference (tới 70×) | Cần batch_size ≥16 → **12GB+ VRAM**; 4GB chỉ batch_size=1 → mất gần hết lợi thế |
| Diarization | Đã chốt không cần |

Hệ thống B snap về ranh giới **câu** → không cần độ chính xác từng-chữ. faster-whisper đã có `word_timestamps` + `vad_filter`, đủ dùng.

**Đổi sang WhisperX khi:** (1) nâng GPU ≥12GB, HOẶC (2) xác minh được model alignment tiếng Việt tốt VÀ cần caption karaoke chính xác (chủ yếu cho Hệ thống A). Nhờ ASR-sau-interface, việc đổi chỉ là thay 1 adapter.

---

## 5. Mô hình dữ liệu

```
work/<recording_id>/
├── source.mp4                 # file gốc (hoặc symlink)
├── audio.wav                  # 16kHz mono, sinh từ ffmpeg
├── transcript.json            # ⭐ CACHE: segments + words + timestamp
├── topics.json                # ⭐ CACHE: output Gemini đã validate
├── clips/                     # các đoạn đã cắt
│   └── 01_<slug>.mp4
└── manifest.json              # trạng thái từng bước, để resume
```

`manifest.json` giữ trạng thái mỗi bước (`pending`/`done`/`failed`) → chạy lại chỉ làm phần còn thiếu, giống cơ chế skip đã có ở `capcut_batch.py`.

---

## 6. Luồng xử lý hệ thống B

```
1. probe        ffprobe → độ dài, codec
2. extract      ffmpeg → audio.wav 16kHz mono
3. transcribe   faster-whisper (GPU) → transcript.json      [CACHE]
4. topics       Gemini + profile + structured output → topics.json   [CACHE]
5. refine       snap điểm cắt về ranh giới câu + đệm ±0.5s
6. merge        nối các segment rời cùng chủ đề (transition giữa các đoạn)
7. reframe      16:9 → 9:16 nền mờ + video giữa (mục 6.1)
8. package      → MP4 (caption ASS)  ⊕  draft CapCut (chỉnh tay)
```

**Bước 5 quan trọng:** LLM trả về thời gian *xấp xỉ*. Phải snap về ranh giới câu gần nhất **lấy từ `transcript.json`** (nguồn timestamp chính xác), không tin thẳng số LLM đưa.

### 6.1 Bố cục 9:16 — nền mờ + video giữa

Canvas **1080×1920**. Nguồn 16:9 scale theo chiều rộng → `1080 × 9/16 ≈ 608px`, đặt giữa theo chiều dọc.

```
┌──────────────────────┐ y=0
│   BĂNG TRÊN 656px    │  ← tiêu đề chủ đề / branding
├──────────────────────┤ y=656
│  VIDEO 1080×608 16:9 │  ← nội dung gốc, KHÔNG crop, không mất gì
├──────────────────────┤ y=1264
│   BĂNG DƯỚI 656px    │  ← caption
└──────────────────────┘ y=1920
```

**Nền:** bản sao của chính video, scale phủ kín 1080×1920 rồi làm mờ (`boxblur`) — cách xử lý phổ biến, nhìn đẹp và không cần asset ngoài.

```
[0:v]scale=1080:1920:force_original_aspect_ratio=increase,
     crop=1080:1920,boxblur=20:2[bg];
[0:v]scale=1080:-2[fg];
[bg][fg]overlay=(W-w)/2:(H-h)/2[out]
```

> **Lợi thế của bố cục này:** hai băng trống 656px cho **rất nhiều chỗ** đặt tiêu đề (trên) và caption (dưới) mà không đè lên nội dung — tốt hơn hẳn so với crop 9:16 (mất hai bên) hoặc caption đè lên mặt người nói.

**Về "bám người nói" của Opus Clip:** cách đó cần face detection + active-speaker detection (nặng, cần model riêng), và **hỏng với họp nhiều người / screen-share**. Bố cục nền-mờ của ta né được hoàn toàn khâu này và bền hơn cho nội dung họp. Bám-người-nói để dành làm **nâng cấp giai đoạn sau**, chỉ bật cho clip 1-người-nói.

### 6.2 Cắt filler & khoảng lặng (tùy chọn, làm clip "gọn")

Opus Clip cắt bỏ từ đệm ("ừm", "à", "kiểu như…") và khoảng lặng dài để clip punchy hơn. Ta làm được nhờ **word-timestamp** đã có trong `transcript.json`:
- Khoảng lặng > ngưỡng (vd 0.7s) giữa 2 từ → cắt bớt (chừa đệm nhỏ).
- Danh sách filter từ đệm tiếng Việt → bỏ các từ đó.
- **Cảnh báo:** cắt trong lòng đoạn làm timeline gãy khúc → nếu xuất draft CapCut, mỗi lần cắt tạo thêm 1 segment. Nên để **tùy chọn bật/tắt**; mặc định tắt cho bản đầu (giữ đoạn liền mạch, đơn giản).

### 6.3 Cấu trúc draft CapCut cho short (khác Hệ thống A)

Hệ thống A ghép **nhiều file clip**; ở đây mỗi short dùng **1 file nguồn** (recording gốc) với **nhiều `source_timerange`** (các đoạn của chủ đề). Draft gồm:
- 1 video material trỏ tới recording gốc; N segment cắt các đoạn (`source_timerange` khác nhau) nối tiếp trên timeline, transition giữa các đoạn.
- Canvas 9:16; clip scale/transform để thành "video giữa" (§6.1). Nền mờ: hoặc pre-render bằng ffmpeg rồi đưa vào, hoặc để người dùng tự thêm trong CapCut (đơn giản hơn cho bản đầu).
- Text track: caption template (tái dùng System A) + băng tiêu đề trên.
- Tái dùng: `capcut_build` (dựng segment/caption), `capcut_batch` (cơ chế resume/skip).

---

## 7. Rủi ro & giảm thiểu

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Gemini 2.5 EOL 16/10/2026 | **Cao** | Xây trên 3.5 Flash; tách tầng LLM sau 1 interface để đổi model dễ |
| LLM trả timestamp lệch | Cao | Snap về ranh giới câu từ transcript; không tin số thô |
| Transcribe chậm (CPU) | Trung bình | Bật CUDA; cache transcript |
| Whisper sai chính tả tiếng Việt | Trung bình | Có kịch bản thì căn theo kịch bản (đã làm ở hệ thống A) |
| CapCut đổi format khi update | Trung bình | Đọc cấu trúc từ draft "donor" lúc chạy, không hard-code |
| CapCut tự reindex `root_meta_info.json` | Thấp | Không sửa tay index; chỉ tạo thư mục draft hợp lệ |
| Chi phí API vượt dự toán | Thấp | Đo bằng `count_tokens` trước; dùng Batch −50% |

---

## 8. Lộ trình phát triển

**Giai đoạn 0 — Nền tảng** *(1 buổi)*
- Bật CUDA cho faster-whisper, đo lại tốc độ thực tế.
- Dựng khung thư mục `work/` + `manifest.json` (resume).

**Giai đoạn 1 — Transcript pipeline** *(1–2 buổi)*
- `probe → extract → transcribe → transcript.json` có cache.
- Xuất bản transcript đọc được (có timestamp) để kiểm tra thủ công.

**Giai đoạn 2 — Trích chủ đề bằng Gemini** *(1–2 buổi)*
- Tầng `llm/` với interface trung lập + adapter Gemini.
- Structured output, kiểm chứng model ID bằng `models.list()`.
- Đo token & chi phí thật trên 1 recording.

**Giai đoạn 3 — Cắt & đóng gói** *(1–2 buổi)*
- Snap điểm cắt, cắt ffmpeg, xuất MP4 + draft CapCut (tái dùng code sẵn có).

**Giai đoạn 4 — Vận hành** *(tuỳ nhu cầu)*
- Batch nhiều recording, log, retry.
- (Tuỳ chọn) FastAPI + web UI.

---

## 9. Quyết định kỹ thuật

### Đã chốt ✅

| # | Vấn đề | Quyết định |
|---|---|---|
| 1 | Nhà cung cấp LLM | **Gemini** (không phải Claude). Tách sau interface trung lập |
| 2 | Nhận diện người nói | **Không cần** → bỏ pyannote, đơn giản hoá |
| 3 | Tiêu chí "đáng làm short" | **Cắm-rút được theo profile YAML** (mục 3.4) — không hard-code |
| 4 | Nhiều đoạn rời cùng chủ đề | **Gộp thành 1 video** → `Topic.segments` là list |
| 5 | Khung hình | **9:16 nền mờ + video giữa** (mục 6.1) — không mất nội dung |
| 6 | Ngôn ngữ lõi | **Python**; "App" = bọc FastAPI + web UI lên trên |

### Còn mở ⏳

| # | Vấn đề | Ghi chú |
|---|---|---|
| 7 | Model Gemini cụ thể | Xác nhận bằng `models.list()` trước khi code (2.5 EOL 16/10/2026) |
| 8 | Bộ profile đầu tiên | Bắt đầu với `meeting.yaml`; thêm loại nào tiếp theo? |
| 9 | Đầu ra ưu tiên | MP4 tự động hay draft CapCut để chỉnh tay — hay cả hai? |
| 10 | Băng trên hiển thị gì | Chỉ tiêu đề chủ đề, hay thêm logo/branding? |
| 11 | Hình thức "App" | CLI đủ dùng, hay cần web UI ngay? |

---

## 10. Phụ lục — Trạng thái hệ thống A (đã xong)

| File | Vai trò |
|---|---|
| `capcut_build.py` | Dựng 1 draft: clip khớp voice, tắt tiếng clip, Slide Zoom, caption template |
| `capcut_batch.py` | Chạy hàng loạt N folder, model nạp 1 lần, skip/resume |
| `ffmpeg_render.py` | Render thẳng MP4 1080×1920 (không cần CapCut) |
| `capcut_auto.py` | Tiện ích draft: list / texts / clone / set-text / restore |

**Đã kiểm chứng thật:** 4 folder `DrStone/1-4` → 4 draft, 0 tham chiếu hỏng, 0 chồng caption, tiếng clip đã tắt. Hiệu năng ~23s/folder.

**Phát hiện kỹ thuật quan trọng:** file draft CapCut 9.0.0 là **JSON thuần không mã hoá**; caption template (`text_template_subtitle`) tái tạo được bằng cách clone cụm thật rồi remap toàn bộ GUID.
