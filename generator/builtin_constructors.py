# generator/builtin_constructors.py
import re

def sanitize_type_name(type_name: str) -> str:
    cleaned_string = re.sub(r'[^0-9A-Za-z_]', '_', type_name)
    cleaned_string = re.sub(r'__+', '_', cleaned_string).strip('_')
    return cleaned_string

def gen_string() -> str:
    return """
using GMString = std::string;
extern "C" const char* __cpp_create_string() {
    REFMAN_REGISTER_TYPE(string, GMString);
    auto* stringPtr = new GMString{};
    std::string _tmp_str = RefManager::instance().store("string", stringPtr);
    return _tmp_str.c_str();
}
""".strip()

def gen_string_view() -> str:
    return """
using GMStringView = std::string_view;
extern "C" const char* __cpp_create_string_view() {
    REFMAN_REGISTER_TYPE(string_view, GMStringView);
    auto* viewPtr = new GMStringView{};
    std::string _tmp_str = RefManager::instance().store("string_view", viewPtr);
    return _tmp_str.c_str();
}
""".strip()

def gen_vector(element_type: str) -> str:
    suffix     = sanitize_type_name(f"vector_{element_type}")
    alias_name = f"GMVectorOf{sanitize_type_name(element_type).title()}"
    return f"""
using {alias_name} = std::vector<{element_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(vector, {alias_name});
    auto* vecPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("vector", vecPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_array(element_type: str, size: int) -> str:
    suffix     = sanitize_type_name(f"array_{element_type}_{size}")
    alias_name = f"GMArrayOf{sanitize_type_name(element_type).title()}_{size}"
    return f"""
