# Đóng gói .exe (PyInstaller)

Từ 30/07/2026, ngoài cách chạy từ mã nguồn (`cai_dat.bat` + `chay.bat`), có thêm bản
`.exe` standalone — không cần cài Python, không cần `.venv`. Dùng khi đưa cho người
không rành dòng lệnh, hoặc máy không tiện cài Python.

## Build lại

```powershell
.\dong_goi.ps1
```

Cần `.venv` đã cài `pyinstaller` (`pip install pyinstaller` nếu chưa có). Script tự dọn
`build/`, `dist/` cũ, chạy PyInstaller ở chế độ `--onedir`, rồi chép `ui.html`,
`assets/{default,donor,fonts}`, `shorts/profiles/*.yaml` vào cạnh `.exe` (những thứ này
PyInstaller không tự gom vì không phải import Python). Ra `dist/CapCutAuto/CapCutAuto.exe`,
**276 MB, ~1900 file** (đo 30/07/2026) — phần lớn là `ctranslate2`/`faster-whisper`
(binary CUDA+CPU) và runtime CPython.

Đưa cho người khác: **nén cả thư mục `dist/CapCutAuto`**, không phải chỉ file `.exe` —
thiếu `_internal/`, `ui.html`, `assets/` thì mở lên là lỗi ngay.

## Vì sao `--onedir`, không `--onefile`

`--onefile` giải nén ra thư mục tạm mỗi lần mở rồi xoá khi thoát — khởi động chậm hơn
nhiều lần, và các thư viện native (`ctranslate2.dll`) hay lỗi khi giải nén-chạy-xoá liên
tục trên Windows. `--onedir` giữ mọi thứ là file thật trên đĩa: khởi động nhanh, và đúng
luật "đo, đừng đoán" trong dự án này — không có gì ẩn trong một file nén.

## Đã kiểm chứng thật (đo 30/07/2026, trên máy dev)

Copy `dist/CapCutAuto` sang thư mục **tách biệt hoàn toàn** khỏi cây mã nguồn (để loại
khả năng bản đóng gói ngầm phụ thuộc `.venv` hay file cạnh đó), cắt 45s từ một video thật
làm input, chạy `CapCutAuto.exe`, rồi gọi trọn pipeline `/api/ingest` qua HTTP:

| Bước | Kết quả đo được |
|---|---|
| Web server khởi động | Sống sau ~6s, `/api/overview` trả JSON đúng |
| Dò CapCut | Tự tìm đúng thư mục draft qua `globalSetting`, không hardcode |
| ROOT đúng chỗ | Ghi dữ liệu (transcript cache, `.env`) vào thư mục chứa `.exe`, không lạc vào `_internal/` |
| ASR thật (`faster-whisper`/`ctranslate2`) | **CHẠY ĐƯỢC** — `17,1x realtime`, không lỗi DLL native. CUDA lỗi driver cũ → tự lùi CPU đúng thiết kế |
| Đo hình đứng yên (`hinh_anh.py`, freezedetect) | Chạy đúng, ra cảnh báo "68% thời lượng hình gần như ĐỨNG YÊN" |
| Gemini API (làm sạch transcript + trích chủ đề) | **CHẠY ĐƯỢC** với `.env` thật — `topics.json` ra 1 chủ đề hợp lệ, không lỗi |

Đây là bằng chứng cho rủi ro kỹ thuật lớn nhất của việc đóng gói: `ctranslate2` là binary
biên dịch sẵn, PyInstaller phân tích tĩnh bytecode dễ bỏ sót — nếu nó không chạy được thì
cả bản đóng gói vô nghĩa. Đã đo chạy được, không phải đoán.

## Giới hạn đã biết (chưa/không giải quyết ở bản này)

- **ffmpeg không đi kèm.** App khởi động vẫn được, nhưng dựng draft sẽ chết giữa chừng —
  sau khi đã tốn thời gian bóc lời. `ui.html` đã có cảnh báo ngay trên trang Tổng quan nếu
  thiếu (`assetlib.co_ffmpeg()`). Người dùng tự tải bản "essentials" tại
  [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) và thêm vào PATH.
- **Không ký số (unsigned).** Windows SmartScreen nhiều khả năng cảnh báo "Windows protected
  your PC" lần đầu mở — cần "More info" → "Run anyway". Chưa mua chứng chỉ ký code.
- **Kích thước 276 MB.** Chấp nhận được cho nội bộ/khách thử nghiệm; nếu phát tán rộng nên
  cân nhắc nén trước khi gửi.
- **Model Whisper tải lần đầu cần mạng** (Hugging Face) — giống hệt bản chạy từ mã nguồn,
  không phải giới hạn riêng của `.exe`.
- **Nhánh THIẾU ffmpeg thật sự chưa thử chạy dựng draft** (chỉ xác nhận cảnh báo hiện đúng
  trên Tổng quan) — nếu cần chứng minh app không sập, phải đo riêng.

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
