# CapCut Automation Toolkit

Tự động dựng CapCut draft bằng cách **ghi thẳng file project (JSON)** — không thao tác UI.
Đã kiểm chứng trên **CapCut 9.0.0** (`version 360000` / `new_version 177.0.0`).

Hai hệ thống:
- **App tự động hoá + kho tài nguyên** (đang phát triển) — xem ngay bên dưới.
- **Dựng hàng loạt từ folder** (đã xong) — xem mục "Pipeline (mỗi folder → 1 draft)".

---

# App: kho tài nguyên học theo gu editor + cân bằng âm thanh

```bash
cd "E:\Source Code\capcut-auto"
python app.py            # mở http://127.0.0.1:8765
```
Cài lần đầu trên máy mới:
```bash
pip install fastapi "uvicorn[standard]" watchdog python-multipart faster-whisper google-genai pydantic
```
Rồi chép `.env.example` thành `.env` và điền 2 key:
```
GEMINI_API_KEY=...
PEXELS_API_KEY=...
```
App tự nạp `.env` khi khởi động (`assetlib.load_env`), khỏi `set` biến môi trường mỗi lần.
Biến đã có sẵn trong môi trường vẫn được ưu tiên hơn file. **`.env` không đưa lên git.**

### Hai chế độ (nút góc phải header)
- **Thủ công** — 4 tab bấm nút, thao tác nhanh, ai cũng dùng được.
- **Agent** — chat tiếng Việt, tự chọn tool, tự hỏi khi thiếu thông tin, **nhớ ngữ cảnh**
  giữa các lượt (lưu SQLite trong `library.db`). Việc nặng đẩy sang job nền.
  Tool có: liệt kê dự án/record/draft, kho tài nguyên, phân tích record, dựng draft,
  chụp mốc, xem editor sửa gì, đồng bộ về kho, đo/cân bằng âm thanh, cài tài nguyên.

### 4 tab (chế độ Thủ công)
| Tab | Làm gì |
|---|---|
| **Kho tài nguyên** | Thống kê kho, gu từng editor (ai dùng gì nhiều), cài tài nguyên thiếu vào CapCut |
| **Draft** | Chụp mốc → xem editor sửa gì → đồng bộ về kho |
| **Âm thanh** | Đo LUFS từng nguồn, cân bằng & ghi thẳng vào draft |
| **Dự án** | **Nạp record mới** (bóc lời + trích chủ đề) → chọn chủ đề → tạo draft theo gu editor |

### Vòng làm việc (làm hết trong app)
```
1. Nạp record      Dự án > "Thêm record mới" > Quét > chọn file > Phân tích
                   (bóc lời GPU + Gemini trích chủ đề; 2 tiếng ~15 phút)
2. Tạo draft       chọn gu editor > "Tạo draft" ở chủ đề muốn
3. Chụp mốc        Draft > "Chụp mốc"
4. Đan/Nguyên sửa trong CapCut rồi lưu, ĐÓNG draft
5. Đồng bộ về kho  Draft > "Đồng bộ về kho"   -> kho học gu mới
6. Cân bằng tiếng  Âm thanh > "Cân bằng & ghi vào draft"
```

### Dòng lệnh
```bash
python assetlib.py --stats                          # xem kho
python draft_scan.py --harvest 0715 --owner nguyen  # nạp draft vào kho
python draft_diff.py --diff 1107_short04_v7         # editor sửa gì
python draft_diff.py --sync 1107_short04_v7 --owner dan
python asset_restore.py --check                     # máy này thiếu gì
python asset_restore.py --restore                   # cài từ kho vào CapCut
python audio_balance.py 1107_short04_v7 --dry       # xem trước
```

### File
| File | Vai trò |
|---|---|
| `assetlib.py` | Kho 2 tầng (default/user), chống trùng bằng `resource_id` + `sha256` |
| `draft_scan.py` | Bóc tài nguyên từ draft CapCut |
| `draft_diff.py` | So sánh trước/sau khi editor sửa → nạp vào kho |
| `asset_restore.py` | Cài tài nguyên sang máy mới (khỏi bấm tải tay trong CapCut) |
| `audio_balance.py` | Cân bằng LUFS theo EBU R128, ghi `volume` vào draft |
| `app.py` + `ui.html` | App web |
| `assets/fonts/` | Font Nunito đóng gói kèm (app chạy được khi không có mạng) |
| `library.db` | Manifest kho + cache kết quả đo LUFS |
| `agent.py` | Chế độ Agent: vòng lặp tool + trí nhớ hội thoại |
| `shorts/gemini_util.py` | Gọi Gemini có retry + xoay tua model |
| **`docs/WORKFLOW.md`** | **Toàn bộ workflow + cơ chế vận hành (đọc cái này trước)** |
| **`docs/ROADMAP.md`** | **Hướng phát triển: tự học, dashboard tài nguyên, agent dài hạn, tách khỏi CapCut** |
| `docs/DESIGN.md` | Style reference (nguồn chân lý về giao diện) |
| `docs/UI.md` | Quy tắc thiết kế giao diện — đọc trước khi sửa `ui.html` |
| `docs/APP_DESIGN.md` | Thiết kế chi tiết |

