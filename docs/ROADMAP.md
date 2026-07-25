# Lộ trình: từ công cụ dựng draft → nền tảng biên tập tự tiến hoá

> Bốn mục tiêu người dùng đặt ra: (1) editor tự động, tự học, tự tiến hoá · (2) quản lý
> project + tài nguyên CapCut bằng dashboard · (3) agent tư vấn dài hạn · (4) không dừng
> ở một phiên bản, sau này tách khỏi CapCut cũng được.
>
> Tài liệu này soi từng mục: **đang có gì, thiếu gì, làm theo thứ tự nào và vì sao**.

---

## 0. Số liệu làm nền (đo trên máy dev, 25/07/2026)

| Đo | Kết quả | Ý nghĩa |
|---|---|---|
| Gói trong cache CapCut | 354 · 448 MB | `Cache/effect` + `Cache/artistEffect` |
| — trong đó **tài nguyên thật** (ID 19 số) | **319 · 353 MB** | sticker / hiệu ứng chữ / transition / effect |
| — module nội bộ (ID ≤12 số) | 35 · 95 MB | `star`, `mirror`, `linear`, `rect`… KHÔNG phải tài nguyên, phải loại khỏi thống kê |
| Từng được dùng thật trong draft | **19** | Đối chiếu `resource_id` qua 25 draft |
| Kho app đã học được | 43 (Đan 26 / Nguyên 17) | Chỉ học từ draft, chưa đụng tới cache |
| Draft đã dựng | 25 | Chưa có trạng thái vòng đời nào |

### Cache đến từ đâu — kiểm chứng trước khi xây dashboard trên nó

`C:\Program Files\CapCut` gần như rỗng: **không tài nguyên nào đi kèm bộ cài**, tất cả tải
qua mạng về `User Data/Cache`. Nhưng phân bố theo ngày cho thấy **không phải người dùng chủ
động bấm tải**:

| Ngày | Gói mới | Draft sửa |
|---|---:|---:|
| 04/07 (ngày đầu mở CapCut) | **224** | 0 |
| 06→21/07 | 9–21 / ngày | 0–2 |
| 23/07 | 0 | 5 |
| 24/07 | 16 | 15 |

224/354 gói rơi vào đúng ngày đầu, khi chưa có draft nào → CapCut tự tải bộ nền lúc mở lần
đầu, và tải thêm khi người dùng **duyệt/hover panel**. Ngày 23/07 sửa 5 draft mà không tải
gói nào: dùng lại đồ có sẵn thì không phát sinh tải.

> **Vì vậy đừng dựng dashboard theo hướng "bạn lãng phí 335 gói".** Cách đọc đúng — và
> giá trị lớn hơn: **máy này đang có sẵn ~300 gói dùng được NGAY, app mới chạm tới 19.**
> Chúng đã nằm trên đĩa nên dựng draft là dùng được liền, không cần tải. Đây chính là
> nguyên liệu để vòng học có cái mà tiến hoá, thay vì quanh quẩn 43 tài nguyên cũ.

Hai kết luận kỹ thuật:

1. **Kho hiện tại đang mù một nửa.** Nó chỉ biết tài nguyên *đã dùng trong draft*, không
   biết trên máy *có sẵn những gì*.
2. **Tên hiển thị chỉ có trong draft.** `config.json` trong gói cache chỉ có tên nội bộ
   (`GESticker_...`, `AmazingAuto_...`); tên thật (`cc_印加太阳神之辉`, `弹出变色-粉`) nằm ở
   `materials[].name` của draft. Dashboard phải **hợp nhất hai nguồn**, không nguồn nào đủ
   một mình — và phải chấp nhận một phần gói chưa dùng thì chưa có tên đẹp để hiển thị.

---

## 1. Mục tiêu 1 — Editor tự động, tự học, tự tiến hoá

### Đang có
Vòng học một chiều: dựng draft → chụp mốc → editor sửa trong CapCut → diff → tài nguyên
thêm vào kho (`use_count++`), tài nguyên bị gỡ bị hạ điểm (`drop_count++`). Lần dựng sau
chọn theo `use_count - drop_count*2`.

