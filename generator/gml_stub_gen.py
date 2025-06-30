# generator/gml_stub_gen.py
import re

def map_jsdoc_type(c_type, known_enums=None, namespace="", cull_enum=True):
    t = c_type.lower().replace('const ', '').replace('*', '').strip()

    # Known enum match
    if known_enums and t in known_enums:
        enum_name = known_enums[t]

        # choose short vs full based on cull_enum
        if cull_enum and enum_name.lower().startswith(namespace.lower()):
            short = enum_name[len(namespace):]
        else:
            short = enum_name

        return f"Constant.{namespace}.{short}"

    # Standard mappings
    if t in ("bool", "_bool"):
        return "Bool"
    if "char" in t or "string" in t:
        return "String"
    if t in ("float", "double"):
        return "Real"
    if t.startswith("int") or t in ("short", "long", "ssize_t", "intptr_t"):
        return "Real.Integer"
    if t.startswith("uint") or "size_t" in t or "uintptr" in t:
        return "Real.Integer"
    if t == "void":
        return "Real"
    if t == "function" or t.startswith("pfn_"):
        return "Function"

    # Structs
    if t.startswith("xr") or "struct" in t:
        name = t.replace("struct", "").strip()
        name = name[0].upper() + name[1:]
        return f"Struct.{name}"

    # Pointer fallback
    if "*" in c_type:
        return "Pointer"

    return "UNKNOWN"


