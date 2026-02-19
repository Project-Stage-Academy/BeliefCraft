Integration Specification: RAG Service for BeliefCraft Agent

## Overview
The RAG Service provides the agent with theoretical knowledge, mathematical formulas, and algorithms for inventory decision-making. The agent interacts with this service via the RAGAPIClient.

## Base Configuration
- **Communication Format:** JSON
- **Base URL:** `RAG_SERVICE_URL` (default: http://localhost:8001)
- **Knowledge Source:** "Algorithms for Decision Making" (Textbook)
- **Response Format:** All endpoints return JSON with consistent structure

## Required Endpoints

### 1. Semantic Knowledge Search
**Endpoint:** `POST /search/semantic`

**Description:** Performs vector similarity search to find relevant text chunks, formulas, or algorithms based on natural language queries.

**Request Body (JSON):**
```json
{
  "query": "string (required, e.g., 'inventory control under uncertainty')",
  "k": "integer (default: 5, min: 1, max: 20)",
  "traverse_types": ["array of entity types (optional)", "e.g., ['formula', 'algorithm']"],
  "filters": {
    "chapter": "string (optional)",
    "section": "string (optional)",
    "page_number": "integer (optional)"
  }
}
```

**Query Examples:**
- "POMDP belief state update algorithm"
- "inventory control (s,S) policy"
- "CVaR tail risk assessment"
- "Bayesian parameter estimation for demand"

**Valid `traverse_types` Values:**
- `formula` - Mathematical equations and definitions
- `algorithm` - Pseudocode and algorithmic procedures
- `table` - Data tables and comparisons
- `figure` - Diagrams and visualizations
- `section` - Chapter sections for context
- `example` - Worked examples
- `exercise` - Practice problems
- `appendix` - Supplementary material

**Response:** Should return array of results with:
```json
{
  "results": [
    {
      "id": "chunk_id",
      "type": "formula|algorithm|table|...",
      "content": "text or LaTeX content",
      "number": "3.2",
      "title": "Title of entity",
      "chapter": "3",
      "section": "3.1",
      "page_number": 87,
      "score": 0.95
    }
  ],
  "total_count": 5
}
```

**Agent-side Caching:** 24 hours (TTL: 86400s). Static knowledge doesn't change frequently.

### 2. Knowledge Graph Expansion
**Endpoint:** `POST /search/expand-graph`

**Description:** Navigates knowledge graph relationships to find connected entities (formulas used in algorithms, algorithms that cite formulas, etc.).

**Request Body (JSON):**
```json
{
  "document_ids": ["array of chunk/entity IDs", "e.g., ['formula_3_2', 'algo_4_1']"],
  "traverse_types": ["array of relationship types (optional)", "e.g., ['USES_IN', 'CITES']"]
}
```

**Valid Relationship Types:**
- `USES_IN` - Formula used in algorithm
- `CITES` - Document cites another
- `REFERENCES` - References another section
- `RELATED_TO` - Thematically related
- `FOLLOWS` - Builds upon (prerequisite)
- `REFERENCED_BY` - Referenced by other entities
- `PART_OF` - Part of a larger section

**Response:** Should return:
```json
{
  "expanded_documents": [
    {
      "id": "entity_id",
      "type": "formula|algorithm|...",
      "content": "text content",
      "relationships": [
        {
          "type": "USES_IN",
          "target_id": "algo_3_2",
          "target_type": "algorithm"
        }
      ]
    }
  ],
  "relationship_count": 3
}
```

**Agent-side Caching:** 24 hours (TTL: 86400s).

### 3. Retrieve Entity by Number
**Endpoint:** `GET /entity/{entity_type}/{number}`
**Description:** Direct retrieval of specific numbered items from the textbook.

**Path Parameters:**
- `entity_type`: Enum - `formula` | `algorithm` | `table` | `figure`
- `number`: String - e.g., "3.2", "16.4", "A.1"

**Example Calls:**
```
GET /entity/algorithm/3.2       → (s,S) Inventory Policy algorithm
GET /entity/formula/16.4        → Risk measure formula
GET /entity/table/5.1           → Demand statistics table
GET /entity/figure/7.2          → Warehouse network diagram
```

**Response:** Should return single entity:
```json
{
  "id": "formula_3_2",
  "type": "algorithm",
  "number": "3.2",
  "title": "(s,S) Inventory Policy",
  "content": "pseudocode or LaTeX content",
  "chapter": "3",
  "section": "3.2",
  "page_number": 89,
  "references": ["formula_3_1", "table_3_2"],
  "cited_by": ["example_3_3", "exercise_3_4"]
}
```

**Status Codes:**
- `200 OK` - Entity found and returned
- `400 Bad Request` - Invalid entity_type or number format
- `404 Not Found` - Entity doesn't exist in knowledge base

**Agent-side Caching:** 7 days (TTL: 604800s). Once an entity number is defined, it doesn't change.

## Technical Expectations for the RAG Team

### Parameter Validation Requirements

**Query Parameter (`/search/semantic`)**
- Must be non-empty string
- Minimum length: 3 characters
- Return 400 Bad Request if empty or too short
- Example error: `{"detail": "query must be at least 3 characters"}`

**k Parameter (Number of Results)**
- Must be integer
- Valid range: 1-20
- Return 400 Bad Request if out of range
- Example error: `{"detail": "k must be between 1 and 20"}`

**traverse_types Array**
- Each value must be from valid set: `[formula, algorithm, table, figure, section, example, exercise, appendix]`
- Return 400 Bad Request if invalid type
- Example error: `{"detail": "traverse_types contains invalid value: 'invalid_type'. Valid values: [formula, algorithm, ...]"}`

**filters Object**
- Keys must match documented properties: `chapter`, `section`, `page_number`
- Return 400 Bad Request if invalid key
- `page_number` must be integer if present
- Example error: `{"detail": "filter 'invalid_key' is not supported"}`

**document_ids Array (Expand Graph)**
- Each ID must exist in knowledge base
- Return 400 Bad Request if ID format invalid
- May return partial results if some IDs not found
- Example: return found documents with warning in metadata

**entity_type and number (`/entity/{type}/{number}`)**
- `entity_type` must be from enum: `formula`, `algorithm`, `table`, `figure`
- `number` must match pattern: digits + dot + digits (e.g., "3.2", "16.4", "A.1")
- Return 400 Bad Request if format invalid
- Return 404 Not Found if entity doesn't exist
- Example errors:
  - `{"detail": "entity_type must be one of: formula, algorithm, table, figure"}`
  - `{"detail": "number format invalid. Expected format: X.Y or X.YZ"}`
  - `{"detail": "Algorithm 99.99 not found in knowledge base"}`

### Semantic Accuracy
- Search results must include relevant mathematics, algorithms, and domain context
- Return results sorted by relevance score (descending)
- Include metadata (chapter, section, page_number) so agent can cite sources
- Handle typos gracefully (e.g., "POMP" → suggest "POMDP")

### Entity Mapping
- Ensure `entity_type` values exactly match: `formula`, `algorithm`, `table`, `figure`
- Numbering system must be consistent across knowledge base
- Each entity should have unique (type, number) combination

### Graph Relationships
Support traversing these relationship types:
- **USES_IN** - Formula used in algorithm
- **PART_OF** - Entity belongs to larger structure
- **REFERENCED_BY** - Other entities reference this one
- **CITES** - Entity cites another work/section
- **FOLLOWS** - Prerequisite/builds upon relationship

### Performance Requirements
- `/search/semantic` response time: < 1 second (vector search is expensive)
- `/search/expand-graph` response time: < 500ms (graph traversal)
- `/entity/{type}/{number}` response time: < 100ms (direct lookup)
- Implement caching/pagination for large result sets

### Error Handling
Return consistent error format:
```json
{
  "detail": "error_message_here",
  "status_code": 400,
  "error_code": "INVALID_PARAMETER",
  "timestamp": "2026-02-18T14:30:00Z"
}
```

## Caching Implications

### Static Knowledge (24h Cache)
- Search results and graph expansion use 24-hour cache
- Same query parameters return cached results
- Reduces API load for repeated agent decisions

### Entity Caching (7 day Cache)
- Direct entity retrieval cached for 7 days
- Changes to entities (new content) won't be immediate
- Requires explicit cache invalidation if entity updates needed

### Example Timeline (Agent Execution)
```
Agent thinks: "What's the (s,S) inventory policy?"
  ↓
Search: "inventory control s s policy" (FRESH from API)
  ↓
Expand: Get formula 3.2 (FRESH from API)
  ↓
Direct: GET /entity/algorithm/3.2 (FRESH from API)
  ↓
Agent cites: "According to Algorithm 3.2 in Chapter 3..."

5 minutes later...
Another agent thinks the same
  ↓
Search: "inventory control s s policy" (FROM CACHE ✓)
  ↓
Expand: Graph expansion (FROM CACHE ✓)
  ↓
Direct: GET /entity/algorithm/3.2 (FROM CACHE ✓)
```

## Common Issues & Solutions

**Issue:** Search returns no results for valid query
- **Solution:** Check if query is too specific. Try broader terms. Verify chunks exist in knowledge base.

**Issue:** 404 on `/entity/algorithm/3.2` but search finds it
- **Solution:** Entity numbering mismatch. Search chunk storage might differ from entity table. Verify entity database has entry.

**Issue:** Graph expansion returns incomplete relationships
- **Solution:** Not all edges in graph might be indexed. Check relationship table for completeness.

**Issue:** High latency on semantic search
- **Solution:** Vector embeddings might not be indexed. Verify vector DB has proper indexes. Consider pagination.