### Thiếu — và đây là chỗ quyết định
| Thiếu | Vì sao quan trọng |
|---|---|
| Học **cách dùng**, không chỉ **dùng cái gì** | Hiện chỉ đếm tài nguyên. Không học: caption đặt ở đâu, cỡ bao nhiêu, nhịp cắt bao lâu, SFX rơi vào loại khoảnh khắc nào, hook dài mấy giây. Đó mới là "gu". |
| **Hàm mục tiêu** để biết mình có khá lên không | Không đo được bản tháng này có tốt hơn tháng trước không → "tiến hoá" chỉ là niềm tin. |
| Tín hiệu **kết quả** (view/giữ chân) | Hiện chỉ học theo sở thích editor, không học theo cái chạy được. |
| **A/B**: mỗi chủ đề chỉ dựng đúng một bản | Không có gì để so, nên không có gì để chọn. |

### Đề xuất then chốt: chỉ số "ĐỘ PHẢI SỬA"

> Thước đo tiến hoá = **editor phải sửa bao nhiêu thì draft mới dùng được**.
> Càng ngày càng phải sửa ít = app càng hợp gu. Con số này giảm dần theo tháng chính là
> bằng chứng "tự tiến hoá", thay cho cảm tính.

Dữ liệu đã có sẵn: `snapshots/` giữ mốc trước, draft sau khi editor lưu là mốc sau. Chỉ
cần **mở rộng `draft_diff.py`** từ "tài nguyên thêm/gỡ" sang cả: segment bị cắt/dời,
caption bị sửa chữ, thời điểm bị đẩy, âm lượng bị chỉnh, transition bị đổi.

Từ cùng dữ liệu đó rút ra **luật dựng** (rule store) thay cho việc chỉ đếm:
`"Đan luôn đổi font sang comicbd"` · `"Nguyên luôn kéo hook ngắn lại còn ≤2.5s"` ·
`"SFX pop chỉ dùng ở chỗ chuyển ý, không dùng ở hook"`.

---

## 2. Mục tiêu 2 — Quản lý project & tài nguyên bằng dashboard

### Quét được những gì (đã kiểm chứng trên máy thật)

| Nguồn | Có gì | Ghi chú |
|---|---|---|
| `Cache/effect`, `Cache/artistEffect` | 354 gói: `resource_id`, kích thước, thời điểm tải, `config.json` (tên nội bộ + version), ảnh `singleImage.png`/`final.gif` | Đây là "đã tải" |
| `draft_content.json` của 25 draft | tên hiển thị thật, `resource_id`, số lần dùng, dùng ở draft nào | Đây là "đã dùng" |
| `Cache/music` (200), `Resources/Font`, `Cache/fontImage` (7.606) | nhạc + font đã tải | Chưa quét |
| `Presets/Adjust`, `Presets/Combination`, `Presets/Text_V2` | **preset do chính editor lưu tay** | Mỏ vàng để học gu, chưa đụng tới |
| `Config/globalSetting` | vị trí thư mục draft | Đã dùng để dò CapCut |

**Không có** CSDL catalog nào trong CapCut (đã quét: 0 file SQLite ngoài cache) → phải tự
dựng inventory và tự hợp nhất.

### Đau thật của người dùng: tải thử rồi không dùng, mà KHÔNG XOÁ ĐƯỢC

> "Thi thoảng tôi edit cũng tải thử vài nhãn dán, hiệu ứng, linh tinh khác nhưng lại không
> dùng cho bản final, nhưng lại không xoá được." — 25/07/2026

CapCut không có chỗ nào để gỡ tài nguyên đã tải. Đây là việc app làm được ngay, và là tính
năng CapCut **không có**. Nguyên tắc thi hành (đã cài trong `capcut_inventory.py`):

1. **Cách ly, không xoá thẳng.** Gói được chuyển sang `quarantine/<lô>/` kèm manifest, hoàn
   tác một nút. Đã kiểm chứng trả về **khớp byte-for-byte** (140 file / 2.970.219 byte /
   cùng sha256). Xoá hẳn là hành động riêng, người dùng phải bấm lần nữa.
2. **Kiểm tra lại ngay trước khi chuyển**, không tin bản quét cũ — người dùng có thể vừa
   dùng gói đó xong.
3. **Quét đệ quy cả timeline lồng** (`<draft>/Timelines/<guid>/draft_content.json` — 25
   draft nhưng 46 file). Bỏ sót là kết luận nhầm "chưa dùng" rồi xoá mất đồ đang dùng.
