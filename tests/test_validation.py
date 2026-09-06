"""
Tests for Form & Metadata Validation Service (TC-VAL)
"""
import pytest
from services.validation import (
    validate_pan, validate_pincode, validate_email, validate_phone, mask_aadhaar, validate_commercial_terms
)


class TestMetadataValidation:
    # -------------------------------------------------------------
    # PAN Validation Tests (TC-VAL-01, TC-VAL-02)
    # -------------------------------------------------------------
    def test_valid_pan_format(self):
        assert validate_pan("ABCDE1234F") is True
        assert validate_pan("abcde1234f") is True # auto-uppercased

    @pytest.mark.parametrize("invalid_pan", [
        "12345ABCDE",   # Inverted pattern
        "ABCDE12345",   # Trailing digit
        "ABCD1234F",    # 4 letters only
        "ABCDEF1234",   # 6 letters
        "",             # Empty string
        None            # NoneType
    ])
    def test_invalid_pan_rejection(self, invalid_pan):
        assert validate_pan(invalid_pan) is False

    # -------------------------------------------------------------
    # PIN Code Validation Tests (TC-VAL-03, TC-VAL-04)
    # -------------------------------------------------------------
    def test_valid_pincode(self):
        assert validate_pincode("560103") is True
        assert validate_pincode("110001") is True

    @pytest.mark.parametrize("invalid_pin", [
        "012345",       # Starts with zero
        "56010",        # 5 digits
        "5601034",      # 7 digits
        "56010A",       # Alphanumeric
        "",             # Empty
        None            # NoneType
    ])
    def test_invalid_pincode_rejection(self, invalid_pin):
        assert validate_pincode(invalid_pin) is False

    # -------------------------------------------------------------
    # Email Validation Tests (TC-VAL-06)
    # -------------------------------------------------------------
    def test_valid_email(self):
        assert validate_email("user@example.com") is True
        assert validate_email("tenant.sub@golegal.in") is True

    @pytest.mark.parametrize("invalid_email", [
        "user@",
        "@example.com",
        "user@example",
        "userexample.com",
        "",
        None
    ])
    def test_invalid_email_rejection(self, invalid_email):
        assert validate_email(invalid_email) is False

    # -------------------------------------------------------------
    # Phone Validation Tests
    # -------------------------------------------------------------
    def test_valid_phone(self):
        assert validate_phone("9876543210") is True
        assert validate_phone("+919876543210") is True
        assert validate_phone("+91 9876543210") is True
        assert validate_phone("6123456789") is True

    @pytest.mark.parametrize("invalid_phone", [
        "5123456789",   # Starts with 5
        "98765",        # Too short
        "98765432100",  # 11 digits
        "abcdefghij",   # Alphabetic
        "",
        None
    ])
    def test_invalid_phone_rejection(self, invalid_phone):
        assert validate_phone(invalid_phone) is False

    # -------------------------------------------------------------
    # Strict Aadhaar Masking Invariants (TC-VAL-05)
    # -------------------------------------------------------------
    def test_valid_aadhaar_masking(self):
        masked = mask_aadhaar("123456789012")
        assert masked == "XXXXXXXX9012"
        # Zero plaintext verification
        assert "12345678" not in masked
        assert len(masked) == 12

    def test_aadhaar_with_spaces_masking(self):
        masked = mask_aadhaar("1234 5678 9012")
        assert masked == "XXXXXXXX9012"

    @pytest.mark.parametrize("invalid_aadhaar", [
        "12345678901",      # 11 digits
        "1234567890123",    # 13 digits
        "12345678901A",     # Contains letters
        "",
        None
    ])
    def test_invalid_aadhaar_raises_value_error(self, invalid_aadhaar):
        with pytest.raises(ValueError):
            mask_aadhaar(invalid_aadhaar)

    # -------------------------------------------------------------
    # Commercial Terms Bounds Checks (TC-VAL-07)
    # -------------------------------------------------------------
    def test_valid_commercial_terms(self):
        errors = validate_commercial_terms(monthly_rent=25000, deposit=100000, lease_months=11)
        assert len(errors) == 0

    def test_invalid_commercial_terms(self):
        errors = validate_commercial_terms(monthly_rent=300, deposit=-500, lease_months=0)
        assert len(errors) == 3
        assert "Monthly rent must be at least ₹500" in errors
        assert "Security deposit cannot be negative" in errors
        assert "Lease period must be between 1 and 60 months" in errors
