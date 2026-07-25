# -*- coding: utf-8 -*-
"""draft_diff.py — So sánh draft TA SINH RA với draft SAU KHI EDITOR SỬA.

Luồng:
  1. Lúc export xong  -> snapshot(draft)  : chụp lại "vân tay" tài nguyên
  2. Editor mở CapCut sửa, lưu lại
  3. sync(draft, owner) -> diff + nạp cái editor THÊM vào kho, đánh dấu cái bị GỠ

  python draft_diff.py --snapshot 1107_short04_v7
  python draft_diff.py --diff     1107_short04_v7
  python draft_diff.py --sync     1107_short04_v7 --owner dan
"""
import argparse, json, sys, time
from pathlib import Path

import assetlib, draft_scan

SNAP_DIR = assetlib.ROOT / "snapshots"


def _key(r: dict) -> str:
    """Khoá nhận dạng 1 tài nguyên trong draft."""
    return f"{r['kind']}|{r.get('resource_id') or ''}|{Path(r.get('path') or '').name or r.get('name','')}"


# ─────────── VÂN TAY CẤU TRÚC: để đo ĐỘ PHẢI SỬA ───────────
# Mốc cũ chỉ chụp tài nguyên nên chỉ trả lời được "editor thêm/gỡ cái gì".
# Câu quan trọng hơn cho việc tự tiến hoá là "editor phải sửa BAO NHIÊU thì draft
# mới dùng được" — càng ngày càng ít nghĩa là app càng hợp gu. Muốn trả lời thì
# phải chụp cả caption, mốc thời gian và âm lượng.
MS = 1000                       # CapCut tính bằng micro giây
LECH_GIO = 100 * MS             # lệch dưới 100ms coi như không đụng tới


def _text_cua(mat: dict) -> str:
    """Chữ nằm trong material text dưới dạng chuỗi JSON."""
    try:
        return (json.loads(mat.get("content") or "{}").get("text") or "").strip()
    except (ValueError, TypeError):
        return (mat.get("recognize_text") or "").strip()


def van_tay(draft: str) -> dict:
    """Vân tay cấu trúc của draft: caption, nhịp cắt, âm lượng."""
    d = draft_scan.DRAFT_ROOT / Path(draft).name / "draft_content.json"
    if not d.is_file():
        return {}
    c = json.loads(d.read_text(encoding="utf-8", errors="replace"))
    mats = c.get("materials") or {}
    text_by_id = {m["id"]: _text_cua(m) for m in (mats.get("texts") or []) if m.get("id")}
    path_by_id = {m["id"]: Path(m.get("path") or "").name
                  for b in ("videos", "audios") for m in (mats.get(b) or []) if m.get("id")}

    caption, video, am_luong = [], [], {}
    for t in c.get("tracks") or []:
        loai = t.get("type")
        for s in t.get("segments") or []:
            tr = s.get("target_timerange") or {}
            if loai == "text":
                txt = text_by_id.get(s.get("material_id"), "")
                if txt:
                    caption.append({"t": txt, "s": tr.get("start", 0), "d": tr.get("duration", 0)})
            elif loai == "video":
                video.append({"s": tr.get("start", 0), "d": tr.get("duration", 0)})
            elif loai == "audio":
                ten = path_by_id.get(s.get("material_id")) or s.get("material_id", "")
                am_luong[ten] = round(s.get("volume", 1.0), 3)
    caption.sort(key=lambda x: x["s"])
    video.sort(key=lambda x: x["s"])
    return {"caption": caption, "video": video, "am_luong": am_luong,
            "tong_dai": max((v["s"] + v["d"] for v in video), default=0)}


def _ghep_caption(ct: list, cs: list):
    """Ghép caption trước ↔ sau, trả (chữ mới, bị bỏ, đổi giờ).

    Ghép bằng dict khoá theo CHỮ là sai: trong 208 caption thì trùng chữ là chắc
    chắn, dict chỉ giữ dòng cuối nên các dòng còn lại bị so với timing của dòng
    khác — so vân tay VỚI CHÍNH NÓ cũng ra 'đổi giờ 18 dòng'. Một chỉ số tiến hoá
    báo sai kiểu này còn tệ hơn là không có chỉ số.
    Cách đúng: cùng chữ thì ghép với dòng GẦN NHẤT về thời gian, ghép rồi thì loại.
    """
    con_lai: dict = {}
    for i, x in enumerate(ct):
        con_lai.setdefault(x["t"], []).append(i)
    moi, doi_gio, da_ghep = 0, 0, 0
    for y in cs:
        ds = con_lai.get(y["t"])
        if not ds:
            moi += 1                       # chữ chưa từng có = editor sửa hoặc thêm
            continue
        j = min(ds, key=lambda i: abs(ct[i]["s"] - y["s"]))
        ds.remove(j); da_ghep += 1
        if abs(ct[j]["s"] - y["s"]) > LECH_GIO or abs(ct[j]["d"] - y["d"]) > LECH_GIO:
            doi_gio += 1
    return moi, len(ct) - da_ghep, doi_gio


