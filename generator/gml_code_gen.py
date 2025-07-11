# generator/gml_stub_gen.py

import os
import re
from pathlib import Path
from string import Template
from generator.gml_templates import (
    render_constant,
    render_enum,
    render_function,
    render_constructor,
    render_builtin,
)

def generate_gml(parse_result, exports, config):
    project_root = Path.cwd()
    output_root = project_root / "output"
    project_name = config.get("project_name", "GMBridge")

    namespace = config.get("namespace", "")
    strip_namespace_from_symbols = config.get("strip_namespace_from_symbols", True)
    use_namespace = bool(namespace.strip())

    extension_folder = output_root / "extensions" / project_name
    extension_folder.mkdir(parents=True, exist_ok=True)
    gml_path = extension_folder / f"{project_name}.gml"

    enums_dict = parse_result.get("enums", {})
    known_enum_map = {key.lower(): key for key in enums_dict.keys()}

    # --- Constants ---
    constants_output = [
        render_constant(name, value, namespace, strip_namespace_from_symbols)
        for name, value in parse_result.get("constants", {}).items()
    ]

    # --- Struct Constructors ---
    constructors_output = [
        render_constructor(struct_name, namespace, strip_namespace_from_symbols)
        for struct_name in sorted(parse_result.get("known_structs", []))
    ]

    # --- Enums ---
    enums_output = [
        render_enum(enum_name, {
            key: val for key, val in enum_data.items() if key != "_meta"
        }, namespace, strip_namespace_from_symbols)
        for enum_name, enum_data in enums_dict.items()
    ]

    # --- Functions ---
    functions_output = [
        render_function(fn, parse_result, config)
        for fn in parse_result.get("functions", [])
    ]

    # --- Final Output ---
    output = render_builtin(constants_output, enums_output, constructors_output, functions_output, namespace, use_namespace)
    with gml_path.open("w", encoding="utf-8") as file:
        file.write(output)

    print(f"[GMBridge][generate] Generated GML stub: {gml_path}")
    return str(gml_path)
