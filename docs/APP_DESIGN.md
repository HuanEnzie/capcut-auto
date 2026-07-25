# CapCut Auto Editor — Thiết kế app cho team (Đan & Nguyên)

> Mục tiêu: đóng gói pipeline hiện tại thành app edit tự động, **học lại gu của editor**
> (stock/icon/SFX/nhãn dán/transition/hiệu ứng chữ/font) và **tự cân bằng âm thanh**.

---

## 1. Nguyên lý cốt lõi

Bài toán stock/icon "không hợp mood" **không giải được bằng cách ép AI đoán giỏi hơn** —
đã thử 2 vòng (mood-driven prompt, siết query) đều thất bại vì stock API keyword-match
không hiểu ẩn dụ và người-lạ-corporate không khớp câu chuyện tiếng Việt cụ thể.

Giải pháp: **human-in-the-loop learning**.

```
v1 auto (stock API + SFX/icon mặc định)
   -> Đan/Nguyên mở CapCut sửa theo gu
   -> app DIFF draft trước/sau, biết CHÍNH XÁC cái gì bị thay
   -> harvest tài nguyên editor chọn vào KHO NGƯỜI DÙNG
   -> lần sau ưu tiên dùng kho này thay vì stock API
```

Càng chạy càng hợp gu. Stock API tụt dần xuống vai trò *fallback khi kho chưa có*.

---

## 2. Phát hiện kỹ thuật nền tảng (đã kiểm chứng trên draft thật)

Soi 4 draft thật của editor (`0708/0710/0715/0721`) — **mọi tài nguyên đều harvest được**:

| Loại | Định danh | Đường dẫn file thật |
|---|---|---|
| Sticker / nhãn dán | `resource_id`, `sticker_id`, `name`, `category_name` | `…/CapCut/User Data/Cache/artistEffect/<id>/<hash>` |
| Hiệu ứng chữ (text template) | `resource_id`, `effect_id`, `name` | `…/CapCut/User Data/Cache/effect/<id>/<hash>` |
| SFX / nhạc | `name`, `music_id`, `category_name: local` | đường dẫn gốc, vd `E:/E Download/meme/x.mp3` |
| Video / ảnh (stock) | `material_name`, `path` | file local đã tải |
| Animation | `material_animations[].type = sticker_animation` | tham chiếu theo id |

**Hệ quả:** không cần hack gì thêm — chỉ cần đọc `draft_content.json`, gom `resource_id`
+ `path` + `name`, copy file cache về kho riêng là tái sử dụng được ở draft sau.
(Pipeline hiện tại đã chứng minh CapCut chấp nhận `path` tuỳ ý — text template donor
`282new` trỏ vào đường dẫn của ta vẫn chạy.)

Thuận lợi thêm: CapCut tự ghi `draft_content.json.bak` mỗi lần lưu → có sẵn mốc so sánh.

---

## 3. Kiến trúc app

```
capcut-auto/
├─ shorts/              # pipeline hiện tại (transcribe → topics → enrich → build draft)
├─ assets/
│  ├─ default/          # KHO MẶC ĐỊNH của app (v1 dùng)
│  │   ├─ sfx/  sticker/  texteffect/  font/  transition/  stock/
│  └─ user/             # KHO NGƯỜI DÙNG — tiến hoá theo thời gian
│      ├─ dan/  nguyen/ # tách theo editor (biết ai chuộng gì)
│      └─ shared/       # dùng chung sau khi được duyệt
├─ library.db           # manifest: hash → metadata, chống duplicate
└─ app/                 # FastAPI + web UI
```

### 3.1 Chống trùng lặp (yêu cầu "tránh bị lưu duplicate")

Khoá dedup **2 tầng**:

1. `resource_id` (CapCut cấp, ổn định toàn cầu) — với sticker/text-effect/transition.
2. `sha256` nội dung file — với file local (SFX, stock, ảnh, font) vì cùng 1 file có thể
   nằm ở nhiều đường dẫn khác nhau trên 2 máy.

