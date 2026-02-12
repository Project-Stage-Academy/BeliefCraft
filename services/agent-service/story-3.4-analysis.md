# Story 3.4 Analysis: Recommendation Generator & Response Formatting

## 📋 Overview
This story focuses on transforming the raw output from the ReAct Agent into a highly structured, machine-readable JSON response. This includes extracting mathematical formulas, validating and translating code snippets, and ensuring all claims are cited back to the "Algorithms for Decision Making" book.

## 🏗️ Components to Build

### 1. Data Models (`app/models/responses.py`)
- **`Citation`**: Links to RAG chunks (id, title, page, entity type).
- **`CodeSnippet`**: Python code with syntax validation and dependency tracking.
- **`Formula`**: LaTeX mathematical expressions with descriptions.
- **`Recommendation`**: Actionable steps with priority and rationale.
- **`AgentRecommendationResponse`**: The master schema for the API.

### 2. Specialized Extractors (`app/services/extractors/`)
- **`FormulaExtractor`**: Uses regex to pull LaTeX from markdown and RAG metadata.
- **`CodeExtractor`**: 
    - Extracts blocks from markdown.
    - **Critical**: Translates Julia code from the book into Python using LLM.
    - Validates syntax using `ast.parse`.
- **`CitationExtractor`**: Collects and deduplicates references from tool results.

### 3. Orchestrator (`app/services/recommendation_generator.py`)
- Uses an LLM to "post-process" the agent's final answer into the structured JSON schema.
- Coordinates the specialized extractors to enrich the response.
- Handles fallback logic if the agent fails or returns incomplete data.

## 🔗 Dependencies & Readiness

| Dependency | Status | Impact on 3.4 |
|------------|--------|---------------|
| **Story 3.1 (Setup)** | ⚠️ Missing | Need `app/` structure and FastAPI routes. |
| **Story 3.2 (ReAct Loop)** | ⚠️ Missing | Need `AgentState` definition and `LLMService`. |
| **Story 3.3 (Tools)** | ⚠️ Missing | Need RAG tool output schemas for citations. |
| **Common Logging** | ✅ Ready | Can be integrated immediately for tracing. |

## 🛠️ Implementation Plan

### Phase 1: Foundation (Current)
- [ ] Define Pydantic schemas based on the requirements.
- [ ] Create mock `AgentState` for testing extractors.

### Phase 2: Extraction Logic
- [ ] Implement `FormulaExtractor` with LaTeX regex patterns.
- [ ] Implement `CitationExtractor` to pull metadata from RAG chunks.
- [ ] Implement `CodeExtractor` with `ast` validation and Julia -> Python LLM prompt.

### Phase 3: Integration
- [ ] Implement `RecommendationGenerator` to tie everything together.
- [ ] Update `/api/v1/agent/analyze` endpoint to return the new schema.
- [ ] Add unit tests for each extractor with edge cases.

## ⚠️ Known Risks
- **Julia Translation**: Algorithms in the book might be complex; translation needs high-quality prompts and validation.
- **LaTeX Consistency**: Ensuring the frontend can render the extracted LaTeX correctly.
- **Performance**: LLM post-processing adds latency; consider efficient prompting or caching.
