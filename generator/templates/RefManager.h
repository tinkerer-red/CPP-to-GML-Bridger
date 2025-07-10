#pragma once
#include <unordered_map>
#include <string>
#include <sstream>
#include <functional>
#include <type_traits>
#include "deps/nlohmann/json.hpp"

using json = nlohmann::json;

class RefManager {
private:
    std::unordered_map<std::string, std::unordered_map<int, void*>> registry;
    std::unordered_map<std::string, std::unordered_map<void*, std::string>> reverse_registry;
    std::unordered_map<std::string, int> counters;
    std::unordered_map<std::string, std::function<void(void*)>> destroy_map;
    std::unordered_map<std::string, std::function<std::string(void*)>> json_exporter;
    std::unordered_map<std::string, std::function<void(void*, const std::string&)>> json_importer;

    RefManager() = default;
    ~RefManager() = default;
    RefManager(const RefManager&) = delete;
    RefManager& operator=(const RefManager&) = delete;

public:
    static RefManager& instance() {
        static RefManager inst;
        return inst;
    }

    // Parse "ref Type id"
    static bool parse_ref(const std::string& ref,
                          std::string& out_type,
                          int& out_id) {
        std::istringstream ss(ref);
        std::string tag;
        ss >> tag >> out_type >> out_id;
        return (tag == "ref" && !out_type.empty());
    }

    // Bridge entry for JSON serialization
    std::string to_string(const std::string& ref) const {
        std::string type; int id;
        if (!parse_ref(ref, type, id)) return "{}";
        void* ptr = retrieve(ref);
        if (!ptr) return "{}";
        if (auto it = json_exporter.find(type); it != json_exporter.end()) {
            return it->second(ptr);
        }
        return "{}";
    }

    // Bridge entry for JSON deserialization
    bool from_string(const std::string& ref, const std::string& data) const {
        std::string type; int id;
        if (!parse_ref(ref, type, id)) return false;
        void* ptr = retrieve(ref);
        if (!ptr) return false;
        // NEW: dispatch via importer map
        if (auto it = json_importer.find(type); it != json_importer.end()) {
            it->second(ptr, data);
            return true;
        }
        return false;
    }


    // Type registration for destruction
    void register_type_custom(
        const std::string& name,
        std::function<void(void*)> deleter,
        std::function<std::string(void*)> exporter = {},
        std::function<void(void*, const std::string&)> importer = {}
    ) {
        destroy_map[name] = std::move(deleter);
        if (exporter) json_exporter[name] = std::move(exporter);
        if (importer) json_importer[name] = std::move(importer);
    }

    // Store / retrieve / release
    std::string store(const std::string& type, void* ptr) {
        int id = counters[type]++;
        registry[type][id] = ptr;
        std::string ref = "ref " + type + " " + std::to_string(id);
        reverse_registry[type][ptr] = ref;
        return ref;
    }
    void* retrieve(const std::string& ref) const {
        std::istringstream ss(ref);
        std::string tag, type; int id;
        ss >> tag >> type >> id;
        if (tag != "ref") return nullptr;
        
        auto rit = registry.find(type);
        if (rit == registry.end()) return nullptr;

        auto it = rit->second.find(id);
        return it != rit->second.end() ? it->second : nullptr;
    }
    void release(const std::string& ref) {
        std::istringstream ss(ref);
        std::string tag, type; int id;
        ss >> tag >> type >> id;
        if (tag != "ref") return;

        auto rit = registry.find(type);
        if (rit == registry.end()) return;

        auto it = rit->second.find(id);
        if (it == rit->second.end()) return;

        void* ptr = it->second;
        auto dit = destroy_map.find(type);
        if (dit != destroy_map.end()) {
            dit->second(ptr);
        }
        
        rit->second.erase(it);
        reverse_registry[type].erase(ptr);
    }


    // Get the original ref string for a live pointer
    std::string get_ref_for_ptr(void* ptr) const {
        for (auto& [type, map] : reverse_registry) {
            if (auto it = map.find(ptr); it != map.end())
                return it->second;
        }
        return {};
    }

    // Clear everything
    void flush() {
        registry.clear();
        reverse_registry.clear();
        counters.clear();
        destroy_map.clear();
        json_exporter.clear();
        json_importer.clear();
    }
};


// === RefManager Macros ===
// For any TYPE that has global to_json/from_json and uses `new` allocation
#define REFMAN_REGISTER_TYPE(NAME, ...)                                    \
static bool _refman_registered_##NAME = []{                                 \
    auto& managerInstance = RefManager::instance();                         \
    managerInstance.register_type_custom(                                   \
        std::string(#NAME),                                                 \
        [](void* pointer){ delete static_cast<__VA_ARGS__*>(pointer); },    \
        [](void* pointer){                                                  \
            return json(*static_cast<__VA_ARGS__*>(pointer)).dump();       \
        },                                                                  \
        [](void* pointer, const std::string& str){                          \
            json::parse(str).get_to(*static_cast<__VA_ARGS__*>(pointer));  \
        }                                                                   \
    );                                                                      \
    return true;                                                            \
}();

// If you need a custom deleter/export/import
#define REFMAN_REGISTER_TYPE_CUSTOM(NAME, ...)                             \
static bool _refman_registered_##NAME = []{                                 \
    auto& managerInstance = RefManager::instance();                         \
    managerInstance.register_type_custom(                                   \
        std::string(#NAME), __VA_ARGS__                                     \
    );                                                                      \
    return true;                                                            \
}();