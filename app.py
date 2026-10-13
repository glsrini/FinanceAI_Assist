"""Small interactive terminal app for the OpenAI Agents API, using curl directly."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "agent.json"
AGENT_ID_PATH = ROOT / ".agent_id"
API_BASE = "https://api.openai.com/v1"
BETA_HEADER = "OpenAI-Beta: agents=v1"


class ApiError(RuntimeError):
    pass


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def curl(args: list[str], *, payload: dict[str, Any] | None = None) -> Iterator[str]:
    """Run curl and yield output lines; errors include the API response body."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise ApiError("OPENAI_API_KEY is missing. Set it in this terminal and restart the app.")
    if not shutil.which("curl"):
        raise ApiError("curl was not found. Install curl or add it to PATH.")

    command = [
        "curl", "--no-buffer", "--silent", "--show-error", "--fail-with-body",
        *args,
        "-H", BETA_HEADER,
        "-H", f"Authorization: Bearer {os.environ['OPENAI_API_KEY']}",
        "-H", f"OpenAI-Project: {load_config()['project_id']}",
        "-H", "Content-Type: application/json",
    ]
    if payload is not None:
        command.extend(["-d", json.dumps(payload, separators=(",", ":"))])

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    assert process.stdout is not None
    body_lines: list[str] = []
    for line in process.stdout:
        body_lines.append(line)
        yield line.rstrip("\r\n")
    stderr = process.stderr.read() if process.stderr else ""
    status = process.wait()
    if status:
        body = "\n".join(body_lines).strip()
        detail = body or stderr.strip() or f"curl exited with status {status}"
        raise ApiError(f"Agents API request failed: {detail}")


