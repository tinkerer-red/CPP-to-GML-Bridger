// Auto-generated GMBridge.cpp
#include <iostream>
#include <string>
#include <limits>
#include "${HEADER_FILE}"
#include "RefManager.h"

extern double debug_mode;

// Shared buffer for JSON/ref returns
static std::string _tmp_str;

// Cache Manager functions...
// Allocate a fresh buffer of `size` bytes and return its GML ref
extern "C" const char* __create_buffer(size_t size) {
    // ref string: "buffer <id>"
    _tmp_str = RefManager::instance().store("buffer", nullptr);
    RefManager::instance().set_buffer(_tmp_str, size);
    return _tmp_str.c_str();
}

// Get pointer into that buffer for C++ calls
extern "C" char* __get_buffer_ptr(const char* buf_ref) {
    return RefManager::instance().get_buffer(buf_ref);
}

// Destroy a buffer when you're done
extern "C" double __destroy_buffer(const char* buf_ref) {
    RefManager::instance().destroy(buf_ref);
    return 1.0;
}


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

// Struct constructors
${STRUCT_CONSTRUCTORS}

// Function bridges
${FUNCTION_BRIDGES}
