# Phiếu chấm — chạy thử trên máy khác (mục B5)

Đây là **mục chặn phát hành duy nhất còn lại**. Mọi con số khác trong dự án đều đo trên
đúng một máy, nên buổi này mới là bằng chứng thật.

## Mang gì đi

`capcut-auto-v1.zip` (**4,5 MB · 159 file**, tạo bằng `git archive`; đo 27/07/2026 trên máy
trạm). Gói này **cố ý không có**: `.env` (key), `library.db`, `assets/user/`, `snapshots/`,
`shorts/work/` (1,4 GB), `.venv/`.

Có sẵn: mã nguồn, **55 SFX mặc định**, **draft mẫu `assets/donor/282new` (39 file)**,
`cai_dat.bat`, `chay.bat`, smoke test.

> Draft mẫu nằm trong gói là điều kiện SỐNG CÒN, không phải chi tiết phụ: thiếu nó thì
> build chạy hết 10 phút rồi mới chết. Kiểm lại sau mỗi lần tạo gói:
> `python -c "import zipfile;print(sum('assets/donor/' in n for n in zipfile.ZipFile('capcut-auto-v1.zip').namelist()))"`
> — phải ra **39**, không phải 0.

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
| 1 | `cai_dat.bat` chạy hết | Không dừng giữa chừng, in `[OK] Thu vien` | ✅ ĐẠT — chạy hết, tự tạo 5 thư mục dữ liệu (`assets/user`, `snapshots`, `shorts/work`, `renders`, `quarantine`) |
| 2 | Báo ffmpeg | Có ffmpeg → `[OK] ffmpeg`; không có → **báo rõ**, không im lặng | ✅ ĐẠT — `[OK] ffmpeg`. Nhánh THIẾU ffmpeg **chưa thử** trên máy này |
| 3 | Smoke test cuối script | **0 failed** trên tổng 23 bài. Đừng chấm bằng số `passed`: vài bài tự skip khi máy chưa có editor/dự án trong kho, nên máy sạch ra `20 passed, 3 skipped` còn máy đã dùng ra `21 passed, 2 skipped` — cả hai đều ĐẠT | ✅ ĐẠT — `20 passed, 3 skipped`, 0 failed |
| 4 | Thời gian từ giải nén tới mở được app | **≤ 15 phút** | ✅ ĐẠT — **0,9 phút**. ⚠️ Máy này ĐÃ có sẵn Python 3.13.9 + ffmpeg + cache pip. Máy trắng đúng nghĩa (tiêu chí C1) **chưa đo** |
| 5 | Dò CapCut | Tab **Draft** hiện đúng thư mục draft của máy đó | ✅ ĐẠT — `C:\Users\user\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft`, thấy 46/46 draft |
| 6 | Nhập key | Lưu xong dùng được **ngay**, không phải khởi động lại | 🟡 MỘT PHẦN — `.env` đã do chính app ghi (2 key), nhưng chưa xem tận mắt luồng nhập-rồi-dùng-ngay |
| 7 | Thiếu key | Trước khi nhập key: nút *Phân tích* bị khoá, có giải thích | 🟡 Khoá nút thì ĐÚNG, nhưng **lời giải thích SAI**: `ui.html` bảo "Đóng app, mở lại bằng `set GEMINI_API_KEY=...`" trong khi B3 đã có mục **Cài đặt**. Đúng người dùng đích là người không biết `set` |
| 8 | Phân tích record | Ra ≥ 1 chủ đề; log chạy có tiến trình thật | ✅ ĐẠT **sau khi đặt `CT2_THREADS=4`** (xem mục sập bên dưới). Record 58 phút → 100 segment trong **3:58 (14,5x realtime)** trên CPU → **3 chủ đề** (7,1 · 6,6 · 5,7). Log có mốc `(57:26/57:42)` |
| 9 | Dựng draft | CapCut mở **không đòi chọn lại đường dẫn** | ✅ ĐẠT ở mức dữ liệu — `dangling: 0`, và **23/23 file được tham chiếu đều CÓ THẬT trên đĩa** (kiểm riêng, vì `dangling` chỉ soi tham chiếu nội bộ). Chưa mở CapCut nhìn tận mắt |
| 10 | **Draft có SFX** | Nghe thấy tiếng động — đây là thứ vừa sửa (B1) | ✅ ĐẠT — **9 SFX** chèn vào 1 track, **cả 9 đều lấy từ `assets/` (kho đi theo app)** và đều tồn tại trên đĩa. Đây là bằng chứng đầu cuối cho bản vá B1 |
| 11 | Draft có caption | Có chữ chạy, đúng chính tả | ✅ ĐẠT — **177 segment text**, `caption-fix` sửa **77/77 dòng** bằng Gemini. Chính tả chưa soi từng dòng |
| 12 | Vòng học | *Editor sửa gì* ra đúng thứ vừa sửa; có **% ĐỘ PHẢI SỬA** | 🟡 ĐANG DỞ — đã *Chụp mốc* `test_t1_shared`, diff nền = 0 thay đổi. Chờ người mở CapCut sửa tay rồi chạy *Editor sửa gì* |
| 13 | Kho tài nguyên | Tab **Tổng quan** → *Quét tài nguyên* ra đúng số gói của máy đó | ✅ ĐẠT — 260 gói / 314 MB (2 đã dùng · 258 chưa dùng · 31 module nội bộ), phân loại theo 6 nhóm |
| 14 | Agent chat | Hỏi "tôi có những dự án nào" → trả lời đúng | ✅ ĐẠT — gọi đúng tool `liet_ke_du_an`, trả lời đúng thực tế (máy này 0 dự án) và mời phân tích record mới |
| 15 | Việc phá huỷ | Bảo agent dựng lại chủ đề đã dựng → **hiện thẻ xác nhận**, không tự chạy | ✅ ĐẠT cả hai lối. Nút *Tạo draft* lần 2 → thẻ "GHI ĐÈ / Huỷ" nói rõ mất phần sửa tay. Agent: gọi tool `dung_draft` nhưng tool trả `can_xac_nhan: true`, `ghi_chu: "CHƯA chạy"` → chỉ đề xuất, chờ người bấm |
| 16 | Mất mạng | Rút mạng → banner đỏ "Mất kết nối", app không chết | ✅ ĐẠT — tắt server: banner đỏ hiện sau 3 lượt trượt liên tiếp (ngưỡng cố ý, tránh nhấp nháy khi bóc lời); bật lại: banner tự tắt, không phải tải lại trang |

