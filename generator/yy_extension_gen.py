import json
import uuid


def generate_yy_extension(functions, config, known_enum_typenames=None):
    if known_enum_typenames is None:
        known_enum_typenames = set()

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
            arg_type = arg["type"].lower()
            if arg_type in ["double", "string"]:
                arg_types.append(1 if arg_type == "string" else 2)
            elif arg_type in ["bool", "int", "float"]:
                print(f"[Warning] Function {fn['name']} uses type '{arg_type}', treating as double.")
                arg_types.append(2)
                local_warnings += 1
            elif arg_type in known_enum_typenames:
                print(f"[Info] Function {fn['name']} uses known enum type '{arg_type}', treating as double.")
                arg_types.append(2)
            else:
                print(f"[Error] Function {fn['name']} has unsupported type '{arg_type}'. Skipping.")
                valid = False
                break

        if not valid:
            count_failure += 1
            continue

        # === Check return ===
        return_type = fn["return_type"].lower()
        if return_type in ["double", "string"]:
            return_code = 1 if return_type == "string" else 2
        elif return_type in ["bool", "int", "float", "void"]:
            if return_type != "void":
                print(f"[Warning] Function {fn['name']} has return type '{return_type}', treating as double.")
                local_warnings += 1
            return_code = 2
        elif return_type in known_enum_typenames:
            print(f"[Info] Function {fn['name']} returns known enum type '{return_type}', treating as double.")
            return_code = 2
        else:
            print(f"[Error] Function {fn['name']} has unsupported return type '{return_type}'. Skipping.")
            count_failure += 1
            continue

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

    return json.dumps(extension, indent=4)
