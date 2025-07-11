# build/detect_defines.py

import os
import re
from typing import List

def get_defines_for_target(config: dict, target: str, sources: dict) -> List[str]:
    """
    Extract compile-time defines for the given target by parsing CMake scripts.
    Priority:
      1) If config["cmake_overrides"][target] is set, parse only that file.
      2) Otherwise, parse all sources["cmake_files"].
      3) If no defines are found, fall back to config["compile_defines"].
    """
    verbose = config.get("verbose_logging", False)
    if verbose:
        print(f"[GMBridge][detect_defines] Starting get_defines_for_target('{target}')")

    project_root = os.getcwd()

    # 1) Figure out which CMake files to parse
    overrides = config.get("cmake_overrides", {})
    if target in overrides:
        override_path = os.path.normpath(os.path.join(project_root, overrides[target]))
        cmake_paths = [override_path] if os.path.isfile(override_path) else []
        if verbose:
            print(f"[GMBridge][detect_defines]  Using override CMake for '{target}':")
            print(f"    {override_path}")
    else:
        cmake_paths = sources.get("cmake_files", [])
        if verbose:
            print(f"[GMBridge][detect_defines]  Found {len(cmake_paths)} CMake script(s) to scan:")
            for p in cmake_paths:
                print(f"    {p}")

    # 2) Prepare our regexes
    patterns = [
        re.compile(r'add_definitions\s*\(\s*(.*?)\s*\)', re.IGNORECASE),
        re.compile(r'add_compile_definitions\s*\(\s*(.*?)\s*\)', re.IGNORECASE),
        re.compile(
            r'target_compile_definitions\s*\(\s*[\w_]+\s+(?:PUBLIC|PRIVATE|INTERFACE)\s+(.*?)\)',
            re.IGNORECASE
        ),
    ]

    defines = set()
    for cm in cmake_paths:
        if not os.path.isfile(cm):
            if verbose:
                print(f"[GMBridge][detect_defines]   Skipping missing file: {cm}")
            continue

        if verbose:
            print(f"[GMBridge][detect_defines]   Parsing CMake script: {cm}")

        text = open(cm, encoding="utf-8", errors="ignore").read()
        text = re.sub(r'#.*', '', text)

        for pat in patterns:
            for group in pat.findall(text):
                for token in re.split(r'[\s,]+', group.strip()):
                    if token.startswith("-D") and len(token) > 2:
                        name = token[2:]
                    elif re.fullmatch(r'[A-Za-z_]\w*', token):
                        name = token
                    else:
                        continue
                    defines.add(name)
                    if verbose:
                        print(f"[GMBridge][detect_defines]     Found define: {name}")

    # 3) Fallback if nothing found
    if not defines:
        fallback = config.get("compile_defines", [])
        if verbose:
            print("[GMBridge][detect_defines]   No CMake defines found, falling back to config:")
            for d in fallback:
                print(f"    {d}")
        defines.update(fallback)

    final = sorted(defines)
    if verbose:
        print(f"[GMBridge][detect_defines]  Final defines for '{target}': {final}")

    return final
