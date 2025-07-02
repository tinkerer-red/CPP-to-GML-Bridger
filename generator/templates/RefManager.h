#pragma once
#include <unordered_map>
#include <string>
#include <sstream>
#include <vector>
#include <functional>
#include <type_traits>

class RefManager {
private:
    std::unordered_map<std::string, std::unordered_map<int, void*>> registry;
    std::unordered_map<std::string, int> counters;
    std::unordered_map<std::string, std::unordered_map<std::string, std::string>> json_data;
    std::unordered_map<std::string, std::vector<char>> buffer_registry;
    std::unordered_map<std::string, std::function<void(void*)>> destroy_map;

    RefManager() = default;
    ~RefManager() = default;
    RefManager(const RefManager&) = delete;
    RefManager& operator=(const RefManager&) = delete;

public:
    static RefManager& instance() {
        static RefManager inst;
        return inst;
    }

    // === Type registration ===
    template<typename T>
    void register_type(const std::string& type_name) {
        destroy_map[type_name] = [](void* ptr) {
            delete static_cast<T*>(ptr);
        };
    }

    void register_type(const std::string& type_name, std::function<void(void*)> deleter) {
        destroy_map[type_name] = std::move(deleter);
    }

    // === JSON I/O ===
    void register_json_io(
        const std::string& type,
        std::function<std::string(void*)> exporter,
        std::function<void(void*, const std::string&)> importer
    ) {
        export_json_map[type] = std::move(exporter);
        import_json_map[type] = std::move(importer);
    }

    const std::function<std::string(void*)>* get_exporter(const std::string& type) const {
        auto it = export_json_map.find(type);
        return (it != export_json_map.end()) ? &it->second : nullptr;
    }

    const std::function<void(void*, const std::string&)>* get_importer(const std::string& type) const {
        auto it = import_json_map.find(type);
        return (it != import_json_map.end()) ? &it->second : nullptr;
    }
    
    // === Ref management ===
    std::string store(const std::string& type, void* ptr) {
        int id = counters[type]++;
        registry[type][id] = ptr;
        return "ref " + type + " " + std::to_string(id);
    }

    void* retrieve(const std::string& ref) {
        std::istringstream ss(ref);
        std::string tag, type;
        int id;
        ss >> tag >> type >> id;
        if (tag != "ref") return nullptr;
        auto it = registry[type].find(id);
        return it != registry[type].end() ? it->second : nullptr;
    }

    void release(const std::string& ref) {
        std::istringstream ss(ref);
        std::string tag, type;
        int id;
        ss >> tag >> type >> id;

        auto it = registry[type].find(id);
        if (it != registry[type].end()) {
            void* ptr = it->second;
            if (destroy_map.contains(type)) {
                destroy_map[type](ptr);
            }
            registry[type].erase(it);
        }
    }

    // === Cleanup ===
    void destroy(const std::string& ref) {
        json_data.erase(ref);
    }

    void flush() {
        registry.clear();
        counters.clear();
        json_data.clear();
        destroy_map.clear();
        buffer_registry.clear();
    }
};

// === RefManager Macros ===

#define REFMAN_REGISTER_TYPE(NAME, TYPE) \
    static bool _refman_registered_##TYPE = [] { \
        RefManager::instance().register_type<TYPE>(NAME); \
        return true; \
    }()

#define REFMAN_REGISTER_TYPE_CUSTOM(NAME, FN) \
    static bool _refman_registered_##NAME = [] { \
        RefManager::instance().register_type(NAME, FN); \
        return true; \
    }()

#define REFMAN_REGISTER_JSON_IO(NAME, EXPORT_FN, IMPORT_FN) \
    static bool _refman_json_registered_##NAME = [] { \
        RefManager::instance().register_json_io(NAME, EXPORT_FN, IMPORT_FN); \
        return true; \
    }()