## 🔴 LỖI MỚI, NẶNG NHẤT — draft TRỘN nội dung hai lần phân tích

**Đo 27/07/2026.** Triệu chứng người dùng thấy: caption, SFX, B-roll đúng chủ đề mới,
nhưng hình và tiếng bên dưới là của chủ đề khác hẳn — nghe như "tiếng của record cũ".

**Cơ chế.** `reframe_t{N}.mp4` và `enrich_{NN}.json` khoá theo **chỉ số chủ đề**. Bấm
*Phân tích* lại thì transcript lấy từ cache nên không đổi, nhưng Gemini **không tất định**
→ trả về danh sách chủ đề KHÁC. "Chủ đề 1" giờ trỏ sang đoạn khác, mà file cũ vẫn còn nên
được tái dùng nguyên xi.

Bằng chứng đo bằng tương quan chéo tiếng với record gốc:

| Chủ đề | `topics.json` khai | Tiếng thật trong reframe | reframe tạo lúc | |
|---|---|---|---|---|
| 1 | 890–984s | **816s** | 12:20 (lần phân tích TRƯỚC) | **lệch 74s — SAI ĐOẠN** |
| 2 | 1948–2000s | 1940s | 12:39 (sau khi phân tích lại) | khớp |
| 3 | 194–257s | 188s | 12:38 (sau khi phân tích lại) | khớp |

**Lỗ hổng cùng lớp, tìm ra khi truy nguyên:** `transcribe.slug()` khoá thư mục làm việc
theo **tên file**, bỏ hết đường dẫn — hai record khác nhau cùng tên `test.mp4` dùng chung
`shorts/work/test/`, và mọi cache trong đó (kể cả `audio.wav`) tái dùng lẫn nhau.

Cả hai là **một lớp lỗi**: định danh cache bằng thứ dễ trùng (thứ tự, tên file) thay vì
bằng nội dung. Ý định cache thì đúng — comment gốc ghi rõ là để Đan/Nguyên cùng chủ đề
khỏi render lại.

