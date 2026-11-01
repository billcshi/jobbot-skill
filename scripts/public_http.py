"""Bounded public HTTPS fetches, with DNS addresses pinned to the TLS socket."""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import quote, urljoin, urlparse, urlunparse


class FetchError(OSError):
    pass


def public_addresses(host):
    addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not addresses:
        raise FetchError("HTTPS host resolved to no addresses")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise FetchError(f"Refusing non-public host address: {address}")
    return addresses


def validate_url(raw):
    if not isinstance(raw, str) or any(ord(c) < 33 or ord(c) == 127 for c in raw):
        raise FetchError("HTTPS URL must not contain whitespace or control characters")
    parsed = urlparse(raw)
    try:
        port = parsed.port
    except ValueError as exc:
        raise FetchError("Invalid HTTPS port") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password or port not in (None, 443):
        raise FetchError("Only public HTTPS URLs on port 443 without embedded credentials are allowed")
    public_addresses(parsed.hostname)
    return urlunparse(parsed._replace(fragment=""))


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        if self._tunnel_host:
            raise FetchError("Implicit proxy tunnels are not supported")
        addresses = public_addresses(self.host)
        last_error = None
        for address in addresses[:8]:
            family = socket.AF_INET6 if ipaddress.ip_address(address).version == 6 else socket.AF_INET
            raw = socket.socket(family, socket.SOCK_STREAM)
            try:
                raw.settimeout(self.timeout)
                # A numeric socket address never resolves the hostname a second time.
                raw.connect((address, 443))
                peer = ipaddress.ip_address(raw.getpeername()[0])
                if not peer.is_global or peer != ipaddress.ip_address(address):
                    raise FetchError("HTTPS socket peer differs from the validated public address")
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                return
            except (OSError, ssl.SSLError) as exc:
                raw.close()
                last_error = exc
        raise FetchError(f"Could not connect to validated public HTTPS host: {last_error}")


def origin(url):
    parsed = urlparse(url)
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port or 443


def redirect_headers(headers, previous, following):
    if origin(previous) == origin(following):
        return dict(headers)
    sensitive = {"authorization", "proxy-authorization", "cookie", "cookie2", "host"}
    return {key: value for key, value in headers.items() if key.lower() not in sensitive}


def fetch(url, headers=None, *, max_bytes=2_000_000, max_redirects=5):
    current = validate_url(url)
    request_headers = {"User-Agent": "JobBotSkill/0.1", **(headers or {})}
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    for attempt in range(max_redirects + 1):
        parsed = urlparse(current)
        connection = PinnedHTTPSConnection(parsed.hostname, port=443, timeout=20, context=context)
        try:
            target = urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
            target = quote(target, safe="/:?@!$&'()*+,;=%-._~")
            connection.request("GET", target, headers=request_headers)
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location or attempt == max_redirects:
                    raise FetchError("Missing redirect location or too many HTTPS redirects")
                following = validate_url(urljoin(current, location))
                request_headers = redirect_headers(request_headers, current, following)
                current = following
                continue
            if not 200 <= response.status < 300:
                raise FetchError(f"HTTPS source returned status {response.status}")
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise FetchError(f"Remote response exceeded {max_bytes} bytes")
            return current, data, response.headers.get_content_type().lower(), response.headers.get_content_charset() or "utf-8"
        except http.client.HTTPException as exc:
            raise FetchError(f"HTTPS protocol failure: {exc}") from exc
        finally:
            connection.close()
    raise FetchError("Too many redirects")
