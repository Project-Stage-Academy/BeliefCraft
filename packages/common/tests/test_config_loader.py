from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from common.utils.config_errors import ConfigValidationError, MissingEnvironmentVariable
from common.utils.config_loader import ConfigLoader


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    env: str


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str
    port: int


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: str


class TestSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app: AppConfig
    server: ServerConfig
    logging: LoggingConfig
    api_key: str


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    _write(
        tmp_path / "services" / "sample-service" / "config" / "default.yaml",
        """
app:
  name: "sample-service"
  env: "local"
server:
  host: "127.0.0.1"
  port: 8000
logging:
  level: "INFO"
api_key: "${API_KEY}"
""".strip(),
    )
    _write(
        tmp_path / "services" / "sample-service" / "config" / "dev.yaml",
        """
app:
  env: "dev"
server:
  port: 9000
logging:
  level: "DEBUG"
""".strip(),
    )
    return tmp_path


def test_loads_default_config(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "env-value")
    settings = ConfigLoader(repo_root=fake_repo).load(
        service_name="sample-service",
        schema=TestSettings,
    )

    assert settings.app.name == "sample-service"
    assert settings.app.env == "local"
    assert settings.server.port == 8000
    assert settings.logging.level == "INFO"
    assert settings.api_key == "env-value"


def test_merges_environment_override(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "env-value")
    settings = ConfigLoader(repo_root=fake_repo).load(
        service_name="sample-service",
        schema=TestSettings,
        env="dev",
    )

    assert settings.app.env == "dev"
    assert settings.server.port == 9000
    assert settings.logging.level == "DEBUG"


def test_precedence_cli_over_env_var_over_default(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override_file = fake_repo / "custom.yaml"
    _write(
        override_file,
        """
app:
  name: "cli-config"
  env: "prod"
server:
  host: "0.0.0.0"
  port: 7777
logging:
  level: "ERROR"
api_key: "${API_KEY}"
""".strip(),
    )
    env_file = fake_repo / "env-file.yaml"
    _write(
        env_file,
        """
app:
  name: "env-config"
  env: "prod"
server:
  host: "0.0.0.0"
  port: 6666
logging:
  level: "WARNING"
api_key: "${API_KEY}"
""".strip(),
    )

    monkeypatch.setenv("API_KEY", "env-value")
    monkeypatch.setenv("SAMPLE_SERVICE_CONFIG", str(env_file))

    loader = ConfigLoader(repo_root=fake_repo)
    settings_from_env = loader.load(
        service_name="sample-service",
        schema=TestSettings,
    )
    assert settings_from_env.server.port == 6666

    settings_from_cli = loader.load(
        service_name="sample-service",
        schema=TestSettings,
        cli_config_path=str(override_file),
    )
    assert settings_from_cli.server.port == 7777
    assert settings_from_cli.app.name == "cli-config"


def test_resolves_vars_from_dotenv_before_os_env(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = fake_repo / "services" / "sample-service" / "config"
    _write(config_dir / ".env", "API_KEY=dotenv-value")
    monkeypatch.setenv("API_KEY", "os-env-value")

    settings = ConfigLoader(repo_root=fake_repo).load(
        service_name="sample-service",
        schema=TestSettings,
    )

    assert settings.api_key == "dotenv-value"


def test_missing_var_raises_helpful_error(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(MissingEnvironmentVariable, match="Define it in .env or export it in the environment"):
        ConfigLoader(repo_root=fake_repo).load(
            service_name="sample-service",
            schema=TestSettings,
            dotenv_mode="none",
        )


def test_validation_errors_are_wrapped(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "env-value")
    default_path = fake_repo / "services" / "sample-service" / "config" / "default.yaml"
    _write(
        default_path,
        """
app:
  name: "sample-service"
server:
  host: "127.0.0.1"
  port: "not-an-int"
logging:
  level: "INFO"
api_key: "${API_KEY}"
""".strip(),
    )

    with pytest.raises(ConfigValidationError, match="Validation failed for service 'sample-service'"):
        ConfigLoader(repo_root=fake_repo).load(
            service_name="sample-service",
            schema=TestSettings,
        )
