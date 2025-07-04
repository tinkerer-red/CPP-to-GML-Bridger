// Auto-generated GMBridge.cpp
#include <iostream>
#include <limits>
#include "${HEADER_FILE}"
#include "RefManager.h"
#include <string>
#include <nlohmann/json.hpp>
using json = nlohmann::json;

extern double debug_mode;

// Shared buffer for JSON/ref returns
static std::string _tmp_str;

// Cache Manager functions...
extern "C" const char* __cpp_to_json(const char* ref_cstr) {
    std::string ref(ref_cstr);

    // 1) Lookup the raw pointer from the GML ref
    void* ptr = RefManager::instance().retrieve(ref);
    if (!ptr) {
        _tmp_str = "{}";
        return _tmp_str.c_str();
    }

    // 2) Delegate to RefManager’s converter (which does json(obj).dump())
    _tmp_str = RefManager::instance().to_string(ref);

    // 3) Return the JSON text back to GML
    return _tmp_str.c_str();
}

extern "C" double __cpp_from_json(const char* ref_cstr, const char* json_cstr) {
    std::string ref(ref_cstr);
    std::string js(json_cstr);

    // Delegate to RefManager’s converter registry:
    bool ok = RefManager::instance().from_string(ref, js);

    // Return 1.0 for success, 0.0 for failure to GML
    return ok ? 1.0 : 0.0;
}

extern "C" double __ref_destroy(const char* ref) {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_destroy" << std::endl;
    }
    RefManager::instance().release(ref);
    RefManager::instance().destroy(ref);
    return 1.0;
}

extern "C" double __ref_manager_flush() {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_manager_flush (ALL)" << std::endl;
    }
    RefManager::instance().flush();
    return 1.0;
}


#pragma region CreateFunctions
// === String ===
extern "C" const char* __cpp_create_string() {
    auto* ptr = new std::string{};
    RefManager::instance().register_type<std::string>("string");
    _tmp_str = RefManager::instance().store("string", ptr);
    return _tmp_str.c_str();
}

// === String View ===
extern "C" const char* __cpp_create_string_view() {
    auto* ptr = new std::string_view{};
    RefManager::instance().register_type<std::string_view>("string_view");
    _tmp_str = RefManager::instance().store("string_view", ptr);
    return _tmp_str.c_str();
}

// === Vector<double> ===
extern "C" const char* __cpp_create_vector() {
    auto* ptr = new std::vector<double>{};
    RefManager::instance().register_type<std::vector<double>>("vector");
    _tmp_str = RefManager::instance().store("vector", ptr);
    return _tmp_str.c_str();
}

// === Map<string,double> ===
extern "C" const char* __cpp_create_map() {
    auto* ptr = new std::unordered_map<std::string,double>{};
    RefManager::instance().register_type<std::unordered_map<std::string,double>>("map");
    _tmp_str = RefManager::instance().store("map", ptr);
    return _tmp_str.c_str();
}

// === Set<string> ===
extern "C" const char* __cpp_create_set() {
    auto* ptr = new std::unordered_set<std::string>{};
    RefManager::instance().register_type<std::unordered_set<std::string>>("set");
    _tmp_str = RefManager::instance().store("set", ptr);
    return _tmp_str.c_str();
}

// === Queue<double> ===
extern "C" const char* __cpp_create_queue() {
    auto* ptr = new std::queue<double>{};
    RefManager::instance().register_type<std::queue<double>>("queue");
    _tmp_str = RefManager::instance().store("queue", ptr);
    return _tmp_str.c_str();
}

// === Stack<double> ===
extern "C" const char* __cpp_create_stack() {
    auto* ptr = new std::stack<double>{};
    RefManager::instance().register_type<std::stack<double>>("stack");
    _tmp_str = RefManager::instance().store("stack", ptr);
    return _tmp_str.c_str();
}

// === Buffer (uint8_t*) ===
extern "C" const char* __cpp_create_buffer() {
    auto* ptr = new uint8_t*{};
    RefManager::instance().register_type_custom("buffer",
        [](void* p){ RefManager::instance().destroy_buffer(*static_cast<uint8_t**>(p)); }
    );
    _tmp_str = RefManager::instance().store("buffer", ptr);
    return _tmp_str.c_str();
}

// === Span<uint8_t> ===
extern "C" const char* __cpp_create_span() {
    auto* ptr = new std::span<uint8_t>{};
    RefManager::instance().register_type<std::span<uint8_t>>("span");
    _tmp_str = RefManager::instance().store("span", ptr);
    return _tmp_str.c_str();
}

// === Raw Ref (T*) ===
extern "C" const char* __cpp_create_ref() {
    auto* ptr = new void*{};  // placeholder for arbitrary pointer
    RefManager::instance().register_type<void*>("ref");
    _tmp_str = RefManager::instance().store("ref", ptr);
    return _tmp_str.c_str();
}

// === Shared<T> ===
extern "C" const char* __cpp_create_shared() {
    auto* ptr = new std::shared_ptr<void>{};
    RefManager::instance().register_type<std::shared_ptr<void>>("shared");
    _tmp_str = RefManager::instance().store("shared", ptr);
    return _tmp_str.c_str();
}

// === Optional<double> ===
extern "C" const char* __cpp_create_optional() {
    auto* ptr = new std::optional<double>{};
    RefManager::instance().register_type<std::optional<double>>("optional");
    _tmp_str = RefManager::instance().store("optional", ptr);
    return _tmp_str.c_str();
}

// === Variant<int,double,string> ===
extern "C" const char* __cpp_create_variant() {
    auto* ptr = new std::variant<int,double,std::string>{};
    RefManager::instance().register_type<std::variant<int,double,std::string>>("variant");
    _tmp_str = RefManager::instance().store("variant", ptr);
    return _tmp_str.c_str();
}

// === Pair<double,double> ===
extern "C" const char* __cpp_create_pair() {
    auto* ptr = new std::pair<double,double>{};
    RefManager::instance().register_type<std::pair<double,double>>("pair");
    _tmp_str = RefManager::instance().store("pair", ptr);
    return _tmp_str.c_str();
}
#pragma endregion

#pragma region StructConstructors
${STRUCT_CONSTRUCTORS}
#pragma endregion

#pragma region FunctionsBridges
${FUNCTION_BRIDGES}
#pragma endregion
