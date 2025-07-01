# generator/cpp_bridge_gen.py
import os
from pathlib import Path
from string import Template

# Load your templates…
TEMPLATES_DIR     = Path(__file__).parent / "templates"
BRIDGE_HEADER_TPL = Template((TEMPLATES_DIR / "bridge_header.cpp.tpl").read_text())
REF_MANAGER_H     = (TEMPLATES_DIR / "RefManager.h").read_text()
REF_MANAGER_CPP   = (TEMPLATES_DIR / "RefManager.cpp").read_text()

# Constants for 64-bit limits
INT64_MIN = "-9223372036854775808"
INT64_MAX = "9223372036854775807"

def generate_cpp_bridge(parse_result, config):
    debug               = config.get("debug", True)
    functions           = parse_result["functions"]
    known_structs       = parse_result["known_structs"]
    func_ptr_aliases    = parse_result["function_ptr_aliases"]
    treat_int64_as_ref  = config.get("treat_int64_as_ref", False)

    header_file = config.get("header_file", "openxr.h").replace("\\", "/")
    namespace   = config.get("namespace", "XR")

    # 1) Struct constructors
    struct_constructors = []
    for s in sorted(known_structs):
        struct_constructors.append(f'''\
// Allocate a fresh {s} and hand back a GML ref
extern "C" const char* __create_{s}() {{
    auto* obj = new {s}{{}};  
    std::string ref = RefManager::instance().store("{s}", obj);
    return ref.c_str();
}}''')

    # 2) Function bridges
    function_bridges = []
    for fn in functions:
        name     = fn["name"]
        ret_meta = fn["return_meta"]
        ret_ext  = ret_meta["extension_type"]
        ret_cat  = ret_meta["usage_category"]
        canon_rt = ret_meta["canonical_type"]

        # pick return signature and default error return
        if ret_ext == "double":
            ret_sig, err_return = "double", "std::numeric_limits<double>::quiet_NaN()"
        elif ret_ext in ("ref", "string"):
            ret_sig, err_return = "const char*", "\"\""
        else:
            ret_sig, err_return = "const char*", "\"\""



        # build argument decls, conversions, and call args 
        decls, converts, call_args = [], [], []
        for i, arg in enumerate(fn["args"]):
            nm  = arg["name"]
            base = arg["base_type"]
            ext = arg["extension_type"]
            cat = arg["usage_category"]

            if cat == "double":
                decls.append(f"double {nm}")
                call_args.append(nm)

            elif cat == "string":
                decls.append(f"const char* {nm}")
                call_args.append(nm)

            elif cat == "ref":
                decls.append(f"const char* {nm}_ref")
                converts.append(f"""
    // Convert Argument{i} ({nm}) to {base}
    void* {nm}_ptr = RefManager::instance().retrieve({nm}_ref);
    if (!{nm}_ptr) return {err_return};
    {base}* {nm} = static_cast<{base}*>({nm}_ptr);""")
                call_args.append(f"{nm}")

            else:
                decls.append(f"/* unsupported: {arg['declared_type']} */ const char* {nm}")
                call_args.append(nm)



        # assemble the function bridge
        fb = [f"// Bridge for {name}"]
        fb.append(f'extern "C" {ret_sig} __{name}({", ".join(decls)}) {{')

        if debug:
            fb.append(f'    std::cout << "[GMBridge] Called {name}" << std::endl;')

        fb += [f"    {line}" for line in converts if line.strip()]
        fb.append(f"\n    {canon_rt} result = {name}({', '.join(call_args)});")

        if ret_cat == "double":
            if not treat_int64_as_ref and canon_rt == "int64_t":
                fb.append(f"""\
    if (result < {INT64_MIN} || result > {INT64_MAX}) {{
        return {err_return};
    }}""")
            elif not treat_int64_as_ref and canon_rt == "uint64_t":
                fb.append(f"""\
    if (result > {INT64_MAX}) {{
        return {err_return};
    }}""")
            fb.append("    return static_cast<double>(result);")

        elif ret_cat == "ref":
            fb.append(f"""\
    _tmp_str = RefManager::instance().store("{ret_meta['base_type']}", result);
    return _tmp_str.c_str();""")

        elif ret_cat == "string":
            fb.append("    return result;")

        else:
            fb.append(f"    return {err_return};")

        fb.append("}\n")
        function_bridges.append("\n".join(fb))

    # 3) Fill in the header template
    bridge_cpp = BRIDGE_HEADER_TPL.substitute({
        "HEADER_FILE":         header_file,
        "REF_MANAGER_BRIDGES": "",  
        "STRUCT_CONSTRUCTORS": "\n".join(struct_constructors),
        "FUNCTION_BRIDGES":    "\n".join(function_bridges)
    })

    return {
        config["output_cpp_file"]: bridge_cpp,
        "RefManager.h": REF_MANAGER_H,
        "RefManager.cpp": REF_MANAGER_CPP
    }
