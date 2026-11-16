
"""StatDesk — Shared SPC Number Formatter.

Centralized formatting for SPC chart labels
and statistical Session Output.

Rules:
- Zero: 0.000
- Ordinary values: exactly 3 decimal places
- Large values (>= 1e6): scientific notation
- Small nonzero values (< 1e-3): scientific notation
- NaN and Infinity are rejected

Formatting is presentation-only.

Never use formatted values for statistical
calculations or special-cause detection.
"""

from math import isfinite


# ======================================================
# DISPLAY CONFIGURATION
# ======================================================

DECIMAL_PLACES = 3

SCIENTIFIC_UPPER_THRESHOLD = 1e6
SCIENTIFIC_LOWER_THRESHOLD = 1e-3


# ======================================================
# SHARED FORMATTER
# ======================================================

def format_spc_number(value) -> str:
    """Format one finite SPC statistical value.

    Examples
    --------
    100.0       -> 100.000
    10.840292   -> 10.840
    0.25        -> 0.250
    0.0         -> 0.000
    1.5319e150  -> 1.532e+150
    0.00001234  -> 1.234e-05

    This function returns text only.
    It does not change the input value.
    """

    try:
        number = float(value)

    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "Nilai SPC tidak dapat diformat "
            "sebagai angka."
        ) from exc

    if not isfinite(number):
        raise ValueError(
            "Nilai SPC harus finite; "
            "NaN/Infinity tidak diperbolehkan."
        )

    if number == 0.0:
        return "0.000"

    magnitude = abs(number)

    # Scientific notation for extreme magnitudes.
    if (
        magnitude >= SCIENTIFIC_UPPER_THRESHOLD
        or magnitude < SCIENTIFIC_LOWER_THRESHOLD
    ):
        return f"{number:.{DECIMAL_PLACES}e}"

    formatted = f"{number:.{DECIMAL_PLACES}f}"

    if formatted == "-0.000":
        return "0.000"

    return formatted