Mỗi asset trong `library.db` giữ:
```
id, kind, resource_id, sha256, name, category, path_in_lib,
origin (default|user), owner (dan|nguyen|app), first_seen, use_count, last_used,
tags[], source_draft[]
```
→ Asset mặc định của v1 **vẫn được ghi nhận khi export** (tăng `use_count`) nhưng
**không copy lần 2**: đã có `sha256` trùng thì chỉ cập nhật thống kê.

### 3.2 Phát hiện editor sửa gì

`draft_diff.py`:
```
snapshot(draft)  -> fingerprint {kind, resource_id|sha256, name, vị trí, thời điểm}
diff(before, after) -> {added[], removed[], changed[], kept[]}
```
- **before** = draft ta sinh ra (app tự lưu snapshot ngay lúc export).
- **after**  = `draft_content.json` sau khi editor lưu.

Kết quả diff cho biết chính xác: sticker nào bị bỏ, sticker nào được thêm, SFX nào bị đổi,
font/hiệu ứng chữ nào editor thích hơn, transition nào được chèn.

**Cơ chế kích hoạt** (2 lựa chọn, làm cả hai):
- Watcher nền theo dõi `mtime` của `draft_content.json` (thư viện `watchdog`).
- Nút **"Đồng bộ về kho"** trong UI — editor bấm khi làm xong (an toàn, không đọc giữa chừng).

### 3.3 Vòng học

Sau harvest, generator đổi thứ tự ưu tiên khi cần 1 tài nguyên:
```
1. Kho user (owner khớp editor, tag khớp ngữ cảnh, use_count cao)
2. Kho shared
3. Kho default
4. Stock API (Pexels…) — chỉ khi 1-3 không có
```
Asset bị editor **gỡ bỏ nhiều lần** → hạ điểm, ngừng đề xuất (negative signal cũng là dữ liệu).

---

## 4. Tự cân bằng âm thanh

### 4.1 Chuẩn tham chiếu
- Đo theo **ITU-R BS.1770 / EBU R128**, đơn vị **LUFS** (không dùng peak thô vì không
  phản ánh cảm nhận to-nhỏ của tai người).
- Nền tảng short (TikTok/YouTube/Reels) chuẩn hoá về khoảng **−14 LUFS** integrated;
  trần **true peak ≤ −1 dBTP** để tránh méo sau khi nén codec.
- Giọng nói cần cao hơn nhạc nền **~15–20 dB** mới nghe thoải mái (nghiên cứu về
  speech intelligibility: SNR ≈ +15 dB đạt độ rõ gần tối đa). Nghe trên điện thoại,
  môi trường ồn → chọn cận trên.

### 4.2 Giá trị mục tiêu khởi điểm

| Nguồn | Mục tiêu | Ghi chú |
|---|---|---|
| Giọng nói (video chính) | **−14 LUFS** integrated | mốc neo, mọi thứ khác so với nó |
| Nhạc nền khi có giọng | **≈ −30 LUFS** (thấp hơn ~16 dB) | đủ nền, không đè lời |
| Nhạc nền lúc không có giọng | **≈ −20 LUFS** | dâng lên lấp khoảng lặng |
| SFX | short-term **−18 … −12 LUFS** | ngắn nên ít ảnh hưởng integrated |
| B-roll có tiếng | khớp giọng chính ±1 dB, hoặc mute | chống "lệch nguồn" |
| True peak | ≤ **−1 dBTP** | toàn bộ mix |

### 4.3 Cách thi hành — KHÔNG re-encode

Điểm mấu chốt: sản phẩm phải **còn sửa được trong CapCut**, nên không bake audio.
Thay vào đó **ghi thẳng `volume` vào draft JSON**:

- `volume` trong CapCut là **hệ số nhân tuyến tính** (1.0 = 0 dB; đo được `9.914` ≈ +19.9 dB
  do editor tự kéo tay ở draft `0715` — đúng việc ta sắp tự động hoá).
- Quy đổi: `volume = 10 ** (gain_dB / 20)`.

Luồng:
```
1. ffmpeg ebur128 đo LUFS từng nguồn (video chính, mỗi B-roll, mỗi SFX, nhạc)
2. gain_dB = target_LUFS - measured_LUFS
3. volume  = 10 ** (gain_dB/20), kẹp trong [0, 10] (giới hạn CapCut)
4. ghi vào segment.volume của draft
```

