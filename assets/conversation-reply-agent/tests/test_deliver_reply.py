"""Unit test for reply delivery (M5)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_m5_achieved_after_successful_reply():
    """M5 should be logged when reply is returned to caller for delivery."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content="We have processed your request.")]
        }
        mock_create.return_value = mock_graph

        with patch("agent.logger") as mock_logger:
            result = await agent._run_agent("Has my ticket been resolved?", "ctx-040")

    log_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("M5.achieved" in c for c in log_calls)
    assert result == "We have processed your request."


@pytest.mark.asyncio
async def test_stream_yields_complete_status():
    """stream() should yield is_task_complete=True after successful run."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch.object(agent, "_run_agent", new=AsyncMock(return_value="Streamed reply.")):
        chunks = []
        async for chunk in agent.stream("Hello", "ctx-041"):
            chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0]["is_task_complete"] is False
    assert chunks[1]["is_task_complete"] is True
    assert chunks[1]["content"] == "Streamed reply."


@pytest.mark.asyncio
async def test_invoke_returns_completed_status():
    """invoke() should return AgentResponse with status=completed."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch.object(agent, "_run_agent", new=AsyncMock(return_value="Final answer.")):
        response = await agent.invoke("Summarise my conversation", "ctx-042")

    assert response.status == "completed"
    assert response.message == "Final answer."
