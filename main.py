from pathlib import Path
from config.loader import load_config
from discover.discover_sources import discover_all_sources
from discover.detect_defines import get_defines_for_target
from discover.discover_exports import discover_exported_symbols
from parser.header_parser import parse_headers
from generator.cmake_gen import generate_cmake_for_target
from generator.cpp_bridge_gen import generate_cpp_bridge
from build.platform_build import build_target
from build.inspect_output import inspect_built_output
from generator.gml_code_gen import generate_gml
from generator.extension_yy_gen import generate_yy_extension
from generator.output_manager import copy_output_binary
from generator.input_stager import copy_upstream_sources
from generator.deps_gen import install_dependencies


import json

def sanitize_for_json(obj):
    """
    Recursively convert sets to sorted lists and sanitize unsupported types.
    """
    if isinstance(obj, dict):
        return {key: sanitize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, set):
        return sorted(sanitize_for_json(item) for item in obj)
    else:
        return obj

def save_debug_json(obj, name="debug"):
    """
    Save a debug JSON file after sanitizing sets and other unserializable objects.
    """
    filename = f"{name}.json"
    try:
        sanitized = sanitize_for_json(obj)
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(sanitized, file, indent=2)
        print(f"[GMBridge][main] Debug JSON written: {filename}")
    except Exception as error:
        print(f"[GMBridge][main] Error writing debug JSON '{filename}': {error}")
        raise

def main():
    config = load_config("config.json")
    verbose = config.get("verbose_logging", False)
    project_root = Path.cwd()
    output_root  = project_root / "output"

    if verbose:
        print("\n[GMBridge][main] Starting bridge generation")

    copy_upstream_sources(project_root, output_root)
    install_dependencies(config)

    # Step 1: Discover input sources
    if verbose:
        print("\n[GMBridge][main]  • Discovering input sources")
    sources = discover_all_sources(config)
    if verbose:
        print(
            f"[GMBridge][main]    → Found {len(sources['source_files'])} source files, "
            f"{len(sources['header_files'])} headers, "
            f"{len(sources['cmake_files'])} CMake scripts"
        )

    # Step 2: For each platform, run full build chain
    all_outputs = []
    target_list = config.get("targets", ["windows-x64", "linux-x64"])
    for target in target_list:
        if verbose:
            print(f"\n[GMBridge][main]  - Processing target '{target}'")

        # Generate compile-time defines
        if verbose:
            print(f"\n[GMBridge][main]    - Generating defines for '{target}'")
        defines = get_defines_for_target(config, target, sources)
        if verbose:
            print(f"[GMBridge][main]      → Defines: {defines}")

        # Parse headers
        if verbose:
            print("\n[GMBridge][main]    - Parsing headers")
        parse_result = parse_headers(config, sources, defines)
        if verbose:
            func_count = len(parse_result.get("functions", []))
            struct_count = len(parse_result.get("struct_fields", {}))
            print(f"[GMBridge][main]      → Parsed {func_count} functions, {struct_count} structs")

        # Discover exports
        if verbose:
            print("\n[GMBridge][main]    - Discovering exports")
        exports = discover_exported_symbols(config, parse_result, sources)
        if verbose:
            print(f"[GMBridge][main]      → Exports: {len(exports)} symbols")

        # Generate C++ bridge code
        if verbose:
            print("\n[GMBridge][main]    - Generating C++ bridge code")
        bridge_files = generate_cpp_bridge(parse_result, config, defines, exports)
        if verbose:
            print(f"[GMBridge][main]      → Generated files: {list(bridge_files.keys())}")

        # Emit CMakeLists.txt
        if verbose:
            print(f"\n[GMBridge][main]    - Emitting CMakeLists.txt for '{target}'")

        save_debug_json(sources)
        generate_cmake_for_target(config, sources, target, defines)
        
        # Build the library
        if verbose:
            print(f"\n[GMBridge][main]    - Building target '{target}'")
        build_target(config, target)

        # Inspect built output
        if verbose:
            print("\n[GMBridge][main]    - Inspecting build output")
        output_info = inspect_built_output(config, target)
        all_outputs.append(output_info)
        if verbose:
            print(f"[GMBridge][main]      → Output info: {output_info}")

        # Copy binary into extension layout
        if verbose:
            print("\n[GMBridge][main]    - Copying binaries into extension layout")
        copy_output_binary(config, output_info)

    # Step 3: Generate GML stubs
    if verbose:
        print("\n[GMBridge][main]  - Generating GML stubs")
    generate_gml(parse_result, config)

    # Step 4: Generate .yy extension metadata
    if verbose:
        print("\n[GMBridge][main]  - Generating .yy extension metadata")
    generate_yy_extension(parse_result, config, all_outputs)

    if verbose:
        print("\n[GMBridge][main] Bridge generation complete")

if __name__ == "__main__":
    main()