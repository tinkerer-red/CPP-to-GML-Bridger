# parser/reachable_parser.py

import json
from typing import List, Set, Dict, Any
from .header_parser import find_reachable_types  # adjust path as needed

def find_reachable_types(
    supplied_function_names: List[str],
    parse_data: Dict[str, Any]
) -> List[str]:
    """
    Given a list of function names and the full parse_data map (with keys
    'functions' and 'struct_fields'), return all canonical types reachable
    from those functions via their return values, arguments, and any nested
    struct fields.
    """
    # 1) Collect initial set of types from return values and arguments
    reachable_types: Set[str] = set()
    for function_entry in parse_data.get("functions", []):
        function_name = function_entry.get("name")
        if function_name in supplied_function_names:
            # return value
            return_meta = function_entry.get("return_meta", {})
            return_type = return_meta.get("canonical_type")
            if return_type:
                reachable_types.add(return_type)
            # arguments
            for arg_meta in function_entry.get("args", []):
                arg_type = arg_meta.get("canonical_type")
                if arg_type:
                    reachable_types.add(arg_type)

    # 2) Iteratively expand via struct_fields until no new types appear
    struct_fields_map = parse_data.get("struct_fields", {})
    grew = True
    while grew:
        before_count = len(reachable_types)
        # scan each type we currently know
        for current_type in list(reachable_types):
            # if it's a struct, gather its fields' types
            fields = struct_fields_map.get(current_type, [])
            for field_meta in fields:
                field_type = field_meta.get("canonical_type")
                if field_type:
                    reachable_types.add(field_type)
        after_count = len(reachable_types)
        grew = (after_count > before_count)

    # 3) Return as a plain list
    return list(reachable_types)


def compute_reachable_results(
    config: Dict[str, Any],
    parse_result: Dict[str, Any],
    exports: List[str]
) -> Dict[str, Any]:
    """
    Given your full parse_result and the list of function names you’re
    exposing, produce a slimmed‐down parse_result containing only:

      • functions in `exports`
      • structs transitively referenced by those functions
      • enums actually used by those types
      • constants (unchanged)
      • typedef_map, using_map (unchanged)
      • function_ptr_aliases filtered to only reachable aliases
      • types: the full list of canonical types from find_reachable_types

    Returns that “reachable_results” dict.
    """

    verbose = config.get("verbose_logging", False)

    # 1) Which canonical types are reachable?
    types = find_reachable_types(exports, parse_result)
    if config.get("verbose_logging", False):
        print(f"[GMBridge][reachable] Reachable types: {types}")

    # 2) Functions: only those you exported
    all_functions = parse_result.get("functions", [])
    functions = [fn for fn in all_functions if fn.get("name") in exports]

    # 3) Structs: only those in the reachable set
    all_structs = parse_result.get("struct_fields", {})
    struct_fields = {
        name: fields
        for name, fields in all_structs.items()
        if name in types
    }

    # 4) Enums: only those whose names appear in the reachable types
    all_enums = parse_result.get("enums", {})
    enums = {
        name: all_enums[name]
        for name in types
        if name in all_enums
    }

    # 5) Constants (keep all; filter here if you want)
    constants = parse_result.get("constants", {})

    # 6) Typedefs & using (pass through unchanged)
    typedef_map = parse_result.get("typedef_map", {})
    using_map   = parse_result.get("using_map", {})

    # 7) Function‐pointer aliases: only those whose alias is a reachable type
    original_ptr_aliases = parse_result.get("function_ptr_aliases", [])
    function_ptr_aliases = [
        alias for alias in original_ptr_aliases
        if alias in types
    ]

    # 8) Compute cpp_native_types: reachable types minus structs, enums, and function_ptr_aliases
    excluded: Set[str] = (
        set(struct_fields.keys()) |
        set(enums.keys()) |
        set(function_ptr_aliases) |
        set(typedef_map.keys())
    )
    # functions themselves are names, not types, so no need to exclude
    cpp_native_types = [t for t in types if t not in excluded]
    
    # drop any struct or pointer types
    cpp_native_types = [
        t for t in cpp_native_types
        if not t.startswith("struct ") and "*" not in t
    ]

    if verbose:
        print(f"[GMBridge][reachable] C++ native types: {cpp_native_types}")

    # 9) Assemble slimmed-down result
    reachable_results: Dict[str, Any] = {
        "functions":            functions,
        "struct_fields":        struct_fields,
        "enums":                enums,
        "constants":            constants,
        "typedef_map":          typedef_map,
        "using_map":            using_map,
        "function_ptr_aliases": function_ptr_aliases,
        "types":                types,
        "cpp_native_types":     cpp_native_types,
    }

    return reachable_results