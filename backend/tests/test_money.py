"""Unit tests for pure financial money utilities."""

from decimal import Decimal
import pytest

from app.domain.money import ceil_div, format_inr, rupees_to_paise


# ==============================================================================
# 1. Tests for rupees_to_paise
# ==============================================================================

class TestRupeesToPaiseValid:
    """Test valid inputs for rupees_to_paise."""

    @pytest.mark.parametrize(
        "amount_input, expected_paise",
        [
            ("0", 0),
            ("0.0", 0),
            ("0.00", 0),
            ("1", 100),
            ("10", 1000),
            ("1234", 123400),
            ("1234.5", 123450),
            ("1234.50", 123450),
            ("1234.56", 123456),
            ("0.1", 10),
            ("0.10", 10),
            ("0.01", 1),
            ("0.05", 5),
            ("1500000", 150000000),          # 15 Lakh INR
            ("100000000", 10000000000),      # 1 Crore INR
            ("999999999.99", 99999999999),   # Large precision
        ],
    )
    def test_valid_decimal_strings(self, amount_input: str, expected_paise: int):
        assert rupees_to_paise(amount_input) == expected_paise

    @pytest.mark.parametrize(
        "amount_input, expected_paise",
        [
            (Decimal("0"), 0),
            (Decimal("0.00"), 0),
            (Decimal("0.000"), 0),
            (Decimal("0.01"), 1),
            (Decimal("0.10"), 10),
            (Decimal("1.00"), 100),
            (Decimal("1.230"), 123),
            (Decimal("1234.56"), 123456),
            (Decimal("10000"), 1000000),
            (Decimal("50000000.50"), 5000000050),
        ],
    )
    def test_valid_decimal_instances(self, amount_input: Decimal, expected_paise: int):
        assert rupees_to_paise(amount_input) == expected_paise


