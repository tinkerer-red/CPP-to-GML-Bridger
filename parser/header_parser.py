import os
import re
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Set, Dict, Any

from parser.utils import classify_c_type, flatten_parse_data
from parser.primitives import (
    SAFE_SIGNED_INTS,
    SAFE_UNSIGNED_INTS,
    UNSAFE_INTS,
    FLOAT_TYPES,
    BOOL_TYPES
)

def find_reachable_types(supplied_function_names, parse_data):
    """
    Given a list of function names and the full parse_data map (with keys
    'functions' and 'struct_fields'), return all canonical types reachable
    from those functions via their return values, arguments, and any nested
    struct fields.
    """
    # 1) Collect initial set of types from return values and arguments
    reachable_types = set()
    for function_entry in parse_data.get("functions", []):
        function_name = function_entry.get("name")
        if function_name in supplied_function_names:
            # return value
            return_meta = function_entry.get("return_meta", {})
            return_type = return_meta.get("canonical_type")
            if return_type:
                reachable_types.add(return_type)
            # arguments
            for arg_meta in function_entry.get("args", []):
                arg_type = arg_meta.get("canonical_type")
                if arg_type:
                    reachable_types.add(arg_type)

    # 2) Iteratively expand via struct_fields until no new types appear
    struct_fields_map = parse_data.get("struct_fields", {})
    grew = True
    while grew:
        before_count = len(reachable_types)
        # scan each type we currently know
        for current_type in list(reachable_types):
            # if it's a struct, gather its fields' types
            fields = struct_fields_map.get(current_type, [])
            for field_meta in fields:
                field_type = field_meta.get("canonical_type")
                if field_type:
                    reachable_types.add(field_type)
        after_count = len(reachable_types)
        grew = (after_count > before_count)

    # 3) Return as a plain list
    return list(reachable_types)

# ——— Module-scope regexes ———
LINE_CONTINUATION_RE = re.compile(r'\\\r?\n\s*')
# We no longer need MACRO_DEF_RE or manual expand_macros once we invoke cpp.
FUNC_PTR_RE = re.compile(r'''
    typedef
    \s+ (?P<ret>.*?)           # return type
    \(\s* (?:[^(]*?) \* \s*     # skip qualifiers then "*"
    (?P<alias>\w+)\)\s*        # alias name
    \((?P<args>[^)]*)\)\s*;     # parameter list
''', re.VERBOSE | re.DOTALL)
ENUM_RE = re.compile(r'''
    \benum
    (?:\s+(?P<alias>[A-Za-z_]\w*))?   # optional name
    \s*
    \{
      (?P<body>[^}]*?)                # everything up to the closing brace
    \}
''', re.VERBOSE)
CONST_RE = re.compile(
    r'^#define\s+([A-Za-z_]\w*)\s+("(?:[^"\\]|\\.)*"|-?\d+|0x[0-9A-Fa-f]+)\s*$',
    re.MULTILINE
)
TYPEDEF_RE = re.compile(r'typedef\s+([^\s]+(?:\s+\w+)*)\s+(\w+)\s*;')
USING_RE   = re.compile(r'using\s+(\w+)\s*=\s*([^;]+);')
HANDLE_RE = re.compile(r'typedef\s+struct\s+(\w+)_T\s*\*\s*(\w+);')
STRUCT_RE  = re.compile(
    r'\btypedef\s+struct\b'
    r'(?:\s+[A-Za-z_]\w*)*'
    r'\s*\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}'
    r'\s*(?P<name>[A-Za-z_]\w*)\s*;',
    re.DOTALL
)

# Generic function-declaration regex (drops XRAPI specifics)
FUNC_RE = re.compile(
    r'^\s*'                            # start of line, maybe whitespace
    r'(?P<ret>[A-Za-z_]\w*(?:\s+[\w\*\:<>]+)*)'  # return type (no newlines!)
    r'\s+'                             # at least one space
    r'(?P<name>[A-Za-z_]\w*)'          # function name
    r'\s*\('                           # opening paren
    r'(?P<args>[^)]*)'                 # argument list (no parentheses inside)
    r'\)\s*;'                          # closing paren + semicolon
    , re.MULTILINE
)


def strip_common_prefix(enum_name, entries):
    parts = [k.split('_') for k in entries if '_' in k]
    common = []
    for i in zip(*parts):
        if all(p == i[0] for p in i):
            common.append(i[0])
        else:
            break
    return '_'.join(common) + '_' if common else ''

def get_enum_prefix_suffix_cleanup(enum_keys):
    keys = list(enum_keys)
    prefix = strip_common_prefix("", keys)
    suffix = None
    suffixes = [k.split('_')[-1] for k in keys if '_' in k]
    if len(suffixes) == len(keys) and all(s == suffixes[0] for s in suffixes):
        sfx = suffixes[0]
        if sfx.isupper() and len(sfx) >= 2:
            suffix = f"_{sfx}"
    return prefix, suffix


