"""Tests for app.utils.url_validator.

Covers: protocol check, SSRF check (1024/::1/10.x/192.168), whitelist modes, validate_url().
"""
import asyncio
import socket
from unittest.mock import patch

import pytest

from app.utils.url_validator import (
    URLValidationError,
    AllowedRule,
    _check_protocol,
    _check_ssrf,
    _check_allowlist,
    validate_url,
)


class TestProtocolCheck:
    """_check_protocol: accepts http/https, rejects everything else."""

    def test_http_accepted(self):
        assert _check_protocol("http://example.com/path") == "example.com"

    def test_https_accepted(self):
        assert _check_protocol("https://example.com/path") == "example.com"

    @pytest.mark.parametrize("url", [
        "ftp://example.com",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,hello",
        "chrome://settings",
    ])
    def test_rejects_non_http_protocols(self, url):
        with pytest.raises(URLValidationError) as exc:
            _check_protocol(url)
        assert exc.value.code == 1003

    def test_missing_hostname_raises_1001(self):
        with pytest.raises(URLValidationError) as exc:
            _check_protocol("https:///path")
        assert exc.value.code == 1001


class TestSSRFCheck:
    """_check_ssrf: rejects private / loopback IPs, passes public IPs."""

    @pytest.mark.parametrize("family,addr", [
        (socket.AF_INET, ("127.0.0.1", 0)),
        (socket.AF_INET, ("10.1.2.3", 0)),
        (socket.AF_INET, ("192.168.1.1", 0)),
        (socket.AF_INET6, ("::1", 0, 0, 0)),
        (socket.AF_INET, ("169.254.1.1", 0)),
        (socket.AF_INET6, ("fc00::1", 0, 0, 0)),
    ])
    @pytest.mark.asyncio
    async def test_private_ip_rejected(self, family, addr):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", return_value=[(family, 0, 0, "", addr)]):
            with pytest.raises(URLValidationError) as exc:
                await _check_ssrf(f"host-{addr[0]}")
            assert exc.value.code == 1005

    @pytest.mark.asyncio
    async def test_public_ip_passes(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", return_value=[(socket.AF_INET, 0, 0, "", ("93.184.216.34", 0))]):
            await _check_ssrf("example.com")  # should not raise


class TestAllowlist:
    """_check_allowlist: exact / suffix / regex match modes."""

    def test_exact_match(self):
        _check_allowlist("example.com", [AllowedRule("example.com", "exact")])

    def test_exact_mismatch_raises_1004(self):
        with pytest.raises(URLValidationError) as exc:
            _check_allowlist("evil.com", [AllowedRule("example.com", "exact")])
        assert exc.value.code == 1004

    def test_suffix_matches_subdomain_and_apex(self):
        rule = AllowedRule("example.com", "suffix")
        _check_allowlist("sub.example.com", [rule])
        _check_allowlist("example.com", [rule])

    def test_suffix_mismatch(self):
        rule = AllowedRule("example.com", "suffix")
        with pytest.raises(URLValidationError):
            _check_allowlist("notexample.com", [rule])

    def test_regex_match(self):
        rule = AllowedRule(r"\.example\.(com|org)$", "regex")
        _check_allowlist("sub.example.com", [rule])
        _check_allowlist("test.example.org", [rule])

    def test_regex_mismatch(self):
        rule = AllowedRule(r"\.example\.(com|org)$", "regex")
        with pytest.raises(URLValidationError):
            _check_allowlist("sub.example.net", [rule])

    def test_invalid_regex_falls_back_to_no_match(self):
        rule = AllowedRule(r"[invalid", "regex")
        with pytest.raises(URLValidationError):
            _check_allowlist("anything.com", [rule])

    def test_no_matching_rule_raises_1004(self):
        rules = [AllowedRule("allowed.com", "exact"), AllowedRule("other.org", "suffix")]
        with pytest.raises(URLValidationError) as exc:
            _check_allowlist("evil.com", rules)
        assert exc.value.code == 1004


class TestValidateURL:
    """validate_url: integration of the three checks."""

    @pytest.mark.asyncio
    async def test_valid_url_returns_hostname(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", return_value=[(socket.AF_INET, 0, 0, "", ("93.184.216.34", 0))]):
            rules = [AllowedRule("example.com", "exact")]
            result = await validate_url("https://example.com/page?q=1#anchor", rules)
            assert result == "example.com"

    @pytest.mark.asyncio
    async def test_ssrf_blocks_localhost(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", return_value=[(socket.AF_INET, 0, 0, "", ("127.0.0.1", 0))]):
            rules = [AllowedRule("localhost", "exact")]
            with pytest.raises(URLValidationError) as exc:
                await validate_url("https://localhost", rules)
            assert exc.value.code == 1005
