import os
import re
import shutil
from pathlib import Path
from string import Template
from generator.builtin_constructors import BUILTIN_PATTERNS

# ——— Load our templates & RefManager sources ———
TEMPLATES_DIR = Path(__file__).parent / "templates"
BRIDGE_HEADER_TEMPLATE = Template(
    (TEMPLATES_DIR / "bridge.h.tpl").read_text(encoding="utf-8")
)
REF_MANAGER_HEADER = (TEMPLATES_DIR / "RefManager.h").read_text(encoding="utf-8")
REF_MANAGER_SOURCE = (TEMPLATES_DIR / "RefManager.cpp").read_text(encoding="utf-8")

# ——— Helper to sanitize C++ types into valid identifier suffixes ———
def sanitize_type_name(type_name: str) -> str:
    cleaned = re.sub(r'[^0-9A-Za-z_]', '_', type_name)
    cleaned = re.sub(r'__+', '_', cleaned).strip('_')
    return cleaned

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

def collect_reachable_structs(parse_result, exported_functions):
    # parse_result["struct_fields"]: Dict[str, List[field_dict]]
    struct_fields = parse_result["struct_fields"]
    reachable   = set()
    work_queue  = []

    # 1) Seed: any struct that is a return or arg type
    for fn in exported_functions:
        rt = fn["return_meta"]["canonical_type"]
        if rt in struct_fields and rt not in reachable:
            reachable.add(rt)
            work_queue.append(rt)

        for arg in fn["args"]:
            at = arg["canonical_type"]
            if at in struct_fields and at not in reachable:
                reachable.add(at)
                work_queue.append(at)

    # 2) BFS/DFS: pull in any nested structs
    while work_queue:
        current = work_queue.pop()
        for field in struct_fields[current]:
            inner_type = field["canonical_type"]
            if inner_type in struct_fields and inner_type not in reachable:
                reachable.add(inner_type)
                work_queue.append(inner_type)

    return reachable

def _write_bridge_and_deps(out_files: dict[str,str], verbose: bool):
    """
    1) Dump every generated bridge file into output/src/
    2) Copy the entire ./deps folder into output/src/deps
    """
    out_src = Path.cwd() / "output" / "src"
    out_src.mkdir(parents=True, exist_ok=True)

    # 1) Write generated bridge files
    for name, text in out_files.items():
        path = out_src / name
        path.write_text(text, encoding="utf-8")
        if verbose:
            print(f"[GMBridge][cpp_bridge] Wrote {path}")

    # 2) Copy deps
    deps_src = Path.cwd() / "deps"
    deps_dst = out_src / "deps"
    if deps_src.is_dir():
        shutil.copytree(deps_src, deps_dst, dirs_exist_ok=True)
        if verbose:
            print(f"[GMBridge][cpp_bridge] Copied deps {deps_src} → {deps_dst}")
    else:
        raise FileNotFoundError(f"[GMBridge][cpp_bridge] Expected './deps' folder, not found.")

def order_structs_by_dependency(dependency_map: dict[str, list[str]]) -> list[str]:
    """
    Given a map struct_name → [structs it depends on],
    returns a list in which every struct appears **after**
    all the structs it relies on.
    """
    # Build reverse adjacency: child → list of parents
    dependents = {name: [] for name in dependency_map}
    for parent, children in dependency_map.items():
        for child in children:
            dependents[child].append(parent)

    # in-degree = how many deps each struct has
    in_degree = {name: len(children) for name, children in dependency_map.items()}

    # start with zero-in-degree structs
    queue = [name for name, deg in in_degree.items() if deg == 0]
    sorted_list = []

    # Kahn’s topo sort
    while queue:
        n = queue.pop(0)
        sorted_list.append(n)
        for parent in dependents[n]:
            in_degree[parent] -= 1
            if in_degree[parent] == 0:
                queue.append(parent)

    if len(sorted_list) != len(dependency_map):
        raise ValueError("Cycle detected in struct dependencies")
    return sorted_list

