import os
import shutil
import uuid
from pathlib import Path
from string import Template

# Load templates…
TEMPLATES_DIR       = Path(__file__).parent / "templates"
VCXPROJ_TEMPLATE    = Template((TEMPLATES_DIR / "vcxproj.tpl").read_text(encoding="utf-8"))
SLN_TEMPLATE = Template((TEMPLATES_DIR / "sln.tpl").read_text(encoding="utf-8"))


# Function to generate .vcxproj and .sln files and move files to correct output structure
def generate_vs_project(config):
    output_folder = Path(config["output_folder"])
    src_dir       = output_folder / "src"
    include_dir   = src_dir / "include"
    ext_name      = config["extension_name"]
    dll_name      = config["dll_name"]
    project_guid  = str(uuid.uuid4()).upper()

    # Copy all files from input_folder to include/
    input_folder = Path(config["input_folder"])
    for root, _, files in os.walk(input_folder):
        for file in files:
            rel_path = Path(root).relative_to(input_folder)
            target_dir = include_dir / rel_path
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(Path(root) / file, target_dir / file)

    # Copy internal bridge dependencies
    internal_deps_src = Path(__file__).parent / "dependencies" / "include"
    if internal_deps_src.exists():
        for item in internal_deps_src.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(internal_deps_src)
                dest_path = include_dir / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest_path)

    # Move generated bridge + RefManager files to src/
    bridge_cpp_file = output_folder / "bridge.cpp"
    bridge_dst = src_dir / bridge_cpp_file.name

    if bridge_cpp_file.exists():
        shutil.move(str(bridge_cpp_file), str(src_dir / bridge_cpp_file.name))

    for fname in ["RefManager.cpp", "RefManager.h"]:
        fpath = output_folder / fname
        shutil.move(str(fpath), str(src_dir / fname))

    # Write config.json into output folder
    config_path = output_folder / "config.json"
    with config_path.open("w") as f:
        import json
        json.dump(config, f, indent=2)

    # Collect all .cpp and .h files for vcxproj
    cpp_files = [f for f in (src_dir).rglob("*.cpp")]
    h_files = [f for f in (src_dir / "include").rglob("*.h")]

    cpp_tags = "\n    ".join(f'<ClCompile Include="{f.relative_to(src_dir)}" />' for f in cpp_files)
    h_tags = "\n    ".join(f'<ClInclude Include="include\\{f.relative_to(src_dir / "include")}" />' for f in h_files)

    
    # Fill in vcxproj content
    vcxproj_content = VCXPROJ_TEMPLATE.safe_substitute({
        "CPP_FILES": cpp_tags,
        "HEADER_FILES": h_tags,
        "PROJECT_GUID": project_guid,
        "EXTENSION_NAME": ext_name,
        "DLL_NAME": dll_name
    })

    vcxproj_path = src_dir / f"{ext_name}.vcxproj"
    vcxproj_path.write_text(vcxproj_content)

    # Fill in .sln content
    sln_content = SLN_TEMPLATE.substitute({
        "PROJECT_NAME": ext_name,
        "PROJECT_GUID": project_guid
    })

    sln_path = output_folder / f"{ext_name}.sln"
    sln_path.write_text(sln_content)

    return f"VS project created under: {output_folder}"

