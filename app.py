# -*- coding: utf-8 -*-
"""app.py — App web cho team: record -> chủ đề -> chọn -> tạo draft cho editor,
kho tài nguyên tiến hoá theo gu, cân bằng âm thanh.

  set GEMINI_API_KEY=... & set PEXELS_API_KEY=... & python app.py
  -> http://127.0.0.1:8765
"""
import contextlib, io, json, os, subprocess, sys, threading, time
from pathlib import Path

# Console Windows mặc định hay là cp1252: chỉ một dòng log tiếng Việt lọt ra stdout
# là app chết giữa chừng vì UnicodeEncodeError. Ép UTF-8 ngay từ đầu.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

import assetlib, asset_restore, audio_balance, capcut_inventory, draft_diff, draft_scan
import projects

sys.path.insert(0, str(assetlib.ROOT / "shorts"))
import build_short_draft as bsd

ROOT = assetlib.ROOT
DRAFT_ROOT = draft_scan.DRAFT_ROOT
WORK = ROOT / "shorts" / "work"

assetlib.khoi_tao(im_lang=False)      # máy mới cài: tạo sẵn thư mục dữ liệu

# Model mặc định TÁCH THEO VIỆC. Trích chủ đề cần PHÁN ĐOÁN -> model mạnh; sửa chính
# tả là việc CƠ HỌC chạy nhiều lô liên tiếp -> model nhanh. Cả hai đều có chuỗi lùi
# (gemini_util.CHUOI_*) nên máy dùng bậc Free vẫn chạy, chỉ là lùi xuống flash/lite.
# Phải khai ở ĐẦU FILE: tham số mặc định của hàm được tính lúc `def` chạy, khai ở giữa
# file thì mọi endpoint phía trên ném NameError ngay khi import.
MODEL_CHAT_LUONG = "gemini-3.1-pro-preview"
MODEL_CO_HOC = "gemini-3.6-flash"

app = FastAPI(title="CapCut Auto Editor")

# Font đóng gói kèm app. KHÔNG dùng Google Fonts: CSS của nó chặn render, máy cài
# xong mà không có mạng sẽ trắng trang tới lúc DNS timeout. Chỉ mở thư mục fonts,
# không mở cả assets/ (trong đó là kho tài nguyên của editor).
_FONTS = ROOT / "assets" / "fonts"
if _FONTS.exists():
    app.mount("/static/fonts", StaticFiles(directory=_FONTS), name="fonts")

# ---- nhật ký việc chạy nền (để UI hiện tiến trình) ----
JOBS: dict[str, dict] = {}
_jid = [0]


class LogWriter(io.TextIOBase):
    """Hứng stdout của pipeline và đẩy vào log job NGAY THEO TỪNG DÒNG.
    (Việc dài như transcribe 2 tiếng phải thấy tiến trình chạy, không đợi tới cuối.)"""

    def __init__(self, log):
        self.log, self.buf = log, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                self.log(line.rstrip())
        return len(s)

    def flush(self):
        if self.buf.strip():
            self.log(self.buf.rstrip()); self.buf = ""


def run_job(title: str, fn):
    _jid[0] += 1
    jid = f"j{_jid[0]}"
    JOBS[jid] = {"id": jid, "title": title, "state": "running", "log": [], "ts": time.time()}

    def work():
        try:
            out = fn(lambda m: JOBS[jid]["log"].append(str(m)))
            JOBS[jid]["state"] = "done"
            JOBS[jid]["result"] = out
        except Exception as e:
            JOBS[jid]["state"] = "error"
            JOBS[jid]["log"].append(f"LỖI: {type(e).__name__}: {e}")
    threading.Thread(target=work, daemon=True).start()
    return jid


# ---------------- API ----------------

@app.get("/api/library")
def api_library():
    c = assetlib.conn()
    rows = [dict(r) for r in c.execute(
        "SELECT id,kind,name,category,owner,origin,use_count,drop_count,path_in_lib,size,resource_id "
        "FROM assets ORDER BY use_count DESC, kind").fetchall()]
    tot = dict(c.execute("SELECT COUNT(*) n, COALESCE(SUM(size),0) sz FROM assets").fetchone())
    by_owner = [dict(r) for r in c.execute(
        "SELECT owner, COUNT(*) n, SUM(use_count) uses FROM assets GROUP BY owner").fetchall()]
    by_kind = [dict(r) for r in c.execute(
        "SELECT kind, COUNT(*) n FROM assets GROUP BY kind ORDER BY n DESC").fetchall()]
    c.close()
    return {"assets": rows, "total": tot, "by_owner": by_owner, "by_kind": by_kind}


