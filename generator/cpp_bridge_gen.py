import os
import re
import shutil
import json
from pathlib import Path
from string import Template
from typing import Dict, List, Any

from generator.export_patterns import EXPORT_PATTERNS
from parser.primitives import NUMERIC_CANONICAL_TYPES
from generator.builtin_constructors import BUILTIN_PATTERNS
from generator.builtin_constructors import *

from parser.primitives import (
    SAFE_SIGNED_INTS,
    SAFE_UNSIGNED_INTS,
    UNSAFE_INTS,
    FLOAT_TYPES,
    BOOL_TYPES
)

# ——— Load our templates & RefManager sources ———
TEMPLATES_DIR = Path(__file__).parent / "templates"
BRIDGE_HEADER_TEMPLATE = Template(
    (TEMPLATES_DIR / "bridge.h.tpl").read_text(encoding="utf-8")
)
REF_MANAGER_HEADER = (TEMPLATES_DIR / "RefManager.h").read_text(encoding="utf-8")
REF_MANAGER_SOURCE = (TEMPLATES_DIR / "RefManager.cpp").read_text(encoding="utf-8")

def sanitize_type_name(type_name: str) -> str:
    cleaned = re.sub(r'[^0-9A-Za-z_]', '_', type_name)
    cleaned = re.sub(r'__+', '_', cleaned).strip('_')
    return cleaned

def resolve_type(type_name: str, typedef_map: Dict[str,str]) -> str:
    seen = set()
    result = type_name.strip()
    while result in typedef_map and result not in seen:
        seen.add(result)
        result = typedef_map[result].strip()
    return result

def classify_field(
    field: Dict[str, Any],
    typedef_map: Dict[str, str],
    struct_set: set,
    enum_set: set
) -> str:
    """
    Classify a C field into one of:
      - char_array
      - array
      - ref_handle
      - struct
      - string
      - numeric
    """
    raw        = field["type"].strip()
    canonical  = field["canonical_type"].lower()
    array_size = field.get("array_size")

    # 1) fixed-size char arrays → pack as string/bytes
    if array_size and raw.rstrip("*").endswith("char"):
        return "char_array"

    # 2) any other C-array → JSON array
    if array_size:
        return "array"

    # 3) any pointer or function pointer → opaque handle
    if raw.endswith("*") or field.get("is_function_ptr", False):
        return "ref_handle"

    # 4) in-place struct value
    if field["canonical_type"] in struct_set:
        return "struct"

    # 5) enums & numeric types
    if canonical in NUMERIC_CANONICAL_TYPES or field.get("is_enum", False):
        return "numeric"

    # 6) plain string (char* not caught above) → string
    if field["extension_type"] == "string" and not field.get("is_ref", False):
        return "string"

    # 7) any remaining ref → handle
    if field.get("is_ref", False):
        return "ref_handle"

    # 8) fallback to numeric
    return "numeric"

def generate_struct_json_overloads(struct_name: str,
                                   fields: List[Dict[str,Any]],
                                   reachable_results: Dict[str,Any]) -> str:
    typedef_map = reachable_results["typedef_map"]
    struct_set  = set(reachable_results["struct_fields"])
    enum_set    = set(reachable_results["enums"])

    def ref_to_json(name: str, sz: int=None, field: Dict[str,Any]=None) -> str:
        raw   = field["declared_type"]
        inner = re.sub(r'\bconst\b\s*', '', raw).strip()
        return (
            f'    jsonValue["{name}"] = '
            f'RefManager::instance().get_ref_for_ptr('
            f'reinterpret_cast<void*>(const_cast<{inner}>(o.{name}))'
            f');'
        )

    def ref_from_json(name: str, sz: int=None, field: Dict[str,Any]=None) -> str:
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
                f'        strncpy_s(o.{name}, tmp.c_str(), {sz});',
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
    lines.append(f'inline void to_json(json& jsonValue, const {struct_name}& o) {{')
    lines.append('    jsonValue = json::object();')
    for field in fields:
        kind    = classify_field(field, typedef_map, struct_set, enum_set)
        handler = GEN_HANDLERS[kind][0]
        lines.append(handler(field["name"], field.get("array_size"), field))
    lines.append('}')
    lines.append(f'inline void from_json(const json& jsonValue, {struct_name}& o) {{')
    for field in fields:
        kind    = classify_field(field, typedef_map, struct_set, enum_set)
        handler = GEN_HANDLERS[kind][1]
        lines.append(handler(field["name"], field.get("array_size"), field))
    lines.append('}')
    lines.append('')
    lines.append(f'REFMAN_REGISTER_TYPE({struct_name}, {struct_name});')
    return "\n".join(lines)

