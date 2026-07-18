# Streaming Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver true Ollama token streaming with cancellation, persisted generation states, developer-only retrieval diagnostics, and one grounding-repair pass.

**Architecture:** Split RAG into preparation, streamed generation, and validation phases. Persist a placeholder assistant message before generation, communicate lifecycle changes through structured SSE, and reconcile the frontend store using stable server IDs.

**Tech Stack:** FastAPI, SQLModel, PostgreSQL/Alembic, httpx/Ollama, Next.js, TypeScript, Zustand, Vitest, Playwright, Docker Compose.

## Global Constraints

- Keep partial output after cancellation and save the assistant message as `cancelled`.
- Retry must reuse the existing user turn and must not create duplicate messages.
- Retrieval diagnostics are available only when enabled in Settings.
- Grounded answers receive at most one automatic repair attempt.
- Keep the current Ollama models and hybrid retrieval behavior.
- Use structured JSON SSE over the existing POST streaming route.

---

### Task 1: Persisted Generation Lifecycle

**Files:**
- Modify: `backend/app/models/chat.py`
- Modify: `backend/app/schemas/chat.py`
- Create: `backend/alembic/versions/0004_streaming_chat_add_generation_lifecycle.py`
- Test: `backend/tests/test_chat_source_schema.py`
- Test: `backend/tests/test_migration_bootstrap.py`

**Interfaces:**
- Produces: `ChatGenerationStatus`, generation fields on `ChatMessages`, and serialized status/metadata fields on `ChatMessageResponse`.

- [ ] Write failing model/schema tests proving assistant status, error, metadata, and timestamps serialize while ordinary user messages remain statusless.
- [ ] Run `docker compose exec backend pytest -q tests/test_chat_source_schema.py tests/test_migration_bootstrap.py` and confirm the new assertions fail.
- [ ] Add `ChatGenerationStatus(StrEnum)` with `streaming`, `completed`, `cancelled`, and `failed`; add nullable `generation_status`, `generation_error`, `generation_metadata` JSONB, `generation_started_at`, and `generation_completed_at` fields.
- [ ] Add migration `0004` with nullable columns and an upgrade data statement setting existing assistant messages to `completed`; implement a complete downgrade.
- [ ] Extend `ChatMessageResponse` and route serialization with the new fields.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Developer Diagnostics Setting