@app.get("/api/drafts")
def api_drafts():
    out = []
    if DRAFT_ROOT.exists():
        for p in sorted(DRAFT_ROOT.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            f = p / "draft_content.json"
            if not p.is_dir() or not f.exists():
                continue
            out.append({
                "name": p.name,
                "locked": (p / ".locked").exists(),
                "mtime": f.stat().st_mtime,
                "snapshot": (draft_diff.SNAP_DIR / f"{p.name}.json").exists(),
                "size_kb": round(f.stat().st_size / 1024),
            })
    cc = assetlib.find_capcut()
    return {"drafts": out, "root": str(DRAFT_ROOT),
            "capcut_found": cc["found"], "capcut_source": cc["source"]}


@app.post("/api/draft/{name}/open")
def api_draft_open(name: str, trong_capcut: bool = False):
    """Mở thư mục draft, hoặc BẬT CapCut lên (không nhảy được tới đúng draft).

    ĐO NGÀY 27/07/2026 — CapCut KHÔNG có cách nào để bên ngoài mở thẳng một draft:

      1. Quét 4 dll lớn nhất của CapCut 9.1.0: **32 route deep-link**, toàn tính năng
         AI / trang thương mại / anchor point. KHÔNG route nào nhận draft. Các chuỗi
         `draft_id`, `draft_path`… chỉ là tên trường dữ liệu nội bộ, không phải route.
      2. Không có tham số dòng lệnh nào liên quan (chỉ `--outfile`, dùng việc khác).
      3. CapCut chạy MỘT THỂ HIỆN: đã mở sẵn rồi thì gọi `CapCut.exe <đường dẫn>`
         lần nữa chẳng làm gì cả — đây đúng là thứ người dùng gặp.

    Nên không hứa thứ làm không được. `trong_capcut=true` chỉ đưa CapCut ra trước
    (bật lên nếu chưa chạy) để người dùng bấm tiếp một nhịp; mặc định mở thư mục."""
    d = (DRAFT_ROOT / name).resolve()
    if d.parent != DRAFT_ROOT.resolve() or not d.is_dir():   # chặn ../ đi ra ngoài
        raise HTTPException(404, "không thấy draft")
    if trong_capcut:
        home = assetlib.find_capcut().get("home")
        exe = Path(home) / "Apps" / "CapCut.exe" if home else None
        if exe and exe.is_file():
            try:
                subprocess.Popen([str(exe)])                 # noqa: S603 (app chạy local)
                return {"ok": True, "cach": "capcut_front", "path": str(d)}
            except OSError as e:
                print(f"[open] bật CapCut hỏng ({e}) -> lùi về mở thư mục")
        else:
            print("[open] không thấy CapCut.exe -> lùi về mở thư mục")
    os.startfile(str(d))                                     # noqa: S606 (app chạy local)
    return {"ok": True, "cach": "thu_muc", "path": str(d)}


@app.get("/api/draft/{name}/scan")
def api_scan(name: str):
    try:
        return {"items": draft_scan.scan(name)}
    except SystemExit as e:
        raise HTTPException(404, str(e))


@app.post("/api/draft/{name}/snapshot")
def api_snapshot(name: str):
    draft_diff.snapshot(name)
    return {"ok": True}


@app.get("/api/draft/{name}/diff")
def api_diff(name: str):
    try:
        return draft_diff.diff(name)
    except SystemExit as e:
        raise HTTPException(400, str(e))


@app.post("/api/draft/{name}/sync")
def api_sync(name: str, owner: str = "shared"):
    try:
        return draft_diff.sync(name, owner)
    except SystemExit as e:
        raise HTTPException(400, str(e))


@app.post("/api/draft/{name}/balance")
def api_balance(name: str, dry: bool = True):
    jid = run_job(f"Cân bằng âm thanh — {name}",
                  lambda log: audio_balance.balance(name, dry=dry, verbose=False))
    return {"job": jid}


@app.get("/api/draft/{name}/audio")
def api_audio_report(name: str):
    """Bảng đo LUFS từng nguồn tiếng (không ghi gì vào draft)."""
    d = DRAFT_ROOT / name
    f = d / "draft_content.json"
    if not f.exists():
        raise HTTPException(404, "không thấy draft")
    data = json.loads(f.read_text(encoding="utf-8"))
    mats = {m["id"]: m for b in ("videos", "audios")
            for m in (data.get("materials") or {}).get(b, []) or []}
    vid_dur = {}
    for t in data.get("tracks", []):
        if t.get("type") == "video":
            for s in t.get("segments", []):
                mid = s.get("material_id")
                if mid in mats:
                    vid_dur[mid] = vid_dur.get(mid, 0) + (s.get("target_timerange") or {}).get("duration", 0)
    main_vid = max(vid_dur, key=vid_dur.get) if vid_dur else None
    seen, rows = set(), []
    for t in data.get("tracks", []):
        if t.get("type") not in ("video", "audio"):
            continue
        for s in t.get("segments", []):
            mat = mats.get(s.get("material_id"))
            if not mat or not mat.get("path"):
                continue
            nm = Path(mat["path"]).name
            if nm in seen:
                continue
            seen.add(nm)
            role = audio_balance.classify(t["type"], mat, mat.get("id") == main_vid)
            meas = audio_balance.measure(Path(mat["path"]))
            if not meas:
                continue
            gain = audio_balance.plan_gain(meas, role)
            vol = round(audio_balance.db_to_vol(gain), 2)
            cur = round(s.get("volume", 1.0), 2)
            rows.append({"role": role, "file": nm, "lufs": round(meas["i"], 1),
                         "gain": round(gain, 1), "volume": vol, "cur": cur,
                         "done": abs(vol - cur) < 0.02})
    return {"rows": rows, "target": audio_balance.TARGET}


@app.get("/api/assets/check")
def api_assets_check():
    rows = asset_restore.cacheable()
    have = [r["name"] for r, rel in rows if (asset_restore.CACHE_ROOT / rel).exists()]
    miss = [{"name": r["name"], "kind": r["kind"], "rid": r["resource_id"],
             "in_lib": bool(r["path_in_lib"])}
            for r, rel in rows if not (asset_restore.CACHE_ROOT / rel).exists()]
    return {"have": len(have), "missing": miss, "cache": str(asset_restore.CACHE_ROOT)}


@app.post("/api/assets/restore")
def api_assets_restore():
    jid = run_job("Cài tài nguyên vào CapCut", lambda log: {"installed": asset_restore.restore()})
    return {"job": jid}


@app.post("/api/harvest")
def api_harvest(draft: str, owner: str = "shared"):
    return draft_scan.harvest(draft, owner)


@app.get("/api/projects")
def api_projects():
    # Draft ĐÃ dựng của từng chủ đề: build ghi ĐÈ tại chỗ, nên UI phải biết cái nào
    # đã có để hỏi lại trước khi xoá mất phần editor sửa tay.
    built: dict[str, list] = {}
    if DRAFT_ROOT.exists():
        for d in DRAFT_ROOT.iterdir():
            if d.is_dir() and (d / "draft_content.json").exists():
                built.setdefault(d.name, []).append(d)

    def drafts_of(proj: str, i: int):
        pre = f"{proj}_t{i}_"
        return [{"name": n, "editor": n[len(pre):],
                 "mtime": (DRAFT_ROOT / n / "draft_content.json").stat().st_mtime,
                 "locked": (DRAFT_ROOT / n / ".locked").exists()}
                for n in sorted(built) if n.startswith(pre)]

    out = []
    if WORK.exists():
        for p in sorted(WORK.iterdir()):
            if not p.is_dir():
                continue
            tj = p / "topics.json"
            topics = []
            if tj.exists():
                try:
                    t = json.loads(tj.read_text(encoding="utf-8"))
                    topics = [{"i": i + 1, "title": x.get("title", ""),
                               "score": x.get("total_score"),
                               "dur": round(sum(s["end_sec"] - s["start_sec"] for s in x["segments"])),
                               "drafts": drafts_of(p.name, i + 1)}
                              for i, x in enumerate(t.get("topics", []))]
                except (ValueError, KeyError):
                    pass
            if not tj.exists():                  # chỉ hiện record ĐÃ phân tích (kể cả 0 chủ đề)
                continue
            out.append({"name": p.name, "topics": topics,
                        "has_transcript": any(p.glob("transcript.*.json"))})
    return {"projects": out}


# ───────────────── DỰ ÁN cấp app (CRUD) + quy trình ─────────────────

@app.get("/api/workflows")
def api_workflows():
    return {"workflows": projects.QUY_TRINH}


@app.get("/api/sfx")
def api_sfx():
    """Danh sách SFX trong kho — để người dùng giới hạn đúng những file được dùng."""
    import build_short_draft as _b
    return {"files": sorted(assetlib.sfx_kho(_b.SFX_DEFAULT).keys())}


@app.get("/api/app-projects")
def api_app_projects(nhan_cu: bool = True):
    """Danh sách dự án cho màn hình chính, kèm số CapCut project đã dựng."""
    if nhan_cu:
        projects.nhan_du_an_cu(WORK)          # thư mục có sẵn không được bỏ rơi
    ds = projects.liet_ke()
    for p in ds:
        w = p.get("work_dir") or ""
        p["so_draft"] = len(_drafts_cua_work(w)) if w else 0
        p["so_chu_de"] = _so_chu_de(w)
        p["da_phan_tich"] = bool(w) and (WORK / w / "topics.json").exists()
    return {"projects": ds}


def _drafts_cua_work(work: str) -> list:
    """CapCut project sinh ra từ một dự án — nhận theo tiền tố '<work>_t<n>_'."""
    if not work or not DRAFT_ROOT.exists():
        return []
    ra = []
    for d in sorted(DRAFT_ROOT.iterdir()):
        if not (d.is_dir() and d.name.startswith(f"{work}_t")
                and (d / "draft_content.json").exists()):
            continue
        try:
            phan = d.name[len(work) + 2:].split("_", 1)
            topic = int(phan[0]); editor = phan[1] if len(phan) > 1 else "shared"
        except (ValueError, IndexError):
            continue
        ra.append({"name": d.name, "topic": topic, "editor": editor,
                   "mtime": (d / "draft_content.json").stat().st_mtime,
                   "locked": (d / ".locked").exists(),
                   "co_moc": (draft_diff.SNAP_DIR / f"{d.name}.json").exists()})
    return ra


def _so_chu_de(work: str) -> int:
    tj = WORK / work / "topics.json" if work else None
    if not tj or not tj.exists():
        return 0
    try:
        return len(json.loads(tj.read_text(encoding="utf-8")).get("topics", []))
    except (OSError, ValueError):
        return 0


@app.post("/api/app-projects")
def api_app_project_tao(ten: str, quy_trinh: str, record_path: str = "",
                        editor: str = "shared"):
    """Tạo dự án. work_dir suy từ file record (nếu đã chọn) để cache/draft bám đúng chỗ."""
    work = ""
    if record_path:
        import transcribe as trm
        work = trm.slug(record_path)      # trùng với dự án khác vẫn cho — xem api_..._gan_record
    try:
        return projects.tao(ten, quy_trinh, record_path, work, editor)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/app-projects/{pid}")
def api_app_project_sua(pid: int, body: dict):
    try:
        p = projects.sua(pid, **body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not p:
        raise HTTPException(404, "không thấy dự án")
    return p


@app.delete("/api/app-projects/{pid}")
def api_app_project_xoa(pid: int):
    try:
        return projects.xoa(pid)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/app-projects/{pid}/transcript")
def api_transcript(pid: int):
    """Toàn bộ lời thoại kèm mốc thời gian, cả bản THÔ lẫn bản ĐÃ SẠCH.

    Trả cả hai để người dùng đối chiếu được AI đã sửa gì — sửa im lặng thì không ai
    biết nó có sửa bậy không, mà ASR tiếng Việt sai đủ nhiều để chuyện đó đáng lo."""
    p = projects.lay(pid)
    if not p:
        raise HTTPException(404, "không thấy dự án")
    if not p.get("work_dir"):
        raise HTTPException(400, "dự án chưa gắn record")
    wd = WORK / p["work_dir"]
    import transcribe as trm
    try:
        t = trm.load_transcript(wd)
    except FileNotFoundError:
        raise HTTPException(404, "chưa có transcript — chạy Phân tích trước")
    dong = [{"i": i, "start": s["start"], "end": s["end"],
             "text": s.get("text", ""), "goc": s.get("text_goc"),
             "bo": bool(s.get("bo"))}
            for i, s in enumerate(t.get("segments", []))]
    n_sach = sum(1 for d in dong if d["goc"] is not None)
    n_doi = sum(1 for d in dong if d["goc"] is not None and d["goc"].strip() != d["text"].strip())
    n_bo = sum(1 for d in dong if d["bo"])
    return {"dong": dong, "n": len(dong), "n_sach": n_sach, "n_doi": n_doi, "n_bo": n_bo,
            "dai": t.get("duration_sec", 0), "model": t.get("model"),
            "record": p.get("record_path", "")}


@app.post("/api/app-projects/{pid}/transcript/lam-sach")
def api_transcript_lam_sach(pid: int, model: str = MODEL_CO_HOC):
    """Làm sạch nốt những dòng còn chữ thô của transcript ĐANG DÙNG.

    Cần vì bản bóc kỹ (transcript.fine.json) sinh ra ở bước dựng draft, sau lượt làm
    sạch lúc phân tích — nên đoạn vừa bóc kỹ luôn là chữ thô cho tới khi có ai đó
    làm sạch lại."""
    p = projects.lay(pid)
    if not p or not p.get("work_dir"):
        raise HTTPException(404, "không thấy dự án hoặc chưa gắn record")
    wd = WORK / p["work_dir"]
    import transcribe as trm
    import caption_fix as cf
    try:
        t = trm.load_transcript(wd)
    except FileNotFoundError:
        raise HTTPException(404, "chưa có transcript")
    ten = t.get("_file") or ("transcript.fine.json" if (wd / "transcript.fine.json").exists()
                             else "transcript.survey.json")

    def run(log):
        with contextlib.redirect_stdout(LogWriter(log)):
            # Đếm TRƯỚC để phân biệt "không có gì phải làm" với "làm không được".
            # Trước đây cả hai đều in "không có dòng nào cần làm sạch" — cạn hạn ngạch
            # mà báo như thể đã sạch hết là nói dối người dùng.
            can = sum(1 for s in t.get("segments", []) if "text_goc" not in s)
            n = cf.lam_sach_toan_bo(t, model)
            if n:
                (wd / ten).write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
                print(f"đã ghi {ten} — {n}/{can} dòng")
            elif can:
                raise RuntimeError(
                    f"Không làm sạch được dòng nào trong {can} dòng còn chữ thô — "
                    f"xem dòng lỗi ngay trên. Thường là cạn hạn ngạch Gemini; "
                    f"chờ reset (nửa đêm giờ Thái Bình Dương) rồi bấm lại.")
            else:
                print("Toàn bộ transcript đã sạch từ trước, không có gì phải làm.")
        return {"n": n, "can": can}

    return {"job": run_job(f"Làm sạch lời thoại · {p['ten']}", run)}


@app.post("/api/app-projects/{pid}/record")
def api_app_project_gan_record(pid: int, path: str):
    """Gắn file record vào dự án. CHỈ LÀM ĐƯỢC MỘT LẦN.

    `work_dir` suy ra từ đây, mà draft CapCut lẫn cache đều bám theo nó — cho đổi
    giữa chừng là dự án đang có draft bỗng trỏ sang thư mục khác."""
    p = projects.lay(pid)
    if not p:
        raise HTTPException(404, "không thấy dự án")
    if p.get("work_dir"):
        raise HTTPException(409, f"Dự án này đã gắn record rồi ({p['work_dir']}). "
                                 f"Muốn dùng record khác thì tạo dự án mới.")
    src = Path(path)
    if not src.is_file():
        raise HTTPException(404, f"Không thấy file: {path}")
    import transcribe as trm
    # Record đã dùng ở dự án khác thì VẪN CHO chọn lại, nhưng phải có THƯ MỤC LÀM
    # VIỆC RIÊNG. Dùng chung thư mục thì dự án mới thừa hưởng luôn transcript, chủ đề
    # và video nền của dự án cũ — tức là "làm lại" mà chẳng làm lại gì, đúng thứ vô
    # nghĩa. Mỗi dự án phân tích từ đầu thì mới ra bộ chủ đề của riêng nó.
    goc = trm.slug(path)
    work, cu = goc, projects.lay_theo_work(goc)
    if cu:
        i = 2
        while projects.lay_theo_work(f"{goc}_{i}"):
            i += 1
        work = f"{goc}_{i}"
    c = assetlib.conn()
    c.execute("UPDATE projects SET work_dir=?, record_path=?, sua_luc=? WHERE id=?",
              (work, str(src), time.time(), pid))
    c.commit(); c.close()
    ra = projects.lay(pid)
    if cu and cu["id"] != pid:
        ra["dung_chung"] = (f"Record này cũng đang dùng ở dự án '{cu['ten']}'. Dự án mới "
                            f"phân tích LẠI TỪ ĐẦU trong thư mục riêng '{work}' — bóc lời "
                            f"lại từ đầu (mất vài phút) và có bộ chủ đề của riêng nó, "
                            f"không dính gì tới dự án kia.")
    return ra


@app.get("/api/app-projects/{pid}")
def api_app_project_mot(pid: int):
    """Toàn bộ dữ liệu cho MÀN HÌNH LÀM VIỆC của một dự án."""
    p = projects.lay(pid)
    if not p:
        raise HTTPException(404, "không thấy dự án")
    w = p.get("work_dir") or ""
    p["drafts"] = _drafts_cua_work(w)
    p["topics"] = []
    tj = WORK / w / "topics.json" if w else None
    if tj and tj.exists():
        try:
            t = json.loads(tj.read_text(encoding="utf-8"))
            dtheo: dict = {}
            for d in p["drafts"]:
                dtheo.setdefault(d["topic"], []).append(d)
            p["topics"] = [{"i": i + 1, "title": x.get("title", ""),
                            "score": x.get("total_score"),
                            "dur": round(sum(s["end_sec"] - s["start_sec"]
                                             for s in x.get("segments", []))),
                            # n_doan: chủ đề ghép nhiều đoạn rời thường ra short hay
                            # hơn -> phải thấy được trên thẻ để người dùng ưu tiên.
                            "n_doan": len(x.get("segments", [])),
                            "tu": min([s["start_sec"] for s in x.get("segments", [])] or [0]),
                            "drafts": dtheo.get(i + 1, [])}
                           for i, x in enumerate(t.get("topics", []))]
        except (OSError, ValueError, KeyError):
            pass
    p["da_phan_tich"] = bool(tj and tj.exists())
    return p


VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mp3", ".wav", ".m4a"}


def default_record_dir() -> Path:
    """Thư mục record mặc định. Máy mới cài KHÔNG có 'E:/E Download/Recap' —
    hardcode một đường dẫn của máy dev là màn hình đầu tiên đã báo lỗi đỏ."""
    home = Path.home()
    for c in (Path(r"E:/E Download/Recap"), home / "Videos", home / "Downloads", home):
        if c.is_dir():
            return c
    return home


MAX_SAU = 4          # tầng thư mục con tối đa
MAX_FILE = 300       # trần số file — quét cả cây rồi ffprobe từng cái là rất lâu


def _duyet_record(d: Path, de_quy: bool):
    """Tìm file record. Quét CẢ THƯ MỤC CON vì người dùng hay xếp record theo
    buổi/tháng, bắt họ trỏ đúng thư mục lá là bắt bấm mò nhiều lần.

    Có trần độ sâu và trần số file: trỏ nhầm vào ổ C: mà quét không giới hạn là app
    đứng hình vài phút, không nút nào bấm được."""
    if not de_quy:
        return sorted([p for p in d.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT]), False
    ra, goc = [], len(d.parts)
    for p in sorted(d.rglob("*")):
        if len(ra) >= MAX_FILE:
            return ra, True                       # còn sót -> phải BÁO, đừng cắt im lặng
        try:
            if p.is_file() and p.suffix.lower() in VIDEO_EXT and len(p.parts) - goc <= MAX_SAU:
                ra.append(p)
        except OSError:
            continue
    return ra, False


@app.get("/api/browse")
def api_browse(dir: str = "", de_quy: bool = True):
    """Liệt kê file record trong 1 thư mục (app chạy local nên duyệt thẳng ổ đĩa,
    không upload — file 2-3 tiếng vài GB không upload qua trình duyệt được)."""
    d = Path(dir) if dir else default_record_dir()
    if not d.exists() or not d.is_dir():
        raise HTTPException(404, f"Không thấy thư mục: {d}")
    ds, cat_bot = _duyet_record(d, de_quy)
    files = []
    for p in ds:
        if True:
            try:
                info = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries",
                     "format=duration:stream=codec_type", "-of", "default=nw=1", str(p)],
                    capture_output=True, text=True, timeout=20).stdout
                dur = 0.0
                for ln in info.splitlines():
                    if ln.startswith("duration="):
                        try:
                            dur = float(ln.split("=", 1)[1])
                        except ValueError:
                            pass
                has_v = "codec_type=video" in info
                # Ước lượng theo tốc độ ĐO ĐƯỢC TRÊN MÁY NÀY. Trước đây chia cứng cho
                # 30 — hệ số đo trên GPU máy dev — nên máy chạy CPU hứa "2 phút" rồi
                # bắt ngồi 4 phút. Chưa đo lần nào thì đoán dè dặt (10x).
                import transcribe as tr_mod
                rtf, da_do = tr_mod.toc_do_asr()
                try:
                    tuong_doi = str(p.relative_to(d)).replace("\\", "/")
                except ValueError:
                    tuong_doi = p.name
                files.append({
                    "path": str(p).replace("\\", "/"),
                    "name": p.name,
                    "duong": tuong_doi,          # có thư mục con -> hiện để phân biệt trùng tên
                    "mb": round(p.stat().st_size / 1e6),
                    "dur_min": round(dur / 60),
                    "eta_min": max(1, round(dur / rtf / 60 * 1.3)),   # +30% cho tách audio
                    "eta_do_that": da_do,
                    "video": has_v,
                })
            except (OSError, subprocess.SubprocessError):
                pass
    return {"dir": str(d).replace("\\", "/"), "files": files,
            "de_quy": de_quy, "cat_bot": cat_bot, "max_file": MAX_FILE}


