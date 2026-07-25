# -*- coding: utf-8 -*-
"""gemini_util.py — gọi Gemini có THỬ LẠI, XOAY MODEL và XOAY KEY.

Gặp thật nhiều lần trong dự án: 503 UNAVAILABLE (quá tải), resp.parsed về None khi
output quá lớn, và 429 RESOURCE_EXHAUSTED khi cạn hạn ngạch. Trước đây mỗi chỗ tự
xử lý -> có chỗ nuốt lỗi rồi ghi cache RỖNG, hỏng ngầm. Gom về một chỗ.

⚠️ XOAY KEY CHỈ CÓ TÁC DỤNG KHI CÁC KEY THUỘC PROJECT KHÁC NHAU.
   Tài liệu Google: "Giới hạn được áp dụng PER PROJECT, không phải per API key —
   tất cả key trong project chia sẻ cùng giới hạn." Nhét 5 key của cùng một project
   vào đây thì vẫn đúng một túi hạn ngạch, chỉ tốn công.

HẠN NGẠCH LÀ RÀNG BUỘC THẬT, KHÔNG PHẢI CHI TIẾT PHỤ (bậc Free, đo 25/07/2026):
    gemini-2.5-flash / 3.5-flash / 3.6-flash   RPM 5    RPD 20
    gemini-3.1-flash-lite / 3.5-flash-lite     RPM 15   RPD 500
Một tin nhắn agent tốn tới 6 lượt gọi (max_steps) -> với RPD 20 là hết quota sau
~3 tin nhắn/ngày. Nên chuỗi cho CHAT phải ưu tiên model RPD cao; chuỗi cho việc
cần chất lượng (trích chủ đề, enrich) thì vẫn ưu tiên model mạnh.
"""
import os, time

# Chuỗi CHẤT LƯỢNG: cho structured output, chạy ít lần, cần model mạnh.
# KIỂM CHỨNG bằng client.models.list() — 'gemini-3-flash' trong danh sách cũ trả
# 404 với tài khoản này, mà 404 không phải lỗi quá tải nên vòng thử lại bỏ qua
# luôn: cả cơ chế dự phòng thành vô dụng đúng lúc cần nhất.
FALLBACKS = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.0-flash"]

# Chuỗi HẠN NGẠCH: cho vòng lặp chat/tool gọi nhiều lần. RPD 500 thay vì 20.
FALLBACKS_CHAT = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
                  "gemini-2.5-flash", "gemini-3.5-flash", "gemini-2.0-flash"]

OVERLOADED = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded")
HET_NGAY = ("PerDay", "per day", "daily limit", "RequestsPerDay")

NGHI_RPM = 60         # 429 theo phút -> nghỉ ngắn
NGHI_RPD = 1800       # 429 theo ngày -> nghỉ dài (RPD reset nửa đêm PST; ước lượng
                      # thô thay vì tính múi giờ, cùng lắm phí 1 lần gọi mỗi 30 phút)


class HetHanNgach(RuntimeError):
    """Cạn hạn ngạch trên MỌI key và MỌI model — khác hẳn 'model chọn sai tool'.
    Có lớp riêng để tầng trên báo đúng nguyên nhân cho người dùng."""


def keys() -> list:
    """GEMINI_API_KEYS='k1,k2,k3' (nên là key của các PROJECT khác nhau),
    hoặc GEMINI_API_KEY đơn lẻ như cũ."""
    if not (os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY")):
        try:                    # script chạy thẳng trong shorts/ chưa nạp .env
            import assetlib
            assetlib.load_env()
        except ImportError:
            pass
    raw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
    ds, thay = [], set()
    for k in raw.split(","):
        k = k.strip()
        if k and k not in thay:
            thay.add(k); ds.append(k)
    return ds


_CLIENTS: dict = {}
_NGHI: dict = {}      # key -> thời điểm được dùng lại


def _client(k: str):
    from google import genai
    if k not in _CLIENTS:
        _CLIENTS[k] = genai.Client(api_key=k)
    return _CLIENTS[k]


def _dang_nghi(k: str) -> bool:
    return _NGHI.get(k, 0) > time.time()


def _cho_nghi(k: str, loi: str):
    _NGHI[k] = time.time() + (NGHI_RPD if any(x in loi for x in HET_NGAY) else NGHI_RPM)


def trang_thai() -> list:
    """Key nào đang nghỉ và còn bao lâu — để giao diện nói được lý do."""
    now = time.time()
    return [{"key": k[:8] + "…", "dang_nghi": _NGHI.get(k, 0) > now,
             "con_giay": max(0, round(_NGHI.get(k, 0) - now))} for k in keys()]


def _call(client, model, contents, config, retries, quiet, require_parsed, chain=None):
    ds_key = keys() or [None]                  # None = dùng client caller đưa vào
    ds_model = [model] + [m for m in (chain or FALLBACKS) if m != model]
    last, het_ngach = None, False
    for mi, m in enumerate(ds_model):
        for k in ds_key:
            if k is not None and _dang_nghi(k):
                continue                        # key này vừa 429, khỏi phí lượt gọi
            cl = client if k is None else _client(k)
            for attempt in range(retries):
                try:
                    r = cl.models.generate_content(model=m, contents=contents, config=config)
                    if require_parsed and r.parsed is None:
                        last = "parsed=None (output có thể vượt giới hạn)"
                        break                   # đổi model, thử lại cùng model vô ích
                    if mi and not quiet:
                        print(f"    (đã chuyển sang model '{m}')")
                    return r, m
                except Exception as e:
                    s = str(e)
                    last = f"{type(e).__name__}: {s[:90]}"
                    if "429" in s or "RESOURCE_EXHAUSTED" in s:
                        het_ngach = True
                        if k is not None:
                            _cho_nghi(k, s)
                        break                   # sang key/model khác, chờ ở đây vô ích
                    if not any(x in s for x in OVERLOADED):
                        break                   # không phải quá tải -> đổi model
                    wait = 3 * (attempt + 1)
                    if not quiet:
                        print(f"    {m} quá tải, chờ {wait}s rồi thử lại...")
                    time.sleep(wait)
    if het_ngach:
        raise HetHanNgach(
            f"Cạn hạn ngạch Gemini trên {len(ds_key)} key × {len(ds_model)} model. "
            f"Bậc Free: gemini-2.5-flash chỉ 20 request/NGÀY (reset nửa đêm giờ Thái Bình "
            f"Dương). Thêm key của PROJECT KHÁC vào GEMINI_API_KEYS, hoặc chờ reset. — {last}")
    raise RuntimeError(f"Gemini hỏng với cả {len(ds_model)} model — {last}")


def generate(client, model: str, *, contents, config, retries: int = 2, quiet: bool = False,
             chain=None):
    """Cho structured output: BẮT BUỘC có resp.parsed, không thì đổi model.
    Trả (response, model_đã_dùng); ném RuntimeError/HetHanNgach nếu mọi lối đều hỏng."""
    return _call(client, model, contents, config, retries, quiet, True, chain)


def generate_raw(client, model: str, *, contents, config, retries: int = 2, quiet: bool = True,
                 chain=None):
    """Cho function-calling / chat: KHÔNG đòi resp.parsed (phản hồi là function_call
    hoặc text), chỉ thử lại + xoay model/key khi lỗi."""
    return _call(client, model, contents, config, retries, quiet, False, chain)
