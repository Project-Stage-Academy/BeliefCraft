from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ValidationError

from common.utils.config_errors import (
    ConfigFileNotFound,
    ConfigParseError,
    ConfigValidationError,
    MissingEnvironmentVariable,
)

T = TypeVar("T", bound=BaseModel)

_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigLoader:
    """
    Monorepo config loader.

    Layout assumed:
      repo_root/
        services/<service_name>/config/default.yaml
        services/<service_name>/config/dev.yaml
        services/<service_name>/config/prod.yaml

    Base config path precedence:
      (1) cli_config_path (--config)
      (2) <SERVICE_NAME>_CONFIG environment variable
      (3) services/<service_name>/config/default.yaml

    Optional env override:
      if env is provided -> merge services/<service_name>/config/{env}.yaml on top

    Placeholder expansion:
      ${VAR} resolved from .env (if present) first, then os.environ.
    """

    def __init__(self, repo_root: Optional[str | Path] = None):
        self.repo_root = Path(repo_root).resolve() if repo_root else self._detect_repo_root()

    def load(
        self,
        *,
        service_name: str,
        schema: Type[T],
        env: Optional[str] = None,                  # "dev" | "prod" | None
        cli_config_path: Optional[str] = None,      # --config
        dotenv_mode: str = "config_dir_then_repo",  # "config_dir_then_repo" | "repo_only" | "none"
    ) -> T:
        config_dir = self.repo_root / "services" / service_name / "config"
        if not config_dir.exists():
            raise ConfigFileNotFound(f"Config directory not found: {config_dir}")

        base_path = self._resolve_base_path(service_name, config_dir, cli_config_path)
        base = self._read_yaml(base_path)

        merged = base

        # Optional env override: dev.yaml / prod.yaml
        if env:
            override_path = config_dir / f"{env}.yaml"
            if override_path.exists():
                override = self._read_yaml(override_path)
                merged = self._deep_merge(merged, override)

        # Expand ${VAR} using .env then os.environ
        dotenv_path = self._resolve_dotenv_path(dotenv_mode, config_dir)
        merged = self._expand_vars(merged, dotenv_path)

        # Validate
        try:
            return schema.model_validate(merged)
        except ValidationError as e:
            raise ConfigValidationError(
                f"Validation failed for service '{service_name}' config loaded from '{base_path}'. {e}"
            ) from e

    # ----------------- internal helpers -----------------

    def _detect_repo_root(self) -> Path:
        # Walk up from current file until we find repo markers
        here = Path(__file__).resolve().parent
        for parent in [here] + list(here.parents):
            if (parent / "services").exists() and (parent / "packages").exists():
                return parent
        return Path.cwd().resolve()

    def _resolve_base_path(self, service_name: str, config_dir: Path, cli_config_path: Optional[str]) -> Path:
        if cli_config_path:
            p = Path(cli_config_path).expanduser().resolve()
            if not p.exists():
                raise ConfigFileNotFound(f"--config file not found: {p}")
            return p

        env_var = f"{service_name.upper().replace('-', '_')}_CONFIG"
        env_path = os.getenv(env_var)
        if env_path:
            p = Path(env_path).expanduser().resolve()
            if not p.exists():
                raise ConfigFileNotFound(f"{env_var} points to missing file: {p}")
            return p

        p = (config_dir / "default.yaml").resolve()
        if not p.exists():
            raise ConfigFileNotFound(f"Default config not found: {p}")
        return p

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigFileNotFound(f"Cannot read config file: {path}. {e}") from e

        try:
            data = yaml.safe_load(text)
        except Exception as e:
            raise ConfigParseError(f"Invalid YAML in {path}: {e}") from e

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ConfigParseError(f"Top-level YAML must be a mapping/object: {path}")
        return data

    def _deep_merge(self, base: Any, override: Any) -> Any:
        if isinstance(base, dict) and isinstance(override, dict):
            out = dict(base)
            for k, v in override.items():
                out[k] = self._deep_merge(out.get(k), v) if k in out else v
            return out
        # lists and scalars: replace (predictable)
        return override

    def _resolve_dotenv_path(self, mode: str, config_dir: Path) -> Optional[Path]:
        if mode == "none":
            return None

        repo_dotenv = self.repo_root / ".env"
        service_dotenv = config_dir / ".env"

        if mode == "repo_only":
            return repo_dotenv if repo_dotenv.exists() else None

        if mode != "config_dir_then_repo":
            raise ConfigParseError(
                "Invalid dotenv_mode. Expected one of: 'config_dir_then_repo', 'repo_only', 'none'."
            )

        # default: config_dir_then_repo
        if service_dotenv.exists():
            return service_dotenv
        if repo_dotenv.exists():
            return repo_dotenv
        return None

    def _expand_vars(self, obj: Any, dotenv_path: Optional[Path]) -> Any:
        dotenv_vars: dict[str, str] = {}
        if dotenv_path:
            raw = dotenv_values(dotenv_path)
            dotenv_vars = {k: v for k, v in raw.items() if v is not None}

        def resolve(var: str, key_path: str) -> str:
            if var in dotenv_vars:
                return dotenv_vars[var]
            if var in os.environ:
                return os.environ[var]
            raise MissingEnvironmentVariable(var, key_path)

        def walk(x: Any, path: str) -> Any:
            if isinstance(x, dict):
                return {k: walk(v, f"{path}.{k}") for k, v in x.items()}
            if isinstance(x, list):
                return [walk(v, f"{path}[{i}]") for i, v in enumerate(x)]
            if isinstance(x, str):
                def repl(m: re.Match) -> str:
                    return resolve(m.group(1), path)
                return _VAR_PATTERN.sub(repl, x)
            return x

        return walk(obj, "root")
