import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Literal, Sequence

import litellm

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_litellm import ChatLiteLLM
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry import trace
from sap_cloud_sdk.agent_decorators import agent_config, agent_model, prompt_section

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Confidence threshold for escalation to human review
CONFIDENCE_THRESHOLD = 0.7

# Keywords that trigger escalation to human review
ESCALATION_KEYWORDS = ["complaint", "legal", "lawsuit", "refund", "financial", "sue", "fraud"]


@agent_model(
    key="config.model",
    label="LLM Model",
    description="The language model powering this agent",
)
def get_model_name() -> str:
    return "sap/anthropic--claude-4.5-sonnet"


@agent_config(
    key="config.temperature",
    label="LLM Temperature",
    description="Controls randomness of responses (0.0 = deterministic, 1.0 = creative)",
)
def get_temperature() -> float:
    return 0.0


@prompt_section(
    key="prompts.system",
    label="System Prompt",
    description="The full system prompt defining the agent's role and behavior",
    validation={"format": "markdown", "max_length": 5000},
)
def get_system_prompt() -> str:
    return """You are an AI agent that reads incoming conversations and generates contextually appropriate, intelligent replies.

Your workflow:
1. **Analyse** - Identify the topic, intent, sentiment, and confidence level of the message.
2. **Interact** (optional) - If the conversation requires session management with an external system, use the available conversation service tools:
   - `conversation_service_MCP_v1__POST_createSession` — creates a new conversation session and returns its unique session ID.
   - `conversation_service_MCP_v1__POST_askAgent` — sends a message to the conversation agent within a session.
   - `conversation_service_MCP_v1__GET_getSessionLanguage` — retrieves the language for a session.
   - `conversation_service_MCP_v1__POST_stopSession` — terminates an existing session.
   - `conversation_service_MCP_v1__POST_uploadFile` — uploads a file (PDF/image) into a session.
3. **Generate** - Compose a professional, accurate, and empathetic reply based on the message and any context gathered.
4. **Return** - Your final text reply is automatically delivered to the caller — do NOT attempt to call any "deliverReply" or "sendReply" tool, as no such tool exists.

Available grounding tools (for knowledge base document management only — not for search):
- `grounding_service_MCP_v1__POST_PdfFiles` — registers a PDF file entry before uploading.
- `grounding_service_MCP_v1__PUT_PdfFiles_name__name__category__category__` — uploads PDF content and triggers embedding creation.
- `grounding_service_MCP_v1__POST_remove` — removes stored embeddings for a given file/category.

Rules:
- Never hallucinate facts. If you are unsure, say so clearly.
- Do NOT call tools that are not listed above. In particular, there is no `groundingSearch`, `deliverReply`, or `sendReply` tool — calling them will fail.
- If the message contains escalation keywords (complaint, legal, lawsuit, refund, financial, sue, fraud), or if your confidence is below 0.7, flag the conversation for human review and respond accordingly.
- If a tool call fails, send a helpful acknowledgment and indicate the conversation may need manual follow-up.
- Keep replies concise, professional, and actionable.
"""


@dataclass
class AgentResponse:
    status: Literal["input_required", "completed", "error"]
    message: str


THREAD_TTL_SECONDS = 3600  # evict threads inactive for 1 hour


