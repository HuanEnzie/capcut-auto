# Toàn bộ workflow & cơ chế vận hành

> Hệ thống biến **1 buổi ghi hình/ghi âm dài 2-4 tiếng** thành **nhiều short dạng DỰ ÁN CapCut
> còn sửa được**, và **học dần gu của từng editor** để lần sau tự lên đúng phong cách.
>
> Điểm khác Opus Clip: nó xuất video đã render — sửa không được. Ta xuất **draft CapCut**,
> editor mở ra chỉnh tiếp bình thường. Và kho tài nguyên tiến hoá theo người dùng.

~4.700 dòng Python, 24 module. Tài liệu này giải thích **cái gì chạy khi nào, và tại sao làm vậy**.

---

## 1. Bản đồ module

```mermaid
flowchart TB
  subgraph UI["Giao diện — app.py + ui.html"]
    M1["Chế độ THỦ CÔNG<br/>4 tab bấm nút"]
    M2["Chế độ AGENT<br/>chat tiếng Việt"]
  end
  subgraph PIPE["Pipeline dựng short — shorts/"]
    T1[transcribe.py<br/>bóc lời 2 tầng]
    T2[topics.py<br/>Gemini trích chủ đề]
    T3[caption_fix.py<br/>sửa chính tả tiếng Việt]
    T4[enrich.py<br/>hook/emoji/SFX/B-roll]
    T5[render_short.py<br/>cắt, reframe, audiogram]
    T6[pexels.py<br/>tải stock]
    T7[build_short_draft.py<br/>RÁP DRAFT CAPCUT]
  end
  subgraph LEARN["Kho học gu — gốc dự án"]
    L1[assetlib.py<br/>kho 2 tầng + chống trùng]
    L2[draft_scan.py<br/>bóc tài nguyên từ draft]
    L3[draft_diff.py<br/>editor sửa gì]
    L4[asset_restore.py<br/>cài sang máy mới]
  end
  A[agent.py<br/>vòng lặp tool] --> PIPE
  A --> LEARN
  M1 --> PIPE
  M1 --> LEARN
  M2 --> A
  T7 --> L1
  L1 --> T7
  T7 --> AB[audio_balance.py<br/>cân bằng LUFS]
  GU[gemini_util.py<br/>retry + xoay model] -.-> T2 & T3 & T4 & A
```

**Nguyên tắc kiến trúc xuyên suốt:** ffmpeg **nướng sẵn** phần nền (khung 9:16, cắt ghép,
audiogram) thành 1 file mp4; CapCut draft chỉ chứa các lớp **CHỈNH ĐƯỢC** (caption, sticker,
SFX, B-roll, emoji). Nướng hết vào video thì editor mất quyền sửa; để hết trong CapCut thì
CapCut đứng hình.

---

## 2. Workflow A — Record thô ➜ danh sách chủ đề

```mermaid
flowchart LR
  V["record<br/>.mp4 / .mp3<br/>2-4 tiếng"] --> W1["ffmpeg<br/>tách audio<br/>16kHz mono"]
  W1 --> W2["TẦNG 1: khảo sát<br/>batched + greedy<br/>KHÔNG mốc từ"]
  W2 --> W3["transcript.survey.json"]
  W3 --> W4["Gemini<br/>+ profile YAML"]
  W4 --> W5["chấm điểm bằng CODE<br/>không để LLM tự chấm"]
  W5 --> W6["topics.json<br/>chủ đề + điểm"]
```

**Vào:** đường dẫn file. **Ra:** `shorts/work/<tên>/topics.json`.

Chi tiết đáng chú ý:

- **Tầng 1 chỉ cần "đủ tốt để tìm chủ đề"**, không cần chính xác từng chữ. Nên bỏ mốc từng từ,
  dùng giải mã tham lam, gom lô 16 — nhanh gấp ~5 lần (mục 9.1).
- **Điểm do code tính, không do LLM tính.** LLM chấm từng tiêu chí trong
  `profiles/meeting.yaml`, code nhân trọng số rồi lọc theo ngưỡng. LLM tự cho điểm tổng thì
  điểm trôi và không giải thích được.
- **Chủ đề = nhiều đoạn RỜI ghép lại.** Người nói hay quay lại ý cũ; 1 chủ đề có thể gồm 2-4
  đoạn ở các mốc khác nhau.
- **Record chỉ có tiếng vẫn chạy bình thường** ở bước này (chỉ khác ở bước dựng hình).

---

