# C4 Model Diagrams: BeliefCraft System

This document contains C4-style Mermaid diagrams aligned with the current repository implementation.

## Level 1: System Context Diagram

```mermaid
C4Context
    title System Context Diagram for BeliefCraft

    Person(operator, "Operator", "Uses BeliefCraft for warehouse analytics and decisions.")
    System(beliefcraft, "BeliefCraft", "Multi-service analytics and ReAct agent platform.")

    Rel(operator, beliefcraft, "Uses", "HTTPS")
```

## Level 2: Container Diagram

```mermaid
C4Container
    title Container Diagram for BeliefCraft

    Person(operator, "Operator")

    System_Boundary(beliefcraft_boundary, "BeliefCraft") {
        Container(ui, "UI Service", "Next.js", "UI shell with health endpoint; backend API integration is planned")

        Container(agent_service, "Agent Service", "FastAPI + LangGraph", "Runs ReAct loop and tool orchestration")
        Container(environment_api, "Environment API", "FastAPI", "Smart-query analytics over warehouse data")
        Container(rag_service, "RAG Service", "FastAPI", "Current implementation: health endpoint")

        ContainerDb(redis, "Redis", "Redis", "Agent cache")
        ContainerDb(postgres, "PostgreSQL", "PostgreSQL", "Relational warehouse data")
        ContainerDb(qdrant, "Qdrant", "Vector DB", "Provisioned vector store")
    }

    Rel(operator, ui, "Uses", "HTTPS")
    Rel(ui, agent_service, "Planned: Calls API", "HTTP")

    Rel(agent_service, environment_api, "Calls tools", "HTTP")
    Rel(agent_service, rag_service, "Calls tools", "HTTP")

    Rel(agent_service, redis, "Caches results", "TCP")
    Rel(environment_api, postgres, "Reads data", "SQL")
    Rel(rag_service, qdrant, "Configured for vector store", "HTTP")
```

Current-state note:
- UI-to-agent business API calls are planned and shown as target architecture; current UI code implements health and middleware only.

## Level 3: Component Diagram (Agent Service)

```mermaid
C4Component
    title Component Diagram for Agent Service

    Container(ui, "UI Service", "Next.js")
    Container(environment_api, "Environment API", "FastAPI")
    Container(rag_service, "RAG Service", "FastAPI")
    ContainerDb(redis, "Redis", "Redis")

    Container_Boundary(agent_service, "Agent Service") {
        Component(api_routes, "API Routes", "FastAPI", "health.py, agent.py, tools.py")
        Component(react_agent, "ReActAgent", "LangGraph", "think/act/finalize workflow")
        Component(llm_service, "LLMService", "Bedrock client", "ChatBedrock invocation")
        Component(tool_registry, "Tool Registry", "Python", "Registered environment/rag tools")
        Component(cached_tools, "CachedTool", "Redis-backed wrapper", "TTL and skip_cache behavior")
        Component(http_clients, "API Clients", "HTTP", "EnvironmentAPIClient, RAGAPIClient")
    }

    Rel(ui, api_routes, "Planned: POST /api/v1/agent/analyze", "HTTP")
    Rel(api_routes, react_agent, "Runs")
    Rel(react_agent, llm_service, "Generates next action")
    Rel(react_agent, tool_registry, "Selects and executes tools")
    Rel(tool_registry, cached_tools, "Wraps tools")
    Rel(cached_tools, redis, "Read/Write cache")
    Rel(cached_tools, http_clients, "Calls downstream")
    Rel(http_clients, environment_api, "HTTP")
    Rel(http_clients, rag_service, "HTTP")
```
