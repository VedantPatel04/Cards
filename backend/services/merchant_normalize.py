"""
Merchant name normalizer.

Turns a noisy statement description into two things:
  merchant_key()       — Standardized no BS key for comparison and lookup
  normalized_display() — human-readable name for the review queue

Deterministic and depdencny free

The problem: big bad * operator bruh
'*' is used two different ways in bank descriptions:
  1. A payment-processor wrapping a submerchant: "SQ *BLUE BOTTLE COFFEE"
      ->the real merchant is on the RIGHT strip the PAYMENT-PROCERSSOR prefix.
  2. Merchant followed by a descriptor:  "LYFT *AIRPORT", "UBER *EATS"
     ->the real merchant is on the LEFT, strip the DESCRIPTOR
  3. Single-character continuation:      "TRADER JOE*S"
     -> join both sides 

PROCESSOR_PREFIXES is the dividing line. If the left side is a known payment
processor, keep right.

Otherwise, keep left. 

Merchants that do their own
billing (LYFT, UBER, AMZN, GOOGLE) are NOT in this set.
"""

import re

MAX_KEY_CHARS = 255

PROCESSOR_PREFIXES = frozenset([
    "SQ",      # Square
    "PAYPAL",  # PayPal
    "TST",     # Toast POS
    "SP",      # Shopify Pay
    "VENMO",   # Venmo
    "ETSY",    # Etsy Payments
])


def _handle_star(text: str) -> str:
    """
    Apply the three-case * rule. Input and output are uppercase.
    Called before # handling, digit removal, and non-alpha stripping.
    """
    if "*" not in text:
        return text

    left, right = text.split("*", 1)
    left = left.strip()
    right = right.strip()

    if len(right) == 1:
        # "TRADER JOE*S" ->treat * as an apostrophe and join both sides
        return left + right
    if left in PROCESSOR_PREFIXES:
        # "SQ *BLUE BOTTLE COFFEE" -> keep the submerchant on the right
        return right
    # "LYFT *AIRPORT", "UBER *EATS PENDING" -> keep the merchant on the left
    return left


def _strip_noise(text: str) -> str:
    """
    Remove store codes, digits, non-alpha characters, and extra whitespace.
    Input is already uppercase after */#  handling.
    """
    # Letter+digit store codes like "F31398", "A1", "B2"
    text = re.sub(r"\b[A-Z]\d+\b", " ", text)
    # All remaining digits
    text = re.sub(r"\d+", "", text)
    # Apostrophes (including curly): removed without adding a space
    text = text.replace("'", "").replace("\u2019", "")
    # Everything that is not A-Z becomes a space
    text = re.sub(r"[^A-Z]+", " ", text)
    return " ".join(text.split())


def merchant_key(description: str | None) -> str:
    """
    Normalize a raw transaction description into a stable, comparable key.

    Rules (applied in order):
      1. Uppercase
      2. Resolve '*' (processor prefix → keep right; merchant → keep left;
         single trailing letter → join)
      3. Resolve '#' (store/location code — keep left)
      4. Remove letter+digit store codes  ("F31398", "A1")
      5. Remove remaining digits
      6. Remove apostrophes (joined, not spaced)
      7. Replace every non A-Z character with a space
      8. Collapse whitespace, strip, truncate to MAX_KEY_CHARS

    The output is all-uppercase and ASCII-alpha+space.

    Examples:
      "MCDONALD'S F31398"             -> "MCDONALDS"
      "WAL-MART #2297"                -> "WAL MART"
      "MTA*NYCT PAYGO"                -> "MTA"
      "LYFT   *AIRPORT 07-06"         -> "LYFT"
      "SQ *BLUE BOTTLE COFFEE 0042"   -> "BLUE BOTTLE COFFEE"
    """
    if not isinstance(description, str):
        return ""

    text = description.upper()
    text = _handle_star(text)

    if "#" in text:
        text = text.split("#", 1)[0]

    return _strip_noise(text)[:MAX_KEY_CHARS]


def normalized_display(description: str | None) -> str:
    """
    Human-readable merchant name for display in the review queue.

    Applies the same normalization logic as merchant_key but title-cases
    the result. Stored alongside the raw description on Transactions so the
    review queue can show both: the clean name prominently and the noisy
    bank string as evidence below.

    Examples:
      "SQ *BLUE BOTTLE COFFEE 0042 SAN FRANCISCO CA"  -> "Blue Bottle Coffee"
      "WAL-MART #2297"                                -> "Wal Mart"
      "PAYPAL *NETFLIX"                               -> "Netflix"
      "TST* JOE'S PIZZA"                              -> "Joes Pizza"
    """
    
    return merchant_key(description).title()
