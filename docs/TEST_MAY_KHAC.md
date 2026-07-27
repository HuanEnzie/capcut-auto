# Phiếu chấm — chạy thử trên máy khác (mục B5)

Đây là **mục chặn phát hành duy nhất còn lại**. Mọi con số khác trong dự án đều đo trên
đúng một máy, nên buổi này mới là bằng chứng thật.

## Mang gì đi

`capcut-auto-v1.zip` (**4,3 MB**, tạo bằng `git archive`). Gói này **cố ý không có**:
`.env` (key), `library.db`, `assets/user/`, `snapshots/`, `shorts/work/` (1,4 GB), `.venv/`.
Có sẵn: mã nguồn, **55 SFX mặc định**, `cai_dat.bat`, `chay.bat`, smoke test.

Tạo lại bất cứ lúc nào: `git archive --format=zip -o capcut-auto-v1.zip HEAD`

## Làm theo thứ tự

1. Giải nén ra thư mục bất kỳ (đường dẫn **không dấu tiếng Việt** cho chắc).
2. Bấm đúp `cai_dat.bat`.
3. Bấm đúp `chay.bat`.
4. Trong app: **Cài đặt** → dán 2 key → *Lưu và áp dụng*.
5. **Dự án** → *Thêm record mới* → Quét → chọn file → *Phân tích*.
6. Chọn một chủ đề → *Tạo draft* → mở draft đó trong CapCut.
7. **Draft** → *Chụp mốc* → sửa vài thứ trong CapCut → lưu, **đóng draft** → *Editor sửa gì*.

## Phiếu chấm

| # | Kiểm tra | Đạt khi | Kết quả |
|---|---|---|---|
| 1 | `cai_dat.bat` chạy hết | Không dừng giữa chừng, in `[OK] Thu vien` | |
| 2 | Báo ffmpeg | Có ffmpeg → `[OK] ffmpeg`; không có → **báo rõ**, không im lặng | |
| 3 | Smoke test cuối script | `19 passed` | |
| 4 | Thời gian từ giải nén tới mở được app | **≤ 15 phút** | |
| 5 | Dò CapCut | Tab **Draft** hiện đúng thư mục draft của máy đó | |
| 6 | Nhập key | Lưu xong dùng được **ngay**, không phải khởi động lại | |
| 7 | Thiếu key | Trước khi nhập key: nút *Phân tích* bị khoá, có giải thích | |
| 8 | Phân tích record | Ra ≥ 1 chủ đề; log chạy có tiến trình thật | |
| 9 | Dựng draft | CapCut mở **không đòi chọn lại đường dẫn** | |
| 10 | **Draft có SFX** | Nghe thấy tiếng động — đây là thứ vừa sửa (B1) | |
| 11 | Draft có caption | Có chữ chạy, đúng chính tả | |
| 12 | Vòng học | *Editor sửa gì* ra đúng thứ vừa sửa; có **% ĐỘ PHẢI SỬA** | |
| 13 | Kho tài nguyên | Tab **Tổng quan** → *Quét tài nguyên* ra đúng số gói của máy đó | |
| 14 | Agent chat | Hỏi "tôi có những dự án nào" → trả lời đúng | |
| 15 | Việc phá huỷ | Bảo agent dựng lại chủ đề đã dựng → **hiện thẻ xác nhận**, không tự chạy | |
| 16 | Mất mạng | Rút mạng → banner đỏ "Mất kết nối", app không chết | |

## Chỗ tôi đoán là dễ hỏng nhất

1. **ffmpeg** chưa có trong PATH → app mở được nhưng không dựng được draft.
2. **Mạng công ty chặn PyPI** → `cai_dat.bat` chết ở bước cài thư viện (344 MB).
   Phòng trước: chép sẵn cả thư mục **kèm `.venv`** từ máy dev ra USB.
3. **GPU khác/không có GPU** → bóc lời chạy CPU, chậm hơn ~5 lần nhưng vẫn phải chạy.
4. **Máy chưa cài CapCut** → phải báo rõ ở tab Draft chứ không được crash.

## Cách báo lại

Mục nào không đạt: chụp màn hình + **chép nguyên văn dòng lỗi** trong cửa sổ đen của
`chay.bat`. Smoke test đỏ thì chép cả tên bài test — nó chỉ thẳng chỗ hỏng.
