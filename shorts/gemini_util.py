# -*- coding: utf-8 -*-
"""gemini_util.py — gọi Gemini có THỬ LẠI và XOAY TUA MODEL.

Gặp thật nhiều lần trong dự án: 'gemini-3.5-flash' trả 503 UNAVAILABLE (quá tải),
hoặc resp.parsed về None khi output quá lớn. Trước đây mỗi chỗ tự xử lý -> có chỗ
nuốt lỗi rồi ghi cache RỖNG, hỏng ngầm. Gom về một chỗ.
"""
import time

# Thứ tự ưu tiên khi model chính hỏng. KIỂM CHỨNG bằng client.models.list() ngày
# 25/07/2026 — 'gemini-3-flash' trong danh sách cũ trả 404 với tài khoản này, mà 404
# không phải lỗi quá tải nên vòng thử lại bỏ qua luôn: cả cơ chế dự phòng thành vô
# dụng đúng lúc cần nhất. Model không tồn tại còn tệ hơn là không có dự phòng.
FALLBACKS = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.0-flash"]
OVERLOADED = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded")


def _call(client, model, contents, config, retries, quiet, require_parsed):
    chain = [model] + [m for m in FALLBACKS if m != model]
    last = None
    for mi, m in enumerate(chain):
        for attempt in range(retries):
            try:
                r = client.models.generate_content(model=m, contents=contents, config=config)
                if require_parsed and r.parsed is None:
                    last = "parsed=None (output có thể vượt giới hạn)"
                    break                   # đổi model, thử lại cùng model vô ích
                if mi and not quiet:
                    print(f"    (đã chuyển sang model '{m}')")
                return r, m
            except Exception as e:
                last = f"{type(e).__name__}: {str(e)[:90]}"
                if not any(k in str(e) for k in OVERLOADED):
                    break                   # không phải quá tải -> đổi model
                wait = 3 * (attempt + 1)
                if not quiet:
                    print(f"    {m} quá tải, chờ {wait}s rồi thử lại...")
                time.sleep(wait)
    raise RuntimeError(f"Gemini hỏng với cả {len(chain)} model — {last}")


def generate(client, model: str, *, contents, config, retries: int = 2, quiet: bool = False):
    """Cho structured output: BẮT BUỘC có resp.parsed, không thì đổi model.
    Trả (response, model_đã_dùng); ném RuntimeError nếu mọi model đều hỏng."""
    return _call(client, model, contents, config, retries, quiet, require_parsed=True)


def generate_raw(client, model: str, *, contents, config, retries: int = 2, quiet: bool = True):
    """Cho function-calling / chat: KHÔNG đòi resp.parsed (phản hồi là function_call
    hoặc text), chỉ thử lại + xoay model khi lỗi."""
    return _call(client, model, contents, config, retries, quiet, require_parsed=False)
