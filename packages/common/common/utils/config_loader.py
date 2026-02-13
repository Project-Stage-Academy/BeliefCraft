from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, TypeVar

import yaml
from common.utils.config_errors import (
    ConfigFileNotFoundError,
    ConfigParseError,
    ConfigValidationError,
    MissingEnvironmentVariableError,
)
from common.utils.settings_base import BaseSettings
from dotenv import dotenv_values
from pydantic import ValidationError

T = TypeVar("T", bound=BaseSettings)

_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigLoader:
    """
    Service-local config loader.

    Layout assumed (relative to service_root):
      config/default.yaml
      config/dev.yaml
      config/prod.yaml

    Base config path precedence:
      (1) cli_config_path (--config)
      (2) config_env_var environment variable (if provided)
      (3) config/default.yaml

    Optional env override:
      if env is provided -> merge config/{env}.yaml on top

    Placeholder expansion:
      ${VAR} resolved from .env (if present) first, then os.environ.
    """

    def __init__(self, service_root: str | Path | None = None, config_dir: str = "config"):
        self.service_root = Path(service_root).resolve() if service_root else Path.cwd().resolve()
        config_dir_path = Path(config_dir)
        self.config_dir = (
            config_dir_path
            if config_dir_path.is_absolute()
            else (self.service_root / config_dir_path)
        ).resolve()

    def load(
        self,
        *,
        schema: type[T],
        env: str | None = None,  # "dev" | "prod" | None
        cli_config_path: str | None = None,  # --config
        config_env_var: str | None = None,
        dotenv_mode: str = (
            "config_dir_then_service_root"
        ),  # "config_dir_then_service_root" | "service_root_only" | "none"
    ) -> T:
        config_dir = self.config_dir
        if not config_dir.exists():
            raise ConfigFileNotFoundError(f"Config directory not found: {config_dir}")

        base_path = self._resolve_base_path(config_dir, cli_config_path, config_env_var)
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
                f"Validation failed for config loaded from '{base_path}'. {e}"
            ) from e

    # ----------------- internal helpers -----------------

    def _resolve_base_path(
        self,
        config_dir: Path,
        cli_config_path: str | None,
        config_env_var: str | None,
    ) -> Path:
        if cli_config_path:
            raw = Path(cli_config_path).expanduser()
            p = (raw if raw.is_absolute() else (self.service_root / raw)).resolve()
            if not p.exists():
                raise ConfigFileNotFoundError(f"--config file not found: {p}")
            return p

        env_path = os.getenv(config_env_var) if config_env_var else None
        if config_env_var and env_path:
            p = Path(env_path).expanduser().resolve()
            if not p.exists():
                raise ConfigFileNotFoundError(f"{config_env_var} points to missing file: {p}")
            return p

        p = (config_dir / "default.yaml").resolve()
        if not p.exists():
            raise ConfigFileNotFoundError(f"Default config not found: {p}")
        return p

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigFileNotFoundError(f"Cannot read config file: {path}. {e}") from e

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

    def _resolve_dotenv_path(self, mode: str, config_dir: Path) -> Path | None:
        if mode == "none":
            return None

        service_root_dotenv = self.service_root / ".env"
        service_dotenv = config_dir / ".env"

        if mode == "service_root_only":
            return service_root_dotenv if service_root_dotenv.exists() else None

        if mode != "config_dir_then_service_root":
            raise ConfigParseError(
                "Invalid dotenv_mode. Expected one of: "
                "'config_dir_then_service_root', 'service_root_only', 'none'."
            )

        # default: config_dir_then_service_root
        if service_dotenv.exists():
            return service_dotenv
        if service_root_dotenv.exists():
            return service_root_dotenv
        return None

    def _expand_vars(self, obj: Any, dotenv_path: Path | None) -> Any:
        dotenv_vars: dict[str, str] = {}
        if dotenv_path:
            raw = dotenv_values(dotenv_path)
            dotenv_vars = {k: v for k, v in raw.items() if v is not None}

        def resolve(var: str, key_path: str) -> str:
            if var in dotenv_vars:
                return dotenv_vars[var]
            if var in os.environ:
                return os.environ[var]
            raise MissingEnvironmentVariableError(var, key_path)

        def walk(x: Any, path: str) -> Any:
            if isinstance(x, dict):
                return {k: walk(v, f"{path}.{k}") for k, v in x.items()}
            if isinstance(x, list):
                return [walk(v, f"{path}[{i}]") for i, v in enumerate(x)]
            if isinstance(x, str):

                def repl(m: re.Match[str]) -> str:
                    return resolve(m.group(1), path)

                return _VAR_PATTERN.sub(repl, x)
            return x

        return walk(obj, "root")
