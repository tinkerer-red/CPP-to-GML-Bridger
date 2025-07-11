import os
import re
import sys
import json
import shutil
import subprocess
from pathlib import Path

from parser.utils import classify_c_type

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
ENUM_RE = re.compile(r'typedef\s+enum\s+(\w+)?\s*{([^}]+)}\s*(\w+)?\s*;', re.DOTALL)
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

def flatten_parse_data(all_results: dict) -> dict:
    """
    Merge multiple per-file parse results into one unified parse_result.
    all_results is expected to have the shape:
        { "files": { filename1: parse_result1, filename2: parse_result2, … } }
    Returns a dict with keys:
        "functions", "typedef_map", "struct_fields",
        "function_ptr_aliases", "enums", "constants", "using_map"
    """
    unified = {
        "functions":            [],
        "typedef_map":          {},
        "struct_fields":        {},
        "function_ptr_aliases": [],
        "enums":                {},
        "constants":            {},
        "using_map":            {}
    }

    for file_res in all_results.get("files", {}).values():
        # 1) append all functions
        unified["functions"].extend(file_res.get("functions", []))

        # 2) merge all maps (later files win on name collisions)
        unified["typedef_map"].update(file_res.get("typedef_map", {}))
        unified["struct_fields"].update(file_res.get("struct_fields", {}))
        unified["enums"].update(file_res.get("enums", {}))
        unified["constants"].update(file_res.get("constants", {}))
        unified["using_map"].update(file_res.get("using_map", {}))

        # 3) collect all function‐pointer aliases
        unified["function_ptr_aliases"].extend(file_res.get("function_ptr_aliases", []))

    # dedupe & sort the aliases
    unified["function_ptr_aliases"] = sorted(set(unified["function_ptr_aliases"]))

    return unified


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

