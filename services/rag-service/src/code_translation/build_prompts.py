import re
import sys
from typing import List, Optional, Iterable, Tuple

print("\n".join(sys.path))

from pdf_parsing.extract_algorithms_and_examples import extract_algorithms_and_examples, extract_algorithms

# def extract_entities_from_algorithm(code):
#     struct_pattern = re.compile(r'\b(?:mutable\s+)?struct\s+(\w+)')
#     func_pattern = re.compile(
#         r"""
#         ^\s*function\s+([A-Za-z_]\w*!?)     # full function
#         |^\s*([A-Za-z_]\w*!?)\s*\(          # short form fname(...) =
#         """, re.MULTILINE | re.VERBOSE
#     )
#
#     structs = []
#     functions = []
#
#     structs += struct_pattern.findall(code)
#
#     for f1, f2 in func_pattern.findall(code):
#         functions.append(f1 or f2)
#
#     return structs, functions

# def extract_entities_from_algorithm(code: str):
#     IDENT = r"[A-Za-z_\u0080-\uFFFF]\w*"
#     FUNC_NAME = rf"{IDENT}[!?]?"
#
#     # Визначення (однорядкові)
#     oneliner_func_re = re.compile(rf"^\s*({FUNC_NAME})\s*\([^=\n]*\)\s*=")
#
#     # Block function: function name(...)
#     block_func_re = re.compile(rf"^\s*function\s+({FUNC_NAME})\b")
#
#     # Structs
#     struct_re = re.compile(rf"^\s*(?:mutable\s+)?struct\s+({IDENT})\b")
#
#     # Блоки, які відкривають ... end (спрощено, але практично працює)
#     block_open_re = re.compile(
#         r"^\s*(function|(?:mutable\s+)?struct|if|for|while|begin|let|try|quote|macro|module)\b"
#     )
#     block_end_re = re.compile(r"^\s*end\b")
#
#     STOPWORDS = {
#         "if", "for", "while", "begin", "let",
#         "try", "catch", "finally", "end", "do"
#     }
#
#     structs = []
#     functions = []
#     seen_structs = set()
#     seen_funcs = set()
#
#     depth = 0
#
#     # Приберемо коментарі (дуже грубо, але ок для ваших фрагментів)
#     # Якщо у вас є строки з '#' всередині лапок — скажи, дам безпечніший варіант.
#     lines = code.splitlines()
#
#     for raw in lines:
#         line = raw.split("#", 1)[0].rstrip()
#         if not line.strip():
#             continue
#
#         # 1) Якщо це "end" — зменшуємо depth ПЕРШЕ
#         # (бо "end" завершує блок, і наступні рядки можуть бути top-level)
#         if block_end_re.match(line):
#             depth = max(0, depth - 1)
#             continue
#
#         # 2) На depth==0 збираємо визначення
#         if depth == 0:
#             m = struct_re.match(line)
#             if m:
#                 name = m.group(1)
#                 if name not in seen_structs:
#                     seen_structs.add(name)
#                     structs.append(name)
#
#             m = block_func_re.match(line)
#             if m:
#                 name = m.group(1)
#                 if name not in STOPWORDS and name not in seen_funcs:
#                     seen_funcs.add(name)
#                     functions.append(name)
#
#             m = oneliner_func_re.match(line)
#             if m:
#                 name = m.group(1)
#                 if name not in STOPWORDS and name not in seen_funcs:
#                     seen_funcs.add(name)
#                     functions.append(name)
#
#         # 3) Якщо рядок відкриває блок — збільшуємо depth ПІСЛЯ обробки
#         if block_open_re.match(line):
#             depth += 1
#
#     return structs, functions

import re

# def extract_entities_from_algorithm(code: str):
#     IDENT = r"[A-Za-z_\u0080-\uFFFF]\w*"
#     FUNC_NAME = rf"{IDENT}[!?]?"
#
#     oneliner_func_re = re.compile(rf"^\s*({FUNC_NAME})\s*\([^=\n]*\)\s*=")
#     block_func_re     = re.compile(rf"^\s*function\s+({FUNC_NAME})\b")
#     struct_re         = re.compile(rf"^\s*(?:mutable\s+)?struct\s+({IDENT})\b")
#
#     # які конструкції відкривають блок, що закривається end
#     block_open_re = re.compile(
#         r"^\s*(function|(?:mutable\s+)?struct|if|for|while|begin|let|try|quote|macro|module)\b"
#     )
#     end_token_re = re.compile(r"\bend\b")
#
#     STOPWORDS = {
#         "if", "for", "while", "begin", "let",
#         "try", "catch", "finally", "end", "do"
#     }
#
#     structs, functions = [], []
#     seen_structs, seen_funcs = set(), set()
#
#     depth = 0
#
#     for raw in code.splitlines():
#         # грубо прибираємо коментарі
#         line = raw.split("#", 1)[0].rstrip()
#         if not line.strip():
#             continue
#
#         opens = 1 if block_open_re.match(line) else 0
#         ends = len(end_token_re.findall(line))
#
#         # збираємо тільки на top-level
#         if depth == 0:
#             m = struct_re.match(line)
#             if m:
#                 name = m.group(1)
#                 if name not in seen_structs:
#                     seen_structs.add(name)
#                     structs.append(name)
#
#             m = block_func_re.match(line)
#             if m:
#                 name = m.group(1)
#                 if name not in STOPWORDS and name not in seen_funcs:
#                     seen_funcs.add(name)
#                     functions.append(name)
#
#             m = oneliner_func_re.match(line)
#             if m:
#                 name = m.group(1)
#                 if name not in STOPWORDS and name not in seen_funcs:
#                     seen_funcs.add(name)
#                     functions.append(name)
#
#         # оновлюємо depth з урахуванням end у цьому ж рядку
#         depth = max(0, depth + opens - ends)
#
#     return structs, functions

