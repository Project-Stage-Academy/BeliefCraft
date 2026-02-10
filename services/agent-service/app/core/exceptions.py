class AgentServiceException(Exception):
    """Base exception for agent service"""
    
    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class ConfigurationError(AgentServiceException):
    """Raised when configuration is invalid"""
    
    def __init__(self, message: str):
        super().__init__(message, status_code=500, error_code="CONFIGURATION_ERROR")


class ExternalServiceError(AgentServiceException):
    """Raised when external service call fails"""
    
    def __init__(self, message: str, service_name: str):
        self.service_name = service_name
        super().__init__(message, status_code=503, error_code="EXTERNAL_SERVICE_ERROR")


class AgentExecutionError(AgentServiceException):
    """Raised when agent execution fails"""
    
    def __init__(self, message: str):
        super().__init__(message, status_code=500, error_code="AGENT_EXECUTION_ERROR")


class ToolExecutionError(AgentServiceException):
    """Raised when tool execution fails"""
    
    def __init__(self, message: str, tool_name: str):
        self.tool_name = tool_name
        super().__init__(message, status_code=500, error_code="TOOL_EXECUTION_ERROR")


class ValidationError(AgentServiceException):
    """Raised when request validation fails"""
    
    def __init__(self, message: str):
        super().__init__(message, status_code=400, error_code="VALIDATION_ERROR")