def request_json(args: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    body = "\n".join(curl(args, payload=payload)).strip()
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ApiError(f"Expected JSON response, received: {body[:1000]}") from exc
    if isinstance(result, dict) and result.get("error"):
        raise ApiError(json.dumps(result["error"], ensure_ascii=False))
    return result


def ensure_agent(config: dict[str, Any]) -> str:
    if AGENT_ID_PATH.exists():
        agent_id = AGENT_ID_PATH.read_text(encoding="utf-8").strip()
        if agent_id:
            print(f"Reusing saved agent: {agent_id}")
            return agent_id

    definition = {key: value for key, value in config.items() if key not in {"project_id", "name"}}
    definition["name"] = config["name"]
    print("Creating reusable Finnie agent definition...")
    result = request_json(["-X", "POST", f"{API_BASE}/agents"], definition)
    agent_id = result.get("id")
    if not agent_id:
        raise ApiError(f"Agent creation returned no id: {json.dumps(result)[:1000]}")
    AGENT_ID_PATH.write_text(agent_id, encoding="utf-8")
    print(f"Created agent: {agent_id}")
    return agent_id


def event_stream(args: list[str], payload: dict[str, Any] | None, on_event=None) -> None:
    """Print event JSON as it arrives and surface event text and failures."""
    event_data: list[str] = []
    for line in curl(args, payload=payload):
        if line.startswith("data:"):
            event_data.append(line[5:].strip())
        elif not line and event_data:
            (on_event or handle_event)("\n".join(event_data))
            event_data.clear()
    if event_data:
        (on_event or handle_event)("\n".join(event_data))


def handle_event(data: str) -> None:
    if data == "[DONE]":
        return
    try:
        event = json.loads(data)
    except json.JSONDecodeError:
        print(f"[event] {data}", flush=True)
        return

    kind = event.get("type", "unknown")
    if kind in {"error", "agent.session.turn.failed", "agent.session.failed"}:
        print(f"\n[error] {json.dumps(event, ensure_ascii=False)}", flush=True)
    elif "output_text.delta" in kind:
        delta = event.get("delta", "")
        print(delta, end="", flush=True)
    elif "tool" in kind or "requires_action" in kind:
        print(f"\n[tool/event] {json.dumps(event, ensure_ascii=False)}", flush=True)
    elif "turn.completed" in kind:
        print("\n[turn completed]", flush=True)
    elif "turn.cancelled" in kind:
        print("\n[turn cancelled]", flush=True)
    else:
        print(f"[event] {json.dumps(event, ensure_ascii=False)}", flush=True)


def start_session(agent_id: str) -> str:
    prompt = "Hi Finnie. Introduce yourself and explain three ways you can help me build better personal finance habits."
    payload = {
        "agent_id": agent_id,
        "environment": {"type": "openai_hosted"},
        "input": prompt,
        "stream": True,
    }
    print(f"\nYou: {prompt}\n\nFinnie: ", end="", flush=True)
    session_id: str | None = None

    # The streaming create endpoint begins with a session.created event.
    # Capture the ID from that event while rendering all events as they arrive.
    def capture(data: str) -> None:
        nonlocal session_id
        try:
            parsed = json.loads(data)
            session_id = parsed.get("session_id") or parsed.get("session", {}).get("id") or session_id
        except (json.JSONDecodeError, AttributeError):
            pass
        handle_event(data)
    event_stream(["-X", "POST", f"{API_BASE}/agents/sessions"], payload, on_event=capture)
    if not session_id:
        # Some stream event variants omit the session id; ask the user to preserve the
        # returned ID rather than inventing one. The service usually includes it.
        raise ApiError("The stream completed without a session ID. Check the event log above and retry after verifying the session state.")
    return session_id


def continue_session(session_id: str, message: str) -> None:
    payload = {
        "events": [{
            "type": "agent.session.input.message",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": message}]}],
        }]
    }
    key = str(uuid.uuid4())
    print("Finnie: ", end="", flush=True)
    # Open the event stream before submitting input so early turn events cannot be missed.
    command = [
        "curl", "--no-buffer", "--silent", "--show-error", "--fail-with-body", "-N", "-i",
        f"{API_BASE}/agents/sessions/{session_id}/events",
        "-H", BETA_HEADER,
        "-H", f"Authorization: Bearer {os.environ['OPENAI_API_KEY']}",
        "-H", f"OpenAI-Project: {load_config()['project_id']}",
        "-H", "Accept: text/event-stream",
    ]
    stream = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1)
    assert stream.stdout is not None
    headers = []
    for header_line in stream.stdout:
        headers.append(header_line.rstrip())
        if header_line.rstrip() == "":
            break
    if not headers or " 200 " not in headers[0]:
        stream.terminate()
        detail = "\n".join(headers) or "no response"
        raise ApiError(f"Could not open the session event stream: {detail}")

    # Submit the message with an idempotency key; the GET stream carries turn events.
    try:
        accepted = request_json(
            ["-X", "POST", f"{API_BASE}/agents/sessions/{session_id}/events", "-H", f"Idempotency-Key: {key}"],
            payload,
        )
        print(f"\n[input accepted] {json.dumps(accepted, ensure_ascii=False)}", flush=True)
        event_data: list[str] = []
        for line in stream.stdout:
            if line.startswith("data:"):
                event_data.append(line[5:].strip())
            elif not line.strip() and event_data:
                data = "\n".join(event_data)
                handle_event(data)
                event_data.clear()
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    event = {}
                if any(suffix in event.get("type", "") for suffix in ("turn.completed", "turn.failed", "turn.cancelled")):
                    break
        stderr = stream.stderr.read() if stream.stderr else ""
        status = stream.poll()
        if status not in (None, 0) and stderr.strip():
            raise ApiError(f"Session event stream failed: {stderr.strip()}")
    finally:
        stream.terminate()
        stream.wait(timeout=5)


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. In PowerShell, run: $env:OPENAI_API_KEY = 'your-key'", file=sys.stderr)
        return 2
    try:
        config = load_config()
        agent_id = ensure_agent(config)
        session_id = start_session(agent_id)
        print(f"Session: {session_id}")
        print("\nContinue chatting. Type /quit to exit.\n")
        while True:
            try:
                message = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            if not message:
                continue
            if message.lower() in {"/quit", "/exit"}:
                break
            try:
                continue_session(session_id, message)
            except ApiError as exc:
                print(f"\nAPI error: {exc}\n", file=sys.stderr)
        return 0
    except ApiError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
