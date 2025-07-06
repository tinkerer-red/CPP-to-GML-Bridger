# generator/cpp_bridge_gen.py
import os
from pathlib import Path
from string import Template

# Load templates…
TEMPLATES_DIR     = Path(__file__).parent / "templates"
BRIDGE_HEADER_TPL = Template((TEMPLATES_DIR / "bridge_header.cpp.tpl").read_text(encoding="utf-8"))
REF_MANAGER_H     = (TEMPLATES_DIR / "RefManager.h").read_text(encoding="utf-8")
REF_MANAGER_CPP   = (TEMPLATES_DIR / "RefManager.cpp").read_text(encoding="utf-8")

# Constants for 64-bit limits
INT64_MIN = "-9223372036854775808"
INT64_MAX = "9223372036854775807"

import re

def resolve_type(type_name: str, typedef_map: dict[str,str]) -> str:
    """Chase typedefs until we find the underlying type."""
    seen = set()
    result = type_name.strip()
    while result in typedef_map and result not in seen:
        seen.add(result)
        result = typedef_map[result].strip()
    return result

def generate_struct_json_overloads(struct_name: str,
                                   fields: list[dict],
                                   parse_result: dict) -> str:
    """
    Emits to_json, from_json, and REFMAN_REGISTER_TYPE for struct_name,
    with support for:
      - numeric types (including enums)
      - std::string
      - fixed-size char arrays
      - nested structs (via ADL)
      - pointer/ref fields (via RefManager.get_ref_for_ptr / retrieve)
      - TODO comments for anything else
    """
    typedef_map = parse_result["typedef_map"]
    struct_set  = set(parse_result["struct_fields"])
    enum_set    = set(parse_result["enums"])

    def classify_field(field: dict) -> str:
        # We use the parser’s canonical_type for integer/enum detection,
        # and never consult treat_int64_as_ref here.
        canonical  = field["canonical_type"]
        array_size = field.get("array_size")
        resolved   = resolve_type(field["type"], typedef_map)

        # fixed-size char arrays
        if array_size and resolved == "char":
            return "char_array"

        integer_types = {
            "bool","int","float","double",
            "int8_t","uint8_t","int16_t","uint16_t",
            "int32_t","uint32_t","int64_t","uint64_t"
        }

        # enums or 64-bit integer handles
        if canonical in enum_set or canonical in integer_types:
            return "numeric"

        # std::string or C strings
        if canonical in ("std::string","char*","const char*"):
            return "string"

        # nested structs
        if canonical in struct_set:
            return "struct"

        # true pointers (declared with *)
        if field["type"].strip().endswith("*"):
            return "ref_handle"

        # anything else is unknown—emit a TODO
        return "unknown"
    
    GEN_HANDLERS = {
        "numeric": (
            lambda name, array_size=None:
                f'    jsonValue["{name}"] = o.{name};',
            lambda name, array_size=None:
                f'    jsonValue.at("{name}").get_to(o.{name});'
        ),
        "string": (
            lambda name, array_size=None:
                f'    jsonValue["{name}"] = o.{name};',
            lambda name, array_size=None:
                f'    jsonValue.at("{name}").get_to(o.{name});'
        ),
        "char_array": (
            lambda name, array_size:
                f'    jsonValue["{name}"] = '
                f'std::string(o.{name}, strnlen(o.{name}, {array_size}));',
            lambda name, array_size: "\n".join([
                f'    {{',
                f'        auto tmp = jsonValue.at("{name}").get<std::string>();',
                f'        std::strncpy(o.{name}, tmp.c_str(), {array_size});',
                f'        o.{name}[{array_size}-1] = \'\\0\';',
                f'    }}'
            ])
        ),
        "struct": (
            lambda name, array_size=None:
                f'    jsonValue["{name}"] = o.{name};',
            lambda name, array_size=None:
                f'    jsonValue.at("{name}").get_to(o.{name});'
        ),
        "ref_handle": (
            # to_json: export the GML handle for this pointer field
            lambda name, array_size=None:
                (f'    jsonValue["{name}"] = '
                 f'RefManager::instance().get_ref_for_ptr('
                 f'const_cast<void*>(o.{name}));'),
            # from_json: retrieve pointer by handle and assign back
            lambda name, array_size=None, field=None: "\n".join([
                f'    {{',
                f'        auto handleString = jsonValue.at("{name}").get<std::string>();',
                f'        void* ptr = RefManager::instance().retrieve(handleString);',
                f'        o.{name} = static_cast<'
                f'{resolve_type(field["type"], typedef_map)}*>(ptr);',
                f'    }}'
            ])
        ),
    }

    lines = []
    # to_json
    lines.append(f'inline void to_json(json& jsonValue, const {struct_name}& o) {{')
    lines.append('    jsonValue = json::object();')
    for field in fields:
        name       = field["name"]
        kind       = classify_field(field)
        array_size = field.get("array_size")
        handler    = GEN_HANDLERS.get(kind)

        if handler is not None:
            if kind == "char_array":
                snippet = handler[0](name, array_size)
            else:
                snippet = handler[0](name, None)
            lines.append(snippet)
        else:
            lines.append(f'    // TODO handle {name}:{field["type"]}')

    lines.append('}')

    # from_json
    lines.append('')
    lines.append(f'inline void from_json(const json& jsonValue, {struct_name}& o) {{')
    for field in fields:
        name       = field["name"]
        kind       = classify_field(field)
        array_size = field.get("array_size")
        handler    = GEN_HANDLERS.get(kind)

        if handler is not None:
            if kind == "char_array":
                lines.append(handler[1](name, array_size))
            elif kind == "ref_handle":
                lines.append(handler[1](name, None, field))
            else:
                lines.append(handler[1](name, None))
        else:
            lines.append(f'    // TODO handle {name}:{field["type"]}')

    lines.append('}')

    # registration
    lines.append('')
    lines.append(f'REFMAN_REGISTER_TYPE({struct_name}, {struct_name});')

    return "\n".join(lines)

