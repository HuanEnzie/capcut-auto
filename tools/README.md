# tools/ — script khảo sát, KHÔNG phải một phần của app

Mấy file này dùng để mổ cấu trúc `draft_content.json` của CapCut hồi đầu dự án, giữ lại
làm tham khảo khi CapCut đổi format. **Không module nào của app import chúng** — xoá đi
app vẫn chạy.

| File | Việc |
|---|---|
| `inspect_draft.py` | In sơ đồ track/segment/material của một draft |
| `inspect_caption.py`, `inspect_caption2.py` | Mổ riêng cụm caption (`text_template_subtitle`) |
| `extract_templates.py` | Bóc mảnh template thật từ draft → `templates.json` |
| `templates.json` | Kết quả bóc (52 KB) — tài liệu tham khảo, builder không đọc |
| `drstone_script.txt` | Kịch bản mẫu để test caption |

Chạy từ gốc dự án: `python tools/inspect_draft.py <tên draft>`