def _so_van_tay(truoc: dict, sau: dict) -> dict:
    """Đếm editor đã đụng vào bao nhiêu phần. Chỉ đếm cái ĐO ĐƯỢC, không suy diễn."""
    sua_chu, bo_chu, doi_gio = _ghep_caption(truoc.get("caption") or [], sau.get("caption") or [])
    cs = sau.get("caption") or []

    vt, vs = truoc.get("video") or [], sau.get("video") or []
    doi_nhip = abs(len(vs) - len(vt)) + sum(
        1 for a, b in zip(vt, vs) if abs(a["s"] - b["s"]) > LECH_GIO or abs(a["d"] - b["d"]) > LECH_GIO)

    at, as_ = truoc.get("am_luong") or {}, sau.get("am_luong") or {}
    chinh_tieng = sum(1 for k, v in as_.items() if k in at and abs(at[k] - v) > 0.02)

    return {"caption": {"tong": len(cs), "sua_hoac_them": sua_chu, "bo": bo_chu, "doi_gio": doi_gio},
            "nhip_cat": {"tong": len(vs), "bi_doi": doi_nhip},
            "am_luong": {"tong": len(as_), "bi_chinh": chinh_tieng},
            "tong_dai_lech_giay": round(abs(sau.get("tong_dai", 0) - truoc.get("tong_dai", 0)) / 1e6, 1)}