## 3. Workflow B — Chủ đề ➜ draft CapCut

Đây là workflow phức tạp nhất. `build_short_draft.py` điều phối:

```mermaid
flowchart TB
  S["chọn chủ đề N + gu editor"] --> F1["TẦNG 2: bóc kỹ<br/>chỉ các đoạn của chủ đề<br/>medium + mốc từng từ"]
  F1 --> F2["snap: dời điểm cắt<br/>về ranh giới CÂU"]
  F2 --> F3["tighten_cuts:<br/>bỏ khoảng lặng > 0.8s"]
  F3 --> F4["enrich: Gemini chọn<br/>hook + emoji + SFX + B-roll"]
  F4 --> F5["hook lên ĐẦU<br/>cold-open"]
  F5 --> F6["ffmpeg dựng nền<br/>reframe 9:16 HOẶC audiogram"]
  F6 --> F7["append_tail<br/>đuôi 2.4s mờ dần"]
  F7 --> G["RÁP DRAFT JSON"]

  G --> G1["track video nền"]
  G --> G2["track B-roll<br/>stock Pexels"]
  G --> G3["track caption<br/>chia cụm ≤18 ký tự"]
  G --> G4["track sticker<br/>LẤY TỪ KHO GU EDITOR"]
  G --> G5["track emoji"]
  G --> G6["track SFX<br/>bin-pack không chồng"]
  G --> G7["card chốt + CTA"]
  G1 & G2 & G3 & G4 & G5 & G6 & G7 --> OUT["draft_content.json<br/>+ draft_meta_info.json"]
```

### Các bước then chốt

**1. Snap về ranh giới câu.** Mốc thời gian LLM đưa ra là *áng chừng*. Không snap thì cắt
giữa câu. `snap()` tìm khoảng lặng lớn nhất quanh điểm cắt trong cửa sổ ±4s.

**2. Cắt khoảng lặng** (`tighten_cuts`). Short mà chết vài giây là mất người xem. Tách mỗi
đoạn thành nhiều đoạn nhỏ nhảy qua chỗ im, chừa 0.15s hai mép cho đỡ cụt hơi.

**3. Cold-open.** Hook không phải chữ chạy trên màn hình mà là **khoảnh khắc ấn tượng nhất
được kéo lên đầu video**. AI chọn câu gây tò mò nhất, đoạn đó được ghép vào trước phần thân.

**4. Nền: reframe hay audiogram?** `has_video()` kiểm tra luồng hình:
- Có hình → khung 9:16 nền mờ + video gốc đặt giữa.
- Chỉ có tiếng → **audiogram**: gradient chuyển động + sóng âm.

**5. Ráp draft.** Không dùng thư viện nào — ghi thẳng JSON của CapCut, clone cấu trúc từ draft
mẫu (`282new`) rồi remap toàn bộ GUID. Chi tiết ở mục 9.4.

---

## 4. Workflow C — Vòng học gu editor ⭐

Đây là thứ khiến hệ thống khác biệt, và là **giải pháp cho một thất bại**: thử 2 vòng bắt AI
chọn stock cho khớp mood đều hỏng (mục 10.1). Kết luận: đừng ép AI đoán giỏi hơn — **để editor
sửa rồi máy học lại**.

```mermaid
flowchart LR
  B["app dựng draft v1<br/>dùng kho hiện có"] --> SNAP["chụp mốc<br/>vân tay tài nguyên"]
  SNAP --> E["Đan/Nguyên mở CapCut<br/>sửa theo gu"]
  E --> D["diff: so mốc trước/sau"]
  D --> ADD["THÊM ➜ nạp vào kho<br/>use_count++"]
  D --> REM["GỠ ➜ drop_count++<br/>hạ ưu tiên"]
  ADD --> K[("kho assets/user/&lt;editor&gt;<br/>+ library.db")]
  REM --> K
  K --> B
```

**Cơ chế chống trùng lặp 2 khoá** (yêu cầu gốc: "tránh lưu duplicate"):
- `resource_id` — CapCut cấp, ổn định toàn cầu, dùng cho sticker/hiệu ứng chữ/transition.
- `sha256` nội dung — dùng cho file local (SFX/font/stock), vì **cùng một file trên máy Đan và
  máy Nguyên sẽ có đường dẫn khác nhau**.

Đã có thì chỉ `use_count++`, **không copy lần hai**. Seed từ 4 draft thật của team: 43 tài
nguyên vào kho, **106 lượt trùng bị chặn**.

