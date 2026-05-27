"""LLM-based merchant categorizer with local JSON cache.

Uses OpenAI to classify merchant names into a two-level spending
hierarchy (category / subcategory).  Results are cached to disk so
repeated runs avoid redundant API calls.
"""

import json
from pathlib import Path

from openai import OpenAI

CATEGORY_HIERARCHY = {
    "Essentials": ["Groceries", "Utilities", "Housing", "Insurance"],
    "Transport": ["Fuel", "Public Transport", "Ride Hailing"],
    "Food & Drink": ["Dining Out", "Takeaways", "Coffee Shops"],
    "Subscriptions": ["Streaming", "Software", "Meal Kits"],
    "Shopping": ["Clothing", "Home & DIY", "Online Retail"],
    "Children & Education": ["School", "Tutoring"],
    "Telecoms": ["Mobile", "Broadband"],
    "Health & Wellbeing": ["Optical", "Pharmacy"],
    "Savings & Investments": ["Pension", "Savings Transfers", "Round-ups"],
    "Income": ["Salary"],
    "Charity": ["Donations"],
}


class Categorizer:
    """Classify merchants into spending categories using an LLM."""

    def __init__(self, cache_path: Path, openai_api_key: str):
        self.cache_path = Path(cache_path)
        self.client = OpenAI(api_key=openai_api_key)
        self._cache = self._load_cache()

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text())
        return {}

    def _save_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=2))

    def categorize_merchants(self, merchant_names: list[str]) -> dict:
        """Categorize a list of merchants, using cache where possible.

        Parameters
        ----------
        merchant_names:
            List of normalized merchant names to classify.

        Returns
        -------
        dict
            Mapping of merchant name to ``{"category": ..., "subcategory": ...}``.
        """
        uncached = [m for m in merchant_names if m not in self._cache]
        if uncached:
            results = self._call_llm(uncached)
            for item in results:
                self._cache[item["merchant"]] = {
                    "category": item["category"],
                    "subcategory": item["subcategory"],
                }
            self._save_cache()
        return {m: self._cache[m] for m in merchant_names if m in self._cache}

    def _call_llm(self, merchants: list[str]) -> list[dict]:
        """Call the OpenAI API to classify *merchants*.

        Returns a list of dicts with keys ``merchant``, ``category``,
        ``subcategory``.
        """
        hierarchy_text = "\n".join(
            f"  {cat}: {', '.join(subs)}" for cat, subs in CATEGORY_HIERARCHY.items()
        )
        numbered = "\n".join(f"{i+1}. {m}" for i, m in enumerate(merchants))
        response = self.client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You classify merchants into spending categories. Always return valid JSON.",
                },
                {
                    "role": "user",
                    "content": f"""Classify each merchant into exactly one subcategory from this hierarchy:
{hierarchy_text}

Merchants:
{numbered}

Return JSON: {{"results": [{{"merchant": "...", "category": "...", "subcategory": "..."}}]}}""",
                },
            ],
        )
        content = json.loads(response.choices[0].message.content)
        return content["results"]

    def override(self, merchant: str, category: str, subcategory: str):
        """Manually set a merchant's category, persisting to cache."""
        self._cache[merchant] = {"category": category, "subcategory": subcategory}
        self._save_cache()
