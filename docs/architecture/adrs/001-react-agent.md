# ADR-001: Adoption of ReAct Architecture for Core Agent Execution

## Status
Accepted

## Date
2026-02-23

## Context
BeliefCraft must answer operational warehouse questions that require multi-step reasoning (inventory state, order risk, shipment delays, historical context). Single-shot responses are insufficient for reliable answers.

The codebase already contains:
- ReAct state machine (`services/agent-service/app/services/react_agent.py`)
- Tool registry with typed tool metadata (`services/agent-service/app/tools/*`)
- HTTP clients for environment and rag dependencies

## Decision
Use ReAct (`think -> act -> finalize`) in `agent-service` with LangGraph.

Implementation choices:
1. `think`: call Bedrock LLM and decide between tool use or final answer.
2. `act`: execute selected tool(s) via local `tool_registry`.
3. `finalize`: return structured API response with answer and reasoning trace.

Tool execution remains local-registry based; no mandatory external gateway is required by the current runtime.

## Consequences

### Positive
- Transparent step-by-step trace (`reasoning_trace`) for debugging and audits.
- Modular growth: tools are added as independent classes with JSON schemas.
- Better error recovery: tool failures are returned to the model as observations.

### Negative
- Higher latency than single-pass inference.
- More token usage due to iterative context updates.
- Requires strong parameter schemas to prevent repeated invalid tool calls.

## Alternatives Considered
- Single-shot prompting without tool calls: rejected because operational questions require external data retrieval and multi-step reasoning.
- External tool gateway as mandatory runtime dependency: rejected for MVP to keep execution path simpler and reduce operational coupling.