4. **Từ chối chạy khi CapCut đang mở.**
5. **Không đụng sticker / hiệu ứng chữ / transition** kể cả khi chưa dùng — đó là đồ editor
   có thể cần. Chỉ nhắm nhóm *làm đẹp · chưa rõ · filter*.

Trên máy dev: dọn được **232 gói · 282 MB** mà không mất gì đang dùng.

### Dashboard trả lời được những câu CapCut không trả lời
- Đã tải 448 MB, thật sự dùng bao nhiêu? Xoá được bao nhiêu?
- Tài nguyên nào tải về rồi bỏ xó 6 tháng?
- Gu mỗi editor: ai hay dùng gì, ai gỡ gì ra khỏi draft app dựng?
- Mỗi dự án đang ở đâu trong vòng đời: đã phân tích → đã dựng → editor đã sửa → đã đồng
  bộ về kho → đã xuất bản?
- Draft nào đang chiếm ổ cứng mà đã xuất bản xong (dọn được)?

---

## 3. Mục tiêu 3 — Agent tư vấn dài hạn

### Đang có
12 tool, nhớ hội thoại trong bảng `chat` của `library.db`, một phiên `default`.

### Thiếu
| Thiếu | Hậu quả hôm nay |
|---|---|
| Bộ nhớ **có cấu trúc**, tách khỏi transcript | Nhớ theo kiểu đọc lại 40 lượt chat gần nhất. Ba tháng nữa thì hoặc phình context hoặc quên sạch. |
| Agent **đọc được kết quả học** | Không tư vấn được "chủ đề này hợp gu Nguyên hơn vì..." — nó không thấy kho tri thức. |
| Tóm tắt định kỳ | Không có cơ chế nén lịch sử dài. |
| Chủ động | Không bao giờ tự nói "3 draft đã 2 tuần chưa đồng bộ về kho". |

### Đề xuất
Tách bộ nhớ làm 3 loại, agent tự ghi khi phát hiện: **sự việc** (đã làm gì, khi nào) ·
**sở thích/luật** (Đan thích font X) · **quyết định** (đã chốt bỏ Pexels cho tuyến B).
Cộng thêm tool đọc dashboard + rule store để tư vấn có căn cứ chứ không đoán.

---

## 4. Mục tiêu 4 — Không khoá vào CapCut

### Vấn đề kiến trúc hiện tại
`build_short_draft.py` (~1.100 dòng) làm hai việc trộn nhau: **quyết định biên tập**
(cắt ở đâu, caption gì, SFX nào, hook nào) và **phẫu thuật JSON của CapCut** (clone donor,
remap GUID, `material_text_ranges` tính theo byte...). Muốn đổi đích xuất là phải mổ lại
toàn bộ.

### Đề xuất: chèn một lớp trung gian — EDL

```mermaid
flowchart LR
  T["chủ đề + gu editor"] --> D["QUYẾT ĐỊNH BIÊN TẬP<br/>(cắt · caption · SFX · B-roll · hook)"]
  D --> E[("EDL<br/>JSON của MÌNH")]
  E --> X1["exporter CapCut<br/>(build_short_draft)"]
  E --> X2["exporter ffmpeg<br/>(ffmpeg_render — đã có)"]
  E --> X3["exporter khác<br/>Premiere XML · DaVinci · web"]
  E --> L["kho luật & chỉ số<br/>học trên EDL, không phụ thuộc CapCut"]
```

Ba cái lợi, theo thứ tự quan trọng:
1. **Luật học được gắn vào EDL, không gắn vào JSON CapCut** → CapCut đổi format hay bỏ
   CapCut thì tri thức tích luỹ vẫn còn nguyên.
2. Diff/đo "độ phải sửa" làm trên EDL sạch hơn nhiều so với dò trong JSON CapCut.
3. `ffmpeg_render.py` vốn đã là exporter thứ hai → mô hình này không phải lý thuyết.

> **Thời điểm:** phải làm **trước** khi xây rule store, nếu không luật sẽ viết bám vào
> cấu trúc CapCut và phải viết lại từ đầu.

---

## 5. Nợ tồn đọng (ngoài 4 mục tiêu)