def generate_gml_stub(functions_dict, config):
    namespace      = config.get("namespace", "XR")
    enums          = functions_dict.get("enums", {})
    cull_enums     = config.get("cull_enum_names", True)
    known_enum_map = {k.lower(): k for k in enums.keys()}

    lines = [
        "/**",
        f" * @self {namespace}",
        " */",
        f"function {namespace}() {{"
    ]



    # --- Cache Manager region ---
    lines.append("""
    #region Cache Manager
    #region JsDocs
    /// @function ref_set(ref, key, value)
    /// @desc Store a JSON-serializable value under `key` on `ref`
    /// @param {String} ref
    /// @param {String} key
    /// @param {Any}    value
    /// @returns {Bool}
    #endregion
    static ref_set = function(_ref, _key, _value) {
        return __ref_set(_ref, _key, _value);
    };

    #region JsDocs
    /// @function ref_get(ref, key)
    /// @desc Retrieve a value stored under `key`
    /// @param {String} ref
    /// @param {String} key
    /// @returns {String}
    #endregion
    static ref_get = function(_ref, _key) {
        var _ret = __ref_get(_ref, _key);
        if (string_pos("ref error", _ret)) {
            show_error(_ret, true);
            return undefined;
        }
        return _ret;
    };

    #region JsDocs
    /// @function ref_set_struct(ref, struct)
    /// @desc Overwrite all data for `ref` using a GML struct
    /// @param {String} ref
    /// @param {Struct} struct
    /// @returns {Bool}
    #endregion
    static ref_set_struct = function(_ref, _data) {
        return __ref_set_struct(_ref, json_stringify(_data));
    };

    #region JsDocs
    /// @function ref_get_struct(ref)
    /// @desc Retrieve stored data for `ref` as a GML struct
    /// @param {String} ref
    /// @returns {Struct}
    #endregion
    static ref_get_struct = function(_ref) {
        return json_parse(__ref_json(_ref));
    };

    #region JsDocs
    /// @function ref_json(ref)
    /// @desc Get raw JSON for debugging
    /// @param {String} ref
    /// @returns {String}
    #endregion
    static ref_json = function(_ref) {
        return __ref_json(_ref);
    };
    #endregion
""")
    
    # --- constants at the top ---
    lines.append(f"    #region Constants")
    # Toggle stripping the namespace prefix from constant names
    cull_consts = config.get("cull_constant_names", True)
    constants = functions_dict.get("constants", {})

    # Build the namespace prefix, e.g. "XR_"
    ns_prefix = f"{namespace}_" if cull_consts else ""

    for const_name, const_val in constants.items():
        if cull_consts and const_name.startswith(ns_prefix):
            clean_name = const_name[len(ns_prefix):]
        else:
            clean_name = const_name
        lines.append(f"    static {clean_name} = {const_val};")
    lines.append(f"    #endregion")
    lines.append("")



    # --- enums at the top ---
    lines.append(f"    #region Enums")
    cull = config.get("cull_enum_names", True)

    for enum_name, enum_data in enums.items():
        meta          = enum_data["_meta"]
        base_prefix   = meta["base_prefix"]
        base_suffix   = meta.get("base_suffix", "")

        # choose field name: stripped short_name vs full enum_name
        gml_field = meta["short_name"] if cull else enum_name

        lines.append(f"    static {gml_field} = {{")
        for key, val in enum_data.items():
            if key == "_meta":
                continue

            if cull:
                # remove parser-computed prefix & suffix
                clean_key = key
                if clean_key.startswith(base_prefix):
                    clean_key = clean_key[len(base_prefix):]
                if base_suffix and clean_key.endswith(base_suffix):
                    clean_key = clean_key[:-len(base_suffix)]
            else:
                # reconstruct the original entry name
                clean_key = f"{base_prefix}{key}{base_suffix}"

            # ensure it doesn’t start with a digit
            if clean_key and clean_key[0].isdigit():
                clean_key = "_" + clean_key

            lines.append(f"        {clean_key}: {val},")
        lines.append("    };")
        lines.append("")

    lines.append(f"    #endregion")
    lines.append("")



    # --- functions ---
    lines.append(f"    #region Functions")
    # toggle stripping the "xr" prefix from GML names
    cull_funcs = config.get("cull_function_names", True)

    for fn in functions_dict["functions"]:
        orig_name = fn["name"]

        # detect if the last arg was a C-style array (parser added "array_size")
        has_array_arg = bool(fn["args"] and "array_size" in fn["args"][-1])

        # derive GML method name
        if cull_funcs and orig_name.startswith("xr"):
            js_name = orig_name[2:]
            js_name = js_name[0].lower() + js_name[1:]
        else:
            js_name = orig_name

        # prepare doc & code arg lists, dropping buffer if present
        doc_args = [arg["name"] or f"a{i}" for i, arg in enumerate(fn["args"])]
        if has_array_arg:
            doc_args = doc_args[:-1]
        code_args = [f"_{n}" for n in doc_args]

        # JsDoc region
        lines.append(f"    #region JsDocs")
        lines.append(f"    /// @function {js_name}({', '.join(doc_args)})")
        lines.append(f"    /// @desc Bridges to {orig_name}")

        # @param tags (skip buffer)
        for arg, name in zip(fn["args"], doc_args):
            js_type = map_jsdoc_type(arg["type"], known_enum_map, namespace, cull_enums)
            lines.append(f"    /// @param {{{js_type}}} {name}")

        # @returns: String if we dropped a buffer, else the mapped return type
        if has_array_arg:
            lines.append(f"    /// @returns {{String}}")
        else:
            rt    = fn.get("return_type", "double")
            js_rt = map_jsdoc_type(rt, known_enum_map, namespace, cull_enums)
            lines.append(f"    /// @returns {{{js_rt}}}")

        lines.append(f"    #endregion")

        # function signature
        lines.append(f"    static {js_name} = function({', '.join(code_args)}) {{")

        if has_array_arg:
            # call the no-buffer C++ wrapper and return the string directly
            lines.append(f"        return __{orig_name}_noBuf({', '.join(code_args)});")
        else:
            lines.append(f"        var _ret = __{orig_name}({', '.join(code_args)});")
            lines.append(f"        if (string_pos(\"ref error\", _ret)) {{")
            lines.append(f"            show_error(_ret, true);")
            lines.append(f"            return undefined;")
            lines.append(f"        }}")
            lines.append(f"        return _ret;")

        lines.append(f"    }};")
        lines.append("")  # blank line between functions

    lines.append(f"    #endregion")
    lines.append("")  # trailing blank line



    lines.append("}")
    lines.append(f"{namespace}();")
    return "\n".join(lines)
