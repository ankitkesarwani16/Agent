"""Unit test for intent analysis (M2)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_m2_achieved_for_normal_message():
    """M2 should be logged when intent is understood."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content="Intent understood reply.")]
        }
        mock_create.return_value = mock_graph

        with patch("agent.logger") as mock_logger:
            result = await agent._run_agent("What is the delivery time?", "ctx-010")

    log_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("M2.achieved" in c for c in log_calls)
    assert result == "Intent understood reply."


@pytest.mark.asyncio
async def test_m2_missed_for_escalation_keyword():
    """M2 should be marked missed when escalation keyword is detected."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.logger") as mock_logger:
        result = await agent._run_agent("I want to file a legal complaint", "ctx-011")

    warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
    assert any("M2.missed" in c for c in warning_calls), "M2.missed not logged for escalation"
    assert "human review" in result.lower()


@pytest.mark.asyncio
async def test_escalation_keywords_detected():
    """All escalation keywords should trigger escalation."""
    from agent import SampleAgent

    agent = SampleAgent()
    keywords = ["complaint", "legal", "lawsuit", "refund", "financial", "sue", "fraud"]

    for kw in keywords:
        result = await agent._run_agent(f"I have a {kw} issue", f"ctx-kw-{kw}")
        assert "human review" in result.lower(), f"Keyword '{kw}' did not trigger escalation"
