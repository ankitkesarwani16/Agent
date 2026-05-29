"""Unit test for knowledge grounding (M3)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_m3_achieved_on_successful_run():
    """M3 should be logged after intent analysis succeeds."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content="Context retrieved and used.")]
        }
        mock_create.return_value = mock_graph

        with patch("agent.logger") as mock_logger:
            result = await agent._run_agent("Tell me about product warranties", "ctx-020")

    log_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("M3.achieved" in c for c in log_calls)
    assert result == "Context retrieved and used."


@pytest.mark.asyncio
async def test_m3_skipped_for_escalation():
    """M3 should not be reached when message is escalated at M2."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.logger") as mock_logger:
        result = await agent._run_agent("I need a refund immediately", "ctx-021")

    info_calls = [str(c) for c in mock_logger.info.call_args_list]
    # M3 should NOT be in the info logs
    assert not any("M3.achieved" in c for c in info_calls), "M3 should not log for escalated messages"
    assert "human review" in result.lower()
