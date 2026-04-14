import ast
from _ast import Return, stmt
from typing import Any

from common.logging import get_logger

logger = get_logger(__name__)


class ClassMethodStripper(ast.NodeTransformer):
    """Strip class methods to signature-only bodies for prompt context."""

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        new_body: list[stmt] = []

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                func_kwargs: dict[str, Any] = {
                    "name": item.name,
                    "args": item.args,
                    "body": self._extract_top_level_returns(item),
                    "decorator_list": item.decorator_list,
                    "returns": item.returns,
                    "type_comment": item.type_comment,
                }

                if hasattr(item, "type_params"):
                    func_kwargs["type_params"] = item.type_params

                new_func = ast.FunctionDef(**func_kwargs)
                new_body.append(new_func)
            else:
                new_body.append(item)

        node.body = new_body
        return node

    def _extract_top_level_returns(self, func_node: ast.FunctionDef) -> list[stmt]:
        returns: list[stmt] = [stmt for stmt in func_node.body if isinstance(stmt, Return)]

        if returns:
            return returns

        return [ast.Expr(value=ast.Constant(value=Ellipsis))]


def strip_to_signatures(code: str) -> str:
    """Return a version of code with class method bodies reduced to signatures only."""
    if not code:
        return code
    tree = ast.parse(code)
    tree = ClassMethodStripper().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)
