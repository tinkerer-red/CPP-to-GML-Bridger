#ifndef ${PROJECT_NAME_UPPER}_BRIDGE_H
#define ${PROJECT_NAME_UPPER}_BRIDGE_H

#if defined(_WIN32) || defined(_WIN64)
    #define GM_EXPORT extern "C" __declspec(dllexport)
    #define GM_CALL   __stdcall
#else
    #define GM_EXPORT extern "C" __attribute__((visibility("default")))
    #define GM_CALL
#endif

#define GM_FUNC(ret_type) GM_EXPORT ret_type GM_CALL

#include "deps/nlohmann/json.hpp"
#include "RefManager.h"
${INCLUDE_LINES}

using nlohmann::json;

#pragma region CreateFunctions
${BUILTIN_CONSTRUCTORS}
#pragma endregion

#pragma region Declarations
${DECLARATIONS}
#pragma endregion

#pragma region StructJSON
${JSON_OVERLOADS}
#pragma endregion

#endif // ${PROJECT_NAME_UPPER}_BRIDGE_H