def _chon_bang_tkinter(kieu: str) -> str:
    """Mở hộp thoại thật của Windows, in đường dẫn ra stdout rồi thoát ngay.

    Gọi từ `_run_pick_con()` trong tiến trình con — KHÔNG gọi trực tiếp từ route:
    tkinter phải ở luồng chính, mà route chạy trong luồng của web server đa luồng."""
    import tkinter as tk
    from tkinter import filedialog
    r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
    if kieu == "thu_muc":
        p = filedialog.askdirectory(title="Chọn thư mục chứa record")
    else:
        p = filedialog.askopenfilename(
            title="Chọn file record",
            filetypes=[("Video/Audio", "*.mp4 *.mov *.mkv *.avi *.m4v *.webm *.mp3 *.wav *.m4a"),
                       ("Tất cả", "*.*")])
    print(p or "")


@app.post("/api/pick")
def api_pick(kieu: str = "thu_muc"):
    """Mở hộp thoại chọn file/thư mục CỦA WINDOWS.

    Bắt người dùng chép tay đường dẫn vào ô text là kiểu bắt làm việc không công —
    và gõ sai một ký tự thì báo 'không thấy thư mục' mà không biết sai chỗ nào.
    App chạy local nên mở được hộp thoại thật; dùng tkinter có sẵn trong Python,
    không thêm phụ thuộc.

    Chạy trong TIẾN TRÌNH RIÊNG qua cờ `--pick` (xem __main__), KHÔNG qua `python -c
    <code>`: bản .exe đóng gói thì sys.executable CHÍNH LÀ CapCutAuto.exe, không hiểu
    cờ `-c` — gọi kiểu đó vô tình mở thêm một bản app thứ hai, bản đó in dòng chào
    "App: http://127.0.0.1:8765" rồi chết vì cổng 8765 đã bị chiếm, và dòng đó bị
    nhặt nhầm làm đường dẫn vừa chọn. Bắt bởi người dùng thật, không phải đoán."""
    if kieu not in ("thu_muc", "file"):
        raise HTTPException(400, "kieu phải là 'thu_muc' hoặc 'file'")
    lenh = [sys.executable] + ([] if getattr(sys, "frozen", False) else [__file__]) + ["--pick", kieu]
    try:
        r = subprocess.run(lenh, capture_output=True, text=True, timeout=300)
    except subprocess.SubprocessError as e:
        raise HTTPException(500, f"Không mở được hộp thoại: {e}")
    duong = (r.stdout or "").strip().splitlines()
    duong = duong[-1].strip() if duong else ""
    return {"path": duong, "huy": not duong}


