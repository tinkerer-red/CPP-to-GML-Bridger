from string import Template
import re

# --- Templates ---
template_wrapper_namespaced = Template("""/** @self $Namespace */
function $Namespace() {
    #region Constants
$Constants
    #endregion

    #region Constructors
$Constructors
    #endregion
    
    #region Enums
$Enums
    #endregion
    
    #region Functions
$Functions
    #endregion
}
$Namespace();
""")
template_wrapper_nonnamespaced = Template("""#region Constants
$Constants
#endregion
                                          
#region Constructors
$Constructors
#endregion
                                          
#region Enums
$Enums
#endregion
                                          
#region Functions
$Functions
#endregion
""")
template_constant_namespaced = Template("    static $ConstName = $ConstValue;")
template_constant_nonnamespaced = Template("#macro $ConstName $ConstValue")
template_enum_namespaced = Template("""    static $EnumName = {
$Members
    };""")
template_enum_nonnamespaced = Template("""enum $EnumName {
$Members
};""")
template_function_namespaced = Template("""    #region JsDocs
    /// @function $Namespace.$Name($ArgsDoc)
    /// @desc $Description
$ParamsDocs
    /// @returns {$Return}
    #endregion
    static $Name = function($ArgsCode) {
$Body
    };""")
template_function_nonnamespaced = Template("""#region JsDocs
/// @function $Name($ArgsDoc)
/// @desc $Description
$ParamsDocs
/// @returns {$Return}
#endregion
function $Name($ArgsCode) {
$Body
};""")
template_constructor_namespaced = Template("""    #region JsDocs
/// @function $Namespace.$Name($ArgsDoc)
    /// @desc $Description
$ParamsDocs
    /// @returns {$Return}
    #endregion
    static $Name = function($ArgsCode) constructor {
$Body
    };""")
template_constructor_nonnamespaced = Template("""#region JsDocs
/// @function $Name($ArgsDoc)
/// @desc $Description
$ParamsDocs
/// @returns {$Return}
#endregion
function $Name($ArgsCode) constructor {
$Body
};""")

def map_jsdobase_type(base_type: str, type: str, canonical_type: str, parse_result: dict, config: dict) -> str:
    """
    Map any C type to a GML JsDoc type, using parse_result enums and structs.
    """
    namespace = config.get("namespace", "")
    strip_ns = config.get("strip_namespace_from_symbols", True)
    lc = canonical_type.lower().replace('const ', '').replace('*', '').strip()

    # Enums
    enums = parse_result.get("enums", {})
    if base_type in enums:
        enum_name = base_type
        if strip_ns:
            enum_name = strip_namespace_prefix(base_type, namespace)
        return f"Constant.{namespace}.{enum_name}" if namespace else f"Constant.{enum_name}"

    # Structs
    structs = parse_result.get("struct_fields", {})
    if base_type.startswith("struct ") or base_type in structs or type in structs:
        struct_name = type
        if strip_ns:
            struct_name = strip_namespace_prefix(struct_name, namespace)
        return f"Struct.{namespace}.{struct_name}" if namespace else f"Struct.{struct_name}"

    # Primitives
    if lc in {"bool", "_bool"}:
        return "Bool"
    if "char" in lc or "string" in lc:
        return "String"
    if lc in {"float", "double"}:
        return "Real"
    if lc.startswith("int") or lc in {"short", "long", "ssize_t", "intptr_t", "long long"}:
        return "Real.Integer"
    if lc.startswith("uint") or lc.startswith("unsigned ") or "size_t" in lc or "uintptr" in lc:
        return "Real.Integer"
    if lc == "void":
        return "Real"
    if "*" in base_type:
        return "Pointer"

    return "UNKNOWN"

def strip_namespace_prefix(name, namespace):
    if not namespace:
        return name
    if not name:
        return name

    lower_name = name.lower()
    lower_namespace = namespace.lower()

    # Remove direct match prefix (with or without underscores)
    for variant in [lower_namespace, f"__{lower_namespace}_", f"{lower_namespace}_"]:
        if lower_name.startswith(variant):
            stripped = name[len(variant):]
            return stripped.lstrip("_")  # clean any remaining underscores

    # Also strip if name starts with the namespace directly (case-insensitive)
    if lower_name.startswith(lower_namespace):
        return name[len(namespace):].lstrip("_")

    return name

