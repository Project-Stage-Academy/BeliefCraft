import pytest
from common.http_client import TracedHttpClient
from fastmcp.client import Client, StreamableHttpTransport
from httpx import ASGITransport
from rag_service.main import app


@pytest.mark.asyncio
async def test_mcp_connection_lists_three_tools():
    """
    Test that we can connect to the MCP endpoint and list exactly 3 tools.
    This uses ASGITransport to avoid needing a running server.
    """
    # Use ASGITransport to route requests directly to the FastAPI app
    transport_asgi = ASGITransport(app=app)
    # Ensure app lifespan is running so FastMCP session manager is initialized
    async with (
        app.router.lifespan_context(app),
        TracedHttpClient("http://ragserver", config={"transport": transport_asgi}) as traced_client,
    ):
        transport = StreamableHttpTransport(
            "http://ragserver/mcp",
            httpx_client_factory=lambda *args, **kwargs: traced_client.get_httpx_client(),
        )

        async with Client(transport) as client:
            tools = await client.list_tools()
            assert len(tools) == 3