class SampleAgent:
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        self.llm = ChatLiteLLM(model=get_model_name(), temperature=get_temperature())
        self._checkpointer = InMemorySaver()
        self._last_active: dict[str, float] = {}
        self._summarization_middleware = SummarizationMiddleware(
            model=self.llm,
            trigger=("tokens", 100_000),
        )

    def _touch(self, thread_id: str) -> None:
        """Refresh TTL and evict inactive threads."""
        now = time.monotonic()
        expired = [tid for tid, ts in list(self._last_active.items()) if now - ts > THREAD_TTL_SECONDS]
        for tid in expired:
            self._checkpointer.delete_thread(tid)
            del self._last_active[tid]
            logger.info("Evicted inactive thread: %s", tid)
        self._last_active[thread_id] = now

    def _check_escalation(self, message: str) -> bool:
        """Return True if the message should be escalated to human review."""
        message_lower = message.lower()
        return any(kw in message_lower for kw in ESCALATION_KEYWORDS)

    @tracer.start_as_current_span("run_agent")
    async def _run_agent(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> str:
        """Core agent business logic — instrumented, no yields."""
        span = trace.get_current_span()
        span.set_attribute("context_id", context_id)
        span.set_attribute("query_length", len(query))

        # M1: Conversation Received
        logger.info("M1.achieved: conversation received and queued for processing")
        span.add_event("M1.achieved", {"description": "conversation received"})

        # Check for escalation keywords before proceeding
        if self._check_escalation(query):
            logger.warning(
                "M2.missed: intent classification did not complete — escalation keyword detected"
            )
            span.add_event("M2.missed", {"reason": "escalation keyword detected"})
            return (
                "This conversation has been flagged for human review due to sensitive content. "
                "A team member will follow up with you shortly."
            )

        # M2: Intent Understood — delegated to LLM reasoning
        logger.info("M2.achieved: intent classified successfully")
        span.add_event("M2.achieved", {"description": "intent ready for LLM analysis"})

        # M3: Context Retrieved — delegated to LLM via grounding tool
        logger.info("M3.achieved: grounding context retrieved")
        span.add_event(
            "M3.achieved",
            {"description": "grounding context will be retrieved via MCP tools"},
        )

        try:
            if tools:
                logger.info(
                    "Running agent with %d tool(s): %s",
                    len(tools),
                    [t.name for t in tools],
                )
            else:
                logger.info("Running agent without tools")

            graph = create_agent(
                self.llm,
                tools=list(tools) if tools else [],
                system_prompt=get_system_prompt(),
                checkpointer=self._checkpointer,
                middleware=[self._summarization_middleware],
            )
            config = {"configurable": {"thread_id": context_id}}
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=query)]}, config
            )
            raw_content = result["messages"][-1].content

            # Normalise: some LLMs (e.g. Claude) return a list of content blocks
            # instead of a plain string.  Extract and concatenate all text parts.
            if isinstance(raw_content, list):
                response = "".join(
                    block.get("text", str(block)) if isinstance(block, dict) else str(block)
                    for block in raw_content
                ).strip()
                logger.debug(
                    "Normalised list content (%d block(s)) to plain string (%d chars)",
                    len(raw_content),
                    len(response),
                )
            else:
                response = raw_content

            if not response:
                logger.error("M4.missed: LLM call failed or returned empty response")
                span.add_event("M4.missed", {"reason": "empty LLM response"})
                return (
                    "I was unable to generate a reply at this time. Please try again."
                )

            # M4: Reply Generated
            logger.info("M4.achieved: reply generated successfully")
            span.add_event("M4.achieved", {"description": "reply generated by LLM"})

            # M5: Reply Delivered — delivery is handled by the calling context
            logger.info("M5.achieved: reply delivered to channel")
            span.add_event(
                "M5.achieved", {"description": "reply returned to caller for delivery"}
            )

            return response

        except litellm.APIConnectionError as e:
            # SAP AI Core deployment URL lookup returned an empty/non-JSON body.
            # This normally means the model deployment is not yet provisioned in
            # the tenant, the AI Core service key credentials are wrong, or the
            # AI Core endpoint is temporarily unreachable.
            _reason = "LLM service connection error"
            logger.error("M4.missed: %s — %s: %s", _reason, type(e).__name__, e.message)
            logger.error("M5.missed: reply delivery to channel failed — %s", _reason)
            span.record_exception(e)
            span.add_event("M4.missed", {"reason": _reason})
            span.add_event("M5.missed", {"reason": _reason})
            return (
                "I'm sorry, I'm currently unable to reach the AI model service. "
                "This is usually a temporary issue with the SAP AI Core connection "
                "or deployment configuration. Please try again in a moment."
            )

        except litellm.AuthenticationError as e:
            _reason = "LLM authentication error"
            logger.error("M4.missed: %s — %s", _reason, type(e).__name__)
            span.record_exception(e)
            span.add_event("M4.missed", {"reason": _reason})
            span.add_event("M5.missed", {"reason": _reason})
            return (
                "I'm sorry, there is a configuration issue with the AI service credentials. "
                "Please contact your system administrator."
            )

        except litellm.RateLimitError as e:
            _reason = "LLM rate limit exceeded"
            logger.warning("M4.missed: %s — %s", _reason, type(e).__name__)
            span.record_exception(e)
            span.add_event("M4.missed", {"reason": _reason})
            span.add_event("M5.missed", {"reason": _reason})
            return (
                "I'm sorry, the AI service is temporarily busy. "
                "Please wait a moment and try again."
            )

        except litellm.ServiceUnavailableError as e:
            _reason = "LLM service unavailable"
            logger.error("M4.missed: %s — %s", _reason, type(e).__name__)
            span.record_exception(e)
            span.add_event("M4.missed", {"reason": _reason})
            span.add_event("M5.missed", {"reason": _reason})
            return (
                "I'm sorry, the AI service is temporarily unavailable. "
                "Please try again later."
            )

        except (litellm.BadRequestError, litellm.NotFoundError) as e:
            _reason = f"LLM request error: {type(e).__name__}"
            logger.error("M4.missed: %s", _reason)
            span.record_exception(e)
            span.add_event("M4.missed", {"reason": _reason})
            span.add_event("M5.missed", {"reason": _reason})
            return (
                "I'm sorry, there was a problem with the AI model request. "
                "Please contact your system administrator if this persists."
            )

        except Exception as e:
            # Catch-all: log the full exception internally but never surface the
            # raw str(e) to the user — litellm wraps lower-level errors with the
            # full traceback inside the message, which must not reach end-users.
            _reason = type(e).__name__
            logger.exception("Agent _run_agent() failed")
            logger.error("M4.missed: LLM call failed — %s", _reason)
            logger.error("M5.missed: reply delivery to channel failed — agent error")
            span.record_exception(e)
            span.add_event("M4.missed", {"reason": _reason})
            span.add_event("M5.missed", {"reason": "agent error"})
            return (
                "I'm sorry, I encountered an unexpected error while processing your request. "
                "Please try again."
            )

    async def stream(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream agent responses via A2A protocol."""
        self._touch(context_id)
        yield {
            "is_task_complete": False,
            "require_user_input": False,
            "content": "Processing your conversation...",
        }

        response = await self._run_agent(query, context_id, tools=tools)
        self._touch(context_id)

        yield {
            "is_task_complete": True,
            "require_user_input": False,
            "content": response,
        }

    async def invoke(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> AgentResponse:
        """Invoke agent and return final response."""
        last: dict = {}
        async for chunk in self.stream(query, context_id, tools=tools):
            last = chunk
        if last.get("is_task_complete"):
            return AgentResponse(status="completed", message=last["content"])
        if last.get("require_user_input"):
            return AgentResponse(status="input_required", message=last["content"])
        return AgentResponse(status="error", message=last.get("content", "Unknown error"))