using {alias_name} = std::array<{element_type}, {size}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(array, {alias_name});
    auto* arrPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("array", arrPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_deque(element_type: str) -> str:
    suffix     = sanitize_type_name(f"deque_{element_type}")
    alias_name = f"GMDequeOf{sanitize_type_name(element_type).title()}"
    return f"""
using {alias_name} = std::deque<{element_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(deque, {alias_name});
    auto* deqPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("deque", deqPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_list(element_type: str) -> str:
    suffix     = sanitize_type_name(f"list_{element_type}")
    alias_name = f"GMListOf{sanitize_type_name(element_type).title()}"
    return f"""
using {alias_name} = std::list<{element_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(list, {alias_name});
    auto* lstPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("list", lstPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_set(element_type: str) -> str:
    suffix     = sanitize_type_name(f"set_{element_type}")
    alias_name = f"GMSetOf{sanitize_type_name(element_type).title()}"
    return f"""
using {alias_name} = std::set<{element_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(set, {alias_name});
    auto* setPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("set", setPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_unordered_set(element_type: str) -> str:
    suffix     = sanitize_type_name(f"unordered_set_{element_type}")
    alias_name = f"GMUnorderedSetOf{sanitize_type_name(element_type).title()}"
    return f"""
using {alias_name} = std::unordered_set<{element_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(unordered_set, {alias_name});
    auto* usetPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("unordered_set", usetPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_ordered_map(key_type: str, value_type: str) -> str:
    suffix     = sanitize_type_name(f"map_{key_type}_{value_type}")
    alias_name = f"GMMapOf{sanitize_type_name(key_type).title()}To{sanitize_type_name(value_type).title()}"
    return f"""
using {alias_name} = std::map<{key_type}, {value_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(map, {alias_name});
    auto* mapPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("map", mapPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_unordered_map(key_type: str, value_type: str) -> str:
    suffix     = sanitize_type_name(f"unordered_map_{key_type}_{value_type}")
    alias_name = f"GMUnorderedMapOf{sanitize_type_name(key_type).title()}To{sanitize_type_name(value_type).title()}"
    return f"""
using {alias_name} = std::unordered_map<{key_type}, {value_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(unordered_map, {alias_name});
    auto* umapPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("unordered_map", umapPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_pair(first_type: str, second_type: str) -> str:
    suffix     = sanitize_type_name(f"pair_{first_type}_{second_type}")
    alias_name = f"GMPair{sanitize_type_name(first_type).title()}{sanitize_type_name(second_type).title()}"
    return f"""
using {alias_name} = std::pair<{first_type}, {second_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(pair, {alias_name});
    auto* pairPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("pair", pairPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_tuple(type_list: str) -> str:
    types      = [t.strip() for t in type_list.split(',')]
    suffix     = sanitize_type_name(f"tuple_{'_'.join(types)}")
    alias_name = "GMTuple" + "".join(sanitize_type_name(t).title() for t in types)
    return f"""
using {alias_name} = std::tuple<{', '.join(types)}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(tuple, {alias_name});
    auto* tplPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("tuple", tplPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_optional(inner_type: str) -> str:
    suffix     = sanitize_type_name(f"optional_{inner_type}")
    alias_name = f"GMOptionalOf{sanitize_type_name(inner_type).title()}"
    return f"""
using {alias_name} = std::optional<{inner_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE_CUSTOM(
        optional,
        /* deleter */[](void* p) {{ delete static_cast<{alias_name}*>(p); }},
        /* exporter */[](void* p)->std::string {{
            auto& opt = *static_cast<{alias_name}*>(p);
            if (!opt.has_value()) return "null";
            return std::to_string(opt.value());
        }},
        /* importer */[](void* p, const std::string& s) {{
            auto& opt = *static_cast<{alias_name}*>(p);
            if (s == "null" or s.empty()) opt = std::nullopt;
            else opt = std::stod(s);
        }}
    );
    auto* optPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("optional", optPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_variant(type_list: str) -> str:
    variants  = [t.strip() for t in type_list.split(',')]
    suffix    = sanitize_type_name(f"variant_{'_'.join(variants)}")
    alias_name = "GMVariant" + "".join(sanitize_type_name(v).title() for v in variants)
    case_lines = []
    for index, typ in enumerate(variants):
        case_lines.append(f"            case {index}: *vp = in.at(1).get<{typ}>(); break;")
    case_block = "\n".join(case_lines)
    return f"""
using {alias_name} = std::variant<{', '.join(variants)}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE_CUSTOM(
        variant,
        /* deleter */[](void* p) {{ delete static_cast<{alias_name}*>(p); }},
        /* exporter */[](void* p)->std::string {{
            auto* vp = static_cast<{alias_name}*>(p);
            int idx = static_cast<int>(vp->index());
            nlohmann::json out;
            std::visit([&](auto&& val) {{ out = nlohmann::json::array({{ idx, val }}); }}, *vp);
            return out.dump();
        }},
        /* importer */[](void* p, const std::string& s) {{
            auto* vp = static_cast<{alias_name}*>(p);
            nlohmann::json in = nlohmann::json::parse(s);
            int idx = in.at(0).get<int>();
            switch(idx) {{
{case_block}
            }}
        }}
    );
    auto* varPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("variant", varPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_shared_ptr(inner_type: str) -> str:
    suffix     = sanitize_type_name(f"shared_ptr_{inner_type}")
    alias_name = f"GMSharedPtrOf{sanitize_type_name(inner_type).title()}"
    return f"""
using {alias_name} = std::shared_ptr<{inner_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(shared_ptr, {alias_name});
    auto* spPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("shared_ptr", spPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_unique_ptr(inner_type: str) -> str:
    suffix     = sanitize_type_name(f"unique_ptr_{inner_type}")
    alias_name = f"GMUniquePtrOf{sanitize_type_name(inner_type).title()}"
    return f"""
using {alias_name} = std::unique_ptr<{inner_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(unique_ptr, {alias_name});
    auto* upPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("unique_ptr", upPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_weak_ptr(inner_type: str) -> str:
    suffix     = sanitize_type_name(f"weak_ptr_{inner_type}")
    alias_name = f"GMWeakPtrOf{sanitize_type_name(inner_type).title()}"
    return f"""
using {alias_name} = std::weak_ptr<{inner_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(weak_ptr, {alias_name});
    auto* wpPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("weak_ptr", wpPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_function(return_type: str, args_list: str) -> str:
    arg_sanit = sanitize_type_name(args_list.replace(',', '_'))
    suffix    = sanitize_type_name(f"function_{return_type}_{arg_sanit}")
    alias_name = f"GMFunctionOf{sanitize_type_name(return_type).title()}_{arg_sanit.title()}"
    return f"""
using {alias_name} = std::function<{return_type}({args_list})>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(function, {alias_name});
    auto* fnPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("function", fnPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_span(element_type: str) -> str:
    suffix     = sanitize_type_name(f"span_{element_type}")
    alias_name = f"GMSpanOf{sanitize_type_name(element_type).title()}"
    return f"""
using {alias_name} = std::span<{element_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(span, {alias_name});
    auto* spPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("span", spPtr);
    return _tmp_str.c_str();
}}
""".strip()

def gen_queue(element_type: str) -> str:
    suffix     = sanitize_type_name(f"queue_{element_type}")
    alias_name = f"GMQueueOf{sanitize_type_name(element_type).title()}"
    return f"""
using {alias_name} = std::queue<{element_type}>;
extern "C" const char* __cpp_create_{suffix}() {{
    REFMAN_REGISTER_TYPE(queue, {alias_name});
    auto* qPtr = new {alias_name}{{}};
    std::string _tmp_str = RefManager::instance().store("queue", qPtr);
    return _tmp_str.c_str();
}}
""".strip()

BUILTIN_PATTERNS = [
    (re.compile(r'^std\.string$'),                                lambda m: gen_string()),
    (re.compile(r'^std\.string_view$'),                           lambda m: gen_string_view()),
    (re.compile(r'^std\.vector<\s*(.+?)\s*>$'),                   lambda m: gen_vector(m.group(1))),
    (re.compile(r'^std\.array<\s*(.+?)\s*,\s*(\d+)\s*>$'),         lambda m: gen_array(m.group(1), int(m.group(2)))),
    (re.compile(r'^std\.deque<\s*(.+?)\s*>$'),                    lambda m: gen_deque(m.group(1))),
    (re.compile(r'^std\.list<\s*(.+?)\s*>$'),                     lambda m: gen_list(m.group(1))),
    (re.compile(r'^std\.set<\s*(.+?)\s*>$'),                      lambda m: gen_set(m.group(1))),
    (re.compile(r'^std\.unordered_set<\s*(.+?)\s*>$'),            lambda m: gen_unordered_set(m.group(1))),
    (re.compile(r'^std\.map<\s*(.+?)\s*,\s*(.+?)\s*>$'),          lambda m: gen_ordered_map(m.group(1), m.group(2))),
    (re.compile(r'^std\.unordered_map<\s*(.+?)\s*,\s*(.+?)\s*>$'), lambda m: gen_unordered_map(m.group(1), m.group(2))),
    (re.compile(r'^std\.pair<\s*(.+?)\s*,\s*(.+?)\s*>$'),         lambda m: gen_pair(m.group(1), m.group(2))),
    (re.compile(r'^std\.tuple<\s*(.+?)\s*>$'),                    lambda m: gen_tuple(m.group(1))),
    (re.compile(r'^std\.optional<\s*(.+?)\s*>$'),                 lambda m: gen_optional(m.group(1))),
    (re.compile(r'^std\.variant<\s*(.+?)\s*>$'),                  lambda m: gen_variant(m.group(1))),
    (re.compile(r'^std\.shared_ptr<\s*(.+?)\s*>$'),               lambda m: gen_shared_ptr(m.group(1))),
    (re.compile(r'^std\.unique_ptr<\s*(.+?)\s*>$'),               lambda m: gen_unique_ptr(m.group(1))),
    (re.compile(r'^std\.weak_ptr<\s*(.+?)\s*>$'),                 lambda m: gen_weak_ptr(m.group(1))),
    (re.compile(r'^std\.function<\s*([^>]+)\(([^)]*)\)\s*>$'),     lambda m: gen_function(m.group(1), m.group(2))),
    (re.compile(r'^std\.span<\s*(.+?)\s*>$'),                     lambda m: gen_span(m.group(1))),
    (re.compile(r'^std\.queue<\s*(.+?)\s*>$'),                    lambda m: gen_queue(m.group(1))),
]
