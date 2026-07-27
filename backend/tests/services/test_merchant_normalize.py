"""
Phase 1 — merchant_key thorough tests.

Pure function (no DB, no Redis, no LLM). Every later tier keys off these
tokens, so behavior here must stay frozen and deterministic.
"""

from django.test import SimpleTestCase

from services.merchant_normalize import merchant_key


class MerchantKeyPhase1SpecTests(SimpleTestCase):
    """Green-bar cases from the Phase 1 normalizer checklist."""

    def test_mcdonalds_rows_collapse_to_mcdonalds(self):
        self.assertEqual(merchant_key("MCDONALD'S F31398"), "MCDONALDS")
        self.assertEqual(merchant_key("MCDONALD'S F25696"), "MCDONALDS")
        self.assertEqual(
            merchant_key("MCDONALD'S F31398"),
            merchant_key("MCDONALD'S F25696"),
        )

    def test_mta_star_cuts_to_mta(self):
        self.assertEqual(merchant_key("MTA*NYCT PAYGO"), "MTA")

    def test_walmart_hash_becomes_wal_mart(self):
        self.assertEqual(merchant_key("WAL-MART #2297"), "WAL MART")

    def test_lyft_star_airport(self):
        self.assertEqual(merchant_key("LYFT   *AIRPORT"), "LYFT")


