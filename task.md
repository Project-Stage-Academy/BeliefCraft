#### **Story 0.2: Development Environment & Docker Setup**

**As a** developer
**I want** a one-command local development environment
**So that** I can quickly onboard and start contributing

**Acceptance Criteria:**
- [ ] `make setup` installs all dependencies for all services
- [ ] `make dev` starts all services in development mode with hot-reload
- [ ] Docker Compose includes: PostgreSQL, Qdrant, Redis (for caching)
- [ ] All services expose health check endpoints (`/health`)
- [ ] Environment variables managed via `.env` files (not hardcoded)
- [ ] Database migrations run automatically on startup
- [ ] Documentation includes troubleshooting common issues

**Technical Tasks:**
- [ ] Write `docker-compose.yml` with services:
  ```yaml
  services:
    postgres:
      image: postgres:15-alpine
      environment: ...
      volumes: ...
    qdrant:
      image: qdrant/qdrant:latest
    redis:
      image: redis:7-alpine
    environment-api:
      build: ./services/environment-api
      depends_on: [postgres]
    rag-service:
      build: ./services/rag-service
      depends_on: [postgres, qdrant]
    agent-service:
      build: ./services/agent-service
      depends_on: [environment-api, rag-service, redis]
    ui:
      build: ./services/ui
      depends_on: [agent-service]
  ```
- [ ] Write Dockerfiles for each service (multi-stage builds)
- [ ] Create Makefile with common commands:
  ```makefile
  setup: Install dependencies
  dev: Start all services in dev mode
  test: Run all tests
  lint: Run linters
  format: Auto-format code
  clean: Remove containers and volumes
  ```
- [ ] Set up PostgreSQL initialization script (create databases)
- [ ] Add health check scripts for all services

**Effort:** 3 story points
**Priority:** P0 (Critical - Blocker)
