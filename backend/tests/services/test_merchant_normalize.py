"""
merchant_key and normalized_display tests.

merchant_key: pure function, no DB, no Redis.
normalized_display: title-cased version of merchant_key.

Every tier in the resolver keys off merchant_key, so its contract is frozen.
Processor-prefix behavior (keep-right) is critical: PAYPAL *NETFLIX must
produce "NETFLIX", not "PAYPAL", or user overrides silently apply to all
PayPal transactions.
"""

from django.test import SimpleTestCase

from services.merchant_normalize import PROCESSOR_PREFIXES, merchant_key, normalized_display


class MerchantKeySpecTests(SimpleTestCase):
    """Core behavior — the examples callers rely on."""

    def test_mcdonalds_store_variants_collapse(self):
        self.assertEqual(merchant_key("MCDONALD'S F31398"), "MCDONALDS")
        self.assertEqual(merchant_key("MCDONALD'S F25696"), "MCDONALDS")
        self.assertEqual(
            merchant_key("MCDONALD'S F31398"),
            merchant_key("MCDONALD'S F25696"),
        )

    def test_walmart_hash_becomes_wal_mart(self):
        self.assertEqual(merchant_key("WAL-MART #2297"), "WAL MART")

    def test_mta_star_kept_as_mta(self):
        """MTA is a merchant, not a processor: keep left side."""
        self.assertEqual(merchant_key("MTA*NYCT PAYGO"), "MTA")

    def test_lyft_star_kept_as_lyft(self):
        """Lyft is a merchant: keep left side."""
        self.assertEqual(merchant_key("LYFT   *AIRPORT"), "LYFT")

    def test_sq_star_keeps_submerchant(self):
        """Square is a payment processor: keep the merchant on the right."""
        self.assertEqual(merchant_key("SQ *BLUE BOTTLE COFFEE 0042"), "BLUE BOTTLE COFFEE")
        self.assertEqual(merchant_key("SQ *COFFEE SHOP"), "COFFEE SHOP")

    def test_paypal_star_keeps_submerchant(self):
        """PayPal is a processor: Netflix and a local seller must be distinct keys."""
        self.assertEqual(merchant_key("PAYPAL *NETFLIX"), "NETFLIX")
        self.assertEqual(merchant_key("PAYPAL *LOCALSELLER"), "LOCALSELLER")
        self.assertNotEqual(
            merchant_key("PAYPAL *NETFLIX"),
            merchant_key("PAYPAL *LOCALSELLER"),
        )

    def test_tst_star_keeps_submerchant(self):
        """Toast POS is a processor: the restaurant is on the right."""
        self.assertEqual(merchant_key("TST* JOE'S PIZZA"), "JOES PIZZA")

    def test_single_char_star_continuation(self):
        """TRADER JOE*S — the *S is an apostrophe substitute, not a submerchant."""
        self.assertEqual(merchant_key("TRADER JOE*S"), "TRADER JOES")


class ProcessorPrefixSetTests(SimpleTestCase):
    def test_known_processors_are_in_the_set(self):
        for p in ("SQ", "PAYPAL", "TST", "SP", "VENMO", "ETSY"):
            self.assertIn(p, PROCESSOR_PREFIXES)

    def test_merchants_are_not_in_the_set(self):
        for m in ("LYFT", "UBER", "AMZN", "GOOGLE", "AMAZON", "MTA"):
            self.assertNotIn(m, PROCESSOR_PREFIXES)


