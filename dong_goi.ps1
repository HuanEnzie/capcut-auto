# dong_goi.ps1 — Đóng gói CapCut Auto Editor thành .exe standalone (PyInstaller).
#
# --onedir (KHÔNG --onefile): --onefile giải nén ra thư mục tạm mỗi lần chạy rồi xoá
# khi thoát — assetlib.ROOT (thư mục chứa .exe) vẫn đúng vì Path(sys.executable) trỏ
# vào chính file .exe thật, nhưng bản thân uvicorn/faster-whisper native libs phải
# GIẢI NÉN LẠI mỗi lần mở app (chậm khởi động, và một số DLL native hay lỗi khi giải
# nén-chạy-xoá liên tục trên Windows). --onedir giữ mọi thứ là file thật trên đĩa,
# khởi động nhanh hơn nhiều, và người dùng nhìn được thư mục — đúng luật "đo, đừng
# đoán": không có gì ẩn trong một file nén.
#
# --collect-all cho các gói có phần BIÊN DỊCH SẴN (ctranslate2, tokenizers) hoặc hay
# import động (uvicorn, fastapi, pydantic): PyInstaller phân tích tĩnh bytecode nên
# bắt được hầu hết import, nhưng native .pyd/.dll và import kiểu plugin (uvicorn chọn
# loop/protocol lúc chạy) thường lọt lưới — collect-all an toàn hơn, đổi lấy build to
# hơn. Ưu tiên CHẠY ĐÚNG trước, tối ưu kích thước sau khi đã có bằng chứng chạy được.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==== Dọn build cũ ====" -ForegroundColor Cyan
Remove-Item -Recurse -Force "build","dist" -ErrorAction SilentlyContinue

# MODULE CỤC BỘ: app.py và các module trong shorts/ nối nhau bằng
# `sys.path.insert(0, <đường dẫn TÍNH LÚC CHẠY>)` rồi mới `import tên_module`. Phân
# tích tĩnh của PyInstaller (đọc bytecode, không THỰC THI code) không thể suy ra giá
# trị runtime đó, nên toàn bộ chuỗi module nối theo kiểu này BỊ BỎ SÓT — build "thành
# công" nhưng chạy lên là ModuleNotFoundError ngay dòng import đầu tiên. Phải liệt kê
# TƯỜNG MINH qua --hidden-import, và chỉ đường bằng --paths để PyInstaller tìm ra
# chúng (chúng không nằm trong site-packages).
# Danh sách chốt bằng cách ĐỌC HẾT từng file (không đoán): mọi module cục bộ ở ROOT
# và shorts/ đều chỉ import lẫn nhau + `assetlib`, không có cascading nào khác.
$MODULE_CUC_BO = @(
    "agent","asset_restore","audio_balance","capcut_build","capcut_inventory",
    "draft_diff","draft_scan","projects",
    "build_short_draft","caption_fix","cuda_setup","enrich","gemini_util",
    "hinh_anh","pexels","render_short","topics","transcribe"
)
$hiddenArgs = $MODULE_CUC_BO | ForEach-Object { "--hidden-import=$_" }

Write-Host "==== Chạy PyInstaller (có thể mất vài phút) ====" -ForegroundColor Cyan
& .venv\Scripts\python.exe -m PyInstaller `
    --name CapCutAuto `
    --onedir `
    --console `
    --noconfirm `
    --paths . `
    --paths shorts `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all tokenizers `
    --collect-all huggingface_hub `
    --collect-all google.genai `
    --collect-all google.auth `
    --collect-all uvicorn `
    --collect-all fastapi `
    --collect-all starlette `
    --collect-all pydantic `
    --collect-all pydantic_core `
    --collect-all yaml `
    --hidden-import multipart `
    --hidden-import watchdog `
    @hiddenArgs `
    app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller thất bại (exit $LASTEXITCODE)" }

$OUT = "dist\CapCutAuto"
if (-not (Test-Path $OUT)) { throw "Không thấy $OUT sau khi build" }

Write-Host "==== Chép asset (ui.html, assets/, shorts/profiles/) cạnh .exe ====" -ForegroundColor Cyan
Copy-Item "ui.html" "$OUT\ui.html" -Force
New-Item -ItemType Directory -Force -Path "$OUT\assets" | Out-Null
Copy-Item "assets\default" "$OUT\assets\default" -Recurse -Force
Copy-Item "assets\donor"   "$OUT\assets\donor"   -Recurse -Force
Copy-Item "assets\fonts"   "$OUT\assets\fonts"   -Recurse -Force
New-Item -ItemType Directory -Force -Path "$OUT\shorts\profiles" | Out-Null
Copy-Item "shorts\profiles\*.yaml" "$OUT\shorts\profiles\" -Force

Write-Host "==== Xong ====" -ForegroundColor Green
$sz = (Get-ChildItem $OUT -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
$n  = (Get-ChildItem $OUT -Recurse -File).Count
Write-Host ("Thư mục: {0}  ·  {1:N0} MB  ·  {2:N0} file" -f (Resolve-Path $OUT), $sz, $n)
Write-Host "Chạy thử: $OUT\CapCutAuto.exe"