| Nợ | Mức | Ghi chú |
|---|---|---|
| **Không có test tự động nào** | 🔴 cao | App sắp phát triển dài hạn mà mỗi lần sửa phải mở trình duyệt bấm tay. Đây là thứ chặn tốc độ mọi giai đoạn sau. |
| Data 1.4 GB nằm trong cây mã nguồn | 🟠 vừa | Draft giữ path tuyệt đối vào `shorts/work` → cần script migration mới dời được |
| Kho là **local một máy** | 🟠 vừa | `library.db` + `assets/user/` nằm trên máy Đan thì máy Nguyên không thấy. Muốn "team học chung" phải có cách gộp kho. |
| Chưa đóng gói `.exe` | 🟡 thấp | Đã đo phương án (một app, gói CUDA 736 MB tuỳ chọn) |
| `shorts/` chưa là package | 🟡 thấp | Còn `sys.path.insert` |

---

## 5b. Ràng buộc mới: mỗi người một máy, hướng tới nhiều người dùng

Chốt ngày 25/07/2026: Đan và Nguyên làm trên **máy riêng**, và app có thể **thương mại hoá
cho nhiều người** chứ không chỉ hai bạn này. Kéo theo 5 hệ quả phải tôn trọng từ bây giờ:

| Hệ quả | Việc phải làm |
|---|---|
| Kho gu là **dữ liệu riêng của từng người**, nằm trên máy họ | Không thiết kế schema theo giả định "một máy có mọi editor". `owner` phải là danh sách động (đã đúng), thêm khái niệm *máy này* vs *kho chung* |
| Hai máy học riêng thì tri thức **không cộng dồn** | Cần đường **xuất/nhập gói kho** (kho + luật + chỉ số), sau đó mới tính tới thư mục chung / server |
| Người mua sẽ **không sửa `.env`** | Cần màn hình **Cài đặt trong app** để nhập API key (lưu cạnh dữ liệu, không nằm trong thư mục cài) |
| Máy khách có CapCut ở **vị trí khác** | Đã xong: `assetlib.find_capcut()` đọc `globalSetting` |
| Kho gu = dữ liệu cá nhân | Không tự gửi đi đâu. Thống kê/telemetry nếu có phải **hỏi trước**, mặc định tắt |

> Hệ quả thiết kế cho GĐ1: mọi bảng thống kê phải phân biệt rõ **"trên máy này"** với
> **"kho đã học"**, vì hai thứ đó sẽ khác nhau ở mỗi máy — đây cũng là lý do dashboard
> phải hợp nhất *cache máy này* + *draft máy này* + *kho gu của người dùng này*.

## 6. Thứ tự đề xuất

| GĐ | Việc | Vì sao đặt ở đây |
|---|---|---|
| **1** | **Inventory + Dashboard**: quét cache CapCut, hợp nhất với kho, tab thống kê; trạng thái vòng đời cho project/draft | Giá trị thấy ngay, không đụng kiến trúc, và tạo ra dữ liệu mà mọi giai đoạn sau đều cần |
| **2** | **EDL**: tách quyết định biên tập khỏi phẫu thuật JSON CapCut | Làm trước rule store, nếu không phải viết lại |
| **3** | **Học sâu**: diff mở rộng (timing/caption/âm lượng) → chỉ số "độ phải sửa" → rule store trên EDL | Cần EDL ở GĐ2 và dữ liệu ở GĐ1 |
| **4** | **Agent dài hạn**: bộ nhớ có cấu trúc + tool đọc dashboard/rule store + tóm tắt phiên | Agent chỉ tư vấn giỏi khi đã có tri thức của GĐ1-3 để đọc |
| **xen kẽ** | **Bộ test tự động** cho pipeline + API | Càng để lâu càng đắt; nên bắt đầu ngay từ GĐ1 |
| **trước khi bán** | Màn hình **Cài đặt** (API key, thư mục dữ liệu) + **xuất/nhập gói kho** giữa các máy | Hệ quả của mục 5b — người mua không sửa `.env`, và hai máy phải cộng dồn được tri thức |

Nguyên tắc xuyên suốt, giữ nguyên từ giai đoạn hiện tại: **đừng ép AI đoán giỏi hơn —
để editor sửa rồi máy học lại** (bài học mục 10.1 của `WORKFLOW.md`).
