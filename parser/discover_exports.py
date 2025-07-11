import os
import re
import sys
import subprocess
from typing import List, Dict, Set
from pathlib import Path

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

def get_exports_from_config(config):
    return [
        name for name in config.get("export_symbols", [])
        if IDENTIFIER_RE.match(name)
    ]

def _extract_and_filter(files, extractor, parsed, verbose, label):
    """
    Run `extractor` on each path in `files`, union the results,
    then if `parsed` is non-empty, return parsed∩collected (if any),
    otherwise return all collected. Returns None if nothing collected.
    """
    collected: Set[str] = set()
    for p in files or []:
        full = os.path.normpath(os.path.join(os.getcwd(), p))
        if verbose:
            print(f"[GMBridge][discover_exports]  Scanning {label}: {full}")
        collected |= set(extractor(full))
    if not collected:
        return None
    # if we parsed some functions, try intersection first
    if parsed:
        inter = [f for f in parsed if f in collected]
        if inter:
            if verbose:
                print(f"[GMBridge][discover_exports]  Using parser {label}: {len(inter)} symbols")
            return inter
    # otherwise return everything we found
    lst = sorted(collected)
    if verbose:
        print(f"[GMBridge][discover_exports]  Using {label} exports alone: {len(lst)} symbols")
    return lst

def get_exports_from_binary(path):
    exports = set()
    if not os.path.isfile(path):
        print(f"[GMBridge][discover_exports]  File not found: {path}")
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

def get_exports_from_map(path):
    exports = set()
    if not os.path.isfile(path):
        return []
    for line in open(path, encoding="utf-8", errors="ignore"):
        m = re.search(r'([A-Za-z_]\w*)$', line.strip())
        if m:
            exports.add(m.group(1))
    return sorted(exports)

def get_exports_from_def(path):
    exports = set()
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

def get_exports_from_object_files(dirs):
    """
    Scan object files in the given directories for exported symbols.
    This function looks for `.obj` files on Windows and `.o` files on other platforms.
    It uses `dumpbin` on Windows and `nm` on Unix-like systems to extract symbols.
    """

    exports = set()
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

def get_exports_from_cmake(cmake_files):
    exports = set()
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

def get_exports_from_export_macros(headers, macros):
    exports = set()
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

def get_exports_from_extern_c_blocks(headers):
    exports = set()
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

def get_exports_from_header_heuristics(headers, prefixes):
    exports = set()
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




def discover_exported_symbols(config, parse_result, sources, expanded_headers, target):
    verbose = config.get("verbose_logging", False)
    if verbose:
        print("[GMBridge][discover_exports] Starting discover_exported_symbols()")

    plat = target.split("-", 1)[0]

    # 1) USER OVERRIDE: config["export_symbols"]
    manual = get_exports_from_config(config)
    if manual:
        if verbose:
            print(f"[GMBridge][discover_exports] Using {len(manual)} user-specified exports")
        return manual

    # 2) CONFIG-SUPPLIED FILES: config["export_files"]
    export_files = config.get("export_files", [])
    if export_files:
        collected = set()
        if verbose:
            print(f"[GMBridge][discover_exports]  Parsing {len(export_files)} export files from config")
        for ef in export_files:
            p = Path(ef)
            if not p.exists():
                if verbose: print(f"   – skip missing {p}")
                continue
            ext = p.suffix.lower()
            if ext == ".lib":
                collected |= set(get_exports_from_binary(str(p)))
            elif ext == ".map":
                collected |= set(get_exports_from_map(str(p)))
            elif ext == ".def":
                collected |= set(get_exports_from_def(str(p)))
            elif ext in (".o", ".obj"):
                collected |= set(get_exports_from_object_files([str(p.parent)]))
            elif ext in (".cmake",):
                collected |= set(get_exports_from_cmake([str(p)]))
            # … you can add other extensions here …
        if collected:
            lst = sorted(collected)
            if verbose:
                print(f"[GMBridge][discover_exports]  → Found {len(lst)} via config export_files")
            return lst

    # 2b) FALLBACK TO SOURCES LISTS: library_files, map_files, def_files, object_files, cmake_files
    #    same approach, but using what we auto-discovered
    if verbose:
        print("[GMBridge][discover_exports] No config export_files, trying auto-discovered source lists")
    
    # 2) Try binary-style files in this order, via our helper:
    parsed_set = {fn["name"] for fn in parse_result.get("functions", [])}

    # 2a) .lib / shared-object exports
    result = _extract_and_filter(
        sources.get("library_files", []),
        get_exports_from_binary,
        parsed_set,
        verbose,
        "binary"
    )
    if result: return result

    # 2b) .map files
    result = _extract_and_filter(
        sources.get("map_files", []),
        get_exports_from_map,
        parsed_set,
        verbose,
        "map"
    )
    if result: return result

    # 2c) .def files
    result = _extract_and_filter(
        sources.get("def_files", []),
        get_exports_from_def,
        parsed_set,
        verbose,
        "def"
    )
    if result: return result

    #2d) .obj files
    result = _extract_and_filter(
        sources.get("object_files", []),
        get_exports_from_binary,  # dumpbin or nm works on .obj too
        parsed_set,
        verbose,
        "object"
    )
    if result: return result

    # 2e) .cmake scripts
    result = _extract_and_filter(
        sources.get("cmake_files", []),
        get_exports_from_cmake,
        parsed_set,
        verbose,
        "CMake"
    )
    if result: return result

    # 3) PREPROCESSED HEADERS: patterns in config["export_patterns"][plat]
    patterns = config.get("export_patterns", {}).get(plat, [])
    if patterns and expanded_headers:
        if verbose:
            print(f"[GMBridge][discover_exports]  Scanning expanded headers with {len(patterns)} patterns")
        found = set()
        regexes = [re.compile(p) for p in patterns]
        for hdr, content in expanded_headers.items():
            for rx in regexes:
                for m in rx.finditer(content):
                    tail = content[m.end():]
                    nm = re.match(r'\s*([A-Za-z_]\w*)\s*\(', tail)
                    if nm:
                        found.add(nm.group(1))
        if found:
            lst = sorted(found)
            if verbose:
                print(f"[GMBridge][discover_exports]  → Found {len(lst)} symbols via preprocessed scan")
            return lst

    # 4) FINAL FALLBACK: header heuristics (macros, extern "C", prefixes)
    headers = config.get("include_files", [])
    # macros
    macros = config.get("export_macros", [])
    if macros:
        if verbose:
            print(f"[GMBridge][discover_exports]  Scanning headers for macros: {macros}")
        r = get_exports_from_export_macros(headers, macros)
        if r:
            if verbose:
                print(f"[GMBridge][discover_exports]   → Found {len(r)} via macros")
            return r

    # extern "C"
    if verbose:
        print('[GMBridge][discover_exports]  Scanning extern "C" blocks')
    r = get_exports_from_extern_c_blocks(headers)
    if r:
        if verbose:
            print(f"[GMBridge][discover_exports]   → Found {len(r)} via extern C")
        return r

    # prefix heuristics
    prefixes = config.get("export_prefixes", [])
    if prefixes:
        if verbose:
            print(f"[GMBridge][discover_exports]  Scanning headers for prefixes: {prefixes}")
        r = get_exports_from_header_heuristics(headers, prefixes)
        if r:
            if verbose:
                print(f"[GMBridge][discover_exports]   → Found {len(r)} via prefixes")
            return r

    # give up
    if verbose:
        print("[GMBridge][discover_exports]  No exports found, returning empty list")
    return []