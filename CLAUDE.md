# CapCut Auto Editor — ghi chú cho Claude Code

Trả lời bằng **tiếng Việt**. Bình luận trong code cũng tiếng Việt, và phải giải thích
**VÌ SAO** chứ không mô tả lại code.

## Dự án này là gì

Biến một buổi ghi hình 2-4 tiếng thành nhiều short dạng **DỰ ÁN CapCut còn sửa được**
(ghi thẳng `draft_content.json`, không thao tác UI), và **học dần gu của từng editor**
để lần sau tự lên đúng phong cách. ~6.300 dòng Python + `ui.html`.

Đọc theo thứ tự khi cần hiểu sâu:
1. `docs/WORKFLOW.md` — toàn bộ cơ chế vận hành, 7 cơ chế then chốt, 2 thất bại lớn
2. `docs/V1.md` — phạm vi v1 đang chốt + tiêu chí chấm điểm phát hành
3. `docs/UI.md` — quy tắc giao diện, **đọc trước khi sửa `ui.html`**
4. `docs/ROADMAP.md` — hướng dài hạn

## Chạy và kiểm tra

```bash
cai_dat.bat            # cài lần đầu (tạo .venv, thư viện, thư mục dữ liệu, dò CapCut)
chay.bat               # mở app ở http://127.0.0.1:8765
python -m pytest -q tests    # 23 bài smoke test — CHẠY SAU MỖI LẦN SỬA
```

`.env` (API key) **không đi theo git**. Máy mới: mở app → mục **Cài đặt** → dán key.

## Luật cứng — rút ra từ lỗi ĐÃ TRẢ GIÁ trong dự án này

1. **Đo, đừng đoán.** Mọi con số trong tài liệu đều đo được và ghi rõ đo trên máy nào.
   Thấy tên thư mục rồi suy ra nội dung là đoán — đã sai một lần với `Presets/` (rỗng).
2. **Không có hỏng im lặng.** Tool trả rỗng, cache ghi kết quả tệ, SFX thiếu, tóm tắt
   cụt — tất cả phải BÁO. Lỗi im lặng đắt hơn crash nhiều lần.
3. **Không hardcode đường dẫn máy dev.** Đã dính 3 lần: đường dẫn CapCut, thư mục SFX,
   draft mẫu `282new`. Có test chặn (`test_khong_con_hardcode_may_dev`).
4. **Việc phá huỷ phải hỏi trước.** Ghi đè draft, dọn tài nguyên, ghi âm lượng — đều
   phải xác nhận + có đường lùi. Agent chỉ được ĐỀ XUẤT, người dùng bấm nút mới chạy.
5. **Sửa bug thì thêm test khoá lại.** Mỗi bài trong `tests/test_smoke.py` tương ứng
   một lỗi đã xảy ra thật.

## Chỗ dễ sập — biết trước đỡ mất thời gian

| Chỗ | Cạm bẫy |
|---|---|
| Đường dẫn CapCut | Dò bằng `assetlib.find_capcut()` (đọc `globalSetting`). **Không** tự ghép `%LOCALAPPDATA%` |
| `shorts/work/`, `assets/` | Draft CapCut giữ **đường dẫn tuyệt đối** vào đây; `library.db` giữ path tương đối. **Dời là hỏng draft** — cần script migration |
| Draft mẫu `assets/donor/282new` | Builder clone cấu trúc từ đây. Đường dẫn cache trong đó tự đổi sang máy đang chạy khi `load_draft()` |
| Hạn ngạch Gemini | Bậc Free: model thường **RPD 20**, model `-lite` **RPD 500**. Chuỗi xoay model ở `shorts/gemini_util.py`. Cạn thì ném `HetHanNgach`, đừng nuốt |
| Gemini 2.5 | Tính **cả token suy nghĩ** vào `max_output_tokens` → để nhỏ là trả lời cụt giữa câu |
| faster-whisper trên Windows | Cần `HF_HUB_DISABLE_SYMLINKS=1`, không thì tải model lần đầu ném `WinError 1314` |
| `cpu_threads` | Nhồi nhiều luồng **chậm hơn**. Dùng `transcribe._luong_cpu()` (chừa 1 nhân cho web server) |
| Bối cảnh agent | API stateless, mỗi lượt gửi lại tất cả. Cắt theo **token**; hy sinh dữ liệu tool trước, **giữ lời người dùng** |

## Trạng thái hiện tại (26/07/2026)

**Đang ở giai đoạn nghiệm thu v1.** Đích: nội bộ (Đan, Nguyên) + 1-2 khách thử nghiệm,
mình cài hộ từng máy.

5/6 mục chặn phát hành đã xong. Còn **B5 — chạy thử trên máy khác**, đang làm dở trên
máy trạm công ty. Xem `docs/TEST_MAY_KHAC.md` (phiếu chấm 16 mục).

Hai lỗi vừa bắt được trên máy trạm và đã vá — **cần xác nhận lại**:
- draft mẫu `282new` không đi theo app → build chết ở phút thứ 10
- chuỗi model cho structured output toàn RPD 20 → cạn hạn ngạch giữa chừng

Máy trạm có card NVIDIA nhưng **driver quá cũ** so với CUDA runtime → đang lùi về CPU,
chậm hơn ~5 lần. Cập nhật driver là đòn bẩy lớn nhất còn lại.

## Cách làm việc mong đợi

- Việc nặng → chạy nền, báo tiến trình thật (có thời gian còn lại, không chỉ %).
- Sửa xong thì **chạy app lên xem tận mắt**, đừng chỉ tin là chạy được.
- Nói thẳng khi đo được điều trái với giả định trong tài liệu — rồi **sửa tài liệu**.
- Commit message tiếng Việt, nêu **vì sao** và **đã kiểm chứng thế nào**.
