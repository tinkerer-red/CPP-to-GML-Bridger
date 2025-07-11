#include "${PROJECT_NAME}.h"

extern "C" {

#pragma region StructConstructors
${STRUCT_DEFS}
#pragma endregion

#pragma region FunctionDefinitions
${FUNCTION_DEFS}
#pragma endregion

GM_FUNC(double) __test() {
    return 1.0;
}

}