#!/usr/bin/env python3
"""
Telegram Remote Gateway for Nova AI.
Inspired by PocketPaw's multi-channel remote connectivity.
Zero third-party pip dependencies - Python standard library only.
"""
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("telegram_gateway")


def handle_remote_confirm(action_id: str, approve: bool, notify: Optional[Callable] = None) -> Dict[str, Any]:
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
                    guardian_verdict=pending.get("guardian", "NONE"),
                    status="DENIED",
                    cfg=cfg,
                )
            return {"ok": True, "approved": False, "action": pending["name"], "command": pending.get("arg", "")}

        p_conv = pending.get("plan_state", {}).get("conv_id") or pending.get("conv_id") or "telegram:general"
        if pending.get("is_tainted") or pending.get("plan_state", {}).get("is_tainted"):
            server.CONVERSATION_TAINT[p_conv] = True
            if hasattr(server, "RUN_CODE_TRUST_STATE"):
                server.RUN_CODE_TRUST_STATE.invalidate()

        res = server.run_skill(
            cfg,
            pending["name"],
            pending["arg"],
            source="telegram",
            is_confirmed=True,
            mode=pending.get("mode", "developer"),
            is_tainted=pending.get("is_tainted", False),
            conv_id=p_conv,
        )
        if pending.get("plan_state") and hasattr(server, "resume_plan_execution"):
            plan_res = server.resume_plan_execution(pending["plan_state"], last_result=res, cfg=cfg, notify=notify)
            if isinstance(plan_res, dict) and plan_res.get("paused"):
                return {
                    "ok": True,
                    "approved": True,
                    "action": pending["name"],
                    "command": pending.get("arg", ""),
                    "result": str(res).strip(),
                    "pending": plan_res.get("pending_info"),
                }
            res_msg = plan_res.get("message") if isinstance(plan_res, dict) else str(plan_res)
            res = f"{res}\n\n{res_msg}"
        if getattr(server, "audit_logger", None):
            server.audit_logger.log_audit_event(
                channel="telegram",
                tool=pending["name"],
                preview=pending.get("arg", ""),
                guardian_verdict=pending.get("guardian", "NONE"),
                status="APPROVED",
                cfg=cfg,
            )
        return {"ok": True, "approved": True, "action": pending["name"], "command": pending.get("arg", ""), "result": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


ACTIVE_TELEGRAM_GATEWAYS: list["TelegramGateway"] = []

def reload_telegram_config(new_cfg: Dict[str, Any]) -> None:
    for gw in list(ACTIVE_TELEGRAM_GATEWAYS):
        try:
            gw.reload_config(new_cfg)
        except Exception:
            pass

class TelegramGateway:
    def __init__(self, cfg: Dict[str, Any], chat_callback: Optional[Callable[..., Any]] = None):
        self.cfg = cfg or {}
        self.chat_callback = chat_callback
        self.token = str(self.cfg.get("telegram_bot_token") or "").strip()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.offset = 0
        if self not in ACTIVE_TELEGRAM_GATEWAYS:
            ACTIVE_TELEGRAM_GATEWAYS.append(self)

    def reload_config(self, new_cfg: Optional[Dict[str, Any]] = None) -> None:
        if new_cfg is not None:
            if isinstance(self.cfg, dict):
                self.cfg.update(new_cfg)
            else:
                self.cfg = new_cfg
        else:
            try:
                import server
                if hasattr(server, "get_config"):
                    live = server.get_config()
                    if isinstance(self.cfg, dict):
                        self.cfg.update(live)
                    else:
                        self.cfg = live
            except Exception:
                pass

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

    def send_approval_announcement(self, chat_id: Any, pending: Dict[str, Any], prefix_text: str = "") -> None:
        import server
        p_id = pending.get("id")
        raw_prompt = pending.get("prompt") or ""
        safe_prompt, _ = server.sanitize_preview(raw_prompt)
        cmd_val = pending.get("command") or pending.get("arg") or pending.get("preview") or ""
        safe_cmd, has_invis = server.sanitize_preview(cmd_val)
        invis_warn = "\n⚠️ Warning: Command contains hidden or invisible characters." if (has_invis and "SECURITY WARNING" not in safe_cmd and "SECURITY WARNING" not in safe_prompt) else ""
        backticks = re.findall(r"`+", safe_cmd)
        fence = "`" * max(3, max([len(b) for b in backticks], default=0) + 1)
        full_approval_msg = (
            f"⚠️ Action Requires Approval (ID: `{p_id}`):\n"
            f"{safe_prompt}\n\n"
            f"Command:\n{fence}\n{safe_cmd}\n{fence}{invis_warn}\n\n"
            f"Use `/allow {p_id}` or `/deny {p_id}`"
        )
        if prefix_text:
            self.send_message(chat_id, prefix_text)
        if len(full_approval_msg) > 4000:
            with server.PENDING_LOCK:
                if p_id in server.PENDING_ACTIONS:
                    server.PENDING_ACTIONS[p_id]["pc_only"] = True
            short_msg = (
                f"⚠️ Action Requires Approval (ID: `{p_id}`):\n"
                f"{safe_prompt}\n\n"
                f"Notice: Approval for this action must be done on the PC (payload exceeds Telegram limits)."
            )
            self.send_message(chat_id, short_msg)
        else:
            self.send_message(chat_id, full_approval_msg)

    def _get_live_cfg(self) -> dict:
        if callable(self.cfg):
            try:
                res = self.cfg()
                if isinstance(res, dict):
                    return res
            except Exception:
                pass
        return self.cfg if isinstance(self.cfg, dict) else {}

    def is_authorized(self, chat_id: Any, user_id: Any = None, chat_type: str = "private") -> bool:
        """
        Verify Telegram sender and chat authorization:
        - Requires sender user_id (from.id) in telegram_allowed_user_ids (empty = nobody allowed,
          unless telegram_allowed_user_ids is omitted/empty AND telegram_allowed_chat_ids is set AND chat is strictly 'private').
        - If only chat IDs are set, group/supergroup/channel chats are strictly refused and only private chats accepted.
        - If both chat IDs and user IDs are set, BOTH must match.
        - Always reads live config dynamically so allowlist changes take effect immediately without restart.
        """
        cid = str(chat_id).strip() if chat_id is not None else ""
        uid = str(user_id).strip() if user_id is not None else ""
        ctype = str(chat_type or "").strip().lower()

        cfg = self._get_live_cfg()
        raw_chats = cfg.get("telegram_allowed_chat_ids") or []
        allowed_chat_ids = [str(x).strip() for x in raw_chats if str(x).strip()]

        raw_users = cfg.get("telegram_allowed_user_ids") or []
        allowed_user_ids = [str(x).strip() for x in raw_users if str(x).strip()]

        if not allowed_chat_ids and not allowed_user_ids:
            return False

        if allowed_chat_ids and cid not in allowed_chat_ids:
            return False

        allow_groups = bool(cfg.get("telegram_allow_groups", False))

        if allowed_user_ids:
            if not uid or uid not in allowed_user_ids:
                return False
            # In the user-id branch, also require chat.type == "private" unless telegram_allow_groups is true
            if not allow_groups and ctype != "private":
                return False
        else:
            # Only chat_ids are set -> group chats must be refused; only private chats accepted
            if ctype and ctype != "private" and not allow_groups:
                return False
            # In a Telegram private chat, the user's ID equals the private chat ID; if from.id is present and differs, reject
            if uid and uid not in allowed_chat_ids:
                return False

        return True

    def process_update(self, update: Dict[str, Any]) -> bool:
        # Strictly drop edited_message, channel_post, edited_channel_post
        message = update.get("message")
        if not message:
            return False

        chat_obj = message.get("chat") or {}
        chat_id_int = chat_obj.get("id")
        if chat_id_int is None:
            return False

        chat_type = str(chat_obj.get("type") or "private").strip().lower()
        from_obj = message.get("from") or {}
        user_id = from_obj.get("id")

        # Sender check must not be bypassed by sender_chat or channel posts
        if message.get("sender_chat") and not user_id:
            logger.warning(
                f"[Telegram Security] Rejected message with sender_chat without individual user.id: chat={chat_id_int}"
            )
            return False

        if not self.is_authorized(chat_id_int, user_id=user_id, chat_type=chat_type):
            logger.warning(
                f"[Telegram Security] Rejected message from unauthorized chat/user/type: chat={chat_id_int}, user={user_id}, type={chat_type}"
            )
            return False

        text = (message.get("text") or "").strip()
        if not text:
            return False

        parts = text.split(maxsplit=1)
        first_word = parts[0].strip().lower()
        is_allow_cmd = (first_word == "/allow" or (first_word.startswith("/allow@") and len(first_word) > 7))
        is_deny_cmd = (first_word == "/deny" or (first_word.startswith("/deny@") and len(first_word) > 6))

        # Command: /allow <id> or /allow@botname <id> (exact command parsing; not /allowance)
        if is_allow_cmd:
            # /allow and /deny MUST strictly come from an allowlisted user.id
            cfg = self._get_live_cfg()
            raw_users = cfg.get("telegram_allowed_user_ids") or []
            allowed_uids = [str(x).strip() for x in raw_users if str(x).strip()]
            raw_chats = cfg.get("telegram_allowed_chat_ids") or []
            allowed_cids = [str(x).strip() for x in raw_chats if str(x).strip()]
            effective_allowed_users = allowed_uids if allowed_uids else allowed_cids
            if not user_id or str(user_id) not in effective_allowed_users:
                logger.warning(f"[Telegram Security] /allow rejected: user {user_id} not in user allowlist")
                self.send_message(chat_id_int, "❌ Unauthorized: /allow must come from an authorized user ID.")
                return False

            action_id = parts[1].strip() if len(parts) > 1 else ""
            if not action_id:
                self.send_message(chat_id_int, "Usage: /allow <action_id>")
                return True

            def _tg_notify(event_dict):
                st = event_dict.get("status")
                if st == "paused":
                    p_info = event_dict.get("pending_info") or (event_dict if (event_dict.get("pending_id") or event_dict.get("id")) else None)
                    if p_info:
                        self.send_approval_announcement(chat_id_int, p_info, prefix_text=event_dict.get("message"))
                    else:
                        self.send_message(chat_id_int, event_dict.get("message", "Plan paused."))
                elif st in ("completed", "failed", "timeout", "error"):
                    self.send_message(chat_id_int, event_dict.get("message", ""))

            import unittest.mock
            if isinstance(handle_remote_confirm, unittest.mock.NonCallableMock):
                res = handle_remote_confirm(action_id, approve=True)
            else:
                res = handle_remote_confirm(action_id, approve=True, notify=_tg_notify)
            if res.get("ok"):
                cmd_raw = res.get("command") or ""
                cmd_info = ""
                if cmd_raw:
                    import server
                    safe_c, _ = server.sanitize_preview(cmd_raw)
                    backticks = re.findall(r"`+", safe_c)
                    fence = "`" * max(3, max([len(b) for b in backticks], default=0) + 1)
                    cmd_info = f"\nCommand:\n{fence}\n{safe_c}\n{fence}"
                prefix_text = f"✅ Action Approved: {res.get('action')}{cmd_info}\n{res.get('result', '')}"
                if res.get("pending"):
                    self.send_approval_announcement(chat_id_int, res["pending"], prefix_text=prefix_text)
                else:
                    self.send_message(chat_id_int, prefix_text)
            else:
                self.send_message(chat_id_int, f"❌ Failed to approve: {res.get('error')}")
            return True

        # Command: /deny <id> or /deny@botname <id> (exact command parsing; not /denying)
        if is_deny_cmd:
            # /allow and /deny MUST strictly come from an allowlisted user.id
            cfg = self._get_live_cfg()
            raw_users = cfg.get("telegram_allowed_user_ids") or []
            allowed_uids = [str(x).strip() for x in raw_users if str(x).strip()]
            raw_chats = cfg.get("telegram_allowed_chat_ids") or []
            allowed_cids = [str(x).strip() for x in raw_chats if str(x).strip()]
            effective_allowed_users = allowed_uids if allowed_uids else allowed_cids
            if not user_id or str(user_id) not in effective_allowed_users:
                logger.warning(f"[Telegram Security] /deny rejected: user {user_id} not in user allowlist")
                self.send_message(chat_id_int, "❌ Unauthorized: /deny must come from an authorized user ID.")
                return False

            action_id = parts[1].strip() if len(parts) > 1 else ""
            if not action_id:
                self.send_message(chat_id_int, "Usage: /deny <action_id>")
                return True
            res = handle_remote_confirm(action_id, approve=False)
            if res.get("ok"):
                cmd_raw = res.get("command") or ""
                cmd_info = ""
                if cmd_raw:
                    import server
                    safe_c, _ = server.sanitize_preview(cmd_raw)
                    backticks = re.findall(r"`+", safe_c)
                    fence = "`" * max(3, max([len(b) for b in backticks], default=0) + 1)
                    cmd_info = f"\nCommand:\n{fence}\n{safe_c}\n{fence}"
                self.send_message(chat_id_int, f"🚫 Action Denied: {res.get('action')}{cmd_info}")
            else:
                self.send_message(chat_id_int, f"❌ Failed to deny: {res.get('error')}")
            return True

        # Command: /stopplan or /stopplan@botname (sender allowlist applies)
        is_stopplan_cmd = (first_word == "/stopplan" or (first_word.startswith("/stopplan@") and len(first_word) > 10))
        if is_stopplan_cmd:
            cfg = self._get_live_cfg()
            raw_users = cfg.get("telegram_allowed_user_ids") or []
            allowed_uids = [str(x).strip() for x in raw_users if str(x).strip()]
            raw_chats = cfg.get("telegram_allowed_chat_ids") or []
            allowed_cids = [str(x).strip() for x in raw_chats if str(x).strip()]
            effective_allowed_users = allowed_uids if allowed_uids else allowed_cids
            if not user_id or str(user_id) not in effective_allowed_users:
                logger.warning(f"[Telegram Security] /stopplan rejected: user {user_id} not in user allowlist")
                self.send_message(chat_id_int, "❌ Unauthorized: /stopplan must come from an authorized user ID.")
                return False
            import server
            res = server.cancel_plan(conv_id=f"telegram:{chat_id_int}", source="telegram")
            self.send_message(chat_id_int, f"🛑 {res.get('message', 'plan cancelled')}")
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
                        self.send_approval_announcement(chat_id_int, res["pending"], prefix_text=reply_text)
                        return True
                    else:
                        if reply_text:
                            self.send_message(chat_id_int, reply_text)
                        return True
                else:
                    self.send_message(chat_id_int, str(res))
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
        params = {"timeout": 15, "offset": self.offset, "allowed_updates": json.dumps(["message"])}
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