@app.post("/api/ingest")
def api_ingest(path: str, asr: str = "small", model: str = MODEL_CHAT_LUONG,
               device: str = "cuda", work: str = "", model_sach: str = MODEL_CO_HOC):
    """LUỒNG ĐẦU: record thô -> transcript -> trích chủ đề -> hiện ở màn hình dự án.

    `work` = thư mục làm việc của DỰ ÁN gọi tới. Không truyền thì suy từ tên file như
    cũ — nhưng dự án thứ hai dùng lại cùng record mà suy từ tên file là ghi đè lên
    phân tích của dự án thứ nhất."""
    src = Path(path)
    if not src.exists():
        raise HTTPException(404, f"Không thấy file: {path}")

    def run(log):
        import transcribe as tr
        import topics as tp
        import caption_fix as cf
        with contextlib.redirect_stdout(LogWriter(log)):
            print(f"[1/3] Khảo sát nhanh '{src.name}' (model {asr}, {device})...")
            # TẦNG 1: batched + greedy, không mốc từ -> đo được ~43x realtime
            # (cách cũ 8.5x). Mốc từng từ để tầng 2 lo, chỉ trên đoạn được chọn.
            sv = tr.transcribe_survey(str(src), asr, device, ten=work)
            wd = tr.work_dir(str(src), work)

            # LÀM SẠCH TRƯỚC KHI TRÍCH CHỦ ĐỀ. Trước đây bản sạch chỉ dùng cho caption
            # ở cuối, còn bước trích chủ đề đọc chữ thô đầy lỗi -> Gemini vừa phải
            # đoán người ta nói gì vừa tìm chủ đề. Chọn sai đoạn là hỏng từ gốc.
            print(f"[2/3] Làm sạch transcript ({model_sach})...")
            if cf.lam_sach_toan_bo(sv, model_sach):
                (wd / "transcript.survey.json").write_text(
                    json.dumps(sv, ensure_ascii=False), encoding="utf-8")

            # Quét phần HÌNH: đoạn nào đứng yên. Rẻ (38 giây cho record 58 phút) và
            # là thứ DUY NHẤT trong cả pipeline nhìn vào video — mọi bước khác chỉ đọc
            # chữ, nên không bước nào phát hiện được "short này không có gì để nhìn".
            import hinh_anh
            h = hinh_anh.quet(str(src), wd)
            nx = hinh_anh.nhan_xet_nguon(h)
            if nx:
                print(f"⚠️  {nx}")

            print(f"[3/3] Gemini trích chủ đề ({model})...")
            prof = str(assetlib.ROOT / "shorts" / "profiles" / "meeting.yaml")
            tp.extract_topics(wd, prof, model, False)
        tj = wd / "topics.json"
        n = len(json.loads(tj.read_text(encoding="utf-8")).get("topics", [])) if tj.exists() else 0
        return {"project": wd.name, "topics": n}

    jid = run_job(f"Phân tích record · {src.name}", run)
    return {"job": jid}


