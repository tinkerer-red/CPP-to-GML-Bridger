import os

def generate_gml(parse_result, config):
    """
    Generates a GML wrapper script with namespaced functions,
    calling the external bridge layer.
    """
    extension_name = config["dll_name"]
    namespace = config["namespace"]

    ext_folder = os.path.join(config["output_folder"], "extensions", extension_name)
    os.makedirs(ext_folder, exist_ok=True)

    gml_path = os.path.join(ext_folder, f"{extension_name}.gml")

    with open(gml_path, "w", encoding="utf-8") as gml:
        gml.write(f"function {namespace}() {{\n")

        for func in parse_result.get("functions", []):
            gml_name = func["name"]
            gml.write(f"    /// @func {namespace}.{gml_name}\n")
            gml.write(f"    /// @desc {func.get('doc', f'Auto-wrapped function {gml_name}')}\n")

            return_type = func.get("return_category", 1)
            return_str = "Number" if return_type == 1 else "String"  # placeholder
            gml.write(f"    /// @return {{{return_str}}}\n")

            gml.write(f"    static {gml_name} = function(")
            gml.write(", ".join(arg["name"] for arg in func.get("args", [])))
            gml.write(") {\n")

            gml.write("        return external_call(\"__")
            gml.write(gml_name)
            gml.write("\"")
            if func.get("args"):
                gml.write(", ")
                gml.write(", ".join(arg["name"] for arg in func["args"]))
            gml.write(");\n")

            gml.write("    };\n\n")

        gml.write("}\n")

    print(f"Generated GML stub: {gml_path}")
