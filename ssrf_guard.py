"""
ssrf_guard.py - Unified Server-Side Request Forgery (SSRF) Protection & Secure HTTP Fetcher.

Provides:
- validate_url_target: parses URL, rejects non-http/https, userinfo, decimal/hex/octal forms,
  resolves DNS once, validates IP ranges (loopback, private, link-local, CGNAT 100.64/10, multicast,
  reserved, unspecified, own-interface, IPv4-mapped IPv6, NAT64 WKP, 6to4, Teredo), enforces
  explicit dev localhost port allowlist (dev_localhost_ports, default [3000, 3001, 4200, 5000, 5173, 8000, 8080]),
  and blocks sensitive ports (8765, 8766, CDP).
- safe_http_fetch: securely performs HTTP/HTTPS requests by connecting directly to the resolved IP,
  preserving Host header & SNI hostname verification, following redirects (max 3) with re-validation on every hop,
  capping response size, enforcing text-only content types, and wrapping output in <UNTRUSTED_TOOL_OUTPUT>.
"""

from __future__ import annotations

import html
import http.client
import ipaddress
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import threading
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

DEFAULT_DEV_LOCALHOST_PORTS: List[int] = [3000, 3001, 4200, 5000, 5173, 8000, 8080]


def wrap_untrusted_tool_output(data: Any, max_chars: int = 6000) -> str:
    """Wraps raw tool feedback in <UNTRUSTED_TOOL_OUTPUT> blocks with safety neutralizations."""
    if data is None:
        return ""
    text = str(data)
    # 1. Neutralize [[ and ]]
    text = text.replace("[[", "([").replace("]]", "])")
    # 2. Strip angle brackets
    text = text.replace("<", "").replace(">", "")
    # 3. Enforce maximum character cap
    if len(text) > max_chars:
        text = text[:max_chars]
    return f"<UNTRUSTED_TOOL_OUTPUT>\n{text}\n</UNTRUSTED_TOOL_OUTPUT>"


def get_dev_localhost_ports(cfg: Optional[Dict[str, Any]] = None) -> Set[int]:
    """Returns the set of explicitly allowed local development server ports."""
    if cfg and "dev_localhost_ports" in cfg:
        raw = cfg.get("dev_localhost_ports")
        if isinstance(raw, (list, tuple, set)):
            ports: Set[int] = set()
            for p in raw:
                try:
                    ports.add(int(p))
                except (ValueError, TypeError):
                    pass
            if ports:
                return ports
    return set(DEFAULT_DEV_LOCALHOST_PORTS)


def get_blocked_ports(cfg: Optional[Dict[str, Any]] = None) -> Set[int]:
    """Returns the set of forbidden local service ports (Nova web, remote, CDP)."""
    blocked: Set[int] = {8765, 8766}
    if cfg:
        try:
            blocked.add(int(cfg.get("port", 8765)))
        except (ValueError, TypeError):
            pass
        try:
            blocked.add(int(cfg.get("remote_port", 8766)))
        except (ValueError, TypeError):
            pass

    # CDP port detection
    try:
        import nova_browser
        cdp_p = getattr(nova_browser, "CDP_PORT", None)
        if cdp_p:
            blocked.add(int(cdp_p))
    except Exception:
        pass

    try:
        cdp_file = Path(__file__).resolve().parent / ".cdp_port"
        if cdp_file.exists():
            val = cdp_file.read_text(encoding="utf-8").strip()
            if val.isdigit():
                blocked.add(int(val))
    except Exception:
        pass

    return blocked


def get_own_interface_ips() -> Set[str]:
    """Enumerates local host interface IPs to prevent self-targeting."""
    ips: Set[str] = set()
    try:
        hostname = socket.gethostname()
        for res in socket.getaddrinfo(hostname, None):
            ips.add(res[4][0])
    except Exception:
        pass
    return ips


