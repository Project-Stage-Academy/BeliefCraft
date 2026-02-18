"""
fetch_github_deps.py

Fetches a Python file from GitHub and recursively collects all classes/functions
imported from chXX modules (transitively). Edit the CONFIG block below and run.
"""

# ==============================================================================
# CONFIG — edit these two values and run
# ==============================================================================

# ==============================================================================

import sys
import re
import ast
import urllib.request
from urllib.parse import urlparse
from pathlib import PurePosixPath
from typing import Optional


# ---------------------------------------------------------------------------
# GitHub URL helpers
# ---------------------------------------------------------------------------

def github_blob_to_raw(url: str) -> str:
    """Convert a GitHub blob URL to a raw content URL."""
    # https://github.com/user/repo/blob/branch/path/to/file.py
    # -> https://raw.githubusercontent.com/user/repo/branch/path/to/file.py
    url = url.rstrip("/")
    parsed = urlparse(url)
    parts = parsed.path.lstrip("/").split("/")
    # parts: [user, repo, "blob", branch, *file_path]
    if len(parts) < 5 or parts[2] != "blob":
        raise ValueError(f"Not a GitHub blob URL: {url}")
    user, repo, _, branch, *file_parts = parts
    raw_path = "/".join(file_parts)
    return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{raw_path}"


def make_ch_raw_url(base_raw_url: str, ch_module: str) -> str:
    """Given the raw URL of any file in the repo, build the raw URL for chXX.py."""
    # base_raw_url: https://raw.githubusercontent.com/user/repo/branch/src/chXX.py
    # ch_module:    ch07  (no .py)
    parts = base_raw_url.split("/")
    parts[-1] = ch_module + ".py"          # replace filename
    return "/".join(parts)


# ---------------------------------------------------------------------------
# Fetching source
# ---------------------------------------------------------------------------

