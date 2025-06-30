# generator/cpp_bridge_gen.py
import os

def generate_cpp_bridge(functions, config):
    header_file = config.get("header_file", "openxr.h").replace("\\", "/")
    namespace   = config.get("namespace", "XR")

    bridge = [f'''\
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

    def is_numeric(t):
        t = t.lower().replace('const ', '').replace('*', '').strip()
        return t in ("float", "double", "int", "int32_t", "int64_t",
                     "short", "long", "size_t", "uint32_t", "uint64_t")

    # --- Cache Manager bridge functions ---
    bridge.append("""



// Cache Manager: set a key/value on an ref
extern "C" double __ref_set(const char* ref, const char* key, const char* json) {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_set" << std::endl;
    }
    // TODO: implement your global cache storage here
    return 1;  // success
}

// Cache Manager: get a simple value
extern "C" const char* __ref_get(const char* ref, const char* key) {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_get" << std::endl;
    }
    // TODO: implement retrieval (return a C-string)
    return "{}"; //returns a ref even if it's a `Real`
}

// Cache Manager: overwrite entire struct
extern "C" double __ref_set_struct(const char* ref, const char* json) {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_set_struct" << std::endl;
    }
    // TODO: implement struct overwrite
    return 1; // success
}

// Cache Manager: alias for ref_get_struct
extern "C" const char* __ref_json(const char* ref) {
    if (debug_mode) {
        std::cout << "[GMBridge] Called __ref_json" << std::endl;
    }
    return "{}"; //return a json of the full object/struct
}



""")

    for fn in functions:
        name      = fn["name"]
        ret       = fn["return_type"]
        ret_clean = ret.lower().replace('const ', '').strip()

        # Detect if last arg was a C‐style array (parser populated "array_size")
        has_array_arg = False
        array_size    = None
        if fn["args"]:
            last = fn["args"][-1]
            if "array_size" in last:
                has_array_arg = True
                array_size    = last["array_size"]

        # Choose return signature & error return
        if has_array_arg:
            # We're going to drop the buffer arg and return its contents as a C‐string
            ret_sig    = "const char*"
            err_return = "\"\""
        else:
            if is_numeric(ret_clean):
                ret_sig    = "double"
                err_return = "std::numeric_limits<double>::quiet_NaN()"
            else:
                ret_sig    = "const char*"
                err_return = "_err.c_str()"

        # Build argument decls, conversions, call args (skip the buffer if present)
        decls, convert, call_args = [], [], []
        for i, arg in enumerate(fn["args"]):
            ctype = arg["type"]
            aname = arg.get("name") or f"arg{i}"
            tclean = ctype.lower().replace('const ', '').replace('*','').strip()

            # Skip the buffer parameter entirely if it's the array
            if has_array_arg and i == len(fn["args"]) - 1:
                continue

            if is_numeric(tclean):
                decls.append(f"double {aname}")
                call_args.append(aname)
            else:
                decls.append(f"const char* {aname}_ref")
                convert.append(f'''\
        // arg #{i} ({aname})
        void* _ptr_{i} = RefManager::instance().retrieve({aname}_ref);
        if (!_ptr_{i}) {{
            std::string _err = "ref ERROR {namespace} {name} argument {i} incorrect type (\\"" + std::string({aname}_ref) + "\\") expecting a ref";
            return {err_return};
        }}''')
                call_args.append(f"_ptr_{i}")

        # Pick wrapper name: add “_noBuf” suffix if we dropped the buffer
        wrapper_name = f"__{name}{'_noBuf' if has_array_arg else ''}"
        sig = f'extern "C" {ret_sig} {wrapper_name}({", ".join(decls)})'
        bridge.append(f"// Bridge for {name}{'_noBuf' if has_array_arg else ''}\n{sig} {{")
        bridge.append(f'''\
        if (debug_mode) {{
            std::cout << "[GMBridge] Called {name}" << std::endl;
        }}''')
        bridge.extend(convert)

        # Actual call
        if has_array_arg:
            bridge.append(f"    // allocate a static buffer of size {array_size}")
            bridge.append(f"    static thread_local char buf[{array_size}];")
            bridge.append("    // call original C API, letting it write into buf")
            bridge.append(f"    {name}({', '.join(call_args + ['buf'])});")
            bridge.append("    return buf;")
        else:
            bridge.append("    // actual call")
            bridge.append(f"    auto result = {name}({', '.join(call_args)});")
            if ret_sig == "double":
                bridge.append("    return result;")
            else:
                if ret_clean in ("char*", "const char*"):
                    bridge.append("    return result;")
                else:
                    bridge.append(f'''\
        // wrap into GM ref
        std::string _result = RefManager::instance().store("{ret_clean}", result);
        return _result.c_str();''')

        bridge.append("}\n")

    # join all lines
    bridge_cpp = "\n".join(bridge)



    # --- RefManager.h ---
    ref_h = '''\
#pragma once
#include <unordered_map>
#include <string>
#include <sstream>
#include <mutex>

class RefManager {
private:
    std::unordered_map<std::string, std::unordered_map<int, void*>> registry;
    std::unordered_map<std::string, int> counters;
    std::mutex mutex_;

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
        std::lock_guard<std::mutex> lock(mutex_);
        int id = counters[type]++;
        registry[type][id] = ptr;
        return "ref " + type + " " + std::to_string(id);
    }

    void* retrieve(const std::string& ref) {
        std::lock_guard<std::mutex> lock(mutex_);
        std::istringstream ss(ref);
        std::string tag, type;
        int id;
        ss >> tag >> type >> id;
        if (tag != "ref") return nullptr;
        auto it = registry[type].find(id);
        return it != registry[type].end() ? it->second : nullptr;
    }

    void release(const std::string& ref) {
        std::lock_guard<std::mutex> lock(mutex_);
        std::istringstream ss(ref);
        std::string tag, type;
        int id;
        ss >> tag >> type >> id;
        registry[type].erase(id);
    }
};'''

    # --- RefManager.cpp (empty) ---
    ref_cpp = '#include "RefManager.h"\n// nothing to implement here; header-only\n'

    return {
        config["output_cpp_file"]: bridge_cpp,
        "RefManager.h": ref_h,
        "RefManager.cpp": ref_cpp
    }
