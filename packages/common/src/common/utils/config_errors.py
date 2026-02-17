class ConfigError(Exception):
    pass


class ConfigFileNotFoundError(ConfigError):
    pass


class ConfigParseError(ConfigError):
    pass


class ConfigValidationError(ConfigError):
    pass


class MissingEnvironmentVariableError(ConfigError):
    def __init__(self, var_name: str, key_path: str):
        super().__init__(
            f"Missing env var '{var_name}' referenced at '{key_path}'. "
            f"Define it in .env or export it in the environment."
        )
