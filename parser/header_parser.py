import os
import re
import sys
import json
import shutil
import subprocess
from pathlib import Path

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

def classify_c_type(parse_result, c_type, config):
    """
    Given a raw C type (possibly via typedef/using), classify it:
    - is_ref: opaque handle
    - is_unsupported_numeric: big integer round-trip
    - is_standard_numeric: float/int32/bool
    - extension_type: "string" or "double"
    """
    typedef_map      = parse_result["typedef_map"]
    using_map        = parse_result["using_map"]
    known_structs    = set(parse_result["struct_fields"].keys())
    function_ptrs    = set(parse_result["function_ptr_aliases"])
    enum_names       = set(parse_result["enums"].keys())

    def resolve_full(name):
        seen = set()
        t = name
        # chase using and typedef chains
        while True:
            if t in using_map and t not in seen:
                seen.add(t)
                t = using_map[t]
                continue
            if t in typedef_map and t not in seen:
                seen.add(t)
                t = typedef_map[t]
                continue
            break
        return t

    cleaned = re.sub(r'\bextern\b\s*', '', c_type, flags=re.IGNORECASE)

    original = cleaned.strip()
    outer    = resolve_full(original)
    # peel const & pointers
    has_const   = outer.startswith("const ")
    has_ptr     = outer.endswith("*")
    no_const    = re.sub(r'^const\s+', '', outer).rstrip('*').strip()
    canonical   = resolve_full(no_const).strip()

    rec = {
        "declared_type": original,
        "base_type":     no_const,
        "canonical_type": canonical,
        "has_const":     has_const,
        "has_pointer":   has_ptr,
        "is_enum":       no_const in enum_names,
        "is_struct":     no_const in known_structs,
        "is_function_ptr": outer in function_ptrs,
        "is_standard_numeric": False,
        "is_unsupported_numeric": False,
        "is_ref": False,
        "extension_type": ""
    }

    # 1) Pointers
    if has_ptr or rec["is_struct"] or rec["is_function_ptr"]:
        rec["is_ref"] = True
        rec["extension_type"] = "string"
        return rec
    
    # 2) Any alias of a big integer *where the alias name differs* → handle
    big_ints = {"int64_t","uint64_t","size_t","uintptr_t"}
    if canonical in big_ints and original != canonical:
        rec["is_ref"] = True
        rec["extension_type"] = "string"
        return rec

    # 3) Raw big integers → strings
    if canonical in big_ints:
        rec["is_unsupported_numeric"] = True
        rec["extension_type"] = "string"
        return rec

    # 4) Enums → double
    if rec["is_enum"]:
        rec["is_standard_numeric"] = True
        rec["extension_type"] = "double"
        return rec

    # 0) Void‐returning functions → no bridge return value
    if canonical == "void":
        rec["extension_type"] = "void"
        return rec
    
    # 5) Everything else numeric → double
    rec["is_standard_numeric"] = True
    rec["extension_type"] = "double"
    return rec

