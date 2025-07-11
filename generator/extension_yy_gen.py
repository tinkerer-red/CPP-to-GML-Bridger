# generator/yy_gen.py

import json
import uuid
from pathlib import Path
from string import Template

# Utility to load a template file from disk
def load_yy_template(template_name: str) -> Template:
    template_path = Path(__file__).parent / "templates" / template_name
    return Template(template_path.read_text(encoding="utf-8"))

# GM return/arg type code mapping
GML_TYPE_CODE = {
    "double": 2,
    "string": 1,
    "void":   2,
}

# Platform/architecture → GM target ID mapping
def platform_to_gm_targets(platform: str, arch: str) -> list:
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

# Render a single function entry block from template
def render_function_entry(fn, namespace, expose_raw_names):
    template_path = Path("generator/templates/extension_file_function.tpl")
    template = Template(template_path.read_text(encoding="utf-8"))

    function_name = fn["name"]
    arg_types = []
    for arg in fn["args"]:
        code = GML_TYPE_CODE.get("string" if arg.get("force_string_wrapper") else arg["extension_type"], 2)
        arg_types.append(code)
    return_type = GML_TYPE_CODE.get(fn["return_meta"]["extension_type"], 2)
    
    # If using namespace exposure, then GML name is namespaced; otherwise, just the raw function name
    hidden = "false" if expose_raw_names else "true"

    return template.substitute({
        "FunctionGmlName": f"__{function_name}",
        "ArgCount": len(arg_types),
        "ArgCodes": json.dumps(arg_types),
        "Documentation": fn.get("doc", "").replace('"', '\\"'),
        "ExternalName": f"__{function_name}",
        "Help": fn.get("doc", ""),
        "ReturnType": return_type,
        "Hidden": hidden,
    })

# Render a single file entry (a DLL or binary with functions) from template
def render_file_entry(output_info: dict, function_blocks: list) -> str:
    """
    output_info: {
        "filename": str,
        "platform": str,
        "architecture": str
    }
    function_blocks: list of strings (rendered function_entry JSON blocks)
    """
    template = load_yy_template("extension_file_entry.tpl")
    return template.substitute({
        "FileName": output_info["filename"],
        "FileTargets": json.dumps(platform_to_gm_targets(output_info["platform"], output_info["architecture"])),
        "FileFunctions": "[\n" + ",\n".join(function_blocks) + "\n]"
    })

# Render the final .yy extension file using all rendered pieces
def render_extension_yy(extension_name: str, config: dict, file_blocks: list) -> str:
    """
    extension_name: "GM_OpenXR"
    file_blocks: list of rendered file_entry strings
    """
    template = load_yy_template("extension.yy.tpl")
    return template.substitute({
        "ExtensionAssetName": extension_name,
        "ExtensionVersion": config.get("extension_version", "0.0.1"),
        "FilesArray": "[\n" + ",\n".join(file_blocks) + "\n]"
    })

def generate_yy_extension(parse_result: dict, config: dict, all_outputs: list):
    """
    Generates a GameMaker .yy extension using the yy_renderers templates.
    """
    if not all_outputs:
        raise RuntimeError("[GMBridge][yy_gen] No build outputs provided")

    extension_name = Path(all_outputs[0]["filename"]).stem
    namespace      = config.get("namespace", extension_name)
    expose_raw_names = (not namespace)

    # 2) Render each function entry
    function_blocks = [
        render_function_entry(fn, namespace, expose_raw_names)
        for fn in parse_result.get("functions", [])
    ]

    # 3) Render each file entry (including functions list)
    file_blocks = [
        render_file_entry(out, function_blocks)
        for out in all_outputs
    ]

    # 4) Render the final .yy JSON
    yy_content = render_extension_yy(extension_name, config, file_blocks)

    # 5) Write to disk
    output_root = Path(config.get("output_folder", "output"))
    ext_folder  = output_root / "extensions" / extension_name
    ext_folder.mkdir(parents=True, exist_ok=True)
    yy_path = ext_folder / f"{extension_name}.yy"
    yy_path.write_text(yy_content, encoding="utf-8")

    print(f"[GMBridge][yy_gen] Generated extension: {yy_path}")
