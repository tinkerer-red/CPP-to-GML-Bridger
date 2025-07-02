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

#pragma region CreateFunctions
extern "C" const char * __cpp_create_string() {
	auto ptr = new std::string();
	REFMAN_REGISTER_TYPE("string", std::string);
	REFMAN_REGISTER_JSON_IO("string",
		// Export
		[](void* ptr) -> std::string {
			return "\"" + *static_cast<std::string*>(ptr) + "\"";
		}

		// Import
		[](void* ptr, const std::string& json) {
			*static_cast<std::string*>(ptr) = json.substr(1, json.size() - 2);
		}

	);
	static std::string ref;
	ref = RefManager::instance().store("string", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_string_view() {
	auto ptr = new std::string_view();
	REFMAN_REGISTER_TYPE("string_view", std::string_view);
	REFMAN_REGISTER_JSON_IO("string_view",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("string_view", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_vector() {
	auto ptr = new std::vector < double > ();
	REFMAN_REGISTER_TYPE("vector", std::vector < double > );
	REFMAN_REGISTER_JSON_IO("vector",
		// Export
		[](void* ptr) -> std::string {
			auto& vec = *static_cast<std::vector<double>*>(ptr);
			std::ostringstream out;
			out << '[';
			for (size_t i = 0; i < vec.size(); ++i) {
				if (i > 0) out << ',';
				out << vec[i];
			}
			out << ']';
			return out.str();
		}

		// Import
		[](void* ptr, const std::string& json) {
			auto& vec = *static_cast<std::vector<double>*>(ptr);
			vec.clear();
			size_t pos = 0;
			while ((pos = json.find_first_of("0123456789-.", pos)) != std::string::npos) {
				size_t end = json.find_first_not_of("0123456789-.", pos);
				vec.push_back(std::stod(json.substr(pos, end - pos)));
				pos = end;
			}
		}

	);
	static std::string ref;
	ref = RefManager::instance().store("vector", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_map() {
	auto ptr = new std::unordered_map < std::string, double > ();
	REFMAN_REGISTER_TYPE("map", std::unordered_map < std::string, double > );
	REFMAN_REGISTER_JSON_IO("map",
		// Export
		[](void* ptr) -> std::string {
			auto& map = *static_cast<std::unordered_map<std::string, double>*>(ptr);
			std::ostringstream out;
			out << '{';
			bool first = true;
			for (const auto& [k, v] : map) {
				if (!first) out << ',';
				out << '\"' << k << "\":" << v;
				first = false;
			}
			out << '}';
			return out.str();
		}

		// Import
		[](void* ptr, const std::string& json) {
			auto& map = *static_cast<std::unordered_map<std::string, double>*>(ptr);
			map.clear();
			size_t pos = 0;
			while ((pos = json.find('\"', pos)) != std::string::npos) {
				size_t ks = pos + 1;
				size_t ke = json.find('\"', ks);
				std::string key = json.substr(ks, ke - ks);
				size_t colon = json.find(':', ke);
				size_t vs = json.find_first_of("0123456789-.", colon);
				size_t ve = json.find_first_not_of("0123456789-.", vs);
				double value = std::stod(json.substr(vs, ve - vs));
				map[key] = value;
				pos = ve;
			}
		}

	);
	static std::string ref;
	ref = RefManager::instance().store("map", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_set() {
	auto ptr = new std::unordered_set < std::string > ();
	REFMAN_REGISTER_TYPE("set", std::unordered_set < std::string > );
	REFMAN_REGISTER_JSON_IO("set",
		//Import:
		[](void* ptr, const std::string& json) {
			auto& set = *static_cast<std::unordered_set<std::string>*>(ptr);
			set.clear();
			size_t pos = 0;
			while ((pos = json.find('"', pos)) != std::string::npos) {
				size_t start = pos + 1;
				size_t end = json.find('"', start);
				set.insert(json.substr(start, end - start));
				pos = end + 1;
			}
		}
		//Export:
		[](void* ptr) -> std::string {
			auto& set = *static_cast<std::unordered_set<std::string>*>(ptr);
			std::ostringstream out;
			out << '[';
			bool first = true;
			for (const auto& val : set) {
				if (!first) out << ',';
				out << '"' << val << '"';
				first = false;
			}
			out << ']';
			return out.str();
		}
	);
	static std::string ref;
	ref = RefManager::instance().store("set", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_queue() {
	auto ptr = new std::queue < double > ();
	REFMAN_REGISTER_TYPE("queue", std::queue < double > );
	REFMAN_REGISTER_JSON_IO("queue",
		//Import:
		[](void* ptr, const std::string& json) {
			auto& q = *static_cast<std::queue<double>*>(ptr);
			std::queue<double> empty;
			std::swap(q, empty);
			size_t pos = 0;
			while ((pos = json.find_first_of("0123456789-.", pos)) != std::string::npos) {
				size_t end = json.find_first_not_of("0123456789-.", pos);
				q.push(std::stod(json.substr(pos, end - pos)));
				pos = end;
			}
		}
		//Export:
		[](void* ptr) -> std::string {
			auto q = *static_cast<std::queue<double>*>(ptr);
			std::ostringstream out;
			out << '[';
			bool first = true;
			while (!q.empty()) {
				if (!first) out << ',';
				out << q.front();
				q.pop();
				first = false;
			}
			out << ']';
			return out.str();
		}

	);
	static std::string ref;
	ref = RefManager::instance().store("queue", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_stack() {
	auto ptr = new std::stack < double > ();
	REFMAN_REGISTER_TYPE("stack", std::stack < double > );
	REFMAN_REGISTER_JSON_IO("stack",
		//Import:
		[](void* ptr, const std::string& json) {
			auto& s = *static_cast<std::stack<double>*>(ptr);
			std::stack<double> empty;
			std::swap(s, empty);
			std::vector<double> tmp;
			size_t pos = 0;
			while ((pos = json.find_first_of("0123456789-.", pos)) != std::string::npos) {
				size_t end = json.find_first_not_of("0123456789-.", pos);
				tmp.push_back(std::stod(json.substr(pos, end - pos)));
				pos = end;
			}
			for (double v : tmp) s.push(v);
		}
		//Export:
		[](void* ptr) -> std::string {
			auto s = *static_cast<std::stack<double>*>(ptr);
			std::vector<double> tmp;
			while (!s.empty()) {
				tmp.push_back(s.top());
				s.pop();
			}
			std::ostringstream out;
			out << '[';
			for (size_t i = 0; i < tmp.size(); ++i) {
				if (i > 0) out << ',';
				out << tmp[i];
			}
			out << ']';
			return out.str();
		}

	);
	static std::string ref;
	ref = RefManager::instance().store("stack", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_buffer() {
	auto ptr = new uint8_t * ();
	REFMAN_REGISTER_TYPE_CUSTOM("buffer", [](void * ptr) {
		RefManager::instance().destroy_buffer(static_cast <
			const char * > (ptr));
	});

	REFMAN_REGISTER_JSON_IO("buffer",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("buffer", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_span() {
	auto ptr = new std::span < uint8_t > ();
	REFMAN_REGISTER_TYPE("span", std::span < uint8_t > );
	REFMAN_REGISTER_JSON_IO("span",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("span", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_ref() {
	auto ptr = new T * ();
	REFMAN_REGISTER_TYPE("ref", T * );
	REFMAN_REGISTER_JSON_IO("ref",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("ref", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_shared() {
	auto ptr = new std::shared_ptr < T > ();
	REFMAN_REGISTER_TYPE("shared", std::shared_ptr < T > );
	REFMAN_REGISTER_JSON_IO("shared",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("shared", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_optional() {
	auto ptr = new std::optional < double > ();
	REFMAN_REGISTER_TYPE("optional", std::optional < double > );
	REFMAN_REGISTER_JSON_IO("optional",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("optional", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_variant() {
	auto ptr = new std::variant < int, double, std::string > ();
	REFMAN_REGISTER_TYPE("variant", std::variant < int, double, std::string > );
	REFMAN_REGISTER_JSON_IO("variant",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("variant", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_pair() {
	auto ptr = new std::pair < double, double > ();
	REFMAN_REGISTER_TYPE("pair", std::pair < double, double > );
	REFMAN_REGISTER_JSON_IO("pair",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("pair", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_tuple() {
	auto ptr = new std::tuple < double, double, double > ();
	REFMAN_REGISTER_TYPE("tuple", std::tuple < double, double, double > );
	REFMAN_REGISTER_JSON_IO("tuple",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("tuple", ptr);
	return ref.c_str();
}

extern "C" const char * __cpp_create_function() {
	auto ptr = new std:: function < void() > ();
	REFMAN_REGISTER_TYPE("function", std:: function < void() > );
	REFMAN_REGISTER_JSON_IO("function",
		[](void * ptr) -> std::string {
			return "{}";
		},
		[](void * ptr,
			const std::string & json) {}
	);
	static std::string ref;
	ref = RefManager::instance().store("function", ptr);
	return ref.c_str();
}
#pragma endregion

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
