import shutil
from pathlib import Path

def copy_output_binary(config: dict, output_info: dict) -> str:
    """
    Copies a compiled binary into the GameMaker extension folder structure.

    Example destination:
      <output_folder>/extensions/GM_OpenXR/platforms/Windows/x64/GM_OpenXR.dll
    Returns the path to the copied binary.
    """
    # 1) Locate build directory
    project_root = Path.cwd()
    input_root   = project_root / "input"
    output_root  = project_root / "output"
    
    project_name = config.get("project_name", "GMBridge")
    extension_name = output_info["filename"]
    source_path = Path(output_info["full_path"])

    # Build destination directory
    destination_directory = (output_root / "extensions" / project_name)
    destination_directory.mkdir(parents=True, exist_ok=True)

    # Destination file path
    destination_path = destination_directory / output_info["filename"]

    # Copy the binary
    shutil.copy2(str(source_path), str(destination_path))

    # Optional log
    if config.get("verbose_logging", False):
        print(f"[GMBridge][copy] Copied binary from {source_path} to {destination_path}")

    return str(destination_path)
