# -*- coding: utf-8 -*-
"""Bật CUDA cho ctranslate2/faster-whisper trên Windows.

ctranslate2 nạp cublas/cudnn theo PATH (không theo os.add_dll_directory),
nên phải thêm các thư mục bin của gói nvidia-*-cu12 vào PATH TRƯỚC khi
import/dùng faster_whisper. Gọi enable_cuda() ở đầu chương trình.
"""
import os
import site


def enable_cuda() -> list[str]:
    """Thêm bin dir của các gói nvidia CUDA runtime vào PATH. Trả về list dir đã thêm."""
    added = []
    roots = list(site.getsitepackages())
    try:
        roots.append(site.getusersitepackages())
    except Exception:
        pass
    for r in roots:
        for sub in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"):
            b = os.path.join(r, "nvidia", sub, "bin")
            if os.path.isdir(b) and b not in added:
                os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(b)
                except Exception:
                    pass
                added.append(b)
    return added
