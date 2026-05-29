# Specification: conversation-reply-agent

> **Guidelines**: Read [guidelines.md](../guidelines.md) and [guidelines-agent.md](../guidelines-agent.md) before executing ANY tasks below. Follow all constraints described there throughout execution.

## Basic Setup

- [x] Read the project input (`product-requirements-document.md`, `intent.md`)
- [x] Bootstrap agent code in `assets/conversation-reply-agent/` using skill `sap-agent-bootstrap` (invoke from inside `assets/conversation-reply-agent/`, use copy commands — do NOT create files manually)
- [x] Install dependencies, validate the agent starts and responds at `/.well-known/agent.json`

## Conversation Ingestion (R1)

- [ ] Implement `ingest_conversation` tool: calls `POST /createSession` on Conversation Service API via MCP to open a session, then calls `POST /askAgent` to retrieve the incoming message content
- [ ] Tool must return: session ID, message text, and any metadata (language, timestamp)
- [ ] Handle session errors gracefully — log `M1.missed: failed to retrieve conversation from Conversation Service` on failure

## Intent & Context Analysis (R2)

- [ ] Implement `analyze_intent` tool: uses LLM on SAP AI Core to classify the message topic, intent, and sentiment
- [ ] Return structured output: `{ intent, topic, sentiment, confidence }`
- [ ] If confidence < threshold (0.7), flag for human review; log `M2.missed: intent classification did not complete`
- [ ] On success log `M2.achieved: intent classified successfully`

## Knowledge Grounding (R3)

- [ ] Implement `retrieve_context` tool: calls Grounding Service `POST /PdfFiles` (or equivalent search endpoint) via MCP to retrieve relevant knowledge chunks matching the identified intent
- [ ] Pass top-3 most relevant chunks to reply generation context
- [ ] Log `M3.achieved: grounding context retrieved` on success; `M3.missed: grounding service returned no context` on failure

## Reply Generation (R4)

- [ ] Implement `generate_reply` tool: constructs an LLM prompt combining original message + grounding context + conversation history; invokes SAP AI Core LLM to produce a reply
- [ ] System prompt must instruct the LLM: (1) do not hallucinate; (2) limit tool calls with `top` to max 100; (3) stay on topic; (4) escalate if unsure
- [ ] Log `M4.achieved: reply generated successfully` on non-empty response; `M4.missed: LLM call failed or returned empty response` on failure

## Reply Delivery (R5)

- [ ] Implement `deliver_reply` tool: calls `POST /askAgent` or session continuation on Conversation Service via MCP to send the generated reply back to the originating session
- [ ] Log `M5.achieved: reply delivered to channel` on success; `M5.missed: reply delivery to channel failed` on failure
- [ ] Implement graceful close: call `POST /stopSession` after delivery

## Agent Orchestration

- [ ] Wire all 5 tools into the agent graph in `app/agent.py` using `get_mcp_tools()` from `mcp_tools.py`
- [ ] Agent system prompt must describe the full flow: ingest → analyse → ground → generate → deliver
- [ ] Add guardrails to system prompt: escalate messages with low confidence, complaints, legal, or financial keywords to human review; send generic acknowledgment if LLM fails
- [ ] Implement confidence threshold check between M2 and M3; if below threshold, skip generation and flag conversation

## Business Step Instrumentation

- [ ] Implement milestone logging for all 5 milestones (M1–M5) with pattern `[MILESTONE_ID].[achieved|missed]: [description]`
- [ ] Add OpenTelemetry spans using `@tracer.start_as_current_span` decorator on each tool method
- [ ] Extract all business logic from `stream()` into `_run_agent()` helper; instrument `_run_agent()` — never wrap `yield` in a span context
- [ ] Verify `auto_instrument()` is called at top of `main.py` before any AI framework imports

## API Integration & MCP

- [ ] API spec files are in `specification/conversation-reply-agent/api-specs/`:
  - `conversation-service.json` — ORD ID: `sap.s4.util:apiResource:Conversation:v1`
    - Key endpoints: `POST /createSession`, `POST /askAgent`, `POST /stopSession`
  - `grounding-service.json` — ORD ID: `sap.s4.util:apiResource:GroundingService:v1`
    - Key endpoints: `POST /PdfFiles` (knowledge search), `PUT /PdfFiles(name,category)` (upload)
- [ ] Invoke `mcp-translation-file` skill to generate MCP translation files from both API specs
- [ ] Invoke `setup-solution` skill to create MCP server assets for each translation file
- [ ] Add MCP server dependencies to `assets/conversation-reply-agent/asset.yaml` under `requires`
- [ ] Invoke `mcp-mock-config` skill to generate `mcp-mock.json` (must be after mcp-translation-file + setup-solution)

## Testing

- [ ] `conftest.py` only sets `IBD_TESTING=true` — agent runs with mock MCP tool results during tests
- [ ] Write unit tests in `assets/conversation-reply-agent/tests/`:
  - [ ] `test_ingest_conversation.py` — mock Conversation Service; verify session creation and message retrieval
  - [ ] `test_analyze_intent.py` — mock LLM; verify intent classification output structure
  - [ ] `test_retrieve_context.py` — mock Grounding Service; verify context chunk retrieval
  - [ ] `test_generate_reply.py` — mock LLM; verify non-empty reply is returned
  - [ ] `test_deliver_reply.py` — mock Conversation Service; verify reply delivery and session close
- [ ] Write one integration test: end-to-end agent flow with real LLM (mock external APIs only)
- [ ] Run `pytest` from `assets/conversation-reply-agent/` (no args); if coverage < 70% add tests
- [ ] Verify `grep -c "^@agent_model\|^@agent_config\|^@prompt_section" assets/conversation-reply-agent/app/agent.py` returns exactly 3
- [ ] Run `pytest` again to generate final `test_report.json`
- [ ] Verify `test_report.json` exists in `assets/conversation-reply-agent/`

## Agent Evaluation

- [ ] Invoke `sap-aeval-framework` skill from `assets/conversation-reply-agent/` to generate `tools.json`
- [ ] Invoke `sap-aeval-generate-testcase` skill with `product-requirements-document.md` and `tools.json`; review and replace placeholder values before running evals