def check_ip_security(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    port: int,
    allow_localhost_dev: bool = False,
    dev_localhost_ports: Optional[Set[int]] = None,
    blocked_ports: Optional[Set[int]] = None,
) -> Optional[str]:
    """
    Validates an IP address against forbidden network ranges:
    - IPv4-mapped IPv6 (::ffff:x.x.x.x)
    - NAT64 Well-Known Prefix (64:ff9b::/96)
    - 6to4 prefix (2002::/16)
    - Teredo prefix (2001::/32)
    - Loopback (with strict explicit port allowlist)
    - Link-local (cloud metadata)
    - Private RFC 1918 / RFC 4193
    - CGNAT (100.64.0.0/10)
    - Multicast, reserved, unspecified, own-interface
    Returns None if safe, or an error string if forbidden.
    """
    blocked_ports = blocked_ports or {8765, 8766}
    allowed_dev_ports = (
        (dev_localhost_ports if dev_localhost_ports is not None else set(DEFAULT_DEV_LOCALHOST_PORTS))
        - blocked_ports
    )

    # 1. IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1, ::ffff:10.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return check_ip_security(ip.ipv4_mapped, port, allow_localhost_dev, dev_localhost_ports, blocked_ports)

    # 2. NAT64 Well-Known Prefix (RFC 6052: 64:ff9b::/96)
    if isinstance(ip, ipaddress.IPv6Address) and ip in ipaddress.ip_network("64:ff9b::/96"):
        embedded_ipv4 = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        err = check_ip_security(embedded_ipv4, port, allow_localhost_dev, dev_localhost_ports, blocked_ports)
        if err:
            return f"NAT64 embedded address ({embedded_ipv4}) is forbidden: {err}"

    # 3. 6to4 Prefix (RFC 3056: 2002::/16)
    if isinstance(ip, ipaddress.IPv6Address) and ip in ipaddress.ip_network("2002::/16"):
        embedded_ipv4 = ipaddress.IPv4Address((int(ip) >> 80) & 0xFFFFFFFF)
        err = check_ip_security(embedded_ipv4, port, allow_localhost_dev, dev_localhost_ports, blocked_ports)
        if err:
            return f"6to4 embedded address ({embedded_ipv4}) is forbidden: {err}"

    # 4. Teredo Prefix (RFC 4380: 2001::/32)
    if isinstance(ip, ipaddress.IPv6Address) and ip in ipaddress.ip_network("2001::/32"):
        teredo_info = ip.teredo
        if teredo_info:
            server_ip, client_ip = teredo_info
            err_server = check_ip_security(server_ip, port, allow_localhost_dev, dev_localhost_ports, blocked_ports)
            if err_server:
                return f"Teredo server address ({server_ip}) is forbidden: {err_server}"
            err_client = check_ip_security(client_ip, port, allow_localhost_dev, dev_localhost_ports, blocked_ports)
            if err_client:
                return f"Teredo client address ({client_ip}) is forbidden: {err_client}"
        # Also check raw lower 32 bits
        raw_lower_ipv4 = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        err_raw = check_ip_security(raw_lower_ipv4, port, allow_localhost_dev, dev_localhost_ports, blocked_ports)
        if err_raw:
            return f"Teredo embedded address ({raw_lower_ipv4}) is forbidden: {err_raw}"

    # 5. Localhost / Loopback policy
    if ip.is_loopback:
        if allow_localhost_dev:
            if port in blocked_ports:
                return f"Loopback connection to port {port} is blocked (Nova / CDP service port)."
            if port in allowed_dev_ports:
                return None  # Permitted dev localhost port
            return f"Loopback port {port} is not in allowed dev ports {sorted(list(allowed_dev_ports))}."
        return "Loopback address (127.0.0.0/8, ::1) is forbidden."

    # 6. Port restriction for any other address (never Nova or CDP)
    if port in blocked_ports:
        return f"Destination port {port} is blocked (Nova / CDP service port)."

    # 7. Prohibited IP ranges
    if ip.is_link_local:
        return f"Link-local address ({ip}) is forbidden."
    if ip.is_private:
        return f"Private network address ({ip}) is forbidden."
    if ip.is_multicast:
        return f"Multicast address ({ip}) is forbidden."
    if ip.is_reserved:
        return f"Reserved address ({ip}) is forbidden."
    if ip.is_unspecified:
        return f"Unspecified address ({ip}) is forbidden."

    # CGNAT range: 100.64.0.0/10
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
        return f"Carrier-Grade NAT address ({ip}) is forbidden."

    # Host own-interface IPs
    try:
        if str(ip) in get_own_interface_ips():
            return f"Host own-interface address ({ip}) is forbidden."
    except Exception:
        pass

    return None