# ───────── XEM TRƯỚC: chọn chủ đề mà không nghe được thì là chọn mù ─────────

@app.get("/api/project/{proj}/topic/{idx}/preview")
def api_topic_preview(proj: str, idx: int):
    """Tóm tắt + góc hook + trích transcript của đúng chủ đề đó."""
    work = (WORK / proj).resolve()
    tj = work / "topics.json"
    if not tj.exists():
        raise HTTPException(404, "chưa phân tích")
    topics = json.loads(tj.read_text(encoding="utf-8")).get("topics", [])
    if not 1 <= idx <= len(topics):
        raise HTTPException(404, "không có chủ đề này")
    t = topics[idx - 1]
    sys.path.insert(0, str(assetlib.ROOT / "shorts"))
    import transcribe as trm
    lines = []
    try:
        segs = trm.load_transcript(work)["segments"]
        for s in t["segments"]:
            for g in segs:
                if g["end"] > s["start_sec"] and g["start"] < s["end_sec"]:
                    lines.append({"sec": int(g["start"]), "text": g["text"]})
    except (FileNotFoundError, KeyError):
        pass
    return {"title": t.get("title", ""), "summary": t.get("summary", ""),
            "hook": t.get("hook", ""), "reason": t.get("reason", ""),
            "scores": t.get("scores", []), "total": t.get("total_score"),
            "ranges": [[s["start_sec"], s["end_sec"]] for s in t["segments"]],
            "lines": lines[:40]}


