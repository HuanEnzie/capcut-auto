#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_auto.py  —  Bộ công cụ tự động hoá CapCut (proof-of-concept)

Đọc / sửa file project (draft) của CapCut trực tiếp qua JSON, không cần mở UI.
An toàn theo thiết kế:
  - Mọi lệnh GHI đều mặc định DRY-RUN (chỉ in ra sẽ làm gì). Thêm --yes để ghi thật.
  - Trước khi ghi luôn tạo bản backup .autobak-<timestamp>.
  - Không bao giờ sửa file khi CapCut đang mở (dùng lệnh `check`).

Format đã kiểm chứng trên máy này: CapCut 9.0.0 (version 360000 / new_version 177.0.0).
Thời gian trong file tính bằng MICRO-GIÂY (1 giây = 1_000_000).

CÁCH DÙNG NHANH:
  python capcut_auto.py list
  python capcut_auto.py texts "0720"
  python capcut_auto.py clone "0720" "0720_COPY" --yes
  python capcut_auto.py set-text "0720_COPY" --index 3 --text "Dòng chữ mới" --yes
  python capcut_auto.py restore "0720_COPY"        # khôi phục backup gần nhất
"""

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

# ----------------------------------------------------------------------------
# Cấu hình đường dẫn (đã dò đúng trên máy này). Có thể override bằng env
# CAPCUT_DRAFTS_ROOT nếu cài ở nơi khác.
# ----------------------------------------------------------------------------
DEFAULT_ROOT = r"C:\Users\Acer\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft"
DRAFTS_ROOT = Path(os.environ.get("CAPCUT_DRAFTS_ROOT", DEFAULT_ROOT))
ROOT_META = DRAFTS_ROOT / "root_meta_info.json"

# Giữ nguyên phong cách JSON của CapCut: minified, UTF-8 thô (không escape unicode).
_DUMP_KW = dict(ensure_ascii=False, separators=(",", ":"))


# ----------------------------------------------------------------------------
# Tiện ích JSON an toàn
# ----------------------------------------------------------------------------
def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_str(obj) -> str:
    return json.dumps(obj, **_DUMP_KW)


def backup(path: Path) -> Path:
    """Sao lưu 1 file trước khi ghi đè. Trả về đường dẫn bản backup."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = path.with_name(path.name + f".autobak-{ts}")
    shutil.copy2(path, bak)
    return bak


def save_json_atomic(path: Path, obj, do_backup=True):
    """Ghi JSON kiểu CapCut một cách nguyên tử (ghi file tạm rồi thay thế)."""
    if do_backup and path.exists():
        b = backup(path)
        print(f"    backup -> {b.name}")
    tmp = path.with_name(path.name + ".writing.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(dump_str(obj))
    os.replace(tmp, path)  # thay thế nguyên tử trên cùng ổ đĩa


# ----------------------------------------------------------------------------
# Truy cập draft
# ----------------------------------------------------------------------------
def read_root_meta():
    return load_json(ROOT_META)


def find_entry(root_meta, name_or_id: str):
    """Tìm 1 draft trong root_meta theo tên hoặc draft_id."""
    for e in root_meta.get("all_draft_store", []):
        if e.get("draft_name") == name_or_id or e.get("draft_id") == name_or_id:
            return e
    return None


def draft_dir(name: str) -> Path:
    return DRAFTS_ROOT / name


def content_path(name: str) -> Path:
    return draft_dir(name) / "draft_content.json"


def timelines_content_paths(name: str):
    """Bản sao timeline nằm trong Timelines/<GUID>/draft_content.json (nếu có)."""
    tl = draft_dir(name) / "Timelines"
    if not tl.is_dir():
        return []
    return [p / "draft_content.json" for p in tl.iterdir()
            if (p / "draft_content.json").exists()]


# ----------------------------------------------------------------------------
# Xử lý text material
# ----------------------------------------------------------------------------
def get_text_materials(content):
    return content.get("materials", {}).get("texts", []) or []


def text_of(mat) -> str:
    """Lấy chuỗi hiển thị từ 1 text material (content là JSON lồng trong string)."""
    raw = mat.get("content")
    if not raw:
        return ""
    try:
        inner = json.loads(raw)
        return inner.get("text", "")
    except Exception:
        return "(không parse được content)"


def set_text_of(mat, new_text: str) -> bool:
    """Đổi chuỗi hiển thị của 1 text material. Trả về True nếu thành công."""
    raw = mat.get("content")
    if not raw:
        return False
    inner = json.loads(raw)
    inner["text"] = new_text
    # Cập nhật range của các style cho khớp độ dài chuỗi mới.
    styles = inner.get("styles") or []
    if len(styles) == 1:
        styles[0]["range"] = [0, len(new_text)]
    elif len(styles) > 1:
        # Nhiều style: giữ nguyên, chỉ nới range cuối để không cắt chữ.
        styles[-1]["range"] = [styles[-1].get("range", [0, 0])[0], len(new_text)]
    mat["content"] = dump_str(inner)
    # Nếu là caption 1-cụm-từ thì đồng bộ luôn 'words'.
    words = mat.get("words")
    if isinstance(words, dict):
        wt = words.get("text")
        if isinstance(wt, list) and len(wt) == 1:
            words["text"] = [new_text]
    return True


# ----------------------------------------------------------------------------
# Lệnh: check
# ----------------------------------------------------------------------------
def cmd_check(args):
    running = False
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq CapCut.exe"],
            capture_output=True, text=True
        ).stdout
        running = "CapCut.exe" in out
    except Exception:
        pass
    print(f"Drafts root : {DRAFTS_ROOT}")
    print(f"root_meta   : {'OK' if ROOT_META.exists() else 'THIẾU'}")
    print(f"CapCut đang chạy: {'CÓ  -> ĐÓNG CapCut trước khi ghi!' if running else 'không'}")


