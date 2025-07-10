# generator/input_stager.py

import shutil
from pathlib import Path

def copy_upstream_sources(project_root: Path, output_root: Path):
    """
    Mirror everything under project_root/input → output_root/input,
    so downstream generators (CMake, etc.) can rely on a single layout.
    """
    src = project_root / "input"
    dst = output_root / "upstream"

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
