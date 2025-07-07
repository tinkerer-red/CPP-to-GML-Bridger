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
    ext_name      = config["extension_name"]
    dll_name      = config["dll_name"]
    project_guid  = str(uuid.uuid4()).upper()

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
    # --- 2) Deep-copy each include_folder (and all its subfolders) into src/include ---
    for root_path in include_folders:
        dest_root = include_dir / root_path.name
        if dest_root.exists():
            # merge into existing tree
            shutil.copytree(root_path, dest_root, dirs_exist_ok=True)
        else:
            shutil.copytree(root_path, dest_root)

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
    bridge_cpp = output_folder / "bridge.cpp"
    if bridge_cpp.exists():
        src_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(bridge_cpp), str(src_dir / bridge_cpp.name))

    for fname in ("RefManager.cpp", "RefManager.h"):
        fpath = output_folder / fname
        if fpath.exists():
            shutil.move(str(fpath), str(src_dir / fname))

    # --- 5) Write config.json for your own record ---
    (output_folder / "config.json").write_text(json.dumps(config, indent=2))

    # --- 6) Gather .cpp / .h for the vcxproj ---
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

    # --- 7) Fill & write *.vcxproj ---
    vcxproj_content = VCXPROJ_TEMPLATE.safe_substitute({
        "CPP_FILES":     cpp_tags,
        "HEADER_FILES":  h_tags,
        "PROJECT_GUID":  project_guid,
        "EXTENSION_NAME": ext_name,
        "DLL_NAME":      dll_name,
        "USER_PREPROCESSOR_DEFINES":  user_defs_str
    })
    (src_dir / f"{ext_name}.vcxproj").write_text(vcxproj_content)

    # --- 8) Fill & write .sln ---
    sln_content = SLN_TEMPLATE.substitute({
        "PROJECT_NAME":  ext_name,
        "PROJECT_GUID":  project_guid
    })
    (output_folder / f"{ext_name}.sln").write_text(sln_content)

    return f"VS project created under: {output_folder}"
