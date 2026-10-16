"""Reject private, loopback, and other non-public HTTP destinations."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
}


class UnsafeURL(ValueError):
    """The URL is not a public http(s) destination."""


def _ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _ip_allowed(mapped)
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return False
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return False
    if not ip.is_global:
        return False
    return True


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if host.isdigit():
        try:
            value = int(host)
        except ValueError:
            return None
        if 0 <= value <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(value)
    return None


def _host_ips(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURL(f"could not resolve host {host!r}") from exc
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        addresses.append(str(sockaddr[0]))
    if not addresses:
        raise UnsafeURL(f"could not resolve host {host!r}")
    return addresses


def public_http_url(url: str, *, reason: str = "url", resolve_dns: bool = True) -> str:
    """Return the URL if it is public http(s). Raise UnsafeURL otherwise.

    Re-check this after every redirect and immediately before connect.
    DNS answers are inspected when resolve_dns is true; loopback, private,
    link-local, multicast, reserved, IPv4-mapped, decimal, and credentialed
    URLs are rejected. Listing a cited URL as a graph candidate may skip
    DNS; fetch still resolves before connect.
    """
    raw = (url or "").strip()
    if not raw or raw.lower().startswith("urn:"):
        raise UnsafeURL(f"{reason} is empty or not http(s)")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURL(f"{reason} must be http or https")
    try:
        username = parsed.username
        password = parsed.password
        host = (parsed.hostname or "").strip().lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURL(f"{reason} has a malformed host or port") from exc
    if username is not None or password is not None:
        raise UnsafeURL(f"{reason} must not include credentials")
    if not host:
        raise UnsafeURL(f"{reason} has no host")
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise UnsafeURL(f"{reason} host {host} is not public")
    literal = _literal_ip(host)
    if literal is not None and not _ip_allowed(literal):
        raise UnsafeURL(f"{reason} address {host} is not public")
    port = port or (443 if parsed.scheme == "https" else 80)
    if literal is None and resolve_dns:
        for address in _host_ips(host, port):
            ip = ipaddress.ip_address(address)
            if not _ip_allowed(ip):
                raise UnsafeURL(f"{reason} resolved {host} to non-public {address}")
    return raw


def redirect_target(current: str, location: str | None) -> str:
    if not location:
        raise UnsafeURL("redirect with no Location")
    nxt = urljoin(current, location)
    return public_http_url(nxt, reason="redirect")
