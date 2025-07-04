# generator/yy_extension_gen.py

import re
import json
import uuid

def generate_yy_extension(parse_result, config):
    """
    Generate the GameMaker .yy extension JSON from the unified parse_result.
    """

    typedef_map   = parse_result["typedef_map"]
    known_structs = parse_result["struct_fields"].keys()
    enum_names    = set(parse_result["enums"].keys())

    dll_name      = config.get("dll_name", "GM-OpenXR.dll")
    init_name     = config.get("init_function", "YYExtensionInitialise")
    cleanup_name  = config.get("cleanup_function", "YYExtensionInitialise")
    extension_name= config.get("extension_name", "GM_OpenXR")

    func_entries = []
    count_success = count_warning = count_failure = 0

    for fn in parse_result["functions"]:
        local_warnings = 0
        arg_types      = []
        valid          = True

        # === Process arguments ===
        for arg in fn["args"]:
            ext_t = arg["extension_type"]           # "string", "double", or "unknown"
            canon = arg["canonical_type"]           # e.g. "XrResult", "float", etc.

            warn = False
            
            # if unknown but enum, treat as double
            if ext_t == "unknown" and canon in enum_names:
                ext_t = "double"

            # map to GML type codes: 1=string, 2=double
            if ext_t == "string":
                type_code = 1
            elif ext_t == "double":
                if canon in ("uint64_t", "int64_t") and not config.get("treat_int64_as_ref", False):
                    print(
                        f"[Warning] Function arg {fn['name']} '{arg['name']}' is 64-bit ('{canon}'); "
                        "as double it may lose precision — enable `treat_int64_as_ref` in config."
                    )
                    warn = True
                type_code = 2
            else:
                # unsupported type
                print(f"[Error] Function arg {fn['name']} '{arg['name']}' has unsupported type '{canon}'")
                valid = False
                break

            arg_types.append(type_code)
            if warn:
                local_warnings += 1

        if not valid:
            count_failure += 1
            continue

        # === Process return type ===
        ret_meta = fn["return_meta"]
        ext_rt   = ret_meta["extension_type"]
        canon_rt = ret_meta["canonical_type"]
        
        warn = False

        if ext_rt == "unknown" and canon_rt in enum_names:
            ext_rt = "double"

        if ext_rt == "string":
            return_code = 1
        elif ext_rt == "double":
            if canon in ("uint64_t", "int64_t") and not config.get("treat_int64_as_ref", False):
                print(
                    f"[Warning] Function return {fn['name']} is 64-bit ('{canon_rt}'); "
                    "as double it may lose precision — enable `treat_int64_as_ref` in config."
                )
                warn = True
            return_code = 2
        elif canon_rt == "void":
            return_code = 2  # GMS treats void as 0 (DOES IT????)
        else:
            print(f"[Error] Function return {fn['name']} has unsupported type '{canon_rt}'")
            count_failure += 1
            continue

        if warn:
            local_warnings += 1

        # === Build the function entry ===
        func_entries.append({
            "$GMExtensionFunction": "",
            "%Name":                fn["name"],
            "argCount":             len(arg_types),
            "args":                 arg_types,
            "documentation":        "",
            "externalName":         fn["name"],
            "help":                 "",
            "hidden":               False,
            "kind":                 1,
            "name":                 fn["name"],
            "resourceType":         "GMExtensionFunction",
            "resourceVersion":      "2.0",
            "returnType":           return_code,
            "id":                   str(uuid.uuid4()).upper()
        })

        # update counters
        if local_warnings:
            count_warning += 1
        else:
            count_success += 1

    # === File entry ===
    file_entry = {
        "$GMExtensionFile":   "",
        "%Name":              "",
        "constants":          [],
        "copyToTargets":      3035426170322551022,
        "filename":           dll_name,
        "functions":          func_entries,
        "init":               init_name,
        "kind":               1,
        "name":               "",
        "order":              [],
        "ProxyFiles":         [],
        "resourceType":       "GMExtensionFile",
        "resourceVersion":    "2.0",
        "uncompress":         False,
        "usesRunnerInterface":False,
        "id":                  str(uuid.uuid4()).upper()
    }

    # === Extension entry ===
    extension = {
        "$GMExtension":      "",
        "%Name":             extension_name,
        "androidProps":      {},
        "filename":          extension_name,
        "functions":         file_entry["functions"],
        "init":              init_name,
        "kind":              1,
        "name":              extension_name,
        "resourceType":      "GMExtension",
        "resourceVersion":   "2.0",
        "files":             [file_entry],
        "id":                str(uuid.uuid4()).upper()
    }

    # === Summary ===
    print("\nSummary:")
    print(f"  success: {count_success}")
    print(f"  warnings: {count_warning}")
    print(f"  failure: {count_failure}")

    # === Debug dump of what we resolved ===
    debug_dump = {
        "functions": parse_result["functions"],
        "typedef_map": typedef_map,
        "known_structs":   list(known_structs),
        "enums":           parse_result["enums"]
    }
    with open("debug_yy.json", "w", encoding="utf-8") as dbg:
        json.dump(debug_dump, dbg, indent=4)

    return json.dumps(extension, indent=4)
