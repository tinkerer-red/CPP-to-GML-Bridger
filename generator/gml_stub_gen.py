# generator/gml_stub_gen.py
import re

def map_jsdoc_type(c_type, known_enums=None, namespace="", cull_enum=True):
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
    if t.startswith("uint") or "size_t" in t or "uintptr" in t:
        return "Real.Integer"
    if t == "void":
        return "Real"
    if t == "function" or t.startswith("pfn_"):
        return "Function"

    # 3) Structs
    if t.startswith("xr") or "struct" in t:
        # e.g. "xractionstategetinfo" → "Xractionstategetinfo" → Struct.XrActionStateGetInfo
        name = re.sub(r'\bstruct\b', '', t).strip()
        name = name[0].upper() + name[1:]
        return f"Struct.{name}"

    # 4) Fallback pointer
    if "*" in c_type:
        return "Pointer"

    return "UNKNOWN"


def generate_gml_stub(functions_dict, config):
    namespace      = config.get("namespace", "XR")
    enums          = functions_dict.get("enums", {})
    cull_enums     = config.get("cull_enum_names", True)
    known_enum_map = {k.lower(): k for k in enums.keys()}
    constants      = functions_dict.get("constants", {})
    known_structs  = functions_dict.get("known_structs", set())

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
        var _json = (typeof(_value) == "string") ? _value : json_stringify(_value);
        return __ref_set(_ref, _key, _json);
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
        if (string_pos("ref error", _ret)) { show_error(_ret, true); return undefined; }
        return _ret;
    };

    #region JsDocs
    /// @function ref_set_struct(ref, struct)
    /// @desc Overwrite all data for `ref` using a GML struct
    /// @param {String} ref
    /// @param {Struct} struct
    /// @returns {Bool}
    #endregion
    static ref_set_struct = function(_ref, _struct) {
        return __ref_set_struct(_ref, json_stringify(_struct));
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

    #region JsDocs
    /// @function ref_destroy(ref)
    /// @desc Destroy a single ref from the manager
    /// @param {String} ref
    /// @returns {Bool}
    #endregion
    static ref_destroy = function(_ref) {
        return __ref_destroy(_ref);
    };

    #region JsDocs
    /// @function ref_manager_flush()
    /// @desc Flush all data from the ref manager
    /// @returns {Bool}
    #endregion
    static ref_manager_flush = function() {
        return __ref_manager_flush();
    };
    #endregion
""")

    # --- Constants ---
    lines.append("    #region Constants")
    cull_consts = config.get("cull_constant_names", True)
    ns_prefix   = f"{namespace}_" if cull_consts else ""
    for name, val in constants.items():
        clean = name[len(ns_prefix):] if cull_consts and name.startswith(ns_prefix) else name
        if clean and clean[0].isdigit(): clean = "_" + clean
        lines.append(f"    static {clean} = {val};")
    lines.append("    #endregion\n")

    # --- Struct Constructors ---
    if known_structs:
        lines.append("    #region Struct Constructors")
        cull_structs = config.get("cull_struct_names", True)
        for s in sorted(known_structs):
            # derive a JS name: drop the namespace prefix if desired
            if cull_structs and s.lower().startswith(namespace.lower()):
                short = s[len(namespace):]
            else:
                short = s
            # camelCase for the ctor
            ctorBase = short[0].upper() + short[1:]
            jsName   = "create" + ctorBase

            lines.append("    #region JsDocs")
            lines.append(f"    /// @function {jsName}()")
            lines.append(f"    /// @desc Create a new `{s}` struct")
            lines.append(f"    /// @returns {{Struct.{s}}}")
            lines.append("    #endregion")
            lines.append(f"    static {jsName} = function() {{")
            lines.append(f"        return __create_{s}();")
            lines.append("    };")
            lines.append("")
        lines.append("    #endregion\n")

    # --- Enums ---
    lines.append("    #region Enums")
    for enum_name, data in enums.items():
        meta       = data["_meta"]
        pre, suf   = meta["base_prefix"], meta.get("base_suffix", "")
        field      = meta["short_name"] if cull_enums else enum_name

        lines.append(f"    static {field} = {{")
        for key, val in data.items():
            if key == "_meta": continue
            # clean name
            if cull_enums:
                clean = key[len(pre):] if key.startswith(pre) else key
                if suf and clean.endswith(suf): clean = clean[:-len(suf)]
            else:
                clean = f"{pre}{key}{suf}"
            if clean and clean[0].isdigit(): clean = "_" + clean
            lines.append(f"        {clean}: {val},")
        lines.append("    };")
        lines.append("")
    lines.append("    #endregion\n")

    # --- Functions ---
    lines.append("    #region Functions")
    cull_funcs = config.get("cull_function_names", True)

    for fn in functions_dict["functions"]:
        orig    = fn["name"]
        args    = fn["args"]
        has_buf = bool(args and "array_size" in args[-1])

        # build GML name
        if cull_funcs and orig.startswith("xr"):
            js_name = orig[2:]
            js_name = js_name[0].lower() + js_name[1:]
        else:
            js_name = orig

        # doc + code args (drop buffer if present)
        doc_args  = [a["name"] for a in args]
        if has_buf: doc_args = doc_args[:-1]
        code_args = [f"_{n}" for n in doc_args]

        # JsDocs
        lines.append("    #region JsDocs")
        lines.append(f"    /// @function {js_name}({', '.join(doc_args)})")
        lines.append(f"    /// @desc Bridges to {orig}")
        for a, nm in zip(args, doc_args):
            js_t = map_jsdoc_type(a["type"], known_enum_map, namespace, cull_enums)
            lines.append(f"    /// @param {{{js_t}}} {nm}")
        if has_buf:
            lines.append("    /// @returns {String}")
        else:
            rt    = fn.get("return_type", "void")
            js_rt = map_jsdoc_type(rt, known_enum_map, namespace, cull_enums)
            lines.append(f"    /// @returns {{{js_rt}}}")
        lines.append("    #endregion")

        # Stub
        lines.append(f"    static {js_name} = function({', '.join(code_args)}) {{")
        if has_buf:
            lines.append(f"        return __{orig}_noBuf({', '.join(code_args)});")
        else:
            lines.append(f"        var _ret = __{orig}({', '.join(code_args)});")
            lines.append('        if (string_pos("ref error", _ret)) { show_error(_ret, true); return undefined; }')
            lines.append("        return _ret;")
        lines.append("    };")
        lines.append("")

    lines.append("    #endregion\n")
    lines.append("}")
    lines.append(f"{namespace}();")

    return "\n".join(lines)
