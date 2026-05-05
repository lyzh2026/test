"""URL 三层校验（PRD 2.1.2 / 5.2）：协议 → SSRF → 白名单。"""
import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

# RFC1918 + Loopback + Link-local + IPv6 等
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


@dataclass
class AllowedRule:
    domain_pattern: str
    match_mode: str  # exact | suffix | regex


class URLValidationError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _check_protocol(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise URLValidationError(1003, f"协议必须是 http/https：{url}")
    if not parsed.hostname:
        raise URLValidationError(1001, f"URL 缺少 host：{url}")
    return parsed.hostname


async def _check_ssrf(hostname: str) -> None:
    """DNS 解析后逐个 IP 校验。"""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise URLValidationError(1001, f"DNS 解析失败：{hostname} ({e})")
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                raise URLValidationError(1005, f"目标 IP 命中保留网段（SSRF 防护）：{hostname} → {ip_str}")


def _match_rule(hostname: str, rule: AllowedRule) -> bool:
    pattern = rule.domain_pattern.lower().strip()
    host = hostname.lower()
    if rule.match_mode == "exact":
        return host == pattern
    if rule.match_mode == "suffix":
        return host == pattern or host.endswith("." + pattern)
    if rule.match_mode == "regex":
        try:
            return re.search(pattern, host) is not None
        except re.error:
            return False
    return False


def _check_allowlist(hostname: str, rules: Iterable[AllowedRule]) -> None:
    for r in rules:
        if _match_rule(hostname, r):
            return
    raise URLValidationError(1004, f"域名不在白名单：{hostname}")


async def validate_url(url: str, rules: Iterable[AllowedRule]) -> str:
    """成功返回 hostname，失败抛 URLValidationError。"""
    hostname = _check_protocol(url)
    await _check_ssrf(hostname)
    _check_allowlist(hostname, rules)
    return hostname
