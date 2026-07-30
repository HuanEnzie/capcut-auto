# Hướng dẫn sử dụng — CapCut Auto Editor

Tài liệu này dành cho **người dùng cuối** (editor, người biên tập), không phải để đọc
mã nguồn. Theo đúng thứ tự bấm nút thật trên giao diện — bạn có thể dùng tài liệu này
để đi từng bước từ lúc cài app tới lúc có video hoàn chỉnh.

> Bản kỹ thuật (kiến trúc, cách vận hành bên trong) nằm ở `docs/WORKFLOW.md`. Tài liệu
> này chỉ nói **bấm gì, ở đâu, để làm gì** — theo đúng nhãn nút hiện có trên app tính đến
> phiên bản `v1.0.4`.

---

## 0. App làm được gì, một câu

> Ném nguyên một buổi ghi hình/ghi âm dài (2-4 tiếng) vào app → app tự tìm những đoạn
> đáng cắt thành video ngắn, chấm điểm từng đoạn → bạn chọn đoạn ưng → app tự dựng
> thành **một dự án CapCut còn sửa được** (không phải video đã render cứng) → bạn mở
> trong CapCut sửa nốt vài chi tiết → app **nhớ** những gì bạn sửa để lần sau tự làm
> đúng gu của bạn hơn.

Khác Opus Clip và các tool tương tự ở chỗ: sản phẩm ra là **dự án CapCut** (caption,
sticker, SFX, B-roll vẫn là các lớp rời, sửa được), không phải một file video cứng.

---

## 1. Cài đặt

