# Store Code Schema

## Purpose

`services/rag-service/src/scripts/store_code_schema.py` parses translated Python algorithm and example JSON files, extracts a structured code schema (classes, methods, and top-level functions), and stores it into three dedicated Weaviate collections. It also enriches existing algorithm and example chunks in the unified collection with cross-references pointing to the code entities they use.

---

## Weaviate Collections

Three new collections are created alongside the existing `unified_collection`:

| Collection      | Contents                              |
|-----------------|---------------------------------------|
| `CodeClass`     | Python class definitions              |
| `CodeMethod`    | Python method definitions             |
| `CodeFunction`  | Python top-level function definitions |

### Collection Properties

All three collections share the following base properties:

| Property    | Type   | Description                                           |
|-------------|--------|-------------------------------------------------------|
| `schema_id` | TEXT   | Stable identifier (`cls:Name`, `mth:A.b`, `fn:name`) |
| `name`      | TEXT   | Short (unqualified) name                              |
| `code`      | TEXT   | Source code of the entity                             |

`CodeMethod` additionally stores:

| Property         | Type | Description                   |
|------------------|------|-------------------------------|
| `qualified_name` | TEXT | Fully qualified `Class.method` |

---

## Cross-References

### `CodeMethod`

| Reference             | Target collection   | Description                                      |
|-----------------------|---------------------|--------------------------------------------------|
| `class_ref`           | `CodeClass`         | The class this method belongs to                 |
| `initialized_classes` | `CodeClass`         | Classes instantiated inside the method body      |
| `referenced_methods`  | `CodeMethod`        | Methods called inside the method body            |
| `referenced_functions`| `CodeFunction`      | Functions called inside the method body          |

### `CodeFunction`

| Reference             | Target collection   | Description                                      |
|-----------------------|---------------------|--------------------------------------------------|
| `initialized_classes` | `CodeClass`         | Classes instantiated inside the function body    |
| `referenced_methods`  | `CodeMethod`        | Methods called inside the function body          |
| `referenced_functions`| `CodeFunction`      | Functions called inside the function body        |

### `unified_collection` — algorithm chunks

| Reference              | Target collection   | Description                                      |
|------------------------|---------------------|--------------------------------------------------|
| `referenced_classes`   | `CodeClass`         | Classes used in the algorithm                    |
| `referenced_methods`   | `CodeMethod`        | Methods used in the algorithm                    |
| `referenced_functions` | `CodeFunction`      | Functions used in the algorithm                  |

### `unified_collection` — example chunks

| Reference              | Target collection   | Description                                      |
|------------------------|---------------------|--------------------------------------------------|
| `referenced_classes`   | `CodeClass`         | Classes used in the example                      |
| `referenced_methods`   | `CodeMethod`        | Methods used in the example                      |
| `referenced_functions` | `CodeFunction`      | Functions used in the example                    |


---

## How It Works

### High-Level Flow

```
translated_algorithms.json
translated_examples.json
          │
          ▼
  build_code_schema()           ← CodeAnalyzer + dependency graph
          │
          ├─► Insert CodeClass objects
          ├─► Insert CodeMethod objects
          ├─► Insert CodeFunction objects
          │         │
          │         └─► Add cross-references between code entities
          │
          ├─► extract_code_refs()  (for each algorithm)
          │         │
          │         └─► Add referenced_classes / referenced_methods / referenced_functions
          │             references on algorithm chunks in unified_collection
          │
          └─► extract_code_refs()  (for each example)
                    │
                    └─► Add referenced_classes / referenced_methods / referenced_functions
                        references on example chunks in unified_collection
```

### Step-by-Step

1. **Load input JSON** — reads `translated_algorithms.json` (required) and `translated_examples.json` (optional) from disk.
2. **Build code schema** — calls `build_code_schema()` which uses `CodeAnalyzer` to parse all Python code fragments via the AST, then builds a dependency graph linking callers to the classes/methods/functions they use.
3. **Set up collections** — creates `CodeClass`, `CodeMethod`, and `CodeFunction` in Weaviate in two phases to avoid circular-reference errors:
   - **Phase 1**: create each collection with its own direct references only.
   - **Phase 2**: add cross-collection references (`initialized_classes`, `referenced_methods`, `referenced_functions`) once all collections exist.
4. **Insert classes** — batches all class records into `CodeClass`.
5. **Insert methods** — batches all method records into `CodeMethod`, resolves `class_ref` and all cross-references.
6. **Insert functions** — batches all function records into `CodeFunction` and resolves cross-references.
7. **Add algorithm → code references** — for each algorithm, `extract_code_refs()` scans the algorithm's Python code for calls, resolves them against the known schema, and adds `referenced_classes`, `referenced_methods`, and `referenced_functions` reference properties on the matching algorithm chunk in `unified_collection`.
8. **Add example → code references** — for each example, `extract_code_refs()` scans the example text for Python code blocks and inline patterns, resolves calls against the known schema, and adds `referenced_classes`, `referenced_methods`, and `referenced_functions` reference properties on the matching example chunk in `unified_collection`.

