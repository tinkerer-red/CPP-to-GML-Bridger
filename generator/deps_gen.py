import shutil
from pathlib import Path

def install_dependencies(config):
    """
    Copies any header-only deps into ./output/deps/include.
    Expects config["deps"] = list of { "source": "<path/to/json.hpp>", "subdir": "nlohmann" }
    """
    out_deps = Path.cwd() / "output" / "deps" / "include"
    for dep in config.get("deps", []):
        src = Path(dep["source"])
        dst = out_deps / dep.get("subdir", "") / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
        print(f"[GMBridge][deps_gen] Installed {src} → {dst}")
