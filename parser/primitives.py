# parser/primitives.py

# ——— Core primitive categories ———

# Boolean
BOOL_TYPES = {"bool", "_Bool"}

# Void
VOID_TYPES = {"void"}

# Safe signed integers (≤32-bit, safe to convert → double)
SAFE_SIGNED_INTS = {
    "char", "signed char",
    "short", "int", "long"
}

# Safe unsigned integers (≤32-bit, safe to convert → double)
SAFE_UNSIGNED_INTS = {
    "unsigned char", "unsigned short", "unsigned int", "unsigned long"
}

# Unsafe integers (≥64-bit or pointer-sized; stringify instead)
UNSAFE_INTS = {
    "long long", "unsigned long long",
    "int64_t", "uint64_t",
    "intptr_t", "uintptr_t",
    "size_t", "ssize_t", "ptrdiff_t"
}

# Floating point
FLOAT_TYPES = {"float", "double"}

# Wide char / I/O
WCHAR_TYPES = {"wchar_t", "wint_t"}

# ——— For DS-create: only primitives that map safely to double (plus void & wide chars) ———
DS_PRIMITIVE_TYPES = (
    VOID_TYPES
    | BOOL_TYPES
    | SAFE_SIGNED_INTS
    | SAFE_UNSIGNED_INTS
    | FLOAT_TYPES
    | WCHAR_TYPES
)

# ——— For classify_field numeric detection: include all safe + unsafe ints, floats, bools ———
NUMERIC_CANONICAL_TYPES = (
    BOOL_TYPES
    | SAFE_SIGNED_INTS
    | SAFE_UNSIGNED_INTS
    | UNSAFE_INTS
    | FLOAT_TYPES
)

# ——— For GML JsDoc mapping ———
GML_BOOL   = BOOL_TYPES
GML_STRING = {"char", "string"}  # covers any char-based or explicit string types
GML_REAL   = FLOAT_TYPES
GML_INT    = SAFE_SIGNED_INTS | SAFE_UNSIGNED_INTS | UNSAFE_INTS
