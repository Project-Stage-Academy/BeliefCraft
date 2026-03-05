import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import cast

# --------------------------------
# Known external modules to ignore
# --------------------------------

EXTERNAL_MODULES = {
    "np",
    "numpy",
    "scipy",
    "sklearn",
    "torch",
    "tf",
    "tensorflow",
    "pd",
    "pandas",
    "plt",
    "matplotlib",
    "sns",
    "seaborn",
    "os",
    "sys",
    "re",
    "math",
    "random",
    "itertools",
    "functools",
    "collections",
    "typing",
    "abc",
    "copy",
    "time",
    "datetime",
    "json",
    "csv",
    "io",
    "pathlib",
    "logging",
    "warnings",
    "linalg",
    "sparse",
    "stats",
    "special",
    "optimize",
    "signal",
}


class CodeAnalyzer(ast.NodeVisitor):

    def __init__(self) -> None:
        # definitions
        self.classes: dict[str, ast.ClassDef] = {}
        self.functions: dict[str, ast.FunctionDef] = {}
        self.methods: dict[str, ast.FunctionDef] = {}

        # global variable types (from annotations)
        self.var_types: dict[str, str] = {}

        # usages: {caller: [(name, argc, kind)]}
        # kind: "class_init" | "function" | "method" | "unknown"
        self.calls: defaultdict[str, list[tuple[str, int, str]]] = defaultdict(list)

        self.current_function: str | None = None
        self.current_class: str | None = None

        # local variable types per function: {func_name: {var: type}}
        self._local_vars: defaultdict[str, dict[str, str]] = defaultdict(dict)

        # self.attr types per function: {func_name: {attr: type}}
        # Example: self.solver = LinearProgramFormulation()
        # becomes {"solver": "LinearProgramFormulation"}
        self._self_attr_types: defaultdict[str, dict[str, str]] = defaultdict(dict)

        # locally defined names per function (nested defs or local vars
        # assigned to non-class callables). Used to shadow bare
        # unqualified calls — if "solve" is defined locally, don't
        # match methods with the same name.
        self._local_definitions: defaultdict[str, set[str]] = defaultdict(set)

        # fragment index tracking: which fragment each definition came from
        # {name: fragment_idx}  — set by analyze_fragments before each visit()
        self.fragment_idx: dict[str, int] = {}
        self.current_fragment_idx: int = 0

        # For classes that appear in multiple fragments (body split across files),
        # track the fragment that contains __init__ separately
        self._class_init_fragment: dict[str, int] = {}  # class_name -> fragment_idx of __init__

    # -----------------------------
    # Definitions
    # -----------------------------

    # def visit_ClassDef(self, node):
    #     self.classes[node.name] = node
    #     self.fragment_idx[node.name] = self.current_fragment_idx
    #
    #     prev = self.current_class
    #     self.current_class = node.name
    #     self.generic_visit(node)
    #     self.current_class = prev
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Only overwrite an existing class definition if the new one has __init__
        # and the existing one doesn't — preserves the "primary" definition
        has_init = any(isinstance(n, ast.FunctionDef) and n.name == "__init__" for n in node.body)
        if node.name not in self.classes or has_init:
            self.classes[node.name] = node
            self.fragment_idx[node.name] = self.current_fragment_idx

        prev = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # Handle async functions the same as regular functions
        self._handle_function(node)

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Shared handling for both FunctionDef and AsyncFunctionDef."""
        if getattr(node, "name", None) is None:
            return

        if self.current_class:
            name = f"{self.current_class}.{node.name}"
            self.methods[name] = cast(
                ast.FunctionDef, node
            )  # stored value is a FunctionDef for simplicity
        else:
            name = node.name
            self.functions[name] = cast(ast.FunctionDef, node)

        self.fragment_idx[name] = self.current_fragment_idx

        # Track which fragment contains __init__ for this class
        if self.current_class and node.name == "__init__":
            self._class_init_fragment[self.current_class] = self.current_fragment_idx

        prev_function = self.current_function

        # If this is a nested function (defined inside another function),
        # register its name as a local definition in the parent scope
        # so bare calls to it are not matched against class methods
        if prev_function is not None:
            self._local_definitions[prev_function].add(node.name)

        self.current_function = name

        # Register self -> CurrentClass so self.method() resolves correctly
        if self.current_class and getattr(node, "args", None) and getattr(node.args, "args", None):
            first_arg = node.args.args[0].arg
            if first_arg == "self":
                self._local_vars[name]["self"] = self.current_class

        # collect parameter types from annotations
        for arg in node.args.args:
            if getattr(arg, "annotation", None) and isinstance(arg.arg, str):
                type_str = ast.unparse(cast(ast.AST, cast(object, arg.annotation)))
                self._local_vars[name][arg.arg] = type_str

        # Visit body
        self.generic_visit(node)

        self.current_function = prev_function

    # -----------------------------
    # Variable typing
    # -----------------------------

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Handle annotated assignments: x: SomeType = ..."""
        if isinstance(node.target, ast.Name):
            var = node.target.id
            # node.annotation is an expr, double-cast to satisfy type checker
            typ = ast.unparse(cast(ast.AST, cast(object, node.annotation)))
            if self.current_function:
                self._local_vars[self.current_function][var] = typ
            else:
                self.var_types[var] = typ
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """
        Handle plain assignments to infer local variable types.

        Patterns we track:
          x = SomeClass(...)           -> var x has type SomeClass
          self.attr = SomeClass(...)   -> self.attr has type SomeClass
                                         (for self.attr.method() calls)
          x, y = a, b                  -> skip (too ambiguous)
        """
        if not self.current_function:
            self.generic_visit(node)
            return

        if len(node.targets) == 1:
            target = node.targets[0]

            # Plain: x = SomeClass(...)
            if isinstance(target, ast.Name):
                var = target.id
                typ = self._infer_type_from_expr(node.value)
                if typ:
                    self._local_vars[self.current_function][var] = typ

            # Self attr: self.attr = SomeClass(...)
            elif (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and self.current_class
            ):
                attr = target.attr
                typ = self._infer_type_from_expr(node.value)
                if typ:
                    self._self_attr_types[self.current_class][attr] = typ

        self.generic_visit(node)

    def _infer_type_from_expr(self, node: ast.expr) -> str | None:
        """
        Try to infer the type name from an expression.
        Returns a type string or None.
        """
        # x = SomeClass(...)  or  x = some_func(...)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                return func.id
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                # e.g. x = module.SomeClass(...)
                obj = func.value.id
                # Only track if the object is NOT an external module
                if obj not in EXTERNAL_MODULES:
                    return func.attr
        return None

    # -----------------------------
    # Calls
    # -----------------------------

    def visit_Call(self, node: ast.Call) -> None:
        if not self.current_function:
            self.generic_visit(node)
            return

        name, kind = self._get_call_name_and_kind(node.func)
        args = len(node.args)

        if name:
            self.calls[self.current_function].append((name, args, kind))

        self.generic_visit(node)

    # -----------------------------
    # Helpers
    # -----------------------------

    def _resolve_var_type(self, var_name: str) -> str | None:
        """Resolve variable type: local scope first, then global."""
        if self.current_function:
            local = self._local_vars.get(self.current_function, {})
            if var_name in local:
                return local[var_name]
        return self.var_types.get(var_name)

    def _get_call_name_and_kind(self, node: ast.expr) -> tuple[str | None, str]:
        """
        Resolve the callable name AND classify the call kind:
          "class_init"  — calling a known class constructor: Assignment(...)
          "function"    — calling a known top-level function: assignments(...)
          "method"      — calling a method on an object: obj.method(), self.method()
          "unknown"     — can't determine

        Returns (resolved_name, kind).
        """
        # --- Bare name: foo() ---
        if isinstance(node, ast.Name):
            name = node.id
            # Defer kind resolution to build_graph where we know all definitions
            # Tag as "bare" and let build_graph classify
            return name, "bare"

        if isinstance(node, ast.Attribute):
            method = node.attr

            # obj.method() where obj is a simple Name
            if isinstance(node.value, ast.Name):
                obj = node.value.id

                if obj in EXTERNAL_MODULES:
                    return None, "unknown"

                typ = self._resolve_var_type(obj)
                if typ:
                    return f"{typ}.{method}", "method"

                # Unknown type — bare method name, can't resolve owner
                return method, "method"

            # self.attr.method() — two-level via self
            if isinstance(node.value, ast.Attribute):
                inner = node.value
                if (
                    isinstance(inner.value, ast.Name)
                    and inner.value.id == "self"
                    and self.current_class
                ):
                    attr = inner.attr
                    attr_type = self._self_attr_types.get(self.current_class, {}).get(attr)
                    if attr_type:
                        return f"{attr_type}.{method}", "method"
                    return method, "method"

                root = self._get_chain_root(cast(ast.expr, cast(object, node.value)))
                if root in EXTERNAL_MODULES:
                    return None, "unknown"
                return method, "method"

        return None, "unknown"

    # Keep old name as alias so nothing else breaks
    def _get_call_name(self, node: ast.expr) -> str | None:
        name, _ = self._get_call_name_and_kind(node)
        return name

    def _get_chain_root(self, node: ast.expr) -> str | None:
        """Walk an Attribute chain to find the root Name."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return self._get_chain_root(node.value)
        return None


# --------------------------------
# Build dependency graph
# --------------------------------

# Edge kinds
KIND_CLASS_INIT = "class_init"
KIND_FUNCTION = "function"
KIND_METHOD = "method"
KIND_UNKNOWN = "unknown"


def build_graph(analyzer: "CodeAnalyzer") -> dict[str, dict[str, str]]:
    """
    Returns graph: {caller: {target: kind}}
    where kind is one of: "class_init", "function", "method", "unknown"
    """
    graph: defaultdict[str, dict[str, str]] = defaultdict(dict)

    definitions: set[str] = set()
    definitions.update(analyzer.functions.keys())
    definitions.update(analyzer.methods.keys())
    definitions.update(analyzer.classes.keys())

    # Short-name index: "solve" -> ["NashEquilibrium.solve", ...]
    index: defaultdict[str, list[str]] = defaultdict(list)
    for d in definitions:
        short = d.split(".")[-1]
        index[short].append(d)

    def _add(caller: str, target: str, kind: str) -> None:
        # Don't overwrite a more specific kind with unknown
        existing = graph[caller].get(target)
        if existing is None or existing == KIND_UNKNOWN:
            graph[caller][target] = kind

    def _resolve_bare(caller: str, short: str) -> list[tuple[str, str]]:
        """
        Resolve a bare (unqualified) name to (target, kind) pairs.
        Priority: class > top-level function > single method
        """
        # Locally defined (nested def) — skip entirely
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
        # Multiple methods, no top-level match — ambiguous, skip
        return []

    for caller, calls in analyzer.calls.items():
        for call_name, _argc, raw_kind in calls:

            parts = call_name.split(".")

            if len(parts) == 2:
                # Qualified: "TypeName.method"
                cls_name, method_name = parts

                if call_name in definitions:
                    _add(caller, call_name, KIND_METHOD)
                    continue

                candidates = [d for d in index.get(method_name, []) if d.split(".")[0] == cls_name]
                if candidates:
                    for c in candidates:
                        _add(caller, c, KIND_METHOD)
                else:
                    all_cands = index.get(method_name, [])
                    if len(all_cands) == 1:
                        _add(caller, all_cands[0], KIND_METHOD)

            else:
                # Bare name — raw_kind is "bare", need to classify
                short = parts[-1]

                if raw_kind == "bare":
                    for target, kind in _resolve_bare(caller, short):
                        _add(caller, target, kind)
                elif raw_kind == "method":
                    # Unresolved bare method name (obj type unknown)
                    candidates = index.get(short, [])
                    methods = [c for c in candidates if c in analyzer.methods]
                    if len(methods) == 1:
                        _add(caller, methods[0], KIND_METHOD)
                    # else ambiguous — skip
                else:
                    if short in definitions:
                        _add(caller, short, raw_kind)

    return graph


# --------------------------------
# Run analysis
# --------------------------------


def analyze_fragments(fragments: list[str]) -> tuple["CodeAnalyzer", dict[str, dict[str, str]]]:
    analyzer = CodeAnalyzer()

    for idx, code in enumerate(fragments):
        try:
            tree = ast.parse(code)
            analyzer.current_fragment_idx = idx
            analyzer.visit(tree)
        except SyntaxError:
            pass

    graph = build_graph(analyzer)
    return analyzer, graph


# --------------------------------
# Example
# --------------------------------

if __name__ == "__main__":

    with Path("./translated_algorithms.json").open() as f:
        data = json.load(f)

    fragments = []
    for algo in data:
        fragments.append(algo["code"])

    analyzer, graph = analyze_fragments(fragments)

    print("Definitions:")
    for func_name in analyzer.functions:
        print(" function:", func_name)
    for method_name in analyzer.methods:
        print(" method:", method_name)
    for class_name in analyzer.classes:
        print(" class:", class_name)

    print("\nCalls (raw):")
    for caller_name, call_list in analyzer.calls.items():
        print(f"  {caller_name} -> {call_list}")

    print("\nDependency graph:")
    for caller_name, edges in graph.items():
        # edges is now {target: kind}
        by_kind = defaultdict(list)
        for target, kind in edges.items():
            by_kind[kind].append(target)
        parts_str = []
        for kind in ("class_init", "function", "method", "unknown"):
            if kind in by_kind:
                parts_str.append(f"{kind}: {sorted(by_kind[kind])}")
        print(f"  {caller_name} -> {{ {'|'.join(parts_str)} }}")