def parse_header(config):
    """
    Fully preprocesses and parses *any* C/C++ header.
    """
    namespace = config.get("namespace", "")
    
    header_files = [Path(p).as_posix() for p in config["include_files"]]
    # throw error for missing files
    for hdr in header_files:
        if not os.path.isfile(hdr):
            raise FileNotFoundError(f"[GMBridge] include_files entry not found: '{hdr}'")

    # Derive include paths purely from the headers we’re parsing:
    include_files = [os.path.abspath(p) for p in header_files]
    include_folders = [os.path.dirname(p) for p in include_files]
    
    # --- gather any user‐requested defines ---
    defines       = config.get("preprocessor_defines", [])
    define_flags  = []
    for d in defines:
        if sys.platform.startswith("win"):
            define_flags.append(f"/D{d}")
        else:
            define_flags.append(f"-D{d}")

    all_results = {"files": {}}

    for hdr in header_files:
        # 2) Pick a preprocessor (user override first, then platform defaults)
        candidates = []
        if "preprocessor" in config:
            candidates.append(config["preprocessor"])
        if sys.platform.startswith("win"):
            candidates += [
                ["clang", "-E", "-dD", "-P"],
                ["gcc",   "-E", "-dD", "-P"],
                ["cl", "/E", "/nologo"],
            ]
        else:
            candidates += [
                ["cpp", "-P", "-dD", "-std=c99"],   # <-- preserve conditionals
                ["clang", "-E", "-dD", "-P"],
                ["gcc", "-E", "-dD", "-P"]
            ]


        cpp_cmd = None
        for cmd in candidates:
            tool = cmd[0]
            path = shutil.which(tool)
            print(f"[GMBridge] Checking for preprocessor '{tool}': {path}")
            if path:
                cpp_cmd = cmd + define_flags
                print(f"[GMBridge] → Using preprocessor: {cmd!r} (resolved to {path})")
                break

        if cpp_cmd is None:
            tried = ", ".join(c[0] for c in candidates)
            raise RuntimeError(f"No C preprocessor found. Tried: {tried}")

        # 3) Decide include-flag syntax
        inc_flag = "/I" if cpp_cmd[0].lower() == "cl" else "-I"

        # 4) Build and log the full command with absolute paths
        full_cmd = cpp_cmd + [f"{inc_flag}{folder}" for folder in include_folders] + include_files
        print(f"[GMBridge] Running preprocessor: {full_cmd!r}")

        # 5) Run it, capturing stdout for parsing
        try:
            proc = subprocess.run(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                encoding="utf-8"
            )
            content = proc.stdout

        except subprocess.CalledProcessError as err:
            print(f"[GMBridge] Preprocessor failed (exit {err.returncode}). stderr:\n{err.stderr}")
            raise



        # 2) Collapse continuations
        content = LINE_CONTINUATION_RE.sub(' ', content)

        parse_result = {
            "functions":            [],
            "enums":                {},
            "constants":            {},
            "typedef_map":          {},
            "using_map":            {},
            "struct_fields":        {},
            "function_ptr_aliases": []
        }

        # 3) Function-pointer typedefs
        ptr_aliases = {m.group("alias") for m in FUNC_PTR_RE.finditer(content)}
        parse_result["function_ptr_aliases"] = sorted(ptr_aliases)

        # 4) Enums
        for m in ENUM_RE.finditer(content):
            raw, body, alias = m.group(1), m.group(2), m.group(3)
            name = alias or raw or "unnamed_enum"
            entries, val = {}, 0
            for line in body.split(','):
                line = line.strip()
                if not line: continue
                if '=' in line:
                    k,v = map(str.strip, line.split('=',1))
                    try: val = int(v,0)
                    except: val = 0
                else:
                    k = line
                entries[k] = val; val += 1

            # strip prefixes/suffixes
            short = name[len(namespace):] if name.lower().startswith(namespace.lower()) else name
            pre, suf = get_enum_prefix_suffix_cleanup(entries.keys())
            cleaned = {}
            for k,v in entries.items():
                ck = (k[len(pre):] if pre and k.startswith(pre) else k)
                if suf and ck.endswith(suf): ck = ck[:-len(suf)]
                cleaned[ck] = v
            cleaned["_meta"] = {"namespace":namespace,"short_name":short,"base_prefix":pre,"base_suffix":suf}
            parse_result["enums"][name] = cleaned

        # 5) Constants
        for name, val in CONST_RE.findall(content):
            parse_result["constants"][name] = (val if val.startswith('"') else int(val,0))

        # 6) Typedefs & usings & struct‐handle typedefs
        for full, alias in TYPEDEF_RE.findall(content):
            parse_result["typedef_map"][alias] = full.strip()
        for alias, target in USING_RE.findall(content):
            parse_result["using_map"][alias] = target.strip()
        for struct_name, alias in HANDLE_RE.findall(content):
            # e.g. struct_name="XrSpace", alias="XrSpace"
            parse_result["typedef_map"][alias] = f"struct {struct_name}_T *"
            
        # 7) Structs
        for m in STRUCT_RE.finditer(content):
            name = m.group("name")
            body = m.group("body")
            fields = []
            for line in body.split(';'):
                line = line.strip()
                if not line:
                    continue

                # — Handle comma-separated declarations (e.g. "unsigned short _Byte, _State")
                parts = [p.strip() for p in line.split(',')]
                if len(parts) > 1:
                    # first part has full “type name”
                    decls = [parts[0]]
                    # extract base type (everything before the last space)
                    base, _ = parts[0].rsplit(None, 1)
                    # rebuild the remaining names with that base
                    for extra in parts[1:]:
                        decls.append(f"{base} {extra}")
                else:
                    decls = [line]

                # now parse each small declaration separately
                for decl in decls:
                    am = re.match(r'''
                        (.+?)             # group(1): the raw base type
                        \s+
                        (\**\w+)          # group(2): the field name
                        (?:\s*\[\s*       # optionally an array
                            ([^\]]+)
                        \s*\]
                        )?
                        $
                    ''', decl, re.VERBOSE)
                    if not am:
                        continue

                    raw_base, nm, sz = am.group(1).strip(), am.group(2).strip(), am.group(3)
                    clean_base = re.sub(r'\b[A-Z_][A-Z0-9_]*\b', '', raw_base).replace('  ', ' ').strip()

                    field = {"name": nm, "type": clean_base}
                    if sz is not None:
                        try:
                            field["array_size"] = int(sz)
                        except ValueError:
                            field["array_size"] = sz

                    meta = classify_c_type(parse_result, clean_base, config)
                    field.update(meta)

                    fields.append(field)

            parse_result["struct_fields"][name] = fields


        # 7a) Promote typedef aliases into struct_fields
        def _resolve_type(t):
            seen = set()
            while t in parse_result["typedef_map"] and t not in seen:
                seen.add(t)
                t = parse_result["typedef_map"][t]
            return t

        for alias in list(parse_result["typedef_map"]):
            root = _resolve_type(alias)
            if root in parse_result["struct_fields"]:
                parse_result["struct_fields"][alias] = parse_result["struct_fields"][root]

        # 8) Cleanup
        # Strip calling conventions
        content = re.sub(r'\b__stdcall\b', '', content)
        content = re.sub(r'\b__cdecl\b',   '', content)
        content = re.sub(r'\b__fastcall\b','', content)
        
        # Collapse multi-line prototypes into single lines:
        #   - join any lines that are inside parentheses
        def _collapse_proto(match):
            inner = match.group(1).replace('\n', ' ').strip()
            return "(" + inner + ")"

        # This will find the first "(" up to the matching ")" and flatten interior newlines
        content = re.sub(r'\(\s*(.*?)\s*\)', _collapse_proto, content, flags=re.DOTALL)
        
        # Finally, ensure each prototype ends on its own line
        content = re.sub(r'\)\s*;\s*', ');' + '\n', content)
        
        # Helper: collapse C-style array syntax into pointer + size
        def normalize_array(tp, nm):
            # e.g. "float vals[16]" → ("float*", "vals", "16")
            if '[' in nm and nm.endswith(']'):
                idx      = nm.index('[')
                size     = nm[idx+1:-1]
                nm_clean = nm[:idx]
                tp_ptr   = (tp + '*').strip()
                return tp_ptr, nm_clean, size
            return tp, nm, None
        
        # 9) Functions
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
                # split into type and name
                parts = a.rsplit(' ', 1)
                if len(parts) == 2:
                    tp, nm = parts
                else:
                    tp, nm = parts[0], f"arg{len(arg_list)}"
                
                # normalize C-style arrays → pointers + capture size
                tp, nm, array_size = normalize_array(tp, nm)

                meta = classify_c_type(parse_result, tp, config)

                if array_size is not None:
                    meta["is_ref"]         = True
                    meta["extension_type"] = "string"

                entry = {"name": nm, "type": tp, **meta}
                arg_list.append(entry)

            ret_meta = classify_c_type(parse_result, m.group("ret").strip(), config)
            parse_result["functions"].append({
                "name":        fn_name,
                "return_type": ret_meta["canonical_type"],
                "return_meta": ret_meta,
                "args":        arg_list
            })

        skip_prefixes = config.get("skip_function_prefixes", [])
        if skip_prefixes:
            filtered = []
            for fn in parse_result["functions"]:
                name = fn.get("name", "")
                # if it matches any of the skip-prefixes, drop it
                if any(name.startswith(pref) for pref in skip_prefixes):
                    if config.get("debug", False):
                        print(f"[GMBridge] Skipping function '{name}' (prefix filter)")
                    continue
                filtered.append(fn)
            parse_result["functions"] = filtered

        # If debugging is enabled, dump the preprocessed content
        if config.get("debug", False):
            # Compute a safe filename: <originalbasename>_expanded.h
            base_name = os.path.splitext(os.path.basename(hdr))[0]
            dump_name = f"{base_name}_expanded.h"
            with open(dump_name, "w", encoding="utf-8") as dbg_file:
                dbg_file.write(content)
            print(f"[GMBridge] Wrote expanded macros to: {dump_name}")

        all_results["files"][hdr] = parse_result

    
    parse_result = flatten_parse_data(all_results)

    # If the user supplied one or more .lib files, extract their exported symbols
    exports = []
    for lib_path_str in config.get("libraries", []):
        lib_path = Path(lib_path_str)
        print(f"[GMBridge] Dumping exports from {lib_path!r}")
        try:
            proc = subprocess.run(
                ["dumpbin", "/EXPORTS", str(lib_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", check=True
            )
        except subprocess.CalledProcessError as err:
            print(f"[GMBridge] dumpbin failed on {lib_path!r}: {err.stderr.strip()}")
            continue

        for line in proc.stdout.splitlines():
            m = re.match(r'^\s+([A-Za-z_]\w+)$', line)
            if m:
                exports.append(m.group(1))
    
    parse_result["exports"] = exports

    
    # Report counts before pruning
    funcs = parse_result.get("functions", [])
    print(f"[GMBridge] Parsed {len(funcs)} functions, found {len(exports)} exports")

    # Now prune to intersection: only keep functions whose names are in exports,
    # and only keep export names that correspond to a parsed function.
    funcs = parse_result.get("functions", [])
    if parse_result["exports"]:
        pruned_funcs = [fn for fn in funcs if fn["name"] in parse_result["exports"]]
        pruned_exports = [name for name in parse_result["exports"]
                          if any(fn["name"] == name for fn in pruned_funcs)]
        parse_result["functions"] = pruned_funcs
        parse_result["exports"]   = pruned_exports

    # Report counts after pruning
    print(f"[GMBridge] Kept {len(parse_result['functions'])} functions, {len(parse_result['exports'])} exports")

    
    if config.get("debug"):
        with open("debug_parser.json","w",encoding="utf-8") as f:
            json.dump(parse_result, f, indent=2)

    return parse_result