# ----------------------------------------------------------------------------
# Lệnh: list
# ----------------------------------------------------------------------------
def cmd_list(args):
    rm = read_root_meta()
    rows = rm.get("all_draft_store", [])
    print(f"{'TÊN DRAFT':<20} {'THỜI LƯỢNG':>10}  {'SỬA LÚC':<17} PATH")
    print("-" * 100)
    for e in rows:
        dur = e.get("tm_duration", 0) / 1_000_000
        mod = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.get("tm_draft_modified", 0) / 1_000_000))
        print(f"{e.get('draft_name',''):<20} {dur:>8.1f}s  {mod:<17} {e.get('draft_fold_path','')}")
    print(f"\nTổng: {len(rows)} draft.")


# ----------------------------------------------------------------------------
# Lệnh: texts
# ----------------------------------------------------------------------------
def cmd_texts(args):
    cp = content_path(args.draft)
    if not cp.exists():
        sys.exit(f"Không thấy {cp}")
    content = load_json(cp)
    mats = get_text_materials(content)
    print(f"Draft '{args.draft}' — {len(mats)} text material:\n")
    for i, m in enumerate(mats):
        t = text_of(m).replace("\n", "\\n")
        preview = (t[:70] + "…") if len(t) > 70 else t
        print(f"  [{i:>3}] {preview}")


# ----------------------------------------------------------------------------
# Lệnh: set-text
# ----------------------------------------------------------------------------
def cmd_set_text(args):
    cp = content_path(args.draft)
    if not cp.exists():
        sys.exit(f"Không thấy {cp}")
    content = load_json(cp)
    mats = get_text_materials(content)
    if not (0 <= args.index < len(mats)):
        sys.exit(f"index {args.index} ngoài phạm vi (0..{len(mats)-1})")

    old = text_of(mats[args.index])
    print(f"Draft   : {args.draft}")
    print(f"Text[{args.index}] cũ : {old!r}")
    print(f"Text[{args.index}] mới: {args.text!r}")

    if not args.yes:
        print("\n[DRY-RUN] Chưa ghi gì. Thêm --yes để áp dụng.")
        return

    set_text_of(mats[args.index], args.text)
    # Ghi cả file chính lẫn bản mirror trong Timelines/.
    save_json_atomic(cp, content)
    for tp in timelines_content_paths(args.draft):
        tc = load_json(tp)
        tm = get_text_materials(tc)
        if args.index < len(tm):
            set_text_of(tm[args.index], args.text)
            save_json_atomic(tp, tc)
    # Đánh dấu vừa sửa để CapCut xếp lên đầu danh sách.
    _touch_modified(args.draft)
    print("\n✅ Đã cập nhật. Mở CapCut và mở draft này để kiểm tra.")


def _touch_modified(name: str):
    now_us = int(time.time() * 1_000_000)
    # draft_meta_info.json
    dmi = draft_dir(name) / "draft_meta_info.json"
    if dmi.exists():
        d = load_json(dmi)
        d["tm_draft_modified"] = now_us
        save_json_atomic(dmi, d, do_backup=False)
    # root_meta_info.json
    rm = read_root_meta()
    e = find_entry(rm, name)
    if e:
        e["tm_draft_modified"] = now_us
        save_json_atomic(ROOT_META, rm, do_backup=False)


