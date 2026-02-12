# Contributing

## Setup

1. Install uv.
2. Create the environment and install deps:
   - `uv sync`

## Code quality (required)

We use:

- pre-commit runner to do checks on commit.
- Black: code formatter, rewrites Python code into a consistent style.
- Ruff: fast linter and auto-fixer.
- isort: sorts imports into a consistent order.
- mypy: checks your code's type hints without running it.

### Install git hooks

- `uv run pre-commit install`

### Run checks manually

- `uv run pre-commit run --all-files`

## CI

GitHub Actions runs the same checks. PRs must be green to merge.
