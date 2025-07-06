// Auto-generated GMBridge.cpp
#include <iostream>
#include <limits>
#include "openxr.h"
#include "RefManager.h"
#include <string>
#include <string_view>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <queue>
#include <stack>
#include <span>
#include <optional>
#include <variant>
#include <memory>
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
using GMString = std::string;
extern "C" const char* __cpp_create_string() {
    REFMAN_REGISTER_TYPE(string, GMString);
    
    auto* stringPtr = new GMString;
    std::string _tmp_str = RefManager::instance().store("string", stringPtr);
    return _tmp_str.c_str();
}

// === String View ===
using GMStringView = std::string_view;
extern "C" const char* __cpp_create_string_view() {
    REFMAN_REGISTER_TYPE(string_view, GMStringView);
    
    auto* stringViewPtr = new GMStringView{};
    std::string _tmp_str = RefManager::instance().store("string_view", stringViewPtr);
    return _tmp_str.c_str();
}

// === Vector<double> ===
using GMVectorOfDouble = std::vector<double>;
extern "C" const char* __cpp_create_vector() {
    REFMAN_REGISTER_TYPE(vector, GMVectorOfDouble);
    
    auto* vecPtr = new GMVectorOfDouble{};
    std::string _tmp_str = RefManager::instance().store("vector", vecPtr);
    return _tmp_str.c_str();
}

// === Map<string,double> ===
using GMMapOfStringDouble = std::unordered_map<std::string, double>;
extern "C" const char* __cpp_create_map() {
    REFMAN_REGISTER_TYPE(map, GMMapOfStringDouble);

    auto* mapPtr = new GMMapOfStringDouble{};
    std::string _tmp_str = RefManager::instance().store("map", mapPtr);
    return _tmp_str.c_str();
}

// === Set<string> ===
using GMSetOfString = std::unordered_set<std::string>;
extern "C" const char* __cpp_create_set() {
    REFMAN_REGISTER_TYPE(set, GMSetOfString);

    auto* setPtr = new GMSetOfString{};
    std::string _tmp_str = RefManager::instance().store("set", setPtr);
    return _tmp_str.c_str();
}

// === Queue<double> ===
using GMQueueOfDouble = std::queue<double>;
extern "C" const char* __cpp_create_queue() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        queue,
        // deleter
        [](void* pointer) {
            delete static_cast<GMQueueOfDouble*>(pointer);
        },
        // exporter: turn queue into a vector and serialize
        [](void* pointer) {
            auto* qp = static_cast<GMQueueOfDouble*>(pointer);
            GMQueueOfDouble copy = *qp;            // copy so we don’t consume the original
            std::vector<double> tempVec;
            while (!copy.empty()) {
                tempVec.push_back(copy.front());
                copy.pop();
            }
            return json(tempVec).dump();
        },
        // importer: parse vector and push back into queue
        [](void* pointer, const std::string& s) {
            auto* qp = static_cast<GMQueueOfDouble*>(pointer);
            std::vector<double> tempVec = json::parse(s).get<std::vector<double>>();
            GMQueueOfDouble empty;
            std::swap(*qp, empty);
            for (double v : tempVec) {
                qp->push(v);
            }
        }
    );
    
    auto* queuePtr = new GMQueueOfDouble{};
    std::string _tmp_str = RefManager::instance().store("queue", queuePtr);
    return _tmp_str.c_str();
}

// === Stack<double> ===
using GMStackOfDouble = std::stack<double>;
extern "C" const char* __cpp_create_stack() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        stack,
        /* deleter */ [](void* p) { delete static_cast<GMStackOfDouble*>(p); },
        /* exporter*/ [](void* p) {
            auto copy = *static_cast<GMStackOfDouble*>(p);
            std::vector<double> v;
            while (!copy.empty()) { v.push_back(copy.top()); copy.pop(); }
            return json(v).dump();
        },
        /* importer*/ [](void* p, const std::string& s) {
            auto* sp = static_cast<GMStackOfDouble*>(p);
            std::vector<double> v = json::parse(s).get<std::vector<double>>();
            GMStackOfDouble empty;
            std::swap(*sp, empty);
            for (double x : v) sp->push(x);
        }
    );

    

    auto* stackPtr = new GMStackOfDouble{};
    std::string _tmp_str = RefManager::instance().store("stack", stackPtr);
    return _tmp_str.c_str();
}