# --- Begin Extraction Functions ---
def render_constant(name: str, value, namespace: str, strip_namespace: bool) -> str:
    use_namespace = bool(namespace.strip())
    if strip_namespace:
        name = strip_namespace_prefix(name, namespace)
    tpl = template_constant_namespaced if use_namespace else template_constant_nonnamespaced
    return tpl.substitute(ConstName=name, ConstValue=value)

def render_enum(enum_name: str, members_dict: dict, namespace: str, strip_namespace: bool) -> str:
    use_namespace = bool(namespace.strip())
    if strip_namespace:
        enum_name = strip_namespace_prefix(enum_name, namespace)
        members_dict = {strip_namespace_prefix(k, namespace): v for k, v in members_dict.items()}
    if use_namespace:
        members_str = ",\n".join(f"        {k}: {v}" for k, v in members_dict.items())
        tpl = template_enum_namespaced
    else:
        members_str = ",\n".join(f"    {k} = {v}" for k, v in members_dict.items())
        tpl = template_enum_nonnamespaced
    return tpl.substitute(EnumName=enum_name, Members=members_str)

def render_function(func: dict, parse_result: dict, config: dict) -> str:
    """
    Render a single function binding, using full parse_result for type mapping.
    """
    namespace = config.get("namespace", "")
    strip_ns = config.get("strip_namespace_from_symbols", True)
    use_ns = bool(namespace)
    
    name = func["name"]
    if strip_ns:
        name = strip_namespace_prefix(name, namespace)

    args = func.get("args", [])
    args_doc = ", ".join(a["name"] for a in args)
    args_code = ", ".join(f"_{a['name']}" for a in args)
    params_docs = "\n".join(
        f"    /// @param {{{map_jsdobase_type(arg['base_type'], arg['type'], arg['canonical_type'], parse_result, config)}}} {arg['name']}\t\t\t{{{arg['base_type']}}}\t{{{arg['type']}}}\t{{{arg['canonical_type']}}}"
        for arg in args
    )

    ret_meta = func.get("return_meta", {})
    ret_raw = func.get("return_type", "")
    ret_doc = "Undefined" if ret_meta.get("extension_type") == "void" else map_jsdobase_type(ret_meta.get("base_type"), ret_raw, ret_meta.get("canonical_type"), parse_result, config)

    # build call body
    call_args = []
    body_lines = []
    for a in args:
        argn = a["name"]
        if a.get("is_unsupported_numeric", False):
            body_lines.append(f"        var {argn}_str = string(_{argn});")
            call_args.append(f"{argn}_str")
        else:
            call_args.append(f"_{argn}")
    if ret_meta.get("extension_type") == "void":
        body_lines.append(f"        __{func['name']}({', '.join(call_args)});")
        body_lines.append("        return undefined;")
    else:
        body_lines.append(f"        var _result = __{func['name']}({', '.join(call_args)});")
        if ret_meta.get("is_unsupported_numeric", False):
            body_lines.append("        return int64(_result);")
        else:
            body_lines.append("        return _result;")

    tpl = template_function_namespaced if use_ns else template_function_nonnamespaced
    return tpl.substitute(
        Namespace=namespace,
        Name=name,
        Description=func.get("doc", f"Auto-wrapped function {name}"),
        ArgsDoc=args_doc,
        ParamsDocs=params_docs,
        Return=ret_doc,
        ArgsCode=args_code,
        Body="\n".join(body_lines)
    )

def render_constructor(struct_name: str, namespace: str, strip_namespace: bool) -> str:
    use_namespace = bool(namespace.strip())
    ctor_base = struct_name[0].upper() + struct_name[1:]
    func_name = f"create{ctor_base}"
    if strip_namespace:
        func_name = strip_namespace_prefix(func_name, namespace)
    doc = f"Create a new `{struct_name}` struct"
    ret_type = f"Struct.{struct_name}"
    args_code = ""
    args_doc = ""
    params_docs = ""
    body = f"        return __create_{struct_name}();"
    tpl = template_constructor_namespaced if use_namespace else template_constructor_nonnamespaced
    return tpl.substitute(
        Namespace=namespace,
        Name=func_name,
        Description=doc,
        ArgsDoc=args_doc,
        ParamsDocs=params_docs,
        Return=ret_type,
        ArgsCode=args_code,
        Body=body
    )

def render_builtin(constants, enums, constructors, functions, namespace, namespaced):
    tpl = template_wrapper_namespaced if namespaced else template_wrapper_nonnamespaced
    return tpl.substitute(
        Namespace=namespace,
        Constants="\n".join(constants),
        Enums="\n".join(enums),
        Constructors="\n".join(constructors),
        Functions="\n".join(functions)
    )
    