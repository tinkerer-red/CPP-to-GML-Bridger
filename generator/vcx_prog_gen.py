import os
import shutil
from pathlib import Path
from string import Template

# Constants
VCXPROJ_TEMPLATE = Template(r"""<?xml version="1.0" encoding="utf-8"?>
<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup Label="ProjectConfigurations">
    <ProjectConfiguration Include="Debug|x64">
      <Configuration>Debug</Configuration>
      <Platform>x64</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Release|x64">
      <Configuration>Release</Configuration>
      <Platform>x64</Platform>
    </ProjectConfiguration>
  </ItemGroup>

  <PropertyGroup Label="Globals">
    <ProjectGuid>{D41205A1-8A5E-4ED6-B2D0-620D16F12551}</ProjectGuid>
    <RootNamespace>GMBridge</RootNamespace>
    <Keyword>Win32Proj</Keyword>
  </PropertyGroup>

  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.Default.props" />

  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|x64'" Label="Configuration">
    <ConfigurationType>DynamicLibrary</ConfigurationType>
    <UseDebugLibraries>true</UseDebugLibraries>
    <PlatformToolset>v143</PlatformToolset>
  </PropertyGroup>

  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|x64'" Label="Configuration">
    <ConfigurationType>DynamicLibrary</ConfigurationType>
    <UseDebugLibraries>false</UseDebugLibraries>
    <PlatformToolset>v143</PlatformToolset>
  </PropertyGroup>

  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.props" />

  <ItemGroup>
    $CPP_FILES
  </ItemGroup>
  <ItemGroup>
    $HEADER_FILES
  </ItemGroup>

  <ItemDefinitionGroup>
    <ClCompile>
      <WarningLevel>Level3</WarningLevel>
      <SDLCheck>true</SDLCheck>
      <PreprocessorDefinitions>_CRT_SECURE_NO_WARNINGS;%(PreprocessorDefinitions)</PreprocessorDefinitions>
      <AdditionalIncludeDirectories>$(ProjectDir)include;%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>
    </ClCompile>
    <Link>
      <SubSystem>Windows</SubSystem>
      <GenerateDebugInformation>true</GenerateDebugInformation>
      <OutputFile>$(SolutionDir)project\extensions\GM_OpenXR\GMBridge.dll</OutputFile>
    </Link>
  </ItemDefinitionGroup>

  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.targets" />
</Project>
""")

# Function to generate .vcxproj and .sln files and move files to correct output structure
def generate_vs_project(config, output_folder):
    output_folder = Path(output_folder)
    src_dir = output_folder / "src"
    include_dir = src_dir / "include"
    extensions_dir = output_folder / "project" / "extensions" / "GM_OpenXR"

    src_dir.mkdir(parents=True, exist_ok=True)
    include_dir.mkdir(parents=True, exist_ok=True)
    extensions_dir.mkdir(parents=True, exist_ok=True)

    # Copy all files from input_folder to include/
    input_folder = Path(config["input_folder"])
    for root, _, files in os.walk(input_folder):
        for file in files:
            rel_path = Path(root).relative_to(input_folder)
            target_dir = include_dir / rel_path
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(Path(root) / file, target_dir / file)

    # Move generated bridge + RefManager files to src/
    bridge_cpp_file = Path(config["output_cpp_file"])
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

    vcxproj_content = VCXPROJ_TEMPLATE.substitute({
        "CPP_FILES": cpp_tags,
        "HEADER_FILES": h_tags
    })

    # Write the vcxproj
    vcxproj_path = src_dir / "GMBridge.vcxproj"
    vcxproj_path.write_text(vcxproj_content)

    # Write a minimal .sln file (can be expanded or generated with devenv if needed)
    sln_path = output_folder / "GMBridge.sln"
    sln_path.write_text("// Placeholder .sln file for GMBridge. Open VCXPROJ directly.\n")

    return f"VS project created under: {output_folder}"

generate_vs_project(
    config={
        "input_folder": "./example_input",
        "output_folder": "./output",
        "output_cpp_file": "./bridge.cpp"
    },
    output_folder="./output"
)