"""
PII Boundary Guard - Core Detection Functions

This module contains pure functions for detecting PII patterns
specific to Belgian/EU financial regulations.

SECURITY CRITICAL: These functions are the first line of defense
against PII leaks to external APIs like Parallel.ai.
"""

import re
from typing import List, Tuple
from dataclasses import dataclass


@dataclass(frozen=True)
class PIIMatch:
    """Represents a detected PII pattern."""

    pattern_type: str
    matched_text: str
    confidence: float
    start_pos: int
    end_pos: int


def contains_pii(text: str) -> Tuple[bool, List[PIIMatch]]:
    """
    Detect PII patterns in text using Belgian/EU-specific patterns.

    Args:
        text: Input text to analyze

    Returns:
        Tuple of (has_pii, list_of_matches)

    MUST be deterministic - same input always produces same output.
    """
    if not text or not isinstance(text, str):
        return False, []

    matches = []

    # Belgian National Registry Number (Rijksregisternummer)
    # Format: YYMMDD-XXX-XX (11 digits with optional dashes)
    rrn_pattern = r"\b\d{2}[./-]?\d{2}[./-]?\d{2}[./-]?\d{3}[./-]?\d{2}\b"
    for match in re.finditer(rrn_pattern, text):
        if _validate_belgian_rrn(match.group()):
            matches.append(
                PIIMatch(
                    pattern_type="belgian_rrn",
                    matched_text=match.group(),
                    confidence=0.95,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )

    # Belgian VAT Number (BTW/TVA)
    # Format: BE 0XXX.XXX.XXX or BE0XXXXXXXXX
    vat_pattern = r"\bBE\s?0?\d{3}[.\s]?\d{3}[.\s]?\d{3}\b"
    for match in re.finditer(vat_pattern, text, re.IGNORECASE):
        if _validate_belgian_vat(match.group()):
            matches.append(
                PIIMatch(
                    pattern_type="belgian_vat",
                    matched_text=match.group(),
                    confidence=0.9,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )

    # IBAN (International Bank Account Number)
    # Format: Country code (2) + check digits (2) + account number (up to 30)
    iban_pattern = r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b"
    for match in re.finditer(iban_pattern, text):
        if _validate_iban_checksum(match.group()):
            matches.append(
                PIIMatch(
                    pattern_type="iban",
                    matched_text=match.group(),
                    confidence=0.95,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )

    # Email addresses (comprehensive pattern)
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    for match in re.finditer(email_pattern, text):
        matches.append(
            PIIMatch(
                pattern_type="email",
                matched_text=match.group(),
                confidence=0.98,
                start_pos=match.start(),
                end_pos=match.end(),
            )
        )

    # Phone numbers (international and Belgian formats)
    # Belgian: +32 X XX XX XX XX, 0X XX XX XX XX
    phone_patterns = [
        r"\+32\s?\d{1,3}\s?\d{2}[\s.]?\d{2}[\s.]?\d{2}[\s.]?\d{2}",  # Belgian international
        r"\b0\d\s\d{3}\s\d{2}\s\d{2}\b",  # Belgian landline format (02 123 45 67)
        r"\b0\d{3}\s\d{2}\s\d{2}\s\d{2}\b",  # Belgian mobile format (0473 12 34 56)
        r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}",  # General international
    ]

    for pattern in phone_patterns:
        for match in re.finditer(pattern, text):
            matches.append(
                PIIMatch(
                    pattern_type="phone",
                    matched_text=match.group(),
                    confidence=0.85,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )

    # IP addresses
    ip_pattern = r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    for match in re.finditer(ip_pattern, text):
        if _validate_ip_address(match.group()):
            matches.append(
                PIIMatch(
                    pattern_type="ip_address",
                    matched_text=match.group(),
                    confidence=0.8,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )

    # Credit card numbers (basic detection)
    cc_pattern = r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"
    for match in re.finditer(cc_pattern, text):
        if _luhn_check(match.group().replace("-", "").replace(" ", "")):
            matches.append(
                PIIMatch(
                    pattern_type="credit_card",
                    matched_text=match.group(),
                    confidence=0.9,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )

    return len(matches) > 0, matches


def _validate_belgian_rrn(rrn: str) -> bool:
    """Validate Belgian National Registry Number format and checksum."""
    # Remove separators
    digits = re.sub(r"[./-]", "", rrn)

    if len(digits) != 11 or not digits.isdigit():
        return False

    # Basic date validation (YYMMDD)
    year = int(digits[:2])
    month = int(digits[2:4])
    day = int(digits[4:6])

    if month < 1 or month > 12 or day < 1 or day > 31:
        return False

    # Checksum validation
    base_number = int(digits[:9])
    check_digits = int(digits[9:11])

    # Try both century assumptions (19xx and 20xx)
    remainder_19 = base_number % 97

    # For years 00-99, we need to try both centuries
    if year < 50:  # Assume 20xx
        remainder_20 = int(f"2{digits[:9]}") % 97
        return check_digits == (97 - remainder_19) or check_digits == (
            97 - remainder_20
        )
    else:  # Assume 19xx
        return check_digits == (97 - remainder_19)


def _validate_belgian_vat(vat: str) -> bool:
    """Validate Belgian VAT number format and checksum."""
    # Extract digits only
    digits = re.sub(r"[^0-9]", "", vat)

    if len(digits) != 10:
        return False

    # First digit must be 0 for Belgian VAT
    if digits[0] != "0":
        return False

    # Checksum validation
    base = int(digits[:8])
    check = int(digits[8:10])

    return check == (97 - (base % 97))


def _validate_iban_checksum(iban: str) -> bool:
    """Validate IBAN checksum using mod-97 algorithm."""
    if len(iban) < 4:
        return False

    # Move first 4 characters to the end
    rearranged = iban[4:] + iban[:4]

    # Replace letters with numbers (A=10, B=11, ..., Z=35)
    numeric_string = ""
    for char in rearranged:
        if char.isalpha():
            numeric_string += str(ord(char.upper()) - ord("A") + 10)
        else:
            numeric_string += char

    try:
        return int(numeric_string) % 97 == 1
    except ValueError:
        return False


def _validate_ip_address(ip: str) -> bool:
    """Validate IP address format and ranges."""
    parts = ip.split(".")
    if len(parts) != 4:
        return False

    try:
        for part in parts:
            # Check for leading zeros (except "0" itself)
            if len(part) > 1 and part[0] == "0":
                return False

            num = int(part)
            if num < 0 or num > 255:
                return False

        # Additional check: avoid common false positives like version numbers
        # If all parts are relatively small, it's likely a version number
        nums = [int(part) for part in parts]
        if all(num < 10 for num in nums) or all(num < 100 for num in nums[:3]):
            return False

        return True
    except ValueError:
        return False


def _luhn_check(card_number: str) -> bool:
    """Validate credit card number using Luhn algorithm."""
    if not card_number.isdigit() or len(card_number) < 13:
        return False

    digits = [int(d) for d in card_number]
    checksum = 0

    # Process from right to left
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:  # Every second digit from right
            digit *= 2
            if digit > 9:
                digit = digit // 10 + digit % 10
        checksum += digit

    return checksum % 10 == 0


def should_open_circuit(failures: int, threshold: int) -> bool:
    """
    Determine if circuit breaker should open based on failure count.

    Args:
        failures: Number of consecutive failures
        threshold: Failure threshold (typically 3)

    Returns:
        True if circuit should open, False otherwise

    MUST be pure function - no side effects.
    """
    return failures >= threshold


def calculate_risk_score(data: dict) -> float:
    """
    Calculate risk score for data payload (0.0-1.0).

    Args:
        data: Dictionary containing the payload to analyze

    Returns:
        Risk score from 0.0 (safe) to 1.0 (high risk)

    MUST be deterministic - same input produces same output.
    """
    if not data:
        return 0.0

    risk_factors = []

    # Convert data to string for analysis
    text_content = _extract_text_from_dict(data)

    # Check for PII
    has_pii, pii_matches = contains_pii(text_content)
    if has_pii:
        # Risk increases with number and confidence of PII matches
        # Use higher weights for PII risk
        total_confidence = sum(match.confidence for match in pii_matches)
        pii_risk = min(1.0, total_confidence / 2.0)  # More aggressive scaling
        risk_factors.append(pii_risk)

    # Payload size risk (larger payloads harder to audit)
    payload_size = len(text_content)
    size_risk = min(1.0, payload_size / 15000)  # 15k char limit
    risk_factors.append(size_risk * 0.3)  # Weight size risk lower

    # Sensitive keywords
    sensitive_keywords = [
        "password",
        "secret",
        "token",
        "key",
        "private",
        "confidential",
        "ssn",
        "social",
        "account",
        "credit",
    ]
    keyword_matches = sum(
        1 for keyword in sensitive_keywords if keyword.lower() in text_content.lower()
    )
    keyword_risk = min(
        1.0, keyword_matches / 3.0
    )  # Scale by fewer keywords for higher impact
    risk_factors.append(keyword_risk * 0.6)  # Higher weight for sensitive keywords

    # Return maximum risk factor (most conservative approach)
    return max(risk_factors) if risk_factors else 0.0


def _extract_text_from_dict(data: dict, max_depth: int = 3) -> str:
    """Extract text content from nested dictionary for analysis."""
    if max_depth <= 0:
        return ""

    text_parts = []

    for key, value in data.items():
        # Include keys in analysis
        text_parts.append(str(key))

        if isinstance(value, str):
            text_parts.append(value)
        elif isinstance(value, dict):
            text_parts.append(_extract_text_from_dict(value, max_depth - 1))
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    text_parts.append(_extract_text_from_dict(item, max_depth - 1))
        else:
            text_parts.append(str(value))

    return " ".join(text_parts)
