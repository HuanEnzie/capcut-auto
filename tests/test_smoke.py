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


# ─────────────── draft mẫu (donor) — lỗi bắt được trên máy trạm 26/07 ───────────────

def test_draft_mau_di_theo_app():
    """Bug đã gặp: donor '282new' chỉ nằm trong thư mục CapCut của máy dev. Máy khác
    build chạy hết 10 phút rồi mới chết ở dòng cuối vì FileNotFoundError."""
    import capcut_build as cb
    for ten in {cb.DONOR_VIDEO, "282new"}:
        p = cb.DONOR_DIR / ten
        if p.is_dir():
            assert (p / "draft_content.json").is_file()
            return
    pytest.fail("không có draft mẫu nào trong assets/donor/ — máy mới sẽ không build được")


def test_draft_mau_doi_duong_dan_cache_ve_may_dang_chay(monkeypatch):
    """Draft mẫu giữ đường dẫn cache của máy làm ra nó -> máy khác mở là CapCut
    đòi chọn lại file."""
    import json as _j
    import capcut_build as cb
    monkeypatch.setattr(assetlib, "cache_root",
                        lambda: Path(r"C:/May/Khac/CapCut/User Data/Cache"))
    s = _j.dumps(cb.load_draft("282new"), ensure_ascii=False)
    assert "May/Khac" in s, "không đổi đường dẫn cache sang máy đang chạy"
    assert "Users/Acer" not in s.replace("\\", "/"), "còn sót đường dẫn máy dev"


def test_bao_ngay_khi_thieu_draft_mau():
    import capcut_build as cb
    with pytest.raises(FileNotFoundError):
        cb.kiem_tra_draft_mau("khong-co-draft-mau-nay")


def test_chuoi_structured_output_co_model_han_ngach_cao():
    """Bug đã gặp: chuỗi structured output toàn model RPD 20 -> cạn giữa chừng,
    build chết ở phút thứ mười."""
    import gemini_util
    assert any(m.endswith("-lite") for m in gemini_util.FALLBACKS), \
        "phải có model RPD cao ở cuối chuỗi để hạ cánh mềm khi cạn hạn ngạch"


# ─────────────── lỗi bắt được trên máy trạm 27/07 ───────────────

def test_luong_cpu_khong_vuot_tran(monkeypatch):
    """Bug đã gặp: máy 12 nhân/20 luồng ra 9 luồng -> ctranslate2.dll SẬP CỨNG
    (0xC00000FD stack overflow) trên file dài, kéo theo cả web server. Đo được:
    4 luồng chạy trọn 58 phút và còn NHANH HƠN 9 luồng."""
    import multiprocessing as mp
    import transcribe
    monkeypatch.delenv("CT2_THREADS", raising=False)
    for so_luong in (4, 8, 12, 20, 32, 128):
        monkeypatch.setattr(mp, "cpu_count", lambda n=so_luong: n)
        v = transcribe._luong_cpu()
        assert 1 <= v <= transcribe.TRAN_LUONG, \
            f"cpu_count={so_luong} -> {v} luồng, vượt trần {transcribe.TRAN_LUONG} là sập cứng"


def test_work_dir_bat_duoc_record_khac_trung_ten(tmp_path, monkeypatch):
    """Bug đã gặp: slug() chỉ lấy TÊN file nên hai record khác nhau cùng tên
    'test.mp4' dùng chung thư mục làm việc; cache tái dùng lẫn nhau -> draft TRỘN
    nội dung hai record, không lỗi, không cảnh báo."""
    import transcribe
    monkeypatch.setattr(transcribe, "WORK_ROOT", tmp_path / "work")

    a = tmp_path / "mayA"; a.mkdir()
    (a / "test.mp4").write_bytes(b"x" * 1000)
    b = tmp_path / "mayB"; b.mkdir()
    (b / "test.mp4").write_bytes(b"y" * 2000)          # record KHÁC, cùng tên

    d1 = transcribe.work_dir(str(a / "test.mp4"))
    d2_se_trung = transcribe.WORK_ROOT / transcribe.slug(str(b / "test.mp4"))
    assert d1 == d2_se_trung, "tiền đề của bug: hai record cùng tên trỏ cùng thư mục"

    with pytest.raises(transcribe.NguonKhongKhop):
        transcribe.work_dir(str(b / "test.mp4"))


