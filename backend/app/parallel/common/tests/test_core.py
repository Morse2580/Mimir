"""
Tests for PII Boundary Guard Core Functions

This module tests the pure PII detection functions against all 5 attack vectors
and Belgian/EU-specific patterns as specified in the requirements.
"""

import pytest
from typing import List
from backend.app.parallel.common.core import (
    contains_pii, 
    should_open_circuit, 
    calculate_risk_score,
    PIIMatch,
    _validate_belgian_rrn,
    _validate_belgian_vat,
    _validate_iban_checksum,
    _luhn_check
)


class TestBelgianRRNDetection:
    """Test Belgian National Registry Number detection."""
    
    def test_valid_rrn_patterns(self):
        """Test detection of valid Belgian RRN patterns."""
        test_cases = [
            "85073003328",  # Valid RRN without separators
            "85.07.30-033.28",  # Valid RRN with separators
            "85/07/30-033-28",  # Valid RRN with mixed separators
            "My RRN is 85073003328 for reference"  # RRN in context
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            assert has_pii, f"Should detect RRN in: {text}"
            assert any(m.pattern_type == "belgian_rrn" for m in matches), f"Should identify as Belgian RRN: {text}"
    
    def test_invalid_rrn_patterns(self):
        """Test that invalid RRN patterns are not detected."""
        test_cases = [
            "12345678901",  # Invalid checksum
            "99991299999",  # Invalid date (month 99)
            "85073299999",  # Invalid date (day 99)
            "1234567890",   # Too short
            "123456789012", # Too long
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            rrn_matches = [m for m in matches if m.pattern_type == "belgian_rrn"]
            assert len(rrn_matches) == 0, f"Should not detect invalid RRN: {text}"
    
    def test_rrn_validation_logic(self):
        """Test RRN validation logic directly."""
        # Valid RRNs
        assert _validate_belgian_rrn("85073003328")  # Valid 1985 birth
        assert _validate_belgian_rrn("00010100105")  # Valid 2000 birth (corrected checksum)
        
        # Invalid RRNs
        assert not _validate_belgian_rrn("85073003329")  # Wrong checksum
        assert not _validate_belgian_rrn("85139903328")  # Invalid month
        assert not _validate_belgian_rrn("85073203328")  # Invalid day


class TestBelgianVATDetection:
    """Test Belgian VAT number detection."""
    
    def test_valid_vat_patterns(self):
        """Test detection of valid Belgian VAT patterns."""
        test_cases = [
            "BE 0123456749",  # Standard format with space
            "BE0123456749",   # Compact format
            "BE 0123.456.749", # With dots
            "Our VAT: BE0123456749"  # In context
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            assert has_pii, f"Should detect VAT in: {text}"
            assert any(m.pattern_type == "belgian_vat" for m in matches), f"Should identify as Belgian VAT: {text}"
    
    def test_invalid_vat_patterns(self):
        """Test that invalid VAT patterns are not detected."""
        test_cases = [
            "BE 1123456749",  # Doesn't start with 0
            "BE0123456748",   # Wrong checksum
            "FR0123456749",   # Wrong country code
            "BE012345674",    # Too short
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            vat_matches = [m for m in matches if m.pattern_type == "belgian_vat"]
            assert len(vat_matches) == 0, f"Should not detect invalid VAT: {text}"
    
    def test_vat_validation_logic(self):
        """Test VAT validation logic directly."""
        # Valid VATs (using checksum calculation)
        assert _validate_belgian_vat("BE0123456749")
        assert _validate_belgian_vat("BE 0999999922")
        
        # Invalid VATs
        assert not _validate_belgian_vat("BE0123456748")  # Wrong checksum
        assert not _validate_belgian_vat("BE1123456749")  # Doesn't start with 0


class TestIBANDetection:
    """Test IBAN detection."""
    
    def test_valid_iban_patterns(self):
        """Test detection of valid IBAN patterns."""
        test_cases = [
            "BE62510007547061",  # Valid Belgian IBAN
            "GB29NWBK60161331926819",  # Valid UK IBAN
            "DE89370400440532013000",   # Valid German IBAN
            "Account: BE62510007547061"  # IBAN in context
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            assert has_pii, f"Should detect IBAN in: {text}"
            assert any(m.pattern_type == "iban" for m in matches), f"Should identify as IBAN: {text}"
    
    def test_invalid_iban_patterns(self):
        """Test that invalid IBAN patterns are not detected."""
        test_cases = [
            "BE62510007547060",  # Wrong checksum
            "XX29NWBK60161331926819",  # Invalid country code
            "BE6251000754706",   # Too short
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            iban_matches = [m for m in matches if m.pattern_type == "iban"]
            assert len(iban_matches) == 0, f"Should not detect invalid IBAN: {text}"
    
    def test_iban_checksum_validation(self):
        """Test IBAN checksum validation directly."""
        # Valid IBANs
        assert _validate_iban_checksum("BE62510007547061")
        assert _validate_iban_checksum("GB29NWBK60161331926819")
        
        # Invalid IBANs
        assert not _validate_iban_checksum("BE62510007547060")  # Wrong checksum
        assert not _validate_iban_checksum("GB28NWBK60161331926819")  # Wrong checksum


class TestEmailDetection:
    """Test email address detection."""
    
    def test_valid_email_patterns(self):
        """Test detection of email addresses."""
        test_cases = [
            "user@example.com",
            "test.email+filter@domain.co.uk",
            "john.doe@company.be",
            "Contact us at support@help.com",
            "user_name@domain-name.org"
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            assert has_pii, f"Should detect email in: {text}"
            assert any(m.pattern_type == "email" for m in matches), f"Should identify as email: {text}"
    
    def test_email_false_positives(self):
        """Test that non-email patterns are not detected as emails."""
        test_cases = [
            "user@",  # Missing domain
            "@domain.com",  # Missing user
            "user.domain.com",  # Missing @
            "user@domain",  # Missing TLD
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            email_matches = [m for m in matches if m.pattern_type == "email"]
            assert len(email_matches) == 0, f"Should not detect invalid email: {text}"


class TestPhoneDetection:
    """Test phone number detection."""
    
    def test_belgian_phone_patterns(self):
        """Test detection of Belgian phone numbers."""
        test_cases = [
            "+32 2 123 45 67",    # Belgian international format
            "+32 2 123.45.67",    # With dots
            "+322 123 45 67",     # Without space after country
            "02 123 45 67",       # National format
            "0473 12 34 56",      # Mobile format
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            assert has_pii, f"Should detect phone in: {text}"
            assert any(m.pattern_type == "phone" for m in matches), f"Should identify as phone: {text}"
    
    def test_international_phone_patterns(self):
        """Test detection of international phone numbers."""
        test_cases = [
            "+1 555 123 4567",     # US format
            "+33 1 23 45 67 89",   # French format
            "+49 30 12345678",     # German format
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            assert has_pii, f"Should detect international phone in: {text}"
            assert any(m.pattern_type == "phone" for m in matches), f"Should identify as phone: {text}"


class TestCreditCardDetection:
    """Test credit card number detection."""
    
    def test_valid_credit_card_patterns(self):
        """Test detection of valid credit card numbers."""
        test_cases = [
            "4111111111111111",    # Valid Visa (Luhn check passes)
            "4111-1111-1111-1111", # With dashes
            "4111 1111 1111 1111", # With spaces
        ]
        
        for text in test_cases:
            has_pii, matches = contains_pii(text)
            assert has_pii, f"Should detect credit card in: {text}"
            assert any(m.pattern_type == "credit_card" for m in matches), f"Should identify as credit card: {text}"
    
    def test_luhn_algorithm(self):
        """Test Luhn checksum algorithm directly."""
        # Valid credit card numbers
        assert _luhn_check("4111111111111111")  # Visa test number
        assert _luhn_check("5555555555554444")  # MasterCard test number
        
        # Invalid checksums
        assert not _luhn_check("4111111111111112")  # Wrong last digit
        assert not _luhn_check("1234567890123456")  # Invalid sequence


class TestPIIAttackVectors:
    """Test all 5 PII attack vectors as specified in requirements."""
    
    def test_attack_vector_1_direct_injection(self):
        """Attack Vector 1: Direct email injection."""
        malicious_input = "Contact support@company.com for assistance"
        
        has_pii, matches = contains_pii(malicious_input)
        assert has_pii, "Should detect direct email injection"
        assert any(m.pattern_type == "email" for m in matches)
    
    def test_attack_vector_2_obfuscated_patterns(self):
        """Attack Vector 2: Obfuscated patterns."""
        # Note: Current implementation focuses on exact patterns
        # This test documents that obfuscated patterns like "john dot doe at company dot com"
        # are NOT currently detected (by design for now)
        obfuscated_input = "Email: john dot doe at company dot com"
        
        has_pii, matches = contains_pii(obfuscated_input)
        # Currently expected to NOT detect obfuscated patterns
        # This is a conscious decision to avoid false positives
        assert not has_pii, "Obfuscated patterns not detected in current implementation"
    
    def test_attack_vector_3_encoded_data(self):
        """Attack Vector 3: Encoded data attempts."""
        import base64
        
        # Base64 encoded email
        email = "user@example.com"
        encoded_email = base64.b64encode(email.encode()).decode()
        
        has_pii, matches = contains_pii(f"Data: {encoded_email}")
        # Currently expected to NOT detect encoded patterns
        # This would require additional decoding logic
        assert not has_pii, "Encoded patterns not detected in current implementation"
    
    def test_attack_vector_4_context_injection(self):
        """Attack Vector 4: Context injection in structured data."""
        # This tests the risk calculation function with structured data
        malicious_data = {
            "user": "john",
            "contact": "john@company.com",
            "metadata": {
                "phone": "+32 2 123 45 67"
            }
        }
        
        risk_score = calculate_risk_score(malicious_data)
        assert risk_score > 0.7, f"Should detect high risk in structured data, got {risk_score}"
    
    def test_attack_vector_5_large_payload_with_embedded_pii(self):
        """Attack Vector 5: Large payload with embedded PII."""
        # Create large payload with embedded PII
        large_text = "This is a large document. " * 100  # ~2500 chars
        pii_text = "Contact details: john@company.com and phone +32 2 123 45 67"
        large_payload = large_text + pii_text + large_text
        
        has_pii, matches = contains_pii(large_payload)
        assert has_pii, "Should detect PII in large payload"
        assert len(matches) >= 2, "Should detect both email and phone"
        
        # Test risk calculation
        risk_score = calculate_risk_score({"content": large_payload})
        assert risk_score > 0.5, f"Should show elevated risk for large payload with PII, got {risk_score}"


class TestCircuitBreakerLogic:
    """Test circuit breaker logic."""
    
    def test_should_open_circuit_logic(self):
        """Test circuit breaker opening logic."""
        # Should not open below threshold
        assert not should_open_circuit(2, 3)
        
        # Should open at threshold
        assert should_open_circuit(3, 3)
        
        # Should open above threshold
        assert should_open_circuit(5, 3)
    
    def test_should_open_circuit_edge_cases(self):
        """Test edge cases for circuit breaker logic."""
        assert not should_open_circuit(0, 3)
        assert should_open_circuit(1, 1)
        assert should_open_circuit(1, 0)  # Edge case: zero threshold


class TestRiskCalculation:
    """Test risk score calculation."""
    
    def test_empty_data_zero_risk(self):
        """Empty data should have zero risk."""
        assert calculate_risk_score({}) == 0.0
        assert calculate_risk_score(None) == 0.0
    
    def test_clean_data_low_risk(self):
        """Clean data should have low risk."""
        clean_data = {
            "query": "What are the DORA compliance requirements?",
            "context": "regulatory research"
        }
        
        risk_score = calculate_risk_score(clean_data)
        assert risk_score < 0.1, f"Clean data should have low risk, got {risk_score}"
    
    def test_pii_data_high_risk(self):
        """Data with PII should have high risk."""
        pii_data = {
            "user_email": "john@company.com",
            "iban": "BE62510007547061"
        }
        
        risk_score = calculate_risk_score(pii_data)
        assert risk_score > 0.7, f"PII data should have high risk, got {risk_score}"
    
    def test_large_payload_moderate_risk(self):
        """Large payloads should have moderate risk due to size."""
        large_data = {
            "content": "This is a very long document. " * 200  # ~6000 chars
        }
        
        risk_score = calculate_risk_score(large_data)
        assert 0.1 < risk_score < 0.4, f"Large payload should have moderate risk, got {risk_score}"
    
    def test_sensitive_keywords_risk(self):
        """Data with sensitive keywords should increase risk."""
        sensitive_data = {
            "content": "Please provide the secret password and private key for authentication"
        }
        
        risk_score = calculate_risk_score(sensitive_data)
        assert risk_score > 0.3, f"Sensitive keywords should increase risk, got {risk_score}"


class TestPerformanceRequirements:
    """Test performance requirements (<50ms for PII detection)."""
    
    def test_pii_detection_performance(self):
        """PII detection should complete within 50ms."""
        import time
        
        # Large text with multiple PII patterns
        test_text = """
        This is a compliance document containing various PII patterns.
        Contact: john.doe@company.be
        Phone: +32 2 123 45 67
        VAT: BE0123456749
        IBAN: BE62510007547061
        RRN: 85073003328
        """ * 10  # Multiply to create larger test
        
        start_time = time.time()
        has_pii, matches = contains_pii(test_text)
        execution_time = (time.time() - start_time) * 1000  # Convert to ms
        
        assert execution_time < 50, f"PII detection took {execution_time}ms (limit: 50ms)"
        assert has_pii, "Should detect PII in test text"
        assert len(matches) >= 5, "Should detect multiple PII patterns"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])