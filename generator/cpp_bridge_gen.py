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

    # 1) fixed-size char arrays
    if array_size and raw.rstrip("*").endswith("char"):
        return "char_array"
    # 2) all other C-arrays
    if array_size:
        return "array"
    # 3) any raw pointer (T*, const T*, T**…) → handle
    if raw.endswith("*"):
        return "ref_handle"
    # 4) function-pointer typedefs → handle
    if field.get("is_function_ptr", False):
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
    if canonical in integer_types or field["is_enum"]:
        return "numeric"
    # 7) strings
    if field["extension_type"] == "string" and not field["is_ref"]:
        return "string"
    # 8) refs caught here (in case classify_c_type set is_ref on some pointer-like)
    if field.get("is_ref", False):
        return "ref_handle"
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
                f'        {field["base_type"]} tmp = '
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
        fn_name     = fn["name"]
        ret_meta = fn["return_meta"]
        ret_ext  = ret_meta["extension_type"]
        canon_rt = ret_meta["canonical_type"]

        # pick return signature and default error return
        if ret_ext == "double":
            ret_sig, err_return = "double", "std::numeric_limits<double>::quiet_NaN()"
        elif ret_ext in ("ref", "string"):
            ret_sig, err_return = "const char*", "\"\""
        else:
            ret_sig, err_return = "const char*", "\"\""



        # Build argument decls, conversions, and call_args:
        decls, converts, call_args = [], [], []
        for i, arg in enumerate(fn["args"]):
            arg_name         = arg["name"]
            base_type    = arg["base_type"]
            canonical    = arg["canonical_type"].lower()
            is_big       = arg["is_unsupported_numeric"]
            is_ref       = arg["is_ref"]
            ext          = arg["extension_type"]

            # 1) Big integers → receive as string, parse back
            if is_big:
                decls.append(f"const char* {name}_str")
                # Use the real declared_type (e.g. XrInstance) for the local variable
                if canonical.startswith("u"):
                    converts.append(f"// Parse big unsigned integer Argument{i} ({name})")
                    converts.append(f"{arg['declared_type']} {name} = static_cast<{arg['declared_type']}>(std::stoull({name}_str));")
                else:
                    converts.append(f"// Parse big signed integer Argument{i} ({name})")
                    converts.append(f"{arg['declared_type']} {name} = static_cast<{arg['declared_type']}>(std::stoll({name}_str));")
                call_args.append(name)

            # 2) Standard numerics (float, double, int32, bool, enum)
            elif ext == "double":
                decls.append(f"double {arg_name}")
                call_args.append(arg_name)

            # 3) Plain strings (const char*, std::string)
            elif ext == "string":
                decls.append(f"const char* {arg_name}")
                call_args.append(arg_name)

            # 4) Refs (pointers to structs or function pointers)
            elif is_ref:
                decls.append(f"const char* {arg_name}_ref")
                converts.append(f"// Convert Argument{i} ({arg_name}) to {base_type}")
                converts.append(f"void* {arg_name}_ptr = RefManager::instance().retrieve({arg_name}_ref);")
                converts.append(f"if (!{arg_name}_ptr) return {err_return};")
                converts.append(f"{base_type}* {arg_name} = static_cast<{base_type}*>({arg_name}_ptr);")
                call_args.append(arg_name)

            # 5) Fallback: treat as string
            else:
                decls.append(f"const char* {arg_name}")
                call_args.append(arg_name)



        # assemble the function bridge
        fb = [f"// Bridge for {fn_name}"]
        fb.append(f'extern "C" {ret_sig} __{fn_name}({", ".join(decls)}) {{')

        if debug:
            fb.append(f'    std::cout << "[GMBridge] Called {fn_name}" << std::endl;')

        fb += [f"    {line}" for line in converts if line.strip()]
        fb.append(f"\n    {canon_rt} result = {fn_name}({', '.join(call_args)});")

        # 1) Unsupported-width integer returns → serialize to string
        if ret_meta["is_unsupported_numeric"]:
            fb.append(
                "    _tmp_str = std::to_string(result);\n"
                "    return _tmp_str.c_str();"
            )

        # 2) Standard-number returns
        elif ret_meta["extension_type"] == "double":
            fb.append("    return static_cast<double>(result);")

        # 3) Ref returns
        elif ret_meta["is_ref"]:
            fb.append(
                f'    _tmp_str = RefManager::instance().store("{ret_meta["base_type"]}", result);\n'
                "    return _tmp_str.c_str();"
            )

        # 4) Native-string returns
        elif ret_meta["extension_type"] == "string":
            fb.append("    return result;")

        # 5) Fallback error
        else:
            fb.append(f"    return {err_return};")
        
        fb.append("}\n")
        function_bridges.append("\n".join(fb))

    # 3) Fill in the header template
    # build a multi-line include block from every entry in config["include_files"]:
    include_lines = []
    for path in config.get("include_files", []):
        # normalize and strip any leading folders up through "include/"
        rel = Path(path).as_posix()
        if "/include/" in rel:
            rel = rel.split("/include/",1)[1]
        include_lines.append(f'#include "{rel}"')
    # if none were supplied, fall back to a single default include
    if not include_lines:
        include_lines = ['#include "openxr.h"']
    include_header = "\n".join(include_lines)

    bridge_cpp = BRIDGE_HEADER_TPL.substitute({
        "INCLUDE_HEADER":         include_header,
        "REF_MANAGER_BRIDGES": "",  
        "STRUCT_CONSTRUCTORS": "\n".join(struct_constructors),
        "FUNCTION_BRIDGES":    "\n".join(function_bridges)
    })

    return {
        config["output_cpp_file"]: bridge_cpp,
        "RefManager.h": REF_MANAGER_H,
        "RefManager.cpp": REF_MANAGER_CPP
    }