**Chọn tài nguyên khi dựng draft:** kho user (đúng editor) → shared → default → stock API.
Điểm xếp hạng `use_count - drop_count*2` — cái bị gỡ nhiều lần sẽ tự chìm xuống.

---

## 5. Workflow D — Cân bằng âm thanh

```mermaid
flowchart LR
  D["draft"] --> M["ffmpeg đo LUFS<br/>từng nguồn tiếng"]
  M --> C["phân vai<br/>giọng / SFX / nhạc / B-roll"]
  C --> G["gain = mục tiêu − đo được<br/>chặn trần −1 dBTP"]
  G --> V["volume = 10^(gain/20)"]
  V --> W["GHI THẲNG vào draft JSON"]
```

Đo theo **ITU-R BS.1770 / EBU R128** (đơn vị LUFS), không dùng peak thô vì peak không phản ánh
cảm nhận to-nhỏ của tai người.

| Nguồn | Mục tiêu | Vì sao |
|---|---|---|
| Giọng nói | **−14 LUFS** | chuẩn TikTok/YouTube/Reels chuẩn hoá về mức này |
| SFX | −16 LUFS | dưới giọng 2 dB: nhấn được mà không giật mình |
| Nhạc nền | −30 LUFS | thấp hơn giọng ~16 dB (nghiên cứu: SNR ≈ +15 dB thì nghe rõ gần tối đa) |
| Trần | ≤ −1 dBTP | tránh méo sau khi nén codec |

**Không re-encode.** Chỉ ghi `volume` (hệ số nhân tuyến tính) vào từng segment → editor mở
CapCut vẫn kéo tay chỉnh được, và lần sau app học luôn cái họ chỉnh.

---

## 6. Workflow E — Mang sang máy mới

Sticker/hiệu ứng chữ/transition phải **bấm tải trong CapCut** mới có, nằm ở
`<LOCALAPPDATA>/CapCut/User Data/Cache/{effect|artistEffect}/<resource_id>/<hash>/`.
Draft trỏ đường dẫn tuyệt đối vào đó → máy mới mở là thiếu.

Vì kho đã giữ **nguyên cả gói effect** (thư mục, không chỉ ID):

```
asset_restore.py --check    → máy này thiếu gì
                 --restore  → đổ gói từ kho vào đúng cache CapCut
                 --fix-draft→ rewrite đường dẫn cho khớp LOCALAPPDATA máy đó
```

Đã kiểm chứng bằng cách giả lập máy trắng: khôi phục **15/15 gói, khớp byte-for-byte**.

---

## 7. Hai chế độ vận hành

| | **Thủ công** | **Agent** |
|---|---|---|
| Giao diện | 4 tab bấm nút | chat tiếng Việt |
| Hợp với | thao tác quen, nhanh | lệnh tự do, nhiều bước |
| Trí nhớ | không | nhớ ngữ cảnh (SQLite) |
| Ai dùng | editor | người điều phối |

**Agent hoạt động thế nào:**

```mermaid
sequenceDiagram
  participant U as Người dùng
  participant A as agent.py
  participant G as Gemini
  participant T as Tool
  U->>A: "dựng chủ đề điểm cao nhất của 2006 theo gu Đan"
  A->>A: nạp lịch sử chat từ SQLite
  A->>G: nội dung + khai báo 12 tool
  G-->>A: function_call liet_ke_du_an
  A->>T: chạy tool
  T-->>A: dữ liệu thật
  A->>G: gửi kết quả tool về
  G-->>A: function_call dung_draft(2006, 1, dan)
  A->>T: đẩy JOB NỀN
  T-->>A: đã khởi động
  A->>G: kết quả
  G-->>A: câu trả lời cuối
  A->>U: "Đã khởi động, xem mục Tiến trình"
```

Việc nặng **không chạy trong lượt chat** — đẩy sang job nền rồi báo lại, tránh chẹn cả phiên.

---

## 8. Vòng đời một dự án (toàn cảnh)

```mermaid
flowchart TB
  R["record 4 tiếng"] --> A1["Workflow A<br/>~6 phút"]
  A1 --> TP["16 chủ đề có điểm"]
  TP --> PICK["NGƯỜI DÙNG CHỌN"]
  PICK --> B1["Workflow B<br/>~2-4 phút/chủ đề"]
  B1 --> DR["draft CapCut"]
  DR --> AB["Workflow D<br/>cân bằng tiếng"]
  AB --> ED["editor sửa trong CapCut"]
  ED --> C1["Workflow C<br/>đồng bộ về kho"]
  C1 -.học gu.-> B1
  ED --> PUB["xuất bản"]
```

