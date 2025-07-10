import os
import shutil

def copy_output_binary(config, output_info):
    """
    Copies a compiled binary into the GameMaker extension folder structure.

    Example target path:
      extensions/GM_OpenXR/platforms/Windows/x64/GM_OpenXR.dll
    """
    ext_folder = os.path.join(
        config["output_folder"],
        "extensions",
        config["dll_name"],
        "platforms",
        output_info["platform"],
        output_info["architecture"]
    )
    os.makedirs(ext_folder, exist_ok=True)

    target_path = os.path.join(ext_folder, output_info["filename"])

    shutil.copy2(output_info["full_path"], target_path)
    print(f"Copied: {output_info['filename']} -> {target_path}")