def collect_reachable_structs(reachable_results: Dict[str,Any],
                              exported_functions: List[Dict[str,Any]]) -> set:
    struct_fields = reachable_results["struct_fields"]
    reachable     = set()
    queue         = []

    for fn in exported_functions:
        rt = fn["return_meta"]["canonical_type"]
        if rt in struct_fields and rt not in reachable:
            reachable.add(rt)
            queue.append(rt)
        for arg in fn["args"]:
            at = arg["canonical_type"]
            if at in struct_fields and at not in reachable:
                reachable.add(at)
                queue.append(at)

    while queue:
        current = queue.pop()
        for f in struct_fields[current]:
            ct = f["canonical_type"]
            if ct in struct_fields and ct not in reachable:
                reachable.add(ct)
                queue.append(ct)

    return reachable

def order_structs_by_dependency(dependency_map: Dict[str,List[str]]) -> List[str]:
    dependents = {name: [] for name in dependency_map}
    for parent, children in dependency_map.items():
        for child in children:
            dependents[child].append(parent)
    in_degree = {name: len(children) for name, children in dependency_map.items()}
    queue     = [n for n, deg in in_degree.items() if deg == 0]
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

def _write_bridge_and_deps(out_files: Dict[str,str], verbose: bool):
    out_src = Path.cwd() / "output" / "src"
    out_src.mkdir(parents=True, exist_ok=True)
    for name, text in out_files.items():
        path = out_src / name
        path.write_text(text, encoding="utf-8")
        if verbose:
            print(f"[GMBridge][cpp_bridge] Wrote {path}")
    deps_src = Path.cwd() / "deps"
    deps_dst = out_src / "deps"
    if deps_src.is_dir():
        shutil.copytree(deps_src, deps_dst, dirs_exist_ok=True)
        if verbose:
            print(f"[GMBridge][cpp_bridge] Copied deps {deps_src} → {deps_dst}")
    else:
        raise FileNotFoundError(f"[GMBridge][cpp_bridge] Expected './deps' folder, not found.")

