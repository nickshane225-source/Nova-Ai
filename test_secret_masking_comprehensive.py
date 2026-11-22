import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import audit_logger
import discord_gateway
import server
import telegram_gateway


class TestSecretMaskingComprehensive(unittest.TestCase):
    FAKE_SECRETS = {
        "api_key": "AQ.Ab8RN6LFakeGoogleKeyValue9876543210XYZ",
        "anthropic_api_key": "sk-ant-api03-FakeAnthropicSecretKey1234567890",
        "gemini_api_key": "AIzaSyDFakeLegacyGoogleKey1234567890ABC",
        "groq_api_key": "gsk_FakeGroqProviderKey1234567890ABCDEF",
        "openrouter_api_key": "sk-or-v1-FakeOpenRouterKey1234567890ABCDEF",
        "telegram_bot_token": "123456789:AAFakeTelegramBotTokenSecret1234567890",
        "discord_bot_token": "MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.GaBcDe.FakeDiscordBotTokenSecret1234567890",
        "remote_token": "RemTokFakePairingSecret9876543210",
        "pairing_code": "PAIR-SECRET-987654",
    }

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_cfg_file = server.CONFIG_FILE
        self.orig_audit_file = audit_logger.get_audit_file()
        server.CONFIG_FILE = Path(self.tmpdir.name) / "config.json"
        self.audit_path = Path(self.tmpdir.name) / "audit.jsonl"
        audit_logger.set_audit_file(self.audit_path)

        cfg = dict(server.DEFAULT_CONFIG)
        cfg["provider"] = "anthropic"
        cfg["encrypt_keys"] = False
        for k, v in self.FAKE_SECRETS.items():
            cfg[k] = v
        server.save_config(cfg)

        with server.LOCK:
            server.EVENTS.clear()

    def tearDown(self):
        server.CONFIG_FILE = self.orig_cfg_file
        audit_logger.set_audit_file(self.orig_audit_file)
        with server.LOCK:
            server.EVENTS.clear()
        self.tmpdir.cleanup()

    def _assert_no_secret_leaked(self, blob: str, where: str):
        for name, secret_val in self.FAKE_SECRETS.items():
            self.assertNotIn(
                secret_val,
                blob,
                f"Secret '{name}' leaked in {where}!",
            )

    def test_aq_pattern_masked_even_when_not_in_config(self):
        unconfigured_aq = "AQ.UnconfiguredBrandNewGoogleKey9876543210"
        self.assertNotIn(unconfigured_aq, server.mask_secrets(f"error using {unconfigured_aq}"))
        self.assertNotIn(unconfigured_aq, audit_logger.mask_secrets(f"error using {unconfigured_aq}"))

    def test_401_leaks_nothing_across_audit_events_console_api_and_gateways(self):
        all_secrets_blob = " ".join(f"{k}={v}" for k, v in self.FAKE_SECRETS.items())
        error_payload = json.dumps({
            "type": "error",
            "error": {"type": "authentication_error", "message": f"invalid key {all_secrets_blob}"},
        }).encode("utf-8")

        def fake_urlopen_401(req, timeout=90):
            raise urllib.error.HTTPError(
                url="https://api.anthropic.com/v1/messages",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=io.BytesIO(error_payload),
            )

        # 1. Start local HTTP server to test real /api/chat and /api/state
        srv = server.SilentThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()

        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"nova_session={server.SESSION_TOKEN}",
                "X-Nova-Token": server.API_SESSION_TOKEN,
                "Origin": f"http://127.0.0.1:{port}",
            }

            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                # Force 401 via /api/chat
                real_urlopen = urllib.request.urlopen
                def selective_urlopen(req, timeout=90):
                    url = req.full_url if hasattr(req, "full_url") else str(req)
                    if "127.0.0.1" in url:
                        return real_urlopen(req, timeout=timeout)
                    return fake_urlopen_401(req, timeout=timeout)

                with mock.patch("urllib.request.urlopen", side_effect=selective_urlopen):
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/chat",
                        data=json.dumps({"message": "hello", "mode": "developer"}).encode("utf-8"),
                        headers=headers,
                        method="POST",
                    )
                    with real_urlopen(req, timeout=10) as resp:
                        chat_resp_text = resp.read().decode("utf-8")

                # Check /api/state
                req_state = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/state",
                    headers=headers,
                    method="GET",
                )
                with real_urlopen(req_state, timeout=10) as resp:
                    state_resp_text = resp.read().decode("utf-8")

                # Write audit event with all secrets
                audit_logger.log_audit_event(
                    channel="pc",
                    tool="CMD",
                    preview=f"401 failure: {all_secrets_blob}",
                    status="ERROR",
                )

                # Emit server event with all secrets
                server.add_event(type="error", message=f"401 failure: {all_secrets_blob}")

                # Send gateway messages with all secrets and capture outgoing payloads
                tg_sent = []
                tg = telegram_gateway.TelegramGateway(
                    cfg=server.get_config(),
                    chat_callback=lambda *a, **k: {},
                )
                def fake_tg_urlopen(req, timeout=10):
                    tg_sent.append(req.data.decode("utf-8"))
                    m = mock.MagicMock()
                    m.__enter__.return_value = m
                    m.status = 200
                    return m
                with mock.patch("urllib.request.urlopen", side_effect=fake_tg_urlopen):
                    tg.send_message("12345", f"401 failure: {all_secrets_blob}")

                dc_sent = []
                dc = discord_gateway.DiscordGateway(
                    bot_token=self.FAKE_SECRETS["discord_bot_token"],
                    channel_ids=["111"],
                    allowed_user_ids=["222"],
                    chat_handler=lambda *a, **k: {},
                )
                with mock.patch.object(dc, "_api_request", side_effect=lambda ep, data=None, method="POST": dc_sent.append(json.dumps(data))):
                    dc.send_message("111", f"401 failure: {all_secrets_blob}")

            # Verify NONE of the secrets appear anywhere
            self._assert_no_secret_leaked(chat_resp_text, "/api/chat response")
            self._assert_no_secret_leaked(state_resp_text, "/api/state response")
            self._assert_no_secret_leaked(self.audit_path.read_text(encoding="utf-8"), "audit.jsonl")
            with server.LOCK:
                events_blob = json.dumps(list(server.EVENTS))
            self._assert_no_secret_leaked(events_blob, "server.EVENTS")
            self._assert_no_secret_leaked(out_buf.getvalue() + err_buf.getvalue(), "console output")
            self._assert_no_secret_leaked("\n".join(tg_sent), "Telegram gateway message")
            self._assert_no_secret_leaked("\n".join(dc_sent), "Discord gateway message")
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
