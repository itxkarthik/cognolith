# Streaming Chat Design

## Goal

Replace Cognolith's simulated client-side chat animation with genuine Ollama token streaming, reliable cancellation, optional retrieval diagnostics, and one automatic grounding-repair pass.

## Scope

- Stream generated tokens from Ollama to the browser over structured Server-Sent Events (SSE).
- Persist an assistant message throughout its `streaming`, `completed`, `cancelled`, or `failed` lifecycle.
- Keep partial text when a user stops generation and support retry without duplicating the user turn.
- Expose retrieval diagnostics only when the user enables a developer-mode setting.
- Validate grounded answers once and perform at most one repair generation when citations are invalid or unsupported.
- Preserve the existing synchronous message endpoint temporarily for compatibility; the chat UI uses the streaming endpoint.

## Transport And Event Contract

The streaming endpoint remains a POST request because it carries the new user message. It returns named SSE events with JSON payloads. Every event includes stable persisted identifiers so the frontend can reconcile state after interruption.

```text
event: generation_started
data: {"session_id":1,"user_message":{...},"assistant_message":{...}}

event: retrieval_complete
data: {"sources":{...},"diagnostics":{...}|null}

event: token
data: {"message_id":2,"delta":"text"}

event: answer_reset
data: {"message_id":2,"reason":"grounding_repair"}

event: sources
data: {"message_id":2,"sources":{...}}

event: completed
data: {"message":{...}}

event: cancelled
data: {"message":{...}}

event: error
data: {"code":"GENERATION_FAILED","message":"...","retryable":true,"assistant_message_id":2}
```

The parser handles CRLF/LF framing, JSON payloads split across network reads, UTF-8 boundaries, comments/heartbeats, and an end-of-stream without treating it as a second completion. Browser requests include cookies and CSRF protection through the existing API conventions.

## Persistence And Generation Lifecycle

`chat_messages` gains a `generation_status` enum-like string, `generation_error`, `generation_metadata` JSONB, and generation timestamps. Existing assistant messages migrate to `completed`; user and system messages have no generation status.

The stream transaction creates and commits the user message and empty assistant placeholder before retrieval. The assistant is then updated in bounded batches while tokens arrive, with a final flush for every terminal state. This makes reload and network recovery deterministic.

A process-local generation coordinator maps assistant message IDs to active tasks and cancellation events. The cancellation endpoint verifies session ownership, sets the cancellation event, and waits briefly for the generator to flush. Closing or cancelling the Ollama HTTP stream stops model generation. This coordinator is intentionally single-process; a future multi-worker deployment must move coordination to Redis.

Disconnecting the browser is treated as cancellation: partial text is retained and marked `cancelled`. A retry streams a replacement assistant answer for the existing preceding user message and never inserts another user message. Only one active generation is permitted per session.

## Retrieval And Answer Quality

The current hybrid RAG retrieval remains authoritative. Streaming splits the pipeline into preparation and generation phases:

1. Prepare conversation grounding, ranked context, citation map, source payload, prompt messages, and diagnostics.
2. Stream the draft answer from `LLMService.stream_response()`.
3. Validate grounded output against the available citation IDs and selected context.
4. If validation fails, emit `answer_reset`, clear persisted draft content, and stream one repair prompt.
5. Persist only the final draft or repaired answer with its cited sources.

Repair is limited to one attempt. It triggers only for grounded requests when citations are missing, reference unknown source IDs, contradict a high-confidence retrieval result with a no-context claim, or fail conservative support checks. Casual model-only conversation is never forced through citation repair.

## Diagnostics

`user_settings` gains `rag_diagnostics_enabled`, defaulting to `false`. When disabled, no diagnostic payload is returned to the browser. When enabled, the assistant's generation metadata records and exposes:

- resolved retrieval query and follow-up subject;
- semantic, lexical, title, previous-source, and final hybrid scores;
- accepted and rejected candidate counts with rejection reasons;
- selected section/chunk ranges and context-budget use;
- retrieval, first-token, generation, repair, and total timings;
- validation outcome and whether repair ran.

The chat UI displays this in a compact `Retrieval details` disclosure below assistant messages. It does not appear for casual answers or users who have not enabled the setting.

## Frontend Behavior

The Zustand chat store owns one active `AbortController` per session and consumes structured events. `generation_started` replaces the optimistic user message and inserts the stable assistant placeholder. `token` appends deltas, `answer_reset` clears the transient draft, and terminal events replace local state with the server response.

While generating, the send control becomes a Stop button. Cancelling keeps the partial answer, labels it `Stopped`, and offers Retry. Retry references the cancelled assistant message and does not duplicate the user turn. A network error triggers a session refresh to reconcile persisted state; the client never automatically resends a POST.

## Failure Handling

- Retrieval or provider failure before tokens: mark the assistant `failed`, emit a retryable error, retain the user message.
- Provider failure after tokens: retain partial text, mark `failed`, and offer Retry.
- User cancellation: retain partial text, mark `cancelled`, and emit `cancelled`.
- Browser disconnect: cancel and persist partial state.
- Duplicate generation: return HTTP 409 before inserting another user message.
- Repair failure: keep the original draft, mark validation metadata as unresolved, and complete without a second retry loop.

## Testing

- Backend tests verify ordered incremental events, cancellation propagation, partial persistence, retry without duplicate user messages, disconnect handling, one repair maximum, diagnostics gating, and migration behavior.
- Frontend tests verify fragmented SSE parsing, UTF-8 handling, store reconciliation, stop/retry behavior, `answer_reset`, diagnostics visibility, and no duplicate messages.
- Authenticated browser testing uses a deliberately slow Ollama response to stop mid-answer, reload the partial result, retry, inspect diagnostics, and verify cited sources.
- Final verification runs backend tests, Ruff, Black, BasedPyright, frontend tests, type checking, production builds, migrations, and Docker health checks.

## Non-Goals

- WebSocket transport.
- Redis-backed distributed cancellation.
- Changing the Ollama chat or embedding models.
- More than one automatic grounding-repair attempt.
- Resuming the same POST stream after a network disconnect.
