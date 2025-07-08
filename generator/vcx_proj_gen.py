import os
import json
import shutil
import uuid
from pathlib import Path
from string import Template

# Load templates…
TEMPLATES_DIR    = Path(__file__).parent / "templates"
VCXPROJ_TEMPLATE = Template((TEMPLATES_DIR / "vcxproj.tpl").read_text(encoding="utf-8"))
SLN_TEMPLATE     = Template((TEMPLATES_DIR / "sln.tpl").read_text(encoding="utf-8"))

def generate_vs_project(config):
    output_folder = Path(config["output_folder"])
    src_dir       = output_folder / "src"
    include_dir   = src_dir / "include"

    # derive everything from a single project_name
    project_name  = config["project_name"]
    dll_name      = f"{project_name}.dll"
    project_guid  = str(uuid.uuid4()).upper()

    library_dirs  = config.get("library_dirs", [])
    libraries     = config.get("libraries", [])

    # --- 1) Gather include_files from config and compute include_folders ---
    include_files = config.get("include_files", [])
    if not include_files:
        raise RuntimeError("config['include_files'] must list at least one header")

    user_defs = config.get("preprocessor_defines", [])
    user_defs_str = ";".join(user_defs)

    # Make them absolute Paths
    abs_include_files = [Path(p).resolve() for p in include_files]
    # Deduplicate their parent dirs
    include_folders = sorted({Path(p).parent for p in abs_include_files})
    
    # --- 2) Clone entire input folder into src/ (preserves include/, lib/, etc) ---
    input_root = Path("input").resolve()
    if not input_root.exists():
        raise RuntimeError(f"Input folder not found: {input_root}")
    src_dir.mkdir(parents=True, exist_ok=True)
    for item in input_root.iterdir():
        dest = src_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    
    # --- 3) Copy internal bridge deps as before ---
    internal_deps_src = Path(__file__).parent / "dependencies" / "include"
    if internal_deps_src.exists():
        for item in internal_deps_src.rglob("*"):
            if item.is_file():
                rel_path  = item.relative_to(internal_deps_src)
                dest_path = include_dir / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest_path)

    # --- 4) Move generated bridge + RefManager files to src/ ---
    bridge_cpp = output_folder / f"{config["project_name"]}.cpp"
    if bridge_cpp.exists():
        src_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(bridge_cpp), str(src_dir / bridge_cpp.name))

    for fname in ("RefManager.cpp", "RefManager.h"):
        fpath = output_folder / fname
        if fpath.exists():
            shutil.move(str(fpath), str(src_dir / fname))

    # --- 5) Write config.json for your own record ---
    (output_folder / "config.json").write_text(json.dumps(config, indent=2))

    # --- 6) Copy each .lib into src/lib and prepare linker paths ---
    lib_dest = src_dir / "lib"
    lib_dest.mkdir(parents=True, exist_ok=True)

    # Copy the actual .lib files into src/lib
    lib_dest = src_dir / "lib"
    lib_dest.mkdir(parents=True, exist_ok=True)
    for lib_dir in library_dirs:
        for lib_name in libraries:
            src_lib = Path(lib_dir) / lib_name
            if not src_lib.exists():
                raise RuntimeError(f"Library not found: {src_lib}")
            shutil.copy2(src_lib, lib_dest / lib_name)

    # Gather .cpp / .h for the vcxproj
    cpp_files = list(src_dir.rglob("*.cpp"))
    h_files   = list(include_dir.rglob("*.h"))

    cpp_tags = "\n    ".join(
        f'<ClCompile Include="{f.relative_to(src_dir)}" />'
        for f in cpp_files
    )
    h_tags = "\n    ".join(
        f'<ClInclude Include="include\\{f.relative_to(include_dir)}" />'
        for f in h_files
    )

    # Now point the linker at our local lib folder and list only .lib names
    lib_dirs_tag = "lib;%(AdditionalLibraryDirectories)"
    libs_tag = ";".join(Path(lib).name for lib in libraries) + ";%(AdditionalDependencies)"

    # --- 7) Fill & write *.vcxproj ---
    vcxproj_content = VCXPROJ_TEMPLATE.safe_substitute({
        "CPP_FILES":                 cpp_tags,
        "HEADER_FILES":              h_tags,
        "PROJECT_GUID":              project_guid,
        "PROJECT_NAME":              project_name,
        "USER_PREPROCESSOR_DEFINES": user_defs_str,
        "LIBRARY_DIRS":              lib_dirs_tag,
        "LIBRARIES":                 libs_tag,
    })
    (src_dir / f"{project_name}.vcxproj").write_text(vcxproj_content)

    # --- 8) Fill & write .sln ---
    sln_content = SLN_TEMPLATE.substitute({
        "PROJECT_NAME": project_name,
        "PROJECT_GUID": project_guid
    })
    (output_folder / f"{project_name}.sln").write_text(sln_content)

    return f"VS project created under: {output_folder}"
