"""Tests for the LLM-based merchant categorizer."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from ingestion.categorizer import Categorizer


@pytest.fixture
def cache_file(tmp_path):
    """Return a path for the category cache file."""
    return tmp_path / "merchant_categories.json"


@pytest.fixture
def categorizer(cache_file):
    """Create a Categorizer with a mock OpenAI client."""
    with patch("ingestion.categorizer.OpenAI"):
        return Categorizer(cache_path=cache_file, openai_api_key="test-key")


@pytest.fixture
def seeded_cache(cache_file):
    """Write a pre-populated cache file and return its path."""
    data = {
        "Tesco": {"category": "Essentials", "subcategory": "Groceries"},
        "Shell": {"category": "Transport", "subcategory": "Fuel"},
    }
    cache_file.write_text(json.dumps(data))
    return cache_file


class TestCategorizerCache:
    """Tests for cache loading, saving, and usage."""

    def test_empty_cache_on_missing_file(self, categorizer):
        assert categorizer._cache == {}

    def test_loads_existing_cache(self, seeded_cache):
        with patch("ingestion.categorizer.OpenAI"):
            cat = Categorizer(cache_path=seeded_cache, openai_api_key="test-key")
        assert "Tesco" in cat._cache
        assert cat._cache["Tesco"]["subcategory"] == "Groceries"

    def test_save_cache_creates_file(self, categorizer, cache_file):
        categorizer._cache["Amazon"] = {
            "category": "Shopping",
            "subcategory": "Online Retail",
        }
        categorizer._save_cache()
        assert cache_file.exists()
        saved = json.loads(cache_file.read_text())
        assert saved["Amazon"]["subcategory"] == "Online Retail"


class TestCategorizeMerchants:
    """Tests for categorize_merchants() with mocked LLM."""

    def test_all_cached_skips_llm(self, seeded_cache):
        """When all merchants are already cached, _call_llm is not called."""
        with patch("ingestion.categorizer.OpenAI"):
            cat = Categorizer(cache_path=seeded_cache, openai_api_key="test-key")
        with patch.object(cat, "_call_llm") as mock_llm:
            result = cat.categorize_merchants(["Tesco", "Shell"])
            mock_llm.assert_not_called()
        assert result["Tesco"]["subcategory"] == "Groceries"
        assert result["Shell"]["subcategory"] == "Fuel"

    def test_uncached_merchants_call_llm(self, categorizer, cache_file):
        """Uncached merchants trigger an LLM call and are persisted."""
        llm_response = [
            {"merchant": "Spotify", "category": "Subscriptions", "subcategory": "Streaming"},
            {"merchant": "GitHub", "category": "Subscriptions", "subcategory": "Software"},
        ]
        with patch.object(categorizer, "_call_llm", return_value=llm_response) as mock_llm:
            result = categorizer.categorize_merchants(["Spotify", "GitHub"])
            mock_llm.assert_called_once_with(["Spotify", "GitHub"])

        assert result["Spotify"]["subcategory"] == "Streaming"
        assert result["GitHub"]["subcategory"] == "Software"
        # Verify cache was saved to disk
        assert cache_file.exists()
        saved = json.loads(cache_file.read_text())
        assert "Spotify" in saved

    def test_mixed_cached_and_uncached(self, seeded_cache):
        """Only uncached merchants are sent to the LLM."""
        with patch("ingestion.categorizer.OpenAI"):
            cat = Categorizer(cache_path=seeded_cache, openai_api_key="test-key")
        llm_response = [
            {"merchant": "Uber", "category": "Transport", "subcategory": "Ride Hailing"},
        ]
        with patch.object(cat, "_call_llm", return_value=llm_response) as mock_llm:
            result = cat.categorize_merchants(["Tesco", "Uber"])
            # Only Uber should be sent to LLM (Tesco is cached)
            mock_llm.assert_called_once_with(["Uber"])

        assert result["Tesco"]["subcategory"] == "Groceries"
        assert result["Uber"]["subcategory"] == "Ride Hailing"

    def test_results_added_to_cache(self, categorizer):
        """After categorization, new merchants exist in the in-memory cache."""
        llm_response = [
            {"merchant": "EE", "category": "Telecoms", "subcategory": "Mobile"},
        ]
        with patch.object(categorizer, "_call_llm", return_value=llm_response):
            categorizer.categorize_merchants(["EE"])
        assert categorizer._cache["EE"]["category"] == "Telecoms"


class TestOverride:
    """Tests for the manual override method."""

    def test_override_new_merchant(self, categorizer, cache_file):
        categorizer.override("Custom Shop", "Shopping", "Clothing")
        assert categorizer._cache["Custom Shop"]["category"] == "Shopping"
        assert categorizer._cache["Custom Shop"]["subcategory"] == "Clothing"
        # Verify persisted
        saved = json.loads(cache_file.read_text())
        assert saved["Custom Shop"]["subcategory"] == "Clothing"

    def test_override_existing_merchant(self, seeded_cache):
        """Override replaces an existing cached classification."""
        with patch("ingestion.categorizer.OpenAI"):
            cat = Categorizer(cache_path=seeded_cache, openai_api_key="test-key")
        cat.override("Tesco", "Food & Drink", "Takeaways")
        assert cat._cache["Tesco"]["subcategory"] == "Takeaways"
        saved = json.loads(seeded_cache.read_text())
        assert saved["Tesco"]["subcategory"] == "Takeaways"
