"""Anti-detection: blocking detection + stealth enhancement helpers.

Detects Cloudflare, rate-limiting, CAPTCHA, and generic blocks from
rendered page HTML, status codes, and response headers.
"""
import logging
import random
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Cloudflare-specific markers
_CF_MARKERS = [
    "checking your browser",
    "cf-ray",
    "__cf_bm",
    "cf-browser-verification",
    "cloudflare",
    "please wait",
    "ddos protection",
]

# DataDome markers
_DD_MARKERS = [
    "datadome",
    "dd.interstitial",
]

# CAPTCHA markers (generic)
_CAPTCHA_MARKERS = [
    "captcha",
    "recaptcha",
    "g-recaptcha",
    "hcaptcha",
    "turnstile",
    "i'm not a robot",
    "verify you are human",
]

# Generic block page keywords (short HTML + block indicators)
_GENERIC_BLOCK_PATTERNS = [
    r"access\s*denied",
    r"forbidden",
    r"blocked",
    r"too\s*many\s*requests",
    r"your\s*ip\s*has\s*been\s*blocked",
    r"unusual\s*traffic",
    r"automated\s*requests",
]

# Minimum HTML length for a "real" page; shorter suggests block/interstitial
_MIN_REAL_PAGE_LENGTH = 800


@dataclass(frozen=True)
class DetectionResult:
    blocked: bool
    block_type: str | None = None
    confidence: float = 0.0

    def is_cloudflare(self) -> bool:
        return self.block_type == "cloudflare"

    def is_ratelimit(self) -> bool:
        return self.block_type == "ratelimit"

    def is_captcha(self) -> bool:
        return self.block_type == "captcha"


def detect_blocking(
    html: str,
    status_code: int = 200,
    headers: dict | None = None,
) -> DetectionResult:
    """Three-tier detection: vendor fingerprints → HTTP status → content heuristics."""
    if not html:
        return DetectionResult(blocked=False)

    text = html.lower()
    h = headers or {}
    headers_lower = {k.lower(): str(v).lower() for k, v in h.items()}

    # Tier 1: known vendor fingerprints
    cf_score = _score_markers(text, _CF_MARKERS)
    if cf_score >= 2 or "cf-ray" in headers_lower or "__cf_bm" in text:
        return DetectionResult(blocked=True, block_type="cloudflare", confidence=0.9)

    dd_score = _score_markers(text, _DD_MARKERS)
    if dd_score >= 1:
        return DetectionResult(blocked=True, block_type="cloudflare", confidence=0.85)

    captcha_score = _score_markers(text, _CAPTCHA_MARKERS)
    if captcha_score >= 2:
        return DetectionResult(blocked=True, block_type="captcha", confidence=0.85)

    # Tier 2: HTTP status codes
    if status_code == 429:
        return DetectionResult(blocked=True, block_type="ratelimit", confidence=0.9)
    if status_code in (403, 503) and len(html) < _MIN_REAL_PAGE_LENGTH * 2:
        # Short 403/503 → likely a block page
        return DetectionResult(blocked=True, block_type="generic", confidence=0.7)

    # Tier 3: generic content heuristics
    generic_score = sum(1 for p in _GENERIC_BLOCK_PATTERNS if re.search(p, text))
    if generic_score >= 2 and len(html) < _MIN_REAL_PAGE_LENGTH * 3:
        return DetectionResult(blocked=True, block_type="generic", confidence=0.6)

    # Very short page with no meaningful content → suspicious
    if len(html) < _MIN_REAL_PAGE_LENGTH:
        return DetectionResult(blocked=True, block_type="generic", confidence=0.5)

    return DetectionResult(blocked=False)


def _score_markers(text: str, markers: list[str]) -> int:
    return sum(1 for m in markers if m in text)


# ---------------------------------------------------------------------------
# Stealth enhancement helpers
# ---------------------------------------------------------------------------

_VIEWPORT_PRESETS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
    {"width": 1280, "height": 720},
]

_WEBGL_VENDORS = [
    ("Intel Inc.", "Intel Iris OpenGL Engine"),
    ("NVIDIA Corporation", "NVIDIA GeForce GTX 1050 Ti/PCIe/SSE2"),
    ("Apple Inc.", "Apple GPU"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
]


def random_viewport() -> dict:
    return random.choice(_VIEWPORT_PRESETS)


def random_webgl_fingerprint() -> tuple[str, str]:
    return random.choice(_WEBGL_VENDORS)


def build_stealth_scripts() -> list[str]:
    """Return enhanced stealth init scripts for Playwright context."""
    vendor, renderer = random_webgl_fingerprint()
    scripts = [
        # Hide navigator.webdriver
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true })",
        # Chrome object
        "window.chrome = { runtime: {} }",
        # Plugins
        "Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] })",
        # Languages
        "Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] })",
        # Permissions
        "window.navigator.permissions.query = (() => Promise.resolve({ state: 'granted' }))",
        # Hardware concurrency
        "Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 })",
        # Device memory
        "Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 })",
        # Notification permission
        "Object.defineProperty(Notification, 'permission', { get: () => 'default' })",
        # WebGL vendor/renderer
        f"""
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) return '{vendor}';
            if (parameter === 37446) return '{renderer}';
            return getParameter(parameter);
        }};
        """,
        # Timezone
        "Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', { value: function() { return { timeZone: 'Asia/Shanghai', locale: 'zh-CN' }; } })",
        # Notification API override
        "window.Notification = window.Notification || function() {};",
        # Permissions API override (more thorough)
        "if (window.navigator.permissions) { window.navigator.permissions.query = () => Promise.resolve({ state: 'granted' }); }",
    ]
    return scripts
