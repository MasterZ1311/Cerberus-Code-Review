"""
Luhn Algorithm (Modulus 10) Checksum Validator for PCI-DSS Compliance.
Accurately validates credit card numbers and filters false-positive number sequences.
"""

import re


def validate_luhn(card_candidate: str) -> bool:
    """
    Validates whether a numeric string represents a valid credit card number
    under the Luhn (Mod 10) algorithm.
    """
    # Remove whitespace, hyphens, and dots
    digits = re.sub(r"[\s\-\.]", "", card_candidate)

    # Valid Primary Account Numbers (PAN) are typically 13 to 19 digits
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False

    # Filter trivial false positives (repeated digits like 0000000000000000 or 1111111111111111)
    if len(set(digits)) <= 2:
        return False

    # Filter trivial sequences (e.g. 1234567890123456)
    if digits in ("0123456789" * 3) or digits in ("9876543210" * 3):
        return False

    # Check common IIN/BIN prefixes (Visa: 4, MC: 51-55/22-27, Amex: 34/37, Discover: 6011/65)
    first_digit = digits[0]
    first_two = digits[:2]
    if first_digit not in ("3", "4", "5", "6") and not (22 <= int(first_two) <= 27):
        return False

    # Luhn checksum calculation
    total = 0
    reverse_digits = digits[::-1]

    for index, char in enumerate(reverse_digits):
        val = int(char)
        if index % 2 == 1:
            doubled = val * 2
            total += doubled - 9 if doubled > 9 else doubled
        else:
            total += val

    return (total % 10) == 0


def mask_pan(card_number: str) -> str:
    """Masks a card number showing only the first 6 and last 4 digits (PCI-DSS standard)."""
    clean = re.sub(r"[\s\-]", "", card_number)
    if len(clean) < 10:
        return "*" * len(clean)
    return f"{clean[:6]}{'*' * (len(clean) - 10)}{clean[-4:]}"