# ——— The refactored bridge generator ———
def order_structs_by_dependency(dependency_map: dict[str, list[str]]) -> list[str]:
    """
    Given struct → [other structs it depends on], returns a list where
    dependencies always come before dependents.
    """
    # Build reverse adjacency
    dependents = {name: [] for name in dependency_map}
    for parent, children in dependency_map.items():
        for child in children:
            dependents[child].append(parent)

    # Compute in-degrees
    in_degree = {name: len(children) for name, children in dependency_map.items()}

    # Kahn’s algorithm
    queue = [n for n, deg in in_degree.items() if deg == 0]
    sorted_list = []
    while queue:
        n = queue.pop(0)
        sorted_list.append(n)
        for parent in dependents[n]:
            in_degree[parent] -= 1
            if in_degree[parent] == 0:
                queue.append(parent)

    if len(sorted_list) != len(dependency_map):
        raise ValueError("Cycle detected in struct dependencies")
    return sorted_list


def generate_cpp_bridge(parse_result, config, defines, exports):
    """
    parse_result: output of parse_headers()
    defines:      list[str] but unused
    exports:      list of symbol names to wrap
    """
    verbose = config.get("verbose_logging", False)
    if verbose:
        print("[GMBridge][cpp_bridge] Starting generate_cpp_bridge()")

    project_name = config["project_name"]
    output_root  = Path.cwd() / "output"
    src_dir      = output_root / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # 1) Filter exported functions
    all_functions = [fn for fn in parse_result["functions"]
                     if fn["name"] in set(exports)]
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Exported functions: {len(all_functions)}")

    # 2) Build includes (based purely on config["include_files"])
    include_lines = []
    include_dirs = set()

    for original_path in config.get("include_files", []):
        original_path = Path(original_path).resolve()
        if not original_path.exists():
            continue  # skip missing files

        # Use only the filename (drop all folders)
        header_name = original_path.name
        include_lines.append(f'#include <{header_name}>')

        # Now scan for "include" folder parent and infer upstream include dir
        for parent in original_path.parents:
            if parent.name.lower() == "include":
                include_dirs.add(str(Path("output") / "upstream" / "include"))
                break
        else:
            include_dirs.add(str(Path("output") / "upstream"))

    if not include_lines:
        include_lines = ['// No include_files provided']
        include_dirs.add(str(Path("output") / "upstream"))

    include_block = "\n".join(include_lines)


    if verbose:
        print(f"[GMBridge][cpp_bridge]  Includes:\n{include_block}")
    
    # 3) Compute used types & reachable structs
    used_types = set()
    for fn in all_functions:
        used_types.add(fn["return_meta"]["canonical_type"])
        for arg in fn["args"]:
            used_types.add(arg["canonical_type"])
    reachable = collect_reachable_structs(parse_result, all_functions)
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Reachable structs: {reachable}")
    for struct in reachable:
        for fld in parse_result["struct_fields"][struct]:
            used_types.add(fld["canonical_type"])
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Types to inspect: {sorted(used_types)}")

    # 3a) Build dependency graph *among reachable only*
    #    struct_name -> [other reachable structs it directly uses]
    deps = {}
    typedef_map = parse_result["typedef_map"]
    struct_fields = parse_result["struct_fields"]
    for struct in reachable:
        needed = []
        for f in struct_fields[struct]:
            canon = resolve_type(f["type"], typedef_map)
            if canon in reachable:
                needed.append(canon)
        deps[struct] = needed

    # 3b) Topologically sort so dependencies come first
    ordered_structs = order_structs_by_dependency(deps)
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Ordered structs: {ordered_structs}")

    # 4) Generate builtin constructors
    builtin_constructors = []
    for t in sorted(used_types):
        for pat, gen in BUILTIN_PATTERNS:
            m = pat.fullmatch(t)
            if m:
                builtin_constructors.append(gen(m))
                break
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Built-in constructors: "
              f"{len(builtin_constructors)}")

    # 5) Struct JSON + create(), **in dependency order**
    struct_json_overloads = []
    struct_create_decls   = []
    struct_create_defs    = []
    for struct in ordered_structs:
        struct_json_overloads.append(
            generate_struct_json_overloads(
                struct,
                struct_fields[struct],
                parse_result
            )
        )
        struct_create_decls.append(
            f'extern "C" const char* __cpp_create_{struct}();'
        )
        struct_create_defs.append(
            f'// === Bridge for {struct} ===\n'
            f'extern "C" const char* __cpp_create_{struct}() {{\n'
            f'    auto* obj = new {struct}{{}};\n'
            f'    return RefManager::instance().store("{struct}", obj).c_str();\n'
            f'}}'
        )
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Struct overloads + create(): "
              f"{len(ordered_structs)}")

    # 6) Function declarations & definitions (unchanged)
    function_declarations = []
    function_definitions  = []
    for fn in all_functions:
        name      = fn["name"]
        ret_meta  = fn["return_meta"]
        ext_ret   = ret_meta["extension_type"]
        canon_rt  = ret_meta["canonical_type"]

        # pick return signature
        if ext_ret == "void":
            ret_sig, err = "double", "0.0"
        elif ext_ret == "double":
            ret_sig, err = "double", "std::numeric_limits<double>::quiet_NaN()"
        else:
            ret_sig, err = "const char*", "\"\""

        decls, converts, calls = [], [], []
        for arg in fn["args"]:
            nm = arg["name"]
            et = arg["extension_type"]
            if arg["is_unsupported_numeric"]:
                decls.append(f"const char* {nm}_str")
                converts.append(
                    f"{arg['declared_type']} {nm} = "
                    f"static_cast<{arg['declared_type']}>"
                    f"(std::stoull({nm}_str));"
                )
                calls.append(nm)

            elif et == "double":
                decls.append(f"double {nm}")
                c = arg["declared_type"]
                if c != "double":
                    converts.append(
                        f"{c} {nm}_val = static_cast<{c}>({nm});"
                    )
                    calls.append(f"{nm}_val")
                else:
                    calls.append(nm)

            elif arg["is_ref"]:
                decls.append(f"const char* {nm}_ref")
                converts.append(
                    f"    void* ptr_{nm} = "
                    f"RefManager::instance().retrieve({nm}_ref);"
                )
                converts.append(f"    if (!ptr_{nm}) return {err};")
                depth = arg["declared_type"].count("*")
                base  = arg["base_type"]
                if depth >= 2:
                    converts.append(
                        f"    {base}* buf = static_cast<{base}*>(ptr_{nm});"
                    )
                    converts.append(
                        f"    {arg['declared_type']} {nm} = &buf;"
                    )
                else:
                    converts.append(
                        f"    {base}* {nm} = static_cast<{base}*>(ptr_{nm});"
                    )
                calls.append(nm)

            elif et == "string":
                decls.append(f"const char* {nm}")
                calls.append(nm)

            else:
                decls.append(
                    f"// TODO marshal '{nm}' of type {arg['type']}"
                )
                calls.append(nm)

        # declaration
        function_declarations.append(
            f'extern "C" {ret_sig} __{name}({", ".join(decls)});'
        )

        # definition
        body = [f'extern "C" {ret_sig} __{name}({", ".join(decls)}) {{']
        for ln in converts:
            body.append(f"    {ln}")
        if ext_ret == "void":
            body.append(f"    {name}({', '.join(calls)});")
            body.append("    return 0.0;")
        else:
            body.append(
                f"    {canon_rt} result = {name}({', '.join(calls)});"
            )
            if ext_ret == "double":
                body.append("    return static_cast<double>(result);")
            else:
                body.append(
                    f'    std::string _tmp = '
                    f'RefManager::instance().store'
                    f'("{ret_meta["base_type"]}", result);'
                )
                body.append("    return _tmp.c_str();")
        body.append("}")
        function_definitions.append("\n".join(body))

    if verbose:
        print(f"[GMBridge][cpp_bridge]  Function bridges: "
              f"{len(all_functions)}")

    # 7) Render templates (unchanged)
    header_ctx = {
        "PROJECT_NAME_UPPER": project_name.upper(),
        "INCLUDE_LINES": include_block,
        "BUILTIN_CONSTRUCTORS": "\n\n".join(builtin_constructors),
        "JSON_OVERLOADS": "\n\n".join(struct_json_overloads),
        "DECLARATIONS": "\n".join(struct_create_decls + function_declarations),
        "STRUCT_DEFS": "\n\n".join(struct_create_defs),
        "FUNCTION_DEFS": "\n\n".join(function_definitions),
    }

    bridge_header = BRIDGE_HEADER_TEMPLATE.substitute(header_ctx)
    bridge_source = f'#include "{project_name}.h"\n'

    # write files
    out_files = {
        f"{project_name}.h": bridge_header,
        f"{project_name}.cpp": bridge_source,
        "RefManager.h": REF_MANAGER_HEADER,
        "RefManager.cpp": REF_MANAGER_SOURCE,
    }
    _write_bridge_and_deps(out_files, verbose)

    if verbose:
        print("[GMBridge][cpp_bridge] Completed generate_cpp_bridge()")

    return out_files