**Đường dẫn CapCut tự dò**, không cấu hình tay: đọc `currentCustomDraftPath` trong
`<CapCut>/User Data/Config/globalSetting` (bắt được cả khi bạn đổi thư mục draft sang ổ
khác), có `CapCut`/`JianyingPro`, `LOCALAPPDATA`/`APPDATA`. Cần chỉ định tay thì đặt
`CAPCUT_DRAFTS_ROOT`. Một chỗ duy nhất: `assetlib.find_capcut()`.

**Lưu ý:** đóng CapCut trước khi ghi vào draft (draft đang mở có `.locked`, app sẽ báo).
Mọi thao tác ghi đều có backup (`.prebalance.bak`, `.prefix.bak`).
API key truyền qua biến môi trường, **không lưu trong code** — thiếu key thì app khoá sẵn
nút *Phân tích* và chế độ Agent, không để chạy 15 phút GPU rồi mới chết.
**Dựng lại một chủ đề đã dựng sẽ GHI ĐÈ draft cũ** — app hỏi lại trước khi đè, cột
"Đã dựng" cho biết chủ đề nào đã có draft của ai.

---

# Hệ thống A — dựng hàng loạt từ folder

## Pipeline (mỗi folder → 1 draft)
```
Folder: <clip nhỏ>.mp4 x N  +  voice.mp3  (+ script.txt tùy chọn)
  │
  ├─ Video track : xếp clip theo tên, KHỚP độ dài voice, TẮT tiếng clip
  │                + transition "Slide Zoom" giữa mỗi clip
  ├─ Audio track : voice.mp3 (voiceover)
  ├─ Caption     : faster-whisper (vi) lấy timing; chữ từ script.txt (đúng 100%)
  │                → template caption giống 0720, cắt cụm ngắn, không đè
  └─ Ghi draft_content.json + draft_meta_info.json → CapCut tự nhận
```

## Yêu cầu (đã có sẵn trên máy này)
- Python 3.11, **ffmpeg/ffprobe**, **faster-whisper** (`pip install faster-whisper`).

## A. Dựng 1 folder — `capcut_build.py`
```bash
python capcut_build.py "<folder>" --name "<tên draft>" --yes
# tùy chọn:
#   --model small|base|medium     model Whisper (mặc định small)
#   --caption template|plain      template = giống 0720 (mặc định)
#   --script "path.txt"           kịch bản (mặc định tự tìm *.txt trong folder)
#   --cap-chars 18  --cap-words 5 độ dài mỗi cụm caption
#   --keep-clip-audio             GIỮ tiếng gốc clip (mặc định TẮT)
```

## B. Dựng HÀNG LOẠT 100 folder — `capcut_batch.py`
```bash
# xem trước (dry-run):
python capcut_batch.py "<thư mục cha>"
# chạy thật:
python capcut_batch.py "<thư mục cha>" --yes --model small --prefix "AUTO_"
# tùy chọn thêm: --caption --cap-chars --limit N --overwrite --keep-clip-audio
```
- Tên draft = `<prefix><tên folder con>`.
- Model Whisper **nạp 1 lần** dùng cho cả loạt (~7-8s/folder).
- Folder thiếu clip/voice → **skip**; draft trùng tên → **skip** (chạy lại an toàn/resume).
- Lỗi 1 folder chỉ skip folder đó, in tổng kết ✅/skip/❌ ở cuối.

### Chuẩn bị 100 folder
```
100_folders/
├── video01/  → 1-1.mp4 … 1-6.mp4 + voice.mp3 + script.txt
├── video02/  → ...
└── ...
```
`script.txt` = kịch bản đọc (để caption đúng chính tả). Không có thì Whisper tự nhận (kém chuẩn hơn).

## ⚠️ An toàn
1. **ĐÓNG CapCut hoàn toàn** trước khi chạy (kể cả tray). Tắt đồng bộ Cloud khi chạy lô lớn.
2. CapCut **tự reindex** thư mục drafts → không cần sửa tay `root_meta_info.json`.
3. Thử `--limit 2` trước khi chạy full 100.
4. Giữ nguyên media ở đúng đường dẫn (draft tham chiếu path tuyệt đối).

## File trong bộ công cụ
| File | Vai trò |
|---|---|
| **capcut_build.py** | Dựng 1 draft (hạt nhân) |
| **capcut_batch.py** | Dựng hàng loạt 100 folder |
| capcut_auto.py | Tiện ích draft (list/texts/clone/set-text) |
| ffmpeg_render.py | Render thẳng ra MP4, không qua CapCut (nhánh phụ) |
| `tools/` | Script khảo sát cấu trúc JSON dùng một lần + dữ liệu mẫu — không phần nào của app import chúng |

## Ghi chú kỹ thuật (cấu trúc caption template)
Mỗi caption = 1 `text_template_subtitle` (mảng `text_templates`, giữ `resource_id` template)
→ trỏ tới 1–2 material `text` qua `text_info_resources[].text_material_id`.
Chữ nằm ở: `origin_word_info`/`current_word_info`/`merge_content` (template) + `content`/`words` (text mat).
`material_text_ranges` = offset BYTE UTF-8; `content.styles.range` = offset KÝ TỰ. Thời gian: µs (segment) & ms (word_info).
Clone nguyên cụm + remap toàn bộ GUID để giữ liên kết → thay chữ/timing.
