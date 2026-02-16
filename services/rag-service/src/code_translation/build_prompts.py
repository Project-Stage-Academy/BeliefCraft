from code_translation.python_github_code import process

from pdf_parsing.extract_algorithms_and_examples import extract_algorithms_and_examples, extract_algorithms

import re

def extract_entities_from_algorithm(code: str):
    IDENT = r"[A-Za-z_\u0080-\uFFFF]\w*"
    FUNC_NAME = rf"{IDENT}[!?]?"

    oneliner_func_re = re.compile(rf"^\s*({FUNC_NAME})\s*\([^=\n]*\)\s*=")
    block_func_re    = re.compile(rf"^\s*function\s+({FUNC_NAME})\(")
    struct_re        = re.compile(rf"^\s*(?:mutable\s+)?struct\s+({IDENT})\b")

    # відкривачі блоків (які закриваються end)
    block_open_re = re.compile(
        r"^\s*(function|(?:mutable\s+)?struct|if|for|while|begin|let|try|quote|macro|module)\b"
    )

    # end як "закриття блоку":
    # - дозволяємо: "end" або "...; end" або "... end" (в т.ч. "struct X end")
    # - забороняємо: якщо перед end стоїть ':' (range/indexing типу j:end)
    block_end_re = re.compile(r"(?<!:)\bend\b")

    STOPWORDS = {
        "if", "for", "while", "begin", "let",
        "try", "catch", "finally", "end", "do"
    }

    structs, functions = [], []
    seen_structs, seen_funcs = set(), set()

    depth = 0

    for raw in code.splitlines():
        # грубо прибираємо коментарі
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        opens = 1 if block_open_re.match(line) else 0

        # рахуємо "end" лише як закриття блоку, ігноруючи j:end
        # (ще додатково: якщо line містить ':' перед end, воно не зменшить depth)
        ends = len(block_end_re.findall(line))

        # збираємо тільки top-level
        if depth == 0:
            m = struct_re.match(line)
            if m:
                name = m.group(1)
                if name not in seen_structs:
                    seen_structs.add(name)
                    structs.append(name)

            m = block_func_re.match(line)
            if m:
                name = m.group(1)
                if name not in STOPWORDS and name not in seen_funcs:
                    seen_funcs.add(name)
                    functions.append(name)

            m = oneliner_func_re.match(line)
            if m:
                name = m.group(1)
                if name not in STOPWORDS and name not in seen_funcs:
                    seen_funcs.add(name)
                    functions.append(name)

        depth = max(0, depth + opens - ends)

    return structs, functions


def extract_algorithm_number_from_caption(caption):
    return f"{caption.split(" ")[0]} {caption.split(" ")[1]}"


def extract_chapter_from_algorithm_caption(caption):
    algorithm_number = caption.split(" ")[1]
    return algorithm_number.split(".")[0]

def get_algorithms_with_chapter(algorithms, chapter_number):
    chapter_algorithms = []

    for algorithm in algorithms:
        if extract_chapter_from_algorithm_caption(algorithm["caption"]) == chapter_number:
            chapter_algorithms.append(algorithm)
    return chapter_algorithms

def find_related_definitions(algorithm_number, algorithms):
    related = []
    for algorithm in algorithms:
        if algorithm["name"] == algorithm_number:
            continue
        for item, used_list in algorithm["functions"].items():
            if algorithm_number in used_list:
                related.append((item, algorithm["name"]))
    return related

def find_related_definitions_for_chapter(chapter_algorithms, all_algorithms):
    related = {}
    for algorithm in chapter_algorithms:
        alg_number = algorithm["name"]
        related[alg_number] = find_related_definitions(alg_number, all_algorithms)
    return related


julia_code = extract_algorithms(extract_algorithms_and_examples("dm.pdf"))

funcs = {}
for algorithm in julia_code:
    algorithm["name"] = extract_algorithm_number_from_caption(algorithm["caption"])
    print(algorithm["name"])
    structs, functions = extract_entities_from_algorithm(algorithm["text"])
    # used_structs, used_funcs = extract_used_entities(algorithm["text"])
    print("Structs:", structs)
    print("Functions:", functions)
    algorithm["structs"] = {struct: [] for struct in structs}
    algorithm["functions"] = {func: [] for func in functions}
    for f in functions:
        if f not in funcs:
            funcs[f] = 0
        funcs[f] += 1
    # print("used_structs:", used_structs)
    # print("used_funcs:", used_funcs)
    print("-" * 40)


called_funcs = {}
for algorithm in julia_code:
    print(algorithm["name"])
    for struct_name, used_list in algorithm["structs"].items():
        for second_algorithm in julia_code:
            if second_algorithm is algorithm:
                continue
            struct_as_typing = f"::{struct_name}"
            called_structure = f"{struct_name}("
            if struct_as_typing in second_algorithm["text"] or called_structure in second_algorithm["text"]:
                used_list.append(second_algorithm["name"])

    for function_name, used_list in algorithm["functions"].items():
        for second_algorithm in julia_code:
            if second_algorithm is algorithm:
                continue
            function_as_definition = f"function {function_name}("
            function_as_short_definition_pattern = rf'\b{re.escape(function_name)}\s*\([^)]*\)\s*='
            if f"{function_name}(" in second_algorithm["text"] and not (function_as_definition in second_algorithm["text"] or re.search(function_as_short_definition_pattern, second_algorithm["text"])):
                used_list.append(second_algorithm["name"])

                if function_name not in called_funcs:
                    called_funcs[function_name] = 0
                called_funcs[function_name] += 1

    print("Structs:", algorithm["structs"])
    print("Functions:", algorithm["functions"], "\n", "-" * 40, "\n\n\n")



for f_name, f_count in funcs.items():
    if f_count > 1:
        print(f"{f_name}: {f_count}         called {called_funcs.get(f_name, 0)} times")

julia_chapter_code = get_algorithms_with_chapter(julia_code, "6")
print(find_related_definitions_for_chapter(julia_chapter_code, julia_code))
python_chapter_code = process("https://github.com/griffinbholt/decisionmaking-code-py/blob/main/src/ch06.py", None)

# print(
#     translated_prompt.format(
#         "\n".join(f"{chapter['caption']} \n\n {chapter['text']} \n\n" for chapter in julia_chapter_code),
#         python_chapter_code,
#     )
# )
