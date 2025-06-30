import re
import json

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

def classify_c_type(c_type, typedef_map, known_enum_typenames, known_structs):
    # unwrap any number of typedef aliases
    def resolve(t):
        seen = set()
        while t in typedef_map and t not in seen:
            seen.add(t)
            t = typedef_map[t]
        return t

    original_type = c_type.strip()
    # first resolve the outer typedef chain
    resolved_type = resolve(original_type).strip()
    resolved_lc   = resolved_type.lower()

    # now peel off const/* and find the base
    is_pointer = resolved_type.endswith("*")
    is_const   = resolved_type.startswith("const ")
    base_type  = re.sub(r'^const\s+', '', resolved_type).rstrip('*').strip()
    # resolve again in case base_type is itself a typedef
    base_resolved = resolve(base_type).strip()
    base_lc       = base_resolved.lower()

    result = {
        "original_type":    original_type,
        "resolved_type":    resolved_type,
        "base_type":        base_type,
        "base_resolved":    base_resolved,
        "is_pointer":       is_pointer,
        "is_const":         is_const,
        "is_enum":          base_lc in known_enum_typenames,
        "is_struct":        base_type in known_structs,
        "is_ref_wrapped":   base_resolved.startswith("ref "),
        "is_primitive":     base_lc in [
            "double","float","int","bool",
            "uint64_t","int64_t","uint32_t","int32_t",
            "uint16_t","int16_t","uint8_t","int8_t"
        ],
        "is_string_buffer_out": (base_resolved=="char" and is_pointer and not is_const),
        "gm_pass_type":     "unknown"
    }

    # classify
    if resolved_lc in ["string","const char*"]:
        result["gm_pass_type"] = "string"
    elif result["is_string_buffer_out"]:
        result["gm_pass_type"] = "buffer"
    elif result["is_ref_wrapped"] or result["is_struct"]:
        result["gm_pass_type"] = "ref"
    elif result["is_enum"] or result["is_primitive"]:
        result["gm_pass_type"] = "double"

    return result

def parse_header(header_path, namespace="XR"):
    with open(header_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1) Collapse multiline macros
    content = re.sub(r'\\\r?\n\s*', ' ', content)

    # 2) Parameterized macros
    macro_defs = {}
    for name, params, body in re.findall(
        r'^\s*#define\s+(\w+)\s*\((.*?)\)\s+(.*)$',
        content, re.MULTILINE
    ):
        macro_defs[name] = {
            "params": [p.strip() for p in params.split(',')],
            "body": body.strip()
        }

    content = expand_macros(content, macro_defs)
    with open("expanded_macros.h", "w", encoding="utf-8") as dbg:
        dbg.write(content)

    # 3) Parse enums
    enums = {}
    known_enum_typenames = set()
    for match in re.finditer(
        r'typedef\s+enum\s+(\w+)?\s*{([^}]+)}\s*(\w+)?\s*;',
        content, re.DOTALL
    ):
        raw_name = match.group(3) or match.group(1) or "unnamed_enum"
        body = match.group(2)
        entries, val = {}, 0
        for line in body.split(','):
            line = line.strip()
            if not line: continue
            if '=' in line:
                k, v = map(str.strip, line.split('=', 1))
                try: val = int(eval(v))
                except: val = 0
            else:
                k = line
            entries[k] = val
            val += 1

        short = raw_name
        if short.lower().startswith(namespace.lower()):
            short = short[len(namespace):]
        pre, suf = get_enum_prefix_suffix_cleanup(entries.keys())

        cleaned = {}
        for k, v in entries.items():
            ck = k[len(pre):] if pre and k.startswith(pre) else k
            if suf and ck.endswith(suf):
                ck = ck[:-len(suf)]
            cleaned[ck] = v
        cleaned["_meta"] = {
            "namespace": namespace,
            "short_name": short,
            "base_prefix": pre,
            "base_suffix": suf
        }

        enums[raw_name] = cleaned
        known_enum_typenames.add(raw_name.lower())

    # 4) Simple #define constants
    constants = {}
    for n, v in re.findall(
        r'^#define\s+([A-Za-z_]\w*)\s+("(?:[^"\\]|\\.)*"|-?\d+|0x[0-9A-Fa-f]+)\s*$',
        content, re.MULTILINE
    ):
        constants[n] = (v if v.startswith('"') else int(v, 0))

    # 5) Typedef map
    typedef_map = {}

    # (a) catch plain aliases, including flags and basic enums
    for full, alias in re.findall(
        r'typedef\s+([^\s]+(?:\s+\w+)*)\s+(\w+)\s*;',
        content
    ):
        typedef_map[alias] = full.strip()

    # (b) handles
    for _, alias in re.findall(
        r'typedef\s+struct\s+(\w+)_T\s*\*\s*(\w+);',
        content
    ):
        typedef_map[alias] = f"ref {alias}"

    # 6) Full-body structs (capture ANY tokens before the '{')
    known_structs = set()
    full_struct = re.compile(
        r'typedef\s+struct\b[^{}]*?\{[^}]+\}\s*(\w+)\s*;',
        re.DOTALL
    )
    for alias in full_struct.findall(content):
        known_structs.add(alias)
        # treat pointers-to-this as ref
        typedef_map[alias] = alias
    

    # 7) Function parsing + classification
    func_pattern = re.compile(
        r'XRAPI_ATTR\s+([^\s]+(?:\s+\w+)*)\s+XRAPI_CALL\s+(xr\w+)\((.*?)\);',
        re.DOTALL
    )
    functions = []
    for ret, name, args in func_pattern.findall(content):
        arg_list = []
        for raw in [a.strip() for a in args.split(',') if a.strip()]:
            m = re.match(r'(.+?)\s+(\**\w+(?:\[[^\]]+\])?)$', raw)
            if not m:
                continue
            tp, nm = m.groups()
            array_size = None
            if '[' in nm and nm.endswith(']'):
                idx = nm.index('[')
                array_size = nm[idx+1:-1]
                tp = tp.strip() + '*'
                nm = nm[:idx]
            entry = {"name": nm.strip(), "type": tp.strip()}
            if array_size:
                entry["array_size"] = array_size
            entry.update(classify_c_type(
                entry["type"],
                typedef_map,
                known_enum_typenames,
                known_structs
            ))
            arg_list.append(entry)

        ret_meta = classify_c_type(
            ret.strip(),
            typedef_map,
            known_enum_typenames,
            known_structs
        )

        functions.append({
            "name": name,
            "return_type": ret.strip(),
            "return_meta": ret_meta,
            "args": arg_list
        })

    # Dump a debug file for inspection
    with open("debug_types.json", "w", encoding="utf-8") as dbg:
        json.dump({
            "typedef_map": typedef_map,
            "known_enum_typenames": list(known_enum_typenames),
            "known_structs": list(known_structs),
            "functions": functions
        }, dbg, indent=4)

    return {
        "functions": functions,
        "enums": enums,
        "constants": constants,
        "typedef_map": typedef_map,
        "known_enum_typenames": known_enum_typenames,
        "known_structs": known_structs
    }
