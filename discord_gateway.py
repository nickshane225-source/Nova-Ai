#!/usr/bin/env python3
"""
Nova AI Discord Remote Gateway
Pure Python Standard Library (zero-pip).

Enables remote interaction with Nova AI via Discord Bot API.
Uses urllib.request (no discord.py or external dependencies needed).
Enforces channel & user whitelisting, silent execution (no audio on PC speakers),
and remote approval of confirmation gates (/allow <id>, /deny <id>).
"""

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

logger = logging.getLogger("nova_ai.discord_gateway")

DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordGateway:
    def __init__(
        self,
        bot_token: str,
        channel_ids: list[str],
        allowed_user_ids: list[str] | None = None,
        chat_handler: Callable[[str, str], dict[str, Any]] | None = None,
        confirm_handler: Callable[[str, bool], dict[str, Any]] | None = None,
        poll_interval: float = 3.0,
    ):
        self.bot_token = (bot_token or "").strip()
        self.channel_ids = [str(cid).strip() for cid in channel_ids if str(cid).strip()]
        self.allowed_user_ids = [str(uid).strip() for uid in (allowed_user_ids or []) if str(uid).strip()]
        self.chat_handler = chat_handler
        self.confirm_handler = confirm_handler
        self.poll_interval = max(1.0, poll_interval)
        self.last_message_ids: dict[str, str] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self.bot_id: str | None = None

    def _api_request(self, endpoint: str, data: dict[str, Any] | None = None, method: str = "GET") -> Any:
        url = f"{DISCORD_API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "User-Agent": "NovaAI-DiscordGateway/1.0",
            "Content-Type": "application/json",
        }
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def send_message(self, channel_id: str, content: str) -> bool:
        """Send message to Discord channel, splitting chunks if > 2000 chars."""
        if not content:
            return False
        # Discord character limit is 2000
        max_len = 1950
        chunks = [content[i : i + max_len] for i in range(0, len(content), max_len)]
        for chunk in chunks:
            try:
                self._api_request(f"/channels/{channel_id}/messages", data={"content": chunk}, method="POST")
            except Exception as e:
                logger.error(f"[Discord Gateway] Failed to send message to {channel_id}: {e}")
                return False
        return True

    def get_bot_info(self) -> dict | None:
        try:
            me = self._api_request("/users/@me")
            self.bot_id = str(me.get("id"))
            return me
        except Exception as e:
            logger.warning(f"[Discord Gateway] Could not fetch bot user info: {e}")
            return None

    def poll_channel(self, channel_id: str) -> None:
        """Fetch and process new messages from a single channel."""
        last_id = self.last_message_ids.get(channel_id)
        endpoint = f"/channels/{channel_id}/messages?limit=10"
        if last_id:
            endpoint += f"&after={last_id}"

        try:
            messages = self._api_request(endpoint)
        except Exception as e:
            logger.debug(f"[Discord Gateway] Poll error on {channel_id}: {e}")
            return

        if not isinstance(messages, list) or not messages:
            return

        # Sort chronologically (Discord returns newest first)
        messages.sort(key=lambda m: int(m.get("id", 0)))

        for msg in messages:
            msg_id = str(msg.get("id"))
            self.last_message_ids[channel_id] = msg_id

            author = msg.get("author", {})
            user_id = str(author.get("id"))
            is_bot = author.get("bot", False)

            # Ignore own messages or other bot messages
            if is_bot or user_id == self.bot_id:
                continue

            if not self.is_authorized(user_id, channel_id):
                logger.warning(f"[Discord Security] Ignored message from unauthorized user/channel: {user_id}/{channel_id}")
                continue

            content = (msg.get("content") or "").strip()
            if not content:
                continue

            self.handle_message(channel_id, user_id, content)

    def is_authorized(self, user_id: str | int, channel_id: str | int = "") -> bool:
        """
        Verify message sender and channel authorization:
        - Must return False whenever allowed_user_ids is empty (regardless of channel_ids).
        - Must require BOTH a listed user and, if channel_ids is set, a listed channel.
        """
        if not self.allowed_user_ids:
            return False
        uid = str(user_id or "").strip()
        if not uid or uid not in self.allowed_user_ids:
            return False
        if self.channel_ids:
            cid = str(channel_id or "").strip()
            if not cid or cid not in self.channel_ids:
                return False
        return True

    def handle_message(self, channel_id: str, user_id: str, text: str) -> None:
        """Handle incoming command or user query."""
        if not self.is_authorized(user_id, channel_id):
            logger.warning(f"[Discord Security] Ignored message from unauthorized user/channel: {user_id}/{channel_id}")
            return
        cmd = text.strip()

        # Approval commands: /allow <id> or /deny <id>
        if cmd.startswith("/allow") or cmd.startswith("/deny"):
            parts = cmd.split(None, 1)
            action = parts[0][1:].lower()
            token = parts[1].strip() if len(parts) > 1 else ""
            if not token:
                self.send_message(channel_id, f"Usage: /{action} <action_id>")
                return
            if self.confirm_handler:
                approved = action == "allow"
                result = self.confirm_handler(token, approved)
                if result.get("ok"):
                    res_detail = result.get("result")
                    res_str = f"\nResult: {res_detail}" if res_detail else ""
                    cmd_raw = result.get('command') or ''
                    cmd_str = ''
                    if cmd_raw:
                        import server
                        safe_c, _ = server.sanitize_preview(cmd_raw)
                        backticks = re.findall(r"`+", safe_c)
                        fence = "`" * max(3, max([len(b) for b in backticks], default=0) + 1)
                        cmd_str = f"\nCommand:\n{fence}\n{safe_c}\n{fence}"
                    reply = f"✅ Action {action}ed: {result.get('action')}{cmd_str}{res_str}"
                else:
                    reply = f"❌ Failed to {action}: {result.get('error', 'Action not found or expired')}"
            else:
                reply = "Confirmation handler not configured."
            self.send_message(channel_id, reply)
            return

        # Status command
        if cmd == "/status":
            self.send_message(channel_id, "🐾 Nova AI is online and operational. Voice mode is silent on remote.")
            return

        # Diagnostics command
        if cmd == "/doctor" or cmd == "/health":
            try:
                import diagnostics
                diag = diagnostics.run_diagnostics()
                self.send_message(
                    channel_id,
                    f"**Nova AI System Health:** {diag['overall_status'].upper()}\n"
                    f"Passed: {diag['summary']['ok']} | Warnings: {diag['summary']['warning']} | Errors: {diag['summary']['error']}"
                )
            except Exception as e:
                self.send_message(channel_id, f"Error checking diagnostics: {e}")
            return

        # General Query -> Hand off to chat handler
        if self.chat_handler:
            try:
                # source="discord" triggers silent remote execution (no PC TTS playback)
                resp = self.chat_handler(text, "discord")
                reply_text = resp.get("reply") or resp.get("response") or "Done."
                if isinstance(resp, dict) and resp.get("pending"):
                    import server
                    p = resp["pending"]
                    p_id = p.get("id")
                    raw_prompt = p.get("prompt") or ""
                    safe_prompt, _ = server.sanitize_preview(raw_prompt)
                    cmd_val = p.get("command") or p.get("arg") or p.get("preview") or ""
                    safe_cmd, has_invis = server.sanitize_preview(cmd_val)
                    invis_warn = "\n⚠️ Warning: Command contains hidden or invisible characters." if has_invis else ""
                    backticks = re.findall(r"`+", safe_cmd)
                    fence = "`" * max(3, max([len(b) for b in backticks], default=0) + 1)
                    full_approval_msg = (
                        f"⚠️ Action Requires Approval (ID: `{p_id}`):\n"
                        f"{safe_prompt}\n\n"
                        f"Command:\n{fence}\n{safe_cmd}\n{fence}{invis_warn}\n\n"
                        f"Use `/allow {p_id}` or `/deny {p_id}`"
                    )
                    if reply_text and reply_text != "Done.":
                        self.send_message(channel_id, reply_text)
                    if len(full_approval_msg) > 1950:
                        with server.PENDING_LOCK:
                            if p_id in server.PENDING_ACTIONS:
                                server.PENDING_ACTIONS[p_id]["pc_only"] = True
                        short_msg = (
                            f"⚠️ Action Requires Approval (ID: `{p_id}`):\n"
                            f"{safe_prompt}\n\n"
                            f"Notice: Approval for this action must be done on the PC (payload exceeds Discord limits)."
                        )
                        self.send_message(channel_id, short_msg)
                    else:
                        self.send_message(channel_id, full_approval_msg)
                    return
                else:
                    self.send_message(channel_id, reply_text)
            except Exception as e:
                self.send_message(channel_id, f"Error processing query: {e}")
        else:
            self.send_message(channel_id, "Chat handler is not attached.")

    def run_loop(self) -> None:
        self.get_bot_info()
        logger.info(f"[Discord Gateway] Gateway started for channels: {self.channel_ids}")

        # Initialize last message id for each channel to avoid replaying historic backlog
        for cid in self.channel_ids:
            try:
                msgs = self._api_request(f"/channels/{cid}/messages?limit=1")
                if msgs and isinstance(msgs, list):
                    self.last_message_ids[cid] = str(msgs[0].get("id"))
            except Exception:
                pass

        while self._running:
            for cid in self.channel_ids:
                try:
                    self.poll_channel(cid)
                except Exception as e:
                    logger.debug(f"[Discord Gateway] Channel {cid} loop exception: {e}")
            time.sleep(self.poll_interval)

    def start(self) -> None:
        if self._running or not self.bot_token or not self.channel_ids:
            return
        self._running = True
        self._thread = threading.Thread(target=self.run_loop, daemon=True, name="DiscordGatewayThread")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)


