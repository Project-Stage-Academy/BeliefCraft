from unittest.mock import AsyncMock, patch

import pytest
from app.clients.rag_mcp_client import RAGMCPClient


class TestRAGMCPClient:
    @pytest.mark.asyncio
    async def test_connect_cleans_up_partial_state_when_session_start_fails(self) -> None:
        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock()

        mock_mcp_client = AsyncMock()
        mock_mcp_client.__aenter__ = AsyncMock(
            side_effect=RuntimeError("All connection attempts failed")
        )
        mock_mcp_client.__aexit__ = AsyncMock(side_effect=RuntimeError("disconnect failed"))

        with (
            patch("app.clients.rag_mcp_client.TracedHttpClient", return_value=mock_http_client),
            patch("app.clients.rag_mcp_client.StreamableHttpTransport"),
            patch("app.clients.rag_mcp_client.Client", return_value=mock_mcp_client),
        ):
            client = RAGMCPClient("http://rag-service:8001")

            with pytest.raises(RuntimeError, match="All connection attempts failed"):
                await client.connect()

        mock_http_client.__aenter__.assert_called_once()
        mock_mcp_client.__aenter__.assert_called_once()
        mock_mcp_client.__aexit__.assert_called_once_with(None, None, None)
        mock_http_client.__aexit__.assert_called_once_with(None, None, None)
        assert client.mcp_client is None
        assert client.http_client is None

    @pytest.mark.asyncio
    async def test_close_swallows_mcp_disconnect_errors(self) -> None:
        client = RAGMCPClient("http://rag-service:8001")

        mock_http_client = AsyncMock()
        mock_http_client.__aexit__ = AsyncMock()

        mock_mcp_client = AsyncMock()
        mock_mcp_client.__aexit__ = AsyncMock(side_effect=RuntimeError("disconnect failed"))

        client.http_client = mock_http_client
        client.mcp_client = mock_mcp_client

        await client.close()

        mock_mcp_client.__aexit__.assert_called_once_with(None, None, None)
        mock_http_client.__aexit__.assert_called_once_with(None, None, None)
        assert client.mcp_client is None
        assert client.http_client is None
