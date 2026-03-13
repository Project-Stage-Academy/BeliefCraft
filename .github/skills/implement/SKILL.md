---
name: implement
description: Step 3 of TDD. Write the minimal production code necessary to pass all existing tests. Focus on clean code, type safety, and removal of comments. Use when failing tests exist.
---

# Implement Skill (TDD Step 3)

This skill focuses on writing the minimal, correct production code required to satisfy the established test suite. You must prioritize clarity, type safety, and adherence to established project patterns.

## Workflow

1.  **Iterative Passes**: Write code for each function stub until the relevant tests pass.
2.  **Surgical Changes**: Only modify the specific files and functions defined in the planning phase.
3.  **Validation**: Run `pytest` and `mypy` after each change to verify correctness.
4.  **Error Handling**: Implement specific exceptions as defined in the test suite.

## Mandates

- **Minimal Code**: Do not add extra "just-in-case" logic that isn't required by the tests.
- **No Inline Comments**: Write self-documenting code with descriptive names. Only use comments to explain the "why," not the "what."
- **Clean Code Principles**: Adhere to DRY, SOLID, and small functions (<= 20 lines).
- **Type Safety**: Use type hints for all variables and signatures where types aren't obvious.
- **Ruff Compliance**: Strictly follow the 100-character line limit.

## Common Mistakes

- **Writing Inline Comments**: If you feel the need for a comment to explain the logic, rename the variable or extract the function instead.
- **Ignoring Warnings**: Ensure the implementation doesn't trigger new linting or type-checking warnings.
- **Complexity**: Keep functions focused on a single responsibility.

## Canonical Example

```python
async def get_stock_level(self, sku: str) -> StockResponse:
    stock_item = await self._repository.fetch_by_sku(sku)
    if stock_item is None:
        raise StockNotFoundError(sku=sku)

    return StockResponse(
        balance=stock_item.balance,
        status=stock_item.status
    )
```