---

## 9. Bảy cơ chế then chốt

### 9.1 Bóc lời 2 tầng — nhanh gấp 5, chất lượng lại cao hơn

Chẩn đoán ban đầu tưởng nghẽn GPU, **đo ra thì ngược lại**: VRAM chỉ dùng 1.4/4 GB,
utilization 51-87% → **GPU bị bỏ đói**, nghẽn ở khâu điều phối và ở các tham số mặc định rất đắt
(beam 5, best_of 5, 6 mức temperature fallback, `condition_on_previous_text=True` gây trôi/lặp
trên file dài → kích hoạt chính cái fallback đó).

| Cấu hình (clip 8 phút) | Thời gian | Tốc độ |
|---|---|---|
| Mặc định | 56.7s | 8.5x |
| greedy + tắt condition | 46.7s | 10.3x |
| bỏ mốc từ | 43.7s | 11.0x |
| **batched(16) + greedy + bỏ mốc từ** | **11.1s** | **43.3x** |

Nên tách: **tầng 1** quét cả file bằng cấu hình nhanh (chỉ để tìm chủ đề) → **tầng 2** bóc kỹ
bằng `medium` + mốc từng từ **chỉ trên đoạn được chọn**.

Vừa nhanh hơn **vừa cho caption đẹp hơn**: không ai kham nổi `medium` cho 4 tiếng, nhưng thừa
sức cho 3 phút.

⚠️ Cạm bẫy: `sorted(glob("transcript.*.json"))[-1]` sẽ chọn nhầm `survey` (xếp chữ cái đứng
cuối) — bản không có mốc từ. Phải dùng `load_transcript()` với thứ tự ưu tiên fine > cũ > survey.

### 9.2 `src_to_out()` — cái trục giữ mọi thứ khớp nhau

Short = nhiều đoạn nguồn rời ghép lại (hook + các đoạn thân + đã cắt lặng). Mọi cue của AI
(emoji giây 631, SFX giây 646...) đều theo **mốc file gốc**, phải đổi sang **mốc video output**.

Hàm này là trục: đổi được nó thì caption/emoji/SFX/B-roll **tự khớp lại hết**. Nhờ vậy việc
cắt khoảng lặng chỉ tốn ~30 dòng — chỉ cần tách `cuts` thành nhiều mảnh hơn.

⚠️ Cue rơi trúng khoảng lặng vừa cắt thì **dời về mép gần nhất**, không bỏ. Bỏ thì mất đúng
những SFX đặt ở chỗ chuyển ý (đã đo: SFX rớt 21 → 13).

### 9.3 Kho 2 tầng + chống trùng 2 khoá

