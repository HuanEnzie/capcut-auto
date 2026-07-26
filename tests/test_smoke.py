# -*- coding: utf-8 -*-
"""Smoke test — chạy sau mỗi lần sửa và ngay sau khi cài trên máy mới.

KHÔNG phải bộ test đầy đủ. Mục tiêu hẹp: bắt những thứ mà nếu hỏng thì app vô
dụng, và bắt lại đúng các lỗi ĐÃ TỪNG xảy ra trong dự án — vì lỗi đã xảy ra một
lần thì hay quay lại:

  * hardcode đường dẫn máy dev  (SFX rỗng trên máy khác, im lặng)
  * mốc so với chính nó lại báo có thay đổi  (chỉ số độ phải sửa nói dối)
  * model dự phòng không tồn tại  (cơ chế xoay model thành vô dụng)
  * tham số tool sai hoa/dấu -> trả rỗng thay vì lỗi  (agent bịa số liệu)
  * việc phá huỷ tự chạy không hỏi  (mất draft editor vừa sửa)

Chạy: python -m pytest -q tests
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "shorts"))

import assetlib                                   # noqa: E402


# ─────────────── nền tảng ───────────────

def test_import_moi_module():
    """Mọi module chính phải import được — bắt lỗi cú pháp và import vòng."""
    import agent, app, asset_restore, audio_balance, capcut_inventory  # noqa: F401
    import capcut_auto, capcut_build, draft_diff, draft_scan           # noqa: F401


def test_thu_muc_du_lieu_tu_tao(tmp_path, monkeypatch):
    monkeypatch.setattr(assetlib, "ROOT", tmp_path)
    tao = assetlib.khoi_tao()
    assert set(tao) == set(assetlib.THU_MUC_DU_LIEU)
    for r in assetlib.THU_MUC_DU_LIEU:
        assert (tmp_path / r).is_dir()


def test_do_capcut_khong_crash_khi_chua_cai(monkeypatch):
    """Máy chưa cài CapCut vẫn phải trả đường dẫn dùng được, found=False."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("CAPCUT_DRAFTS_ROOT", raising=False)
    d = assetlib.find_capcut(refresh=True)
    assert d["found"] is False and isinstance(d["draft"], Path)
    assetlib.find_capcut(refresh=True)             # trả lại trạng thái thật


def test_khong_con_hardcode_may_dev():
    """Đường dẫn máy dev chỉ được xuất hiện như NGUỒN PHỤ, không phải nguồn duy nhất."""
    xau = ("Users/Acer", "Users\\\\Acer")
    for f in list(ROOT.glob("*.py")) + list((ROOT / "shorts").glob("*.py")):
        t = f.read_text(encoding="utf-8", errors="replace")
        for dong in t.splitlines():
            if dong.strip().startswith("#") or '"""' in dong:
                continue
            assert not any(x in dong for x in xau), f"{f.name}: còn hardcode -> {dong.strip()[:70]}"


# ─────────────── SFX: lỗi hỏng im lặng đã từng gặp ───────────────

def test_sfx_co_san_khong_can_thu_muc_may_dev():
    kho = assetlib.sfx_kho("Z:/thu-muc-khong-ton-tai")
    assert len(kho) >= 20, "kho SFX mặc định phải đi theo app"
    assert all(Path(p).exists() for p in kho.values())


# ─────────────── chỉ số độ phải sửa ───────────────

def test_van_tay_so_voi_chinh_no_phai_bang_khong():
    """Bug đã gặp: ghép caption bằng dict khoá theo chữ -> caption trùng chữ bị so
    nhầm dòng -> so mốc với chính nó vẫn ra 'đổi giờ 18 dòng'."""
    import draft_diff as dd
    goc = {"caption": [{"t": "cùng một câu", "s": i * 1_000_000, "d": 900_000} for i in range(30)],
           "video": [{"s": 0, "d": 5_000_000}], "am_luong": {"a.mp3": 0.5}, "tong_dai": 5_000_000}
    s = dd._so_van_tay(goc, goc)
    assert s["caption"] == {"tong": 30, "sua_hoac_them": 0, "bo": 0, "doi_gio": 0}
    assert dd._diem(s, 0, 0) == 0.0


def test_diem_phai_sua_tang_theo_muc_do_sua():
    import copy

    import draft_diff as dd
    goc = {"caption": [{"t": f"câu {i}", "s": i * 1_000_000, "d": 900_000} for i in range(20)],
           "video": [{"s": 0, "d": 5_000_000}], "am_luong": {"a.mp3": 0.5}, "tong_dai": 5_000_000}
    nhe = copy.deepcopy(goc); nhe["caption"][0]["t"] = "đã sửa"
    nang = copy.deepcopy(goc); nang["caption"] = nang["caption"][:3]
    d_nhe = dd._diem(dd._so_van_tay(goc, nhe), 0, 0)
    d_nang = dd._diem(dd._so_van_tay(goc, nang), 0, 0)
    assert 0 < d_nhe < d_nang <= 1.0


# ─────────────── agent ───────────────

def test_registry_tool_hop_le():
    import agent
    assert len(agent.TOOLS) >= 10
    for t in agent.TOOLS.values():
        assert t.kieu in ("doc", "nen", "nguy_hiem")
        assert t.mo_ta.strip() and t.tham_so.get("type") == "object"
        if t.kieu == "nguy_hiem":
            assert t.canh_bao.strip(), f"{t.ten}: việc phá huỷ phải có cảnh báo"


