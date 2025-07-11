# generator/cmake_gen.py
import os
import re
from pathlib import Path
from string import Template

TEMPLATE_PATH = Path(__file__).parent / "templates" / "cmake_lists.txt.tpl"
CMAKE_TEMPLATE = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))

def _to_src_rel(path: Path) -> str:
    """
    Convert a project‐root–relative path to a ${CMAKE_CURRENT_SOURCE_DIR}/… form
    so that fixed/generated files all resolve properly.
    """
    project_root = Path.cwd().resolve()
    output_root  = project_root / "output"
    rel = path.resolve().relative_to(project_root)
    return f"${{CMAKE_CURRENT_SOURCE_DIR}}/{rel.as_posix()}"

def to_cmake_rel(path: Path, cmake_dir: Path) -> str:
    """
    Convert an absolute Path into a CMake-friendly relative path
    from the directory containing CMakeLists.txt (cmake_dir), by:
      1) Walking cmake_dir ↑ parent by parent until `path` is underneath it.
      2) Counting how many levels we walked (n).
      3) Computing the leftover path from that common ancestor ↓ to `path`.
      4) Emitting ../ repeated n times, then the downward segments.
    Raises if no common ancestor is found.
    """
    path = path.resolve()
    cmake_dir = cmake_dir.resolve()

    ups = 0
    current = cmake_dir

    # Walk up until `path` is a subpath of `current`
    while True:
        try:
            # path.relative_to(current) will succeed if `path` is inside `current`
            down = path.relative_to(current)
            break
        except Exception:
            # Move one directory up
            if current.parent == current:
                raise ValueError(f"Cannot relativize {path} to {cmake_dir}")
            current = current.parent
            ups += 1

    # Build "../" * ups + downward path
    parts = [".."] * ups + list(down.parts)
    rel = Path(*parts).as_posix()

    return f"${{CMAKE_CURRENT_SOURCE_DIR}}/{rel}"

from pathlib import Path

def select_best_library(target: str, lib_paths: list[Path]) -> Path:
    """
    Given a CMake target name (e.g. "windows-x64-uwp") and a list of .lib Paths,
    returns the best match based on architecture and UWP suffix.

    Heuristic:
      1. If there's exactly one candidate, return it immediately.
      2. Parse out `arch` (second dash-separated component) and `uwp` flag.
      3. Score each path:
           +10 if it contains the exact arch (or arch_… / …_arch) segment
           +5  if it has or does not have "uwp" to match the target’s uwp-ness
      4. Return the highest-scoring path. If top score ≤ 0, errors out.
    """
    if not lib_paths:
        raise ValueError("No library files provided to select from")
    if len(lib_paths) == 1:
        return lib_paths[0]

    # tokenize your target ("windows-x64" → ["windows","x64"])
    tokens = [t for t in re.split(r'[^0-9A-Za-z]+', target.lower()) if t]

    # if there's only one choice, just use it
    if len(lib_paths) == 1:
        return lib_paths[0]

    # convert every path‐string into a Path once
    path_objs = [Path(p) for p in lib_paths]

    def score(path: Path) -> int:
        # break the full path into segments and lowercase them
        segments = [seg.lower() for seg in path.parts]
        # count how many target-tokens appear in those segments
        return sum(1 for tok in tokens if tok in segments)

    # pick the Path with the highest score
    best_path = max(path_objs, key=score)
    best_score = score(best_path)

    if best_score == 0:
        raise RuntimeError(
            f"Could not pick a library for target '{target}'.\n"
            f"Candidates: {lib_paths}"
        )

    return str(best_path)

