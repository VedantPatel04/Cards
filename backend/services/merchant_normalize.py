"""
Phase 1 — Merchant name normalizer.

Turns a noisy statement description into a stable, comparable key so that
variants like "MCDONALD'S F31398" and "MCDONALD'S F25696" collapse to the
same token ("MCDONALDS"). Every later tier (rules, cache, DB, LLM) keys off
this value, so it must be deterministic and dependency-free.
"""


def merchant_key(description: str) -> str:
    """
    Normalize a raw transaction description into a canonical merchant key.

    Intended algorithm (you implement):
      1. uppercase
      2. cut everything after the first '*' or '#' (processor/store noise)
      3. delete digits
      4. replace any non A-Z character with a space
      5. collapse repeated whitespace and strip

    Examples (target behavior — cover these in tests):
      "MCDONALD'S F31398"   -> "MCDONALDS"
      "WAL-MART #2297"      -> "WAL MART"
      "MTA*NYCT PAYGO"      -> "MTA"
      "LYFT   *AIRPORT"     -> "LYFT"

    Returns an uppercase, whitespace-collapsed string (possibly empty).
    """
    # TODO: implement per docstring
    raise NotImplementedError