// === Buffer (uint8_t*) ===
using GMBufferPtr = uint8_t*;
extern "C" const char* __cpp_create_buffer() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        buffer,
        /* deleter */ [](void* p) {
            // p is uint8_t**; first delete the pointed‐to array, then the holder
            uint8_t* data = *static_cast<GMBufferPtr*>(p);
            delete[] data;
            delete static_cast<GMBufferPtr*>(p);
        },
        /* exporter */ nullptr,
        /* importer */ nullptr
    );

    auto* buffPtr = new GMBufferPtr{};
    std::string _tmp_str = RefManager::instance().store("buffer", buffPtr);
    return _tmp_str.c_str();
}

// === Span<uint8_t> ===
using GMSpanOfUint8 = std::span<uint8_t>;
extern "C" const char* __cpp_create_span() {
    REFMAN_REGISTER_TYPE(span, GMSpanOfUint8);

    auto* spanPtr = new GMSpanOfUint8{};
    std::string _tmp_str = RefManager::instance().store("span", spanPtr);
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

    auto* refPtr = new void* {};
    std::string _tmp_str = RefManager::instance().store("ref", refPtr);
    return _tmp_str.c_str();
}

// === Shared<T> ===
using GMSharedVoid = std::shared_ptr<void>;
extern "C" const char* __cpp_create_shared() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        shared,
        /* deleter: delete the holder itself */
        [](void* p) {
            delete static_cast<GMSharedVoid*>(p);
        },
        /* exporter: return the held GML ref if any */
        [](void* p) -> std::string {
            // get the shared_ptr<void>*
            auto sp = static_cast<GMSharedVoid*>(p);
            void* held = sp->get();  // NOT *sp!
            return RefManager::instance().get_ref_for_ptr(held);
        },
        /* importer: not needed here */
        nullptr
    );

    auto* sharedPtr = new GMSharedVoid{};
    std::string _tmp_str = RefManager::instance().store("shared", sharedPtr);
    return _tmp_str.c_str();
}

// === Optional<double> ===
using GMOptionalOfDouble = std::optional<double>;
extern "C" const char* __cpp_create_optional() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        optional,
        /*deleter=*/[](void* p) { delete static_cast<GMOptionalOfDouble*>(p); },
        /*exporter=*/[](void* p)->std::string {
            auto& opt = *static_cast<GMOptionalOfDouble*>(p);
            if (!opt.has_value()) return "null";
            return std::to_string(opt.value());
        },
        /*importer=*/[](void* p, const std::string& s) {
            auto& opt = *static_cast<GMOptionalOfDouble*>(p);
            if (s == "null" || s == "") {
                opt = std::nullopt;
            }
            else {
                opt = std::stod(s);
            }
        }
    );

    auto* optnPtr = new GMOptionalOfDouble{};
    std::string _tmp_str = RefManager::instance().store("optional", optnPtr);
    return _tmp_str.c_str();
}

// === Variant<int,double,string> ===
using GMVariantIntDoubleStr = std::variant<int, double, std::string>;
extern "C" const char* __cpp_create_variant() {
    REFMAN_REGISTER_TYPE_CUSTOM(
        variant,

        /* deleter */
        [](void* p) {
            delete static_cast<GMVariantIntDoubleStr*>(p);
        },

        /* exporter: serialize as [ index, value ] */
        [](void* p) -> std::string {
            auto* vp = static_cast<GMVariantIntDoubleStr*>(p);
            // produce a small JSON array: [which_index, value]
            int idx = static_cast<int>(vp->index());
            json out;
            std::visit([&](auto&& val) {
                out = json::array({ idx, val });
                }, *vp);
            return out.dump();
        },

        /* importer: parse [ index, value ] back into variant */
        [](void* p, const std::string& s) {
            auto* vp = static_cast<GMVariantIntDoubleStr*>(p);
            json in = json::parse(s);
            int idx = in.at(0).get<int>();
            // depending on idx, pull the right type
            switch (idx) {
            case 0: *vp = in.at(1).get<int>();        break;
            case 1: *vp = in.at(1).get<double>();     break;
            case 2: *vp = in.at(1).get<std::string>(); break;
            }
        }
    );

    auto* variantPtr = new GMVariantIntDoubleStr{};
    std::string _tmp_str = RefManager::instance().store("variant", variantPtr);
    return _tmp_str.c_str();
}

// === Pair<double,double> ===
using GMPairDoubleDouble = std::pair<double, double>;
extern "C" const char* __cpp_create_pair() {
    REFMAN_REGISTER_TYPE(pair, GMPairDoubleDouble);

    auto* pairPtr = new GMPairDoubleDouble{};
    std::string _tmp_str = RefManager::instance().store("pair", pairPtr);
    return _tmp_str.c_str();
}

#pragma endregion



#pragma region StructConstructors
${STRUCT_CONSTRUCTORS}
#pragma endregion

#pragma region FunctionsBridges
${FUNCTION_BRIDGES}
#pragma endregion
