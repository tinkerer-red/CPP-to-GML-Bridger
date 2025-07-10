#ifndef ${PROJECT_NAME_UPPER}_BRIDGE_H
#define ${PROJECT_NAME_UPPER}_BRIDGE_H

#include "deps/nlohmann/json.hpp"
#include "RefManager.h"
${INCLUDE_LINES}

using nlohmann::json;

#pragma region CreateFunctions
${BUILTIN_CONSTRUCTORS}
#pragma endregion

#pragma region StructJSON
${JSON_OVERLOADS}
#pragma endregion

#pragma region Declarations
${DECLARATIONS}
#pragma endregion

#pragma region StructConstructors
${STRUCT_DEFS}
#pragma endregion

#pragma region FunctionBridges
${FUNCTION_DEFS}
#pragma endregion

#endif // ${PROJECT_NAME_UPPER}_BRIDGE_H