**Files:**
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/schemas/settings.py`
- Modify: `backend/app/api/routes/user.py`
- Modify: `backend/alembic/versions/0004_streaming_chat_add_generation_lifecycle.py`
- Modify: `frontend/types/index.ts`
- Modify: `frontend/lib/api/settings.ts`
- Modify: `frontend/components/features/settings/AIModelSettings.tsx`
- Test: `backend/tests/test_user_ai_settings.py`
- Test: `frontend/components/features/settings/AIModelSettings.test.tsx`

**Interfaces:**
- Produces: `rag_diagnostics_enabled: bool` in user settings GET/PATCH and a Settings toggle.

- [ ] Write failing backend tests for a default-disabled setting and PATCH updates that do not require changing the selected model.
- [ ] Write a failing frontend test proving the toggle reflects and saves the preference.
- [ ] Run both focused suites and confirm expected failures.
- [ ] Extend the settings model, migration, Pydantic response/update schemas, and route with partial-update semantics.
- [ ] Extend frontend types/API and add a labelled developer `Retrieval diagnostics` switch using the existing settings component style.
- [ ] Re-run focused tests and confirm they pass.

### Task 3: Structured SSE Parser

**Files:**
- Rewrite: `frontend/lib/api/stream.ts`
- Create: `frontend/lib/api/__tests__/stream.test.ts`
- Modify: `frontend/config/api.ts`

**Interfaces:**
- Produces: `ChatStreamEvent` discriminated union and `streamChatMessage(sessionId, payload, callbacks)` using credentials and CSRF headers.

- [ ] Write failing Vitest cases for fragmented frames, CRLF, UTF-8 split boundaries, comments, malformed JSON errors, each event type, and a normal EOF.
- [ ] Run `pnpm --dir frontend test -- lib/api/__tests__/stream.test.ts` and confirm failures.
- [ ] Implement a named-event SSE decoder that dispatches typed JSON payloads and uses the configured API base URL, `credentials: "include"`, and the existing CSRF token helper.
- [ ] Re-run the parser tests and confirm they pass.

### Task 4: RAG Preparation And Grounding Validation

**Files:**
- Modify: `backend/app/ai/rag.py`
- Create: `backend/app/ai/grounding.py`
- Modify: `backend/app/ai/llm.py`
- Test: `backend/tests/test_rag_sources.py`
- Create: `backend/tests/test_grounding.py`

**Interfaces:**
- Produces: `PreparedRAGResponse(messages, sources, diagnostics, grounded)`, `prepare_rag_response(...)`, and `validate_grounded_answer(answer, sources, context) -> GroundingValidation`.

- [ ] Write failing tests proving preparation returns the same hybrid sources/prompts as the current pipeline and diagnostics contain no raw document content.
- [ ] Write failing validation tests for valid citations, missing citations, unknown citation IDs, false no-context claims, casual answers, and a strict one-repair decision.
- [ ] Run the focused backend tests and confirm failures.
- [ ] Extract retrieval/prompt construction from `run_rag_pipeline` into `prepare_rag_response` while retaining the synchronous wrapper for existing callers.
- [ ] Implement conservative validation and a repair prompt that lists only valid citation IDs and selected context.
- [ ] Re-run focused tests and confirm they pass.

### Task 5: Streaming Generation Coordinator And Endpoints

**Files:**
- Create: `backend/app/services/chat_generation.py`
- Modify: `backend/app/services/chat_service.py`
- Modify: `backend/app/api/routes/chat.py`
- Modify: `backend/app/schemas/chat.py`
- Test: `backend/tests/test_chat_routes.py`
- Test: `backend/tests/test_chat_service.py`

**Interfaces:**
- Produces: `GenerationCoordinator`, `stream_chat_generation(...)`, `cancel_generation(...)`, and `retry_generation(...)`.
- Consumes: `PreparedRAGResponse` and `LLMService.stream_response()`.

- [ ] Replace the fake-stream test with failing tests that require `generation_started`, multiple `token` events, `sources`, and `completed` in order.
- [ ] Add failing tests for cancelling after a token, retaining partial content, stopping provider iteration, duplicate-generation 409, retry without a duplicate user message, provider errors, and disconnect cleanup.
- [ ] Run focused tests and confirm failures are caused by the missing lifecycle implementation.
- [ ] Implement a process-local coordinator keyed by assistant message ID and guarded by session ID.
- [ ] Refactor the stream route to create both persisted messages first, prepare retrieval, stream Ollama deltas, flush content in bounded intervals, and finalize terminal state.
- [ ] Add owner-checked `POST /chat/sessions/{session_id}/messages/{message_id}/cancel` and `POST /chat/sessions/{session_id}/messages/{message_id}/retry/stream` endpoints.
- [ ] Emit diagnostics only when the persisted user setting is enabled.
- [ ] Validate grounded output and stream one `answer_reset` repair; if repair fails, restore and complete the original draft with unresolved validation metadata.
- [ ] Re-run backend focused tests and confirm they pass.

### Task 6: Frontend Store Cancellation And Retry

**Files:**
- Modify: `frontend/store/chatStore.ts`
- Modify: `frontend/store/chatRequestState.ts`
- Modify: `frontend/lib/hooks/useChat.ts`
- Create: `frontend/store/__tests__/chatStreaming.test.ts`

**Interfaces:**
- Consumes: `ChatStreamEvent`.
- Produces: `cancelMessage(sessionId)`, `retryMessage(sessionId, assistantMessageId)`, active generation state, and deterministic session reconciliation.

- [ ] Write failing store tests for optimistic-to-stable ID replacement, token append, answer reset, terminal replacement, cancel, retry, network refresh, and duplicate suppression.
- [ ] Run the focused Vitest suite and confirm failures.
- [ ] Remove simulated `streamAssistantMessage`; integrate the structured streaming client and one `AbortController` per session.
- [ ] On network interruption, fetch the session once and reconcile instead of resending.
- [ ] Re-run focused tests and confirm they pass.

### Task 7: Chat Controls And Diagnostics UI

**Files:**
- Modify: `frontend/components/features/chat/ChatInput.tsx`
- Modify: `frontend/components/features/chat/ChatMessage.tsx`
- Modify: `frontend/components/features/chat/ChatHistory.tsx`
- Create: `frontend/components/features/chat/RetrievalDiagnostics.tsx`
- Modify: `frontend/app/dashboard/chat/[sessionID]/page.tsx`
- Test: `frontend/components/features/chat/ChatMessage.test.tsx`
- Test: `frontend/components/features/chat/ChatInput.test.tsx`

**Interfaces:**
- Consumes: generation status and diagnostic metadata from `ChatMessageResponse` plus store cancel/retry actions.

- [ ] Write failing component tests for Send-to-Stop transition, cancelled/failed labels, Retry, repair reset state, and diagnostics visibility gating.
- [ ] Run focused tests and confirm failures.
- [ ] Add the Stop control, partial-answer status, Retry action, streaming cursor, and brief `Improving grounding...` state without shifting the message layout.
- [ ] Add a compact retrieval-details disclosure that renders timings, query resolution, candidate counts, selected scores, and validation outcome without raw context.
- [ ] Re-run focused tests and confirm they pass.

### Task 8: End-To-End Verification And Documentation

**Files:**
- Modify: `README.md`
- Modify: `.env.example` only if a new tunable flush interval is required
- Modify: `frontend/e2e/chat.spec.ts` or the existing authenticated chat Playwright spec

**Interfaces:**
- Verifies the complete feature contract.

- [ ] Add an authenticated Playwright flow that starts a slow response, receives incremental text, stops it, reloads the cancelled partial answer, retries without duplicating the user message, and verifies diagnostics are hidden/enabled according to Settings.
- [ ] Document true streaming, cancellation semantics, developer diagnostics, single-pass grounding repair, and the single-process coordinator limitation.
- [ ] Run `docker compose exec backend alembic upgrade head` twice and confirm both invocations succeed.
- [ ] Run `docker compose exec backend pytest -q`, `docker compose exec backend ruff check .`, `docker compose exec backend black --check .`, and `docker compose exec backend basedpyright`.
- [ ] Run `pnpm --dir frontend test`, `pnpm --dir frontend lint`, `pnpm --dir frontend type-check`, and `pnpm --dir frontend build`.
- [ ] Rebuild Docker services, verify health endpoints, and execute the authenticated Playwright scenario in desktop and mobile viewports.
