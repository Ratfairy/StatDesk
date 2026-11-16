
"""StatDesk — Shewhart special-cause Rules 1–4.

Statistical rule profiles:
- standard_6_14: 6-point trend and 14-point alternating pattern.
- minitab18_observed: experimental 7-point trend and 15-point
  alternating pattern, matching selected observed Minitab cases.

The identifiers remain unchanged for compatibility with existing GUI
and analysis calls. The profile name describes rule behavior, not a
claim that every version of Minitab implements the same convention.

This module never calculates or modifies control limits.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real


RULE_PROFILE_STANDARD = "standard_6_14"
RULE_PROFILE_MINITAB18_OBSERVED = "minitab18_observed"

RULE_PROFILE_LABELS = {
    RULE_PROFILE_STANDARD: "6/14-point pattern rules (Nelson-style)",
    RULE_PROFILE_MINITAB18_OBSERVED: (
        "7/15-point pattern rules (Minitab-observed, experimental)"
    ),
}

PROFILE_WINDOWS = {
    RULE_PROFILE_STANDARD: {
        1: 1,
        2: 9,
        3: 6,
        4: 14,
    },
    RULE_PROFILE_MINITAB18_OBSERVED: {
        1: 1,
        2: 9,
        3: 7,
        4: 15,
    },
}

# Backward-compatible names.
RULE_WINDOWS = PROFILE_WINDOWS[RULE_PROFILE_STANDARD]

RULE_DESCRIPTIONS = {
    1: "One point strictly outside the 3-sigma control limits",
    2: "Nine consecutive points strictly on the same side of CL",
    3: "Six consecutive points strictly increasing or decreasing",
    4: "Fourteen consecutive points strictly alternating up and down",
}


class SpcRulesError(ValueError):
    """Invalid configuration or numerical input."""


@dataclass(frozen=True)
class RuleFinding:
    test: int
    point: int
    window_start: int


@dataclass(frozen=True)
class RulesResult:
    enabled_tests: tuple[int, ...]
    n_points: int
    findings: tuple[RuleFinding, ...]
    rule_profile: str = RULE_PROFILE_STANDARD

    def points_for(self, test: int) -> tuple[int, ...]:
        if test not in self.enabled_tests:
            raise SpcRulesError(
                f"Test {test} tidak diaktifkan."
            )

        return tuple(
            finding.point
            for finding in self.findings
            if finding.test == test
        )


def get_rule_windows(rule_profile=RULE_PROFILE_STANDARD):
    """Return validated rule window definitions."""
    if rule_profile not in PROFILE_WINDOWS:
        raise SpcRulesError(
            f"Rule profile tidak dikenal: {rule_profile!r}."
        )

    return PROFILE_WINDOWS[rule_profile]


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise SpcRulesError(
            f"{label} harus angka Numeric."
        )

    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise SpcRulesError(
            f"{label} tidak dapat dikonversi."
        ) from exc

    if not isfinite(number):
        raise SpcRulesError(
            f"{label}: NaN/Infinity tidak diperbolehkan."
        )

    return number


def evaluate_spc_rules(
    points,
    *,
    center_line,
    ucl,
    lcl,
    enabled_tests=(1,),
    rule_profile=RULE_PROFILE_STANDARD,
) -> RulesResult:
    """Evaluate rules on a time-ordered plotted series.

    Signals are 1-based and recorded at the last point of
    each qualifying window.

    Control limits are supplied externally and never changed.
    """

    windows = get_rule_windows(rule_profile)

    cl = _number(center_line, "Center line")
    upper = _number(ucl, "UCL")
    lower = _number(lcl, "LCL")

    if not lower < cl < upper:
        raise SpcRulesError("Wajib LCL < CL < UCL.")

    try:
        selected = tuple(enabled_tests)
    except TypeError as exc:
        raise SpcRulesError(
            "enabled_tests harus urutan nomor test."
        ) from exc

    if not selected or any(
        type(test) is not int or test not in windows
        for test in selected
    ):
        raise SpcRulesError(
            "Pilih minimal satu Test dari 1, 2, 3, 4."
        )

    if len(set(selected)) != len(selected):
        raise SpcRulesError(
            "Nomor test tidak boleh duplikat."
        )

    selected = tuple(sorted(selected))

    try:
        raw_values = tuple(points)
    except TypeError as exc:
        raise SpcRulesError(
            "points harus urutan pengukuran."
        ) from exc

    if not raw_values:
        raise SpcRulesError(
            "Minimal diperlukan satu titik data."
        )

    values = tuple(
        _number(value, f"Titik {index}")
        for index, value in enumerate(raw_values, start=1)
    )

    findings = []

    for end in range(1, len(values) + 1):

        # RULE 1 — strictly outside control limits.
        if 1 in selected:
            current = values[end - 1]

            if current < lower or current > upper:
                findings.append(
                    RuleFinding(
                        test=1,
                        point=end,
                        window_start=end,
                    )
                )

        # RULE 2 — 9 consecutive points on the same side.
        # Equality to CL breaks the run.
        if 2 in selected and end >= windows[2]:
            size = windows[2]
            window = values[end - size:end]

            all_above = all(value > cl for value in window)
            all_below = all(value < cl for value in window)

            if all_above or all_below:
                findings.append(
                    RuleFinding(
                        test=2,
                        point=end,
                        window_start=end - size + 1,
                    )
                )

        # RULE 3 — strictly monotonic points.
        # Standard: 6 points. Observed profile: 7 points.
        if 3 in selected and end >= windows[3]:
            size = windows[3]
            window = values[end - size:end]

            increasing = all(
                b > a for a, b in zip(window, window[1:])
            )
            decreasing = all(
                b < a for a, b in zip(window, window[1:])
            )

            if increasing or decreasing:
                findings.append(
                    RuleFinding(
                        test=3,
                        point=end,
                        window_start=end - size + 1,
                    )
                )

        # RULE 4 — strictly alternating up/down.
        # Standard: 14 points. Observed profile: 15 points.
        if 4 in selected and end >= windows[4]:
            size = windows[4]
            window = values[end - size:end]

            directions = [
                1 if b > a else -1 if b < a else 0
                for a, b in zip(window, window[1:])
            ]

            no_ties = all(d != 0 for d in directions)
            alternating = all(
                a != b
                for a, b in zip(directions, directions[1:])
            )

            if no_ties and alternating:
                findings.append(
                    RuleFinding(
                        test=4,
                        point=end,
                        window_start=end - size + 1,
                    )
                )

    return RulesResult(
        enabled_tests=selected,
        n_points=len(values),
        findings=tuple(findings),
        rule_profile=rule_profile,
    )


def format_spc_rules_report(result: RulesResult) -> str:
    windows = get_rule_windows(result.rule_profile)

    lines = [
        "SPC SPECIAL-CAUSE TESTS (EXPLORATORY)",
        f"Rule profile: {RULE_PROFILE_LABELS[result.rule_profile]}",
        f"Plotted observations : {result.n_points}",
        "Signals are numbered at the end "
        "of each completed window.",
    ]

    for number in result.enabled_tests:
        points = result.points_for(number)

        if number == 3:
            description = (
                f"{windows[3]} consecutive points "
                "strictly increasing or decreasing"
            )
        elif number == 4:
            description = (
                f"{windows[4]} consecutive points "
                "strictly alternating up and down"
            )
        else:
            description = RULE_DESCRIPTIONS[number]

        points_text = (
            ", ".join(map(str, points))
            if points
            else "No signals"
        )

        lines.append(
            f"Test {number}: {description} | {points_text}"
        )

    lines.append(
        "SPC pattern signals describe the charted process; "
        "they are not product specification limits."
    )

    if result.rule_profile == RULE_PROFILE_MINITAB18_OBSERVED:
        lines.append(
            "Experimental 7/15 profile matched selected Minitab "
            "tests; equivalence across all datasets is unverified."
        )

    return "\n".join(lines)