**Ducking** (nhạc/SFX né giọng): ghi `common_keyframes` kiểu volume trên segment nhạc —
hạ 6–12 dB khi có giọng, attack ~50–100 ms, release ~300–500 ms, lấy mốc thời gian từ
transcript (đã có sẵn word-level timestamps từ Whisper → biết chính xác chỗ có giọng).

Ưu điểm: editor mở ra thấy volume/keyframe đã set sẵn, **vẫn kéo tay chỉnh được** —
và lần sau app học luôn cái editor chỉnh (mục 3.2 bắt được thay đổi `volume`).

---

## 4b. Mang tài nguyên sang máy mới (không phải bấm tải tay trong CapCut)

Sticker / hiệu ứng chữ / transition / hiệu ứng phải bấm tải trong CapCut mới có, nằm ở:
```
<LOCALAPPDATA>/CapCut/User Data/Cache/{effect|artistEffect}/<resource_id>/<hash>/
```
Draft trỏ **đường dẫn tuyệt đối** vào đó → máy mới mở draft là thiếu.

Vì kho đã giữ **nguyên cả gói effect** (thư mục, không chỉ ID), `asset_restore.py` làm:
1. `--check`   : liệt kê máy hiện tại còn thiếu tài nguyên nào.
2. `--restore` : copy ngược gói từ kho vào đúng `Cache/<loại>/<rid>/<hash>/` của máy này.
3. `--fix-draft`: rewrite đường dẫn trong draft cho khớp `LOCALAPPDATA` của máy này.

**Đã kiểm chứng**: giả lập máy trắng (cache rỗng) → khôi phục 15/15 gói, đối chiếu nội dung
**khớp byte-for-byte** với gói gốc.

