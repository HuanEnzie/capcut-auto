# Đóng gói .exe (PyInstaller + Inno Setup)

Từ 30/07/2026, ngoài cách chạy từ mã nguồn (`cai_dat.bat` + `chay.bat`), có bản cài đặt
`.exe` **một file duy nhất** — không cần cài Python, không cần `.venv`, không cần tự tải
ffmpeg. Chạy xong wizard là dùng được ngay, đúng kiểu app desktop bình thường. Dùng khi
đưa cho người không rành dòng lệnh, hoặc máy không tiện cài Python.

Hai bước, hai công cụ khác nhau:

1. **`dong_goi.ps1`** (PyInstaller) — gom mã nguồn + Python runtime + ffmpeg thành một
   thư mục chạy được (`dist/CapCutAuto/`).
2. **`installer.iss`** (Inno Setup) — đóng GÓI thư mục đó thành một file
   `CapCutAuto-Setup-vX.Y.Z.exe` duy nhất, có wizard cài đặt/gỡ cài đặt/shortcut như app
   desktop thật.

## Build lại

```powershell
.\dong_goi.ps1
"C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss
```

`dong_goi.ps1` cần `.venv` đã cài `pyinstaller`. Script tự dọn `build/`, `dist/` cũ, tải
**ffmpeg** (bản essentials từ gyan.dev, cache lại ở `ffmpeg_bin_cache/` — chỉ tải lần
đầu, ~194MB, KHÔNG commit git), chạy PyInstaller ở chế độ `--onedir`, rồi chép `ui.html`,
`assets/{default,donor,fonts}`, `shorts/profiles/*.yaml`, `ffmpeg_bin/` vào cạnh `.exe`
(những thứ này PyInstaller không tự gom vì không phải import Python). Ra
`dist/CapCutAuto/CapCutAuto.exe`, **~480 MB, ~2580 file** (đo 30/07/2026, bản có `pywebview`).

