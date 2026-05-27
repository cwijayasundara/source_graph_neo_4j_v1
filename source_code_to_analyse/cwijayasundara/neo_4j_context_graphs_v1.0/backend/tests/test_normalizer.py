"""Tests for the transaction normalizer."""

import pytest
from ingestion.normalizer import (
    normalize_merchant,
    extract_payment_method,
    extract_person,
    generate_transaction_id,
)


# ---- normalize_merchant ----


class TestNormalizeMerchant:
    """Tests for normalize_merchant()."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("TESCO STORES 3372", "Tesco"),
            ("TESCO STORES 6753 WATFORD (DEB)", "Tesco"),
            ("TESCO STORES 3372 Watford WD17 2UB (DEB)", "Tesco"),
            ("TESCOS STORES 3372", "Tesco"),
            ("AMAZON.CO.UK *R684K9ZJ4", "Amazon"),
            ("AMZNMKTPLACE*R66EF9ZC4", "Amazon"),
            ("PAYPAL *JUSTEATCOUK", "Just Eat"),
            ("PAYPAL *JUSTEATCOUK (DEB)", "Just Eat"),
            ("GOOGLE *YOUTUBEPREMIUM", "YouTube Premium"),
            ("UBER *TRIP HELP.UBER.COM", "Uber"),
            ("TFL TRAVEL CH TFL.GOV.UK/CP", "TFL"),
            ("TFL.GOV.UK/CP (DEB)", "TFL"),
            ("SPOTIFY 14 Avengers Close Watford Hertfordshire WD99 9ZZ (DEB)", "Spotify"),
            ("SAINSBURY'S S/MKT WATFORD", "Sainsbury's"),
            ("SAINSBURYS S/MKTS WATFORD (DEB)", "Sainsbury's"),
            ("WM MORRISONS STORE 586 (DEB)", "Morrisons"),
            ("MARKS & SPENCER PLC (DEB)", "Marks & Spencer"),
            ("COSTCO PFS - WATFORD (DEB)", "Costco"),
            ("COSTCO WHOLESALE #WATFORD (DEB)", "Costco"),
            ("B&M 828 Watford WD17 2UB (DEB)", "B&M"),
            ("AWS EMEA AWS.AMAZON.COM LUX", "AWS"),
            ("APPLE.COM/BILL CORK IRL", "Apple"),
            ("OPENAI *CHATGPT SUBSCR", "OpenAI ChatGPT"),
            ("GITHUB, INC. Watford WD17 2UB CA", "GitHub"),
            ("HELLOFRESH UK LONDON", "HelloFresh"),
            ("UBER EATS (DEB)", "Uber Eats"),
            ("JAMAICA BLUE WATFORD", "Jamaica Blue"),
            ("WELCOME BREAK NEWPORT PAGNE", "Welcome Break"),
            ("SHELL CROXLEY 191 (DEB)", "Shell"),
            ("EE LIMITED MOBILE (DD)", "EE"),
            ("VIRGIN MEDIA PYMTS (DD)", "Virgin Media"),
            ("VODAFONE LTD (DD)", "Vodafone"),
            ("VODAFONE LTD DEVICE (DD)", "Vodafone"),
            ("E.ON NEXT LTD (DD)", "E.ON"),
            ("AFFINITY WATER (DD)", "Affinity Water"),
            ("SWALE HEATING LTD (DD)", "Swale Heating"),
            ("WATFORD BOROUGH COUNCIL (DD)", "Watford Borough Council"),
            ("TV LICENCE QBP1 (DD)", "TV Licence"),
            ("ADMIRAL HOME INSURANCE (DD)", "Admiral Home Insurance"),
            ("ADMIRAL MOTOR INSURANCE (DD)", "Admiral Motor Insurance"),
            ("HOME INSURANCE Mr Tony Stark (DD)", "Home Insurance"),
            ("SCOTTISH WIDOWS WIDOWS PENSION (DD)", "Scottish Widows Pension"),
            ("SCOTTISH WIDOWS WIDOWS LIFE (DD)", "Scottish Widows Life"),
            ("NATIONWIDE BS MORTGAGE (DD)", "Nationwide Mortgage"),
            ("CREATION CONSUMER FIN (DD)", "Creation Consumer Finance"),
            ("HALIFAX CREDIT CARD (DD)", "Halifax Credit Card"),
            ("SAVETHECHANGE-6366 (BP)", "Save the Change"),
            ("FOOT LOCKER INC 4237", "Foot Locker"),
            ("UNIQLO WATFORD", "Uniqlo"),
            ("VISION EXPRESS WATFORD", "Vision Express"),
            ("BOOTS WATFORD (DEB)", "Boots"),
            ("B & Q 1245 WATFORD", "B&Q"),
            ("TUTORFUL* 14 Avengers Close Watford Hertfordshire WD99 9ZZ", "Tutorful"),
            ("PARENTPAY E-COM Mr Tony Stark", "ParentPay"),
            ("PAYPAL *DISNEYPLUS (DEB)", "Disney+"),
            ("WWF 14 Avengers Close Watford Hertfordshire WD99 9ZZ (DD)", "WWF"),
            ("PAYPAL *PYPL PAYIN (DEB)", "PayPal"),
            ("BALANCE FROM PREVIOUS STATEMENT", "Balance Brought Forward"),
            ("DIRECT DEBIT PAYMENT - THANK YOU", "Direct Debit Payment"),
            ("INTEREST (GROSS) ()", "Interest"),
        ],
    )
    def test_merchant_normalisation(self, raw, expected):
        assert normalize_merchant(raw) == expected

    def test_unknown_merchant_fallback(self):
        """Unknown merchants should be title-cased with method stripped."""
        result = normalize_merchant("RANDOM SHOP 123 LONDON (DEB)")
        assert result == "Random Shop 123 London"

    def test_unknown_merchant_no_method(self):
        """Unknown merchants without method code keep full title case."""
        result = normalize_merchant("SOME NEW PLACE")
        assert result == "Some New Place"


# ---- extract_payment_method ----


class TestExtractPaymentMethod:
    """Tests for extract_payment_method()."""

    @pytest.mark.parametrize(
        "desc, expected",
        [
            ("WATFORD BOROUGH COUNCIL (DD)", "DD"),
            ("TESCO STORES 3372 Watford WD17 2UB (DEB)", "DEB"),
            ("ACME INDUSTRIES SALARY (BGC)", "BGC"),
            ("Pepper Potts SAVINGS (SO)", "SO"),
            ("SAVETHECHANGE-6366 (BP)", "BP"),
            ("INTEREST (GROSS) ()", None),  # empty parens, not a method
            ("AMAZON.CO.UK *R684K9ZJ4", None),  # no method suffix
            ("UBER *TRIP HELP.UBER.COM", None),
        ],
    )
    def test_payment_method(self, desc, expected):
        assert extract_payment_method(desc) == expected


# ---- extract_person ----


class TestExtractPerson:
    """Tests for extract_person()."""

    def test_salary_employer(self):
        result = extract_person("ACME INDUSTRIES SALARY (BGC)")
        assert result is not None
        assert result["name"] == "Acme Industries"
        assert result["role"] == "employer"

    def test_savings_payee(self):
        result = extract_person("Pepper Potts SAVINGS (SO)")
        assert result is not None
        assert result["name"] == "Pepper Potts"
        assert result["role"] == "payee"

    def test_no_person(self):
        assert extract_person("TESCO STORES 3372 (DEB)") is None

    def test_no_person_in_utility(self):
        assert extract_person("WATFORD BOROUGH COUNCIL (DD)") is None


# ---- generate_transaction_id ----


class TestGenerateTransactionId:
    """Tests for generate_transaction_id()."""

    def test_format(self):
        tid = generate_transaction_id("12345678", "2025-01-01", -28.74, 0)
        assert tid == "12345678-2025-01-01--28.74-0"

    def test_deterministic(self):
        """Same inputs must produce the same ID."""
        a = generate_transaction_id("ACC", "2025-06-15", -100.0, 1)
        b = generate_transaction_id("ACC", "2025-06-15", -100.0, 1)
        assert a == b

    def test_seq_disambiguates(self):
        """Different seq values produce different IDs."""
        a = generate_transaction_id("ACC", "2025-06-15", -100.0, 0)
        b = generate_transaction_id("ACC", "2025-06-15", -100.0, 1)
        assert a != b

    def test_positive_amount(self):
        tid = generate_transaction_id("ACC", "2025-01-01", 500.0, 0)
        assert tid == "ACC-2025-01-01-500.0-0"