1. Tải bản cài đặt mới nhất tại
   [github.com/HuanEnzie/capcut-auto/releases](https://github.com/HuanEnzie/capcut-auto/releases)
   — file `CapCutAuto-Setup-vX.Y.Z.exe`.
2. Chạy file vừa tải. Windows SmartScreen có thể cảnh báo "Windows protected your PC"
   vì file chưa ký số — bấm **More info → Run anyway**.
3. Làm theo wizard — cài xong app **tự mở** trong một cửa sổ riêng (không phải tab
   trình duyệt).
4. Cần có **CapCut** đã cài trên máy (app tự dò thư mục draft của CapCut, không cần
   cấu hình gì thêm).
5. Cần có **ffmpeg** — bản cài đặt đã **bundle sẵn**, không phải tự tải.
6. Vào mục **Cài đặt** (thanh bên trái) → dán API key trước khi dùng (xem mục 10).

Cài đè bản mới lên bản cũ được luôn, không cần gỡ cài đặt trước — dữ liệu (kho tài
nguyên đã học, các dự án, draft) nằm trong `library.db`/`shorts/work` và được giữ
nguyên. **Gỡ cài đặt thì mất dữ liệu này** — app có hỏi lại và nói rõ trước khi gỡ.

---

## 2. Bắt đầu một dự án

Màn hình **Home** (mở app lên là vào thẳng đây):

1. Bấm **+ Tạo dự án** → chọn quy trình. Hiện chỉ có **Record AI Editor** dùng được
   (buổi ghi hình dài → nhiều short); các quy trình khác (KOC, Cartoon, Podcast) đang
   "sắp có".
2. Dự án mới tạo tự mở sang màn hình làm việc, khối **"Cài đặt dự án"** tự bung sẵn vì
   đó là việc duy nhất cần làm lúc này.

### Gắn file record

Trong khối "Cài đặt dự án" → mục **"File record"**:

- Gõ đường dẫn thư mục vào ô **Thư mục**, hoặc bấm **Chọn thư mục…** để mở hộp thoại
  Windows thật. App tự quét cả thư mục con tìm file video/audio (`.mp4 .mov .mkv .avi
  .m4v .webm .mp3 .wav .m4a`).
- Chọn đúng file trong danh sách **File record** (hoặc bấm **Chọn file…** để trỏ thẳng
  một file bất kỳ), rồi bấm **Dùng file này**.
- Một record dùng được ở **nhiều dự án khác nhau** — mỗi dự án phân tích riêng, không
  đụng tới bản phân tích của dự án kia (app tự hỏi lại nếu record đó đã dùng ở dự án
  khác).

> **Gắn xong không đổi lại được** — draft và cache đều bám theo record đó. Muốn đổi
> record khác thì tạo dự án mới.

### Chọn tài nguyên đưa vào draft (tuỳ chọn, có thể bỏ qua)

Mục **"Tài nguyên đưa vào draft"** — 7 lớp: Caption, Hook mở đầu, Hiệu ứng tiếng (SFX),
Emoji, B-roll stock, Card chốt/CTA, Nhạc nền. Tắt lớp nào thì draft dựng ra **không có**
lớp đó. Trong lớp đã bật, có thể bấm **Chọn SFX cụ thể** để giới hạn đúng vài file được
dùng — để trống là dùng cả kho. Bấm **Lưu cấu hình** để giữ lựa chọn này (không bắt
buộc phải làm bước này trước khi Phân tích).

---

## 3. Phân tích — bóc lời và tìm chủ đề

Mục **"Bóc lời & trích chủ đề"**:

1. Chọn **Độ chính xác bóc lời**: `tiny` (nhanh nhất, sai chữ nhiều) → `base` → `small`
   (mặc định, cân bằng) → `medium` (chuẩn nhất, chậm nhất). Không chắc thì để mặc định.
2. Bấm **Phân tích**. Job chạy **nền** — theo dõi tiến trình ở khối **"Tiến trình"** cuối
   trang (có log từng bước, không phải chỉ thanh phần trăm im lìm).

App làm 3 việc, theo thứ tự (đọc log để biết đang ở đâu):

| Bước | Việc | Ghi chú |
|---|---|---|
| 1/3 | Bóc lời (ASR) | GPU nếu có, tự lùi CPU nếu không dùng được CUDA — không chết cứng |
| 2/3 | Làm sạch transcript bằng Gemini | Sửa lỗi chính tả/ASR trước khi tìm chủ đề, để AI không phải vừa đoán chữ vừa tìm ý |
| 3/3 | Gemini trích chủ đề, có chấm điểm | Cắt theo cửa sổ 15 phút nếu record dài, để không bỏ sót phần cuối |

Mỗi chủ đề được chấm theo 5 tiêu chí có trọng số (chốt quyết định, giải thích/chia sẻ
kinh nghiệm, tranh luận, số liệu, câu mở đầu gây chú ý) **cộng thêm điểm phạt nếu phần
hình đứng yên quá nhiều** (ví dụ ghi màn hình không có ai xuất hiện) — short mà mở ra
không có gì để nhìn thì bị hạ điểm dù lời nói hay.

**Cần GEMINI_API_KEY** để bước 2 và 3 chạy — thiếu thì nút Phân tích bị khoá luôn, có
ghi rõ lý do, không để job chạy xong bóc lời (tốn nhiều phút) mới báo lỗi.

Phân tích lại một record đã phân tích (nút đổi thành **"Phân tích lại"**) có thể ra
**danh sách chủ đề khác** — không sao, draft đã dựng trước đó vẫn giữ nguyên.

### Xem lời thoại

Bấm **Xem lời thoại** (bật lên sau khi Phân tích xong) để đọc lại toàn bộ transcript có
mốc giờ, không cần mở video. Có ô tìm chữ, và tick **"bản đã làm sạch"** để so bản AI đã
sửa với bản gốc Whisper nghe được (dòng bị sửa có gạch dưới, hiện cả bản gốc bên cạnh —
ASR tiếng Việt sai đủ nhiều nên đáng để đối chiếu). Hai nút **Sao chép** và **Tải .txt**
xuất đúng bản đang xem (sạch hoặc gốc) ra ngoài app.

---

## 4. Duyệt danh sách Chủ đề

Phân tích xong, khối **"Chủ đề"** hiện lưới thẻ, mỗi thẻ có:

- Số thứ tự chủ đề và **điểm tổng**.
- Tiêu đề, độ dài, số đoạn ghép (nếu chủ đề đó ghép từ nhiều đoạn rời trong record), và
  mốc thời gian bắt đầu.
- Danh sách editor đã dựng draft cho chủ đề này (nếu có) — thẻ xanh là draft rảnh, thẻ
  đỏ là đang mở trong CapCut.

Danh sách phân trang 9 chủ đề/trang để so sánh dễ hơn thay vì cuộn một danh sách dài.

### Xem trước trước khi quyết định

Bấm **Xem trước** trên thẻ chủ đề để mở hộp thoại xem chi tiết **trước khi tốn thời
gian dựng draft**:

- Điểm từng tiêu chí (không chỉ điểm tổng).
- Tóm tắt nội dung + góc hook gợi ý.
- **Nghe thử 40 giây đầu** ngay trong hộp thoại, không cần mở file video gốc.
- Trích đoạn transcript có mốc giờ.
- Nút **"Tạo draft từ chủ đề này"** ngay tại chỗ nếu ưng.

---

## 5. Tạo draft CapCut

1. Chọn **gu editor** ở ô dropdown "Dựng theo gu editor" (danh sách này lấy từ những
   editor đã có dữ liệu học — xem mục 8). Mỗi editor có font/sticker/nhịp cắt khác
   nhau; cùng một chủ đề dựng theo 2 gu khác nhau sẽ ra 2 draft khác nhau về hình thức,
   giống nhau về nội dung.
2. Bấm **Tạo draft** trên thẻ chủ đề (hoặc từ hộp Xem trước). App hỏi xác nhận, rồi chạy
   nền — theo dõi ở "Tiến trình".
3. Xong, draft xuất hiện trong CapCut với tên dạng `<dự_án>_t<số_chủ_đề>_<gu_editor>`.

**Dựng lại một chủ đề đã có draft sẽ GHI ĐÈ** draft cũ — app luôn hỏi lại, nói rõ dựng
lúc nào, và **chặn hẳn** nếu draft đó đang mở trong CapCut (`.locked`) thay vì để job
chạy xong rồi mới báo lỗi.

Draft dựng ra gồm: nền video 9:16 đã cắt/ghép sẵn (không sửa được — CapCut không cho),
cộng các lớp **sửa được**: caption, sticker/emoji, SFX, B-roll, card chốt. Đây là điểm
khác các tool xuất video cứng: mở draft ra sửa tiếp bình thường như dự án CapCut tự tay
dựng.

---

## 6. Mở CapCut và sửa tay

Vào **Tổng quan** (thanh bên trái) để thấy toàn bộ dự án CapCut app đã dựng:

- Mỗi thẻ hiện tên draft, trạng thái (đang mở trong CapCut / rảnh), có mốc hay chưa,
  sửa lần cuối lúc nào.
- Bấm **Mở CapCut** để bật app CapCut lên — CapCut không có cách nào để app tự mở
  thẳng một dự án cụ thể (đã kiểm chứng: 32 route deep-link không route nào nhận
  tham số draft), nên bạn tự chọn đúng dự án trong danh sách CapCut sau khi nó mở.
- Bấm vào cả thẻ để mở thẳng thư mục chứa draft đó ngoài Windows Explorer.

Sửa gì tuỳ ý trong CapCut — thêm sticker, đổi SFX, chỉnh nhịp cắt, viết lại caption...
Xong thì lưu (Ctrl+S) và **đóng draft trong CapCut** (về màn hình danh sách dự án của
CapCut) trước khi quay lại app — draft đang mở thì app không ghi/đo được gì vào đó.

---

## 7. Vòng học gu editor (điểm khác biệt cốt lõi)

Đây là cơ chế app "nhớ" phong cách của từng editor để lần dựng sau tự đúng gu hơn, ít
phải sửa tay hơn. Bốn bước, đều ở màn **Tổng quan**, trên thẻ của từng draft:

1. **Chụp mốc** — chụp lại trạng thái draft NGAY SAU KHI app vừa dựng xong (làm việc
   này sớm, trước khi editor bắt đầu sửa).
2. Editor sửa tay trong CapCut (mục 6), lưu, đóng draft.
3. **"Editor sửa gì"** (bật lên sau khi có mốc) — so draft hiện tại với mốc, hiện:
   - **Độ phải sửa** — % — 0% nghĩa là editor mở ra dùng luôn không phải chỉnh gì.
     Chỉ số này càng giảm theo thời gian nghĩa là app càng hợp gu editor hơn.
   - Số caption bị sửa chữ/đổi giờ/bị bỏ, số đoạn hình bị cắt lại, số nguồn tiếng bị
     chỉnh âm lượng.
   - Danh sách tài nguyên **thêm mới** (editor tự kéo vào) và **bị gỡ** (editor không
     dùng) so với bản app dựng.
4. **"Đồng bộ về kho"** — nạp phần editor vừa thêm vào kho tài nguyên của đúng editor
   đó. Lần dựng sau, app ưu tiên dùng đúng những gì editor này hay chọn.

> **Sửa tay một lần, app nhớ mãi.** Đây là lý do "Kho tài nguyên" (mục 8) có cột "của
> ai" và "mức dùng" — số liệu đó tự lớn lên qua đúng vòng lặp Chụp mốc → sửa →
> Đồng bộ này, không phải ai đó ngồi gõ tay.

---

## 8. Quản lý tài nguyên

Thanh bên trái → **Quản lý tài nguyên**. Hai phần:

**Kho gu đã học** (phần trên): tổng số tài nguyên, dung lượng, số tài nguyên của từng
editor + lượt dùng, số tài nguyên **thiếu trên máy này** (máy khác cài lại thì thiếu —
bấm **"Cài tài nguyên thiếu vào CapCut"** để tự copy vào đúng chỗ CapCut cần). Bảng bên
dưới liệt kê từng tài nguyên, sắp theo mức dùng nhiều nhất = gu rõ nhất của mỗi người,
lọc được theo tên/loại.

**Tài nguyên CapCut có sẵn trên máy** (phần dưới, sau khi bấm **Quét tài nguyên** — mất
~15 giây): CapCut tự tải rất nhiều gói (sticker, hiệu ứng, filter...) khi bạn lướt panel
trong CapCut, phần lớn **chưa dùng lần nào** nhưng đã nằm sẵn trên đĩa — dựng draft dùng
ngay được, không cần tải thêm. Mục "Có sẵn mà chưa dùng" cho thử trực tiếp những gói
này. Mục "Dọn tài nguyên tải thử rồi không dùng" cho dọn bớt (luôn hỏi lại, chọn được
từng cái, không có nút "xoá tất cả" ép chọn).

---

## 9. Cân bằng âm thanh

Trong màn làm việc của dự án (mục 2-5) → khối **"Cân bằng âm thanh"** → **"Đo & cân
bằng"**, hoặc từ modal riêng khi có nhiều draft. Chuẩn dùng: **EBU R128** — giọng nói
−14 LUFS, SFX −16 LUFS, nhạc nền −30 LUFS, trần true peak −1 dBTP (chuẩn phát sóng).

1. Chọn draft → **Đo lại** để xem bảng LUFS từng nguồn tiếng (hay lệch nhau rất nhiều,
   có case đo được lệch ~18 dB giữa các SFX).
2. Ưng thì bấm **"Cân bằng & ghi vào draft"** — có xác nhận trước, tự tạo bản backup
   `.prebalance.bak`, và **chặn nếu draft đang mở trong CapCut**.

---

## 10. Cài đặt API key

Thanh bên trái → **Cài đặt**. Dán key vào đúng ô nhà cung cấp, bấm **Lưu và áp dụng** —
dùng được ngay, không cần khởi động lại app. Key lưu trong file `.env` ngay trên máy
bạn, app không gửi đi đâu khác.

| Key | Bắt buộc | Dùng để |
|---|---|---|
| `GEMINI_API_KEY` | **Bắt buộc** | Trích chủ đề, chấm điểm, làm sạch transcript, chọn hook/SFX/B-roll, sửa caption. Thiếu thì khoá hẳn nút Phân tích |
| `PEXELS_API_KEY` | Tuỳ chọn | Tải video stock làm B-roll. Không có thì draft vẫn dựng bình thường, chỉ thiếu lớp B-roll |
| Gemini — nhiều key | Tuỳ chọn | Xoay key khi cạn hạn ngạch (RPD) — chỉ có tác dụng nếu các key thuộc **project Google khác nhau**, vì Google tính hạn ngạch theo project chứ không theo key |

---

## Toàn bộ quy trình, tóm tắt một mạch

```
Tạo dự án → Gắn record → (tuỳ chọn: chọn lớp tài nguyên) → Phân tích
   → xem danh sách Chủ đề có chấm điểm → Xem trước (nghe 40s, đọc tóm tắt)
   → chọn gu editor → Tạo draft → Mở CapCut sửa tay → lưu, đóng draft
   → Chụp mốc (làm SỚM, ngay sau khi dựng) → Editor sửa gì → Đồng bộ về kho
   → Cân bằng âm thanh → xong, video là dự án CapCut hoàn chỉnh, xuất bình thường
     trong CapCut như mọi dự án khác.
```

---

## Mẹo & xử lý sự cố thường gặp

| Gặp gì | Vì sao | Làm gì |
|---|---|---|
| Nút Phân tích bị khoá, có chữ đỏ | Thiếu `GEMINI_API_KEY` | Vào Cài đặt dán key |
| Cảnh báo đỏ "Không thấy ffmpeg" trên Home | Máy thiếu ffmpeg (hiếm — bản cài đặt đã bundle sẵn) | Cài lại bằng bản `CapCutAuto-Setup-*.exe` mới nhất |
| Tạo/ghi draft báo `.locked` | Draft đó đang mở trong CapCut | Đóng draft đó trong CapCut (về màn hình danh sách), thử lại |
| "Editor sửa gì" bị khoá | Chưa Chụp mốc cho draft đó | Bấm Chụp mốc trước, rồi mới sửa trong CapCut |
| Phân tích lại ra chủ đề khác hẳn lần trước | Bình thường — Gemini không đảm bảo ra y hệt mỗi lần | Draft cũ đã dựng không bị ảnh hưởng, vẫn dùng được |
| Job Phân tích báo lỗi liên quan CUDA/DLL | Card đồ hoạ có nhưng thiếu thư viện CUDA cần thiết | Từ `v1.0.4`: app tự thử lại trên CPU, không cần làm gì thêm |
| Gỡ cài đặt | Xoá LUÔN kho tài nguyên đã học, các dự án, API key đã lưu | Hộp thoại gỡ cài đặt đã nói rõ trước — cân nhắc kỹ, không có cách khôi phục lại |

---

## Có thể bạn chưa biết — chế độ Agent chat

Ngoài thao tác bằng nút bấm, thanh bên trái có nút **"Agent chat"** — chat tiếng Việt
với app để hỏi/ra lệnh thay vì bấm nút (ví dụ: "Tôi đang có những dự án nào?", "Kho có
gì của Nguyên?", "Draft nào chưa chụp mốc?"). Đây là **cùng một dữ liệu, khác cách nhìn**
— dùng cách nào tuỳ thói quen, không có gì làm được ở chat mà không làm được bằng nút và
ngược lại.
