# CRITICAL: Suppress traceloop DeprecationWarning BEFORE any other import.
# traceloop-sdk 0.54.x uses a Pydantic V1-style `class Config` inside a
# BaseModel subclass. Pydantic V2 emits a PydanticDeprecatedSince20 warning
# (a subclass of DeprecationWarning) at class-definition time (import time).
# The deployment container runs with PYTHONWARNINGS=error, which turns that
# warning into an exception and crashes the process before it can start.
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="traceloop.*")

# CRITICAL: Initialize telemetry BEFORE importing AI frameworks
from sap_cloud_sdk.aicore import set_aicore_config
from sap_cloud_sdk.core.telemetry import auto_instrument

set_aicore_config()
auto_instrument()

import logging
import os

import click
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from agent_executor import AgentExecutor
from opentelemetry.instrumentation.starlette import StarletteInstrumentor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))


@click.command()
@click.option("--host", default=HOST)
@click.option("--port", default=PORT)
def main(host: str, port: int):
    skill = AgentSkill(
        id="conversation-reply-agent",
        name="conversation-reply-agent",
        description="An AI agent that reads incoming conversations and generates contextually appropriate, intelligent replies in real time using SAP AI Core.",
        tags=["conversation", "reply", "agent", "customer-service"],
        examples=["Reply to this customer message about a delayed order", "Generate a professional response to this complaint email"],
    )
    agent_card = AgentCard(
        name="conversation-reply-agent",
        description="An AI agent that reads incoming conversations and generates contextually appropriate, intelligent replies in real time using SAP AI Core.",
        url=os.environ.get("AGENT_PUBLIC_URL", f"http://{host}:{port}/"),
        version="1.0.0",
        default_input_modes=["text", "text/plain"],
        default_output_modes=["text", "text/plain"],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        skills=[skill],
    )
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=DefaultRequestHandler(
            agent_executor=AgentExecutor(),
            task_store=InMemoryTaskStore(),
        ),
    )
    app = server.build()
    StarletteInstrumentor().instrument_app(app)

    logger.info(f"Starting A2A server at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
