import os
import re
import sys
import subprocess
from typing import List, Dict, Set

# Regex to match C/C++ free-function prototypes
FUNC_RE = re.compile(
    r'^\s*'
    r'(?P<ret>[A-Za-z_]\w*(?:\s+[\w\*\:<>]+)*)'
    r'\s+'
    r'(?P<name>[A-Za-z_]\w*)'
    r'\s*\('
    r'(?P<args>[^)]*)'
    r'\)\s*;',
    re.MULTILINE
)

IDENTIFIER_RE = re.compile(r'^[A-Za-z_]\w*$')
IDENTIFIER_WITH_STDCALL = re.compile(r'^[A-Za-z_]\w*(?:@\d+)?$')

def get_exports_from_binary(path: str) -> List[str]:
    exports: Set[str] = set()
    if not os.path.isfile(path):
        print(f"[GMBridge][discover_exports]  ⚠️ File not found: {path}")
        return []

    # pick the right tool
    if os.name == "nt":
        cmd = ["dumpbin", "/EXPORTS", path]
    else:
        ext = os.path.splitext(path)[1].lower()
        cmd = ["nm", "-D", "--defined-only", path] if ext != ".a" else ["nm", "--defined-only", path]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              encoding="utf-8", check=True)
    except subprocess.CalledProcessError as e:
        return []

    for line in proc.stdout.splitlines():
        # split on whitespace
        parts = line.strip().split()
        if not parts:
            continue

        # scan for the first token that looks like a symbol
        for token in parts:
            # skip dll names, section headers, numbers, etc.
            low = token.lower()
            if low.endswith(".dll") or low == "ordinal" or low == "hint" or low == "rva":
                continue
            if IDENTIFIER_WITH_STDCALL.match(token):
                # strip stdcall decoration if you want the undecorated name:
                name = token.split("@", 1)[0]
                exports.add(name)
                break

    return sorted(exports)


def get_exports_from_map(path: str) -> List[str]:
    exports: Set[str] = set()
    if not os.path.isfile(path):
        return []
    for line in open(path, encoding="utf-8", errors="ignore"):
        m = re.search(r'([A-Za-z_]\w*)$', line.strip())
        if m:
            exports.add(m.group(1))
    return sorted(exports)

def get_exports_from_def(path: str) -> List[str]:
    exports: Set[str] = set()
    if not os.path.isfile(path):
        return []
    in_section = False
    for raw in open(path, encoding="utf-8", errors="ignore"):
        line = raw.strip()
        if not line:
            continue
        if not in_section and line.upper().startswith("EXPORTS"):
            in_section = True
            for sym in line.split()[1:]:
                if IDENTIFIER_RE.match(sym):
                    exports.add(sym)
            continue
        if in_section:
            if line.upper().startswith(("LIBRARY", "SECTIONS")):
                break
            sym = line.split()[0]
            if IDENTIFIER_RE.match(sym):
                exports.add(sym)
    return sorted(exports)