@app.get("/api/project/{proj}/topic/{idx}/audio")
def api_topic_audio(proj: str, idx: int, sec: int = 40):
    """Cắt vài chục giây đầu của chủ đề ra mp3 để nghe thử (có cache)."""
    work = (WORK / proj).resolve()
    wav = work / "audio.wav"
    tj = work / "topics.json"
    if not (wav.exists() and tj.exists()):
        raise HTTPException(404, "chưa có audio đã tách")
    topics = json.loads(tj.read_text(encoding="utf-8")).get("topics", [])
    if not 1 <= idx <= len(topics):
        raise HTTPException(404, "không có chủ đề này")
    start = min(s["start_sec"] for s in topics[idx - 1]["segments"])
    out = work / "previews" / f"t{idx}_{sec}s.mp3"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.2f}", "-t", str(sec),
                            "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "96k", str(out)],
                           capture_output=True)
        if r.returncode != 0 or not out.exists():
            raise HTTPException(500, "không cắt được đoạn nghe thử")
    return FileResponse(out, media_type="audio/mpeg")


@app.get("/api/asset/{aid}/thumb")
def api_asset_thumb(aid: int):
    """Ảnh của sticker/hiệu ứng — gói effect có sẵn singleImage.png / final.gif bên trong."""
    c = assetlib.conn()
    row = c.execute("SELECT path_in_lib, src_path FROM assets WHERE id=?", (aid,)).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, "không có tài nguyên này")
    for base in (row["path_in_lib"] and (assetlib.ROOT / row["path_in_lib"]), row["src_path"]):
        if not base:
            continue
        p = Path(base)
        if p.is_file() and p.suffix.lower() in (".png", ".gif", ".jpg", ".webp"):
            return FileResponse(p)
        if p.is_dir():
            for pat in ("singleImage.png", "final.gif", "*.png", "*.gif", "*.webp"):
                hit = next(iter(sorted(p.glob(pat))), None)
                if hit and hit.is_file():
                    return FileResponse(hit)
    raise HTTPException(404, "tài nguyên này không có ảnh")


# ───────── TỔNG QUAN: tài nguyên có sẵn trên máy + việc đang dở ─────────

@app.get("/api/inventory")
def api_inventory(kind: str = "", used: str = "", q: str = "", limit: int = 60):
    return {"stats": capcut_inventory.stats(),
            "rows": capcut_inventory.rows(kind, used, q, limit)}


@app.get("/api/inventory/{rid}/thumb")
def api_inventory_thumb(rid: str):
    """Ảnh của gói nằm sẵn trong cache (singleImage.png / final.gif / cover_icon.png).
    Quy tắc UI: tài nguyên hình ảnh thì phải hiện hình, đừng bắt đoán qua tên."""
    p = capcut_inventory.thumb_path(rid)     # cùng hàm với lúc quét -> khớp cờ has_thumb
    if not p:
        raise HTTPException(404, "gói này không có ảnh")
    return FileResponse(p)


@app.post("/api/inventory/scan")
def api_inventory_scan():
    """Quét lại ~350 gói mất hơn chục giây -> job nền, không chẹn giao diện."""
    return {"job": run_job("Quét tài nguyên CapCut trên máy",
                           lambda log: capcut_inventory.rebuild(log))}


@app.get("/api/cleanup")
def api_cleanup(kinds: str = ""):
    """Xem trước: dọn được bao nhiêu, gồm những gì. KHÔNG đụng vào đĩa."""
    rows = capcut_inventory.cleanup_candidates(kinds)
    return {"n": len(rows), "size": sum(r["size"] for r in rows),
            "capcut_running": capcut_inventory.capcut_running(),
            "batches": capcut_inventory.batches(),
            "rows": rows[:40]}


class CleanupReq(BaseModel):
    rids: list[str] = []


@app.post("/api/cleanup/quarantine")
def api_cleanup_quarantine(kinds: str = "", req: CleanupReq | None = None):
    """Chuyển gói chưa dùng sang khu cách ly (hoàn tác được), chạy nền.

    Hai lối vào: tích chọn từng gói (`rids`) hoặc dọn cả nhóm (`kinds`). Dù đi lối
    nào, `quarantine()` vẫn kiểm tra lại từng gói trước khi đụng vào đĩa.
    """
    rids = list(req.rids) if req and req.rids else \
        [r["resource_id"] for r in capcut_inventory.cleanup_candidates(kinds)]
    if not rids:
        raise HTTPException(400, "không có gói nào để dọn")
    return {"job": run_job(f"Dọn {len(rids)} gói chưa dùng",
                           lambda log: capcut_inventory.quarantine(rids, log))}


@app.post("/api/cleanup/undo")
def api_cleanup_undo(batch: str):
    try:
        return capcut_inventory.undo(batch)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/api/cleanup/purge")
def api_cleanup_purge(batch: str):
    try:
        return capcut_inventory.purge(batch)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.get("/api/overview")
def api_overview():
    """Việc đang dở, tính từ dữ liệu thật — để người dùng biết cần làm gì tiếp."""
    projects = api_projects()["projects"]
    n_topics = sum(len(p["topics"]) for p in projects)
    built = [d for p in projects for t in p["topics"] for d in t["drafts"]]
    drafts = api_drafts()["drafts"]
    todo = {
        "chua_dung": sum(1 for p in projects for t in p["topics"] if not t["drafts"]),
        "chua_chup_moc": sum(1 for d in drafts if not d["snapshot"]),
        "dang_mo_trong_capcut": sum(1 for d in drafts if d["locked"]),
    }
    c = assetlib.conn()
    lib = dict(c.execute("SELECT COUNT(*) n, COALESCE(SUM(size),0) sz FROM assets").fetchone())
    owners = [dict(r) for r in c.execute(
        "SELECT owner, COUNT(*) n, SUM(use_count) uses FROM assets "
        "WHERE owner IS NOT NULL AND owner!='' GROUP BY owner ORDER BY n DESC").fetchall()]
    c.close()
    return {"projects": len(projects), "topics": n_topics, "built": len(built),
            "drafts": len(drafts), "todo": todo, "lib": lib, "owners": owners,
            "ffmpeg": assetlib.co_ffmpeg(),
            "capcut": {k: (str(v) if k in ("draft", "cache", "home") else v)
                       for k, v in assetlib.find_capcut().items()}}