Lưu ý kỹ thuật: gói effect CapCut có tên file rất dài → vượt `MAX_PATH` 260 của Windows,
gây `WinError 3`. Mọi thao tác copy/duyệt phải dùng tiền tố đường dẫn dài `\\?\`
(`assetlib.lp()`).

**Còn phải xác minh 1 lần trên máy Đan/Nguyên**: CapCut có đọc gói thẳng từ path hay còn
cần bản ghi trong index nội bộ. Nếu cần, fallback là `--check` in ra danh sách phải bấm
tải tay đúng 1 lần.

**Ràng buộc bản quyền**: hiệu ứng thuộc gói CapCut Pro thì khôi phục file **không** cấp
quyền dùng — tài khoản đích vẫn phải có Pro. Nên chuẩn hoá team quanh các hiệu ứng miễn phí.

## 5. Lộ trình

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| **P0** | Pipeline sinh draft v1 (transcribe → topics → enrich → draft) | ✅ xong |
| **P1** | `assetlib` (2 kho + dedup), `draft_scan` (harvest), `asset_restore` (cài sang máy mới) | ✅ xong |
| **P2** | `draft_diff` + watcher: biết editor sửa gì, tự nạp về kho | tiếp theo |
| **P3** | Audio balance (đo LUFS → ghi volume + keyframe ducking) | tiếp theo |
| **P4** | Generator ưu tiên kho user > default > stock API | |
| **P5** | Đóng gói app: FastAPI + web UI, 2 tài khoản Đan/Nguyên, nút đồng bộ | |

## 6. Hình hài app: agent hội thoại làm việc trên folder

Không làm app "bấm nút khô khan" mà làm **agent chat trên một thư mục dự án** (kiểu Claude
Code / Codex). Mọi bước trong pipeline vốn đã là hàm sạch → phơi ra thành **tool** cho agent gọi:

| Tool | Việc |
|---|---|
| `transcribe` | video → transcript (GPU/CPU tự dò) |
| `extract_topics` | transcript → danh sách chủ đề chấm điểm |
| `enrich` | chọn hook / emoji / SFX / B-roll |
| `build_draft` | dựng draft CapCut |
| `harvest_assets` / `restore_assets` | đồng bộ kho tài nguyên |
| `balance_audio` | cân bằng LUFS |
| `ask_user` | hỏi lại khi mơ hồ (chọn hook, chọn tông) |

Trạng thái + ngữ cảnh lưu **SQLite ngay trên máy** (dùng chung `library.db`): lịch sử hội
thoại, dự án đang làm, quyết định đã chốt, gu từng editor. Agent nhớ được "lần trước Nguyên
thích hiệu ứng chữ nào" mà không cần hỏi lại.

### 6.1 Cấu hình model — xoay tua & thay mới

Bảng `models` trong DB, mỗi TÁC VỤ có một **danh sách model theo thứ tự ưu tiên**:
```
topics  : [gemini-3.5-flash, gemini-2.5-flash, ...]
enrich  : [gemini-3.5-flash, gemini-2.5-flash, ...]
caption : [...]
```
Gặp lỗi `503 UNAVAILABLE` / hết quota / model bị khai tử thì **tự tụt xuống model kế tiếp**
— đúng tình huống đã gặp thật: `gemini-3.5-flash` quá tải, phải tay chuyển sang
`gemini-2.5-flash`. Thêm/bớt model chỉ là sửa bảng, không đụng code.

Module cũ bật/tắt bằng bảng `modules(name, enabled, version)` — agent chỉ nạp tool đang bật.

## 7. Đóng gói & tối ưu dung lượng (số đo thật)

**Không cần tách 2 app.** Một app duy nhất, CUDA là **thành phần TUỲ CHỌN tải khi cần**.

Đo thực nghiệm bộ DLL tối thiểu cho faster-whisper (clip 8s, GTX 1650):

| Bộ | Dung lượng | Kết quả |
|---|---|---|
| Đủ cả cublas + cudnn + nvrtc | 2.0 GB | OK 4.6s |
| Bỏ nvrtc + `cudnn_adv` + engines_runtime_compiled | 1.5 GB | OK 4.8s |
| Bỏ thêm `cudnn_engines_precompiled` | 991 MB | OK 4.2s |
| **Chỉ cuBLAS (bỏ SẠCH cuDNN)** | **736 MB** | **OK 4.3s** |
| Bỏ nốt `cublasLt64_12` | 98 MB | ❌ FAIL |

**Kết luận: CTranslate2 KHÔNG dùng cuDNN — chỉ cần `cublas64_12.dll` +
`cublasLt64_12.dll`. Cắt 2.0 GB → 736 MB (−63%), tốc độ không đổi.**
(`cublas64_12` phụ thuộc `cublasLt64_12` nên phải có cả hai — 736 MB là đáy.)

GPU vs CPU trên clip 180 giây: **GPU 19.8s — CPU 103.7s (~5.2x)**. Nghĩa là máy không có
NVIDIA vẫn chạy được, chỉ chậm hơn (bản ghi 2 tiếng: ~15 phút GPU so với ~78 phút CPU).

**Phương án đóng gói:**
```
Installer nền  ~250-350 MB : Python + ffmpeg + deps + app  (chạy được NGAY, CPU mode)
+ gói CUDA      736 MB     : chỉ tải khi máy có GPU NVIDIA, tải 1 lần từ server nội bộ
```
- PyInstaller `--onedir` + Inno Setup (đừng `--onefile`: khởi động chậm, hay bị antivirus cờ).
- **API key không nhúng trong exe** (moi ra được) — nhập lần đầu, lưu DB máy người dùng.
- Exe không ký số sẽ hiện SmartScreen; nội bộ 3 người thì bấm qua, chưa cần mua cert.

## 8. Rủi ro cần lưu ý

- **Cache CapCut có thể bị dọn** → phải copy file ra kho riêng ngay khi harvest, không
  trỏ thẳng vào `User Data/Cache`.
- **2 máy khác nhau** → đường dẫn tuyệt đối khác nhau; kho phải lưu theo hash + rewrite
  path khi build draft trên từng máy.
- **Không đọc draft khi CapCut đang mở** (file `.locked`) → ưu tiên nút đồng bộ thủ công.
- **Bản quyền stock**: Pexels miễn phí thương mại, nhưng asset editor tự tải từ nguồn
  khác cần kiểm tra trước khi đưa vào kho dùng chung.
