"""Tests for util.py helper functions and mcp_tools.py mock loading."""
import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# --- util.py tests ---

def test_enhance_tool_description_with_none():
    from util import enhance_tool_description
    result = enhance_tool_description(None)
    assert result == ""


def test_enhance_tool_description_with_valid_tool():
    from util import enhance_tool_description

    mock_tool = MagicMock()
    mock_tool.fragment_name = None
    mock_tool.server_name = "test_server"
    mock_tool.description = "Get items"

    result = enhance_tool_description(mock_tool)
    assert "test_server" in result or "Get items" in result


def test_enhance_tool_name_basic():
    from util import enhance_tool_name

    mock_tool = MagicMock()
    mock_tool.name = "get_items"
    mock_tool.server_name = "my_server"

    result = enhance_tool_name(mock_tool)
    assert isinstance(result, str)
    assert len(result) > 0


def test_is_retryable_error_generic():
    import httpx
    from util import _is_retryable_error

    # Generic exceptions are retryable
    assert _is_retryable_error(ValueError("test")) is True
    assert _is_retryable_error(RuntimeError("test")) is True


def test_is_retryable_error_http_4xx():
    import httpx
    from util import _is_retryable_error

    response = MagicMock()
    response.status_code = 400
    err = httpx.HTTPStatusError("bad request", request=MagicMock(), response=response)
    assert _is_retryable_error(err) is False


def test_is_retryable_error_http_5xx():
    import httpx
    from util import _is_retryable_error

    response = MagicMock()
    response.status_code = 500
    err = httpx.HTTPStatusError("server error", request=MagicMock(), response=response)
    assert _is_retryable_error(err) is True


# --- mcp_tools.py tests ---

def test_build_mock_tools_loads_mcp_mock_json():
    """_build_mock_tools should load tools from mcp-mock.json in IBD_TESTING mode."""
    from mcp_tools import _build_mock_tools

    tools = _build_mock_tools()
    assert isinstance(tools, list)
    # Should have tools for both Conversation Service and Grounding Service
    assert len(tools) > 0


def test_build_mock_tools_returns_structured_tools():
    """All mock tools should be LangChain StructuredTool instances."""
    from mcp_tools import _build_mock_tools
    from langchain_core.tools import StructuredTool

    tools = _build_mock_tools()
    for tool in tools:
        assert isinstance(tool, StructuredTool), f"{tool} is not a StructuredTool"


def test_build_mock_tools_missing_file(tmp_path, monkeypatch):
    """_build_mock_tools should return [] when mcp-mock.json is absent."""
    import mcp_tools as mt

    original = mt._MOCK_FILE
    monkeypatch.setattr(mt, "_MOCK_FILE", tmp_path / "nonexistent.json")
    result = mt._build_mock_tools()
    monkeypatch.setattr(mt, "_MOCK_FILE", original)
    assert result == []


def test_build_mock_tools_invalid_json(tmp_path, monkeypatch):
    """_build_mock_tools should return [] when mcp-mock.json is invalid JSON."""
    import mcp_tools as mt

    bad_file = tmp_path / "mcp-mock.json"
    bad_file.write_text("NOT_VALID_JSON")

    original = mt._MOCK_FILE
    monkeypatch.setattr(mt, "_MOCK_FILE", bad_file)
    result = mt._build_mock_tools()
    monkeypatch.setattr(mt, "_MOCK_FILE", original)
    assert result == []


@pytest.mark.asyncio
async def test_get_mcp_tools_in_ibd_testing_mode():
    """get_mcp_tools() should return mock tools when IBD_TESTING=1."""
    assert os.environ.get("IBD_TESTING") == "1", "IBD_TESTING must be set by conftest.py"

    from mcp_tools import get_mcp_tools

    tools = await get_mcp_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0


@pytest.mark.asyncio
async def test_get_mcp_tools_returns_cached_result():
    """Subsequent calls should return cached tools (same list object or same contents)."""
    from mcp_tools import get_mcp_tools

    tools1 = await get_mcp_tools(use_cache=True)
    tools2 = await get_mcp_tools(use_cache=True)
    assert len(tools1) == len(tools2)


@pytest.mark.asyncio
async def test_mock_tool_returns_mock_response():
    """Calling a mock tool should return the mock_response from mcp-mock.json."""
    from mcp_tools import _build_mock_tools

    tools = _build_mock_tools()
    assert len(tools) > 0

    # Find the createSession tool
    create_session = next((t for t in tools if "createSession" in t.name or "POST_createSession" in t.name), None)
    assert create_session is not None, "POST_createSession tool not found in mock tools"

    result = await create_session.ainvoke({})
    assert "sess-mock" in str(result) or "sessionId" in str(result)


def test_convert_mcp_tool_none_raises():
    """_convert_mcp_tool_to_langchain should raise ValueError for None input."""
    from mcp_tools import _convert_mcp_tool_to_langchain
    with pytest.raises(ValueError, match="cannot be None"):
        _convert_mcp_tool_to_langchain(None, MagicMock())


