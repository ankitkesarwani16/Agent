"""Unit test for reply generation (M4)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_m4_achieved_on_valid_llm_response():
    """M4 should be logged when LLM returns a non-empty response."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content="Your order will arrive in 3-5 business days.")]
        }
        mock_create.return_value = mock_graph

        with patch("agent.logger") as mock_logger:
            result = await agent._run_agent("When will my order arrive?", "ctx-030")

    log_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("M4.achieved" in c for c in log_calls)
    assert result == "Your order will arrive in 3-5 business days."


@pytest.mark.asyncio
async def test_m4_missed_on_empty_llm_response():
    """M4 should be missed when LLM returns an empty string."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content="")]
        }
        mock_create.return_value = mock_graph

        with patch("agent.logger") as mock_logger:
            result = await agent._run_agent("How do I track my package?", "ctx-031")

    error_calls = [str(c) for c in mock_logger.error.call_args_list]
    assert any("M4.missed" in c for c in error_calls), "M4.missed not logged on empty response"
    assert "unable to generate" in result.lower()


@pytest.mark.asyncio
async def test_m4_achieved_on_list_content_blocks():
    """M4 should succeed and return plain text when LLM returns a list of content blocks (e.g. Claude)."""
    from agent import SampleAgent

    agent = SampleAgent()

    # Simulate Claude-style structured content response
    content_blocks = [
        {"type": "text", "text": "Thank you for reaching out. "},
        {"type": "text", "text": "Your order will arrive in 3-5 business days."},
    ]

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content=content_blocks)]
        }
        mock_create.return_value = mock_graph

        with patch("agent.logger") as mock_logger:
            result = await agent._run_agent("When will my order arrive?", "ctx-033")

    log_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("M4.achieved" in c for c in log_calls)
    assert isinstance(result, str), "Response must be a plain string, not a list"
    assert "Thank you for reaching out." in result
    assert "3-5 business days" in result


@pytest.mark.asyncio
async def test_m4_missed_on_llm_exception():
    """M4 should be missed when LLM raises an exception."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = RuntimeError("LLM timeout")
        mock_create.return_value = mock_graph

        with patch("agent.logger"):
            result = await agent._run_agent("I need help", "ctx-032")

    assert "error" in result.lower() or "encountered" in result.lower()