`installer.iss` cần **Inno Setup** (tải bản chính thức tại
[jrsoftware.org](https://jrsoftware.org/isinfo.php), hoặc thẳng từ
[GitHub releases](https://github.com/jrsoftware/issrc/releases)). Nén `dist/CapCutAuto/`
bằng LZMA2 xuống còn **~136 MB** — file duy nhất đưa cho người dùng.

**Cài vào `%LocalAppData%\Programs\CapCutAuto`, KHÔNG PHẢI Program Files.** App ghi dữ
liệu thật (`library.db`, `assets/user`, `shorts/work`, `.env`) vào chính thư mục chứa
`.exe` — Program Files bị khoá ghi với người dùng thường (cần quyền admin), cài vào đó
thì lần chạy đầu đã hỏng ngay ở bước tạo thư mục dữ liệu. Cài theo-người-dùng vào
LocalAppData (giống VS Code, Discord) thì luôn ghi được, không cần UAC.

## Vì sao `--onedir`, không `--onefile`

`--onefile` giải nén ra thư mục tạm mỗi lần mở rồi xoá khi thoát — khởi động chậm hơn
nhiều lần, và các thư viện native (`ctranslate2.dll`) hay lỗi khi giải nén-chạy-xoá liên
tục trên Windows. `--onedir` giữ mọi thứ là file thật trên đĩa: khởi động nhanh, và đúng
luật "đo, đừng đoán" trong dự án này — không có gì ẩn trong một file nén.

## Đã kiểm chứng thật (đo 30/07/2026, trên máy dev)

Copy `dist/CapCutAuto` sang thư mục tách biệt khỏi cây mã nguồn, cắt 45s từ video thật
làm input, chạy `CapCutAuto.exe`, gọi trọn pipeline `/api/ingest` qua HTTP; sau đó build
installer thật, **cài — chạy — gỡ cài đặt** bằng `/VERYSILENT` (không cần GUI):

| Bước | Kết quả đo được |
|---|---|
| Web server khởi động | Sống sau ~6-8s, `/api/overview` trả JSON đúng |
| ffmpeg bundle | `co_ffmpeg()` → `True` — nhận đúng bản trong `ffmpeg_bin/`, ưu tiên trước cả ffmpeg hệ thống (PATH được chèn ở `assetlib._ghep_ffmpeg_vao_path`) |
| tkinter (màn chờ + hộp thoại chọn thư mục) | Tải được trong bản đóng gói, không lỗi thiếu DLL Tcl/Tk — tiến trình `--pick` sống chờ tương tác, không crash |
| Dò CapCut | Tự tìm đúng thư mục draft qua `globalSetting`, không hardcode |
| ROOT đúng chỗ | Ghi dữ liệu (`library.db`, `shorts/work`) vào thư mục chứa `.exe`, không lạc vào `_internal/` |
| ASR thật (`faster-whisper`/`ctranslate2`) | **CHẠY ĐƯỢC** — `17,1x realtime`, không lỗi DLL native. CUDA lỗi driver cũ → tự lùi CPU đúng thiết kế |
| Gemini API (làm sạch transcript + trích chủ đề) | **CHẠY ĐƯỢC** với `.env` thật — `topics.json` ra 1 chủ đề hợp lệ |
| Cài installer | `/VERYSILENT` → exit 0, 2408 file đúng vào `%LocalAppData%\Programs\CapCutAuto`, đăng ký đúng trong Add/Remove Programs |
| Gỡ cài đặt | `/VERYSILENT` → exit 0, xoá sạch thư mục cài + Start Menu group |

Riêng **pixel thật của cửa sổ pywebview** (chữ có hiện đúng font, có bị vỡ layout không)
và **nội dung chính xác của hộp thoại xác nhận gỡ cài đặt** chưa xác nhận bằng mắt (không
xin được quyền điều khiển màn hình lúc đóng gói bản này) — đã kiểm bằng cách khác (tiêu đề
cửa sổ đúng qua `EnumWindows`, kết nối TCP thật tới server), nhưng nên tự tay mở app một
lần trước khi phát rộng.

## Lỗi đã bắt được và vá (30/07/2026, do người dùng thật báo)

- **Hộp thoại chọn thư mục vỡ trong bản đóng gói.** `/api/pick` gọi
  `subprocess.run([sys.executable, "-c", <code tkinter>])` — ở bản `.exe`, `sys.executable`
  CHÍNH LÀ `CapCutAuto.exe`, không hiểu cờ `-c`, nên lệnh đó vô tình mở thêm một bản app
  thứ hai (tranh cổng 8765, chết ngay, dòng chào bị nhặt nhầm làm "đường dẫn vừa chọn").
  Vá: cờ `--pick <kieu>` chặn ở đầu `__main__`. Test khoá lại:
  `test_pick_khong_goi_python_dash_c`.
- **Quá nhiều nút xanh lá cạnh nhau** trong khối "Cài đặt dự án" khiến người dùng mới
  không biết bấm gì trước — đúng luật `docs/UI.md` đã cảnh báo. Vá: hạ nút không phải
  CTA chính xuống nút phụ, thêm dòng "Bước tiếp theo" ngay tại chỗ.
- **~6-8 giây console đen ngòm lúc khởi động** trông như treo. Vá: màn chờ tkinter
  (`_man_hinh_cho()`) — uvicorn chuyển xuống luồng nền, tk.mainloop() ở luồng chính, tự
  đóng + mở trình duyệt khi server bắt đầu trả lời thật (poll, không đoán thời gian).
- **Nút "Phân tích" bấm không có phản ứng gì — không toast, không job.** `ingest()` trong
  `ui.html` đọc thẳng `$('#fileSel').value` — nhưng `#fileSel` (dropdown chọn file) CHỈ
  tồn tại lúc CHƯA gắn record; gắn xong thì khối đó đổi sang thẻ tĩnh, không còn dropdown,
  ĐÚNG LÚC nút Phân tích mới bật lên (cần `p.work_dir`). Bấm vào là gọi `.value` trên
  `null`, `TypeError` chết ngay dòng đầu handler — im lặng hoàn toàn, không lộ ra console
  hay toast nào. Vá: đọc `PROJ.record_path` khi `#fileSel` không tồn tại. Kiểm bằng
  click thật qua Browser pane (không phải suy luận): tạo dự án test, gắn record, bấm
  Phân tích — job chạy thật (`asr-survey` bắt đầu).
- **"Trông thiếu chuyên nghiệp" — mở tab trình duyệt hệ thống thay vì cửa sổ app riêng.**
  `webbrowser.open()` mở đúng một TAB, có thanh địa chỉ lộ `127.0.0.1:8765`, không giống
  desktop app. Vá: `pywebview` (dùng WebView2/Chromium có sẵn trên Windows 10/11) mở CỬA
  SỔ RIÊNG không thanh địa chỉ, tiêu đề "CapCut Auto Editor". Có đường lùi: pywebview lỗi
  (máy hiếm gặp thiếu WebView2 Runtime) thì tự lùi về `webbrowser.open()` như cũ, không
  chặn app dùng được. Đóng cửa sổ pywebview = đóng app luôn (khác đóng tab trình duyệt,
  vốn không tắt được server phía sau) — đúng kỳ vọng desktop app.
  Kiểm bằng cách liệt kê cửa sổ hệ thống thật (Win32 `EnumWindows`, không phải đoán): thấy
  đúng cửa sổ tiêu đề "CapCut Auto Editor" của tiến trình `.exe` vừa cài, có 4-5 kết nối
  TCP thật tới cổng 8765 (đang tải nội dung app, không phải màn trắng).

## Lỗi đã bắt được và vá — vòng 2 (30/07/2026, do người dùng thật báo)

- **`RuntimeError: Library cublas64_12.dll is not found or cannot be loaded` làm job
  Phân tích chết cứng**, dù pipeline đã có cơ chế lùi CPU. Gốc: cả 3 hàm ASR
  (`transcribe`, `transcribe_survey`, `refine_range` trong `shorts/transcribe.py`) chỉ
  bọc `try/except` quanh việc **khởi tạo** `WhisperModel(...)` — nhưng các DLL CUDA
  (cuBLAS...) nạp **LƯỜI** lúc tính toán thật, không phải lúc khởi tạo. Lỗi nổ ra GIỮA
  CHỪNG `model.transcribe()`/vòng lặp tiêu thụ segment, NGOÀI vùng bắt lỗi. Vá: bọc cả
  khối (khởi tạo + transcribe + tiêu thụ segment) trong một hàm `_chay(device)`, lỗi ở
  bất kỳ đâu trong đó đều kích hoạt thử lại TOÀN BỘ trên CPU. Test khoá lại:
  `test_transcribe_survey_lui_cpu_khi_cuda_loi_giua_chung` — verify bằng cách chạy lại
  trên code CŨ trước khi vá, xác nhận test FAIL đúng traceback thật của người dùng.
- **"Vẫn còn cmd mở kèm app còn thiếu chuyên nghiệp hơn."** Giữ `--console` lúc build
  (không đổi `--windowed`, tránh rủi ro `sys.stdout=None` làm vỡ `print()` rải rác khắp
  pipeline), nhưng ẨN cửa sổ console ngay khi khởi động bằng
  `ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)` — `print()` vẫn ghi bình thường (job
  log trong UI không phụ thuộc console, đọc qua `LogWriter`/`contextlib.redirect_stdout`),
  chỉ là cửa sổ không HIỆN ra. Kiểm bằng `EnumWindows`: trước khi vá thấy 2 cửa sổ (console
  + "CapCut Auto Editor"), sau khi vá chỉ còn đúng 1.

## Giới hạn đã biết (chưa/không giải quyết ở bản này)

- **Không ký số (unsigned).** Windows SmartScreen nhiều khả năng cảnh báo "Windows protected
  your PC" lần đầu mở — cần "More info" → "Run anyway". Chưa mua chứng chỉ ký code.
- **Model Whisper tải lần đầu cần mạng** (Hugging Face) — giống hệt bản chạy từ mã nguồn,
  không phải giới hạn riêng của `.exe`. Có thể bundle sẵn (~250-500MB tuỳ model) nếu cần
  zero-download thật sự — chưa làm ở bản này, người dùng chấp nhận tự tải lần đầu.
- **Gỡ cài đặt xoá LUÔN dữ liệu người dùng** (`library.db`, `assets/user`, `shorts/work`,
  `.env`) vì chúng nằm trong thư mục cài — đúng bản chất của cách ROOT hoạt động, không
  phải lỗi. Đã ghi đè `ConfirmUninstall` trong `installer.iss` để nói RÕ sẽ mất gì trước
  khi gỡ (luật cứng #4), nhưng nội dung hộp thoại đó chưa xác nhận bằng mắt thật.

## Chỗ dễ sập khi sửa code sau này

Mọi module cục bộ mới thêm (`shorts/*.py` hoặc file ở ROOT) phải được thêm vào mảng
`$MODULE_CUC_BO` trong `dong_goi.ps1`. Lý do: `app.py` và các module nối nhau bằng
`sys.path.insert(0, <đường dẫn tính lúc chạy>)` rồi mới `import`, PyInstaller phân tích
tĩnh bytecode (không thực thi code) nên **không suy ra được** — quên thêm là build "thành
công" nhưng mở `.exe` lên bị `ModuleNotFoundError` ngay import đầu tiên. Đã dính lỗi này
một lần lúc build thử (thiếu `build_short_draft`), vá bằng cách audit lại toàn bộ import
cục bộ trong từng file.

`assetlib._goc()` là nơi duy nhất quyết định ROOT — nếu thêm chỗ nào khác trong code tính
đường dẫn dữ liệu bằng `Path(__file__)` thay vì `assetlib.ROOT`, bản đóng gói sẽ ghi nhầm
vào `_internal/` và mất dữ liệu ở lần cập nhật sau. Test khoá lại:
`tests/test_smoke.py::test_root_dung_thu_muc_chua_exe_khi_dong_goi`.
