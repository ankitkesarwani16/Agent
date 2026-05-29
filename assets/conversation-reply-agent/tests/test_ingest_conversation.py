"""Unit test for conversation ingestion (M1)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_m1_achieved_on_normal_input():
    """M1 should be logged when the agent receives a valid query."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content="Thank you for your message.")]
        }
        mock_create.return_value = mock_graph

        with patch("agent.logger") as mock_logger:
            result = await agent._run_agent("Where is my order?", "ctx-001")

    # M1 log should appear
    log_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("M1.achieved" in c for c in log_calls), "M1.achieved not logged"
    assert result == "Thank you for your message."


@pytest.mark.asyncio
async def test_m1_with_tools():
    """M1 should log with tools available."""
    from agent import SampleAgent
    from langchain_core.tools import StructuredTool

    agent = SampleAgent()
    dummy_tool = StructuredTool.from_function(
        func=lambda: "result",
        name="dummy_tool",
        description="A dummy tool",
    )

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content="Reply with tool.")]
        }
        mock_create.return_value = mock_graph

        with patch("agent.logger") as mock_logger:
            result = await agent._run_agent("Hello", "ctx-002", tools=[dummy_tool])

    log_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("M1.achieved" in c for c in log_calls)
    assert result == "Reply with tool."