def validate_url_target(
    url: str,
    allow_localhost_dev: bool = False,
    dev_localhost_ports: Optional[Set[int]] = None,
    blocked_ports: Optional[Set[int]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    custom_resolver: Optional[Callable[[str, int], list]] = None,
    dns_timeout: float = 5.0,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validates a URL target against SSRF vulnerabilities:
    - Enforces http/https only
    - Rejects userinfo (@)
    - Rejects decimal/hex/octal IP obfuscations
    - Resolves hostname once and inspects all resolved IP addresses (refuses if ANY are insecure)
    - Enforces dev_localhost_ports allowlist on loopback dev connections
    - Returns (is_valid, error_reason, target_info)
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string.", None

    url_str = url.strip()
    try:
        parsed = urllib.parse.urlsplit(url_str)
    except Exception as e:
        return False, f"Failed to parse URL: {e}", None

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"Refused: Scheme '{scheme}' is not allowed. Only http:// and https:// URLs are permitted.", None

    # Reject userinfo: user@host, user:pass@host
    if parsed.username or parsed.password or ("@" in (parsed.netloc.split("/")[0] if parsed.netloc else "")):
        return False, "Refused: URLs containing userinfo (username/password or '@') are forbidden.", None

    raw_host = parsed.hostname
    if not raw_host:
        return False, "Refused: Missing hostname in URL.", None

    host = raw_host.strip("[]").strip()

    # Reject decimal IP form (e.g. 2130706433)
    if host.isdigit():
        return False, f"Refused: Decimal integer IP representation '{host}' is forbidden.", None

    # Reject hex / octal IP form (e.g. 0x7f000001, 0o17700000001)
    if host.lower().startswith(("0x", "0o")):
        return False, f"Refused: Hexadecimal or octal IP representation '{host}' is forbidden.", None

    # Reject dotted decimal variations with leading zeros (octal) or hex parts (e.g. 0177.0.0.1, 127.1, 0x7f.0.0.1)
    parts = host.split(".")
    if len(parts) in (2, 3, 4) and all(p.isdigit() or p.lower().startswith("0x") for p in parts):
        if len(parts) < 4 or any((len(p) > 1 and p.startswith("0") and p.isdigit()) or p.lower().startswith("0x") for p in parts):
            return False, f"Refused: Non-standard / octal / hex IP representation '{host}' is forbidden.", None

    port = parsed.port
    if not port:
        port = 443 if scheme == "https" else 80

    ports_to_block = blocked_ports if blocked_ports is not None else get_blocked_ports(cfg)
    allowed_dev_ports = (
        (dev_localhost_ports if dev_localhost_ports is not None else get_dev_localhost_ports(cfg))
        - ports_to_block
    )

    # Check for direct loopback hostname
    is_direct_loopback_host = (host.lower() in ("localhost", "127.0.0.1", "::1"))
    if is_direct_loopback_host and not allow_localhost_dev:
        return False, "SSRF Protection: Loopback address (127.0.0.0/8, ::1) is forbidden.", None
    if is_direct_loopback_host:
        if port in ports_to_block:
            return False, f"SSRF Protection: Loopback connection to port {port} is blocked (Nova / CDP service port).", None
        if port not in allowed_dev_ports:
            return False, f"SSRF Protection: Loopback port {port} is not in allowed dev ports {sorted(list(allowed_dev_ports))}.", None

    # DNS Resolution
    if custom_resolver:
        try:
            addr_info = custom_resolver(host, port)
        except Exception as e:
            return False, f"DNS resolution failed for '{host}': {e}", None
    else:
        res_container = []
        exc_container = []

        def _resolve_worker():
            try:
                res = socket.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
                res_container.append(res)
            except Exception as ex:
                exc_container.append(ex)

        t = threading.Thread(target=_resolve_worker, daemon=True)
        t.start()
        t.join(dns_timeout)
        if t.is_alive():
            return False, f"DNS resolution timed out after {dns_timeout}s for '{host}'.", None
        if exc_container:
            return False, f"DNS resolution failed for '{host}': {exc_container[0]}", None
        if not res_container or not res_container[0]:
            return False, f"No IP addresses resolved for '{host}'.", None
        addr_info = res_container[0]

    if not addr_info:
        return False, f"No IP addresses resolved for '{host}'.", None

    resolved_ips = [entry[4][0] for entry in addr_info]

    # Validate EVERY resolved IP address - if ANY IP is insecure, refuse!
    for ip_str in resolved_ips:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"Invalid resolved IP '{ip_str}'.", None

        err = check_ip_security(
            ip_obj,
            port,
            allow_localhost_dev=allow_localhost_dev,
            dev_localhost_ports=allowed_dev_ports,
            blocked_ports=ports_to_block,
        )
        if err:
            return False, f"SSRF Protection: {err}", None

    path_query = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")

    return True, "", {
        "url": url_str,
        "scheme": scheme,
        "hostname": host,
        "port": port,
        "ip": resolved_ips[0],
        "resolved_ips": resolved_ips,
        "path": path_query,
        "parsed": parsed,
    }


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that connects directly to a pre-resolved IP while enforcing SNI hostname and cert verification."""
    def __init__(self, ip: str, port: int, hostname: str, timeout: float = 10.0, context: Optional[ssl.SSLContext] = None):
        super().__init__(ip, port, timeout=timeout, context=context)
        self._server_hostname = hostname

    def connect(self):
        super(http.client.HTTPSConnection, self).connect()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self._server_hostname)


def safe_http_fetch(
    url: str,
    timeout: float = 15.0,
    max_size: int = 6000,
    max_redirects: int = 3,
    allow_localhost_dev: bool = False,
    dev_localhost_ports: Optional[Set[int]] = None,
    wrap_output: bool = True,
    blocked_ports: Optional[Set[int]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    custom_resolver: Optional[Callable[[str, int], list]] = None,
    dns_timeout: float = 5.0,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Executes a hardened HTTP/HTTPS GET request with strict SSRF defense:
    - Resolves hostname once and connects directly to the pinned IP (preserving Host header & SNI hostname verification)
    - Re-validates every redirect hop (up to max_redirects)
    - Enforces text-only content types
    - Caps response size at max_size
    - Wraps output in <UNTRUSTED_TOOL_OUTPUT> if wrap_output is True
    - Enforces total deadline across connect, headers, and body reading (default 15.0s)
    """
    current_url = url
    headers = {
        "User-Agent": "NovaAI/1.0",
        "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*;q=0.8",
    }
    ports_to_block = blocked_ports if blocked_ports is not None else get_blocked_ports(cfg)
    allowed_dev_ports = (
        (dev_localhost_ports if dev_localhost_ports is not None else get_dev_localhost_ports(cfg))
        - ports_to_block
    )

    deadline = time.time() + timeout

    for hop in range(max_redirects + 1):
        rem = deadline - time.time()
        if rem <= 0:
            return False, f"Total fetch deadline exceeded ({timeout}s)", {}

        cur_dns_timeout = min(dns_timeout, rem)
        ok, reason, target = validate_url_target(
            current_url,
            allow_localhost_dev=allow_localhost_dev,
            dev_localhost_ports=allowed_dev_ports,
            blocked_ports=ports_to_block,
            cfg=cfg,
            custom_resolver=custom_resolver,
            dns_timeout=cur_dns_timeout,
        )
        if not ok or not target:
            return False, f"Refused by SSRF Protection: {reason}", {}

        rem = deadline - time.time()
        if rem <= 0:
            return False, f"Total fetch deadline exceeded ({timeout}s)", {}

        ip = target["ip"]
        port = target["port"]
        scheme = target["scheme"]
        hostname = target["hostname"]
        path = target["path"]

        req_headers = dict(headers)
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            req_headers["Host"] = hostname
        else:
            req_headers["Host"] = f"{hostname}:{port}"

        try:
            conn_timeout = max(0.001, rem)
            if scheme == "https":
                ctx = ssl.create_default_context()
                conn: http.client.HTTPConnection = PinnedHTTPSConnection(ip, port, hostname, timeout=conn_timeout, context=ctx)
            else:
                conn = http.client.HTTPConnection(ip, port, timeout=conn_timeout)

            conn.request("GET", path, headers=req_headers)
            resp = conn.getresponse()

            # Handle redirects (301, 302, 303, 307, 308)
            if resp.status in (301, 302, 303, 307, 308):
                location = resp.getheader("Location")
                conn.close()
                if not location:
                    return False, f"HTTP {resp.status} redirect without Location header from {current_url}", {}
                if hop >= max_redirects:
                    return False, f"Too many redirects (exceeded maximum of {max_redirects} hops)", {}
                current_url = urllib.parse.urljoin(current_url, location)
                continue

            if resp.status >= 400:
                conn.close()
                return False, f"HTTP Error {resp.status}: {resp.reason}", {"status": resp.status}

            # Enforce text-only Content-Type
            ctype = (resp.getheader("Content-Type") or "").lower()
            allowed_text_types = (
                "text/",
                "application/json",
                "application/xml",
                "application/xhtml+xml",
                "application/javascript",
                "application/rss+xml",
                "application/atom+xml",
            )
            if ctype and not any(ctype.startswith(t) or t in ctype for t in allowed_text_types):
                conn.close()
                return False, f"Refused: non-text Content-Type '{ctype}'. Only text content is permitted.", {"status": resp.status}

            # Enforce deadline while reading body chunks
            raw_chunks = []
            bytes_read = 0
            while bytes_read < max_size + 1:
                cur_rem = deadline - time.time()
                if cur_rem <= 0:
                    conn.close()
                    return False, f"Total fetch deadline exceeded ({timeout}s)", {}
                if hasattr(conn, "sock") and conn.sock:
                    try:
                        conn.sock.settimeout(cur_rem)
                    except Exception:
                        pass
                chunk = resp.read(min(1024, max_size + 1 - bytes_read))
                if not chunk:
                    break
                raw_chunks.append(chunk)
                bytes_read += len(chunk)
                if time.time() > deadline:
                    conn.close()
                    return False, f"Total fetch deadline exceeded ({timeout}s)", {}

            raw_data = b"".join(raw_chunks)
            conn.close()

            truncated = len(raw_data) > max_size
            raw_data = raw_data[:max_size]
            text = raw_data.decode("utf-8", errors="replace")

            if wrap_output:
                output_text = wrap_untrusted_tool_output(text, max_chars=max_size)
            else:
                output_text = text

            return True, output_text, {
                "status": resp.status,
                "headers": dict(resp.getheaders()),
                "url": current_url,
                "truncated": truncated,
            }

        except Exception as e:
            if time.time() >= (deadline - 0.2) or isinstance(e, (socket.timeout, TimeoutError, http.client.IncompleteRead)):
                return False, f"Total fetch deadline exceeded ({timeout}s): {e}", {}
            return False, f"Failed to fetch {current_url}: {e}", {}

    return False, f"Too many redirects (exceeded maximum of {max_redirects} hops)", {}