def test_work_dir_cho_phep_doi_record_di_cho(tmp_path, monkeypatch):
    """Cùng một file dời sang thư mục khác thì KHÔNG được chặn — người dùng dời
    record là chuyện thường, chặn nhầm còn khó chịu hơn."""
    import transcribe
    monkeypatch.setattr(transcribe, "WORK_ROOT", tmp_path / "work")
    a = tmp_path / "cho_cu"; a.mkdir()
    (a / "rec.mp4").write_bytes(b"z" * 4096)
    transcribe.work_dir(str(a / "rec.mp4"))

    b = tmp_path / "cho_moi"; b.mkdir()
    (b / "rec.mp4").write_bytes(b"z" * 4096)           # cùng kích thước = cùng file
    transcribe.work_dir(str(b / "rec.mp4"))            # không được ném


def test_nghi_theo_tung_model_khong_theo_ca_key(monkeypatch):
    """Bug đã gặp 27/07: _NGHI khoá theo KEY. Gặp 429 ở model đầu chuỗi là cả key bị
    đánh dấu nghỉ -> 5 model dự phòng còn lại đều bị bỏ qua. Chuỗi dự phòng sinh ra để
    đổi model khi một model cạn, lại tự sập ngay ở lỗi cạn ĐẦU TIÊN. Hạn ngạch Google
    tính theo TỪNG MODEL: 2.5-flash cạn (RPD 20) không có nghĩa lite cạn (RPD 500)."""
    import gemini_util as g
    g._NGHI.clear()
    g._cho_nghi("key1", "gemini-2.5-flash", "429 RESOURCE_EXHAUSTED PerDay")
    assert g._dang_nghi("key1", "gemini-2.5-flash"), "model vừa 429 phải được cho nghỉ"
    assert not g._dang_nghi("key1", "gemini-3.5-flash-lite"), \
        "model KHÁC trên cùng key vẫn phải gọi được — nếu không chuỗi dự phòng vô dụng"
    g._NGHI.clear()


def test_cam_ai_doi_ten_rieng_khi_lam_sach():
    """Bug đã gặp 27/07: Whisper nghe 'nano bar na 2' (Nano Banana 2 — model ảnh của
    Google), AI 'sửa' thành 'Runway Gen-2' — đổi hẳn sang sản phẩm KHÁC. Gán cho diễn
    giả câu họ chưa từng nói là hỏng nặng hơn nhiều so với sai chính tả."""
    import caption_fix
    s = caption_fix.SYS
    assert "TÊN RIÊNG" in s.upper(), "prompt phải cấm đổi tên riêng"
    assert "GIỮ NGUYÊN" in s, "không nhận ra tên thì phải giữ nguyên chữ ASR nghe được"


def test_lam_sach_chia_lo_theo_ky_tu(monkeypatch):
    """Bug đã gặp: chia lô theo SỐ DÒNG (120) vốn chỉnh cho câu ngắn của bản bóc kỹ.
    Bản khảo sát mỗi dòng ~34 giây tiếng nói -> 100 dòng thành khối ~35k ký tự, output
    vượt giới hạn, resp.parsed về None, vòng dự phòng xoay hết model mà lần nào cũng
    cụt -> treo cứng."""
    import inspect
    import caption_fix
    src = inspect.getsource(caption_fix.lam_sach_toan_bo)
    assert "MAX_KY_TU" in src, "phải chia lô theo số ký tự, không theo số dòng"
    assert "text_goc" in src, "phải giữ bản thô để người dùng đối chiếu AI sửa gì"


