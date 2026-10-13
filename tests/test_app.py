import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class ConfigTests(unittest.TestCase):
    def test_agent_config_has_requested_project_and_settings(self):
        config = app.load_config()
        self.assertEqual(config["project_id"], "proj_2mzAhWk9r2mmsb1MA1Wfq1h1")
        self.assertEqual(config["model"], "gpt-6-astra")
        self.assertEqual(config["reasoning"]["effort"], "medium")
        self.assertEqual(config["reasoning"]["summary"], "auto")
        self.assertFalse(config["multi_agent"]["enabled"])
        self.assertEqual(config["tools"][0]["type"], "web_search")
        self.assertTrue(config["instructions"])

    def test_agent_id_is_saved_then_reused(self):
        id_path = Path(__file__).parent / ".agent_id_test"
        try:
            with patch.object(app, "AGENT_ID_PATH", id_path), patch.object(app, "request_json", return_value={"id": "agent_test"}) as request:
                agent_id = app.ensure_agent(app.load_config())
                self.assertEqual(agent_id, "agent_test")
                self.assertEqual(id_path.read_text(), "agent_test")
                self.assertEqual(app.ensure_agent(app.load_config()), "agent_test")
                request.assert_called_once()
        finally:
            id_path.unlink(missing_ok=True)


class ApiTests(unittest.TestCase):
    def test_curl_requires_api_key_before_running_subprocess(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(app.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(app.ApiError, "OPENAI_API_KEY"):
                list(app.curl(["-X", "GET", "https://example.invalid"]))
            popen.assert_not_called()

    def test_main_stops_with_setup_instructions_when_key_is_missing(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(output):
            self.assertEqual(app.main(), 2)
        self.assertIn("OPENAI_API_KEY is not set", output.getvalue())

    def test_request_json_reports_invalid_json(self):
        with patch.object(app, "curl", return_value=iter(["not-json"])):
            with self.assertRaisesRegex(app.ApiError, "Expected JSON response"):
                app.request_json(["-X", "POST"], {})

    def test_request_json_surfaces_api_error_object(self):
        response = json.dumps({"error": {"message": "permission denied"}})
        with patch.object(app, "curl", return_value=iter([response])):
            with self.assertRaisesRegex(app.ApiError, "permission denied"):
                app.request_json(["-X", "POST"], {})

    def test_event_stream_parses_sse_and_dispatches_complete_events(self):
        raw = [
            "event: message", 'data: {"type":"agent.session.output_text.delta","delta":"Hello"}', "",
            'data: {"type":"agent.session.turn.completed"}', "",
        ]
        events = []
        with patch.object(app, "curl", return_value=iter(raw)):
            app.event_stream(["-X", "POST"], {}, on_event=events.append)
        self.assertEqual(len(events), 2)
        self.assertEqual(json.loads(events[0])["delta"], "Hello")
        self.assertEqual(json.loads(events[1])["type"], "agent.session.turn.completed")

    def test_output_delta_is_rendered(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            app.handle_event('{"type":"agent.session.output_text.delta","delta":"A test"}')
        self.assertEqual(output.getvalue(), "A test")

    def test_tool_events_are_visible_to_operator(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            app.handle_event('{"type":"agent.session.tool.started","name":"web_search"}')
        self.assertIn("web_search", output.getvalue())

    def test_failed_events_are_visible_to_operator(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            app.handle_event('{"type":"agent.session.turn.failed","error":{"message":"failed"}}')
        self.assertIn("[error]", output.getvalue())
        self.assertIn("failed", output.getvalue())

    def test_initial_session_captures_session_id_and_uses_hosted_env(self):
        def stream(_args, payload, on_event=None):
            self.assertEqual(payload["agent_id"], "agent_abc")
            self.assertEqual(payload["environment"], {"type": "openai_hosted"})
            self.assertTrue(payload["stream"])
            on_event('{"type":"agent.session.created","session_id":"sess_abc"}')
        with patch.object(app, "event_stream", side_effect=stream):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(app.start_session("agent_abc"), "sess_abc")

    def test_initial_session_without_id_fails_clearly(self):
        with patch.object(app, "event_stream", return_value=None):
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaisesRegex(app.ApiError, "without a session ID"):
                app.start_session("agent_abc")


if __name__ == "__main__":
    unittest.main(verbosity=2)
