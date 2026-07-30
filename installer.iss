; installer.iss — Inno Setup: đóng gói dist/CapCutAuto/ (sinh ra từ dong_goi.ps1)
; thành một file Setup.exe duy nhất, cài đặt kiểu app desktop chuẩn (wizard, shortcut,
; gỡ được qua "Add or Remove Programs").
;
; CÀI VÀO {localappdata}\Programs\CapCutAuto, KHÔNG PHẢI Program Files: assetlib.ROOT
; là chính thư mục chứa .exe, và app GHI DỮ LIỆU THẬT vào đó lúc chạy (library.db,
; assets/user, shorts/work, .env — xem assetlib._goc()). Program Files bị khoá ghi
; với người dùng thường (cần quyền admin) — cài vào đó thì lần chạy đầu tiên đã hỏng
; ngay ở bước tạo thư mục dữ liệu. Cài theo-người-dùng vào LocalAppData (giống
; VS Code, Discord) thì luôn ghi được, không cần UAC, không cần chạy Setup bằng admin.
;
; Build: "C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss
; (chạy dong_goi.ps1 trước — installer đóng gói NGUYÊN dist\CapCutAuto\, không tự build)

#define MyAppName "CapCut Auto Editor"
#define MyAppVersion "1.0.3"
#define MyAppExeName "CapCutAuto.exe"

[Setup]
AppId={{B3F1E1B4-9C5C-4E76-9A9B-2C1E9E5F6A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\CapCutAuto
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_out
OutputBaseFilename=CapCutAuto-Setup-v{#MyAppVersion}
Compression=lzma2/normal
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tạo shortcut ngoài Desktop"; GroupDescription: "Shortcut khác:"; Flags: unchecked

[Files]
Source: "dist\CapCutAuto\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Gỡ cài đặt {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Mở {#MyAppName} ngay"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Chỉ dọn cache pip/model nếu có — KHÔNG đụng library.db, assets/user, shorts/work,
; .env: đó là dữ liệu thật của người dùng, không phải sinh ra từ lúc cài. Inno Setup
; mặc định chỉ xoá đúng file đã cài (mục [Files]) rồi hỏi lại nếu thư mục còn sót file
; lạ — đúng ý muốn, không cần khai gì thêm ở đây.

[Messages]
; Mặc định của Inno Setup chỉ hỏi chung chung "remove [app] and all of its components?"
; — KHÔNG đủ, vì gỡ app này còn xoá theo library.db/assets/user/shorts/work/.env, tức
; dữ liệu THẬT (thư viện đã học, record đã phân tích, API key), không phải chỉ chương
; trình. Luật cứng #4 của dự án: việc phá huỷ phải hỏi trước VÀ nêu rõ mất cái gì —
; câu hỏi mặc định của Inno Setup không đạt, phải ghi đè.
ConfirmUninstall=Gỡ {#MyAppName}?%n%nViệc này xoá LUÔN dữ liệu trong thư mục cài đặt: thư viện SFX/tài nguyên đã học theo gu editor, các record đã phân tích (transcript, chủ đề), và API key đã lưu.%n%nDraft đã tạo TRONG CapCut không bị ảnh hưởng — chỉ mất dữ liệu bên trong app này. Chắc chắn muốn gỡ?