# ───────── CÀI ĐẶT: nhập API key trong app, không sửa .env bằng tay ─────────
# Khai báo dạng DANH SÁCH để sau này thêm nhà cung cấp khác chỉ là thêm một dòng,
# không phải sửa cả backend lẫn giao diện.
NHA_CUNG_CAP = [
    {"key": "GEMINI_API_KEY", "ten": "Google Gemini", "bat_buoc": True,
     "dung_de": "Trích chủ đề từ record, chọn hook/SFX/B-roll, sửa caption, chế độ Agent",
     "lay_o": "https://aistudio.google.com/apikey"},
    {"key": "PEXELS_API_KEY", "ten": "Pexels", "bat_buoc": False,
     "dung_de": "Tải video stock làm B-roll. Không có thì draft vẫn dựng, chỉ thiếu B-roll",
     "lay_o": "https://www.pexels.com/api/"},
    {"key": "GEMINI_API_KEYS", "ten": "Gemini — nhiều key (tuỳ chọn)", "bat_buoc": False,
     "dung_de": "Xoay key khi cạn hạn ngạch. CHỈ có tác dụng nếu các key thuộc PROJECT "
                "khác nhau — Google tính hạn ngạch theo project",
     "lay_o": ""},
]


def _che(v: str) -> str:
    """Che key khi trả về giao diện — không bao giờ gửi nguyên văn ra ngoài."""
    return f"{v[:6]}…{v[-4:]}" if v and len(v) > 12 else ("đã có" if v else "")


@app.get("/api/settings")
def api_settings():
    return {"nha_cung_cap": [dict(n, da_co=bool(os.environ.get(n["key"])),
                                  che=_che(os.environ.get(n["key"], "")))
                             for n in NHA_CUNG_CAP],
            "file_env": str(ROOT / ".env")}


class SettingsReq(BaseModel):
    gia_tri: dict = {}          # {"GEMINI_API_KEY": "...", ...}


@app.post("/api/settings")
def api_settings_save(req: SettingsReq):
    """Ghi .env và áp dụng NGAY, không bắt khởi động lại."""
    hop_le = {n["key"] for n in NHA_CUNG_CAP}
    moi = {k: v.strip() for k, v in (req.gia_tri or {}).items() if k in hop_le and v.strip()}
    if not moi:
        raise HTTPException(400, "không có giá trị nào để lưu")

    f = ROOT / ".env"
    cu = {}
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.strip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cu[k.strip()] = v.strip()
    cu.update(moi)
    f.write_text("# Key do app ghi. KHÔNG đưa file này lên git / gửi cho người khác.\n"
                 + "".join(f"{k}={v}\n" for k, v in cu.items()), encoding="utf-8")

    for k, v in moi.items():        # áp dụng ngay cho tiến trình đang chạy
        os.environ[k] = v
    import sys as _s
    _s.path.insert(0, str(ROOT / "shorts"))
    import gemini_util
    gemini_util._CLIENTS.clear()    # client cũ giữ key cũ -> phải bỏ
    gemini_util._NGHI.clear()
    return {"da_luu": sorted(moi), "ghi_chu": "áp dụng ngay, không cần khởi động lại"}


@app.get("/api/editors")
def api_editors():
    """Danh sách editor có trong kho (để chọn gu khi tạo draft)."""
    c = assetlib.conn()
    rows = [r[0] for r in c.execute(
        "SELECT owner FROM assets WHERE owner IS NOT NULL AND owner!='' "
        "GROUP BY owner ORDER BY COUNT(*) DESC").fetchall()]
    c.close()
    if "shared" not in rows:
        rows.append("shared")
    return {"editors": rows, "keys": {"gemini": bool(os.environ.get("GEMINI_API_KEY")),
                                      "pexels": bool(os.environ.get("PEXELS_API_KEY"))}}


@app.post("/api/project/{proj}/generate")
def api_generate(proj: str, topic: int, editor: str = "shared", model: str = MODEL_CHAT_LUONG):
    """LUỒNG CHÍNH: chọn chủ đề + editor -> dựng draft CapCut theo gu editor đó."""
    work = (WORK / proj).resolve()
    if not (work / "topics.json").exists():
        raise HTTPException(404, "dự án chưa có topics.json (chưa phân tích record)")
    draft_name = f"{proj}_t{topic}_{editor}"

    def run(log):
        w = LogWriter(log)
        try:
            with contextlib.redirect_stdout(w):
                # Truyền cấu hình lớp của DỰ ÁN xuống build. Trước đây giao diện có
                # 7 công tắc, lưu vào DB đầy đủ, mà build không đọc — bật tắt xong
                # chẳng có gì xảy ra.
                du_an = projects.lay_theo_work(proj)
                bsd.build(work, topic, bsd.SFX_DEFAULT, model, False, draft_name, editor,
                          cau_hinh=(du_an or {}).get("cau_hinh"))
        except SystemExit as e:            # build tự dừng (vd .locked / thiếu key)
            w.flush(); log(str(e))
            raise RuntimeError("dừng — xem log")
        w.flush()
        return {"draft": draft_name}

    jid = run_job(f"Tạo draft · {proj} chủ đề {topic} · gu {editor}", run)
    return {"job": jid, "draft": draft_name}


@app.get("/api/jobs")
def api_jobs():
    return {"jobs": sorted(JOBS.values(), key=lambda j: -j["ts"])[:20]}


# ───────────────── CHẾ ĐỘ AGENT (chat) ─────────────────

@app.post("/api/agent/chat")
def api_agent_chat(session: str = "default", message: str = "",
                   model: str = "gemini-2.5-flash"):
    if not message.strip():
        raise HTTPException(400, "tin nhắn rỗng")
    import agent
    try:
        return agent.chat(session, message, model, run_job=run_job)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:200]}")


class XacNhanReq(BaseModel):
    session: str = "default"
    hanh_dong: str
    tham_so: dict = {}


