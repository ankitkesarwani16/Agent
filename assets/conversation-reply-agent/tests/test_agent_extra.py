"""Additional coverage tests for agent.py edge cases."""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch


def test_check_escalation_true():
    from agent import SampleAgent
    agent = SampleAgent()
    assert agent._check_escalation("I want to sue your company") is True
    assert agent._check_escalation("This is a legal matter") is True
    assert agent._check_escalation("I need a refund") is True
    assert agent._check_escalation("There is fraud in my account") is True


def test_check_escalation_false():
    from agent import SampleAgent
    agent = SampleAgent()
    assert agent._check_escalation("When does my order arrive?") is False
    assert agent._check_escalation("Tell me about product warranties") is False


def test_touch_evicts_expired_thread():
    """_touch should evict threads inactive beyond THREAD_TTL_SECONDS."""
    from agent import SampleAgent, THREAD_TTL_SECONDS
    agent = SampleAgent()

    # Manually insert an "expired" thread
    agent._last_active["old-thread"] = time.monotonic() - THREAD_TTL_SECONDS - 1

    # Mock checkpointer
    agent._checkpointer.delete_thread = MagicMock()

    agent._touch("new-thread")

    agent._checkpointer.delete_thread.assert_called_once_with("old-thread")
    assert "old-thread" not in agent._last_active
    assert "new-thread" in agent._last_active


@pytest.mark.asyncio
async def test_invoke_returns_input_required_status():
    """invoke() should return AgentResponse with status=input_required when agent needs input."""
    from agent import SampleAgent

    agent = SampleAgent()

    # Override stream to yield require_user_input=True
    async def fake_stream(query, ctx, tools=None):
        yield {"is_task_complete": False, "require_user_input": True, "content": "Please clarify your request."}

    with patch.object(agent, "stream", fake_stream):
        response = await agent.invoke("unclear message", "ctx-inv-001")

    assert response.status == "input_required"
    assert "clarify" in response.message.lower()


@pytest.mark.asyncio
async def test_invoke_returns_error_on_empty_stream():
    """invoke() should return error status if stream yields nothing useful."""
    from agent import SampleAgent

    agent = SampleAgent()

    # Override stream to yield a non-complete, non-input-required chunk
    async def fake_stream(query, ctx, tools=None):
        yield {"is_task_complete": False, "require_user_input": False, "content": "Working..."}

    with patch.object(agent, "stream", fake_stream):
        response = await agent.invoke("anything", "ctx-inv-002")

    assert response.status == "error"
