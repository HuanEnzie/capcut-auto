# Quy tắc thiết kế giao diện

Nguồn chân lý: **`docs/DESIGN.md`** (Duolingo style reference).
Toàn bộ token đã được chép vào khối `:root{}` đầu file `ui.html`.

> **Sửa giao diện thì sửa token trước.** Đừng hardcode màu/kích thước rải rác —
> đổi một chỗ trong `:root` phải kéo theo cả app.

---

## 1. Bảng màu và vai trò

| Token | Mã | CHỈ dùng cho |
|---|---|---|
| `--color-eager-green` | `#58cc02` | Nền nút CHÍNH, trạng thái "xong", bong bóng chat của người dùng |
| `--color-storybook-green` | `#d7ffb8` | Nền nhạt: tab đang chọn, đầu khối dự án đang mở |
| `--color-spark-blue` | `#1cb0f6` | Chữ của link và **nút PHỤ** |
| `--color-charcoal` | `#4b4b4b` | Chữ chính, số liệu lớn |
| `--color-pencil-gray` | `#777777` | Chữ phụ, nhãn, tiêu đề mục |
| `--color-faded-gray` | `#afafaf` | Viền phần tử tương tác, trạng thái vô hiệu |
| `--color-hairline` | `#e5e5e5` | *(mở rộng)* Viền bề mặt lớn — thẻ, bảng |
| `--color-danger` | `#e5533d` | *(mở rộng)* Lỗi, tài nguyên bị gỡ |

**Hai token mở rộng ngoài `DESIGN.md`, có lý do:** spec chỉ cấp `#afafaf` cho viền. Dùng
`2px #afafaf` cho *mọi* thẻ và bảng thì mặt giao diện nặng và ồn. Nên giữ `#afafaf` đúng spec
cho **phần tử tương tác** (nút, input, pill), còn **bề mặt lớn** dùng hairline nhạt hơn.
Spec cũng không có màu báo lỗi — thêm `--color-danger`.

## 2. Ba luật bất di bất dịch (từ mục Don'ts của spec)

1. **Không góc nhọn.** Mọi thứ bo `--radius: 12px`, kể cả tag nhỏ nhất.
2. **Không gradient, không đổ bóng, không glass.** Bề mặt phẳng, phân tách bằng **viền 2px** —
   cảm giác "sticker dán lên giấy".
3. **Không tô màu chữ nội dung.** Chữ đọc giữ `charcoal`/`pencil-gray`. Xanh lá dành cho tiêu
   đề lớn và nền nút; xanh dương dành cho link và nút phụ.

## 3. Phân cấp nút — luật quan trọng nhất về trải nghiệm

| Loại | Class | Dùng khi |
|---|---|---|
| Chính | `.btn` (nền xanh lá) | **Tối đa 1 cái cho mỗi khu vực màn hình** |
| Phụ | `.btn.ghost` (chữ xanh dương, viền) | Hành động trong dòng bảng, thao tác lặp lại |
| Nguy hiểm | `.btn.danger` | Xoá, huỷ bỏ |

> **Đã trả giá cho luật này.** Bản đầu để nút "Tạo draft" của cả 26 chủ đề đều là nút chính
> xanh đậm → 26 thứ cùng hét lên, mắt không biết nhìn đâu, và nút "Phân tích" thật sự quan
> trọng thì chìm nghỉm. Chuyển hành động trong bảng sang nút phụ là phân cấp trở lại rõ ràng.

## 4. Chữ

- Font: **Nunito** (thay cho `feather`/`duolingo-sans` của spec — đúng danh sách thay thế spec
  đề xuất). Có `<link>` Google Fonts, mất mạng thì tự lùi về font hệ thống.
- Tiêu đề mục (`h2`): **15px, IN HOA, weight 700, letter-spacing 0.053em**, màu `pencil-gray`.
  Spec dành kiểu chữ này cho nhãn điều hướng — trong app dùng làm nhãn khu vực.
- Số liệu lớn trong thẻ: 32px weight 800.
- Nội dung bảng: 13px (`--text-caption`) — spec để body 17px, nhưng bảng dữ liệu dày mà 17px
  thì phải cuộn ngang liên tục.
- **Không dùng cỡ chữ display (48-64px) trong app** — spec cấm dùng font display dưới 48px, mà
  app công cụ thì không có chỗ cho chữ 48px.

## 5. Không dùng hộp thoại của trình duyệt

