---
name: plan
description: Step 1 of TDD. Define class/function signatures, Pydantic models, and technical strategy without implementation logic. Use when starting a new feature or refactoring an interface.
---

# Plan Skill (TDD Step 1)

This skill focuses exclusively on the structural definition of a new feature. You must not write any implementation logic (methods body must be `...` or `pass`).

## Workflow

1.  **Analyze Requirements**: Review the user request and existing codebase to identify necessary changes. **Skip this step and Step 2 if you are modifying an existing feature and the signature doesn't change.**
2.  **Define Interfaces**: Create class and function stubs.
3.  **Define Data Models**: Create Pydantic models or dataclasses for request/response payloads.
4.  **Strategy**: Provide a brief (max 5 lines) technical strategy for the implementation phase.

## Mandates

- **No Implementation**: Do not write the bodies of functions or methods.
- **Type Safety**: Include comprehensive type hints for all signatures.
- **Docstrings**: Include Google-style docstrings for public interfaces explaining the intent.
- **Surgical Design**: Ensure the new interface aligns with existing monorepo patterns (e.g., `packages/common/schemas`).

## Canonical Example

```python
class InventoryService:
    async def get_stock_level(self, sku: str) -> StockResponse:
        """Retrieves the current stock level for a specific SKU.

        Args:
            sku: The Stock Keeping Unit identifier.

        Returns:
            StockResponse containing current balance and status.
        """
        ...
```