def extract_used_entities_from_algorithm(
    code: str,
    defined_structs: Optional[Iterable[str]] = None,
    defined_functions: Optional[Iterable[str]] = None,
) -> Tuple[List[str], List[str]]:
    """
    Повертає (used_structs, used_functions) — що ВИКОРИСТОВУЄТЬСЯ у коді:
      - used_functions: виклики функцій foo(...)
      - used_structs: типи/структури в ::Type, Foo{T}, Type(...) (конструктор), або як тип у сигнатурах

    Якщо передати defined_structs/defined_functions, то:
      - ці імена не будуть повертатися як used (за замовчуванням),
      - і точніше класифікуються конструктори типів.
    """

    defined_structs = set(defined_structs or [])
    defined_functions = set(defined_functions or [])

    IDENT = r"[A-Za-z_\u0080-\uFFFF]\w*"
    # дозволимо ! і ? в кінці та dotted names типу Base.show
    NAME = rf"(?:{IDENT}\.)*{IDENT}[!?]?"

    STOPWORDS = {
        "if", "for", "while", "begin", "let", "try", "catch", "finally", "end", "do",
        "function", "struct", "mutable", "module", "macro", "quote", "return"
    }

    def strip_strings(s: str) -> str:
        out = []
        i, n = 0, len(s)
        in_str = None  # "'" або '"'
        while i < n:
            ch = s[i]
            if in_str:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                i += 1
                continue
            else:
                if ch in ("'", '"'):
                    in_str = ch
                    i += 1
                    continue
                out.append(ch)
                i += 1
        return "".join(out)

    # --- 1) Підготуємо чистий текст (без строк/коментарів) ---
    cleaned_lines = []
    for raw in code.splitlines():
        s = strip_strings(raw)
        s = s.split("#", 1)[0]
        cleaned_lines.append(s)
    cleaned = "\n".join(cleaned_lines)

    # --- 2) Знайдемо всі ІМЕНА, які є ВИЗНАЧЕННЯМИ функцій, щоб виключити їх з "used_calls" ---
    # block: function name(...)
    def_block_re = re.compile(rf"(?m)^\s*function\s+({NAME})\b")
    # one-liner def: name(args) = ...
    def_oneliner_re = re.compile(rf"(?m)^\s*({NAME})\s*\([^=\n]*\)\s*=")

    defined_here = set(def_block_re.findall(cleaned)) | set(def_oneliner_re.findall(cleaned))

    # --- 3) ВИКЛИКИ функцій: name(...)
    # беремо всі name( , але відсікаємо визначення та ключові слова
    call_re = re.compile(rf"(?m)(?<!function\s)\b({NAME})\s*\(")

    used_functions: List[str] = []
    used_structs: List[str] = []
    seen_f, seen_s = set(), set()

    def add_unique(lst, seen, x):
        if x not in seen:
            seen.add(x)
            lst.append(x)

    # helper: чи схоже на "тип/структуру"
    def looks_like_type(name: str) -> bool:
        base = name.split(".")[-1]
        return (base in defined_structs) or (base[:1].isupper())

    for m in call_re.finditer(cleaned):
        name = m.group(1)
        base = name.split(".")[-1]

        if base in STOPWORDS:
            continue
        # відсікаємо визначення
        if base in defined_here or name in defined_here:
            continue

        # якщо це схоже на конструктор типу — рахуємо як struct, інакше як function
        if looks_like_type(name):
            add_unique(used_structs, seen_s, base)
        else:
            # не викидаємо dotted: Base.show -> "show" чи "Base.show"?
            # ти просив "назви" — зазвичай зручно повертати повне dotted ім'я.
            add_unique(used_functions, seen_f, name)

    # --- 4) ВИКОРИСТАННЯ ТИПІВ через :: та Foo{T} ---
    # 4a) все після :: ... витягуємо ідентифікатори
    ann_re = re.compile(r"::\s*([^\n=;,)]+)")
    for ann in ann_re.findall(cleaned):
        # витягнемо всі слова-ідентифікатори з цієї частини
        for t in re.findall(rf"{IDENT}", ann):
            if t in STOPWORDS:
                continue
            # типи з анотацій — в used_structs
            add_unique(used_structs, seen_s, t)

    # 4b) параметрики Foo{Bar,Baz} (витягуємо Foo і внутрішні)
    param_re = re.compile(rf"\b({IDENT})\s*\{{([^}}]+)\}}")
    for outer, inner in param_re.findall(cleaned):
        if outer not in STOPWORDS:
            add_unique(used_structs, seen_s, outer)
        for t in re.findall(rf"{IDENT}", inner):
            if t not in STOPWORDS:
                add_unique(used_structs, seen_s, t)

    # --- 5) За бажанням: прибрати з used те, що ви самі визначили (якщо хочеш) ---
    # Я роблю це за замовчуванням, бо ти просив "юзаються", а визначення — це не "use".
    used_structs = [s for s in used_structs if s not in defined_structs]
    used_functions = [f for f in used_functions if f.split(".")[-1] not in defined_functions]

    return used_structs, used_functions


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


