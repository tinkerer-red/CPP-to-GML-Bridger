import os
import json

from parser import parse_header
from generator.cpp_bridge_gen import generate_cpp_bridge
from generator.gml_stub_gen import generate_gml_stub
from generator.yy_extension_gen import generate_yy_extension
from generator.vcx_proj_gen import generate_vs_project

def main():
    # Load tool configuration
    with open("config.json", "r", encoding="utf-8") as cfg_file:
        config = json.load(cfg_file)

    # Parse the header into a single result dict
    parse_result  = parse_header(config)

    # 1) Generate C++ bridge files
    cpp_files = generate_cpp_bridge(parse_result, config)
    for fname, content in cpp_files.items():
        out_path = os.path.join(config["output_folder"], fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

    # 2) Generate the GML stub
    gml_file = generate_gml_stub(parse_result, config)
    gml_path = os.path.join(config["output_folder"], config["gml_stub"])
    with open(gml_path, "w", encoding="utf-8") as f:
        f.write(gml_file)

    # 3) Generate the YY extension file
    yy_file = generate_yy_extension(parse_result, config)
    yy_path = os.path.join(config["output_folder"], config["yy_extension"])
    with open(yy_path, "w", encoding="utf-8") as f:
        f.write(yy_file)

    # 4) Build the Visual Studio project structure
    generate_vs_project(config, config["output_folder"])

if __name__ == "__main__":
    main()