class MerchantKeyAlgorithmStepTests(SimpleTestCase):
    """One test group per normalization step (and real-world combos)."""

    def test_step1_uppercases(self):
        self.assertEqual(merchant_key("lyft"), "LYFT")
        self.assertEqual(merchant_key("Wal-Mart"), "WAL MART")
        self.assertEqual(merchant_key("mTa*nyct"), "MTA")

    def test_step2_cuts_after_first_star(self):
        cases = [
            ("MTA*NYCT PAYGO", "MTA"),
            ("LYFT*RIDE HELP.LYFT.COM", "LYFT"),
            ("SQ *COFFEE SHOP", "SQ"),
            ("AMZN*MARKETPLACE", "AMZN"),
            ("PAYPAL *SPOTIFY", "PAYPAL"),
            ("UBER *EATS PENDING", "UBER"),
            ("GOOGLE *YouTubePremium", "GOOGLE"),
            ("A*B*C", "A"),
            ("FOO*BAR#BAZ", "FOO"),
            ("*LEADING STAR", ""),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)

    def test_step2_cuts_after_first_hash(self):
        cases = [
            ("WAL-MART #2297", "WAL MART"),
            ("DOMINOS PIZZA #10278", "DOMINOS PIZZA"),
            ("BEST BUY #123", "BEST BUY"),
            ("WHOLEFDS #10123", "WHOLEFDS"),
            ("CVS/PHARMACY #4521", "CVS PHARMACY"),
            ("FOO#BAR*BAZ", "FOO"),
            ("#LEADING HASH", ""),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)

    def test_step3_deletes_digits(self):
        cases = [
            ("12345", ""),
            ("123 ABC 456", "ABC"),
            ("CHIPOTLE 1842", "CHIPOTLE"),
            ("SHELL OIL 5541", "SHELL OIL"),
            ("EXXONMOBIL 12345678", "EXXONMOBIL"),
            ("PMUSA 304046 JERSEY CI", "PMUSA JERSEY CI"),
            ("7-ELEVEN", "ELEVEN"),
            ("7-ELEVEN #123", "ELEVEN"),
            ("LYFT   *AIRPORT 07-06", "LYFT"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)

    def test_step3_letter_digit_store_codes(self):
        """F31398 / A1 style tokens (letter + digits) are store noise."""
        cases = [
            ("MCDONALD'S F31398", "MCDONALDS"),
            ("STORE A1 B2", "STORE"),
            ("XX F1 YY", "XX YY"),
            ("A1", ""),
            ("STORE AB12", "STORE AB"),  # digits glued to letters → digits only
            ("A12B", "AB"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)

    def test_step4_non_letters_become_spaces(self):
        cases = [
            ("WAL-MART", "WAL MART"),
            ("PERUSALL E-BOOK", "PERUSALL E BOOK"),
            ("CVS/PHARMACY", "CVS PHARMACY"),
            ("APPLE.COM/BILL", "APPLE COM BILL"),
            ("WWW.AMAZON.COM", "WWW AMAZON COM"),
            ("H&M STORE", "H M STORE"),
            ("AT&T", "AT T"),
            ("AT&T*BILL PAYMENT", "AT T"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)

    def test_step4_apostrophes_removed_not_spaced(self):
        self.assertEqual(merchant_key("MCDONALD'S"), "MCDONALDS")
        self.assertEqual(merchant_key("MCDONALD’S"), "MCDONALDS")  # U+2019
        self.assertEqual(
            merchant_key("MCDONALD'S F31398"),
            merchant_key("MCDONALD’S F31398"),
        )

    def test_step5_collapses_whitespace_and_strips(self):
        cases = [
            ("  mcdonald's   f99  ", "MCDONALDS"),
            ("SPACES    BETWEEN", "SPACES BETWEEN"),
            ("trailing   ", "TRAILING"),
            ("   ", ""),
            ("LYFT   *AIRPORT", "LYFT"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)


class MerchantKeyChaseStatementTests(SimpleTestCase):
    """Real-ish Chase description rows → stable keys for rules / cache / LLM."""

    CASES = [
        ("WAL-MART #2297", "WAL MART"),
        ("PERUSALL E-BOOK", "PERUSALL E BOOK"),
        ("MCDONALD'S F31398", "MCDONALDS"),
        ("MCDONALD'S F25696", "MCDONALDS"),
        ("PMUSA 304046 JERSEY CI", "PMUSA JERSEY CI"),
        ("MTA*NYCT PAYGO", "MTA"),
        ("LYFT   *AIRPORT 07-06", "LYFT"),
        ("LYFT   *WAITSAVE 07-06", "LYFT"),
        ("FOREIGN TRANSACTION FEE", "FOREIGN TRANSACTION FEE"),
        ("DOMINOS PIZZA #10278", "DOMINOS PIZZA"),
        ("BEST BUY #123", "BEST BUY"),
        ("WHOLEFDS #10123", "WHOLEFDS"),
        ("CVS/PHARMACY #4521", "CVS PHARMACY"),
        ("EXXONMOBIL 12345678", "EXXONMOBIL"),
        ("PAYPAL *SPOTIFY", "PAYPAL"),
        ("GOOGLE *YouTubePremium", "GOOGLE"),
        ("APPLE.COM/BILL", "APPLE COM BILL"),
        ("WWW.AMAZON.COM", "WWW AMAZON COM"),
        ("POS DEBIT CHIPOTLE", "POS DEBIT CHIPOTLE"),
        ("CHIPOTLE 1842", "CHIPOTLE"),
        ("SHELL OIL 5541", "SHELL OIL"),
        ("UBER *EATS PENDING", "UBER"),
        ("TST* JOE'S PIZZA", "TST"),
    ]

    def test_chase_rows(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)


class MerchantKeyCollapseAndDistinctnessTests(SimpleTestCase):
    def test_store_variants_collapse_to_same_key(self):
        pairs = [
            ("MCDONALD'S F31398", "MCDONALD'S F25696"),
            ("WAL-MART #2297", "WAL-MART #0001"),
            ("DOMINOS PIZZA #10278", "DOMINOS PIZZA #99999"),
            ("LYFT   *AIRPORT 07-06", "LYFT   *WAITSAVE 07-06"),
            ("CHIPOTLE 1842", "CHIPOTLE 0001"),
            ("XX F1 YY", "XX F99 YY"),
        ]
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertEqual(merchant_key(a), merchant_key(b))
                self.assertTrue(merchant_key(a))

    def test_unrelated_merchants_stay_distinct(self):
        keys = {
            merchant_key("MCDONALD'S F31398"),
            merchant_key("WAL-MART #2297"),
            merchant_key("MTA*NYCT PAYGO"),
            merchant_key("LYFT   *AIRPORT"),
            merchant_key("CHIPOTLE 1842"),
            merchant_key("SHELL OIL 5541"),
            merchant_key("FOREIGN TRANSACTION FEE"),
        }
        self.assertEqual(len(keys), 7)
        self.assertNotIn("", keys)


class MerchantKeyRobustnessTests(SimpleTestCase):
    def test_empty_and_garbage_never_raise(self):
        cases = [
            ("", ""),
            ("   ", ""),
            ("***", ""),
            ("###", ""),
            ("12345", ""),
            ("!!!@@@", ""),
            (None, ""),
            (123, ""),
            ([], ""),
            ({}, ""),
            (True, ""),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)  # type: ignore[arg-type]

    def test_non_ascii_letters_dropped(self):
        self.assertEqual(merchant_key("café"), "CAF")
        self.assertEqual(merchant_key("NAÏVE"), "NA VE")
        self.assertEqual(merchant_key("NAIVE"), "NAIVE")

    def test_output_is_idempotent(self):
        raws = [
            "MCDONALD'S F31398",
            "WAL-MART #2297",
            "MTA*NYCT PAYGO",
            "PMUSA 304046 JERSEY CI",
            "CVS/PHARMACY #4521",
            "FOREIGN TRANSACTION FEE",
            "7-ELEVEN",
            "H&M STORE",
            "LYFT   *AIRPORT",
        ]
        for raw in raws:
            key = merchant_key(raw)
            with self.subTest(raw=raw, key=key):
                self.assertEqual(merchant_key(key), key)

    def test_return_type_is_str(self):
        for raw in ["MTA*X", None, 1, ""]:
            self.assertIsInstance(merchant_key(raw), str)  # type: ignore[arg-type]