`alert()` / `confirm()` / `prompt()` **bị cấm** — chặn luồng, xấu, không style được, không
dịch được. Thay bằng:

| Thay cho | Dùng | Ghi chú |
|---|---|---|
| `alert()` | `toast(msg, bad?)` | Góc phải dưới, tự tắt |
| `confirm()` | `await confirmBox(title, body)` | Trả `true`/`false` |
| `prompt()` | `await modal({title, body, actions})` | Cho chọn bằng NÚT, đừng bắt gõ chữ |

Modal đóng được bằng **Esc** hoặc bấm ra ngoài, giữ tiêu điểm bên trong khi Tab, và
**trả tiêu điểm về đúng nút vừa bấm** khi đóng.

> **Tiêu điểm không bao giờ rơi vào nút phá huỷ.** `modal()` tự focus hành động
> không-`danger` đầu tiên. Hộp "Dựng lại sẽ ghi đè draft cũ" mà focus sẵn nút *Ghi đè*
> thì một phát Enter theo phản xạ là mất bản editor vừa ngồi sửa cả buổi.
> Hộp chỉ để xem (xem trước chủ đề) thì focus vào **khung hộp**, không vào nút nào.

## 6. Trạng thái phải luôn có

Mỗi khu vực tải dữ liệu cần đủ 4 trạng thái:

1. **Đang tải** — `skeleton(n)`, đừng để trắng trơn.
2. **Rỗng** — `emptyBox(tiêu đề, gợi ý)`, phải nói người dùng **làm gì tiếp**.
3. **Có dữ liệu** — bình thường.
4. **Lỗi** — toast đỏ hoặc chữ `.neg`, nói rõ lỗi gì.

Nút bị vô hiệu **phải có `title=` giải thích tại sao** (vd `title="Cần chụp mốc trước"`).

**Cách thi hành — 3 hàm, dùng cho mọi khu vực:**

| Hàm | Việc |
|---|---|
| `guard('#tab', loader)` | Loader ném lỗi thì vẽ hộp lỗi + nút **Thử lại** (`RETRY`), thay vì để skeleton nằm lại vĩnh viễn — trông y hệt app treo |
| `busy(btn, 'Đang…', fn)` | Khoá nút suốt lúc chạy. Bấm hai lần "Tạo draft" là dựng đè lên chính nó; hai lần "Phân tích" là hai job giành cùng một GPU |
| `api(url, opt)` | Lỗi **mạng** quy về banner `#offline` chung. App đóng gói thì cửa sổ python có thể bị tắt — không báo thì mọi nút chỉ "im lặng không làm gì" |

**Không cắt bớt trong im lặng.** Bảng cắt còn 25 dòng thì phải ghi `Hiện 25/43` kèm nút
*Xem tất cả* — nhìn 25 dòng mà tưởng kho chỉ có ngần đó là app nói dối.

## 7. Ba mẫu bắt buộc cho việc chạy lâu và dữ liệu "khó hình dung"

**a. Việc chạy lâu phải có tiến trình THẬT, và theo người dùng đi khắp app.**
Pipeline vốn đã in `(1:19:06/3:55:06)` và tên từng giai đoạn — `jobProgress()` đọc ra để vẽ
thanh %. Chỉ báo nằm ở **header** nên thấy được ở mọi tab, kể cả chế độ Agent; bấm vào là nhảy
về đúng khu tiến trình. Xong thì có toast + thông báo trình duyệt + đổi tiêu đề tab.
> Trước đây chỉ hiện 4 dòng log trong tab Dự án. Người dùng chạy 30 phút rồi phải hỏi
> "sao chưa xong" — đó là hỏng thiết kế, không phải hỏng backend.

**b. Bắt người dùng chọn thì phải cho họ xem/nghe trước.**
Chủ đề có nút **Xem trước**: điểm từng tiêu chí, khoảng thời gian, tóm tắt, góc hook,
**nghe thử 40 giây**, trích transcript có mốc giờ, và nút tạo draft ngay tại chỗ.
Trước đó chọn 1 trong 16 chủ đề mà chỉ nhìn tiêu đề + điểm là **chọn mù**.