def generate_cmake_for_target(config, sources, target, defines):
    project_name = config["project_name"]
    verbose      = config.get("verbose_logging", False)

    project_root = Path.cwd()
    input_root   = project_root / "input"
    output_root  = project_root / "output"
    build_dir    = output_root / "build" / target
    build_dir.mkdir(parents=True, exist_ok=True)

    # ── Sources ────────────────────────────────────────────────────────────────
    native_sources = [
        to_cmake_rel(Path(p), build_dir)
        for p in sources.get("source_files", [])
    ]
    gen_src_dir    = output_root / "src"
    generated_srcs = [
        to_cmake_rel(gen_src_dir / f"{project_name}.cpp", build_dir),
        to_cmake_rel(gen_src_dir / f"{project_name}.h",  build_dir),
        to_cmake_rel(gen_src_dir / "RefManager.cpp",     build_dir),
        to_cmake_rel(gen_src_dir / "RefManager.h",       build_dir),
    ]
    extra_srcs     = [to_cmake_rel(Path(s), build_dir) for s in config.get("extra_sources", [])]

    all_sources = native_sources + generated_srcs + extra_srcs
    all_sources_txt = "\n".join(f"    {s}" for s in all_sources)

    # ── Headers ───────────────────────────────────────────────────────────────
    header_files = []
    for h in sources.get("header_files", []):
        orig = Path(h).resolve()
        # if it lives under input_root, map it into output/upstream/…
        try:
            rel = orig.relative_to(input_root)
            mapped = output_root / "upstream" / rel
        except ValueError:
            mapped = orig
        header_files.append(to_cmake_rel(mapped, build_dir))

    extra_headers = [
        to_cmake_rel(Path(h).resolve(), build_dir)
        for h in config.get("extra_headers", [])
    ]

    all_headers = header_files + extra_headers
    all_headers_lines = "\n".join(f"    {h}" for h in all_headers)

    # ── Include directories ────────────────────────────────────────────────────
    include_dirs = set()

    # infer SDK include roots from your input headers
    for hdr in sources.get("header_files", []):
        hdr = Path(hdr).resolve()
        try:
            rel = hdr.relative_to(input_root)
            sdk_root = (output_root / "upstream" / rel.parent).resolve()
            include_dirs.add(sdk_root)
        except ValueError:
            # not under input_root → skip
            pass

    # always add generated headers
    include_dirs.add((output_root / "src").resolve())

    # any extras
    include_dirs |= {Path(d).resolve() for d in config.get("extra_includes", [])}

    include_lines = "\n".join(
        f"    {to_cmake_rel(d, build_dir)}"
        for d in sorted(include_dirs)
    )


    # ── Compile‐time definitions ────────────────────────────────────────────────
    compile_defs = list(defines) + config.get("preprocessor_defines", [])
    if "windows" in target:
        compile_defs.append("GM_WINDOWS")
    elif "linux" in target:
        compile_defs.append("GM_LINUX")
    elif "android" in target:
        compile_defs.append("GM_ANDROID")
    elif "ios" in target:
        compile_defs.append("GM_IOS")
    elif "mac" in target:
        compile_defs.append("GM_MAC")
    defs_lines = "\n".join(f"    {d}" for d in compile_defs)

    # ── Link libraries ─────────────────────────────────────────────────────────
    link_lines = []
    # first try an automatically‐discovered .lib from sources["library_files"]
    libs = sources.get("library_files", []) or config.get("link_libraries", [])
    if libs:
        # if we have parsed library_files, pick best one
        if sources.get("library_files"):
            chosen = select_best_library(target, libs)
            link_lines.append(f'    "{to_cmake_rel(Path(chosen), build_dir)}"')
        else:
            # fall back to whatever user configured explicitly
            for lib in libs:
                link_lines.append(f'    "{to_cmake_rel(Path(lib), build_dir)}"')
    link_lines_txt = "\n".join(link_lines)

    # ── Library type & C++ std ────────────────────────────────────────────────
    lib_type = "STATIC" if "ios" in target else "SHARED"
    cpp_std  = config.get("cpp_standard", "17")

    # ── Render & write ────────────────────────────────────────────────────────
    cmake_txt = CMAKE_TEMPLATE.substitute({
        "PROJECT_NAME":        project_name,
        "LIBRARY_TYPE":        lib_type,
        "ALL_SOURCES":         all_sources_txt,
        "ALL_HEADERS":         all_headers_lines,
        "INCLUDE_DIRS":        include_lines,
        "COMPILE_DEFINITIONS": defs_lines,
        "LINK_LIBRARIES":      link_lines_txt,
        "CPP_STANDARD":        cpp_std,
    })

    cmake_file = build_dir / "CMakeLists.txt"
    cmake_file.write_text(cmake_txt, encoding="utf-8")
    if verbose:
        print(f"[GMBridge][cmake_gen] Wrote {cmake_file}")
