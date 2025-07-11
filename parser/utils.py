import re
from parser.primitives import (
    SAFE_SIGNED_INTS,
    SAFE_UNSIGNED_INTS,
    UNSAFE_INTS,
    FLOAT_TYPES,
    BOOL_TYPES
)

def flatten_parse_data(all_results: dict) -> dict:
    """
    Merge multiple per-file parse results into one unified parse_result.
    all_results is expected to have the shape:
        { "files": { filename1: parse_result1, filename2: parse_result2, … } }
    Returns a dict with keys:
        "functions", "typedef_map", "struct_fields",
        "function_ptr_aliases", "enums", "constants", "using_map"
    """
    unified = {
        "functions":            [],
        "typedef_map":          {},
        "struct_fields":        {},
        "function_ptr_aliases": [],
        "enums":                {},
        "constants":            {},
        "using_map":            {}
    }

    for file_res in all_results.get("files", {}).values():
        # 1) append all functions
        unified["functions"].extend(file_res.get("functions", []))

        # 2) merge all maps (later files win on name collisions)
        unified["typedef_map"].update(file_res.get("typedef_map", {}))
        unified["struct_fields"].update(file_res.get("struct_fields", {}))
        unified["enums"].update(file_res.get("enums", {}))
        unified["constants"].update(file_res.get("constants", {}))
        unified["using_map"].update(file_res.get("using_map", {}))

        # 3) collect all function‐pointer aliases
        unified["function_ptr_aliases"].extend(file_res.get("function_ptr_aliases", []))

    # dedupe & sort the aliases
    unified["function_ptr_aliases"] = sorted(set(unified["function_ptr_aliases"]))

    return unified

def classify_c_type(parse_result, c_type, config):
    """
    Given a raw C type, classify:
      - is_ref: opaque handle or stringified numeric
      - is_standard_numeric: fits in double safely
      - is_unsupported_numeric: too big, stringified
      - extension_type: "string", "double", or "void"
    """
    typedef_map   = parse_result["typedef_map"]
    using_map     = parse_result["using_map"]
    known_structs = set(parse_result["struct_fields"].keys())
    func_ptrs     = set(parse_result["function_ptr_aliases"])
    enum_names    = set(parse_result["enums"].keys())

    def resolve_full(name: str) -> str:
        seen = set()
        t = name
        while True:
            if t in using_map and t not in seen:
                seen.add(t); t = using_map[t]; continue
            if t in typedef_map and t not in seen:
                seen.add(t); t = typedef_map[t]; continue
            break
        return t

    cleaned  = re.sub(r'\bextern\b\s*', '', c_type, flags=re.IGNORECASE).strip()
    original = cleaned
    outer    = resolve_full(original)
    has_const= outer.startswith("const ")
    has_ptr  = outer.endswith("*")
    no_const = re.sub(r'^const\s+', '', outer).rstrip('*').strip()
    canonical= resolve_full(no_const).strip()

    rec = {
        "declared_type":        original,
        "base_type":            no_const,
        "canonical_type":       canonical,
        "has_const":            has_const,
        "has_pointer":          has_ptr,
        "is_enum":              no_const in enum_names,
        "is_struct":            no_const in known_structs,
        "is_function_ptr":      outer in func_ptrs,
        "is_standard_numeric":  False,
        "is_unsupported_numeric": False,
        "is_ref":               False,
        "extension_type":       ""
    }

    # 1) Pointers, structs, or function pointers → opaque handle
    if rec["has_pointer"] or rec["is_struct"] or rec["is_function_ptr"]:
        rec["is_ref"] = True
        rec["extension_type"] = "string"
        return rec

    # 2) Unsafe (≥64-bit or pointer-sized) integers → stringified numeric
    if canonical in UNSAFE_INTS:
        rec["is_unsupported_numeric"] = True
        rec["extension_type"] = "string"
        return rec

    # 3) Enums → double
    if rec["is_enum"]:
        rec["is_standard_numeric"] = True
        rec["extension_type"] = "double"
        return rec

    # 4) Void → no return
    if canonical == "void":
        rec["extension_type"] = "void"
        return rec

    # 5) Safe numerics (bools, floats, ≤32-bit ints) → double
    if (canonical in BOOL_TYPES
        or canonical in FLOAT_TYPES
        or canonical in SAFE_SIGNED_INTS
        or canonical in SAFE_UNSIGNED_INTS):
        rec["is_standard_numeric"] = True
        rec["extension_type"] = "double"
        return rec

    # 6) Fallback: anything else treat as string‐based handle
    rec["is_ref"] = True
    rec["extension_type"] = "string"
    return rec