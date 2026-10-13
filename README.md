# Finnie Finance Assistant — Agents API starter

A runnable interactive terminal application that creates or reuses a saved Finnie agent, creates a session in an OpenAI-hosted environment, streams its first response, and accepts follow-up messages in that session. HTTP calls use `curl` directly; Python uses only its standard library.

## Requirements

- Python 3.10 or newer
- `curl` available on `PATH`
- An OpenAI API key for project `proj_2mzAhWk9r2mmsb1MA1Wfq1h1` with `api.agents.read`, `api.agents.write`, and `api.responses.write` permissions
- Network access to `api.openai.com`

The application uses `environment: {"type":"openai_hosted"}`. OpenAI provisions and runs the execution environment, so this starter does not need a local executor or environment template. The app keeps the API key on the local host and does not pass it into the managed environment.

## Run on Windows PowerShell

```powershell
cd "C:\Users\glsri\OneDrive\Desktop\1. Finnie - Personal Finance Agent\FinanceAI_Assist"
$env:OPENAI_API_KEY = "your-project-api-key"
python app.py
```

On first run, the app creates a saved agent using `config/agent.json`, writes the returned agent ID to `.agent_id`, starts a hosted session, sends a greeting, and streams the event output. Later runs reuse the saved agent definition but start a new session. Follow-up messages in the current process continue the same session. Type `/quit` to exit. `.agent_id` is local runtime state and is excluded from Git.

If the key is missing, the app stops before making a request. API errors and streamed failures are shown in the terminal. Built-in web search is executed by the Agents API; tool-related events are displayed as they arrive. The starter does not register custom function tools that need a local executor.

## Test

Run the local unit suite (no API key or network access required):

```powershell
python -m unittest discover -s tests -v
```

The suite checks configuration, saved-agent reuse, key validation, API error parsing, SSE parsing, event rendering, streamed session ID capture, and failure handling. Results from the completed run are in [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md).

## Agent configuration

`config/agent.json` preserves the supplied model (`gpt-6-astra`), web search tool, reasoning settings, text output settings, and disabled multi-agent setting. The missing display name and instructions are completed for a beginner-friendly educational finance assistant. The app selects the supported `openai_hosted` environment. The saved definition is created with `POST /v1/agents`; session creation and continued input use the Agents API session endpoints with `OpenAI-Beta: agents=v1`.

## Project context

The source problem statement and milestones describe a broader finance assistant capstone: multi-agent routing, RAG, portfolio/goal analysis, market integration, a web interface, and documentation. The grading rubric gives particular weight to architecture and testing. This repository is the requested runnable Agents API session integration and does not yet claim those broader capstone features are implemented. The supplied documents are preserved in `docs/source_documents/`.

For the current API contract, see the [Agents API overview](https://developers.openai.com/api/docs/guides/agents-api/overview), [configuration guide](https://developers.openai.com/api/docs/guides/agents-api/configuration), and [session guide](https://developers.openai.com/api/docs/guides/agents-api/sessions).