Xem mục 4. Điểm tinh tế: **gói effect của CapCut là THƯ MỤC**, không phải file đơn — phải hash
và copy theo thư mục, và trên Windows cần tiền tố đường dẫn dài `\\?\` vì tên file trong gói
vượt giới hạn 260 ký tự.

### 9.4 Phẫu thuật JSON của CapCut

`draft_content.json` là **JSON thuần, không mã hoá**. Mọi thời gian tính bằng **micro giây**.
Cấu trúc `tracks[].segments[]` → `material_id` + `extra_material_refs[]`, dính nhau bằng GUID.

Cách làm: clone nguyên cụm từ draft mẫu → **remap toàn bộ GUID** → thay nội dung. Sau đó
`integrity()` đếm tham chiếu mồ côi, luôn phải bằng **0**.

Ba cái bẫy đã trả giá:
- Giữ nguyên `music_id` của nhạc online từ draft mẫu → CapCut **gộp cả 15 SFX thành một tiếng**.
  Phải "địa phương hoá": `type=extract_music`, `category_name=local`, `music_id` GUID riêng.
- Giữ nguyên `icon_url`/`preview_cover_url` → **thumbnail timeline khác hẳn video** (CapCut vẽ
  timeline từ URL, vẽ canvas từ path). Phải blank hai trường đó.
- Đường dẫn media phải **tuyệt đối**, và phải điền `draft_materials` trong meta, nếu không
  CapCut đòi chọn lại đường dẫn.

### 9.5 Nướng sẵn vs để chỉnh được

| Nướng vào mp4 (ffmpeg) | Để trong draft (chỉnh được) |
|---|---|
| khung 9:16, nền mờ | caption |
| cắt ghép, bỏ lặng | sticker, emoji |
| audiogram | SFX |
| đuôi kết mờ dần | B-roll |
| | âm lượng |

Ranh giới này do một thất bại định ra: bản v1 nhét 28 caption template vào draft làm **CapCut
báo đỏ và đứng hình**. Chuyển sang text thường thì hết.

### 9.6 Chống 503 & xoay tua model

Gemini trả 503 (quá tải) nhiều lần trong quá trình làm. `gemini_util` gom một chỗ: lỗi quá tải
→ chờ giãn dần rồi thử lại; hết lượt → **xoay sang model kế tiếp**; `parsed=None` (output vượt
giới hạn) cũng coi là hỏng.

⚠️ Kèm nguyên tắc: **không cache kết quả tệ**. Từng có lần 0/41 dòng caption sửa được nhưng
vẫn ghi cache rỗng → mọi build sau dùng lại cache đó, caption vĩnh viễn không được sửa **mà
không báo gì**. Giờ chỉ cache khi đạt ≥50%.

### 9.7 Chia lô mọi thứ gửi LLM

Record 4 tiếng → 16 chủ đề → 755 dòng caption gửi một lần → vượt giới hạn output → `parsed`
về None → **gãy cả build**. Không lộ với record 2 tiếng (227 dòng). Giờ chia lô 120 dòng, một
lô hỏng không làm hỏng cả build.

---

## 10. Hai quyết định lớn rút ra từ thất bại

### 10.1 Stock tự động không cứu được mood

Thử 2 vòng: prompt "bám mood & câu chuyện", rồi siết query. Vẫn hỏng. Xem tận mắt clip Pexels
trả về:

| Query gửi đi | Nhận về |
|---|---|
| "person telling story, expressive face" | một bà cụ Tây ngẫu nhiên |
| "endless loop, hamster wheel, stuck" | **một anh đạp xe BMX** (match chữ "cycle") |

Hai lý do gốc: stock keyword-search **không hiểu ẩn dụ**, và người-lạ-corporate **không khớp
câu chuyện tiếng Việt cụ thể**. → Chuyển sang human-in-the-loop (mục 4).

### 10.2 Đóng gói: một app, CUDA là gói tuỳ chọn

Đo ra: `nvidia/` chiếm 2.0 GB. Nhưng thử nghiệm cho thấy **CTranslate2 không dùng cuDNN chút
nào** — chỉ cần `cublas64_12.dll` + `cublasLt64_12.dll`.

| Bộ DLL | Dung lượng | Kết quả |
|---|---|---|
| Đủ cả | 2.0 GB | chạy |
| **Chỉ cuBLAS** | **736 MB** | **chạy, tốc độ y hệt** |
| Bỏ nốt cublasLt | 98 MB | hỏng |

→ Không cần tách 2 app. Một app, installer nền ~250-350 MB (chạy CPU được ngay), **gói CUDA
736 MB chỉ tải khi máy có GPU NVIDIA**. GPU nhanh hơn CPU ~5.2 lần.

---

## 11. Số liệu đo thật

| Hạng mục | Kết quả |
|---|---|
| Bóc lời record 100 phút | **1 phút 47 giây** (55.8x realtime) |
| Phân tích trọn vẹn 100 phút (cả Gemini) | **4.7 phút** |
| Record 4 tiếng (cách cũ, model medium) | 54 phút → nay ~6 phút |
| Chủ đề trích từ buổi 4 tiếng | **16** |
| Dựng 1 draft (đã có cache) | ~5 giây · chưa cache: 2-4 phút |
| Kho tài nguyên | 43 (Đan 26 / Nguyên 17), chặn 106 lượt trùng |
| Khôi phục sang máy mới | 15/15 gói khớp byte-for-byte |
| Lệch âm lượng SFX phát hiện được | **19.9 dB** |
| Cắt lặng 1 chủ đề | 178.6s → 147.9s (bỏ 15 khoảng, rút 30.7s) |
| Toàn bộ mã nguồn | ~4.700 dòng / 24 module |

---

## 12. Chưa làm

- Đóng gói `.exe` (đã đo xong phương án, chưa dựng).
- Xác minh khôi phục tài nguyên trên máy Đan/Nguyên (mới giả lập máy trắng).
- Validate bộ CUDA 736 MB trên file 2 tiếng thật (mới test clip ngắn).
- B-roll vẫn dùng Pexels làm mặc định — sẽ nhạt dần khi kho user đủ giàu.