# ----------------------------------------------------------------------------
# Lệnh: clone  (nhân bản 1 draft thành project mới — KHÔNG đụng bản gốc)
# ----------------------------------------------------------------------------
def _ignore_locks(dirpath, names):
    # Không copy marker khoá / file tạm để tránh CapCut tưởng draft đang mở.
    return [n for n in names if n == ".locked" or n.endswith(".writing.tmp")]


def cmd_clone(args):
    src = args.src
    dst = args.dst
    src_dir = draft_dir(src)
    dst_dir = draft_dir(dst)
    if not src_dir.is_dir():
        sys.exit(f"Không thấy draft nguồn: {src_dir}")
    if dst_dir.exists():
        sys.exit(f"Đích đã tồn tại: {dst_dir}")

    rm = read_root_meta()
    src_entry = find_entry(rm, src)
    if not src_entry:
        sys.exit(f"Không thấy '{src}' trong root_meta_info.json")

    new_id = str(uuid.uuid4()).upper()
    print(f"Clone   : '{src}'  ->  '{dst}'")
    print(f"new draft_id: {new_id}")
    print(f"đích       : {dst_dir}")

    if not args.yes:
        print("\n[DRY-RUN] Chưa tạo gì. Thêm --yes để nhân bản thật.")
        return

    # 1) copy toàn bộ thư mục draft
    shutil.copytree(src_dir, dst_dir, ignore=_ignore_locks)

    # 2) sửa draft_meta_info.json của bản sao
    dmi = dst_dir / "draft_meta_info.json"
    d = load_json(dmi)
    d["draft_id"] = new_id
    d["draft_name"] = dst
    d["draft_fold_path"] = str(dst_dir).replace("\\", "/")
    now_us = int(time.time() * 1_000_000)
    d["tm_draft_create"] = now_us
    d["tm_draft_modified"] = now_us
    save_json_atomic(dmi, d, do_backup=False)

    # 3) sửa 'name' trong draft_content.json (và mirror)
    for cp in [dst_dir / "draft_content.json", *timelines_content_paths(dst)]:
        c = load_json(cp)
        c["name"] = dst
        save_json_atomic(cp, c, do_backup=False)

    # 4) đăng ký vào root_meta_info.json (có backup)
    new_entry = json.loads(dump_str(src_entry))  # deep copy
    new_entry["draft_id"] = new_id
    new_entry["draft_name"] = dst
    dst_fold = str(dst_dir).replace("\\", "/")
    new_entry["draft_fold_path"] = dst_fold
    new_entry["draft_cover"] = dst_fold + "\\draft_cover.jpg"
    new_entry["draft_json_file"] = dst_fold + "\\draft_content.json"
    new_entry["tm_draft_create"] = now_us
    new_entry["tm_draft_modified"] = now_us
    rm["all_draft_store"].insert(0, new_entry)
    rm["draft_ids"] = rm.get("draft_ids", 0) + 1
    save_json_atomic(ROOT_META, rm)

    print("\n✅ Đã nhân bản. Mở CapCut, draft mới sẽ xuất hiện đầu danh sách.")


# ----------------------------------------------------------------------------
# Lệnh: restore  (khôi phục backup gần nhất cho draft_content.json)
# ----------------------------------------------------------------------------
def cmd_restore(args):
    d = draft_dir(args.draft)
    baks = sorted(d.glob("draft_content.json.autobak-*"))
    if not baks:
        sys.exit("Không có bản backup nào để khôi phục.")
    latest = baks[-1]
    print(f"Khôi phục {latest.name}  ->  draft_content.json")
    if not args.yes:
        print("[DRY-RUN] Thêm --yes để khôi phục thật.")
        return
    shutil.copy2(latest, d / "draft_content.json")
    print("✅ Đã khôi phục.")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Tự động hoá CapCut qua file project (JSON).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="Kiểm tra đường dẫn & CapCut có đang chạy không").set_defaults(func=cmd_check)
    sub.add_parser("list", help="Liệt kê tất cả draft").set_defaults(func=cmd_list)

    p = sub.add_parser("texts", help="Liệt kê các dòng text trong 1 draft")
    p.add_argument("draft")
    p.set_defaults(func=cmd_texts)

    p = sub.add_parser("set-text", help="Đổi 1 dòng text trong draft")
    p.add_argument("draft")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--yes", action="store_true", help="Ghi thật (mặc định dry-run)")
    p.set_defaults(func=cmd_set_text)

    p = sub.add_parser("clone", help="Nhân bản 1 draft thành project mới")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--yes", action="store_true", help="Tạo thật (mặc định dry-run)")
    p.set_defaults(func=cmd_clone)

    p = sub.add_parser("restore", help="Khôi phục draft_content.json từ backup gần nhất")
    p.add_argument("draft")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_restore)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    # Đảm bảo stdout in được tiếng Việt trên Windows console.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
