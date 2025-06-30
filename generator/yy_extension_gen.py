import re
import json
import uuid



def resolve_gml_type(c_type, fn_name, role, typedef_map, known_enum_typenames, known_structs):
    original_type = c_type

    def resolve_typedef_chain(t):
        seen = set()
        while t in typedef_map and t not in seen:
            seen.add(t)
            t = typedef_map[t]
        return t.strip()
    resolved_type = resolve_typedef_chain(original_type)

    t_lc = resolved_type.lower()

    if t_lc in ["string", "const char*"]:
        return 1, False, True  # string
    elif t_lc in ["double", "float", "int", "bool",
                  "uint64_t", "int64_t", "uint32_t", "int32_t",
                  "uint16_t", "int16_t", "uint8_t", "int8_t"]:
        return 2, True, True  # numeric as double
    elif t_lc.startswith("ref "):
        return 1, False, True  # already reference
    elif resolved_type.lower() in known_enum_typenames:
        return 2, False, True  # enum as double
    elif t_lc == "void" and role == "return":
        return 2, False, True  # void as double

    # --- Struct pointer or const struct pointer ---
    stripped = re.sub(r'^const\s+', '', resolved_type).rstrip('*').strip()
    if stripped in known_structs:
        return 1, False, True  # treat struct pointer as reference string

        # --- Numeric or handle pointer handling ---
    if resolved_type.endswith("*"):
        base_type = resolved_type.rstrip("*").strip()
        base_type = re.sub(r'^const\s+', '', base_type)

        # Map typedefs again if needed
        base_resolved = typedef_map.get(base_type, base_type)
        base_lc = base_resolved.lower()

        if base_lc in ["double", "float", "int", "bool",
                       "uint64_t", "int64_t", "uint32_t", "int32_t",
                       "uint16_t", "int16_t", "uint8_t", "int8_t"]:
            return 2, True, True  # numeric out param as double
        
        if base_lc in known_enum_typenames:
            return 2, True, True  # enum out param, treat as double

        if base_resolved.startswith("ref ") or base_type in known_structs:
            return 1, False, True  # treat pointer to struct or handle as ref string

    print(f"[Error] Function {role} {fn_name} has unsupported type '{resolved_type}'. Skipping.")
    return None, False, False




def generate_yy_extension(functions, config, known_enum_typenames=None):
    if known_enum_typenames is None:
        known_enum_typenames = set()

    typedef_map = functions.get("typedef_map", {})
    known_structs = functions.get("known_structs", set())
    
    dll_name = config.get("dll_name", "GM-OpenXR.dll")
    init_name = config.get("init_function", "YYExtensionInitialise")
    cleanup_name = config.get("cleanup_function", "YYExtensionInitialise")
    extension_name = config.get("extension_name", "GM_OpenXR")

    func_entries = []
    count_success = 0
    count_warning = 0
    count_failure = 0

    for fn in functions["functions"]:
        local_warnings = 0
        arg_types = []
        valid = True

        # === Check args ===
        for arg in fn["args"]:
            type_code, warn, ok = resolve_gml_type(arg["type"], fn["name"], "arg", typedef_map, known_enum_typenames, known_structs)
            if not ok:
                valid = False
                break
            arg_types.append(type_code)
            if warn:
                local_warnings += 1


        if not valid:
            count_failure += 1
            continue

        # === Check return type ===
        original_ret = fn["return_type"]
        resolved_ret = typedef_map.get(original_ret, original_ret)
        rt_lc = resolved_ret.lower()

        return_code, warn, ok = resolve_gml_type(fn["return_type"], fn["name"], "return", typedef_map, known_enum_typenames, known_structs)
        if not ok:
            count_failure += 1
            continue
        if warn:
            local_warnings += 1



        # === Add function entry ===
        func_entries.append({
            "$GMExtensionFunction": "",
            "%Name": fn["name"],
            "argCount": len(arg_types),
            "args": arg_types,
            "documentation": "",
            "externalName": fn["name"],
            "help": "",
            "hidden": False,
            "kind": 1,
            "name": fn["name"],
            "resourceType": "GMExtensionFunction",
            "resourceVersion": "2.0",
            "returnType": return_code,
            "id": str(uuid.uuid4()).upper()
        })

        if local_warnings > 0:
            count_warning += 1
        else:
            count_success += 1

    # === File and extension entries ===
    file_entry = {
        "$GMExtensionFile": "",
        "%Name": "",
        "constants": [],
        "copyToTargets": 3035426170322551022,
        "filename": dll_name,
        "final": "",
        "functions": func_entries,
        "init": init_name,
        "kind": 1,
        "name": "",
        "order": [],
        "origname": "",
        "ProxyFiles": [],
        "resourceType": "GMExtensionFile",
        "resourceVersion": "2.0",
        "uncompress": False,
        "usesRunnerInterface": False,
        "id": str(uuid.uuid4()).upper()
    }

    extension = {
        "$GMExtension": "",
        "%Name": extension_name,
        "androidProps": {},
        "copyToTargets": 3035426170322551022,
        "filename": extension_name,
        "iosProps": {},
        "macProps": {},
        "name": extension_name,
        "optionsFile": "",
        "packageId": "",
        "productId": "",
        "resourceType": "GMExtension",
        "resourceVersion": "2.0",
        "tvosProps": {},
        "files": [file_entry],
        "id": str(uuid.uuid4()).upper()
    }

    # === Final Summary ===
    print("\nSummary:")
    print(f"success: {count_success}")
    print(f"warning: {count_warning}")
    print(f"failure: {count_failure}")

    # === Debug: print resolved function info as JSON ===
    debug_dump = {
        "functions": functions["functions"],
        "typedef_map": typedef_map,
        "known_enum_typenames": list(known_enum_typenames),
        "known_structs": list(functions.get("known_structs", []))  # fallback to empty list if not present
    }
    
    with open("debug_resolved.json", "w", encoding="utf-8") as dbg:
        json.dump(debug_dump, dbg, indent=4)


    return json.dumps(extension, indent=4)
