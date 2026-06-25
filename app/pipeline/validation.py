"""Validation layer (§7): schema validation + business logic checks.

Schema validation is handled by Pydantic at parse time. This module applies
the post-schema business logic rules that cannot be expressed in JSON Schema."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.verdicts import BottleneckVerdict, ReadinessVerdict


@dataclass
class ValidationResult:
    passed: bool
    overrides: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_readiness_verdict(
    verdict: ReadinessVerdict,
    *,
    gsc_connected: bool,
) -> ValidationResult:
    """Apply business logic rules to a ReadinessVerdict (§7.2).

    Returns a ValidationResult. On failure, the pipeline logs and does not retry
    the LLM — it applies overrides and writes a validation_overrides record."""
    errors: list[str] = []
    overrides: list[str] = []

    # If outcome is "ready", the indexing dimension must have passed
    if verdict.outcome.value == "ready":
        indexing_dim = verdict.dimensions.get("indexing")
        if indexing_dim and not indexing_dim.passed:
            errors.append("outcome=ready but indexing dimension did not pass")

    # If GSC not connected, confidence cannot be high
    if not gsc_connected and verdict.confidence.value == "high":
        overrides.append("confidence_floor:gsc_not_connected → medium")
        verdict.confidence = verdict.confidence.__class__("medium")

    return ValidationResult(
        passed=len(errors) == 0,
        overrides=overrides,
        errors=errors,
    )


def validate_bottleneck_verdict(verdict: BottleneckVerdict) -> ValidationResult:
    """Apply business logic rules to a BottleneckVerdict (§7.2)."""
    errors: list[str] = []
    overrides: list[str] = []

    # Constraint breakdown weights must sum to 1.0 ± 0.01
    total_weight = sum(c.weight for c in verdict.constraint_breakdown)
    if not (0.99 <= total_weight <= 1.01):
        errors.append(
            f"constraint_breakdown weights sum to {total_weight:.3f}, expected 1.0 ± 0.01"
        )

    # links_are_the_answer=False must not have primary_constraint=link_authority
    if (
        not verdict.links_are_the_answer
        and verdict.primary_constraint.value == "link_authority"
    ):
        errors.append(
            "links_are_the_answer=False but primary_constraint=link_authority — contradictory"
        )

    # Mild severity should not be paired with high confidence
    if (
        verdict.primary_severity.value == "mild"
        and verdict.confidence.value == "high"
    ):
        overrides.append("confidence_override:mild_primary_constraint → medium")
        verdict.confidence = verdict.confidence.__class__("medium")

    return ValidationResult(
        passed=len(errors) == 0,
        overrides=overrides,
        errors=errors,
    )