def extract_used_entities(code: str) -> Tuple[List[str], List[str]]:
    IDENT = r"[A-Za-z_\u0080-\uFFFF]\w*"
    NAME  = rf"(?:{IDENT}\.)*{IDENT}[!?]?"  # дозволяє Base.show / normalize! / foo?

    STOPWORDS = {
        "if","for","while","begin","let","try","catch","finally","end","do",
        "function","struct","mutable","module","macro","quote","return"
    }

    def strip_strings(s: str) -> str:
        out, i, n = [], 0, len(s)
        in_str = None
        while i < n:
            ch = s[i]
            if in_str:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                i += 1
                continue
            if ch in ("'", '"'):
                in_str = ch
                i += 1
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    # прибрати строки і коментарі
    cleaned_lines = []
    for raw in code.splitlines():
        s = strip_strings(raw)
        s = s.split("#", 1)[0]
        cleaned_lines.append(s)
    cleaned = "\n".join(cleaned_lines)

    used_funcs, used_structs = [], []
    seen_f, seen_s = set(), set()

    def add(lst, seen, x):
        if x and x not in seen:
            seen.add(x)
            lst.append(x)

    # 1) Витягуємо виклики name(...)
    call_re = re.compile(rf"\b({NAME})\s*\(")

    # але виключаємо визначення:
    def_block_re    = re.compile(rf"(?m)^\s*function\s+({NAME})\b")
    def_oneliner_re = re.compile(rf"(?m)^\s*({NAME})\s*\([^=\n]*\)\s*=")
    defined = set(def_block_re.findall(cleaned)) | set(def_oneliner_re.findall(cleaned))

    for m in call_re.finditer(cleaned):
        name = m.group(1)
        base = name.split(".")[-1]
        if base in STOPWORDS:
            continue
        # не рахувати самі визначення
        if name in defined or base in defined:
            continue

        # Якщо ім'я з великої — вважаємо конструктором (struct), інакше — функція
        if base[:1].isupper():
            add(used_structs, seen_s, base)
        else:
            add(used_funcs, seen_f, name)

    # 2) Типи в анотаціях ::Type
    ann_re = re.compile(r"::\s*([^\n=;,)]+)")
    for ann in ann_re.findall(cleaned):
        for t in re.findall(rf"{IDENT}", ann):
            if t not in STOPWORDS:
                add(used_structs, seen_s, t)

    # 3) Параметричні типи Foo{Bar,Baz}
    param_re = re.compile(rf"\b({IDENT})\s*\{{([^}}]+)\}}")
    for outer, inner in param_re.findall(cleaned):
        if outer not in STOPWORDS:
            add(used_structs, seen_s, outer)
        for t in re.findall(rf"{IDENT}", inner):
            if t not in STOPWORDS:
                add(used_structs, seen_s, t)

    return used_structs, used_funcs


def extract_algorithm_number_from_caption(caption):
    return f"{caption.split(" ")[0]} {caption.split(" ")[1]}"


def extract_chapter_from_algorithm_caption(caption):
    algorithm_number = caption.split(" ")[1]
    return int(algorithm_number.split(".")[0])

def get_algorithms_with_chapter(algorithms, chapter_number):
    chapter_algorithms = []

    for algorithm in algorithms:
        if extract_chapter_from_algorithm_caption(algorithm["caption"]) == chapter_number:
            algorithms.append(algorithm)
    return chapter_algorithms


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
