import ast


class ClassMethodStripper(ast.NodeTransformer):
    def visit_ClassDef(self, node: ast.ClassDef):
        new_body = []

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                new_func = ast.FunctionDef(
                    name=item.name,
                    args=item.args,
                    body=self._extract_top_level_returns(item),
                    decorator_list=item.decorator_list,
                    returns=item.returns,
                    type_comment=item.type_comment,
                )
                new_body.append(new_func)

        node.body = new_body
        return node

    def _extract_top_level_returns(self, func_node):
        returns = [
            stmt for stmt in func_node.body
            if isinstance(stmt, ast.Return)
        ]

        if returns:
            return returns

        return [ast.Expr(value=ast.Constant(value=Ellipsis))]


def strip_to_signatures(code: str) -> str:
    if not code:
        return code
    tree = ast.parse(code)
    tree = ClassMethodStripper().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)
