# Julia Code Translation

> **Important**: Running `translate.py` incurs LLM costs. Avoid re-running it unless you need new translations. Use `build_prompts.py` if you only need the prompts.

## Purpose
`services/rag-service/src/pipeline/julia_code_translation/translate.py` translates Julia algorithms and examples from the Decision Making PDF into idiomatic Python using an LLM. It also updates descriptions for already-translated chapters and stores all generated translations in JSON for later use.

## How It Works
The pipeline reads algorithm/example blocks from the PDF, builds prompts based on `PromptConfig`, saves those prompts to disk, submits them to the LLM, and appends the JSON response payloads to the output files.

High-level flow:
1. Parse `dm.pdf` blocks with `open_block_processor`.
2. Build prompts via `PromptBuilder` using:
   - Book blocks (Julia code and captions).
   - Previously translated algorithms from `translated_algorithms.json`.
   - Translated Python chapter code fetched from GitHub when available.
3. Save each prompt to `prompts/` for audit and replay.
4. Send prompts to Bedrock and parse JSON payloads from the response.
5. Append new items to `translated_algorithms.json` and `translated_examples.json`.

### Prompt Types
There are three prompt types, each aligned to a specific configuration list in `PromptConfig`:

1. **Algorithm translation prompt**
   Used for chapters listed in `PromptConfig.translated_chapters`.
   For these chapters the authors already provide translated Python code on GitHub, so the prompt:
   - Includes the original Julia code from the PDF.
   - Includes the translated Python code fetched from GitHub.
   - Asks the LLM to update the code descriptions accordingly.

2. **Full chapter translation prompt**
   Used for chapters *not* in `PromptConfig.translated_chapters` (i.e., `PromptConfig.chapters_to_translate`).
   In this case, the LLM is asked to translate the entire chapter and update the descriptions. The prompt includes:
   - The Julia code for the current chapter.
   - An example translation drawn from previously translated algorithms.
   - The struct/function definitions from older chapters that are referenced in the current chapter.

3. **Example translation prompt**
   Used for examples listed in `PromptConfig.example_with_code_numbers`.
   It includes the structs and functions used in the example (from earlier chapters), and asks the LLM to translate the example along with its description.

## Configuration
`services/rag-service/src/pipeline/julia_code_translation/constants.py` centralizes the prompt configuration:
- `PromptConfig.translated_chapters`: chapters with existing Python translations on GitHub.
- `PromptConfig.chapters_to_translate`: chapters that require full Julia-to-Python translation.
- `PromptConfig.example_with_code_numbers`: examples to translate.
- `PromptConfig.prompts_dir`: default prompts output directory.

## Data Flow Details
The prompt builder and processors add useful context and normalize data before prompting:
- `BookCodeProcessor` extracts top-level Julia structs/functions per block and builds a usage index so prompts can include only relevant prior definitions.
- `TranslatedAlgorithmStore` loads prior translations from `translated_algorithms.json` and injects them as examples or dependencies.
- `GitHubCodeFetcher` pulls translated Python chapter code and recursively includes dependent `chXX.py` symbols to keep the context complete.
- For example prompts, `signature_stripper.strip_to_signatures` reduces class methods to signatures only to keep the context concise.

## How to Run
From the repo root:

```bash
uv run services/rag-service/src/pipeline/julia_code_translation/translate.py \
  --pdf-path dm.pdf \
  --pdf-jsons-dir pdf_jsons \
  --prompts-dir prompts \
  --translated-algorithms-json translated_algorithms.json
```

### Notes:
1. The script uses AWS Bedrock. Make sure `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set.
Run these scripts to load them from AWS CLI configuration:

**On Linux/macOS:**
```bash
. scripts/aws-env.sh
```

**On Windows (PowerShell):**
```powershell
. .\scripts\aws-env.ps1
```
2. Defaults if you omit flags:
  - `--pdf-path dm.pdf`
  - `--pdf-jsons-dir pdf_jsons`
  - `--prompts-dir prompts`
  - `--translated-algorithms-json translated_algorithms.json`

## Results
Running `translate.py` will produce or update:
- `translated_algorithms.json`: a JSON list of translated algorithm blocks and updated descriptions.
- `translated_examples.json`: a JSON list of translated example blocks.
- Prompt files under the `prompts/` directory:
  - `prompts/update_description/`
  - `prompts/translate_algorithms/`
  - `prompts/translate_examples/`

## Prompt-Only Mode
Prompts are always saved when you run `translate.py`. If you only want to generate prompts without sending them to the LLM, run:

```bash
uv run services/rag-service/src/pipeline/julia_code_translation/build_prompts.py \
  --pdf-path dm.pdf \
  --pdf-jsons-dir pdf_jsons \
  --prompts-dir prompts \
  --translated-algorithms-json translated_algorithms.json
```

This writes the same prompt files to `prompts/` without making any model calls.