**c. Tài nguyên hình ảnh thì phải hiện hình.**
Kho có cột ảnh (`/api/asset/{id}/thumb` lấy `singleImage.png`/`final.gif` trong gói effect).
Chỉ gọi ảnh cho loại **thực sự có** hình (`THUMBABLE`); `audio`/`font` vẽ ký hiệu `♪`/`Aa`.
> Gọi ảnh cho mọi loại thì server trả 404 hàng loạt — bẩn console, tốn request vô ích.
> (Đã giảm từ 17 xuống 2 lỗi 404.)

## 8. Việc có thể làm hỏng dữ liệu thì phải chặn TRƯỚC

`build_short_draft.py` **ghi đè draft tại chỗ**. Nên tab Dự án hiện cột **Đã dựng** (tên
editor đã có draft cho chủ đề đó) và nút *Tạo draft* hỏi lại trước khi đè.

Hai luật rút ra:

1. **Hỏi trước khi ghi đè công của người khác** — nêu rõ *đã dựng lúc nào* và *mất cái gì*.
2. **Điều kiện biết trước thì chặn ngay ở nút, đừng để job chạy rồi mới báo.** Draft đang
   mở trong CapCut (`.locked`) là biết ngay từ `/api/projects` và `/api/drafts` — chặn lúc
   bấm, thay vì để build chạy 3 phút rồi mới `sys.exit` vì `.locked`. Tương tự: thiếu
   `GEMINI_API_KEY` thì khoá luôn nút *Phân tích* (bóc lời 15 phút GPU xong mới chết ở
   bước trích chủ đề là kiểu hỏng tệ nhất).

## 9. Chạy được khi KHÔNG có mạng (điều kiện để đóng gói)

- **Font đóng gói kèm app** ở `assets/fonts/` (Nunito 500/700/800, tập latin + vietnamese,
  153 KB), khai báo `@font-face` ngay trong `ui.html`, FastAPI mount `/static/fonts`.
  Không dùng Google Fonts: CSS của nó **chặn render**, máy không mạng sẽ trắng trang tới
  lúc DNS timeout. `font-display:swap` để chữ hiện ngay bằng font hệ thống.
- **Favicon là SVG data-URI** trong `<link rel=icon>` — không thêm request, không 404.
- **Không hardcode đường dẫn của máy dev.** Thư mục record mặc định do server chọn
  (`default_record_dir()`), UI nhớ lựa chọn lần trước.
- **Banner `#offline`** khi mất kết nối tới server, tự tắt khi gọi lại được.

## 10. Khác

- **Danh sách dài thì gập lại.** Dự án dùng `<details class="proj">`, chỉ mở sẵn cái đầu.
  Trước khi gập, tab Dự án dài 2429px; sau khi gập còn ~1100px.
- **Điều khiển ảnh hưởng danh sách dài phải dính trên** (`.row.sticky`) — cuộn xuống chủ đề
  thứ 16 mà không thấy đang chọn gu editor nào thì rất dễ bấm nhầm.
- **Bảng luôn bọc trong `.wrap`** để cuộn ngang được trên màn hình hẹp.
- `:focus-visible` viền xanh dương 3px — đừng tắt outline.
- Sáng-only theo spec (`theme: light`). Cần chế độ tối thì phải bổ sung bảng màu tối vào
  `DESIGN.md` trước, không tự chế.
- **Hành động trong bảng đi qua `data-act`**, không dùng `onclick="fn('${name}')"`: tên
  draft có dấu nháy là vỡ handler, và chuỗi từ server không nên biến thành mã chạy được.
  `esc()` escape cả `"` và `'` vì các chuỗi đó nằm trong thuộc tính HTML.
- **Nhớ lựa chọn của người dùng** bằng `PREF` (localStorage): thư mục record, gu editor,
  độ chính xác ASR, tab + chế độ đang xem, draft đang đo. Bắt chọn lại mỗi lần mở app là
  bắt họ làm việc không công, ngày mấy chục lần.
- **Việc chạy lâu báo bằng thời gian, không bằng phần trăm.** `jobProgress()` suy ETA từ
  tốc độ thật của máy (`elapsed × còn lại / đã xong`) → "còn ~12 phút". Giai đoạn không
  có mốc thời gian (Gemini trích chủ đề) phải có nhãn riêng, đừng để thanh đứng im ở
  "bóc lời 3:55:06 / 3:55:06" — nhìn y như treo.
- **Xong việc thì màn hình tự đúng.** Job xong: vẽ lại tab đang mở, đo lại LUFS sau khi
  ghi (`JOB_DONE_CB`, đợi job xong THẬT chứ không `setTimeout` đoán mò).