**Đã sửa 27/07:**
- `build_short_draft.khoa_khoang_cat()` — băm **nguồn + khoảng cắt** thành khoá cho video
  nền, B-roll và thư mục tạm. Khoảng cắt đổi → file khác; giống nhau → vẫn dùng chung,
  giữ nguyên lợi ích ban đầu.
- `enrich.khoa_chu_de()` — băm **tiêu đề + khoảng thời gian** của chủ đề.
- `transcribe._khoa_nguon()` — ghi `nguon.json` trong thư mục làm việc, đối chiếu
  **kích thước byte** trước khi dùng bất kỳ cache nào; lệch thì ném `NguonKhongKhop` kèm
  hướng xử lý. Dùng kích thước chứ không dùng đường dẫn để người dùng dời record không bị
  chặn nhầm. **Không đổi cách đặt tên thư mục** nên draft cũ không hỏng.
- `caption_fix` — cache cộng dồn theo id dòng, chỉ gọi Gemini cho phần còn thiếu, thay vì
  trả nguyên khối rồi để chủ đề mới rơi về text ASR thô mà không báo.

## 🔴 LỖI MỚI, CHẶN PHÁT HÀNH — app SẬP CỨNG khi bóc lời trên CPU

**Đo 27/07/2026, máy trạm i7-12700 (12 nhân / 20 luồng).** Đây là thứ B5 sinh ra để bắt:
máy dev chạy CUDA nên **chưa bao giờ đi vào nhân CPU của CTranslate2**; máy này driver cũ
→ lùi CPU → sập ngay đường code chưa ai đặt chân.

Triệu chứng: `python.exe` chết trong `ctranslate2.dll`, mã `0xC00000FD` (**stack overflow**),
kéo theo cả web server. Không có exception Python, **không dòng lỗi nào trong log job** —
trình duyệt chỉ hiện banner "Mất kết nối". Đúng kiểu hỏng im lặng mà luật cứng #2 cấm.
Windows Event Log ghi 2 lần (11:23 và 11:51), tức **tái hiện được**, không phải rủi ro.

Ma trận đo được (file `audio.wav` 58 phút, model `small`, batched + VAD):

| Độ dài | `cpu_threads` | Kết quả |
|---|---|---|
| 300s | 9 | OK — 12,6x realtime |
| 600s | 9 | **SẬP** stack overflow |
| 1200s | 9 | **SẬP** stack overflow |
| FULL | 9 | **SẬP** (cả ở LUỒNG CHÍNH — nên KHÔNG phải do `run_job` chạy luồng phụ) |
| FULL | **4** | **OK — 230s (15,0x realtime)** ← nhanh nhất |
| FULL | 1 | OK — 474s (7,3x realtime) |

**Nguyên nhân gốc:** `transcribe._luong_cpu()` dùng `mp.cpu_count() // 2 - 1`. Docstring nói
hàm trả về *số nhân thật*, nhưng công thức chỉ đúng khi mọi nhân đều siêu phân luồng đồng
nhất — như máy dev 4 nhân/8 luồng (ra 3). i7-12700 là **nhân lai**: 8 P-core có HT + 4
E-core không HT = 12 nhân / 20 luồng → công thức ra **9**, và 9 làm tràn stack.

**Điểm mấu chốt: 4 luồng vừa AN TOÀN vừa NHANH NHẤT.** Không phải đánh đổi tốc độ lấy ổn
định — cấu hình cũ vừa sập vừa chậm hơn. Khớp đúng số liệu trong chính docstring của
`_luong_cpu()`: nhồi luồng vào batched inference là hại.

**Đã sửa 27/07:** `transcribe.TRAN_LUONG = 4` chặn trần trong `_luong_cpu()`. Máy dev
(4 nhân/8 luồng) vẫn ra 3 như cũ nên không đổi gì; máy nhân lai ra 4 thay vì 9. Chữa tạm
`CT2_THREADS=4` trong `.env` đã **gỡ bỏ** — để lại thì nó che mất lỗi hồi quy sau này.

**Việc phụ đi kèm — đã sửa:** ô chọn file hiện `xử lý ~2 phút`, tính bằng `eta_min =
dur/30/60` — hằng số **30x realtime đo trên GPU máy dev**, đóng cứng cho mọi máy. Máy này
đo được 14,5x → hứa 2 phút, bắt ngồi 4 phút. Giờ `transcribe.ghi_toc_do()` lưu tốc độ đo
được sau mỗi lần bóc lời và `toc_do_asr()` trả về cho giao diện; chưa đo lần nào thì đoán
dè dặt 10x (thà báo lâu hơn thực tế).