@app.post("/api/agent/confirm")
def api_agent_confirm(req: XacNhanReq):
    """Agent KHÔNG tự chạy việc phá huỷ — nó đề xuất, người dùng bấm nút, rồi mới chạy.
    Một câu tiếng Việt hiểu nhầm không được phép xoá công của editor."""
    import agent
    return agent.xac_nhan(req.session, req.hanh_dong, req.tham_so, run_job=run_job)


@app.get("/api/agent/tools")
def api_agent_tools():
    """Registry tool + nhật ký chọn tool — để đo có cần router hay chưa."""
    import agent
    import sys as _s
    _s.path.insert(0, str(assetlib.ROOT / "shorts"))
    import gemini_util
    return {"tools": [{"ten": t.ten, "nhom": t.nhom, "kieu": t.kieu, "mo_ta": t.mo_ta}
                      for t in agent.TOOLS.values()],
            "thong_ke_tool": agent.thong_ke_tool(),
            "thong_ke_luot": agent.thong_ke_luot(),      # số liệu để chốt max_steps
            "key": gemini_util.trang_thai()}


@app.get("/api/agent/sessions")
def api_agent_sessions():
    import agent
    return {"sessions": agent.sessions()}


@app.get("/api/agent/history")
def api_agent_history(session: str = "default"):
    import agent
    return {"messages": agent.history(session)}


@app.post("/api/agent/reset")
def api_agent_reset(session: str = "default"):
    import agent
    agent.reset(session)
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    # no-store: đang sửa giao diện liên tục, để trình duyệt cache là mở ra thấy bản CŨ
    # ROOT chứ không phải __file__: đóng gói .exe thì __file__ trỏ vào bên trong gói
    # nội bộ (xem assetlib._goc()), ui.html phải nằm ngay cạnh file .exe.
    return HTMLResponse(
        (ROOT / "ui.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache"})


def _man_hinh_cho():
    """Màn chờ lúc khởi động bản .exe đóng gói.

    VÌ SAO: bấm .exe xong có tới ~6 giây cửa sổ console đen ngòm không phản hồi gì —
    lần đầu Windows Defender quét file mới copy còn lâu hơn nữa. Người quen desktop
    app bình thường thấy vậy tưởng app treo/lỗi, bấm thêm vài phát hoặc tắt luôn.

    Tkinter phải chạy trên LUỒNG CHÍNH (như _chon_bang_tkinter đã ghi chú) — nên đảo
    ngược cấu trúc cũ: uvicorn chuyển xuống luồng nền, luồng chính giữ tk.mainloop().
    uvicorn tự bỏ qua cài signal handler khi không chạy ở luồng chính (server.py:
    `if threading.current_thread() is not threading.main_thread(): return`) — không
    lo mất khả năng Ctrl+C, chỉ là do luồng nền lo, không phải signal module.

    Splash tự đóng + tự mở trình duyệt ngay khi server bắt đầu TRẢ LỜI THẬT (poll
    /api/overview), không phải sau một khoảng thời gian đoán mò — máy chậm hơn máy
    dev (CPU thay vì GPU, cold-start bị Defender quét) mà đoán mò 1,2 giây thì mở
    trình duyệt vào lúc server còn chưa lên, ra trang "không kết nối được"."""
    import threading, time, urllib.request
    import tkinter as tk

    t = threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning"),
        daemon=True)
    t.start()

    root = tk.Tk()
    root.title("CapCut Auto Editor")
    root.attributes("-topmost", True)
    w, h = 360, 130
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    root.resizable(False, False)
    tk.Label(root, text="CapCut Auto Editor", font=("Segoe UI", 13, "bold")).pack(pady=(22, 6))
    tk.Label(root, text="Đang khởi động…", font=("Segoe UI", 10)).pack()

    def cho_roi_dong():
        for _ in range(300):                              # trần 60s (300 × 0,2s)
            try:
                urllib.request.urlopen("http://127.0.0.1:8765/api/overview", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        root.after(0, root.destroy)

    threading.Thread(target=cho_roi_dong, daemon=True).start()
    root.mainloop()
    _mo_cua_so_app(giu_song=t.join)


def _mo_cua_so_app(giu_song):
    """Mở CỬA SỔ APP RIÊNG bằng pywebview (WebView2), không phải tab trình duyệt hệ thống.

    VÌ SAO: webbrowser.open() mở tab trình duyệt THẬT — có thanh địa chỉ hiện lồ lộ
    "127.0.0.1:8765", nút back/forward, favicon trình duyệt. Người dùng thử app báo
    đúng điều này: "trông thiếu chuyên nghiệp", không giống app desktop. pywebview mở
    một cửa sổ riêng của app, không thanh địa chỉ, dùng WebView2 (Chromium) đã có sẵn
    trên Windows 10/11 hiện đại — không cần cài thêm trình duyệt hay engine nào khác.

    Đóng cửa sổ này = đóng app (webview.start() mới trả về lúc đó) — khác hẳn đóng một
    TAB trình duyệt, vốn không tắt được server đứng phía sau. Vì vậy nhánh pywebview
    thành công thì KHÔNG gọi giu_song(): để __main__ trôi hết, tiến trình tự thoát.

    CÓ ĐƯỜNG LÙI: máy hiếm gặp thiếu WebView2 Runtime thì pywebview lỗi ngay lúc tạo
    cửa sổ — bắt lỗi, lùi về webbrowser.open() như bản trước, gọi giu_song() để giữ
    server sống (đóng tab lúc này KHÔNG được phép tắt app, vì không mở lại tab được
    nữa nếu chưa biết mở app bằng cách gõ lại URL)."""
    try:
        import webview
        webview.create_window("CapCut Auto Editor", "http://127.0.0.1:8765",
                               width=1360, height=860, min_size=(960, 600))
        webview.start()
    except Exception as e:
        print(f"  [!] Không mở được cửa sổ app riêng ({e}) — dùng trình duyệt hệ thống")
        import webbrowser
        webbrowser.open("http://127.0.0.1:8765")
        giu_song()           # đóng TAB không phải đóng app — giữ tiến trình sống


if __name__ == "__main__":
    # Tiến trình con của /api/pick gọi lại chính file/exe này kèm --pick — phải chặn
    # NGAY ĐẦU, trước dòng in "App: ..." và trước server, nếu không tiến trình con
    # lại thành một bản app thứ hai tranh cổng 8765 với bản gốc.
    if len(sys.argv) > 1 and sys.argv[1] == "--pick":
        _chon_bang_tkinter(sys.argv[2] if len(sys.argv) > 2 else "thu_muc")
        sys.exit(0)
    print("  App: http://127.0.0.1:8765")
    if getattr(sys, "frozen", False):
        _man_hinh_cho()
    else:
        uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
