"""Test dedup helper functions from app.modules.crawler.service."""
import pytest

import app.modules.crawler.service as svc

# Access module-private functions for testing
_normalize_url = svc._normalize_url
_simhash = svc._simhash
_hamming_distance = svc._hamming_distance


# =========================================================================
# URL Normalization
# =========================================================================


class TestNormalizeUrl:
    """Tests for _normalize_url — URL tracking-param stripping."""

    def test_remove_utm_source(self):
        url = "https://example.com/page?utm_source=twitter&id=123"
        assert _normalize_url(url) == "https://example.com/page?id=123"

    def test_remove_all_utm_params(self):
        url = "https://example.com/page?utm_source=twitter&utm_medium=social&utm_campaign=spring"
        assert _normalize_url(url) == "https://example.com/page"

    def test_remove_fbclid(self):
        url = "https://example.com/page?fbclid=abc&q=search"
        assert _normalize_url(url) == "https://example.com/page?q=search"

    def test_remove_gclid(self):
        url = "https://example.com/page?gclid=xyz&foo=bar"
        assert _normalize_url(url) == "https://example.com/page?foo=bar"

    def test_remove_multiple_tracking_types(self):
        url = "https://example.com/page?utm_source=twitter&fbclid=abc&gclid=xyz&keep=stay"
        assert _normalize_url(url) == "https://example.com/page?keep=stay"

    def test_no_params_unchanged(self):
        url = "https://example.com/page"
        assert _normalize_url(url) == url

    def test_no_tracking_params_unchanged(self):
        url = "https://example.com/page?q=search&page=1"
        assert _normalize_url(url) == url

    def test_invalid_url_returns_original(self):
        url = "not a valid url"
        assert _normalize_url(url) == url

    def test_empty_string(self):
        assert _normalize_url("") == ""

    def test_referrer_param_removed(self):
        url = "https://example.com/page?ref=direct&id=42"
        assert _normalize_url(url) == "https://example.com/page?id=42"


# =========================================================================
# SimHash
# =========================================================================


class TestSimHash:
    """Tests for _simhash — text fingerprinting."""

    def test_similar_texts_closer_than_different(self):
        """Similar texts have smaller Hamming distance than very different texts."""
        text_sim_a = "Climate change impacts global weather patterns"
        text_sim_b = "Climate change impacts global weather pattern"
        text_diff = "Stock market reaches new record highs today"
        h_sim_a = _simhash(text_sim_a)
        h_sim_b = _simhash(text_sim_b)
        h_diff = _simhash(text_diff)
        assert h_sim_a is not None and h_sim_b is not None and h_diff is not None
        dist_similar = _hamming_distance(h_sim_a, h_sim_b)
        dist_different = _hamming_distance(h_sim_a, h_diff)
        assert dist_similar < dist_different, (
            f"Similar texts ({dist_similar}) should be closer than different ({dist_different})"
        )

    def test_different_texts_produce_different_hashes(self):
        """Very different texts produce different hash values."""
        h1 = _simhash("Climate change impacts global weather patterns")
        h2 = _simhash("Stock market reaches new record highs today")
        assert h1 is not None and h2 is not None
        assert h1 != h2

    def test_empty_text_returns_none(self):
        assert _simhash("") is None

    def test_whitespace_text_returns_none(self):
        assert _simhash("   ") is None

    def test_short_text_produces_hash(self):
        h = _simhash("a")
        assert h is not None
        assert isinstance(h, int)

    def test_identical_texts_same_hash(self):
        assert _simhash("Hello World") == _simhash("Hello World")

    def test_chinese_text_produces_hash(self):
        """Two or more consecutive CJK characters are treated as a word."""
        h = _simhash("你好世界")
        assert h is not None
        assert isinstance(h, int)

    def test_single_chinese_char_no_hash(self):
        """Single CJK character does not satisfy the {2,} quantifier."""
        assert _simhash("你") is None

    def test_non_alpha_only_no_hash(self):
        """Text with no letters or Chinese bigrams returns None."""
        assert _simhash("!!!123###") is None


# =========================================================================
# Hamming Distance
# =========================================================================


class TestHammingDistance:
    """Tests for _hamming_distance."""

    def test_same_value_distance_zero(self):
        assert _hamming_distance(0, 0) == 0
        assert _hamming_distance(0b10101010, 0b10101010) == 0

    def test_single_bit_flip(self):
        assert _hamming_distance(0b0001, 0b0000) == 1
        assert _hamming_distance(0b0010, 0b0000) == 1
        assert _hamming_distance(0b10000000, 0b00000000) == 1

    def test_multiple_bit_differences(self):
        assert _hamming_distance(0b1111, 0b0000) == 4
        assert _hamming_distance(0b1010, 0b0101) == 4

    def test_symmetric(self):
        """Distance is symmetric: distance(x, y) == distance(y, x)."""
        pairs = [
            (0b1010, 0b0101),
            (0b11001100, 0b00110011),
            (123456789, 987654321),
        ]
        for x, y in pairs:
            assert _hamming_distance(x, y) == _hamming_distance(y, x), (
                f"Hamming distance not symmetric for ({x}, {y})"
            )

    def test_large_values(self):
        """63-bit number XOR 0 produces distance 63."""
        val = (1 << 63) - 1  # 63 bits all set to 1
        assert _hamming_distance(val, 0) == 63
