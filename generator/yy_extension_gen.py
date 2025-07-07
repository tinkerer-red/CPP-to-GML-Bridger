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
            ext_type    = arg["extension_type"]       # "string" or "double"
            is_big_arg  = arg.get("is_unsupported_numeric", False)
            valid       = True

            # Big numerics always come in as strings now
            if is_big_arg:
                type_code = 1

            # Standard strings
            elif ext_type == "string":
                type_code = 1

            # Standard numerics (float, double, int32, bool, enums)
            elif ext_type == "double":
                type_code = 2

            else:
                # unsupported type
                print(
                    f"[Error] Function arg {fn['name']} "
                    f"'{arg['name']}' has unsupported extension_type "
                    f"'{ext_type}'"
                )
                valid = False

            if not valid:
                count_failure += 1
                break

            arg_types.append(type_code)

        if not valid:
            count_failure += 1
            continue

        # === Process return type ===
        ret_meta   = fn["return_meta"]
        ext_type   = ret_meta["extension_type"]
        canon_rt   = ret_meta["canonical_type"]

        # Map to GML return codes: 1=string, 2=double
        if ext_type == "string":
            return_code = 1
        elif ext_type == "double" or canon_rt == "void":
            return_code = 2
        else:
            print(
                f"[Error] Function return {fn['name']} "
                f"has unsupported extension_type '{ext_type}'"
            )
            count_failure += 1
            continue
        
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