def fetch_source(raw_url: str) -> str:
    """Download source code from a raw URL."""
    req = urllib.request.Request(raw_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def parse_chxx_imports(source: str) -> dict[str, list[str]]:
    """
    Return {module_name: [symbol, ...]} for all `from chXX import ...` lines.
    """
    result: dict[str, list[str]] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback: regex
        for m in re.finditer(r"from\s+(ch\d+)\s+import\s+(.+)", source):
            mod = m.group(1)
            names = [n.strip() for n in m.group(2).split(",")]
            result.setdefault(mod, []).extend(names)
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if re.fullmatch(r"ch\d+", mod):
                names = [alias.asname or alias.name for alias in node.names]
                result.setdefault(mod, []).extend(names)
    return result


def extract_node_source(source: str, node: ast.AST) -> str:
    """Extract source lines for an AST node (class or function)."""
    lines = source.splitlines(keepends=True)
    # ast gives 1-based line numbers
    start = node.lineno - 1
    end = node.end_lineno          # end_lineno is inclusive and 1-based; using it as the slice end is correct because slicing is end-exclusive
    return "".join(lines[start:end])


def find_symbol(source: str, name: str) -> Optional[str]:
    """
    Return the source text of the top-level class or function named `name`.
    Returns None if not found.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return extract_node_source(source, node)
        # Also handle module-level assignments (e.g. NamedTuple aliases)
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return extract_node_source(source, node)
    return None


def symbols_used_in_code(code: str, candidates: set[str]) -> set[str]:
    """Return which names from `candidates` appear in `code`."""
    used = set()
    for name in candidates:
        # Use word-boundary search to avoid false positives
        if re.search(r"\b" + re.escape(name) + r"\b", code):
            used.add(name)
    return used


# ---------------------------------------------------------------------------
# Core recursive logic
# ---------------------------------------------------------------------------

class Collector:
    def __init__(self, base_raw_url: str):
        self.base_raw_url = base_raw_url          # URL of the starting file
        self._source_cache: dict[str, str] = {}   # module -> source
        self._collected: dict[str, str] = {}       # "module.Symbol" -> code snippet
        self._visited_modules: set[str] = set()

    def get_source(self, module: str) -> Optional[str]:
        if module in self._source_cache:
            return self._source_cache[module]
        url = make_ch_raw_url(self.base_raw_url, module)
        try:
            src = fetch_source(url)
            self._source_cache[module] = src
            return src
        except Exception as e:
            print(f"  [WARNING] Could not fetch {module}: {e}", file=sys.stderr)
            return None

    def collect_symbols(self, module: str, symbols: list[str]):
        """
        For each symbol in `symbols` from `module`, extract its source and
        recursively collect any chXX symbols it needs.
        """
        src = self.get_source(module)
        if src is None:
            return

        # Parse what chXX imports are available in this module
        chxx_imports = parse_chxx_imports(src)   # {dep_module: [sym, ...]}
        # Flat map: symbol_name -> dep_module
        available_dep_symbols: dict[str, str] = {}
        for dep_mod, dep_syms in chxx_imports.items():
            for s in dep_syms:
                available_dep_symbols[s] = dep_mod

        for sym in symbols:
            key = f"{module}.{sym}"
            if key in self._collected:
                continue  # already done

            code = find_symbol(src, sym)
            if code is None:
                print(f"  [WARNING] Symbol '{sym}' not found in {module}", file=sys.stderr)
                continue

            self._collected[key] = code

            # Find which dep symbols are actually used inside this code
            used_dep_syms = symbols_used_in_code(code, set(available_dep_symbols.keys()))

            # Group by their source module and recurse
            deps_by_mod: dict[str, list[str]] = {}
            for dep_sym in used_dep_syms:
                dep_mod = available_dep_symbols[dep_sym]
                deps_by_mod.setdefault(dep_mod, []).append(dep_sym)

            for dep_mod, dep_syms in deps_by_mod.items():
                self.collect_symbols(dep_mod, dep_syms)

    def collect_full_file(self, module: str):
        """Collect the full source of a chXX module and recurse into its imports."""
        if module in self._visited_modules:
            return
        self._visited_modules.add(module)

        src = self.get_source(module)
        if src is None:
            return

        key = f"{module}.__full__"
        self._collected[key] = src

        # Recurse into all chXX imports of this file
        chxx_imports = parse_chxx_imports(src)
        for dep_mod, dep_syms in chxx_imports.items():
            self.collect_symbols(dep_mod, dep_syms)

    def build_result(self, main_source: str, requested_symbols: Optional[list[str]]) -> str:
        """
        Assemble the final string.
        Order: dependency symbols first (sorted by module number), then the main file / symbols.
        """
        sections = []

        # Separate collected items: full files vs individual symbols
        full_files = {k: v for k, v in self._collected.items() if k.endswith(".__full__")}
        sym_items  = {k: v for k, v in self._collected.items() if not k.endswith(".__full__")}

        # Output dependency symbols grouped by their module
        # We want a stable order: sort by module number ascending (ch07 before ch09, etc.)
        def mod_number(key):
            mod = key.split(".")[0]
            m = re.search(r"\d+", mod)
            return int(m.group()) if m else 0

        for key in sorted(sym_items.keys(), key=mod_number):
            mod, sym = key.split(".", 1)
            sections.append(f"# --- {mod}.py :: {sym} ---")
            sections.append(sym_items[key].rstrip())
            sections.append("")

        # Finally the main file / requested symbols
        if requested_symbols:
            main_module = PurePosixPath(urlparse(self.base_raw_url).path).stem
            for sym in requested_symbols:
                code = find_symbol(main_source, sym)
                if code:
                    sections.append(f"# --- {main_module}.py :: {sym} ---")
                    sections.append(code.rstrip())
                    sections.append("")
        else:
            sections.append("# --- main file ---")
            sections.append(main_source.rstrip())
            sections.append("")

        return "\n".join(sections)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def get_translated_python_code_from_github(
    chapter: str,
    requested_symbols: Optional[list[str]] = None,
    repo_url: str = "https://github.com/griffinbholt/decisionmaking-code-py",
) -> str:
    """
    Main function.

    chapter        – Chapter number as a string, e.g. "02" (no "ch" prefix)
    requested_symbols – optional list of specific symbols to extract;
                        if None/empty the full file is used
    repo_url       – GitHub repo base URL, e.g. "https://github.com/user/repo"

    Returns a single string with all the code.
    """
    raw_url = github_blob_to_raw(f"{repo_url}/blob/main/src/ch{chapter}.py")
    print(f"Fetching: {raw_url}", file=sys.stderr)
    main_source = fetch_source(raw_url)

    collector = Collector(raw_url)

    if requested_symbols:
        # Collect only the requested symbols and their transitive deps
        main_module = PurePosixPath(urlparse(raw_url).path).stem
        # First collect the requested symbols from the main module's chXX imports
        chxx_imports = parse_chxx_imports(main_source)
        # Also parse which chXX symbols requested_symbols themselves use
        collector._source_cache[main_module] = main_source
        collector.collect_symbols(main_module, requested_symbols)
        # Also check direct imports for the requested symbols
        for sym in requested_symbols:
            for dep_mod, dep_syms in chxx_imports.items():
                if sym in dep_syms:
                    collector.collect_symbols(dep_mod, [sym])
    else:
        # Full file mode: collect all chXX imports recursively
        chxx_imports = parse_chxx_imports(main_source)
        for dep_mod, dep_syms in chxx_imports.items():
            collector.collect_symbols(dep_mod, dep_syms)

    return collector.build_result(main_source, requested_symbols)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = get_translated_python_code_from_github("02", None)
