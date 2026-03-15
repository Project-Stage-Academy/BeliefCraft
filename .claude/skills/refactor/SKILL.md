---
name: refactor
description: Step 4 of TDD. Improve code readability and performance while maintaining green tests. Focus on O(n) complexity and idiomatic patterns. Use after tests pass.
---

# Refactor Skill (TDD Step 4)

This skill focuses on refining the passing implementation into its most readable, maintainable, and efficient form. All changes must be verified by the existing test suite.

## Workflow

1.  **Analyze Complexity**: Identify O(n^2) or higher complexity and optimize for performance.
2.  **Idiomatic Patterns**: Apply Pythonic patterns (list comprehensions, context managers, structural pattern matching).
3.  **Clean Code Check**: Ensure functions are small (<= 20 lines) and have a single responsibility.
4.  **Verification**: Re-run the test suite and linters after each refactoring step.

## Mandates

- **Tests Must Remain Green**: Refactoring only applies to internal logic; behavior must not change.
- **Shortest Clear Path**: Choose the most concise implementation that meets all readability and standard requirements.
- **Early Returns**: Prefer early returns to reduce nesting.
- **Explicit Imports**: Avoid wildcard imports or ambiguous names.
- **Ruff Optimization**: Ensure the code is fully compliant with `ruff` and `isort`.

## Common Mistakes

- **Refactoring without Tests**: Never attempt to refactor if you don't have passing tests.
- **Behavioral Changes**: If you need to change behavior, return to Step 1 (Plan).
- **Over-abstraction**: Avoid complex patterns that make the code harder to read than a simple implementation.

## Canonical Example

```python
# Before
async def fetch_all(self, items):
    results = []
    for item in items:
        if item.is_valid:
            results.append(item.data)
    return results

# After
async def fetch_all(self, items: list[Item]) -> list[ItemData]:
    """Retrieves data for all valid items.

    Args:
        items: A list of Item objects to process.
    Returns:
        A list of ItemData for all valid items.
    """
    return [item.data for item in items if item.is_valid]
```

## Python Coding Standards

### General

- Use **type hints** on every function signature and variable where the type is not obvious.
- **Coding Style:** PEP 8 enforced by `ruff`. Max line length: 100.
- Write **docstrings** on every public function and class using the Google-style format:
  ```python
  def my_function(arg: str) -> int:
      """Short one-line description of what the function does.

        Optional longer description if needed, explaining the logic and any non-obvious details
        and how function does what it does.

      Args:
          arg: What this argument represents.

      Returns:
          What the function returns.

      Raises:
          SomeError: When and why it is raised.
      """
  ```
- No inline comments unless they answer **why** the code is written this way (not what it does). Readable names make the "what" obvious.
- Prefer **descriptive variable names** over comments: `filtered_books` not `result`.
- Follow all **Clean Code** principles: SOLID, DRY, small functions, clear names.
- Use `StrEnum` for enumerations that are also used as string values.
- Use **dataclasses** for domain model objects, not `TypedDict` or plain dicts.
- Care about O(n) complexity of your code, especially in loops and recursive functions.
- Make code secure, modular and testable.
- Of all possible implementations that meet all other criteria mentioned in this instructions, choose the shortest, most concise and the most readable.

### Clean code guide

#### Naming

- Names must reveal intent, not implementation.
- If a name needs a comment, rename it.
- One word per concept across the codebase (get ≠ fetch).
- Avoid abbreviations, encodings, prefixes, suffixes.
- Never use noise words: `data`, `info`, `manager`, `handler`.
- Prefer clarity over brevity.
- Name booleans this way: `is_`, `has_`, `can_`

#### Functions

- Functions must be small (≤ 20 lines).
- A function must do **exactly one thing**.
- One abstraction level per function.
- Avoid deep nesting; extract functions instead.
- A function is either:
  - a **command** (changes state)
  - or a **query** (returns data)
- Never both.

#### Control Flow

- Prefer early returns.
- Avoid `else` after `return`.
- Large `if/elif/match` blocks indicate missing polymorphism.
- `break` / `continue` allowed only in small scopes.

#### Errors & Exceptions

- Use exceptions, never error codes.
- Never return `None` to signal failure.
- Exceptions must include:
  - operation
  - reason
  - relevant context
- Error handling must never obscure main logic.

#### Comments

- Prefer expressive code over comments.
- Comments do NOT fix bad code.
- Allowed:
  - intent
  - warnings
  - TODO (temporary only)
- Forbidden:
  - redundant comments
  - commented-out code
  - historical logs
  - obvious explanations
- If a comment explains logic → refactor the code.

#### Tests

- Tests are production code.
- Tests must be readable.
- One concept per test.
- Tests must be:
  - Fast
  - Independent
  - Repeatable
  - Self-validating
  - Written before or with production code

#### Python-Specific Rules

- Prefer composition over inheritance.
- Use `with` for all resource management.
- Avoid global mutable state.
- No magic numbers; name all constants.
- Explicit imports only.
- Avoid metaprogramming unless strictly required.

#### Other Rules

- Hard to name → redesign.
- Growing function → split.
- Comment explaining logic → refactor.
- Type checks → missing polymorphism.
- Many files touched per change → abstraction failure.
