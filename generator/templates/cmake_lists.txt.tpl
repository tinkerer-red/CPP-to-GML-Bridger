cmake_minimum_required(VERSION 3.14)
project(${PROJECT_NAME} LANGUAGES CXX)

# === Sources & Headers ===
add_library(${PROJECT_NAME} ${LIBRARY_TYPE}
$ALL_SOURCES
$ALL_HEADERS
)

# === Includes ===
target_include_directories(${PROJECT_NAME} PRIVATE
${INCLUDE_DIRS}
)

# === Defines ===
target_compile_definitions(${PROJECT_NAME} PRIVATE
${COMPILE_DEFINITIONS}
)

# === C++ Standard ===
target_compile_features(${PROJECT_NAME} PRIVATE cxx_std_${CPP_STANDARD})

# === Link Libraries ===
target_link_libraries(${PROJECT_NAME} PRIVATE
${LINK_LIBRARIES}
)

# === Output Locations ===
set_target_properties(${PROJECT_NAME} PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "$${CMAKE_BINARY_DIR}"
    LIBRARY_OUTPUT_DIRECTORY "$${CMAKE_BINARY_DIR}"
    ARCHIVE_OUTPUT_DIRECTORY "$${CMAKE_BINARY_DIR}"
)
