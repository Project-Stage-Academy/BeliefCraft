"""
Base class for all agent tools.

This module provides the foundation for creating tools that can be used by
the ReAct agent. All tools must inherit from BaseTool and implement the
required abstract methods.

Example:
    ```python
    from app.tools.base import BaseTool, ToolMetadata
    
    class MyTool(BaseTool):
        def get_metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="my_tool",
                description="Does something useful",
                parameters={
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string"}
                    },
                    "required": ["param1"]
                },
                category="utility"
            )
        
        async def execute(self, param1: str) -> dict:
            return {"result": f"Processed {param1}"}
    ```
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from common.logging import get_logger
from pydantic import BaseModel, Field, ConfigDict

logger = get_logger(__name__)


class ToolMetadata(BaseModel):
    """
    Metadata describing a tool's interface and purpose.
    
    This schema is used to generate OpenAI function calling schemas
    that are compatible with Amazon Bedrock and other LLM platforms.
    
    Attributes:
        name: Unique identifier for the tool (snake_case recommended)
        description: Clear description of what the tool does
        category: Tool category for filtering (environment/rag/planning/utility)
        parameters: JSON Schema object describing tool parameters (defaults to empty schema)
    """
    
    model_config = ConfigDict(frozen=True)
    
    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="What the tool does")
    category: str = Field(..., description="Tool category")
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
            "required": []
        },
        description="JSON Schema for parameters"
    )


class ToolResult(BaseModel):
    """
    Result from tool execution with metadata.
    
    Attributes:
        success: Whether execution succeeded
        data: Result data (if successful)
        error: Error message (if failed)
        execution_time_ms: Time taken to execute in milliseconds
        cached: Whether result was retrieved from cache
        timestamp: UTC timestamp of execution
    """
    
    success: bool = Field(..., description="Execution success status")
    data: Any = Field(default=None, description="Result data")
    error: str | None = Field(default=None, description="Error message if failed")
    execution_time_ms: float = Field(..., description="Execution time in ms")
    cached: bool = Field(default=False, description="Result from cache")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Execution timestamp")


class BaseTool(ABC):
    """
    Abstract base class for all agent tools.
    
    Tools provide capabilities to the agent such as querying APIs,
    performing calculations, or retrieving knowledge. Each tool must:
    
    1. Define metadata (name, description, parameters schema)
    2. Implement async execute() method
    3. Return structured data (dict, list, or Pydantic models)
    
    The base class handles:
    - Execution timing with high-precision perf_counter
    - Error handling and recovery
    - Structured logging
    - Conversion to OpenAI function calling format
    """
    
    def __init__(self) -> None:
        """Initialize tool and validate metadata."""
        self.metadata = self.get_metadata()
        logger.debug(
            "tool_initialized",
            tool_name=self.metadata.name,
            category=self.metadata.category
        )
    
    @abstractmethod
    def get_metadata(self) -> ToolMetadata:
        """
        Return tool metadata for function calling schema.
        
        Returns:
            ToolMetadata with name, description, parameters, and category
        """
        pass
    
    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """
        Execute the tool with given parameters.
        
        Args:
            **kwargs: Tool-specific parameters matching the JSON schema
        
        Returns:
            Tool-specific result data (dict, list, or Pydantic model)
        
        Raises:
            Any exception during execution (will be caught by run())
        """
        pass
    
    async def run(self, **kwargs: Any) -> ToolResult:
        """
        Wrapper that handles execution, timing, and error catching.
        
        This method should be called instead of execute() directly.
        It provides:
        - High-precision timing with perf_counter
        - Automatic error handling
        - Structured logging
        - Consistent ToolResult format
        
        Args:
            **kwargs: Parameters to pass to execute()
        
        Returns:
            ToolResult with success status, data, and metadata
        """
        start_time = time.perf_counter()
        
        try:
            logger.info(
                "tool_execution_start",
                tool=self.metadata.name,
                category=self.metadata.category,
                parameters=kwargs
            )
            
            result = await self.execute(**kwargs)
            
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            logger.info(
                "tool_execution_success",
                tool=self.metadata.name,
                duration_ms=round(execution_time_ms, 2)
            )
            
            return ToolResult(
                success=True,
                data=result,
                execution_time_ms=round(execution_time_ms, 2)
            )
            
        except Exception as e:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            logger.error(
                "tool_execution_error",
                tool=self.metadata.name,
                category=self.metadata.category,
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=round(execution_time_ms, 2),
                exc_info=True
            )
            
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                execution_time_ms=round(execution_time_ms, 2)
            )
    
    def to_openai_function(self) -> dict[str, Any]:
        """
        Convert tool metadata to OpenAI function calling schema.
        
        This format is compatible with:
        - OpenAI GPT-4 function calling
        - Amazon Bedrock Claude function calling
        - Azure OpenAI function calling
        
        Returns:
            Dictionary with 'type' and 'function' keys
        """
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": self.metadata.parameters
            }
        }
