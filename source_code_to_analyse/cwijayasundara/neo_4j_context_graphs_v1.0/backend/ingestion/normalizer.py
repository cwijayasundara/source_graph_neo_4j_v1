"""Transaction normalizer: merchant dedup, payment-method extraction,
person extraction, and deterministic transaction-ID generation.
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Merchant normalisation rules
# ---------------------------------------------------------------------------
# Each tuple: (compiled regex, canonical merchant name)
# Order matters: first match wins.  Regexes are case-insensitive.

_MERCHANT_RULES: list[tuple[re.Pattern, str]] = [
    # ---- Supermarkets / Grocery ----
    (re.compile(r"TESCO\b|TESCOS\b", re.I), "Tesco"),
    (re.compile(r"SAINSBURY", re.I), "Sainsbury's"),
    (re.compile(r"WM\s*MORRISONS|MORRISONS", re.I), "Morrisons"),
    (re.compile(r"MARKS\s*&\s*SPENCER|M\s*&\s*S\b", re.I), "Marks & Spencer"),
    (re.compile(r"COSTCO", re.I), "Costco"),
    (re.compile(r"B\s*&\s*M\b", re.I), "B&M"),

    # ---- Online / Tech ----
    (re.compile(r"AWS\s+EMEA", re.I), "AWS"),
    (re.compile(r"AMAZON\.CO\.UK|AMZNMKTPLACE|AMAZON", re.I), "Amazon"),
    (re.compile(r"APPLE\.COM/BILL", re.I), "Apple"),
    (re.compile(r"GOOGLE\s*\*\s*YOUTUBEPREMIUM", re.I), "YouTube Premium"),
    (re.compile(r"OPENAI\s*\*\s*CHATGPT", re.I), "OpenAI ChatGPT"),
    (re.compile(r"GITHUB", re.I), "GitHub"),
    (re.compile(r"SPOTIFY", re.I), "Spotify"),
    (re.compile(r"HELLOFRESH", re.I), "HelloFresh"),

    # ---- Food / Delivery ----
    (re.compile(r"PAYPAL\s*\*\s*JUSTEATCOUK|JUST\s*EAT", re.I), "Just Eat"),
    (re.compile(r"UBER\s*EATS", re.I), "Uber Eats"),
    (re.compile(r"UBER\s*\*\s*TRIP|HELP\.UBER\.COM", re.I), "Uber"),
    (re.compile(r"JAMAICA\s+BLUE", re.I), "Jamaica Blue"),
    (re.compile(r"WELCOME\s+BREAK", re.I), "Welcome Break"),

    # ---- Transport ----
    (re.compile(r"TFL\b", re.I), "TFL"),
    (re.compile(r"SHELL\b", re.I), "Shell"),

    # ---- Telecom ----
    (re.compile(r"EE\s+LIMITED|EE\s+LTD", re.I), "EE"),
    (re.compile(r"VIRGIN\s+MEDIA", re.I), "Virgin Media"),
    (re.compile(r"VODAFONE", re.I), "Vodafone"),

    # ---- Utilities ----
    (re.compile(r"E\.ON\s+NEXT", re.I), "E.ON"),
    (re.compile(r"AFFINITY\s+WATER", re.I), "Affinity Water"),
    (re.compile(r"SWALE\s+HEATING", re.I), "Swale Heating"),
    (re.compile(r"WATFORD\s+BOROUGH\s+COUNCIL", re.I), "Watford Borough Council"),
    (re.compile(r"TV\s+LICENCE", re.I), "TV Licence"),

    # ---- Insurance ----
    (re.compile(r"ADMIRAL\s+HOME\s+INSURANCE", re.I), "Admiral Home Insurance"),
    (re.compile(r"ADMIRAL\s+MOTOR\s+INSURANCE", re.I), "Admiral Motor Insurance"),
    (re.compile(r"HOME\s+INSURANCE", re.I), "Home Insurance"),

    # ---- Finance / Pension ----
    (re.compile(r"SCOTTISH\s+WIDOWS.*PENSION", re.I), "Scottish Widows Pension"),
    (re.compile(r"SCOTTISH\s+WIDOWS.*LIFE", re.I), "Scottish Widows Life"),
    (re.compile(r"NATIONWIDE\s+BS\s+MORTGAGE", re.I), "Nationwide Mortgage"),
    (re.compile(r"CREATION\s+CONSUMER\s+FIN", re.I), "Creation Consumer Finance"),
    (re.compile(r"HALIFAX\s+CREDIT\s+CARD", re.I), "Halifax Credit Card"),
    (re.compile(r"SAVETHECHANGE", re.I), "Save the Change"),

    # ---- Retail ----
    (re.compile(r"FOOT\s+LOCKER", re.I), "Foot Locker"),
    (re.compile(r"UNIQLO", re.I), "Uniqlo"),
    (re.compile(r"VISION\s+EXPRESS", re.I), "Vision Express"),
    (re.compile(r"BOOTS\b", re.I), "Boots"),
    (re.compile(r"B\s*&\s*Q\b", re.I), "B&Q"),

    # ---- Education ----
    (re.compile(r"TUTORFUL", re.I), "Tutorful"),
    (re.compile(r"PARENTPAY", re.I), "ParentPay"),

    # ---- Streaming / Subscriptions ----
    (re.compile(r"PAYPAL\s*\*\s*DISNEYPLUS|DISNEY\s*\+", re.I), "Disney+"),
    (re.compile(r"WWF\b", re.I), "WWF"),

    # ---- PayPal catch-all (after specific PayPal merchants) ----
    (re.compile(r"PAYPAL\s*\*\s*PYPL\s+PAYIN", re.I), "PayPal"),
    (re.compile(r"PAYPAL", re.I), "PayPal"),

    # ---- Banking meta-transactions ----
    (re.compile(r"BALANCE\s+FROM\s+PREVIOUS\s+STATEMENT", re.I), "Balance Brought Forward"),
    (re.compile(r"DIRECT\s+DEBIT\s+PAYMENT.*THANK\s+YOU", re.I), "Direct Debit Payment"),
    (re.compile(r"INTEREST\s*\(GROSS\)", re.I), "Interest"),
]

# ---------------------------------------------------------------------------
# Payment-method extraction
# ---------------------------------------------------------------------------
_PAYMENT_METHOD_RE = re.compile(r"\(([A-Z]{2,3})\)\s*$")

_KNOWN_METHODS = {"DD", "DEB", "BGC", "SO", "BP", "TFR", "FPO", "FPI"}


def extract_payment_method(description: str) -> Optional[str]:
    """Extract the payment-method code from a description suffix.

    Recognised codes: DD (Direct Debit), DEB (Debit card), BGC (Bank Giro
    Credit), SO (Standing Order), BP (Bill Payment), TFR (Transfer),
    FPO (Faster Payment Out), FPI (Faster Payment In).

    Returns
    -------
    str | None
        The uppercase method code, or ``None`` if not found.
    """
    m = _PAYMENT_METHOD_RE.search(description)
    if m and m.group(1) in _KNOWN_METHODS:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Person extraction
# ---------------------------------------------------------------------------
_SALARY_RE = re.compile(r"^(.+?)\s+SALARY\b", re.I)
_SAVINGS_RE = re.compile(r"^(.+?)\s+SAVINGS\b", re.I)


def extract_person(description: str) -> Optional[dict]:
    """Extract a person reference from a description.

    Patterns detected:

    * ``ACME INDUSTRIES SALARY (BGC)`` -> ``{"name": "Acme Industries", "role": "employer"}``
    * ``Pepper Potts SAVINGS (SO)`` -> ``{"name": "Pepper Potts", "role": "payee"}``

    Returns
    -------
    dict | None
        A dict with ``name`` and ``role`` keys, or ``None``.
    """
    m = _SALARY_RE.match(description)
    if m:
        return {"name": m.group(1).strip().title(), "role": "employer"}

    m = _SAVINGS_RE.match(description)
    if m:
        return {"name": m.group(1).strip().title(), "role": "payee"}

    return None


# ---------------------------------------------------------------------------
# Merchant normalisation
# ---------------------------------------------------------------------------


def normalize_merchant(raw_description: str) -> str:
    """Map a raw transaction description to a canonical merchant name.

    Uses a prioritised list of regex rules.  If no rule matches the raw
    description is returned in title case with trailing payment-method
    codes stripped.
    """
    for pattern, canonical in _MERCHANT_RULES:
        if pattern.search(raw_description):
            return canonical
    # Fallback: strip trailing payment-method code, title-case
    cleaned = _PAYMENT_METHOD_RE.sub("", raw_description).strip()
    return cleaned.title() if cleaned else raw_description


# ---------------------------------------------------------------------------
# Transaction-ID generation
# ---------------------------------------------------------------------------


def generate_transaction_id(
    account_id: str, date: str, amount: float, seq: int = 0
) -> str:
    """Generate a deterministic transaction ID.

    Format: ``{account_id}-{date}-{amount}-{seq}``

    The *seq* disambiguator handles same-account, same-date, same-amount
    duplicates (e.g. two identical Uber trips).
    """
    return f"{account_id}-{date}-{amount}-{seq}"