def parse_headers(config, sources, defines):
    """
    Preprocesses and parses the public headers, using:
      - config["include_files"]   : list of headers to process
      - defines                    : compile-time defines for this target
      - sources                    : output of discover_all_sources, for include dirs

    Returns a parse_result dict with:
      - functions, enums, constants, typedef_map, using_map,
        struct_fields, function_ptr_aliases
    """
    verbose = config.get("verbose_logging", False)
    project_root = os.getcwd()

    # 1) Prepare list of headers to parse
    header_list = config.get("include_files", [])
    if verbose:
        print(f"[GMBridge][parse_headers]  Public headers: {header_list}")
    # Verify existence
    for header in header_list:
        header_path = os.path.normpath(os.path.join(project_root, header))
        if not os.path.isfile(header_path):
            raise FileNotFoundError(f"[parse_headers] Missing public header: {header_path}")


    # 2) Build include dirs

    include_dirs = set(os.path.dirname(h) for h in sources.get("header_files", []))
    include_dirs |= { os.path.normpath(os.path.join(project_root, inc))
                      for inc in config.get("extra_includes", []) }
    if verbose:
        print("[GMBridge][parse_headers]  Include directories:")
        for inc in sorted(include_dirs):
            print(f"    {inc}")

    # 3) Build preprocessor command and flags
    preprocessor_cmds = []
    if "preprocessor" in config:
        preprocessor_cmds.append(config["preprocessor"])
    if sys.platform.startswith("win"):
        preprocessor_cmds += [
            ["clang", "-E", "-dD", "-P"],
            ["gcc",   "-E", "-dD", "-P"],
            ["cl", "/E", "/nologo"]
        ]
    else:
        preprocessor_cmds += [
            ["cpp", "-P", "-dD"],
            ["clang", "-E", "-dD", "-P"],
            ["gcc", "-E", "-dD", "-P"]
        ]

    # 4) Gather define flags (user defines first)
    define_flags = []
    for user_define in defines:
        define_flags.append(f"-D{user_define}")
    for extra_define in config.get("preprocessor_defines", []):
        define_flags.append(f"-D{extra_define}")

    all_results = {"files": {}}

    # 5) Iterate headers and run preprocessor + parse
    for header in header_list:
        hdr_path = os.path.normpath(os.path.join(project_root, header))
        # 5a) select a working preprocessor
        cpp_command = None
        for candidate in preprocessor_cmds:
            tool = candidate[0]
            if shutil.which(tool):
                cpp_command = candidate.copy()
                if verbose:
                    print(f"[GMBridge][parse_headers]    Using preprocessor: {candidate[0]}")
                break
        if not cpp_command:
            raise RuntimeError("[GMBridge][parse_headers] No suitable C preprocessor found.")

        # 5b) assemble full command
        inc_flag = "/I" if cpp_command[0].lower() == "cl" else "-I"
        full_command = cpp_command + define_flags
        for inc in include_dirs:
            full_command.append(f"{inc_flag}{inc}")
        full_command.append(hdr_path)

        if verbose:
            print(f"[GMBridge][parse_headers]    Running: {full_command}")

        proc = subprocess.run(
            full_command,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", check=True
        )
        content = proc.stdout

        # 5c) normalize content
        content = LINE_CONTINUATION_RE.sub(" ", content)
        content = re.sub(r'\s+', ' ', content)
        
        # 5d) init per-file file_result
        file_result = {
            "functions": [],
            "enums": {},
            "constants": {},
            "typedef_map": {},
            "using_map": {},
            "struct_fields": {},
            "function_ptr_aliases": []
        }

        # 6) Function-pointer typedefs
        file_result["function_ptr_aliases"] = sorted({
            match.group("alias") for match in FUNC_PTR_RE.finditer(content)
        })
        
        # 7) Enums
        for match in ENUM_RE.finditer(content):
            raw, body, alias = match.group(1), match.group(2), match.group(3)
            name = alias or raw or "unnamed_enum"
            entries, val = {}, 0
            for part in body.split(","):
                part = part.strip()
                if not part:
                    continue
                if "=" in part:
                    key, value = map(str.strip, part.split("=", 1))
                    try:
                        val = int(value, 0)
                    except:
                        val = 0
                else:
                    key = part
                entries[key] = val
                val += 1
            # cleanup prefixes/suffixes omitted for brevity...
            file_result["enums"][name] = entries

        # 8) Constants
        for name, value in CONST_RE.findall(content):
            file_result["constants"][name] = (value if value.startswith('"') else int(value, 0))

        # 9) Typedefs, using, handle typedefs
        for full, alias in TYPEDEF_RE.findall(content):
            file_result["typedef_map"][alias] = full.strip()
        for alias, target in USING_RE.findall(content):
            file_result["using_map"][alias] = target.strip()
        for struct_name, alias in HANDLE_RE.findall(content):
            file_result["typedef_map"][alias] = f"struct {struct_name}_T *"
        
        # 10) Structs
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
                        except:
                            field["array_size"] = sz

                    meta = classify_c_type(file_result, clean_base, config)
                    field.update(meta)

                    fields.append(field)

            file_result["struct_fields"][name] = fields
        
        # 11) Promote typedef aliases into struct_fields
        def _resolve_type(t):
            seen = set()
            while t in file_result["typedef_map"] and t not in seen:
                seen.add(t)
                t = file_result["typedef_map"][t]
            return t

        for alias in list(file_result["typedef_map"]):
            root = _resolve_type(alias)
            if root in file_result["struct_fields"]:
                file_result["struct_fields"][alias] = file_result["struct_fields"][root]

        # 12) Cleanup
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
        
        # 13) Functions
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

                meta = classify_c_type(file_result, tp, config)

                if array_size is not None:
                    meta["is_ref"]         = True
                    meta["extension_type"] = "string"

                entry = {"name": nm, "type": tp, **meta}
                arg_list.append(entry)

            ret_meta = classify_c_type(file_result, m.group("ret").strip(), config)
            file_result["functions"].append({
                "name":        fn_name,
                "return_type": ret_meta["canonical_type"],
                "return_meta": ret_meta,
                "args":        arg_list
            })

        skip_prefixes = config.get("skip_function_prefixes", [])
        if skip_prefixes:
            filtered = []
            for fn in file_result["functions"]:
                name = fn.get("name", "")
                # if it matches any of the skip-prefixes, drop it
                if any(name.startswith(pref) for pref in skip_prefixes):
                    if config.get("debug", False):
                        print(f"[GMBridge] Skipping function '{name}' (prefix filter)")
                    continue
                filtered.append(fn)
            file_result["functions"] = filtered

        # If debugging is enabled, dump the preprocessed content
        if config.get("debug", False):
            # Compute a safe filename: <originalbasename>_expanded.h
            base_name = os.path.splitext(os.path.basename(hdr_path))[0]
            dump_name = f"{base_name}_expanded.h"
            with open(dump_name, "w", encoding="utf-8") as dbg_file:
                dbg_file.write(content)
            print(f"[GMBridge] Wrote expanded macros to: {dump_name}")

        all_results["files"][hdr_path] = file_result
        
        if verbose:
            num_funcs  = len(file_result["functions"])
            num_enums  = len(file_result["enums"])
            num_const  = len(file_result["constants"])
            num_struct = len(file_result["struct_fields"])
            print(f"[GMBridge][parse_headers]    → Parsed: {num_funcs} funcs, "
                  f"{num_enums} enums, {num_const} consts, {num_struct} structs")
            
    # 11) merge all per-file results
    parse_result = flatten_parse_data(all_results)
    
    if verbose:
        total_f = len(parse_result["functions"])
        total_s = len(parse_result["struct_fields"])
        print(f"[GMBridge][parse_headers] Done parse_headers(): "
              f"{total_f} total funcs, {total_s} total structs")
        
    if config.get("debug"):
        with open("debug_parser.json", "w", encoding="utf-8") as debug_file:
            json.dump(parse_result, debug_file, indent=2)
        if verbose:
            print("[GMBridge][parse_headers] Wrote debug_parser.json")

    return parse_result
