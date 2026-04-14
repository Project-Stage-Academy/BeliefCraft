"""Runtime helpers for agent-driven retrieval evaluation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

try:
    from weaviate.util import generate_uuid5 as _generate_uuid5
except Exception:  # pragma: no cover - fallback for constrained environments
    from uuid import NAMESPACE_URL, uuid5

    def _generate_uuid5(value: str) -> str:
        return str(uuid5(NAMESPACE_URL, value))


@dataclass
class ChunkResolutionIndex:
    """Indexes used to resolve tool payload UUIDs back to golden-set chunk IDs."""

    known_chunk_ids: set[str] = field(default_factory=set)
    uuid_to_chunk_id: dict[str, str] = field(default_factory=dict)
    entity_to_chunk_id: dict[tuple[str, str], str] = field(default_factory=dict)
    content_to_chunk_id: dict[str, str] = field(default_factory=dict)


@dataclass
class ManagedService:
    """Represents one background service process started by evaluation."""

    name: str
    base_url: str
    health_path: str
    process: subprocess.Popen[str] | None = None


class ManagedServiceStack(AbstractContextManager["ManagedServiceStack"]):
    """Starts required services for evaluation and shuts them down automatically."""

    def __init__(
        self,
        *,
        project_root: Path,
        start_services: bool,
        rag_base_url: str,
        agent_base_url: str,
    ) -> None:
        self._project_root = project_root
        self._start_services = start_services
        self.rag_base_url = rag_base_url.rstrip("/")
        self.agent_base_url = agent_base_url.rstrip("/")
        self._services: list[ManagedService] = []

    def __enter__(self) -> ManagedServiceStack:
        if not self._start_services:
            return self

        rag_service = ManagedService(
            name="rag-service",
            base_url=self.rag_base_url,
            health_path="/health",
        )
        agent_service = ManagedService(
            name="agent-service",
            base_url=self.agent_base_url,
            health_path="/api/v1/health",
        )

        self._ensure_service(
            service=rag_service,
            cwd=self._project_root / "services" / "rag-service",
            module="rag_service.main:app",
            env_overrides={
                "ENV": os.getenv("RAG_ENV", "dev"),
            },
        )

        self._ensure_service(
            service=agent_service,
            cwd=self._project_root / "services" / "agent-service",
            module="app.main:app",
            env_overrides={
                "ENV": os.getenv("AGENT_ENV", "local"),
                "RAG_API_URL": self.rag_base_url,
            },
        )

        return self

    def __exit__(self, exc_type: Any, exc: Any, exc_tb: Any) -> None:
        for service in reversed(self._services):
            process = service.process
            if process is None:
                continue
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def _ensure_service(
        self,
        *,
        service: ManagedService,
        cwd: Path,
        module: str,
        env_overrides: dict[str, str],
    ) -> None:
        if _is_service_ready(service.base_url, service.health_path):
            return

        env = os.environ.copy()
        env.update(env_overrides)

        command = [
            sys.executable,
            "-m",
            "uvicorn",
            module,
            "--host",
            "127.0.0.1",
            "--port",
            service.base_url.rsplit(":", 1)[-1],
        ]

        process = (
            subprocess.Popen(  # noqa: S603 - module and args are fully controlled by this script
                command,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        )

        service.process = process
        self._services.append(service)

        if not _wait_until_ready(service.base_url, service.health_path, timeout_seconds=40):
            process.terminate()
            raise RuntimeError(
                f"Failed to start {service.name}; endpoint {service.base_url}{service.health_path} "
                "did not become ready"
            )


def _is_service_ready(base_url: str, health_path: str) -> bool:
    try:
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=2.0) as client:
            response = client.get(health_path)
        return response.status_code < 500
    except Exception:
        return False


def _wait_until_ready(base_url: str, health_path: str, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_service_ready(base_url, health_path):
            return True
        time.sleep(0.5)
    return False


def load_chunk_resolution_index(enriched_path: Path) -> ChunkResolutionIndex:
    """Build a resolver index for mapping UUID/document payloads to `chunk_id`."""
    index = ChunkResolutionIndex()
    if not enriched_path.exists():
        return index

    with enriched_path.open(encoding="utf-8") as file_obj:
        payload = json.load(file_obj)

    if not isinstance(payload, list):
        return index

    content_bucket: dict[str, list[str]] = defaultdict(list)

    for row in payload:
        if not isinstance(row, dict):
            continue
        chunk_id = row.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            continue
        chunk_id = chunk_id.strip()
        index.known_chunk_ids.add(chunk_id)

        entity_id = row.get("entity_id")
        chunk_type = row.get("chunk_type")
        if isinstance(entity_id, str) and entity_id and isinstance(chunk_type, str) and chunk_type:
            index.entity_to_chunk_id.setdefault((entity_id, chunk_type), chunk_id)

        content = row.get("content")
        if isinstance(content, str) and content:
            content_bucket[content].append(chunk_id)

        explicit_uuid = row.get("id")
        if isinstance(explicit_uuid, str) and explicit_uuid:
            index.uuid_to_chunk_id.setdefault(explicit_uuid, chunk_id)

        _populate_uuid_candidates(index.uuid_to_chunk_id, row, chunk_id)

    for content, chunk_ids in content_bucket.items():
        if len(chunk_ids) == 1:
            index.content_to_chunk_id[content] = chunk_ids[0]

    return index


def _populate_uuid_candidates(uuid_map: dict[str, str], row: dict[str, Any], chunk_id: str) -> None:
    candidate_variants = [
        dict(row),
        {key: value for key, value in row.items() if key != "chunk_id"},
    ]

    for candidate in candidate_variants:
        candidate_uuid = _generate_deterministic_uuid(candidate)
        if candidate_uuid:
            uuid_map.setdefault(candidate_uuid, chunk_id)


def _generate_deterministic_uuid(chunk: dict[str, Any]) -> str | None:
    entity_id = chunk.get("entity_id", "")
    chunk_type = chunk.get("chunk_type", "")

    if isinstance(entity_id, str) and entity_id and isinstance(chunk_type, str) and chunk_type:
        return _generate_uuid5(f"{entity_id}:{chunk_type}")

    try:
        return _generate_uuid5(repr(chunk))
    except Exception:
        return None


def resolve_document_chunk_id(
    document: dict[str, Any], index: ChunkResolutionIndex
) -> tuple[str | None, str]:
    """Resolve chunk identity from tool document payload with fallback strategies."""

    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    chunk_id = metadata.get("chunk_id") or document.get("chunk_id")
    if isinstance(chunk_id, str) and chunk_id in index.known_chunk_ids:
        return chunk_id, "metadata.chunk_id"

    raw_id = document.get("id")
    if isinstance(raw_id, str) and raw_id in index.known_chunk_ids:
        return raw_id, "document.id_chunk_id"

    if isinstance(raw_id, str):
        mapped_chunk_id = index.uuid_to_chunk_id.get(raw_id)
        if mapped_chunk_id:
            return mapped_chunk_id, "uuid_map"

    entity_id = metadata.get("entity_id") or document.get("entity_id")
    chunk_type = metadata.get("chunk_type") or document.get("chunk_type")
    if isinstance(entity_id, str) and isinstance(chunk_type, str):
        mapped_chunk_id = index.entity_to_chunk_id.get((entity_id, chunk_type))
        if mapped_chunk_id:
            return mapped_chunk_id, "entity_chunk_type"

    content = document.get("content")
    if isinstance(content, str):
        mapped_chunk_id = index.content_to_chunk_id.get(content)
        if mapped_chunk_id:
            return mapped_chunk_id, "content_match"

    return None, "unresolved"
