import os
import json
from parser import parse_header
from generator.cpp_bridge_gen import generate_cpp_bridge
from generator.gml_stub_gen import generate_gml_stub
from generator.yy_extension_gen import generate_yy_extension

def main():
    with open("config.json", "r") as cfg:
        config = json.load(cfg)

    header_path = os.path.join(config["input_folder"], config["header"])
    functions = parse_header(header_path)

    known_enum_typenames = set(k.lower() for k in functions["enums"].keys())

    # Handle C++ files
    cpp_files = generate_cpp_bridge(functions["functions"], config)
    for fname, content in cpp_files.items():
        with open(os.path.join(config["output_folder"], fname), "w") as f:
            f.write(content)

    # GML Stub output
    output_gml_path = os.path.join(config["output_folder"], config["gml_stub"])
    with open(output_gml_path, "w") as f:
        f.write(generate_gml_stub(functions, config))

    # YY Extension output
    output_yy_path = os.path.join(config["output_folder"], config["yy_extension"])
    with open(output_yy_path, "w") as f:
        f.write(generate_yy_extension(functions, config, known_enum_typenames))

if __name__ == "__main__":
    main()