def snapshot(draft: str) -> Path:
    res = draft_scan.scan(draft)
    SNAP_DIR.mkdir(exist_ok=True)
    vt = van_tay(draft)
    p = SNAP_DIR / f"{Path(draft).name}.json"
    p.write_text(json.dumps({"draft": Path(draft).name, "ts": time.time(),
                             "items": {_key(r): r for r in res}, "van_tay": vt},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã chụp {len(res)} tài nguyên + {len(vt.get('caption', []))} caption "
          f"/ {len(vt.get('video', []))} đoạn hình -> {p.name}")
    return p


def diff(draft: str) -> dict:
    p = SNAP_DIR / f"{Path(draft).name}.json"
    if not p.exists():
        sys.exit(f"Chưa có snapshot cho '{draft}' — chạy --snapshot ngay sau khi export.")
    moc = json.loads(p.read_text(encoding="utf-8"))
    before = moc["items"]
    after = {_key(r): r for r in draft_scan.scan(draft)}
    added = [v for k, v in after.items() if k not in before]
    removed = [v for k, v in before.items() if k not in after]
    kept = [v for k, v in after.items() if k in before]
    out = {"added": added, "removed": removed, "kept": kept}

    # Mốc chụp bằng bản cũ chưa có vân tay -> nói thẳng là chưa đo được, đừng trả 0
    # rồi để người đọc tưởng editor không sửa gì.
    if moc.get("van_tay"):
        out["sua"] = _so_van_tay(moc["van_tay"], van_tay(draft))
        out["sua"]["diem"] = _diem(out["sua"], len(added), len(removed))
    else:
        out["sua"] = {"chua_do_duoc": "mốc này chụp trước khi có vân tay cấu trúc — "
                                      "chụp mốc lại để lần sau đo được độ phải sửa"}
    return out


def _diem(sua: dict, them: int, go: int) -> float:
    """ĐỘ PHẢI SỬA: tỉ lệ phần editor phải đụng vào / tổng số phần.

    0 = mở ra dùng luôn, 1 = sửa lại gần hết. Chỉ số này giảm dần theo tháng mới là
    bằng chứng app đang hợp gu hơn — thay cho cảm tính "hình như đỡ hơn".
    """
    dung = (sua["caption"]["sua_hoac_them"] + sua["caption"]["bo"] + sua["caption"]["doi_gio"]
            + sua["nhip_cat"]["bi_doi"] + sua["am_luong"]["bi_chinh"] + them + go)
    tong = (sua["caption"]["tong"] + sua["nhip_cat"]["tong"] + sua["am_luong"]["tong"]) or 1
    return round(min(1.0, dung / tong), 3)


def _ghi_do(draft: str, editor: str, sua: dict):
    """Lưu lại mỗi lần đo. Một con số lẻ không nói gì; ĐƯỜNG của nó theo tháng mới
    trả lời được câu 'app có đang hợp gu hơn không'."""
    if not sua or "diem" not in sua:
        return
    c = assetlib.conn()
    c.execute("CREATE TABLE IF NOT EXISTS sua_log("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, draft TEXT, editor TEXT,"
              " diem REAL, chi_tiet TEXT, ts REAL)")
    c.execute("INSERT INTO sua_log(draft,editor,diem,chi_tiet,ts) VALUES(?,?,?,?,?)",
              (Path(draft).name, editor, sua["diem"],
               json.dumps(sua, ensure_ascii=False), time.time()))
    c.commit(); c.close()


def lich_su_do(editor: str = "", limit: int = 100) -> dict:
    c = assetlib.conn()
    c.execute("CREATE TABLE IF NOT EXISTS sua_log("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, draft TEXT, editor TEXT,"
              " diem REAL, chi_tiet TEXT, ts REAL)")
    sql = "SELECT draft, editor, diem, ts FROM sua_log"
    a = []
    if editor:
        sql += " WHERE editor=?"; a.append(editor)
    rows = [dict(r) for r in c.execute(sql + " ORDER BY id DESC LIMIT ?", a + [limit]).fetchall()]
    c.close()
    if not rows:
        return {"so_lan_do": 0,
                "ghi_chu": "chưa có số liệu — chụp mốc rồi đồng bộ vài draft là có"}
    d = [r["diem"] for r in rows]
    return {"so_lan_do": len(rows), "moi_nhat": d[0],
            "trung_binh": round(sum(d) / len(d), 3),
            "tot_nhat": min(d), "te_nhat": max(d), "lich_su": rows[:20]}


def sync(draft: str, owner: str) -> dict:
    """Nạp tài nguyên editor THÊM vào kho; ghi nhận cái bị GỠ (tín hiệu âm)."""
    d = diff(draft)
    _ghi_do(draft, owner, d.get("sua") or {})
    n_new = 0
    for r in d["added"]:
        nm = (r["name"] or "") + " " + (r["path"] or "")
        if any(h in nm for h in draft_scan.SKIP_NAME_HINT):
            continue
        if r["kind"] == "video" and not any(h in nm.lower() for h in draft_scan.STOCK_HINT):
            continue
        if not r["resource_id"] and not r["has_file"]:
            continue
        _, st = assetlib.add(r["kind"], name=r["name"], category=r["category"],
                             src_path=r["path"] if r["has_file"] else None,
                             resource_id=r["resource_id"], origin="user",
                             owner=owner, draft=Path(draft).name)
        n_new += (st == "new")
    for r in d["removed"]:
        assetlib.mark_dropped(resource_id=r.get("resource_id"), draft=Path(draft).name)
    # giữ nguyên cái editor GIỮ LẠI -> tín hiệu dương
    for r in d["kept"]:
        if r.get("resource_id"):
            assetlib.add(r["kind"], name=r["name"], category=r["category"],
                         src_path=r["path"] if r["has_file"] else None,
                         resource_id=r["resource_id"], origin="user", owner=owner,
                         draft=Path(draft).name)
    snapshot(draft)     # cập nhật mốc cho lần sau
    return {"added": len(d["added"]), "new_in_lib": n_new,
            "removed": len(d["removed"]), "kept": len(d["kept"]),
            "do_phai_sua": (d.get("sua") or {}).get("diem")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", metavar="DRAFT")
    ap.add_argument("--diff", metavar="DRAFT")
    ap.add_argument("--sync", metavar="DRAFT")
    ap.add_argument("--owner", default="shared")
    ap.add_argument("--do", action="store_true", help="xem lịch sử độ phải sửa")
    a = ap.parse_args()
    if a.do:
        import json as _j
        print(_j.dumps(lich_su_do(), ensure_ascii=False, indent=1))
    elif a.snapshot:
        snapshot(a.snapshot)
    elif a.diff:
        d = diff(a.diff)
        for tag, items in (("THÊM", d["added"]), ("GỠ BỎ", d["removed"])):
            print(f"\n=== {tag} ({len(items)}) ===")
            for r in items:
                print(f"  {r['kind']:14} {str(r['name'])[:44]:46} rid={r.get('resource_id')}")
        print(f"\nGiữ nguyên: {len(d['kept'])}")
    elif a.sync:
        r = sync(a.sync, a.owner)
        print(f"Editor thêm {r['added']} ({r['new_in_lib']} mới vào kho), "
              f"gỡ {r['removed']}, giữ {r['kept']}")
    else:
        ap.error("cần --snapshot / --diff / --sync / --do")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
