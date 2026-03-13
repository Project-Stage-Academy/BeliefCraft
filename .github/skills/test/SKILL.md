---
name: test
description: Step 2 of TDD. Write exhaustive tests before implementation. Focus on happy paths, edge cases, and error states using Arrange-Act-Assert. Use when interface stubs are defined.
---

# Test Skill (TDD Step 2)

This skill focuses on writing high-fidelity tests to drive the implementation. You must write the tests after stubs are created but before any production logic is implemented.

## Workflow

1.  **Fixtures**: Define any `pytest` fixtures needed for shared setup (e.g., database sessions, mocked clients).
2.  **Happy Path**: Write tests for the primary expected behavior.
3.  **Edge Cases**: Identify and write tests for potential failures (e.g., missing data, invalid formats, empty lists).
4.  **Error States**: Verify that the correct exceptions are raised for expected error conditions.

## Mandates

- **Arrange-Act-Assert**: Always structure tests with clear separation between these phases using blank lines.
- **No Phase Labels**: Do **NOT** use `# Arrange`, `# Act`, or `# Assert` comments.
- **Descriptive Names**: Test names must read as complete sentences describing the expected behavior (e.g., `test_returns_404_when_sku_is_not_found`).
- **One Concept per Test**: Each test should verify exactly one logical assertion.
- **Parametrization**: Use `@pytest.mark.parametrize` for repetitive test cases with different inputs/outputs.
- Use `@pytest.fixture()` for shared setup.
- Use `@pytest.mark.parametrize` as much as possible to avoid test duplication.
- When needed, add comments for each set of params in parametrize list to explain what case they cover.
- **Do not duplicate tests across layers.** Test each concern at exactly one level
- Come up with creative edge cases that will break future code.

## Common Mistakes

- **Commented Phase Labels**: Do not label sections; use empty lines instead.
- **Leaking State**: Ensure each test is independent and clean up any persistent state using fixtures.
- **Ignoring Warnings**: Ensure all tests run with `filterwarnings = ["error"]` locally if configured.

## Canonical Example

```python
@pytest.mark.asyncio
async def test_get_stock_level_returns_current_balance(service: InventoryService) -> None:
    sku = "SKU-123"
    expected_balance = 50

    response = await service.get_stock_level(sku)

    assert response.balance == expected_balance
    assert response.status == StockStatus.AVAILABLE
```