class MerchantKeyAlgorithmStepTests(SimpleTestCase):

    def test_step1_uppercases(self):
        self.assertEqual(merchant_key("lyft"), "LYFT")
        self.assertEqual(merchant_key("Wal-Mart"), "WAL MART")
        self.assertEqual(merchant_key("mTa*nyct"), "MTA")  # MTA not processor → keep left

    def test_step2_star_processor_keeps_right(self):
        processor_cases = [
            ("SQ *COFFEE SHOP", "COFFEE SHOP"),
            ("PAYPAL *SPOTIFY", "SPOTIFY"),
            ("TST* JOE'S PIZZA", "JOES PIZZA"),
        ]
        for raw, expected in processor_cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)

    def test_step2_star_non_processor_keeps_left(self):
        non_processor_cases = [
            ("MTA*NYCT PAYGO", "MTA"),
            ("LYFT*RIDE HELP.LYFT.COM", "LYFT"),
            ("AMZN*MARKETPLACE", "AMZN"),
            ("UBER *EATS PENDING", "UBER"),
            ("GOOGLE *YouTubePremium", "GOOGLE"),
            ("A*B*C", "A"),
            ("FOO*BAR#BAZ", "FOO"),
            ("*LEADING STAR", ""),
        ]
        for raw, expected in non_processor_cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)

    def test_step2_star_single_char_continuation(self):
        self.assertEqual(merchant_key("TRADER JOE*S"), "TRADER JOES")

    def test_step2_hash_keeps_left(self):
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
        cases = [
            ("MCDONALD'S F31398", "MCDONALDS"),
            ("STORE A1 B2", "STORE"),
            ("XX F1 YY", "XX YY"),
            ("A1", ""),
            ("STORE AB12", "STORE AB"),
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
            ("AT&T*BILL PAYMENT", "AT T"),  # AT&T is not a processor
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)

    def test_step4_apostrophes_removed_not_spaced(self):
        self.assertEqual(merchant_key("MCDONALD'S"), "MCDONALDS")
        self.assertEqual(merchant_key("MCDONALD\u2019S"), "MCDONALDS")

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
    """Real-ish Chase description rows → expected stable keys."""

    CASES = [
        ("WAL-MART #2297",               "WAL MART"),
        ("PERUSALL E-BOOK",              "PERUSALL E BOOK"),
        ("MCDONALD'S F31398",            "MCDONALDS"),
        ("MCDONALD'S F25696",            "MCDONALDS"),
        ("PMUSA 304046 JERSEY CI",       "PMUSA JERSEY CI"),
        ("MTA*NYCT PAYGO",               "MTA"),
        ("LYFT   *AIRPORT 07-06",        "LYFT"),
        ("LYFT   *WAITSAVE 07-06",       "LYFT"),
        ("FOREIGN TRANSACTION FEE",      "FOREIGN TRANSACTION FEE"),
        ("DOMINOS PIZZA #10278",         "DOMINOS PIZZA"),
        ("BEST BUY #123",                "BEST BUY"),
        ("WHOLEFDS #10123",              "WHOLEFDS"),
        ("CVS/PHARMACY #4521",           "CVS PHARMACY"),
        ("EXXONMOBIL 12345678",          "EXXONMOBIL"),
        # Processor prefixes: keep the submerchant on the right
        ("PAYPAL *SPOTIFY",              "SPOTIFY"),
        ("TST* JOE'S PIZZA",             "JOES PIZZA"),
        # Non-processor: keep the merchant on the left
        ("GOOGLE *YouTubePremium",       "GOOGLE"),
        ("APPLE.COM/BILL",               "APPLE COM BILL"),
        ("WWW.AMAZON.COM",               "WWW AMAZON COM"),
        ("POS DEBIT CHIPOTLE",           "POS DEBIT CHIPOTLE"),
        ("CHIPOTLE 1842",                "CHIPOTLE"),
        ("SHELL OIL 5541",               "SHELL OIL"),
        ("UBER *EATS PENDING",           "UBER"),
    ]

    def test_chase_rows(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)


class MerchantKeyCollapseAndDistinctnessTests(SimpleTestCase):
    def test_store_variants_collapse_to_same_key(self):
        pairs = [
            ("MCDONALD'S F31398",                 "MCDONALD'S F25696"),
            ("WAL-MART #2297",                    "WAL-MART #0001"),
            ("DOMINOS PIZZA #10278",              "DOMINOS PIZZA #99999"),
            ("LYFT   *AIRPORT 07-06",             "LYFT   *WAITSAVE 07-06"),
            ("CHIPOTLE 1842",                     "CHIPOTLE 0001"),
            ("XX F1 YY",                          "XX F99 YY"),
            # Processor submerchant store variants collapse (digits stripped)
            ("SQ *BLUE BOTTLE COFFEE 0042",       "SQ *BLUE BOTTLE COFFEE 0099"),
            ("PAYPAL *NETFLIX",                   "PAYPAL *NETFLIX"),
        ]
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertEqual(merchant_key(a), merchant_key(b))
                self.assertTrue(merchant_key(a))

    def test_processor_submerchants_are_distinct(self):
        """The whole reason for keep-right: different merchants must not share a key."""
        self.assertNotEqual(
            merchant_key("PAYPAL *NETFLIX"),
            merchant_key("PAYPAL *LOCALSELLER"),
        )
        self.assertNotEqual(
            merchant_key("SQ *BLUE BOTTLE COFFEE"),
            merchant_key("SQ *DOWNTOWN BARBER"),
        )

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
            "SQ *BLUE BOTTLE COFFEE",
            "PAYPAL *NETFLIX",
        ]
        for raw in raws:
            key = merchant_key(raw)
            with self.subTest(raw=raw, key=key):
                self.assertEqual(merchant_key(key), key)

    def test_return_type_is_str(self):
        for raw in ["MTA*X", None, 1, ""]:
            self.assertIsInstance(merchant_key(raw), str)  # type: ignore[arg-type]


class NormalizedDisplayTests(SimpleTestCase):
    def test_title_cases_merchant_key(self):
        self.assertEqual(normalized_display("WAL-MART #2297"), "Wal Mart")
        self.assertEqual(normalized_display("SQ *BLUE BOTTLE COFFEE 0042"), "Blue Bottle Coffee")
        self.assertEqual(normalized_display("PAYPAL *NETFLIX"), "Netflix")
        self.assertEqual(normalized_display("MCDONALD'S F31398"), "Mcdonalds")

    def test_empty_and_none_return_empty_string(self):
        self.assertEqual(normalized_display(""), "")
        self.assertEqual(normalized_display(None), "")  # type: ignore[arg-type]

    def test_consistent_with_merchant_key(self):
        raws = [
            "WAL-MART #2297",
            "MTA*NYCT PAYGO",
            "SQ *COFFEE SHOP",
            "PAYPAL *SPOTIFY",
            "LYFT   *AIRPORT",
        ]
        for raw in raws:
            with self.subTest(raw=raw):
                self.assertEqual(
                    normalized_display(raw).upper().replace(" ", ""),
                    merchant_key(raw).replace(" ", ""),
                )
