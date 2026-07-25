# Runbook demo — CapCut Auto Editor

## Khởi động (trước demo)
```bash
cd "E:\Source Code\capcut-auto"
python app.py
```
Key nằm trong `.env` cạnh `app.py`, app tự nạp — không cần `set` gì nữa. Thiếu key thì
tab Dự án hiện cảnh báo đỏ và nút *Phân tích* bị khoá, thấy ngay trước khi demo.
Mở http://127.0.0.1:8765 (Ctrl+F5 nếu tab cũ). **Đóng CapCut** trước khi tạo/ghi draft.

## Câu chuyện demo (6-7 phút)

**1. Nạp record thô → tự ra chủ đề — tab "Dự án" › "Thêm record mới"**
- Bấm **Quét** thư mục record → chọn file → **Phân tích**.
- Chạy live: bóc lời bằng GPU → Gemini trích chủ đề, log hiện tiến trình theo dòng.
- **Dùng `demo_8phut.mp4`** để chạy live (~70 giây, ra 2 chủ đề). Record 2 tiếng thật ≈ 15 phút —
  đừng chạy live, chỉ vào bản 1107 đã phân tích sẵn.
- Chốt ý: *"Ném nguyên buổi ghi hình vào, máy tự tìm đoạn đáng cắt và chấm điểm."*

**2. Chọn chủ đề → tạo draft**
- Recording 1107 (2 tiếng) đã ra **4 chủ đề** có điểm; `demo_8phut` ra 2 chủ đề.
- Chọn **gu editor** (Dan / Nguyên) → bấm **Tạo draft** ở chủ đề muốn.
- Job chạy, hiện log, báo tên draft → mở trong CapCut.
- Chốt ý: *"Opus Clip chỉ ra video; ta ra DỰ ÁN CapCut còn sửa được."*

**3. App học gu editor — tab "Kho tài nguyên"**
- 42 tài nguyên đã học từ draft thật của 2 bạn; bảng "dùng nhiều nhất" = gu mỗi người
  (Nguyên: hiệu ứng chữ `cc_印加太阳神之辉` 31×; Dan: font `comicbd`, sticker Pet Meme).
- Chốt ý: *"Càng dùng càng hợp gu — đây là điểm khác Opus Clip."*

**4. Draft tự lên đúng style từng người**
- So `1107_t4_dan` và `1107_t4_nguyen`: **cùng nội dung, khác font + khác sticker** — tự động.

**5. Vòng học khép kín — tab "Draft"**  ⚠️ *cần chuẩn bị trước 2 phút, nếu không diff ra 0/0 rất nhạt*
- **Chuẩn bị**: các draft `1107_t*` đã được **chụp mốc sẵn**. Trước demo: mở 1 draft trong CapCut
  (vd `1107_t2_dan`), **thêm 1 sticker + đổi 1 SFX theo ý mình**, Ctrl+S, rồi **đóng draft**
  (về màn hình danh sách, để hết `.locked`).
- Khi demo: bấm "Xem editor sửa gì" → hiện đúng cái vừa thêm/gỡ → "Đồng bộ về kho"
  → quay tab "Kho tài nguyên" thấy tài nguyên mới đã vào kho.
- Chốt ý: *"Editor sửa tay một lần, app nhớ mãi — lần sau tự dùng."*

**6. Cân bằng âm thanh — tab "Âm thanh"**
- Chọn draft → thấy bảng LUFS từng nguồn (SFX lệch nhau ~18 dB) → "Cân bằng & ghi vào draft".
- Chốt ý: *"Giọng chuẩn −14 LUFS, nhạc/SFX tự lùi lại, theo chuẩn phát sóng."*

## Draft dựng sẵn (mở nhanh khi demo)
- `1107_t4_dan`, `1107_t4_nguyen` — so sánh style.
- `1107_t1_dan`, `1107_t2_dan`, `1107_t3_dan` — 3 chủ đề còn lại (đã pre-warm).

## Nếu trục trặc
- Tạo draft báo lỗi `.locked` → **đóng draft đó trong CapCut** (về màn hình danh sách).
- Bấm Tạo draft topic đã pre-warm → ~5s; topic mới toanh → 1-2 phút (render + Gemini + Pexels).
- App không phản hồi → xem cửa sổ chạy `python app.py`; khởi động lại.

## Chưa có (nói trước nếu bị hỏi)
- Bước record→chủ đề hiện chạy CLI (transcribe 2h ~15 phút GPU), demo bắt đầu từ record đã phân tích.
- Đóng gói .exe: đã đo xong (một app, gói CUDA 736 MB tuỳ chọn), làm sau.
- Agent chat (kiểu Claude Code): làm sau demo.
