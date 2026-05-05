"""Tests for anti_detection module.

Covers: blocking detection (Cloudflare, rate-limit, CAPTCHA, generic),
        stealth helper functions.
"""
import pytest

from app.modules.crawler.anti_detection import (
    DetectionResult,
    build_stealth_scripts,
    detect_blocking,
    random_viewport,
)


class TestDetectBlocking:
    """Three-tier blocking detection."""

    def test_cloudflare_challenge_page(self):
        html = "<html><body>Checking your browser before accessing example.com. cf-ray: abc123</body></html>"
        result = detect_blocking(html, status_code=200, headers={})
        assert result.blocked is True
        assert result.block_type == "cloudflare"
        assert result.confidence >= 0.9

    def test_cloudflare_by_header(self):
        html = "<html><body>Some content</body></html>"
        result = detect_blocking(html, status_code=200, headers={"CF-Ray": "abc123"})
        assert result.blocked is True
        assert result.block_type == "cloudflare"

    def test_cloudflare_cookie(self):
        html = "<html>__cf_bm=somevalue</html>"
        result = detect_blocking(html, status_code=200, headers={})
        assert result.blocked is True
        assert result.block_type == "cloudflare"

    def test_datadome(self):
        html = "<html><body><script src='https://dd.interstitial.js'></script></body></html>"
        result = detect_blocking(html, status_code=200, headers={})
        assert result.blocked is True
        assert result.block_type == "cloudflare"

    def test_captcha(self):
        html = "<html><body><div class='g-recaptcha'></div></body></html>"
        result = detect_blocking(html, status_code=200, headers={})
        assert result.blocked is True
        assert result.block_type == "captcha"

    def test_ratelimit_429(self):
        html = "<html><body>Too many requests</body></html>"
        result = detect_blocking(html, status_code=429, headers={})
        assert result.blocked is True
        assert result.block_type == "ratelimit"
        assert result.confidence >= 0.9

    def test_403_short_page(self):
        html = "<html><body>Forbidden</body></html>"
        result = detect_blocking(html, status_code=403, headers={})
        assert result.blocked is True
        assert result.block_type == "generic"

    def test_503_short_page(self):
        html = "<html><body>Service Unavailable</body></html>"
        result = detect_blocking(html, status_code=503, headers={})
        assert result.blocked is True
        assert result.block_type == "generic"

    def test_generic_block_keywords(self):
        html = (
            "<html><body>"
            "Access denied. Your IP has been blocked due to unusual traffic. "
            "We detected automated requests from your network."
            "</body></html>"
        )
        result = detect_blocking(html, status_code=200, headers={})
        assert result.blocked is True
        assert result.block_type == "generic"

    def test_normal_page_passes(self):
        html = (
            "<html><head><title>Article Title</title></head>"
            "<body><article>"
            + "<p>This is a long article with substantial content that should not trigger any blocking detection. "
            "It contains many paragraphs and real content. "
            "</p>" * 20
            + "</article></body></html>"
        )
        result = detect_blocking(html, status_code=200, headers={})
        assert result.blocked is False

    def test_empty_html(self):
        result = detect_blocking("", status_code=200, headers={})
        assert result.blocked is False

    def test_200_short_page_suspicious(self):
        html = "<html><body>OK</body></html>"
        result = detect_blocking(html, status_code=200, headers={})
        assert result.blocked is True
        assert result.block_type == "generic"
        assert result.confidence == 0.5

    def test_200_very_short_no_block(self):
        """Extremely short page with 200 should be flagged as suspicious."""
        html = "<html><body></body></html>"
        result = detect_blocking(html, status_code=200, headers={})
        assert result.blocked is True


class TestStealthHelpers:
    """Stealth script generation and viewport randomization."""

    def test_build_stealth_scripts_returns_list(self):
        scripts = build_stealth_scripts()
        assert isinstance(scripts, list)
        assert len(scripts) > 0
        for s in scripts:
            assert isinstance(s, str)
            assert len(s) > 0

    def test_build_stealth_scripts_contains_webdriver_hiding(self):
        scripts = build_stealth_scripts()
        combined = " ".join(scripts)
        assert "webdriver" in combined.lower()

    def test_build_stealth_scripts_contains_webgl(self):
        scripts = build_stealth_scripts()
        combined = " ".join(scripts)
        assert "WebGLRenderingContext" in combined

    def test_random_viewport(self):
        vp = random_viewport()
        assert "width" in vp
        assert "height" in vp
        assert vp["width"] > 0
        assert vp["height"] > 0

    def test_random_viewport_varies(self):
        """Viewport should vary across calls (probabilistic)."""
        vps = [random_viewport() for _ in range(20)]
        unique = {tuple(v.items()) for v in vps}
        assert len(unique) > 1


class TestDetectionResult:
    def test_is_cloudflare(self):
        r = DetectionResult(blocked=True, block_type="cloudflare", confidence=0.9)
        assert r.is_cloudflare() is True
        assert r.is_ratelimit() is False
        assert r.is_captcha() is False

    def test_is_ratelimit(self):
        r = DetectionResult(blocked=True, block_type="ratelimit", confidence=0.9)
        assert r.is_ratelimit() is True
        assert r.is_cloudflare() is False

    def test_is_captcha(self):
        r = DetectionResult(blocked=True, block_type="captcha", confidence=0.9)
        assert r.is_captcha() is True