def generate_cpp_bridge(reachable_results: Dict[str,Any],
                        config: Dict[str,Any],
                        defines: List[str],
                        exports: List[str]) -> Dict[str,Any]:
    """
    reachable_results: output of parse_headers()
    defines:      list[str]
    exports:      list of symbol names to wrap
    Returns:
      {
        "DSCreateFunctions": [...],
        "FunctionBridges":   [...],
        "StructConstructors":[...],
        "Enums":             { ... },
        "Constants":         { ... }
      }
    """
    verbose = config.get("verbose_logging", False)
    project_name = config["project_name"]
    output_root  = Path.cwd() / "output"
    src_dir      = output_root / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # 1) Filter exported functions
    export_set    = set(exports)
    all_functions = [
        fn for fn in reachable_results["functions"]
        if fn["name"] in export_set
    ]
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Exported functions: {len(all_functions)}")

    # 2) Build includes
    include_lines = []
    include_dirs  = set()
    for header_path in config.get("include_files", []):
        path_obj = Path(header_path).resolve()
        if not path_obj.exists():
            continue
        include_lines.append(f'#include <{path_obj.name}>')
        for parent in path_obj.parents:
            if parent.name.lower() == "include":
                include_dirs.add(str(Path("output") / "upstream" / "include"))
                break
        else:
            include_dirs.add(str(Path("output") / "upstream"))
    if not include_lines:
        include_lines = ["// No include_files provided"]
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
    reachable = collect_reachable_structs(reachable_results, all_functions)
    for struct in reachable:
        for field in reachable_results["struct_fields"][struct]:
            used_types.add(field["canonical_type"])
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Types to inspect: {sorted(used_types)}")

    # 3a) Build dependency graph
    deps          = {}
    typedef_map   = reachable_results["typedef_map"]
    struct_fields = reachable_results["struct_fields"]
    for struct in reachable:
        needed = []
        for f in struct_fields[struct]:
            ct = resolve_type(f["type"], typedef_map)
            if ct in reachable:
                needed.append(ct)
        deps[struct] = needed
    ordered_structs = order_structs_by_dependency(deps)
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Ordered structs: {ordered_structs}")

    # 4) Generate DS-create functions only for memory-backed/native types
    # Primitives don’t need special constructors; they map to double.
    primitive_types = {
        # special types
        "bool", "void",
        "size_t", "ssize_t", "ptrdiff_t",
        "wchar_t", "wint_t",
        # signed integers
        "char", "signed char",
        "short", "int", "long", "long long",
        # unsigned integers
        "unsigned char", "unsigned short", "unsigned int", "unsigned long", "unsigned long long",
        # floating-point
        "float", "double",
        # (optional) pointer-sized ints
        "intptr_t", "uintptr_t",
    }


    builtin_constructors: List[str] = []
    ds_create_functions:  List[str] = []

    for native_type in sorted(reachable_results["cpp_native_types"]):
        if verbose:
            print(f"[GMBridge][cpp_bridge] DS-create: considering '{native_type}'")

        # Skip pure primitives—they map directly to double in GML
        if native_type in primitive_types:
            if verbose:
                print(f"[GMBridge][cpp_bridge] DS-create: skipping primitive '{native_type}'")
            continue

        # Try each pattern
        matched = False
        for pattern, make_fn in BUILTIN_PATTERNS:
            matcher = pattern.fullmatch(native_type)
            if not matcher:
                continue
            matched = True

            if verbose:
                print(f"[GMBridge][cpp_bridge] DS-create: pattern '{pattern.pattern}' matched")

            snippet = make_fn(matcher)
            builtin_constructors.append(snippet)

            if verbose:
                print(f"[GMBridge][cpp_bridge] DS-create: generated snippet:\n{snippet}")

            first_line = snippet.splitlines()[0]
            fn_match   = re.match(r'.*? (\w+)\(', first_line)
            if fn_match:
                fn_name = fn_match.group(1)
                ds_create_functions.append(fn_name)
                if verbose:
                    print(f"[GMBridge][cpp_bridge] DS-create: registered '{fn_name}'")
            else:
                if verbose:
                    print(f"[GMBridge][cpp_bridge] DS-create: ❗ couldn't extract name for '{native_type}'")
            break

        if not matched:
            # allow bypass via config if you really know what you're doing
            if config.get("allow_unsafe_native_constructors", False):
                if verbose:
                    print(f"[GMBridge][cpp_bridge] DS-create: WARNING, no constructor for '{native_type}', continuing unsafely")
                continue

            # otherwise, fail hard
            raise RuntimeError(
                f"[GMBridge][cpp_bridge] No DS-create constructor for type '{native_type}'.\n"
                "  • To add one, extend BUILTIN_PATTERNS with a matching regex + generator.\n"
                "  • To bypass this safety check and continue anyway, add the following to your config:\n"
                "      \"allow_unsafe_native_constructors\": true"
            )
    
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Built-in constructors: {len(builtin_constructors)}")
        print(f"[GMBridge][cpp_bridge]  DSCreateFunctions: {ds_create_functions}")

    # 5) Struct JSON overloads and create() bridges
    struct_json_overloads = []
    struct_create_decls   = []
    struct_create_defs    = []
    for struct in ordered_structs:
        struct_json_overloads.append(
            generate_struct_json_overloads(
                struct,
                struct_fields[struct],
                reachable_results
            )
        )
        struct_create_decls.append(
            f'GM_FUNC(const char*) __cpp_create_{struct}();'
        )
        struct_create_defs.append(
            f'// === Bridge for {struct} ===\n'
            f'GM_FUNC(const char*) __cpp_create_{struct}() {{\n'
            f'    auto* obj = new {struct}{{}};\n'
            f'    return RefManager::instance().store("{struct}", obj).c_str();\n'
            f'}}'
        )
    if verbose:
        print(f"[GMBridge][cpp_bridge]  Struct overloads + create(): {len(ordered_structs)}")

    # 6) Function declarations & definitions
    function_declarations = []
    function_definitions  = []
    for fn in all_functions:
        name     = fn["name"]
        ret_meta = fn["return_meta"]
        ext_ret  = ret_meta["extension_type"]
        canon_rt = ret_meta["canonical_type"]

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
            if arg.get("is_unsupported_numeric", False):
                decls.append(f"const char* {nm}_str")
                converts.append(
                    f'{arg["declared_type"]} {nm} = '
                    f'static_cast<{arg["declared_type"]}>(std::stoull({nm}_str));'
                )
                calls.append(nm)
            elif et == "double":
                if arg.get("force_string_wrapper", False):
                    decls.append(f"const char* {nm}_str")
                    converts.append(
                        f'{arg["declared_type"]} {nm} = static_cast<{arg["declared_type"]}>(std::stod({nm}_str));'
                    )
                    calls.append(nm)
                else:
                    decls.append(f"double {nm}")
                    c = arg["declared_type"]
                    if c != "double":
                        converts.append(f"{c} tmp_{nm} = static_cast<{c}>({nm});")
                        calls.append(f"tmp_{nm}")
                    else:
                        calls.append(nm)

            elif arg.get("is_ref", False):
                decls.append(f"const char* {nm}_ref")
                converts.append(
                    f'    void* ptr_{nm} = RefManager::instance().retrieve({nm}_ref);'
                )
                converts.append(f"    if (!ptr_{nm}) return {err};")
                depth = arg["declared_type"].count("*")
                base  = arg["base_type"]
                if depth >= 2:
                    converts.append(
                        f"    {base}* buf_{nm} = static_cast<{base}*>(ptr_{nm});"
                    )
                    converts.append(f"    {arg['declared_type']} {nm} = &buf_{nm};")
                else:
                    converts.append(
                        f"    {base}* {nm} = static_cast<{base}*>(ptr_{nm});"
                    )
                calls.append(nm)
            elif et == "string":
                decls.append(f"const char* {nm}")
                calls.append(nm)
            else:
                decls.append(f"// TODO marshal '{nm}' of type {arg['type']}")
                calls.append(nm)

        function_declarations.append(
            f'GM_FUNC({ret_sig}) __{name}({", ".join(decls)});'
        )

        body = [f'GM_FUNC({ret_sig}) __{name}({", ".join(decls)}) {{']
        for ln in converts:
            body.append(f"    {ln}")
        if ext_ret == "void":
            body.append(f"    {name}({", ".join(calls)});")
            body.append("    return 0.0;")
        else:
            body.append(f"    {canon_rt} result = {name}({", ".join(calls)});")
            if ext_ret == "double":
                if canon_rt in UNSAFE_INTS:
                    body.append('    static std::string _tmp = std::to_string(result);')
                    body.append("    return _tmp.c_str();")
                else:
                    body.append("    return static_cast<double>(result);")
            else:
                body.append(
                    f'    std::string _tmp = RefManager::instance().store'
                    f'("{ret_meta["base_type"]}", result);'
                )
                body.append("    return _tmp.c_str();")
        body.append("}")
        function_definitions.append("\n".join(body))

    if verbose:
        print(f"[GMBridge][cpp_bridge]  Function bridges: {len(all_functions)}")

    # 7) Render templates
    header_ctx = {
        "PROJECT_NAME_UPPER":   project_name.upper(),
        "INCLUDE_LINES":        include_block,
        "BUILTIN_CONSTRUCTORS": "\n\n".join(builtin_constructors),
        "JSON_OVERLOADS":       "\n\n".join(struct_json_overloads),
        "DECLARATIONS":         "\n".join(struct_create_decls + function_declarations),
    }
    bridge_header = BRIDGE_HEADER_TEMPLATE.substitute(header_ctx)

    # Build the .cpp with all struct + function definitions
    struct_defs_code   = "\n\n".join(struct_create_defs)
    function_defs_code = "\n\n".join(function_definitions)

    bridge_source = (
        f'#include "{project_name}.h"\n\n'
        f'#pragma region StructConstructors\n'
        f'{struct_defs_code}\n'
        f'#pragma endregion\n\n'
        f'#pragma region FunctionDefinitions\n'
        f'{function_defs_code}\n'
        f'#pragma endregion\n'
    )

    out_files = {
        f"{project_name}.h":   bridge_header,
        f"{project_name}.cpp": bridge_source,
        "RefManager.h":        REF_MANAGER_HEADER,
        "RefManager.cpp":      REF_MANAGER_SOURCE,
    }
    _write_bridge_and_deps(out_files, verbose)

    # 8) Build exports_summary
    function_bridges    = [fn["name"] for fn in all_functions]
    struct_constructors = ordered_structs  # your __cpp_create_<Struct> list

    # Enums referenced by your exports
    used_enums = set()
    for fn in all_functions:
        if fn["return_meta"].get("is_enum"):
            used_enums.add(fn["return_meta"]["canonical_type"])
        for arg in fn["args"]:
            if arg.get("is_enum"):
                used_enums.add(arg["canonical_type"])
    for struct in ordered_structs:
        for field in struct_fields[struct]:
            if field.get("is_enum"):
                used_enums.add(field["canonical_type"])
    enums = {name: reachable_results["enums"][name]
             for name in used_enums
             if name in reachable_results["enums"]}

    # All constants (you can filter here if desired)
    constants = reachable_results.get("constants", {})

    exports_summary = {
        "DSCreateFunctions":  ds_create_functions,
        "FunctionBridges":    function_bridges,
        "StructConstructors": struct_constructors,
        "Enums":              enums,
        "Constants":          constants,
    }

    # Write out exports_summary.json for reference
    summary_path = Path.cwd() / "output" / "exports_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(exports_summary, f, indent=2)
    if verbose:
        print(f"[GMBridge][cpp_bridge] Wrote exports_summary: {summary_path}")

    return exports_summary