# generator/export_patterns.py

EXPORT_PATTERNS = {
    "windows": [
        r"__cdecl",
        r"__stdcall",
        r"__fastcall",
        r"__vectorcall",
        r"__thiscall",
        r"__clrcall",        # for mixed‐mode / C++/CLI
        r"__pascal",         # very old but still recognized

        # MSVC’s built-in API macros
        r"WINAPI",
        r"CALLBACK",
        r"APIENTRY",
        r"NTAPI",
    ],
    "linux": [
        r"__attribute__\(\(\s*visibility\(\"default\"\)\s*\)\)",
        r"__attribute__\(\(\s*used\s*\)\)",
    ],
    "macos": [
        r"__attribute__\(\(\s*visibility\(\"default\"\)\s*\)\)",
        r"__attribute__\(\(\s*used\s*\)\)",
        r"__symbol\(public\)",    # Apple‐specific
    ],
    "android": [
        r"__attribute__\(\(\s*visibility\(\"default\"\)\s*\)\)",
        r"__attribute__\(\(\s*used\s*\)\)",
    ],
    "ios": [
        r"__attribute__\(\(\s*visibility\(\"default\"\)\s*\)\)",
        r"__attribute__\(\(\s*used\s*\)\)",
    ],
}
