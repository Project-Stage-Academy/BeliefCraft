import json
from pathlib import Path
from typing import Iterable

from code_translation.prompts import translated_prompt, translate_prompt, example_prompt
from code_translation.python_github_code import process

from pdf_parsing.extract_algorithms_and_examples import extract_algorithms_and_examples, extract_algorithms, BlockType
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

def find_related_definitions(algorithm_number, blocks):
    related = []
    for algorithm in blocks:
        if algorithm["name"] == algorithm_number:
            continue

        for item, used_list in algorithm["functions"].items():
            if algorithm_number in used_list:
                related.append((item, algorithm["name"]))

        for item, used_list in algorithm["structs"].items():
            if algorithm_number in used_list:
                related.append((item, algorithm["name"]))
    return related

def find_related_definitions_for_chapter(chapter_algorithms, all_algorithms):
    related = {}
    for algorithm in chapter_algorithms:
        alg_number = algorithm["name"]
        related[alg_number] = find_related_definitions(alg_number, all_algorithms)
    return related


def extract_algorithms_structs_and_functions(algorithms):
    for algorithm in algorithms:
        algorithm["name"] = extract_algorithm_number_from_caption(algorithm["caption"])
        print(algorithm["name"])
        structs, functions = extract_entities_from_algorithm(algorithm["text"])
        # used_structs, used_funcs = extract_used_entities(algorithm["text"])
        print("Structs:", structs)
        print("Functions:", functions)
        algorithm["structs"] = {struct: [] for struct in structs}
        algorithm["functions"] = {func: [] for func in functions}
        # print("used_structs:", used_structs)
        # print("used_funcs:", used_funcs)
        print("-" * 40)


def extract_entities_usage(blocks, blocks_type: BlockType=BlockType.ALGORITHM):
    for block in blocks:
        print(block["name"])
        if block["block_type"] != blocks_type.value:
            continue

        for struct_name, used_list in block["structs"].items():
            for second_algorithm in blocks:
                if second_algorithm is block:
                    continue
                struct_as_typing = f"::{struct_name}"
                called_structure = f"{struct_name}("
                if struct_as_typing in second_algorithm["text"] or called_structure in second_algorithm["text"]:
                    used_list.append(second_algorithm["name"])

        for function_name, used_list in block["functions"].items():
            for second_algorithm in blocks:
                if second_algorithm is block:
                    continue
                function_as_definition = f"function {function_name}("
                function_as_short_definition_pattern = rf'\b{re.escape(function_name)}\s*\([^)]*\)\s*='
                if f"{function_name}(" in second_algorithm["text"] and not (function_as_definition in second_algorithm["text"] or re.search(function_as_short_definition_pattern, second_algorithm["text"])):
                    used_list.append(second_algorithm["name"])

        print("Structs:", block["structs"])
        print("Functions:", block["functions"], "\n", "-" * 40, "\n\n\n")

# julia_code = extract_algorithms(extract_algorithms_and_examples("dm.pdf"))
# extract_algorithms_structs_and_functions(julia_code)
# extract_entities_usage(julia_code)
#
# julia_chapter_code = get_algorithms_with_chapter(julia_code, "6")
# print(find_related_definitions_for_chapter(julia_chapter_code, julia_code))
# python_chapter_code = process("06", None)

# print(
#     translated_prompt.format(
#         "\n".join(f"{chapter['caption']} \n\n {chapter['text']} \n\n" for chapter in julia_chapter_code),
#         python_chapter_code,
#     )
# )

def get_translated_algorithm(algorithm_number):
    json_path = Path("translated_algorithms.json")
    with json_path.open("r", encoding="utf-8") as fh:
        json_data = json.load(fh)

    for item in json_data:
        if item["algorithm_number"] == algorithm_number:
            return item["code"]
    return None


def extract_block_chapter(block_number):
    number = block_number.split(" ")[1]
    chapter = number.split(".")[0]
    if chapter in ["A", "B", "C", "D", "E", "F", "G", "H"]:
        return 28 + ord(chapter) - ord("A")
    return int(chapter)


def get_translated_algorithms(algorithm_numbers: Iterable[str]):
    return [
        {
            "algorithm_number": algorithm_number,
            "translated": get_translated_algorithm(algorithm_number)
        } for algorithm_number in algorithm_numbers
    ]