def handle_remote_confirm(action_id: str, approve: bool) -> dict[str, Any]:
    """Invokes pending action confirmation in Nova AI server."""
    try:
        import server
        with server.PENDING_LOCK:
            pending = server.PENDING_ACTIONS.get(action_id)
            if not pending:
                return {"ok": False, "error": "Pending action not found or expired"}
            if pending.get("pc_only"):
                return {"ok": False, "error": "Approval for this action must be done on the PC."}
            pending = server.PENDING_ACTIONS.pop(action_id, None)
        if pending.get("expires_at", 0) < time.time():
            return {"ok": False, "error": "Pending action expired"}

        cfg = server.get_config()
        if not approve:
            if getattr(server, "audit_logger", None):
                server.audit_logger.log_audit_event(
                    channel="discord",
                    tool=pending["name"],
                    preview=pending.get("arg", ""),
                    guardian_verdict=pending.get("guardian", "NONE"),
                    status="DENIED",
                    cfg=cfg,
                )
            return {"ok": True, "approved": False, "action": pending["name"], "command": pending.get("arg", "")}

        res = server.run_skill(
            cfg,
            pending["name"],
            pending["arg"],
            source="discord",
            is_confirmed=True,
            mode=pending.get("mode", "developer"),
            is_tainted=pending.get("is_tainted", False),
        )
        if getattr(server, "audit_logger", None):
            server.audit_logger.log_audit_event(
                channel="discord",
                tool=pending["name"],
                preview=pending.get("arg", ""),
                guardian_verdict=pending.get("guardian", "NONE"),
                status="APPROVED",
                cfg=cfg,
            )
        return {"ok": True, "approved": True, "action": pending["name"], "command": pending.get("arg", ""), "result": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def start_discord_daemon(cfg: dict[str, Any], chat_callback: Callable[..., Any] | None = None) -> DiscordGateway | None:
    """Helper to start Discord gateway directly from Nova AI server config."""
    if not cfg.get("discord_enabled"):
        return None
    token = cfg.get("discord_bot_token")
    channels = cfg.get("discord_channel_ids") or []
    allowed_users = cfg.get("discord_allowed_user_ids") or []
    if not token or not channels or not allowed_users:
        return None
    return start_discord_gateway(
        bot_token=token,
        channel_ids=channels,
        allowed_user_ids=allowed_users,
        chat_handler=chat_callback,
        confirm_handler=handle_remote_confirm,
    )


# Module singleton
_GATEWAY: DiscordGateway | None = None


def start_discord_gateway(
    bot_token: str,
    channel_ids: list[str],
    allowed_user_ids: list[str] | None = None,
    chat_handler: Callable[[str, str], dict[str, Any]] | None = None,
    confirm_handler: Callable[[str, bool], dict[str, Any]] | None = None,
) -> DiscordGateway | None:
    global _GATEWAY
    stop_discord_gateway()
    if not bot_token or not channel_ids:
        return None
    _GATEWAY = DiscordGateway(
        bot_token=bot_token,
        channel_ids=channel_ids,
        allowed_user_ids=allowed_user_ids,
        chat_handler=chat_handler,
        confirm_handler=confirm_handler,
    )
    _GATEWAY.start()
    return _GATEWAY


def stop_discord_gateway() -> None:
    global _GATEWAY
    if _GATEWAY:
        _GATEWAY.stop()
        _GATEWAY = None