def parse_headers(config, sources, defines, expanded_headers):
    """
    Parses the public headers using pre-expanded contents.

    Args:
      - config: loaded config dict
      - sources: result of discover_all_sources()
      - defines: compile-time defines for this target
      - expanded_headers: map of absolute header path → preprocessed content

    Returns:
      A flattened parse_result dict with keys:
        functions, enums, constants, typedef_map, using_map,
        struct_fields, function_ptr_aliases
    """
    verbose = config.get("verbose_logging", False)
    project_root = Path.cwd()
    input_root   = project_root / "input"
    output_root  = project_root / "output"
    

    # 1) Public headers list
    header_list = config.get("include_files", [])
    if verbose:
        print(f"[GMBridge][parse_headers]  Public headers: {header_list}")

    # verify each header exists on disk and in expanded_headers
    abs_headers = []
    for hdr in header_list:
        hdr_path = (project_root / hdr).resolve()
        if not hdr_path.is_file():
            raise FileNotFoundError(f"[GMBridge][parse_headers] Missing public header: {hdr_path}")
        abs_headers.append(str(hdr_path))

    # 2) Build include directories (for classify_c_type, if needed)
    include_dirs: Set[str] = set()
    for h in sources.get("header_files", []):
        include_dirs.add(str(Path(h).parent))
    for extra in config.get("extra_includes", []):
        include_dirs.add(str((project_root / extra).resolve()))
    if verbose:
        print("[GMBridge][parse_headers]  Include directories:")
        for inc in sorted(include_dirs):
            print(f"    {inc}")

    all_results = {"files": {}}

    # 3) Iterate each header and parse its expanded content
    for abs_hdr in abs_headers:
        content = expanded_headers.get(abs_hdr)
        if content is None:
            raise RuntimeError(f"[GMBridge][parse_headers] No expanded content for: {abs_hdr}")

        # normalize line continuations & whitespace
        content = LINE_CONTINUATION_RE.sub(" ", content)
        content = re.sub(r'\s+', ' ', content)

        # per-file result containers
        file_result = {
            "functions": [],
            "enums": {},
            "constants": {},
            "typedef_map": {},
            "using_map": {},
            "struct_fields": {},
            "function_ptr_aliases": []
        }

        # 3a) Function-pointer typedefs
        file_result["function_ptr_aliases"] = sorted({
            m.group("alias") for m in FUNC_PTR_RE.finditer(content)
        })
        
        # 3b) Enums
        for match in ENUM_RE.finditer(content):
            groups = match.groupdict()
            body_text = groups.get("body", "")
            name_text = groups.get("alias") or "unnamed_enum"

            entries = {}
            value_counter = 0
            for element in body_text.split(","):
                element = element.strip()
                if not element:
                    continue
                if "=" in element:
                    key_name, raw_value = map(str.strip, element.split("=", 1))
                    try:
                        value_counter = int(raw_value, 0)
                    except ValueError:
                        value_counter = 0
                else:
                    key_name = element
                entries[key_name] = value_counter
                value_counter += 1

            file_result["enums"][name_text] = entries

        # 3c) Constants
        for name, val in CONST_RE.findall(content):
            file_result["constants"][name] = (
                val if val.startswith('"') else int(val, 0)
            )

        # 3d) Typedefs & using & handle typedefs
        for full, alias in TYPEDEF_RE.findall(content):
            file_result["typedef_map"][alias] = full.strip()
        for alias, target in USING_RE.findall(content):
            file_result["using_map"][alias] = target.strip()
        for struct_name, alias in HANDLE_RE.findall(content):
            file_result["typedef_map"][alias] = f"struct {struct_name}_T *"

        # 3e) Struct definitions
        for m in STRUCT_RE.finditer(content):
            name = m.group("name")
            body = m.group("body")
            fields = []
            for decl in filter(None, map(str.strip, body.split(";"))):
                # split comma-decls: e.g. "int a, b"
                parts = [p.strip() for p in decl.split(",")]
                if len(parts) > 1:
                    base = parts[0].rsplit(None, 1)[0]
                    parts = [parts[0]] + [f"{base} {p}" for p in parts[1:]]
                for d in parts:
                    am = re.match(
                        r'(.+?)\s+(\**\w+)(?:\s*\[\s*([^\]]+)\s*\])?$', d
                    )
                    if not am:
                        continue

                    raw_base    = am.group(1).strip()
                    nm          = am.group(2).strip()
                    sz          = am.group(3)

                    # Preserve full declarator for classification
                    declared    = raw_base
                    user_type   = declared

                    field = {
                        "name": nm,
                        "type": user_type,
                        "declared_type": declared
                    }

                    if sz is not None:
                        try:
                            field["array_size"] = int(sz)
                        except ValueError:
                            field["array_size"] = sz

                    # Classify based on the full declarator
                    meta = classify_c_type(file_result, declared, config)

                    # Normalize canonical_type to the raw struct name
                    underlying = re.sub(r'(?:\bconst\b\s*)|\*', '', declared).strip()
                    meta["canonical_type"] = underlying

                    field.update(meta)
                    fields.append(field)

            file_result["struct_fields"][name] = fields

        # promote typedef aliases for structs
        def _resolve(t):
            seen = set()
            while t in file_result["typedef_map"] and t not in seen:
                seen.add(t)
                t = file_result["typedef_map"][t]
            return t
        for alias in list(file_result["typedef_map"]):
            root = _resolve(alias)
            if root in file_result["struct_fields"]:
                file_result["struct_fields"][alias] = file_result["struct_fields"][root]

        # 3f) Strip calling conventions
        content = re.sub(r'\b__stdcall\b|\b__cdecl\b|\b__fastcall\b', '', content)

        # collapse prototypes to single lines
        def _collapse(m):
            return "(" + m.group(1).replace('\n', ' ').strip() + ")"
        content = re.sub(r'\(\s*(.*?)\s*\)', _collapse, content, flags=re.DOTALL)
        content = re.sub(r'\)\s*;\s*', ');\n', content)

        # 3g) Functions
        for m in FUNC_RE.finditer(content):
            fn_name = m.group("name")
            raw_args = m.group("args").strip()
            # split args by commas *outside* nested angle brackets or parentheses:
            args = re.split(r',\s*(?![^<]*>)', raw_args) if raw_args else []
            arg_list = []
            for a in args:
                a = a.strip()
                if not a or a.lower() == "void":
                    continue
                parts = a.rsplit(" ", 1)
                tp, nm = (parts if len(parts)==2 else (parts[0], f"arg{len(arg_list)}"))
                # normalize C arrays
                array_size = None
                if "[" in nm and nm.endswith("]"):
                    idx = nm.index("[")
                    array_size = nm[idx+1:-1]
                    nm = nm[:idx]
                    tp += "*"
                meta = classify_c_type(file_result, tp, config)
                if array_size is not None:
                    meta["is_ref"]         = True
                    meta["extension_type"] = "string"

                # --- Unsafe number override ---
                canon = meta.get("canonical_type", "").lower()
                if canon in UNSAFE_INTS:
                    meta["extension_type"] = "string"
                    meta["requires_string_wrapper"] = True

                entry = {"name": nm, "type": tp, **meta}
                arg_list.append(entry)

            # Detect "needs stringification" for GML if >4 mixed args
            arg_types = [arg["extension_type"] for arg in arg_list]
            if len(arg_list) > 4 and "string" in arg_types and "double" in arg_types:
                for arg in arg_list:
                    if arg["extension_type"] == "double":
                        arg["force_string_wrapper"] = True

            ret_meta = classify_c_type(file_result, m.group("ret").strip(), config)
            file_result["functions"].append({
                "name":        fn_name,
                "return_type": ret_meta["canonical_type"],
                "return_meta": ret_meta,
                "args":        arg_list
            })

        # skip by prefix if configured
        skips = config.get("skip_function_prefixes", [])
        if skips:
            file_result["functions"] = [
                fn for fn in file_result["functions"]
                if not any(fn["name"].startswith(pref) for pref in skips)
            ]

        all_results["files"][abs_hdr] = file_result

        if verbose:
            print(f"[GMBridge][parse_headers]    → Parsed '{Path(abs_hdr).name}': "
                  f"{len(file_result['functions'])} funcs, "
                  f"{len(file_result['struct_fields'])} structs")

    # 4) Merge per-file data into one parse_result
    parse_result = flatten_parse_data(all_results)

    # ——— NEW: Compute reachable types from the functions we actually exposed ———
    # 4a) Gather the list of function names we parsed
    function_names = [fn["name"] for fn in parse_result["functions"]]
    # 4b) Feed them plus the full parse_result into your reachability routine
    reachable_types = find_reachable_types(function_names, parse_result)
    # 4c) Stash it on the parse_result for downstream use
    parse_result["reachable_types"] = reachable_types

    if verbose:
        print(f"[GMBridge][parse_headers]   Reachable types: {reachable_types}")
    
    if verbose:
        print(f"[GMBridge][parse_headers] Done: "
              f"{len(parse_result['functions'])} total funcs, "
              f"{len(parse_result['struct_fields'])} total structs")

    if config.get("debug"):
        with open("debug_parser.json", "w", encoding="utf-8") as f:
            json.dump(parse_result, f, indent=2)
        if verbose:
            print("[GMBridge][parse_headers] Wrote debug_parser.json")

    return parse_result
