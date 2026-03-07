import ast
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from common.logging import get_logger
from pipeline.code_processing.python_code_processing.constants import EXTERNAL_MODULES

logger = get_logger(__name__)

# Edge kind constants
KIND_CLASS_INIT = "class_init"
KIND_FUNCTION = "function"
KIND_METHOD = "method"
KIND_UNKNOWN = "unknown"


# ------------------------------------------------------------------ #
# CodeAnalyzer
# ------------------------------------------------------------------ #


class CodeAnalyzer(ast.NodeVisitor):
    """Collect definitions and call sites from Python ASTs.

    After visiting one or more ASTs, the public attributes hold:
    - ``classes / functions / methods`` — all found definitions
    - ``calls`` — per-function list of ``(call_name, argc, kind)``
    - ``fragment_idx`` — maps definition name → source fragment index
    """

    def __init__(self) -> None:
        self.classes: dict[str, ast.ClassDef] = {}
        self.functions: dict[str, ast.FunctionDef] = {}
        self.methods: dict[str, ast.FunctionDef] = {}
        self.var_types: dict[str, str] = {}
        self.calls: defaultdict[str, list[tuple[str, int, str]]] = defaultdict(list)

        self.current_function: str | None = None
        self.current_class: str | None = None

        self._local_vars: defaultdict[str, dict[str, str]] = defaultdict(dict)
        self._self_attr_types: defaultdict[str, dict[str, str]] = defaultdict(dict)
        self._local_definitions: defaultdict[str, set[str]] = defaultdict(set)

        self.fragment_idx: dict[str, object] = {}
        self.current_fragment_idx: object = 0
        self._class_init_fragment: dict[str, object] = {}

    # ------------------------------------------------------------------ #
    # Definition visitors
    # ------------------------------------------------------------------ #

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Register a class, preferring the definition that contains ``__init__``."""
        has_init = any(isinstance(n, ast.FunctionDef) and n.name == "__init__" for n in node.body)
        if node.name not in self.classes or has_init:
            self.classes[node.name] = node
            self.fragment_idx[node.name] = self.current_fragment_idx

        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node)

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Register a function/method definition and recurse into its body."""
        if not getattr(node, "name", None):
            return

        name = self._register_definition(node)
        self._track_init_fragment(node)
        self._register_nested_def(node)

        prev_function = self.current_function
        self.current_function = name
        self._collect_param_types(node, name)
        self.generic_visit(node)
        self.current_function = prev_function

    def _register_definition(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Add the node to ``functions`` or ``methods`` and return its qualified name."""
        name = f"{self.current_class}.{node.name}" if self.current_class else node.name

        if self.current_function is None:
            if self.current_class:
                self.methods[name] = cast(ast.FunctionDef, node)
            else:
                self.functions[name] = cast(ast.FunctionDef, node)
            self.fragment_idx[name] = self.current_fragment_idx

        return name

    def _track_init_fragment(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Record which fragment contains ``__init__`` for the current class."""
        if self.current_class and node.name == "__init__":
            self._class_init_fragment[self.current_class] = self.current_fragment_idx

    def _register_nested_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Track locally-defined names so they are excluded from call resolution."""
        if self.current_function is not None:
            self._local_definitions[self.current_function].add(node.name)

    def _collect_param_types(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, func_name: str
    ) -> None:
        """Populate ``_local_vars`` with parameter types inferred from annotations."""
        args = getattr(node, "args", None)
        if not args:
            return
        arg_list = getattr(args, "args", [])
        if arg_list and arg_list[0].arg == "self" and self.current_class:
            self._local_vars[func_name]["self"] = self.current_class
        for arg in arg_list:
            if getattr(arg, "annotation", None) and isinstance(arg.arg, str):
                typ = ast.unparse(arg.annotation)
                self._local_vars[func_name][arg.arg] = typ

    # ------------------------------------------------------------------ #
    # Variable type tracking
    # ------------------------------------------------------------------ #

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Record annotated variable types at local or module scope."""
        if isinstance(node.target, ast.Name):
            typ = ast.unparse(node.annotation)
            if self.current_function:
                self._local_vars[self.current_function][node.target.id] = typ
            else:
                self.var_types[node.target.id] = typ
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.current_function and len(node.targets) == 1:
            self._infer_assignment(node.targets[0], node.value)
        self.generic_visit(node)

    def _infer_assignment(self, target: ast.expr, value: ast.expr) -> None:
        """Infer and store the type of a local variable or ``self`` attribute from its RHS."""
        typ = self._infer_type_from_expr(value)
        if not typ:
            return
        if isinstance(target, ast.Name):
            self._local_vars[self.current_function][target.id] = typ  # type: ignore[index]
        elif (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and self.current_class
        ):
            self._self_attr_types[self.current_class][target.attr] = typ

    def _infer_type_from_expr(self, node: ast.expr) -> str | None:
        """Return the class name when *node* is a constructor call, else ``None``."""
        if not isinstance(node, ast.Call):
            return None
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id not in EXTERNAL_MODULES
        ):
            return func.attr
        return None

    # ------------------------------------------------------------------ #
    # Call tracking
    # ------------------------------------------------------------------ #

    def visit_Call(self, node: ast.Call) -> None:
        if self.current_function:
            name, kind = self._resolve_call(node.func)
            if name:
                self.calls[self.current_function].append((name, len(node.args), kind))
        self.generic_visit(node)

    def _resolve_call(self, node: ast.expr) -> tuple[str | None, str]:
        """Return ``(call_name, kind)`` for a call target node."""
        if isinstance(node, ast.Name):
            return node.id, "bare"
        if isinstance(node, ast.Attribute):
            return self._resolve_attribute_call(node)
        return None, KIND_UNKNOWN

    def _resolve_attribute_call(self, node: ast.Attribute) -> tuple[str | None, str]:
        """Resolve a dotted call expression to ``(qualified_name_or_method, KIND_METHOD)``.

        Handles three shapes:

        - ``obj.method()``       — qualifies with the inferred type of ``obj`` when known.
        - ``self.attr.method()`` — qualifies with the stored type of the ``self`` attribute.
        - ``a.b.c.method()``     — returns bare ``method`` name (root checked against external
                                                                                        modules).

        Returns ``(None, KIND_UNKNOWN)`` when the receiver is an external module.
        """
        method = node.attr

        if isinstance(node.value, ast.Name):
            obj = node.value.id
            if obj in EXTERNAL_MODULES:
                return None, KIND_UNKNOWN
            typ = self._resolve_var_type(obj)
            return (f"{typ}.{method}" if typ else method), KIND_METHOD

        if isinstance(node.value, ast.Attribute):
            inner = node.value
            if (
                isinstance(inner.value, ast.Name)
                and inner.value.id == "self"
                and self.current_class
            ):
                attr_type = self._self_attr_types.get(self.current_class, {}).get(inner.attr)
                return (f"{attr_type}.{method}" if attr_type else method), KIND_METHOD
            root = self._get_chain_root(inner)
            if root in EXTERNAL_MODULES:
                return None, KIND_UNKNOWN
            return method, KIND_METHOD

        return None, KIND_UNKNOWN

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _resolve_var_type(self, var_name: str) -> str | None:
        """Look up the type of *var_name*, checking local scope before module scope."""
        if self.current_function:
            local = self._local_vars.get(self.current_function, {})
            if var_name in local:
                return local[var_name]
        return self.var_types.get(var_name)

    def _get_chain_root(self, node: ast.expr) -> str | None:
        """Return the leftmost name in a dotted chain (``a.b.c`` → ``"a"``), or ``None``."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return self._get_chain_root(node.value)
        return None


# ------------------------------------------------------------------ #
# Dependency graph
# ------------------------------------------------------------------ #


def _build_short_name_index(definitions: set[str]) -> defaultdict[str, list[str]]:
    """Map unqualified names to all fully-qualified definitions that share that short name."""
    index: defaultdict[str, list[str]] = defaultdict(list)
    for d in definitions:
        index[d.split(".")[-1]].append(d)
    return index


def _resolve_bare(
    caller: str,
    short: str,
    analyzer: CodeAnalyzer,
    index: defaultdict[str, list[str]],
) -> list[tuple[str, str]]:
    """Resolve an unqualified call name to ``(target, kind)`` pairs.

    Resolution priority: locally-defined names are skipped, then classes,
    then functions, then methods (only when unambiguous).
    """
    if short in analyzer._local_definitions.get(caller, set()):
        return []

    candidates = index.get(short, [])
    classes = [c for c in candidates if c in analyzer.classes]
    functions = [c for c in candidates if c in analyzer.functions]
    methods = [c for c in candidates if c in analyzer.methods]

    if classes:
        return [(c, KIND_CLASS_INIT) for c in classes]
    if functions:
        return [(f, KIND_FUNCTION) for f in functions]
    if len(methods) == 1:
        return [(methods[0], KIND_METHOD)]
    return []


def _resolve_qualified(
    caller: str,
    call_name: str,
    definitions: set[str],
    index: defaultdict[str, list[str]],
) -> list[tuple[str, str]]:
    """Resolve a ``Class.method`` call to ``(target, KIND_METHOD)`` pairs.

    Tries exact match first, then candidates filtered by class prefix,
    then falls back to any single unambiguous match on the method name.
    """
    cls_name, method_name = call_name.split(".", 1)
    if call_name in definitions:
        return [(call_name, KIND_METHOD)]
    by_class = [d for d in index.get(method_name, []) if d.split(".")[0] == cls_name]
    if by_class:
        return [(c, KIND_METHOD) for c in by_class]
    all_cands = index.get(method_name, [])
    if len(all_cands) == 1:
        return [(all_cands[0], KIND_METHOD)]
    return []


def build_graph(analyzer: CodeAnalyzer) -> dict[str, dict[str, str]]:
    """Build a dependency graph ``{caller: {target: kind}}`` from collected calls."""
    graph: defaultdict[str, dict[str, str]] = defaultdict(dict)

    definitions: set[str] = set(analyzer.functions) | set(analyzer.methods) | set(analyzer.classes)
    index = _build_short_name_index(definitions)

    for caller, calls in analyzer.calls.items():
        for call_name, _argc, raw_kind in calls:
            parts = call_name.split(".")

            if len(parts) == 2:
                for target, kind in _resolve_qualified(caller, call_name, definitions, index):
                    if graph[caller].get(target) in (None, KIND_UNKNOWN):
                        graph[caller][target] = kind

            elif raw_kind == "bare":
                for target, kind in _resolve_bare(caller, parts[-1], analyzer, index):
                    if graph[caller].get(target) in (None, KIND_UNKNOWN):
                        graph[caller][target] = kind

            elif raw_kind == KIND_METHOD:
                candidates = [c for c in index.get(parts[-1], []) if c in analyzer.methods]
                if len(candidates) == 1:
                    target = candidates[0]
                    if graph[caller].get(target) in (None, KIND_UNKNOWN):
                        graph[caller][target] = KIND_METHOD

            else:
                short = parts[-1]
                if short in definitions and graph[caller].get(short) in (None, KIND_UNKNOWN):
                    graph[caller][short] = raw_kind

    return graph


# ------------------------------------------------------------------ #
# Public entry point
# ------------------------------------------------------------------ #


def analyze_fragments(
    fragments: Sequence[object],
) -> tuple[CodeAnalyzer, dict[str, dict[str, str]]]:
    """Analyze a sequence of code fragments and return ``(analyzer, graph)``.

    Each item may be a plain Python source string, or a dict with at least
    a ``"code"`` key and an optional ``"algorithm_number"`` used as the
    fragment index.
    """
    analyzer = CodeAnalyzer()

    for idx, item in enumerate(fragments):
        try:
            if isinstance(item, dict):
                code = item.get("code", "")
                analyzer.current_fragment_idx = item.get("algorithm_number", idx)
            else:
                code = str(item)
                analyzer.current_fragment_idx = idx

            analyzer.visit(ast.parse(code))
        except SyntaxError:
            pass

    return analyzer, build_graph(analyzer)


# ------------------------------------------------------------------ #
# Example
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    with Path("./translated_algorithms.json").open() as f:
        data = json.load(f)

    analyzer, graph = analyze_fragments(data)

    logger.info("Definitions:")
    for name in analyzer.functions:
        logger.info("  function: %s", name)
    for name in analyzer.methods:
        logger.info("  method: %s", name)
    for name in analyzer.classes:
        logger.info("  class: %s", name)

    logger.info("Calls (raw):")
    for caller, call_list in analyzer.calls.items():
        logger.info("  %s -> %s", caller, call_list)

    logger.info("Dependency graph:")
    for caller, edges in graph.items():
        by_kind: defaultdict[str, list[str]] = defaultdict(list)
        for target, kind in edges.items():
            by_kind[kind].append(target)
        parts_str = [
            f"{k}: {sorted(by_kind[k])}"
            for k in (KIND_CLASS_INIT, KIND_FUNCTION, KIND_METHOD, KIND_UNKNOWN)
            if k in by_kind
        ]
        logger.info("  %s -> { %s }", caller, "|".join(parts_str))
