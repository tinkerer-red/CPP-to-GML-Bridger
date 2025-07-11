import json
import os
import sys
from pathlib import Path

REQUIRED_KEYS = [
    "include_files",
    "project_name",
    "namespace"
]

def load_config(path):
    """
    Loads and validates the bridge config.json file.
    Applies defaults and normalizes static paths.
    No assumptions about input/output layout.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as file:
        raw = json.load(file)

    # Legacy alias support
    if "headers" in raw:
        print("[config] Warning: 'headers' is deprecated, use 'include_files' instead.")
        raw["include_files"] = raw.pop("headers")

    if "dll_name" in raw:
        print("[config] Warning: 'dll_name' is deprecated, use 'project_name' instead.")
        raw["project_name"] = raw.pop("dll_name")

    # Validate required keys
    for key in REQUIRED_KEYS:
        if key not in raw:
            raise ValueError(f"Missing required config key: {key}")

    # Normalize path-based fields
    raw["include_files"]    = [os.path.normpath(p) for p in raw["include_files"]]
    raw["link_libraries"]   = [os.path.normpath(p) for p in raw.get("link_libraries", [])]
    raw["extra_sources"]    = [os.path.normpath(p) for p in raw.get("extra_sources", [])]
    raw["extra_includes"]   = [os.path.normpath(p) for p in raw.get("extra_includes", [])]

    # Validate that every public header actually exists on disk
    missing_headers = [hdr for hdr in raw["include_files"] if not Path(hdr).exists()]
    if missing_headers:
        print("[config] Error: the following include_files were not found:", file=sys.stderr)
        for hdr in missing_headers:
            print(f"  • {hdr}", file=sys.stderr)
        sys.exit(1)

    # Validate that every link library actually exists on disk
    missing_libs = [lib for lib in raw["link_libraries"] if not Path(lib).exists()]
    if missing_libs:
        print("[config] Error: the following link_libraries were not found:", file=sys.stderr)
        for lib in missing_libs:
            print(f"  • {lib}", file=sys.stderr)
        sys.exit(1)

    # Optional fields
    raw.setdefault("targets", "auto")
    raw.setdefault("cmake_overrides", {})

    raw.setdefault("init_function", "YYExtensionInitialise")
    raw.setdefault("cleanup_function", "YYExtensionCleanup")

    raw.setdefault("skip_function_prefixes", [])
    raw.setdefault("strip_namespace_from_symbols", True)

    raw.setdefault("debug", False)
    raw.setdefault("verbose_logging", False)

    raw.setdefault("emit_docs", True)
    raw.setdefault("emit_vs_project", False)

    raw.setdefault("pre_build", [])
    raw.setdefault("post_build", [])

    raw.setdefault("preprocessor", ["cpp", "-P", "-dD"])
    raw.setdefault("preprocessor_defines", [])

    return raw
