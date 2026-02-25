# Julia Code Translation

## Purpose
`services/rag-service/src/pipeline/julia_code_translation/translate.py` translates Julia algorithms and examples from the Decision Making PDF into idiomatic Python using an LLM. It also updates descriptions for already-translated chapters and stores all generated translations in JSON for later use.

## How to Run
From the repo root:

```bash
python services/rag-service/src/pipeline/julia_code_translation/translate.py \
  --pdf-path dm.pdf \
  --prompts-dir prompts \
  --translated-algorithms-json translated_algorithms.json
```

Notes:
- The script uses AWS Bedrock. Make sure `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set.
- Defaults if you omit flags:
  - `--pdf-path dm.pdf`
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
python services/rag-service/src/pipeline/julia_code_translation/build_prompts.py \
  --pdf-path dm.pdf \
  --prompts-dir prompts \
  --translated-algorithms-json translated_algorithms.json
```

This writes the same prompt files to `prompts/` without making any model calls.