def test_bo_dong_dem_khoi_prompt_nhung_giu_moc_thoi_gian():
    """Câu đệm ('ba ơi ba ơi ba ơi', 'alo alo') làm loãng nội dung khi tìm chủ đề.
    Bỏ khỏi PROMPT thì được, nhưng KHÔNG được xoá segment: mốc thời gian là thứ dùng
    để cắt video, mất là hỏng cả bản dựng."""
    import topics as tp
    tr = {"segments": [
        {"start": 0, "end": 5, "text": "Nội dung thật sự đáng làm short"},
        {"start": 5, "end": 8, "text": "Alo alo mọi người nghe rõ không", "bo": True},
        {"start": 8, "end": 12, "text": "Nội dung thứ hai"},
    ]}
    body = tp.format_transcript(tr)
    assert "Nội dung thật sự" in body and "Nội dung thứ hai" in body
    assert "Alo alo" not in body, "dòng đánh dấu bỏ vẫn lọt vào prompt"
    assert len(tr["segments"]) == 3, "KHÔNG được xoá segment — mất mốc là hỏng cắt video"


def test_chia_cua_so_phu_het_record():
    """Bug đã gặp: nhồi cả transcript 58 phút vào MỘT lượt gọi -> 20 phút CUỐI không
    sinh chủ đề nào, độ phủ 9,5%. Cửa sổ phải phủ kín [0, dài] và có chồng lấn để
    chủ đề vắt qua ranh giới không bị cắt đôi."""
    import topics as tp
    for dai in (300, 900, 3462, 4 * 3600):
        cs = tp.chia_cua_so(dai)
        assert cs[0][0] == 0, f"dài {dai}: không bắt đầu từ 0"
        assert abs(cs[-1][1] - dai) < 1, f"dài {dai}: bỏ sót phần cuối ({cs[-1][1]} != {dai})"
        for (a1, b1), (a2, b2) in zip(cs, cs[1:]):
            assert a2 < b1, f"dài {dai}: hai cửa sổ không chồng lấn -> mất chủ đề ở ranh giới"
    assert len(tp.chia_cua_so(3462)) >= 3, "record 58 phút phải chia nhiều hơn 1 cửa sổ"


def test_gop_chu_de_khu_trung_o_vung_chong_lan():
    """Vùng chồng lấn sinh ra cùng một chủ đề hai lần — phải khử, và giữ bản ĐIỂM CAO."""
    import topics as tp
    a = {"title": "A", "total_score": 8.0, "segments": [{"start_sec": 100, "end_sec": 200}]}
    b = {"title": "A lần 2", "total_score": 5.0, "segments": [{"start_sec": 110, "end_sec": 205}]}
    c = {"title": "Khác hẳn", "total_score": 7.0, "segments": [{"start_sec": 900, "end_sec": 1000}]}
    ra = tp.gop_chu_de([b, a, c])
    assert len(ra) == 2, "không khử được bản trùng"
    assert any(t["title"] == "A" for t in ra), "phải giữ bản điểm cao hơn"
    assert not any(t["title"] == "A lần 2" for t in ra)


def test_prompt_co_rang_buoc_so_luong_chu_de():
    """Bug đã gặp: prompt chỉ quy định ĐỘ DÀI mỗi chủ đề, không nói cần BAO NHIÊU cái
    -> model tự chọn ít cho chắc, record 1 tiếng ra đúng 3 chủ đề."""
    import topics as tp
    p = tp.load_profile(str(ROOT / "shorts" / "profiles" / "meeting.yaml"))
    pr = tp.build_system_prompt(p, 0, 900, 4)
    assert "ÍT NHẤT 4" in pr, "phải nêu số chủ đề tối thiểu cho cửa sổ"
    assert "900" in pr or "15 phút" in pr, "phải nêu rõ cửa sổ đang xét"


