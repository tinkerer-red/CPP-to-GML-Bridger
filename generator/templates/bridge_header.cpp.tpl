// Auto-generated GMBridge.cpp
#include <iostream>
#include <limits>
#include "openxr.h"
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
        std::string _tmp_str = "{}";
        return _tmp_str.c_str();
    }

    // 2) Delegate to RefManager’s converter (which does json(obj).dump())
    std::string _tmp_str = RefManager::instance().to_string(ref);

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
    REFMAN_REGISTER_TYPE(string, std::string);
    std::string _tmp_str = RefManager::instance().store("string", ptr);
    return _tmp_str.c_str();
}

// === String View ===
extern "C" const char* __cpp_create_string_view() {
    auto* ptr = new std::string_view{};
    REFMAN_REGISTER_TYPE(string_view, std::string_view);
    std::string _tmp_str = RefManager::instance().store("string_view", ptr);
    return _tmp_str.c_str();
}

// === Vector<double> ===
extern "C" const char* __cpp_create_vector() {
    auto* ptr = new std::vector<double>{};
    REFMAN_REGISTER_TYPE(vector, std::vector<double>);
    std::string _tmp_str = RefManager::instance().store("vector", ptr);
    return _tmp_str.c_str();
}

// === Map<string,double> ===
extern "C" const char* __cpp_create_map() {
    REFMAN_REGISTER_TYPE(map, std::unordered_map<std::string, double>);

    auto* mapPtr = new std::unordered_map<std::string, double>{};
    std::string _tmp_str = RefManager::instance().store("map", mapPtr);
    return _tmp_str.c_str();
}

// === Set<string> ===
extern "C" const char* __cpp_create_set() {
    REFMAN_REGISTER_TYPE(set, std::unordered_set<std::string>);

    auto* ptr = new std::unordered_set<std::string>{};
    std::string _tmp_str = RefManager::instance().store("set", ptr);
    return _tmp_str.c_str();
}

/ === Queue<double> ===
extern "C" const char* __cpp_create_queue() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        queue,
        // deleter
        [](void* pointer) {
            delete static_cast<std::queue<double>*>(pointer);
        },
        // exporter: turn queue into a vector and serialize
        [](void* pointer) {
            auto* qp = static_cast<std::queue<double>*>(pointer);
            std::queue<double> copy = *qp;            // copy so we don’t consume the original
            std::vector<double> tempVec;
            while (!copy.empty()) {
                tempVec.push_back(copy.front());
                copy.pop();
            }
            return json(tempVec).dump();
        },
        // importer: parse vector and push back into queue
        [](void* pointer, const std::string& s) {
            auto* qp = static_cast<std::queue<double>*>(pointer);
            std::vector<double> tempVec = json::parse(s).get<std::vector<double>>();
            std::queue<double> empty;
            std::swap(*qp, empty);
            for (double v : tempVec) {
                qp->push(v);
            }
        }
    );
    
    auto* queuePtr = new std::queue<double>{};
    std::string _tmp_str = RefManager::instance().store("queue", queuePtr);
    return _tmp_str.c_str();
}

// === Stack<double> ===
extern "C" const char* __cpp_create_stack() {
    REFMAN_REGISTER_TYPE(stack, std::stack<double>);

    auto* ptr = new std::stack<double>{};
    std::string _tmp_str = RefManager::instance().store("stack", ptr);
    return _tmp_str.c_str();
}

// === Buffer (uint8_t*) ===
extern "C" const char* __cpp_create_buffer() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        buffer,
        /* deleter */ [](void* p) {
            // p is uint8_t**; first delete the pointed‐to array, then the holder
            uint8_t* data = *static_cast<uint8_t**>(p);
            delete[] data;
            delete static_cast<uint8_t**>(p);
        },
        /* exporter */ nullptr,
        /* importer */ nullptr
    );

    auto* ptr = new uint8_t* {};
    std::string _tmp_str = RefManager::instance().store("buffer", ptr);
    return _tmp_str.c_str();
}

// === Span<uint8_t> ===
extern "C" const char* __cpp_create_span() {
    REFMAN_REGISTER_TYPE(span, std::span<uint8_t>);

    auto* ptr = new std::span<uint8_t>{};
    std::string _tmp_str = RefManager::instance().store("span", ptr);
    return _tmp_str.c_str();
}

// === Raw Ref (void*) ===
extern "C" const char* __cpp_create_ref() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        ref,
        /*deleter*/    [](void* p) { delete static_cast<void**>(p); },
        /*exporter*/   [](void* p) {
            // get the already‐registered GML ref for the inner pointer
            return RefManager::instance().get_ref_for_ptr(*static_cast<void**>(p));
        },
        /*importer*/   nullptr
    );

    auto* ptr = new void* {};
    std::string _tmp_str = RefManager::instance().store("ref", ptr);
    return _tmp_str.c_str();
}

// === Shared<T> ===
extern "C" const char* __cpp_create_shared() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        shared,
        /* deleter: delete the holder itself */
        [](void* p) {
            delete static_cast<std::shared_ptr<void>*>(p);
        },
        /* exporter: return the held GML ref if any */
        [](void* p) -> std::string {
            // get the shared_ptr<void>*
            auto sp = static_cast<std::shared_ptr<void>*>(p);
            void* held = sp->get();  // NOT *sp!
            return RefManager::instance().get_ref_for_ptr(held);
        },
        /* importer: not needed here */
        nullptr
    );

    auto* ptr = new std::shared_ptr<void>{};
    std::string _tmp_str = RefManager::instance().store("shared", ptr);
    return _tmp_str.c_str();
}

// === Optional<double> ===
extern "C" const char* __cpp_create_optional() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        optional,
        /*deleter=*/[](void* p) { delete static_cast<std::optional<double>*>(p); },
        /*exporter=*/[](void* p)->std::string {
            auto& opt = *static_cast<std::optional<double>*>(p);
            if (!opt.has_value()) return "null";
            return std::to_string(opt.value());
        },
        /*importer=*/[](void* p, const std::string& s) {
            auto& opt = *static_cast<std::optional<double>*>(p);
            if (s == "null" || s == "") {
                opt = std::nullopt;
            }
            else {
                opt = std::stod(s);
            }
        }
    );

    auto* ptr = new std::optional<double>{};
    std::string _tmp_str = RefManager::instance().store("optional", ptr);
    return _tmp_str.c_str();
}

// === Variant<int,double,string> ===
extern "C" const char* __cpp_create_variant() {
    REFMAN_REGISTER_TYPE(variant, std::variant<int, double, std::string>);

    auto* variantPtr = new std::variant<int, double, std::string>{};
    std::string _tmp_str = RefManager::instance().store("variant", variantPtr);
    return _tmp_str.c_str();
}

// === Pair<double,double> ===
extern "C" const char* __cpp_create_pair() {
    REFMAN_REGISTER_TYPE(pair, std::pair<double, double>);

    auto* ptr = new std::pair<double, double>{};
    std::string _tmp_str = RefManager::instance().store("pair", ptr);
    return _tmp_str.c_str();
}

#pragma endregion


#pragma region StructConstructors
${STRUCT_CONSTRUCTORS}
#pragma endregion

#pragma region FunctionsBridges
${FUNCTION_BRIDGES}
#pragma endregion
