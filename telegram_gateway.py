import server
"""
Telegram Remote Gateway for Nova AI.
Inspired by PocketPaw's multi-channel remote connectivity.
Zero third-party pip dependencies - Python standard library only.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("telegram_gateway")


def handle_remote_confirm(action_id: str, approve: bool) -> Dict[str, Any]:
    """
    Invokes pending action confirmation in Nova AI server.
    """
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
                    channel="telegram",
                    tool=pending["name"],
                    preview=pending.get("arg", ""),
                    guardian_verdict="NONE",
                    status="DENIED",
                    cfg=cfg,
                )
            return {"ok": True, "approved": False, "action": pending["name"], "command": pending.get("arg", "")}

        res = server.run_skill(
            cfg,
            pending["name"],
            pending["arg"],
            source="telegram",
            is_confirmed=True,
            mode=pending.get("mode", "developer"),
        )
        if getattr(server, "audit_logger", None):
            server.audit_logger.log_audit_event(
                channel="telegram",
                tool=pending["name"],
                preview=pending.get("arg", ""),
                guardian_verdict="NONE",
                status="APPROVED",
                cfg=cfg,
            )
        return {"ok": True, "approved": True, "action": pending["name"], "command": pending.get("arg", ""), "result": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class TelegramGateway:
    def __init__(self, cfg: Dict[str, Any], chat_callback: Optional[Callable[..., Any]] = None):
        self.cfg = cfg or {}
        self.chat_callback = chat_callback
        self.token = str(self.cfg.get("telegram_bot_token") or "").strip()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.offset = 0

    def get_api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def send_message(self, chat_id: Any, text: str) -> bool:
        if not self.token or not text:
            return False
        url = self.get_api_url("sendMessage")
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text[:4000],  # Telegram message length limit is 4096
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"[Telegram] Failed to send message to {chat_id}: {e}")
            return False

    def process_update(self, update: Dict[str, Any]) -> bool:
        message = update.get("message")
        if not message:
            return False

        chat_id_int = message.get("chat", {}).get("id")
        if chat_id_int is None:
            return False

        chat_id = str(chat_id_int)
        raw_allowed = self.cfg.get("telegram_allowed_chat_ids") or []
        allowed_chat_ids = [str(x).strip() for x in raw_allowed if str(x).strip()]

        # Strict chat ID whitelist check
        if allowed_chat_ids and chat_id not in allowed_chat_ids:
            logger.warning(f"[Telegram Security] Rejected message from unauthorized chat ID: {chat_id}")
            return False

        text = (message.get("text") or "").strip()
        if not text:
            return False

        # Command: /allow <id>
        if text.startswith("/allow"):
            parts = text.split(maxsplit=1)
            action_id = parts[1].strip() if len(parts) > 1 else ""
            if not action_id:
                self.send_message(chat_id_int, "Usage: /allow <action_id>")
                return True
            res = handle_remote_confirm(action_id, approve=True)
            if res.get("ok"):
                cmd_info = f"\nCommand:\n`{res.get('command')}`" if res.get("command") else ""
                self.send_message(chat_id_int, f"✅ Action Approved: {res.get('action')}{cmd_info}\n{res.get('result', '')}")
            else:
                self.send_message(chat_id_int, f"❌ Failed to approve: {res.get('error')}")
            return True

        # Command: /deny <id>
        if text.startswith("/deny"):
            parts = text.split(maxsplit=1)
            action_id = parts[1].strip() if len(parts) > 1 else ""
            if not action_id:
                self.send_message(chat_id_int, "Usage: /deny <action_id>")
                return True
            res = handle_remote_confirm(action_id, approve=False)
            if res.get("ok"):
                cmd_info = f"\nCommand:\n`{res.get('command')}`" if res.get("command") else ""
                self.send_message(chat_id_int, f"🚫 Action Denied: {res.get('action')}{cmd_info}")
            else:
                self.send_message(chat_id_int, f"❌ Failed to deny: {res.get('error')}")
            return True

        if text in ("/start", "/help"):
            self.send_message(
                chat_id_int,
                "🤖 *Nova AI Telegram Gateway*\n\nSend any prompt to chat with Nova.\nCommands:\n- `/allow <id>`: Approve action\n- `/deny <id>`: Cancel action",
            )
            return True

        # General turn - invoke chat callback
        if self.chat_callback:
            try:
                res = self.chat_callback(text, source="telegram")
                if isinstance(res, dict):
                    reply_text = res.get("reply", "") or res.get("response", "")
                    if res.get("pending"):
                        p = res["pending"]
                        p_id = p.get("id")
                        cmd_val = p.get("command") or p.get("arg") or p.get("preview") or ""
                        # 1b. Strip or escape backticks
                        safe_cmd = cmd_val.replace("```", "'''").replace("`", "'")
                        # 1c. Escape control and invisible characters
                        if hasattr(server, "sanitize_preview"):
                            safe_cmd, _ = server.sanitize_preview(safe_cmd)
                        full_approval_msg = (
                            f"\n\n⚠️ Action Requires Approval (ID: `{p_id}`):\n"
                            f"{p.get('prompt')}\n\n"
                            f"Command:\n```\n{safe_cmd}\n```\n"
                            f"Use `/allow {p_id}` or `/deny {p_id}`"
                        )
                        if len(reply_text + full_approval_msg) > 4096:
                            with server.PENDING_LOCK:
                                if p_id in server.PENDING_ACTIONS:
                                    server.PENDING_ACTIONS[p_id]["pc_only"] = True
                            reply_text += (
                                f"\n\n⚠️ Action Requires Approval (ID: `{p_id}`):\n"
                                f"{p.get('prompt')}\n\n"
                                f"Notice: Approval for this action must be done on the PC (payload exceeds Telegram limits)."
                            )
                        else:
                            reply_text += full_approval_msg
                else:
                    reply_text = str(res)
                self.send_message(chat_id_int, reply_text)
                return True
            except Exception as e:
                logger.error(f"[Telegram] Error executing chat callback: {e}")
                self.send_message(chat_id_int, f"Error processing request: {e}")
                return True

        return False

    def poll_updates(self):
        if not self.token:
            return
        url = self.get_api_url("getUpdates")
        params = {"timeout": 15, "offset": self.offset}
        full_url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(full_url)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("ok"):
                    return
                for update in data.get("result", []):
                    self.offset = max(self.offset, update.get("update_id", 0) + 1)
                    self.process_update(update)
        except Exception:
            time.sleep(2)

    def _run(self):
        while self.running:
            self.poll_updates()
            time.sleep(0.5)

    def start(self):
        if self.running or not self.token:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="TelegramGatewayThread")
        self.thread.start()

    def stop(self):
        self.running = False


def start_telegram_daemon(cfg: Dict[str, Any], chat_callback: Optional[Callable[..., Any]] = None) -> Optional[TelegramGateway]:
    if not cfg.get("telegram_enabled"):
        return None
    token = cfg.get("telegram_bot_token")
    if not token:
        return None
    gw = TelegramGateway(cfg, chat_callback=chat_callback)
    gw.start()
    return gw