def get_exports_from_export_macros(
    headers: List[str], macros: List[str]
) -> List[str]:
    exports: Set[str] = set()
    if not macros:
        return []
    pattern = re.compile(
        rf'\b(?:{"|".join(re.escape(m) for m in macros)})\b\s+([A-Za-z_]\w*)'
    )
    for hdr in headers:
        try:
            text = open(hdr, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in pattern.finditer(text):
            exports.add(m.group(1))
    return sorted(exports)

def get_exports_from_extern_c_blocks(headers: List[str]) -> List[str]:
    exports: Set[str] = set()
    block_pat = re.compile(r'extern\s+"C"\s*\{(?P<body>.*?)\}', re.DOTALL)
    for hdr in headers:
        try:
            text = open(hdr, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for blk in block_pat.finditer(text):
            for fn in FUNC_RE.finditer(blk.group("body")):
                exports.add(fn.group("name"))
    return sorted(exports)

def get_exports_from_header_heuristics(
    headers: List[str], prefixes: List[str]
) -> List[str]:
    exports: Set[str] = set()
    if not prefixes:
        return []
    for hdr in headers:
        try:
            text = open(hdr, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for fn in FUNC_RE.finditer(text):
            name = fn.group("name")
            if any(name.startswith(pref) for pref in prefixes):
                exports.add(name)
    return sorted(exports)

def get_exports_from_object_files(dirs: List[str]) -> List[str]:
    exports: Set[str] = set()
    for od in dirs or []:
        if not os.path.isdir(od):
            continue
        for root, _, files in os.walk(od):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                path = os.path.join(root, f)
                if sys.platform.startswith("win") and ext == ".obj":
                    cmd = ["dumpbin", "/symbols", path]
                elif ext == ".o":
                    cmd = ["nm", "--defined-only", path]
                else:
                    continue
                try:
                    out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
                except Exception:
                    continue
                for line in out.splitlines():
                    parts = line.split()
                    if parts and IDENTIFIER_RE.match(parts[-1]):
                        exports.add(parts[-1])
    return sorted(exports)

def get_exports_from_cmake(cmake_files: List[str]) -> List[str]:
    exports: Set[str] = set()
    install_pat = re.compile(r'install\s*\(\s*EXPORTS\s+([^)]+)\)', re.IGNORECASE)
    target_pat  = re.compile(r'target_exported_symbols\s*\(\s*\w+\s+([^)]+)\)', re.IGNORECASE)
    for cm in cmake_files or []:
        try:
            text = open(cm, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for pat in (install_pat, target_pat):
            for m in pat.finditer(text):
                for name in re.split(r'[\s;]+', m.group(1).strip()):
                    if IDENTIFIER_RE.match(name):
                        exports.add(name)
    return sorted(exports)

def get_exports_from_config(config: Dict) -> List[str]:
    return [
        name for name in config.get("exports", [])
        if IDENTIFIER_RE.match(name)
    ]

def discover_exported_symbols(
    config: Dict, parse_result: Dict, sources: Dict
) -> List[str]:
    verbose = config.get("verbose_logging", False)
    if verbose:
        print("[GMBridge][discover_exports] Starting discover_exported_symbols()")

    parsed = [fn["name"] for fn in parse_result.get("functions", [])]
    libs   = sources.get("library_files", [])
    if verbose:
        print(f"[GMBridge][discover_exports]  Parsed functions: {len(parsed)}")
        print(f"[GMBridge][discover_exports]  Library files: {libs}")

    # 1) Intersection of parsed vs binary
    bin_exports: Set[str] = set()
    for lib in libs:
        full = os.path.normpath(os.path.join(os.getcwd(), lib))
        if verbose:
            print(f"[GMBridge][discover_exports]  Scanning binary: {full}")
        found = get_exports_from_binary(full)
        if verbose:
            print(f"[GMBridge][discover_exports]   → Found {len(found)} symbols")
        bin_exports.update(found)

    bin_list = sorted(bin_exports)
    if parsed and bin_list:
        intersect = [f for f in parsed if f in bin_list]
        if intersect:
            if verbose:
                print(f"[GMBridge][discover_exports]  Using parsed∩binary: {len(intersect)} symbols")
            return intersect

    # 2) Binary exports alone
    if bin_list:
        if verbose:
            print(f"[GMBridge][discover_exports]  Using binary exports alone: {len(bin_list)} symbols")
        return bin_list

    # 3) Map files
    for mf in sources.get("map_files", []):
        if verbose:
            print(f"[GMBridge][discover_exports]  Scanning map file: {mf}")
        result = get_exports_from_map(mf)
        if result:
            if verbose:
                print(f"[GMBridge][discover_exports]   → Found {len(result)} from map")
            return result

    # 4) DEF files
    for df in sources.get("def_files", []):
        if verbose:
            print(f"[GMBridge][discover_exports]  Scanning DEF file: {df}")
        result = get_exports_from_def(df)
        if result:
            if verbose:
                print(f"[GMBridge][discover_exports]   → Found {len(result)} from def")
            return result

    # 5) Export macros
    headers = config.get("include_files", [])
    macros  = config.get("export_macros", [])
    if verbose:
        print(f"[GMBridge][discover_exports]  Scanning headers for macros: {macros}")
    result = get_exports_from_export_macros(headers, macros)
    if result:
        if verbose:
            print(f"[GMBridge][discover_exports]   → Found {len(result)} via macros")
        return result

    # 6) extern "C" blocks
    if verbose:
        print("[GMBridge][discover_exports]  Scanning extern \"C\" blocks")
    result = get_exports_from_extern_c_blocks(headers)
    if result:
        if verbose:
            print(f"[GMBridge][discover_exports]   → Found {len(result)} via extern C")
        return result

    # 7) Header-prefix heuristics
    prefixes = config.get("export_prefixes", [])
    if verbose:
        print(f"[GMBridge][discover_exports]  Scanning headers for prefixes: {prefixes}")
    result = get_exports_from_header_heuristics(headers, prefixes)
    if result:
        if verbose:
            print(f"[GMBridge][discover_exports]   → Found {len(result)} via prefixes")
        return result

    # 8) Object-file symbols
    object_dirs = sources.get("object_dirs", [])
    if verbose:
        print(f"[GMBridge][discover_exports]  Scanning object dirs: {object_dirs}")
    result = get_exports_from_object_files(object_dirs)
    if result:
        if verbose:
            print(f"[GMBridge][discover_exports]   → Found {len(result)} via object files")
        return result

    # 9) CMake exports
    cmake_files = sources.get("cmake_files", [])
    if verbose:
        print(f"[GMBridge][discover_exports]  Scanning CMake scripts: {cmake_files}")
    result = get_exports_from_cmake(cmake_files)
    if result:
        if verbose:
            print(f"[GMBridge][discover_exports]   → Found {len(result)} via CMake")
        return result

    # 10) Manual fallback
    if verbose:
        print("[GMBridge][discover_exports]  Falling back to config[\"exports\"]")
    result = get_exports_from_config(config)
    if verbose:
        print(f"[GMBridge][discover_exports]   → Found {len(result)} via config")
    return result
