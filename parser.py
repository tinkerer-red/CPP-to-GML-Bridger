import re

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

def parse_header(header_path, namespace="XR"):
    with open(header_path, "r") as f:
        content = f.read()

    func_pattern = re.compile(
        r'XRAPI_ATTR\s+([^\s]+(?:\s+\w+)*)\s+XRAPI_CALL\s+(xr\w+)\((.*?)\);',
        re.DOTALL
    )

    functions = []

    for ret_type, name, args in func_pattern.findall(content):
        arg_list = []
        if args.strip():
            for arg in args.split(','):
                arg = arg.strip()
                match = re.match(r'(.+?)\s+(\**\w+(?:\[[^\]]+\])?)$', arg)
                if match:
                    arg_type, arg_name = match.groups()

                    # Detect C-style arrays, capture the SIZE for later
                    array_size = None
                    if '[' in arg_name and arg_name.endswith(']'):
                        idx        = arg_name.index('[')
                        base_name  = arg_name[:idx]
                        size_macro = arg_name[idx+1:-1]               # e.g. "XR_MAX_RESULT_STRING_SIZE"
                        arg_type   = arg_type.strip() + '*'           # char → char*
                        arg_name   = base_name

                        array_size = size_macro

                    arg_entry = {
                        "type": arg_type.strip(),
                        "name": arg_name.strip()
                    }
                    if array_size:
                        arg_entry["array_size"] = array_size         # stash it for the generators

                    arg_list.append(arg_entry)


        functions.append({
            "name": name,
            "return_type": ret_type.strip(),
            "args": arg_list
        })

    enum_pattern = re.compile(r'typedef\s+enum\s+(\w+)?\s*{([^}]+)}\s*(\w+)?\s*;', re.DOTALL)
    enums = {}
    known_enum_typenames = set()

    for match in enum_pattern.finditer(content):
        enum_name = match.group(3) or match.group(1) or "unnamed_enum"
        enum_body = match.group(2)
        enum_entries = {}
        current_value = 0

        for line in enum_body.split(','):
            line = line.strip()
            if not line:
                continue
            if '=' in line:
                key, val = map(str.strip, line.split('=', 1))
                try:
                    current_value = int(eval(val))
                except Exception:
                    current_value = 0
            else:
                key = line
            enum_entries[key] = current_value
            current_value += 1

        short_name = enum_name
        if short_name.lower().startswith(namespace.lower()):
            short_name = short_name[len(namespace):]

        prefix, suffix = get_enum_prefix_suffix_cleanup(enum_entries.keys())

        cleaned_entries = {}
        for key, val in enum_entries.items():
            clean_key = key
            if prefix and clean_key.startswith(prefix):
                clean_key = clean_key[len(prefix):]
            if suffix and clean_key.endswith(suffix):
                clean_key = clean_key[:-len(suffix)]
            cleaned_entries[clean_key] = val

        cleaned_entries["_meta"] = {
            "namespace": namespace,
            "short_name": short_name,
            "base_prefix": prefix,
            "base_suffix": suffix
        }

        enums[enum_name] = cleaned_entries
        known_enum_typenames.add(enum_name.lower())

    # --- Parse simple #defines with numeric or string values; ignore macros ---
    define_pattern = re.compile(
        r'^#define\s+([A-Za-z_]\w*)\s+("(?:[^"\\]|\\.)*"|-?\d+|0x[0-9A-Fa-f]+)\s*$',
        re.MULTILINE
    )
    constants = {}
    for name, val in define_pattern.findall(content):
        if val.startswith('"') and val.endswith('"'):
            # keep the quotes for string literals
            constants[name] = val
        else:
            # parse decimal or hex integers
            constants[name] = int(val, 0)

    return {
        "functions": functions,
        "enums": enums,
        "known_enum_typenames": known_enum_typenames,
        "constants": constants
    }