class TestRupeesToPaiseInvalid:
    """Test rejection of malformed, negative, non-finite, and excess-precision inputs."""

    @pytest.mark.parametrize(
        "malformed_str",
        [
            "",
            "   ",
            "abc",
            "12.34.56",
            "12.",
            ".50",
            "0123",            # Leading zero on non-zero integer
            "1,234.56",        # Comma in decimal string
            " 1234 ",          # Leading/trailing whitespace
            "1e5",             # Scientific notation
            "1E2",
            "+100",            # Explicit plus sign
        ],
    )
    def test_rejects_malformed_strings(self, malformed_str: str):
        with pytest.raises(ValueError):
            rupees_to_paise(malformed_str)

    @pytest.mark.parametrize(
        "negative_input",
        [
            "-1",
            "-0.01",
            "-1234.56",
            "-0",
            "-0.00",
            Decimal("-1"),
            Decimal("-0.01"),
            Decimal("-1234.56"),
            Decimal("-0"),
            Decimal("-0.00"),
        ],
    )
    def test_rejects_negative_amounts(self, negative_input):
        with pytest.raises(ValueError):
            rupees_to_paise(negative_input)

    @pytest.mark.parametrize(
        "non_finite",
        [
            Decimal("NaN"),
            Decimal("sNaN"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
        ],
    )
    def test_rejects_nan_and_infinity(self, non_finite: Decimal):
        with pytest.raises(ValueError):
            rupees_to_paise(non_finite)

    @pytest.mark.parametrize(
        "excess_precision",
        [
            "0.001",
            "1234.567",
            "10.9999",
            Decimal("0.001"),
            Decimal("1.231"),
            Decimal("1234.567"),
            Decimal("10.1234"),
        ],
    )
    def test_rejects_more_than_two_decimal_places(self, excess_precision):
        with pytest.raises(ValueError):
            rupees_to_paise(excess_precision)

    @pytest.mark.parametrize(
        "unsupported_type",
        [
            100,               # int
            12.34,             # float
            0.0,               # float
            True,              # bool
            False,             # bool
            None,
            ["1234"],
            {"amount": "1234"},
        ],
    )
    def test_rejects_unsupported_types(self, unsupported_type):
        with pytest.raises(TypeError):
            rupees_to_paise(unsupported_type)


# ==============================================================================
# 2. Tests for format_inr
# ==============================================================================

class TestFormatINRValid:
    """Test INR string formatting using Indian numbering system."""

    @pytest.mark.parametrize(
        "paise, expected_formatted",
        [
            (0, "₹0.00"),
            (1, "₹0.01"),
            (5, "₹0.05"),
            (9, "₹0.09"),
            (10, "₹0.10"),
            (99, "₹0.99"),
            (100, "₹1.00"),
            (1000, "₹10.00"),
            (10000, "₹100.00"),
            (100000, "₹1,000.00"),
            (123456, "₹1,234.56"),
            (1000000, "₹10,000.00"),
            (10000000, "₹1,00,000.00"),                                # 1 Lakh INR
            (123456789, "₹12,34,567.89"),                              # 12.34 Lakh INR
            (1000000000, "₹1,00,00,000.00"),                          # 1 Crore INR
            (1500000000, "₹1,50,00,000.00"),                          # 1.5 Crore INR
            (15000000000, "₹15,00,00,000.00"),                        # 15 Crore INR
            (100000000000, "₹1,00,00,00,000.00"),                     # 100 Crore INR
        ],
    )
    def test_valid_inr_formatting(self, paise: int, expected_formatted: str):
        assert format_inr(paise) == expected_formatted


class TestFormatINRInvalid:
    """Test error handling in format_inr for negative or wrong-type inputs."""

    @pytest.mark.parametrize("negative_paise", [-1, -100, -123456])
    def test_rejects_negative_paise(self, negative_paise: int):
        with pytest.raises(ValueError):
            format_inr(negative_paise)

    @pytest.mark.parametrize(
        "invalid_type",
        [
            12.34,             # float
            0.0,               # float
            True,              # bool
            False,             # bool
            "123456",          # str
            Decimal("123456"), # Decimal
            None,
        ],
    )
    def test_rejects_invalid_types(self, invalid_type):
        with pytest.raises(TypeError):
            format_inr(invalid_type)


# ==============================================================================
# 3. Tests for ceil_div
# ==============================================================================

class TestCeilDivValid:
    """Test ceiling division mathematical correctness."""

    @pytest.mark.parametrize(
        "numerator, denominator, expected_quotient",
        [
            # Exact divisions
            (0, 30, 0),
            (0, 1, 0),
            (90, 30, 3),
            (100, 10, 10),
            (10, 1, 10),
            (120, 12, 10),

            # Non-exact divisions (rounding ceiling)
            (100, 30, 4),
            (10, 3, 4),
            (5, 2, 3),
            (1, 2, 1),
            (5, 10, 1),
            (1, 100, 1),
            (120001, 12, 10001),
            (12000000, 12, 1000000),
            (12000001, 12, 1000001),
        ],
    )
    def test_valid_ceil_div_calculations(
        self, numerator: int, denominator: int, expected_quotient: int
    ):
        assert ceil_div(numerator, denominator) == expected_quotient


class TestCeilDivInvalid:
    """Test error handling in ceil_div for negative values, non-positive denominators, and invalid types."""

    @pytest.mark.parametrize("invalid_denominator", [0, -1, -30])
    def test_rejects_zero_or_negative_denominator(self, invalid_denominator: int):
        with pytest.raises(ValueError):
            ceil_div(100, invalid_denominator)

    @pytest.mark.parametrize("negative_numerator", [-1, -100, -500])
    def test_rejects_negative_numerator(self, negative_numerator: int):
        with pytest.raises(ValueError):
            ceil_div(negative_numerator, 10)

    @pytest.mark.parametrize(
        "num, den",
        [
            (10.0, 2),
            (10, 2.0),
            (10.5, 2.5),
            (True, 2),
            (10, False),
            (True, True),
            ("10", 2),
            (10, "2"),
            (None, 10),
            (10, None),
        ],
    )
    def test_rejects_floats_booleans_and_invalid_types(self, num, den):
        with pytest.raises(TypeError):
            ceil_div(num, den)