### UUID Strategy

All UUIDs are **deterministic** and derived from a stable string identifier using `generate_uuid5`:

| Entity type              | UUID seed                        |
|--------------------------|----------------------------------|
| Class / Method / Function | `schema_id` (e.g. `cls:Foo`)    |
| Algorithm chunk          | `"{entity_id}:algorithm"`        |
| Example chunk            | `"{entity_id}:example"`          |

This makes re-runs idempotent — the same entity always maps to the same UUID.

---

## Supporting Modules

### `build_code_schema.py`

Builds the full code schema dictionary from a list of algorithm objects:

```python
schema = build_code_schema(algorithms)
# Returns:
# {
#   "classes":   [ClassRecord, ...],
#   "methods":   [MethodRecord, ...],
#   "functions": [FunctionRecord, ...],
# }
```

**ClassRecord** — contains the class header and `__init__` method (plus any leading docstring). The rest of the class body is omitted to keep the stored code concise.

**MethodRecord** — contains the full method source, its class reference (`cls:ClassName`), and lists of cross-references to other entities it uses:
- `initialized_classes` — classes instantiated within the method.
- `referenced_functions` — functions called within the method.
- `referenced_methods` — methods called within the method.

**FunctionRecord** — contains the full function source and the same cross-reference lists as MethodRecord.

`__init__` methods are intentionally skipped as stand-alone `MethodRecord` entries because their code is already embedded inside the `ClassRecord`.

### `code_analyzer.py`

An `ast.NodeVisitor` subclass that statically analyses Python code to collect:

- **Class definitions** (`CodeAnalyzer.classes`)
- **Method definitions** (`CodeAnalyzer.methods`)
- **Top-level function definitions** (`CodeAnalyzer.functions`)
- **Call sites** — records which function/method calls which other entities, tracking local variable types and `self` attribute types to resolve qualified calls such as `self.model.predict()`.

After visiting all fragments `build_graph()` produces a dependency graph `{caller: {target: kind}}` used by `build_code_schema` to populate the cross-reference lists.

External library calls (NumPy, PyTorch, Pandas, etc.) are filtered out via the `EXTERNAL_MODULES` allow-list.

### `extract_code_refs.py`

Extracts code entity references from a chunk's text. Works for both **algorithm chunks** (plain Python code) and **example chunks** (prose with embedded Python snippets). It operates in three passes:

1. Explicit ```` ```python … ``` ```` fenced code blocks.
2. Consecutive lines outside fenced blocks that parse as valid Python.
3. Inline `var = func(` patterns in prose sentences.

All discovered calls are resolved against the known schema (built from algorithms) and returned as:

```python
{
    "initialized_classes":  ["cls:X", ...],
    "referenced_functions": ["fn:foo", ...],
    "referenced_methods":   ["mth:Bar.baz", ...],
}
```

---

## Usage

```bash
python store_code_schema.py \
    --algorithms_file_path translated_algorithms.json \
    --examples_file_path translated_examples.json \
    [--recreate]
```

### Arguments

| Argument                    | Default                       | Description                                                     |
|-----------------------------|-------------------------------|-----------------------------------------------------------------|
| `--algorithms_file_path`    | `translated_algorithms.json`  | Path to the translated algorithms JSON file (required input)    |
| `--examples_file_path`      | `translated_examples.json`    | Path to the translated examples JSON file                       |
| `--recreate`                | *(flag, off by default)*      | Delete and recreate the three code collections before loading   |

> **Warning**: `--recreate` will **drop** `CodeClass`, `CodeMethod`, and `CodeFunction` before re-populating them. It does **not** affect `unified_collection`.

### Prerequisites

- A local Weaviate instance must be running and reachable (the script connects via `weaviate.connect_to_local()`).
- `unified_collection` must already exist and be populated with algorithm and example chunks before running this script, because `referenced_*` cross-references point into it.
- Both JSON files should be produced by the Julia code translation pipeline (see [Julia Code Translation](JULIA_CODE_TRANSLATION.md)).

---

## Schema ID Format

Every entity is assigned a stable `schema_id` that acts as a human-readable key and as the seed for its UUID:

| Entity type    | Format                 | Example              |
|----------------|------------------------|----------------------|
| Class          | `cls:<ClassName>`      | `cls:BeliefMDP`      |
| Method         | `mth:<Class>.<method>` | `mth:BeliefMDP.solve`|
| Function       | `fn:<function_name>`   | `fn:pomdp_solve`     |

---

## Re-Idempotency

The script is safe to re-run without `--recreate`. Because UUIDs are deterministic:
- Objects that already exist in Weaviate will be silently overwritten by the batch insert.
- Missing references will be added; existing ones are unaffected.

Use `--recreate` only when the schema structure itself has changed (e.g., new properties or collections).