## Xác nhận lại 2 lỗi đã vá (đo 27/07/2026, máy trạm)

**1. Draft mẫu `282new` có đi theo app không — ĐÃ VÁ, xác nhận.**
Ba tầng đều kiểm được: `git ls-files` thấy 32 file; gói `git archive` chứa 39 file kể cả
`draft_content.json`; giải nén ra thư mục sạch vẫn còn nguyên. Builder tìm
`assets/donor/` TRƯỚC thư mục CapCut (`capcut_build._duong_dan_mau`), và
`build_short_draft` gọi `cb.kiem_tra_draft_mau()` ngay đầu nên thiếu là báo ở giây đầu
chứ không phải phút thứ 10.

> Còn một khoản nợ, **không chặn v1**: `capcut_build.build()` (đường CLI cũ) vẫn cần donor
> `"0720"` — thứ KHÔNG có trong `assets/donor/`. App không đi qua đó (`app.py` → 
> `build_short_draft`, dùng `282new` cho cả hai vai). Ai chạy `capcut_auto.py build` trên
> máy khác sẽ dính lại đúng lỗi cũ.

**2. Cạn hạn ngạch Gemini có giết cả lượt build không — VÁ MỘT NỬA.**
Phần đã tốt: chuỗi `FALLBACKS` nay có 2 model RPD 500 ở cuối, và **cả 6 model đều tồn tại
thật** với tài khoản máy này (`client.models.list()` — quan trọng vì tiền lệ
`gemini-3-flash` từng trả 404 làm cả cơ chế dự phòng thành vô dụng). Vòng thử lại cũng
không `sleep` dài trong một lượt gọi: gặp 429 là đánh dấu key nghỉ rồi sang key/model
khác, nên không có kiểu "treo giả".

Phần CHƯA tốt: **chỉ `agent.py` bắt `HetHanNgach`**. Trong luồng build,
`enrich_topic()` ném thẳng qua `build_short_draft.py:108` và làm hỏng cả lượt. Nghĩa là
cạn hạn ngạch giờ *hiếm hơn nhiều* chứ **kiểu chết thì y nguyên**. Giảm nhẹ: lỗi hiện
đúng nguyên nhân tiếng Việt trong log job, và transcript/reframe/enrich đều có cache nên
chạy lại sau khi hạn ngạch reset là chạy tiếp chứ không làm lại từ đầu.

> **Bằng chứng thực địa (27/07):** trong đúng một lượt chạy thật, chuỗi dự phòng nhảy
> `gemini-2.5-flash → gemini-3.5-flash` **ba lần** (trích chủ đề, enrich, caption-fix) và
> lượt việc vẫn ra kết quả. Trước bản vá, cả ba chỗ đều nằm trong nhóm RPD 20 nên đây
> chính là kịch bản từng làm chết build ở phút thứ 10.

Đáng làm tiếp: bắt `HetHanNgach` quanh `enrich_topic` và **dựng draft trơn** (không hook/
emoji/SFX/B-roll) kèm cảnh báo rõ, thay vì mất trắng. Enrich là đồ tô điểm, không phải
xương sống — mất nó không đáng để mất cả draft.

## Chỗ tôi đoán là dễ hỏng nhất

1. **ffmpeg** chưa có trong PATH → app mở được nhưng không dựng được draft.
2. **Mạng công ty chặn PyPI** → `cai_dat.bat` chết ở bước cài thư viện (344 MB).
   Phòng trước: chép sẵn cả thư mục **kèm `.venv`** từ máy dev ra USB.
3. **GPU khác/không có GPU** → bóc lời chạy CPU, chậm hơn ~5 lần nhưng vẫn phải chạy.
4. **Máy chưa cài CapCut** → phải báo rõ ở tab Draft chứ không được crash.

## Cách báo lại

Mục nào không đạt: chụp màn hình + **chép nguyên văn dòng lỗi** trong cửa sổ đen của
`chay.bat`. Smoke test đỏ thì chép cả tên bài test — nó chỉ thẳng chỗ hỏng.
