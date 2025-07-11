# parser/preprocessor.py

import re
import shutil
import subprocess
import sys
from pathlib import Path

LINE_CONTINUATION_RE = re.compile(r'\\\s*\n')

def pick_preprocessor(cmds, verbose=False, was_user_configured=False):
    """
    Try each candidate list of args in `cmds`; return the first whose
    executable (cmds[i][0]) is found on PATH. If none match:
      - if was_user_configured: error out
      - otherwise: return (None, None)
    """
    for candidate in cmds:
        if not candidate or not isinstance(candidate, (list, tuple)):
            continue
        tool = candidate[0]
        if shutil.which(tool):
            if verbose:
                print(f"[GMBridge][preprocess] Using preprocessor: {tool}")
            inc_flag = "/I" if tool.lower() == "cl" else "-I"
            return candidate.copy(), inc_flag

    if was_user_configured:
        raise RuntimeError(
            "[GMBridge][preprocess] No suitable C preprocessor found for your\n"
            f"  configured candidate(s): {cmds!r}\n"
            "  • Ensure one of these tools is on your PATH,\n"
            "  • or remove the `preprocessor` entry from your config to auto-detect."
        )

    return None, None


def preprocess_sources(config, sources, defines):
    """
    1) If config['include_files'] is a non-empty list, only preprocess those.
    2) If config['include_files'] exists and is empty, preprocess ALL files from
       sources['header_files'] + sources['source_files'].
    3) Otherwise (missing or malformed), error out immediately.

    Each file is run through the C preprocessor, line-continuations and
    extra whitespace collapsed, then written to output/expanded_headers/.
    Returns a dict mapping each absolute input path → its expanded text.
    """
    project_root = Path.cwd()
    input_root   = project_root / "input"
    output_root  = project_root / "output"
    verbose_logging     = config.get("verbose_logging", False)
    include_directories = config.get("extra_includes", [])

    # ——— Validate and pick input files ———
    if "include_files" not in config:
        raise RuntimeError(
            "[GMBridge][preprocess] Missing `include_files` in config. "
            "Add it as a list of paths (or [] for auto-discovery)."
        )
    configured_list = config["include_files"]
    if not isinstance(configured_list, list):
        raise RuntimeError(
            f"[GMBridge][preprocess] `include_files` must be a list, got {type(configured_list).__name__}."
        )

    if configured_list:
        # user-specified; ignore everything else
        target_files = configured_list
    else:
        # empty list → auto-discover both headers & sources
        header_files = sources.get("header_files", [])
        source_files = sources.get("source_files", [])
        candidate_files = []

        if isinstance(header_files, list):
            candidate_files.extend(header_files)
        if isinstance(source_files, list):
            candidate_files.extend(source_files)

        if not candidate_files:
            raise RuntimeError(
                "[GMBridge][preprocess] Auto-discovery failed: no files in "
                "`sources['header_files']` or `sources['source_files']`. "
                "Either populate those in your discovery step or specify "
                "`include_files` in config."
            )
        target_files = candidate_files

    # ——— Build define flags ———
    define_flags = [f"-D{definition}" for definition in defines]
    define_flags += [f"-D{definition}" for definition in config.get("preprocessor_defines", [])]

    # ——— Pick preprocessor tool ———
    user_pp = config.get("preprocessor", [])
    if len(user_pp):
        if not isinstance(user_pp, (list, tuple)) or not user_pp:
            raise RuntimeError(
                "[GMBridge][preprocess] `preprocessor` must be a non-empty list of command+args."
            )
        base_cmd, inc_flag = pick_preprocessor([user_pp], verbose_logging, was_user_configured=True)
    else:
        # auto-detect path
        if sys.platform.startswith("win"):
            candidates = [
                ["cl",    "/E",   "/nologo"],
                ["clang", "-E",   "-dD",  "-P"],
                ["gcc",   "-E",   "-dD",  "-P"],
            ]
        else:
            candidates = [
                ["cpp",   "-P",   "-dD"],
                ["clang", "-E",   "-dD",  "-P"],
                ["gcc",   "-E",   "-dD",  "-P"],
            ]
        base_cmd, inc_flag = pick_preprocessor(candidates, verbose_logging, was_user_configured=False)
        if base_cmd is None:
            raise RuntimeError(
                "[GMBridge][preprocess] No C preprocessor could be auto-detected. "
                "Install `cpp`, `clang`, `gcc`, or `cl`, or set `preprocessor` in config."
            )

    # ——— Ensure output directory ———
    expanded_dir = project_root / "output" / "expanded_headers"
    expanded_dir.mkdir(parents=True, exist_ok=True)

    # ——— Run preprocessing ———
    results = {}
    for relative_path in target_files:
        path_obj = Path(relative_path)
        if not path_obj.is_absolute():
            path_obj = project_root / path_obj
        if not path_obj.exists():
            raise RuntimeError(
                f"[GMBridge][preprocess] File not found: {path_obj}\n"
                "Check your `include_files` entries or source discovery."
            )

        cmd = base_cmd + define_flags
        for inc in include_directories:
            cmd.append(f"{inc_flag}{inc}")
        cmd.append(str(path_obj))

        if verbose_logging:
            print(f"[GMBridge][preprocess] Running: {' '.join(cmd)}")

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        expanded_text = proc.stdout

        # collapse continuations & whitespace
        expanded_text = LINE_CONTINUATION_RE.sub(" ", expanded_text)
        expanded_text = re.sub(r"\s+", " ", expanded_text)

        # save
        absolute_key = str(path_obj.resolve())
        results[absolute_key] = expanded_text

        stem, suffix = path_obj.stem, path_obj.suffix
        out_file = expanded_dir / f"{stem}_expanded{suffix}"
        out_file.write_text(expanded_text, encoding="utf-8")

        if verbose_logging:
            print(f"[GMBridge][preprocess] Wrote: {out_file}")

    return results
