# Finnie Agent Test Results

**Run date:** 2026-10-12

**Command:** `python -m unittest discover -s tests -v`

**Result:** PASS — 12 tests passed, 0 failed.

## Covered checks

| Area | Result |
| --- | --- |
| Agent configuration uses the requested project and model; web search, reasoning, and multi-agent values are present | Pass |
| Agent creation persists the returned ID and reuses it on later starts | Pass |
| Missing `OPENAI_API_KEY` is rejected before a network process starts | Pass |
| Invalid JSON and API error response bodies are surfaced as readable errors | Pass |
| Server-sent event records are parsed and dispatched | Pass |
| Text deltas, tool events, and failed-turn events are rendered | Pass |
| Hosted session configuration and session ID capture are validated | Pass |
| Missing session ID after stream completion returns a clear failure | Pass |

## Live integration status

Live API tests were **not run** in this environment because `OPENAI_API_KEY` was not set. Therefore no saved agent or remote session was created during this run. After setting a project API key with `api.agents.read`, `api.agents.write`, and `api.responses.write`, run `python app.py` to exercise agent creation, hosted session startup, web search, event streaming, and follow-up turns. This limitation is not counted as a passing integration test.

The local suite uses mocked HTTP/event responses. It does not validate account permissions, model availability, network connectivity, hosted environment provisioning, or live web search results.