def test_thieu_tham_so_tra_loi_co_cau_truc():
    """Không được ném TypeError của Python vào mặt model."""
    import agent
    r = agent.goi_tool("xem_editor_sua_gi", {})
    assert r.get("thieu") == ["draft"] and "goi_y" in r


def test_chuan_hoa_tham_so_hoa_dau():
    """Bug đã gặp: owner='Đan' -> lọc ra RỖNG mà không báo lỗi -> agent nói
    'Đan chưa có tài nguyên nào'. Sai sự thật, không bắt được."""
    import agent
    ds = agent._ds_editor()
    if "dan" not in ds:
        pytest.skip("máy này chưa có editor 'dan' trong kho")
    r = agent.goi_tool("kho_tai_nguyen", {"owner": "Đan"})
    assert "loi" not in r and r["tong_theo_bo_loc"] > 0


def test_gia_tri_sai_tra_kem_lua_chon_hop_le():
    import agent
    r = agent.goi_tool("kho_tai_nguyen", {"owner": "KhongCoAi"})
    assert "gia_tri_hop_le" in r and r["gia_tri_hop_le"]


def test_viec_pha_huy_khong_tu_chay():
    """Agent chỉ được ĐỀ XUẤT; chạy thật phải qua nút xác nhận.

    Dùng dự án CÓ THẬT: chuẩn hoá tham số chạy TRƯỚC cổng xác nhận (đúng thứ tự —
    tham số sai thì báo sai tham số, không đề xuất một việc vô nghĩa)."""
    import agent
    ds = agent._ds_du_an()
    if not ds:
        pytest.skip("máy này chưa có dự án nào đã phân tích")
    r = agent.goi_tool("dung_draft", {"project": ds[0], "topic": 1})
    assert r.get("can_xac_nhan") is True and r.get("canh_bao")


def test_cat_boi_canh_giu_loi_nguoi_dung_bo_du_lieu_tool():
    """Ngân sách token: hy sinh dữ liệu tool (gọi lại được), giữ lời người dùng."""
    import agent
    ss = "test_smoke_ctx"
    agent.reset(ss)
    c = agent._init_db(); c.execute("DELETE FROM chat_summary WHERE session=?", (ss,))
    c.commit(); c.close()
    try:
        for i in range(15):
            agent._save(ss, "user", f"câu hỏi {i}")
            agent._save_tool(ss, "kho_tai_nguyen", {}, {"x": "y" * 400})
        ls = agent.dung_lich_su(ss, ngan_sach=1200)
        assert sum(1 for m in ls if m["role"] == "user") == 15
        assert any(m["content"].startswith("[đã tra") for m in ls)
        assert sum(agent.uoc_token(m["content"]) for m in ls) <= 1200 * 1.1
    finally:
        agent.reset(ss)


# ─────────────── gọi Gemini ───────────────

def test_chuoi_model_du_phong_khong_rong():
    """Bug đã gặp: chuỗi dự phòng chứa model 404 -> 404 không phải lỗi quá tải nên
    vòng thử lại bỏ qua, cả cơ chế dự phòng thành vô dụng."""
    import gemini_util
    assert gemini_util.FALLBACKS and gemini_util.FALLBACKS_CHAT
    assert gemini_util.FALLBACKS_CHAT[0].endswith("-lite"), \
        "chuỗi chat phải ưu tiên model RPD cao"


@pytest.mark.skipif(not assetlib.load_env() and not __import__("os").environ.get("GEMINI_API_KEY"),
                    reason="chưa có GEMINI_API_KEY")
def test_model_trong_chuoi_du_phong_deu_ton_tai():
    import os

    from google import genai

    import gemini_util
    cl = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    co = {m.name.replace("models/", "") for m in cl.models.list()}
    thieu = [m for m in set(gemini_util.FALLBACKS + gemini_util.FALLBACKS_CHAT) if m not in co]
    assert not thieu, f"model không tồn tại với key này: {thieu}"


# ─────────────── API ───────────────

def test_api_khong_lo_key():
    """Màn hình Cài đặt chỉ được trả key dạng che."""
    import app
    d = app.api_settings()
    for n in d["nha_cung_cap"]:
        assert "…" in n["che"] or n["che"] in ("", "đã có")
        assert len(n["che"]) < 20


def test_api_chinh_tra_ve_duoc():
    import app
    assert "drafts" in app.api_drafts()
    assert "projects" in app.api_projects()
    assert "stats" in app.api_inventory(limit=1)
    ov = app.api_overview()
    assert {"projects", "todo", "capcut"} <= set(ov)


def test_mo_thu_muc_chan_di_ra_ngoai():
    import app
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        app.api_draft_open("khong-ton-tai-dau")


def test_giao_dien_khong_dung_hop_thoai_trinh_duyet():
    """docs/UI.md mục 5: alert/confirm/prompt bị cấm."""
    t = (ROOT / "ui.html").read_text(encoding="utf-8")
    for cam in ("alert(", "confirm(", "prompt("):
        for dong in t.splitlines():
            truoc = dong.split(cam)[0]
            la_ghi_chu = "//" in truoc or "/*" in truoc or dong.strip().startswith(("*", "/*"))
            if cam in dong and "confirmBox" not in dong and not la_ghi_chu:
                pytest.fail(f"ui.html còn dùng {cam} -> {dong.strip()[:60]}")