def filter_out_older_chapters(algorithm_numbers, current_chapter):
    try:
        current_chapter = int(current_chapter)
    except ValueError:
        current_chapter = 28 + ord(current_chapter) - ord("A")
    filtered = []
    for algorithm_number in algorithm_numbers:
        chapter = extract_block_chapter(algorithm_number)
        if chapter <= current_chapter:
            filtered.append(algorithm_number)
    return filtered

def build_translated_algorithm_code_prompt(chapter, julia_code):
    julia_chapter_code = get_algorithms_with_chapter(julia_code, str(int(chapter)))
    extract_algorithms_structs_and_functions(julia_chapter_code)
    # print(find_related_definitions_for_chapter(julia_chapter_code, julia_code))
    python_chapter_code = process(chapter, None)

    return translated_prompt.format(
        "\n".join(f"{chapter['caption']} \n\n {chapter['text']} \n\n" for chapter in julia_chapter_code),
        python_chapter_code,
    )

def build_translate_algorithm_prompt(chapter, julia_code):
    extract_algorithms_structs_and_functions(julia_code)
    extract_entities_usage(julia_code)

    try:
        chapter_number = str(int(chapter))
    except ValueError:
        chapter_number = chapter

    julia_chapter_code = get_algorithms_with_chapter(julia_code, chapter_number)
    related_entities = find_related_definitions_for_chapter(julia_chapter_code, julia_code)

    related_entities_by_algorithms = [value for value in related_entities.values()]
    related_algorithms = set()
    for entities in related_entities_by_algorithms:
        for entity in entities:
            related_algorithms.add(entity[1])
    filtered_related_algorithms = filter_out_older_chapters(related_algorithms, chapter)
    translated_algorithms = get_translated_algorithms(filtered_related_algorithms)

    return translate_prompt.format(
        "\n".join(f"{chapter['caption']} \n\n {chapter['text']} \n\n" for chapter in julia_chapter_code),
        "\n".join(f"{translated['algorithm_number']} \n\n {translated['translated']} \n\n" for translated in translated_algorithms),
    )


def build_translate_example_prompt(example_number, blocks):
    extract_algorithms_structs_and_functions(blocks)
    extract_entities_usage(blocks)

    example = None
    for block in blocks:
        if block["name"] == example_number:
            example = block
            break

    if not example:
        raise ValueError(f"Example with number {example_number} not found")

    related_entities = find_related_definitions(example_number, blocks)
    related_algorithms = set()
    for entity in related_entities:
        related_algorithms.add(entity[1])

    filtered_related_algorithms = filter_out_older_chapters(related_algorithms, extract_block_chapter(example_number))
    translated_examples = get_translated_algorithms(filtered_related_algorithms)


    return example_prompt.format(
        f"{example['caption']} \n\n {example['text']} \n\n",
        "\n".join(f"{translated['translated']} \n\n" for translated in translated_examples),
    )


if __name__ == "__main__":
    example_with_code_numbers = [
        "Example 2.3.",
        "Example 2.5.",
        "Example 4.1.",
        "Example 4.2.",
        "Example 9.10.",
        "Example 10.1.",
        "Example 11.2.",
        "Example 15.2.",
        "Example 17.2.",
        "Example 17.3.",
        "Example 17.4.",
        "Example 21.1.",
        "Example 22.1.",
        "Example 22.3.",
        "Example 22.6.",
    ]

    translated_chapters = [
        "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "14", "15", "16", "17", "20", "24",
    ]

    chapters_to_translate = ["13", "18", "19", "21", "22", "23", "25", "26", "27", "E"]

    blocks = extract_algorithms_and_examples("dm.pdf")

    julia_code = extract_algorithms(blocks)

    for chapter in translated_chapters:
        prompt = build_translated_algorithm_code_prompt(chapter, julia_code)
        Path("prompts").mkdir(parents=True, exist_ok=True)
        with open(f"prompts/chapter_{chapter}_code_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    for chapter in chapters_to_translate:
        prompt = build_translate_algorithm_prompt(chapter, julia_code)
        with open(f"prompts/chapter_{chapter}_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    for example in example_with_code_numbers:
        prompt = build_translate_example_prompt(example, blocks)
        with open(f"prompts/{example.replace(' ', '_')}_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
