# generator/cpp_bridge_gen.py
import os

def generate_cpp_bridge(parse_result, config):
    functions     = parse_result["functions"]
    known_structs = parse_result["known_structs"]

    header_file = config.get("header_file", "openxr.h").replace("\\", "/")
    namespace   = config.get("namespace", "XR")

    bridge = [f'''\
// Auto-generated GMBridge.cpp
#include <iostream>
#include <string>
#include <limits>
#include "{header_file}"
#include "RefManager.h"

extern double debug_mode;

extern "C" double get_debug_mode() {{
    return debug_mode;
}}
''']

    # --- Cache Manager bridge functions ---
    bridge.append("""

// Shared buffer for JSON/ref returns
static std::string _tmp_str;

// Cache Manager: get value by key
extern "C" const char* __ref_get(const char* ref, const char* key) {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_get" << std::endl;
    }
    _tmp_str = RefManager::instance().get(ref, key);
    return _tmp_str.c_str();
}

// Cache Manager: set full struct
extern "C" double __ref_set_struct(const char* ref, const char* json) {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_set_struct" << std::endl;
    }
    return RefManager::instance().set_struct(ref, json) ? 1.0 : 0.0;
}

// Cache Manager: get struct as JSON
extern "C" const char* __ref_json(const char* ref) {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_json" << std::endl;
    }

    void* obj = RefManager::instance().retrieve(ref);
    if (obj) {
        // If your type has to_json(), you can do:
        // _tmp_str = static_cast<YourType*>(obj)->to_json();
        // return _tmp_str.c_str();
    }

    _tmp_str = RefManager::instance().get_struct(ref);
    return _tmp_str.c_str();
}

// Cache Manager: destroy a single ref
extern "C" double __ref_destroy(const char* ref) {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_destroy" << std::endl;
    }
    RefManager::instance().release(ref);
    RefManager::instance().destroy(ref);
    return 1.0;
}

// Cache Manager: flush everything
extern "C" double __ref_manager_flush() {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_manager_flush (ALL)" << std::endl;
    }
    RefManager::instance().flush();
    return 1.0;
}

""")


    # === Struct constructors ===
    for s in sorted(known_structs):
        # e.g. XrMyStruct → __create_XrMyStruct()
        bridge.append(f'''
// Allocate a fresh {s} and hand back a GML ref
extern "C" const char* __create_{s}() {{
    auto* obj = new {s}{{}};  // zero-initialize
    std::string ref = RefManager::instance().store("{s}", obj);
    return ref.c_str();
}}
''')

    # --- Function bridges ---
    for fn in functions:
        name      = fn["name"]
        ret_meta  = fn.get("return_meta", {})
        ret_type  = ret_meta.get("gm_pass_type", "unknown")

        # detect a buffer-style out-param
        has_buffer_arg = False
        buffer_size    = None
        for arg in fn["args"]:
            if arg.get("gm_pass_type") == "buffer":
                has_buffer_arg = True
                buffer_size    = arg.get("array_size", "1024")
                break

        # choose return signature & error return
        if has_buffer_arg:
            ret_sig    = "const char*"
            err_return = "\"\""
        elif ret_type == "double":
            ret_sig    = "double"
            err_return = "std::numeric_limits<double>::quiet_NaN()"
        elif ret_type == "string":
            ret_sig    = "const char*"
            err_return = "\"\""
        elif ret_type == "ref":
            ret_sig    = "const char*"
            err_return = "_tmp_str.c_str()"
        else:
            ret_sig    = "const char*"
            err_return = "_tmp_str.c_str()"

        # build decls, conversions, and call-args
        decls, convert, call_args = [], [], []
        for i, arg in enumerate(fn["args"]):
            # drop buffer params—they become thread-local arrays
            if arg.get("gm_pass_type") == "buffer":
                continue

            aname     = arg["name"]
            pass_type = arg.get("gm_pass_type", "unknown")
            
            if pass_type == "double":
                decls.append(f"double {aname}")
                call_args.append(aname)

            elif pass_type == "string":
                decls.append(f"const char* {aname}")
                call_args.append(aname)

            elif pass_type == "ref":
                decls.append(f"const char* {aname}_ref")
                convert.append(f"""\
// Convert GML ref -> C++ pointer
    void* _ptr_{i} = RefManager::instance().retrieve({aname}_ref);
    if (!_ptr_{i}) return {err_return};""")
                call_args.append(f"_ptr_{i}")

            else:
                # fallback for anything else — show the original C type inline
                orig_type = arg.get("original_type", arg["type"])
                decls.append(f"/* unsupported: {orig_type} */ const char* {aname}")
                call_args.append(aname)

        # wrapper name (suffix _noBuf if buffer was dropped)
        suffix       = "_noBuf" if has_buffer_arg else ""
        wrapper_name = f"__{name}{suffix}"
        sig          = f'extern "C" {ret_sig} {wrapper_name}({", ".join(decls)})'

        bridge.append(f"// Bridge for {name}{suffix}")
        bridge.append(sig + " {")
        bridge.append(f'    if (debug_mode) std::cout << "[GMBridge] Called {name}" << std::endl;')
        bridge.extend(convert)

        if has_buffer_arg:
            bridge.append(f"    static thread_local char buf[{buffer_size}];")
            bridge.append(f"    // call original API, let it write into buf")
            bridge.append(f"    {name}({', '.join(call_args + ['buf'])});")
            bridge.append("    return buf;")
        else:
            bridge.append(f"    auto result = {name}({', '.join(call_args)});")
            if ret_sig == "double":
                bridge.append("    return result;")
            elif ret_type == "string":
                bridge.append("    return result;")
            elif ret_type == "ref":
                bridge.append(f"""\
// wrap into GML ref
    _tmp_str = RefManager::instance().store("{ret_meta.get('resolved_type','')}", result);
    return _tmp_str.c_str();""")
            else:
                bridge.append("    return nullptr;  // unsupported return")

        bridge.append("}\n")

    bridge_cpp = "\n".join(bridge)

    # emit RefManager.h/.cpp unchanged…
    ref_h = """\
#pragma once
#include <unordered_map>
#include <string>
#include <sstream>

class RefManager {
private:
    std::unordered_map<std::string, std::unordered_map<int, void*>> registry;
    std::unordered_map<std::string, int> counters;
    std::unordered_map<std::string, std::unordered_map<std::string, std::string>> json_data;

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

    void destroy(const std::string& ref) {
        json_data.erase(ref);
    }
    void flush() {
        registry.clear();
        counters.clear();
        json_data.clear();
    }
};
"""

    ref_cpp = '#include "RefManager.h"\n// nothing to implement here; header-only\n'

    return {
        config["output_cpp_file"]: bridge_cpp,
        "RefManager.h": ref_h,
        "RefManager.cpp": ref_cpp
    }
