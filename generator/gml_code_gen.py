# generator/gml_stub_gen.py

import os
import re
from pathlib import Path

def map_jsdoc_type(c_type: str,
                   known_enums: dict = None,
                   namespace: str = "",
                   cull_enum: bool = True) -> str:
    """
    Map a C type (possibly with const/*) to a GML JsDoc type.
    """
    t = c_type.lower().replace('const ', '').replace('*', '').strip()

    # 1) Enums
    if known_enums and t in known_enums:
        enum_name = known_enums[t]
        if cull_enum and enum_name.lower().startswith(namespace.lower()):
            short = enum_name[len(namespace):]
        else:
            short = enum_name
        return f"Constant.{namespace}.{short}"

    # 2) Primitives
    if t in ("bool", "_bool"):
        return "Bool"
    if "char" in t or "string" in t:
        return "String"
    if t in ("float", "double"):
        return "Real"
    if t.startswith("int") or t in ("short", "long", "ssize_t", "intptr_t"):
        return "Real.Integer"
    if t.startswith("uint") or t.startswith("unsigned ") or \
       "size_t" in t or "uintptr" in t:
        return "Real.Integer"
    if t == "void":
        return "Real"
    if t == "function":
        return "Function"

    # 3) Structs
    if t.startswith(namespace.lower()) or "struct" in t:
        name = re.sub(r'\bstruct\b', '', t).strip()
        name = name[0].upper() + name[1:]
        return f"Struct.{name}"

    # 4) Fallback pointer
    if "*" in c_type:
        return "Pointer"

    return "UNKNOWN"


def generate_gml(parse_result, exports, config):
    """
    Generates a GML wrapper script in:
      output/extensions/<project_name>/<project_name>.gml

    Returns the path to the generated .gml file.
    """
    # ——— Prepare paths & names ———
    project_root = Path.cwd()
    input_root   = project_root / "input"
    output_root  = project_root / "output"

    project_name = config.get("project_name") or config["dll_name"]
    namespace    = config.get("namespace", project_name)

    extension_folder = output_root / "extensions" / project_name
    extension_folder.mkdir(parents=True, exist_ok=True)

    gml_path = extension_folder / f"{project_name}.gml"

    # ——— Setup known-enum map for type mapping ———
    enums_dict      = parse_result.get("enums", {})
    known_enum_map  = {key.lower(): key for key in enums_dict.keys()}
    cull_enums_flag = config.get("cull_enum_names", True)

    # ——— Begin writing ———
    with gml_path.open("w", encoding="utf-8") as file:
        file.write(f"/** @self {namespace} */\n")
        file.write(f"function {namespace}() {{\n\n")

        # --- Constants ---
        constants_dict = parse_result.get("constants", {})
        if constants_dict:
            file.write("    // --- Constants ---\n")
            cull_constants = config.get("cull_constant_names", True)
            prefix         = f"{namespace}_" if cull_constants else ""
            for full_name, value in constants_dict.items():
                clean_name = (full_name[len(prefix):]
                              if cull_constants and full_name.startswith(prefix)
                              else full_name)
                if clean_name and clean_name[0].isdigit():
                    clean_name = "_" + clean_name
                file.write(f"    static {clean_name} = {value};\n")
            file.write("\n")

        # --- Struct Constructors ---
        known_structs = parse_result.get("known_structs", set())
        if known_structs:
            file.write("    // --- Struct Constructors ---\n")
            cull_structs = config.get("cull_struct_names", True)
            for struct_name in sorted(known_structs):
                if cull_structs and struct_name.lower().startswith(namespace.lower()):
                    short_name = struct_name[len(namespace):]
                else:
                    short_name = struct_name
                ctor_base = short_name[0].upper() + short_name[1:]
                js_ctor   = "create" + ctor_base

                file.write(f"    /// @function {js_ctor}()\n")
                file.write(f"    /// @desc Create a new `{struct_name}` struct\n")
                file.write(f"    /// @returns {{Struct.{struct_name}}}\n")
                file.write(f"    static {js_ctor} = function() {{\n")
                file.write(f"        return __create_{struct_name}();\n")
                file.write("    };\n\n")

        # --- Enums ---
        if enums_dict:
            file.write("    // --- Enums ---\n")
            for enum_name, enum_data in enums_dict.items():
                meta    = enum_data.get("_meta", {})
                prefix  = meta.get("base_prefix", "")
                suffix  = meta.get("base_suffix", "")
                field   = meta.get("short_name", enum_name) if cull_enums_flag else enum_name

                file.write(f"    static {field} = {{\n")
                for key, val in enum_data.items():
                    if key == "_meta":
                        continue
                    clean_key = key
                    if cull_enums_flag and clean_key.startswith(prefix):
                        clean_key = clean_key[len(prefix):]
                        if suffix and clean_key.endswith(suffix):
                            clean_key = clean_key[:-len(suffix)]
                    if clean_key and clean_key[0].isdigit():
                        clean_key = "_" + clean_key
                    file.write(f"        {clean_key}: {val},\n")
                file.write("    };\n\n")

        # --- Functions ---
        functions_list = parse_result.get("functions", [])
        if functions_list:
            file.write("    // --- Functions ---\n")
            cull_functions = config.get("cull_function_names", True)

            for fn in functions_list:
                orig_name = fn["name"]
                doc_desc  = fn.get("doc", f"Auto-wrapped function {orig_name}")
                args_info = fn.get("args", [])
                ret_meta  = fn.get("return_meta", {})
                ret_type  = fn.get("return_type", "")

                # build JS name
                if cull_functions and orig_name.startswith(namespace.lower()):
                    js_name = orig_name[len(namespace):]
                    js_name = js_name[0].lower() + js_name[1:]
                else:
                    js_name = orig_name

                # JsDoc
                file.write(f"    /// @function {namespace}.{js_name}({', '.join(a['name'] for a in args_info)})\n")
                file.write(f"    /// @desc {doc_desc}\n")
                for arg in args_info:
                    js_type = map_jsdoc_type(arg["type"], known_enum_map, namespace, cull_enums_flag)
                    file.write(f"    /// @param {{{js_type}}} {arg['name']}\n")
                # return JsDoc
                if ret_meta.get("extension_type") == "void":
                    file.write("    /// @returns {Undefined}\n")
                else:
                    js_ret = map_jsdoc_type(ret_type, known_enum_map, namespace, cull_enums_flag)
                    file.write(f"    /// @returns {{{js_ret}}}\n")

                # Stub body
                file.write(f"    static {js_name} = function({', '.join(a['name'] for a in args_info)}) {{\n")

                # big-number args → string
                call_args = []
                for arg in args_info:
                    name = arg["name"]
                    if arg.get("is_unsupported_numeric", False):
                        file.write(f"        var {name}_str = string({name});\n")
                        call_args.append(f"{name}_str")
                    else:
                        call_args.append(name)

                # call
                if ret_meta.get("extension_type") == "void":
                    file.write(f"        __{orig_name}({', '.join(call_args)});\n")
                    file.write("        return undefined;\n")
                else:
                    file.write(f"        var _result = __{orig_name}({', '.join(call_args)});\n")
                    if ret_meta.get("is_unsupported_numeric", False):
                        file.write("        return int64(_result);\n")
                    else:
                        file.write("        return _result;\n")

                file.write("    };\n\n")

        # close namespace
        file.write("}\n")
        file.write(f"{namespace}();\n")

    print(f"[GMBridge][generate] Generated GML stub: {gml_path}")
    return str(gml_path)
