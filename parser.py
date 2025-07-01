import os
import re
import json

# ——— Module-scope regexes ———
LINE_CONTINUATION_RE = re.compile(r'\\\r?\n\s*')
MACRO_DEF_RE         = re.compile(r'^\s*#define\s+(\w+)\s*\((.*?)\)\s+(.*)$', re.MULTILINE)
FUNC_PTR_RE          = re.compile(r'''
    typedef
    \s+ (?P<ret>.*?)           # lazy return type
    \(\s* (?:[^(]*?) \* \s*     # skip qualifiers, then "*"
    (?P<alias>\w+) \)\s*       # alias name
    \((?P<args>[^)]*)\) \s*;    # parameter list
''', re.VERBOSE | re.DOTALL)
ENUM_RE              = re.compile(r'typedef\s+enum\s+(\w+)?\s*{([^}]+)}\s*(\w+)?\s*;', re.DOTALL)
CONST_RE             = re.compile(r'^#define\s+([A-Za-z_]\w*)\s+("(?:[^"\\]|\\.)*"|-?\d+|0x[0-9A-Fa-f]+)\s*$', re.MULTILINE)
TYPEDEF_RE           = re.compile(r'typedef\s+([^\s]+(?:\s+\w+)*)\s+(\w+)\s*;')
HANDLE_RE            = re.compile(r'typedef\s+struct\s+(\w+)_T\s*\*\s*(\w+);')
STRUCT_RE = re.compile(
    r'\btypedef\s+struct\b'       # start with 'typedef struct'
    r'(?:\s+[A-Za-z_]\w*)*'        # optional struct qualifiers/names
    r'\s*\{'                       # the opening '{'
    r'(?:[^{}]|\{[^{}]*\})*'       # allow balanced nested braces
    r'\}\s*([A-Za-z_]\w*)\s*;'     # capture the alias after the closing '}'
, re.DOTALL)
XRAPI_RE             = re.compile(
    r'XRAPI_ATTR\s+([^\s]+(?:\s+\w+)*)\s+XRAPI_CALL\s+(xr\w+)\((.*?)\);',
    re.DOTALL
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

    suffixes = [k.split('_')[-1] for k in keys if '_' in k]
    suffix = None
    if len(suffixes) == len(keys) and all(s == suffixes[0] for s in suffixes):
        sfx = suffixes[0]
        if sfx.isupper() and len(sfx) >= 2:
            suffix = f"_{sfx}"

    return prefix, suffix

def expand_macros(text, macro_defs):
    for name, macro in macro_defs.items():
        params, body = macro["params"], macro["body"]
        pattern = re.compile(rf'\b{name}\s*\((.*?)\)')
        for match in reversed(list(pattern.finditer(text))):
            args = [a.strip() for a in match.group(1).split(',')]
            if len(args) != len(params):
                continue
            mapping = dict(zip(params, args))
            expanded = body
            for p, v in mapping.items():
                expanded = expanded.replace(f"{p}##_T", f"{v}_T")
                expanded = expanded.replace(p, v)
            start, end = match.span()
            text = text[:start] + expanded + text[end:]
    return text

def classify_c_type(parse_result, c_type, config):
    namespace = config.get("namespace", "XR")
    typedef_map = parse_result["typedef_map"]
    known_structs = set(parse_result["known_structs"])
    function_ptr_aliases = set(parse_result["function_ptr_aliases"])
    enum_names = set(parse_result["enums"].keys())

    def resolve(t):
        seen = set()
        while t in typedef_map and t not in seen:
            seen.add(t)
            t = typedef_map[t]
        return t

    declared_type = c_type.strip()
    intermediate = resolve(declared_type).strip()

    bare = re.sub(r'^const\s+', '', intermediate).rstrip('*').strip()
    base_type = bare
    canonical_type = resolve(base_type).strip()

    if base_type.lower().startswith(namespace.lower()):
        culled_name = base_type[len(namespace):]
    else:
        culled_name = base_type

    lc = canonical_type.lower()
    is_string = intermediate.lower() in ("string", "const char*")
    is_primitive = lc in {
        "double", "float", "int", "bool",
        "uint64_t", "int64_t", "uint32_t", "int32_t",
        "uint16_t", "int16_t", "uint8_t", "int8_t"
    }
    is_enum = base_type in enum_names

    if is_enum:
        canonical_type = "int32_t"
        is_primitive = True

    is_ref = (
        base_type.lower() in function_ptr_aliases or #is_function
        intermediate.endswith("*") or #is_pointer
        (not intermediate.endswith("*") and base_type in known_structs) #is_struct
    )

    if is_string:
        extension_type = "string"
    elif is_primitive:
        extension_type = "double"
    elif is_ref:
        extension_type = "string"
    else:
        extension_type = "unknown"

    usage_category = "ref" if is_ref else extension_type

    treat_int64_as_ref = config.get("treat_int64_as_ref", False)
    if treat_int64_as_ref and canonical_type in ("int64_t", "uint64_t"):
        extension_type = "string"
        usage_category = "ref"

    return {
        "declared_type": declared_type,
        "base_type": base_type,
        "culled_name": culled_name,
        "canonical_type": canonical_type,
        "usage_category": usage_category,
        "extension_type": extension_type,
    }

def parse_header(config):
    """
    Parse an OpenXR header into a unified parse_result dict.
    All helpers consume parse_result directly.
    """
    
    header_path   = os.path.join(config["input_folder"], config["header"])
    namespace = config.get("namespace", "XR")
    debug = config.get("debug", True)
    
    # 0) Prepare the unified result container
    parse_result = {
        "functions":            [],
        "enums":                {},
        "constants":            {},
        "typedef_map":          {},
        "known_structs":        [],
        "function_ptr_aliases": []
    }

    # 0b) Helper to normalize C-style arrays into pointer types
    def normalize_array(tp, nm):
        if '[' in nm and nm.endswith(']'):
            idx  = nm.index('[')
            size = nm[idx+1:-1]
            nm   = nm[:idx]
            tp   = tp + '*'
            return tp.strip(), nm, size
        return tp, nm, None

    # 1) Read & collapse line continuations
    with open(header_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = LINE_CONTINUATION_RE.sub(' ', content)

    # 2) Expand parameterized macros
    macro_defs = {}
    for name, params, body in MACRO_DEF_RE.findall(content):
        macro_defs[name] = {
            "params": [p.strip() for p in params.split(',')],
            "body":   body.strip()
        }
    content = expand_macros(content, macro_defs)

    # optional dump of expanded macros
    if debug:
        with open("expanded_macros.h", "w", encoding="utf-8") as dbg:
            dbg.write(content)

    # 3) Collect PFN_… aliases
    parse_result["function_ptr_aliases"] = {
        m.group('alias').lower()
        for m in FUNC_PTR_RE.finditer(content)
    }

    # 4) Parse enums safely
    for m in ENUM_RE.finditer(content):
        raw, body, alias = m.group(1), m.group(2), m.group(3)
        name = alias or raw or "unnamed_enum"

        entries, val = {}, 0
        for line in body.split(','):
            line = line.strip()
            if not line:
                continue
            if '=' in line:
                k, v = map(str.strip, line.split('=', 1))
                try:
                    val = int(v, 0)
                except ValueError:
                    val = 0
            else:
                k = line
            entries[k] = val
            val += 1

        # strip common enum prefixes/suffixes
        short = name
        if short.lower().startswith(namespace.lower()):
            short = short[len(namespace):]
        pre, suf = get_enum_prefix_suffix_cleanup(entries.keys())

        cleaned = {}
        for k, v in entries.items():
            ck = (k[len(pre):] if pre and k.startswith(pre) else k)
            if suf and ck.endswith(suf):
                ck = ck[:-len(suf)]
            cleaned[ck] = v

        cleaned["_meta"] = {
            "namespace":   namespace,
            "short_name":  short,
            "base_prefix": pre,
            "base_suffix": suf
        }

        parse_result["enums"][name] = cleaned
        

    # 5) Parse simple #define constants
    for n, v in CONST_RE.findall(content):
        parse_result["constants"][n] = (v if v.startswith('"') else int(v, 0))

    # 6) Build typedef map
    for full, alias in TYPEDEF_RE.findall(content):
        parse_result["typedef_map"][alias] = full.strip()
    for struct_name, alias in HANDLE_RE.findall(content):
        parse_result["typedef_map"][alias] = f"ref {alias}"

    # 7) Collect full-body structs
    all_structs = set(STRUCT_RE.findall(content))  # e.g. {"XrUuid", "XrPosef", ...}

    # 7a) Promote any typedef aliases whose ultimate target is a struct
    def _resolve_type(t):
        seen = set()
        while t in parse_result["typedef_map"] and t not in seen:
            seen.add(t)
            t = parse_result["typedef_map"][t]
        return t

    # If alias → some chain → a struct name, we want alias in known_structs too
    for alias in list(parse_result["typedef_map"]):
        root = _resolve_type(alias)
        if root in all_structs:
            all_structs.add(alias)

     # Now store as a list (JSON‐friendly)
    parse_result["known_structs"] = sorted(all_structs)

    # 8) Parse XRAPI functions and classify
    for ret, name, args in XRAPI_RE.findall(content):
        # arguments
        arg_list = []
        for raw in [a.strip() for a in args.split(',') if a.strip()]:
            m = re.match(r'(.+?)\s+(\**\w+(?:\[[^\]]+\])?)$', raw)
            if not m:
                continue
            tp, nm = m.group(1).strip(), m.group(2).strip()
            tp, nm, array_size = normalize_array(tp, nm)

            # single helper signature
            meta = classify_c_type(parse_result, tp, config)
            entry = {"name": nm, "type": tp, **meta}
            if array_size:
                entry["array_size"] = array_size
            arg_list.append(entry)

        # return
        ret_meta = classify_c_type(parse_result, ret.strip(), config)

        parse_result["functions"].append({
            "name":        name,
            "return_type": ret.strip(),
            "return_meta": ret_meta,
            "args":        arg_list
        })

    # 9) Optional debug dump of the final parse_result
    if True:
        with open("debug_parser.json", "w", encoding="utf-8") as dbg:
            json.dump(parse_result, dbg, indent=4, default=list)

    return parse_result