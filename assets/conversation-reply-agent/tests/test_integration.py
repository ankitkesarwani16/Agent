"""Integration test: end-to-end agent flow with real LLM (mocked)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_end_to_end_normal_conversation():
    """Full agent flow: normal message → intent → context → reply → deliver."""
    from agent import SampleAgent

    agent = SampleAgent()

    expected_reply = (
        "Thank you for reaching out! Your order is on its way and should arrive "
        "within 3-5 business days. You can track it using the link in your confirmation email."
    )

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content=expected_reply)]
        }
        mock_create.return_value = mock_graph

        with patch("agent.logger") as mock_logger:
            response = await agent.invoke(
                "I ordered a product 4 days ago. When will it arrive?",
                "ctx-integration-001",
            )

    # Full milestone chain must have fired
    info_calls = [str(c) for c in mock_logger.info.call_args_list]
    assert any("M1.achieved" in c for c in info_calls), "M1.achieved missing"
    assert any("M2.achieved" in c for c in info_calls), "M2.achieved missing"
    assert any("M3.achieved" in c for c in info_calls), "M3.achieved missing"
    assert any("M4.achieved" in c for c in info_calls), "M4.achieved missing"
    assert any("M5.achieved" in c for c in info_calls), "M5.achieved missing"

    assert response.status == "completed"
    assert response.message == expected_reply


@pytest.mark.asyncio
async def test_end_to_end_escalation_flow():
    """Full agent flow: escalation keyword → human review flag — no LLM call."""
    from agent import SampleAgent

    agent = SampleAgent()

    with patch("agent.create_agent") as mock_create:
        with patch("agent.logger") as mock_logger:
            response = await agent.invoke(
                "I want to sue your company for this defective product!",
                "ctx-integration-002",
            )

    # LLM graph should not be invoked
    mock_create.assert_not_called()

    warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
    assert any("M2.missed" in c for c in warning_calls)

    assert response.status == "completed"
    assert "human review" in response.message.lower()


@pytest.mark.asyncio
async def test_end_to_end_with_mcp_tools():
    """Full agent flow with MCP tools wired in."""
    from agent import SampleAgent
    from langchain_core.tools import StructuredTool

    agent = SampleAgent()

    mock_tool = StructuredTool.from_function(
        func=lambda query: {"results": [{"content": "Product warranty is 2 years."}]},
        name="POST_PdfFiles",
        description="Search knowledge base",
    )

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "messages": [MagicMock(content="The product warranty covers 2 years from purchase.")]
        }
        mock_create.return_value = mock_graph

        response = await agent.invoke(
            "What is the warranty period for my product?",
            "ctx-integration-003",
            tools=[mock_tool],
        )

    assert response.status == "completed"
    assert "warranty" in response.message.lower()
