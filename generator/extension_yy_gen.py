import os
import json
import uuid

def generate_yy_extension(parse_result, config, all_outputs):
    """
    Generates the GameMaker .yy extension JSON from the parse result and build outputs.
    """
    extension_name = config["dll_name"]
    namespace = config["namespace"]

    ext_folder = os.path.join(config["output_folder"], "extensions", extension_name)
    os.makedirs(ext_folder, exist_ok=True)

    yy_path = os.path.join(ext_folder, f"{extension_name}.yy")

    yy_data = {
        "id": str(uuid.uuid4()).upper(),
        "name": extension_name,
        "options": [],
        "files": [],
        "functions": [],
        "copyToTargets": 0,
        "order": [],
        "resourceType": "GMExtension",
        "resourceVersion": "2.0"
    }

    # Platform/arch-specific binaries
    for entry in all_outputs:
        yy_data["files"].append({
            "filename": entry["filename"],
            "origname": entry["filename"],
            "init": f"__{extension_name}_init",
            "final": f"__{extension_name}_cleanup",
            "kind": 1,  # DLL
            "uncompress": False,
            "functions": [],
            "targets": platform_to_gm_targets(entry["platform"], entry["architecture"])
        })

    # Bindings for each function
    for func in parse_result.get("functions", []):
        # This is placeholder — you'll eventually fill these out from actual parse metadata
        yy_data["functions"].append({
            "externalName": f"__{func['name']}",
            "kind": 1,
            "help": func.get("doc", f"{func['name']} function"),
            "hidden": False,
            "returnType": func.get("return_category", 1),  # default: double
            "argCount": len(func.get("args", [])),
            "args": [1 for _ in func.get("args", [])],     # assume all args are doubles for now
            "name": f"{namespace}_{func['name']}",
            "argNames": [arg["name"] for arg in func.get("args", [])]
        })

    # Write to disk
    with open(yy_path, "w", encoding="utf-8") as out_file:
        json.dump(yy_data, out_file, indent=2)
    print(f"Generated extension: {yy_path}")


def platform_to_gm_targets(platform, arch):
    """
    Maps output_info platform/arch to GameMaker target constants.
    """
    if platform == "Windows":
        return [1] if arch == "x86" else [2]
    if platform == "macOS":
        return [3] if arch == "x64" else [12]
    if platform == "Linux":
        return [5] if arch == "x64" else []
    if platform == "Android":
        return [6] if arch == "arm64" else []
    if platform == "iOS":
        return [7]
    return []
