import os

VALID_SOURCE_EXTENSIONS = {".cpp", ".cc", ".c"}
VALID_HEADER_EXTENSIONS = {".h", ".hpp", ".hh"}

def discover_all_sources(config):
    """
    Recursively scans the ./input folder for:
      - source files (.cpp, .cc, .c)
      - header files (.h, .hpp, .hh)
      - CMake scripts (CMakeLists.txt, *.cmake)
      - Map files (*.map)
      - Module-definition files (*.def)
      - Object files (.o/.obj)
      - Library files (.lib, .a)

    Honors any explicit overrides in config["cmake_overrides"] for CMake paths.

    Returns a dict:
        source_files:     list of source file paths
        header_files:     list of header file paths
        cmake_files:      list of CMakeLists.txt and .cmake file paths
        has_cmake_list:   True if a CMakeLists.txt is present
        map_files:        list of .map file paths
        def_files:        list of .def file paths
        object_files:     list of all discovered .o and .obj files
        library_files:    list of .lib and .a file paths
    """
    verbose = config.get("verbose_logging", False)
    if verbose:
        print("[GMBridge][discover_sources] Starting discover_all_sources()")

    project_root    = os.getcwd()
    input_directory = os.path.join(project_root, "input")
    if not os.path.isdir(input_directory):
        raise FileNotFoundError(f"Input directory not found: {input_directory!r}")
    input_directory = os.path.normpath(input_directory)
    if verbose:
        print(f"[GMBridge][discover_sources]  Input directory: {input_directory}")

    source_files    = []
    header_files    = []
    cmake_files     = []
    map_files       = []
    def_files       = []
    library_files   = []
    object_files    = []

    # 1) Collect any override CMake paths
    override_paths = []
    for override in config.get("cmake_overrides", {}).values():
        override_path = os.path.normpath(os.path.join(project_root, override))
        if os.path.isfile(override_path):
            override_paths.append(override_path)
    if verbose:
        print(f"[GMBridge][discover_sources]  CMake override paths: {override_paths}")

    # 2) Walk input/ for everything else
    for current_root, _, file_names in os.walk(input_directory):
        for file_name in file_names:
            file_path = os.path.normpath(os.path.join(current_root, file_name))
            ext       = os.path.splitext(file_name)[1].lower()
            lower     = file_name.lower()

            if ext in VALID_SOURCE_EXTENSIONS:
                source_files.append(file_path)
                continue

            if ext in VALID_HEADER_EXTENSIONS:
                header_files.append(file_path)
                continue

            if not override_paths and (lower == "cmakelists.txt" or ext == ".cmake"):
                cmake_files.append(file_path)
                continue

            if ext == ".map":
                map_files.append(file_path)
                continue

            if ext == ".def":
                def_files.append(file_path)
                continue

            if ext in {".o", ".obj"}:
                object_files.append(file_path)
                continue

            if ext in {".lib", ".a"}:
                library_files.append(file_path)
                continue

    if verbose:
        print(f"[GMBridge][discover_sources]  Collected {len(source_files)} source files")
        print(f"[GMBridge][discover_sources]  Collected {len(header_files)} header files")
        print(f"[GMBridge][discover_sources]  Collected {len(map_files)} map files")
        print(f"[GMBridge][discover_sources]  Collected {len(def_files)} def files")
        print(f"[GMBridge][discover_sources]  Collected {len(library_files)} library files")
        print(f"[GMBridge][discover_sources]  Collected {len(object_files)} object files")

    # 3) Apply CMake override if present
    if override_paths:
        cmake_files = override_paths
    if verbose:
        print(f"[GMBridge][discover_sources]  Final CMake files: {cmake_files}")

    # 4) Detect presence of any top-level CMakeLists.txt
    has_cmake_list = any(
        os.path.basename(path).lower() == "cmakelists.txt"
        for path in cmake_files
    )
    if verbose:
        print(f"[GMBridge][discover_sources]  has_cmake_list = {has_cmake_list}")

    return {
        "source_files":   source_files,
        "header_files":   header_files,
        "cmake_files":    cmake_files,
        "has_cmake_list": has_cmake_list,
        "map_files":      map_files,
        "def_files":      def_files,
        "object_files":   object_files,
        "library_files":  library_files
    }
