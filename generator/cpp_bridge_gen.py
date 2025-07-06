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

def classify_field(field: dict,
                   typedef_map: dict[str,str],
                   struct_set: set[str],
                   enum_set: set[str]) -> str:
    raw        = field["type"].strip()
    canonical  = field["canonical_type"].lower()
    array_size = field.get("array_size")

    # 1) fixed‐size char arrays
    if array_size and raw.rstrip("*").endswith("char"):
        return "char_array"
    # 2) all other C‐arrays
    if array_size:
        return "array"
    # 3) any raw pointer (T*, const T*, T**…) → handle
    if raw.endswith("*"):
        return "ref_handle"
    # 4) parser said “ref” (covers function‐pointer typedefs, flags‐as‐refs, void*, etc.)
    if field["usage_category"] == "ref":
        # but if it’s actually a nested struct, do struct instead
        if field["canonical_type"] in struct_set:
            return "struct"
        return "ref_handle"
    # 5) nested structs
    if field["canonical_type"] in struct_set:
        return "struct"
    # 6) numeric & enums
    integer_types = {
        "bool","int","float","double",
        "int8_t","uint8_t","int16_t","uint16_t",
        "int32_t","uint32_t","int64_t","uint64_t"
    }
    if canonical in integer_types or field["base_type"] in enum_set:
        return "numeric"
    # 7) strings
    if canonical in ("std::string","char*","const char*"):
        return "string"
    # fallback
    return "numeric"

def generate_struct_json_overloads(struct_name: str,
                                   fields: list[dict],
                                   parse_result: dict) -> str:
    typedef_map = parse_result["typedef_map"]
    struct_set  = set(parse_result["struct_fields"])
    enum_set    = set(parse_result["enums"])

    # Named handlers for pointer/handle fields
    def ref_to_json(name: str, sz: int=None, field: dict=None) -> str:
        """
        Emit a RefManager handle for any pointer‐typed field (including function pointers).
        """
        raw       = field["declared_type"]
        # strip all const so we can const_cast
        inner     = re.sub(r'\bconst\b\s*', '', raw).strip()
        return (
            f'    jsonValue["{name}"] = '
            f'RefManager::instance().get_ref_for_ptr('
            f'reinterpret_cast<void*>(const_cast<{inner}>(o.{name}))'
            f');'
        )

    def ref_from_json(name: str, sz: int=None, field: dict=None) -> str:
        """
        Retrieve a RefManager handle and cast it back to the exact declared type.
        """
        decl = field["declared_type"]
        return "\n".join([
            f'    {{',
            f'        auto handleString = jsonValue.at("{name}").get<std::string>();',
            f'        void* ptr = RefManager::instance().retrieve(handleString);',
            f'        o.{name} = reinterpret_cast<{decl}>(ptr);',
            f'    }}'
        ])

    GEN_HANDLERS = {
        "char_array": (
            lambda name, sz, field=None:
                f'    jsonValue["{name}"] = std::string(o.{name}, strnlen(o.{name}, {sz}));',
            lambda name, sz, field=None: "\n".join([
                f'    {{',
                f'        auto tmp = jsonValue.at("{name}").get<std::string>();',
                f'        std::strncpy(o.{name}, tmp.c_str(), {sz});',
                f'        o.{name}[{sz}-1] = \'\\0\';',
                f'    }}'
            ])
        ),
        "array": (
            lambda name, sz, field=None: "\n".join([
                f'    {{',
                f'        std::vector<{field["canonical_type"]}> tmp;',
                f'        tmp.reserve({sz});',
                f'        for (size_t i = 0; i < {sz}; ++i) tmp.push_back(o.{name}[i]);',
                f'        jsonValue["{name}"] = tmp;',
                f'    }}'
            ]),
            lambda name, sz, field=None: "\n".join([
                f'    {{',
                f'        auto tmp = jsonValue.at("{name}").get<std::vector<{field["canonical_type"]}>>();',
                f'        size_t n = std::min(tmp.size(), size_t({sz}));',
                f'        for (size_t i = 0; i < n; ++i) o.{name}[i] = tmp[i];',
                f'        for (size_t i = n; i < {sz}; ++i) o.{name}[i] = {field["canonical_type"]}();',
                f'    }}'
            ])
        ),
        "numeric": (
            lambda name, sz=None, field=None:
                f'    jsonValue["{name}"] = ({field["canonical_type"]})o.{name};',
            lambda name, sz=None, field=None: "\n".join([
                f'    {{',
                f'        {field["canonical_type"]} tmp = '
                f'jsonValue.at("{name}").get<{field["canonical_type"]}>();',
                f'        o.{name} = ({field["type"]})tmp;',
                f'    }}'
            ])
        ),
        "string": (
            lambda name, sz=None, field=None:
                f'    jsonValue["{name}"] = o.{name};',
            lambda name, sz=None, field=None:
                f'    jsonValue.at("{name}").get_to(o.{name});'
        ),
        "struct": (
            lambda name, sz=None, field=None:
                f'    jsonValue["{name}"] = o.{name};',
            lambda name, sz=None, field=None:
                f'    jsonValue.at("{name}").get_to(o.{name});'
        ),
        "ref_handle": (
            ref_to_json,
            ref_from_json
        ),
    }
    
    lines = []
    # to_json
    lines.append(f'inline void to_json(json& jsonValue, const {struct_name}& o) {{')
    lines.append('    jsonValue = json::object();')
    for field in fields:
        kind = classify_field(field, typedef_map, struct_set, enum_set)
        handler = GEN_HANDLERS[kind]
        lines.append(handler[0](
            field["name"],
            field.get("array_size"),
            field
        ))
    lines.append('}')

    # from_json
    lines.append(f'inline void from_json(const json& jsonValue, {struct_name}& o) {{')
    for field in fields:
        kind = classify_field(field, typedef_map, struct_set, enum_set)
        handler = GEN_HANDLERS[kind]
        lines.append(handler[1](
            field["name"],
            field.get("array_size"),
            field
        ))
    lines.append('}')



    # registration
    lines.append('')
    lines.append(f'REFMAN_REGISTER_TYPE({struct_name}, {struct_name});')
    return "\n".join(lines)


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

    # Only keep structs whose name is their own canonical type
    filtered_structs = [
        name for name in ordered_structs
        if resolve_type(name, parse_result["typedef_map"]) == name
    ]

    # 1) Struct constructors + JSON I/O (import then export)
    struct_constructors = []
    for name in filtered_structs:
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