def test_moi_du_an_co_thu_muc_lam_viec_rieng(tmp_path, monkeypatch):
    """Hai dự án dùng chung MỘT record phải phân tích RIÊNG. Dùng chung thư mục thì
    dự án thứ hai thừa hưởng transcript + chủ đề + video nền của dự án thứ nhất —
    tức là 'làm lại' mà chẳng làm lại gì."""
    import transcribe
    monkeypatch.setattr(transcribe, "WORK_ROOT", tmp_path / "work")
    rec = tmp_path / "test.mp4"
    rec.write_bytes(b"a" * 512)

    mac_dinh = transcribe.work_dir(str(rec))
    rieng = transcribe.work_dir(str(rec), ten="test_2")
    assert mac_dinh.name == "test"
    assert rieng.name == "test_2", "phải theo tên caller đưa, không suy từ tên file"
    assert mac_dinh != rieng


def test_khoa_video_nen_theo_khoang_cat_khong_theo_chi_so():
    """Bug đã gặp: reframe_t{N}.mp4 khoá theo CHỈ SỐ chủ đề. Phân tích lại ra danh
    sách chủ đề khác -> 'chủ đề 1' là đoạn khác, nhưng file cũ vẫn được tái dùng:
    caption/SFX của chủ đề MỚI phủ lên hình+tiếng của chủ đề CŨ."""
    import build_short_draft as bsd
    nguon = "C:/rec/test.mp4"
    cu = [(816.0, 972.0)]
    moi = [(890.0, 984.0)]
    assert bsd.khoa_khoang_cat(nguon, cu) != bsd.khoa_khoang_cat(nguon, moi), \
        "khoảng cắt đổi mà khoá không đổi -> tái dùng nhầm video nền"
    assert bsd.khoa_khoang_cat(nguon, cu) == bsd.khoa_khoang_cat(nguon, list(cu)), \
        "cùng khoảng cắt phải cùng khoá (2 editor cùng chủ đề vẫn dùng chung file)"
    assert bsd.khoa_khoang_cat("D:/khac/test.mp4", cu) != bsd.khoa_khoang_cat(nguon, cu), \
        "khác record mà cùng khoá -> lại trộn nội dung"


def test_khoa_enrich_theo_noi_dung_chu_de():
    """Cùng lỗi lớp trên, ở cache enrich: hook/emoji/SFX của chủ đề cũ dán vào mới."""
    import enrich
    a = {"title": "Chủ đề A", "segments": [{"start_sec": 10, "end_sec": 20}]}
    b = {"title": "Chủ đề B", "segments": [{"start_sec": 90, "end_sec": 99}]}
    assert enrich.khoa_chu_de(a) != enrich.khoa_chu_de(b)
    assert enrich.khoa_chu_de(a) == enrich.khoa_chu_de(dict(a))


def test_build_ha_canh_mem_khi_can_han_ngach(monkeypatch):
    """Bug đã gặp: HetHanNgach từ enrich ném xuyên qua build -> mất trắng cả lượt
    sau khi đã bóc lời và render. Enrich là đồ tô điểm, không phải xương sống."""
    import build_short_draft as bsd, gemini_util, inspect
    src = inspect.getsource(bsd.build)
    assert "HetHanNgach" in src, "build phải bắt HetHanNgach quanh enrich_topic"
    assert hasattr(gemini_util, "HetHanNgach")


def test_uoc_luong_thoi_gian_khong_hardcode_toc_do_may_dev():
    """Bug đã gặp: eta = dur/30/60 — hệ số 30x đo trên GPU máy dev, đóng cứng cho
    mọi máy. Máy chạy CPU đo được 14,5x -> hứa 2 phút, bắt ngồi 4 phút."""
    import inspect
    import app
    src = inspect.getsource(app.api_browse)
    assert "toc_do_asr" in src, "phải ước lượng theo tốc độ đo được trên máy đang chạy"
    assert "/ 30 / 60" not in src, "còn hardcode hệ số của máy dev"