def order_structs_by_dependency(dependency_map: dict[str, list[str]]) -> list[str]:
    """
    dependency_map: map from struct_name to list of structs it depends on
    returns a list of struct_names in an order where dependencies come first
    """
    # 1) Build reverse adjacency: for each edge parent→child, record child→parent
    dependents: dict[str, list[str]] = {name: [] for name in dependency_map}
    for parent, children in dependency_map.items():
        for child in children:
            dependents[child].append(parent)

    # 2) Compute in-degree = number of dependencies each struct has
    in_degree: dict[str, int] = {
        name: len(children)
        for name, children in dependency_map.items()
    }

    # 3) Start with structs that have no dependencies
    processing_queue = [name for name, deg in in_degree.items() if deg == 0]
    sorted_list: list[str] = []

    # 4) Kahn’s algorithm
    while processing_queue:
        current = processing_queue.pop(0)
        sorted_list.append(current)
        # “Remove” edges from current to its dependents
        for parent in dependents[current]:
            in_degree[parent] -= 1
            if in_degree[parent] == 0:
                processing_queue.append(parent)

    # 5) Detect cycles
    if len(sorted_list) != len(dependency_map):
        raise ValueError("Cycle detected in struct dependencies")

    return sorted_list



def generate_cpp_bridge(parse_result, config):
    debug               = config.get("debug", True)
    functions           = parse_result["functions"]
    known_structs       = parse_result["struct_fields"].keys()
    func_ptr_aliases    = parse_result["function_ptr_aliases"]
    treat_int64_as_ref  = config.get("treat_int64_as_ref", False)

    header_file = config.get("header_file", "openxr.h").replace("\\", "/")
    namespace   = config.get("namespace", "XR")

    # 0) Build dependency graph: structName -> [list of nested struct names]
    struct_fields = parse_result["struct_fields"]
    struct_set    = set(struct_fields.keys())

    deps = {}
    for struct_name, fields in struct_fields.items():
        needed = []
        for f in fields:
            # resolve to canonical type (reuse your resolve_type logic)
            canon = resolve_type(f["type"], parse_result["typedef_map"])
            # if it’s one of your structs, record the dependency
            if canon in struct_set:
                needed.append(canon)
        deps[struct_name] = needed

    # Topologically sort so that nested structs come first
    ordered_structs = order_structs_by_dependency(deps)

    # 1) Struct constructors + JSON I/O (import then export)
    struct_constructors = []
    for name in ordered_structs:
        fields = parse_result["struct_fields"][name]
        # 1) Create function
        struct_constructors.append(f'''
// === Auto-generated bridge for {name} ===
extern "C" const char* __cpp_create_{name}() {{
    auto* obj = new {name}{{}};
    std::string _tmp_str = RefManager::instance().store("{name}", obj);
    return _tmp_str.c_str();
}}
'''.strip())

        # 2) JSON overloads
        struct_constructors.append(generate_struct_json_overloads(name, fields, parse_result))

    
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
