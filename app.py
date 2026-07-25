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

sys.path.insert(0, str(assetlib.ROOT / "shorts"))
import build_short_draft as bsd

ROOT = assetlib.ROOT
DRAFT_ROOT = draft_scan.DRAFT_ROOT
WORK = ROOT / "shorts" / "work"

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
def api_draft_open(name: str):
    """Mở thư mục draft trong Explorer. Dựng xong mà phải tự đi tìm thư mục thì
    coi như chưa xong việc — nút này nối app với CapCut."""
    d = (DRAFT_ROOT / name).resolve()
    if d.parent != DRAFT_ROOT.resolve() or not d.is_dir():   # chặn ../ đi ra ngoài
        raise HTTPException(404, "không thấy draft")
    os.startfile(str(d))                                     # noqa: S606 (app chạy local)
    return {"ok": True, "path": str(d)}


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


VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mp3", ".wav", ".m4a"}


def default_record_dir() -> Path:
    """Thư mục record mặc định. Máy mới cài KHÔNG có 'E:/E Download/Recap' —
    hardcode một đường dẫn của máy dev là màn hình đầu tiên đã báo lỗi đỏ."""
    home = Path.home()
    for c in (Path(r"E:/E Download/Recap"), home / "Videos", home / "Downloads", home):
        if c.is_dir():
            return c
    return home


@app.get("/api/browse")
def api_browse(dir: str = ""):
    """Liệt kê file record trong 1 thư mục (app chạy local nên duyệt thẳng ổ đĩa,
    không upload — file 2-3 tiếng vài GB không upload qua trình duyệt được)."""
    d = Path(dir) if dir else default_record_dir()
    if not d.exists() or not d.is_dir():
        raise HTTPException(404, f"Không thấy thư mục: {d}")
    files = []
    for p in sorted(d.iterdir()):
        if p.is_file() and p.suffix.lower() in VIDEO_EXT:
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
                files.append({
                    "path": str(p).replace("\\", "/"), "name": p.name,
                    "mb": round(p.stat().st_size / 1e6),
                    "dur_min": round(dur / 60),
                    # đo thật trên GPU này: tầng khảo sát (batched+greedy) ~43x realtime;
                    # chia 30 để cộng luôn thời gian tách audio 16kHz của file dài.
                    "eta_min": max(1, round(dur / 30 / 60)),
                    "video": has_v,
                })
            except (OSError, subprocess.SubprocessError):
                pass
    return {"dir": str(d).replace("\\", "/"), "files": files}


@app.post("/api/ingest")
def api_ingest(path: str, asr: str = "small", model: str = "gemini-2.5-flash",
               device: str = "cuda"):
    """LUỒNG ĐẦU: record thô -> transcript -> trích chủ đề -> hiện ở tab Dự án."""
    src = Path(path)
    if not src.exists():
        raise HTTPException(404, f"Không thấy file: {path}")

    def run(log):
        import transcribe as tr
        import topics as tp
        with contextlib.redirect_stdout(LogWriter(log)):
            print(f"[1/2] Khảo sát nhanh '{src.name}' (model {asr}, {device})...")
            # TẦNG 1: batched + greedy, không mốc từ -> đo được ~43x realtime
            # (cách cũ 8.5x). Mốc từng từ để tầng 2 lo, chỉ trên đoạn được chọn.
            tr.transcribe_survey(str(src), asr, device)
            wd = tr.work_dir(str(src))
            print(f"[2/2] Gemini trích chủ đề ({model})...")
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
            "capcut": {k: (str(v) if k in ("draft", "cache", "home") else v)
                       for k, v in assetlib.find_capcut().items()}}


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
def api_generate(proj: str, topic: int, editor: str = "shared", model: str = "gemini-2.5-flash"):
    """LUỒNG CHÍNH: chọn chủ đề + editor -> dựng draft CapCut theo gu editor đó."""
    work = (WORK / proj).resolve()
    if not (work / "topics.json").exists():
        raise HTTPException(404, "dự án chưa có topics.json (chưa phân tích record)")
    draft_name = f"{proj}_t{topic}_{editor}"

    def run(log):
        w = LogWriter(log)
        try:
            with contextlib.redirect_stdout(w):
                bsd.build(work, topic, bsd.SFX_DEFAULT, model, False, draft_name, editor)
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
    return HTMLResponse(
        (Path(__file__).parent / "ui.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache"})


if __name__ == "__main__":
    print("  App: http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
