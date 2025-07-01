#pragma once
#include <unordered_map>
#include <string>
#include <sstream>

class RefManager {
private:
    std::unordered_map<std::string, std::unordered_map<int, void*>> registry;
    std::unordered_map<std::string, int> counters;
    std::unordered_map<std::string, std::unordered_map<std::string, std::string>> json_data;
    std::unordered_map<std::string, std::vector<char>> buffer_registry;

    RefManager() = default;
    ~RefManager() = default;
    RefManager(const RefManager&) = delete;
    RefManager& operator=(const RefManager&) = delete;

public:
    static RefManager& instance() {
        static RefManager inst;
        return inst;
    }

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
        registry[type].erase(id);
    }

    bool set(const std::string& ref, const std::string& key, const std::string& value) {
        json_data[ref][key] = value;
        return true;
    }
    std::string get(const std::string& ref, const std::string& key) {
        return json_data[ref][key];
    }

    bool set_struct(const std::string& ref, const std::string& json) {
        json_data[ref].clear();
        size_t pos = 0;
        while ((pos = json.find("\"", pos)) != std::string::npos) {
            size_t ks = pos+1, ke = json.find("\"", ks);
            std::string k = json.substr(ks, ke-ks);
            size_t colon = json.find(":", ke);
            size_t vs = json.find("\"", colon), ve = json.find("\"", vs+1);
            std::string v = json.substr(vs+1, ve-vs-1);
            json_data[ref][k] = v;
            pos = ve+1;
        }
        return true;
    }

    std::string get_struct(const std::string& ref) {
        std::ostringstream out;
        out << "{";
        bool first = true;
        for (auto& [k,v] : json_data[ref]) {
            if (!first) out << ",";
            out << "\"" << k << "\":\"" << v << "\"";
            first = false;
        }
        out << "}";
        return out.str();
    }

    /// Create or resize a named buffer
    bool set_buffer(const std::string& ref, size_t size) {
        buffer_registry[ref].assign(size, '\0');
        return true;
    }
    /// Get raw pointer to buffer data
    char* get_buffer(const std::string& ref) {
        auto it = buffer_registry.find(ref);
        return (it != buffer_registry.end()) ? it->second.data() : nullptr;
    }
    /// Destroy a buffer
    void destroy_buffer(const std::string& ref) {
        buffer_registry.erase(ref);
    }

    void destroy(const std::string& ref) {
        json_data.erase(ref);
    }
    void flush() {
        registry.clear();
        counters.clear();
        json_data.clear();
    }
};