def test_convert_mcp_tool_valid():
    """_convert_mcp_tool_to_langchain should return a StructuredTool."""
    from mcp_tools import _convert_mcp_tool_to_langchain
    from langchain_core.tools import StructuredTool

    mock_tool = MagicMock()
    mock_tool.name = "get_items"
    mock_tool.server_name = "test_server"
    mock_tool.fragment_name = None
    mock_tool.description = "Gets items"
    mock_tool.input_schema = {
        "properties": {
            "count": {"type": "integer", "description": "Count"},
            "ratio": {"type": "number"},
            "active": {"type": "boolean"},
            "name": {"type": "string"},
        },
        "required": ["count"]
    }

    agw_client = MagicMock()
    tool = _convert_mcp_tool_to_langchain(mock_tool, agw_client)
    assert isinstance(tool, StructuredTool)


@pytest.mark.asyncio
async def test_get_mcp_tools_production_path_mocked(monkeypatch):
    """get_mcp_tools() production path should use Agent Gateway and cache results."""
    import mcp_tools as mt
    import os

    # Temporarily unset IBD_TESTING to exercise the production path
    original_val = os.environ.pop("IBD_TESTING", None)

    try:
        # Clear cache
        mt._tool_cache = None

        mock_mcp_tool = MagicMock()
        mock_mcp_tool.name = "test_tool"
        mock_mcp_tool.server_name = "test_server"
        mock_mcp_tool.fragment_name = None
        mock_mcp_tool.description = "Test tool"
        mock_mcp_tool.input_schema = {"properties": {}, "required": []}

        mock_client = AsyncMock()
        mock_client.list_mcp_tools.return_value = [mock_mcp_tool]

        from langchain_core.tools import StructuredTool

        with patch("mcp_tools.create_client", return_value=mock_client):
            with patch("mcp_tools._convert_mcp_tool_to_langchain") as mock_convert:
                mock_convert.return_value = StructuredTool.from_function(
                    func=lambda: "result",
                    name="test_tool",
                    description="Test",
                )
                tools = await mt.get_mcp_tools(use_cache=True)

        assert len(tools) == 1
        # Second call should return from cache
        tools2 = await mt.get_mcp_tools(use_cache=True)
        assert len(tools2) == 1
    finally:
        if original_val is not None:
            os.environ["IBD_TESTING"] = original_val
        mt._tool_cache = None


@pytest.mark.asyncio
async def test_get_mcp_tools_production_path_empty(monkeypatch):
    """get_mcp_tools() should return [] when Agent Gateway returns no tools."""
    import mcp_tools as mt
    import os

    original_val = os.environ.pop("IBD_TESTING", None)

    try:
        mt._tool_cache = None

        mock_client = AsyncMock()
        mock_client.list_mcp_tools.return_value = []

        with patch("mcp_tools.create_client", return_value=mock_client):
            tools = await mt.get_mcp_tools(use_cache=False)

        assert tools == []
    finally:
        if original_val is not None:
            os.environ["IBD_TESTING"] = original_val
        mt._tool_cache = None


@pytest.mark.asyncio
async def test_get_mcp_tools_production_path_exception(monkeypatch):
    """get_mcp_tools() should return [] when Agent Gateway raises an exception."""
    import mcp_tools as mt
    import os

    original_val = os.environ.pop("IBD_TESTING", None)

    try:
        mt._tool_cache = None

        with patch("mcp_tools.create_client", side_effect=RuntimeError("AGW unavailable")):
            tools = await mt.get_mcp_tools(use_cache=False)

        assert tools == []
    finally:
        if original_val is not None:
            os.environ["IBD_TESTING"] = original_val
        mt._tool_cache = None


@pytest.mark.asyncio
async def test_get_mcp_tools_stale_cache_on_failure(monkeypatch):
    """get_mcp_tools() should return stale cache when AGW fails and cache exists."""
    import mcp_tools as mt
    import time
    import os
    from langchain_core.tools import StructuredTool

    original_val = os.environ.pop("IBD_TESTING", None)

    try:
        # Pre-populate cache with stale data
        stale_tool = StructuredTool.from_function(func=lambda: "stale", name="stale_tool", description="Stale")
        mt._tool_cache = ([stale_tool], time.time() - 1000)  # Expired cache

        with patch("mcp_tools.create_client", side_effect=RuntimeError("AGW down")):
            tools = await mt.get_mcp_tools(use_cache=True)

        assert len(tools) == 1
        assert tools[0].name == "stale_tool"
    finally:
        if original_val is not None:
            os.environ["IBD_TESTING"] = original_val
        mt._tool_cache = None


def test_build_mock_tools_integer_field(tmp_path, monkeypatch):
    """_build_mock_tools should handle integer-typed fields."""
    import mcp_tools as mt

    mock_file = tmp_path / "mcp-mock.json"
    mock_file.write_text(json.dumps({
        "servers": {
            "test-server": {
                "mcp_server_name": "test/server",
                "description": "Test",
                "tools": {
                    "get_items": {
                        "description": "Get items",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "count": {"type": "integer", "description": "Count"},
                                "ratio": {"type": "number", "description": "Ratio"},
                                "active": {"type": "boolean", "description": "Active"},
                                "name": {"type": "string", "description": "Name"},
                            },
                            "required": ["count"]
                        },
                        "mock_response": {"results": [{"count": 1}]}
                    }
                }
            }
        },
        "metadata": {"version": "1.0.0"}
    }))

    original = mt._MOCK_FILE
    monkeypatch.setattr(mt, "_MOCK_FILE", mock_file)
    tools = mt._build_mock_tools()
    monkeypatch.setattr(mt, "_MOCK_FILE", original)
    assert len(tools) == 1
