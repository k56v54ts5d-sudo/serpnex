"""Tests for the business logic validation layer (§7.2)."""

import pytest

from app.pipeline.validation import validate_bottleneck_verdict, validate_readiness_verdict
from app.schemas.verdicts import (
    BottleneckCategory,
    BottleneckVerdict,
    Confidence,
    ConstraintBreakdown,
    ConstraintSeverity,
    Priority,
    ReadinessDimension,
    ReadinessOutcome,
    ReadinessVerdict,
)


def _make_readiness_verdict(**overrides) -> ReadinessVerdict:
    defaults = dict(
        outcome=ReadinessOutcome.READY,
        confidence=Confidence.MEDIUM,
        confidence_rationale="Test rationale",
        headline="Test headline",
        dimensions={
            "content_sufficiency": ReadinessDimension(passed=True, severity="low", reason="ok"),
            "indexing": ReadinessDimension(passed=True, severity="low", reason="ok"),
        },
        actions=[],
        data_quality={"page_crawled": True},
    )
    defaults.update(overrides)
    return ReadinessVerdict(**defaults)


def _make_bottleneck_verdict(**overrides) -> BottleneckVerdict:
    defaults = dict(
        primary_constraint=BottleneckCategory.LINK_AUTHORITY,
        primary_severity=ConstraintSeverity.SIGNIFICANT,
        links_are_the_answer=True,
        headline="Link authority is the bottleneck.",
        competitive_context="Target has 5 RDs vs top competitor with 80 RDs.",
        constraint_breakdown=[
            ConstraintBreakdown(
                category=BottleneckCategory.LINK_AUTHORITY,
                severity=ConstraintSeverity.SIGNIFICANT,
                weight=0.8,
                reason="Large referring domain gap.",
            ),
            ConstraintBreakdown(
                category=BottleneckCategory.CONTENT_DEPTH,
                severity=ConstraintSeverity.MILD,
                weight=0.2,
                reason="Minor content gap.",
            ),
        ],
        recommended_action="Build 10 high-authority links.",
        recommended_action_priority=Priority.HIGH,
        confidence=Confidence.MEDIUM,
        confidence_rationale="GSC data available, backlinks available.",
        data_quality={"gsc_data": True},
    )
    defaults.update(overrides)
    return BottleneckVerdict(**defaults)


class TestValidateReadinessVerdict:
    def test_valid_verdict_passes(self):
        v = _make_readiness_verdict()
        result = validate_readiness_verdict(v, gsc_connected=True)
        assert result.passed
        assert result.errors == []

    def test_ready_with_failed_indexing_dimension_is_error(self):
        v = _make_readiness_verdict(
            outcome=ReadinessOutcome.READY,
            dimensions={
                "indexing": ReadinessDimension(passed=False, severity="high", reason="blocked"),
            },
        )
        result = validate_readiness_verdict(v, gsc_connected=True)
        assert not result.passed
        assert any("indexing" in e for e in result.errors)

    def test_gsc_not_connected_floors_high_confidence_to_medium(self):
        v = _make_readiness_verdict(confidence=Confidence.HIGH)
        result = validate_readiness_verdict(v, gsc_connected=False)
        assert v.confidence == Confidence.MEDIUM
        assert any("gsc_not_connected" in o for o in result.overrides)

    def test_gsc_not_connected_leaves_medium_unchanged(self):
        v = _make_readiness_verdict(confidence=Confidence.MEDIUM)
        result = validate_readiness_verdict(v, gsc_connected=False)
        assert v.confidence == Confidence.MEDIUM
        assert result.overrides == []


class TestValidateBottleneckVerdict:
    def test_valid_verdict_passes(self):
        v = _make_bottleneck_verdict()
        result = validate_bottleneck_verdict(v)
        assert result.passed
        assert result.errors == []

    def test_weights_sum_not_1_is_error(self):
        v = _make_bottleneck_verdict(
            constraint_breakdown=[
                ConstraintBreakdown(
                    category=BottleneckCategory.LINK_AUTHORITY,
                    severity=ConstraintSeverity.SIGNIFICANT,
                    weight=0.5,
                    reason="reason",
                ),
            ]
        )
        result = validate_bottleneck_verdict(v)
        assert not result.passed
        assert any("weights sum" in e for e in result.errors)

    def test_links_not_answer_with_link_authority_constraint_is_error(self):
        v = _make_bottleneck_verdict(
            links_are_the_answer=False,
            primary_constraint=BottleneckCategory.LINK_AUTHORITY,
        )
        result = validate_bottleneck_verdict(v)
        assert not result.passed
        assert any("links_are_the_answer" in e for e in result.errors)

    def test_mild_primary_with_high_confidence_overrides_to_medium(self):
        v = _make_bottleneck_verdict(
            primary_severity=ConstraintSeverity.MILD,
            confidence=Confidence.HIGH,
            links_are_the_answer=False,
            primary_constraint=BottleneckCategory.CONTENT_DEPTH,
        )
        result = validate_bottleneck_verdict(v)
        assert v.confidence == Confidence.MEDIUM
        assert any("mild_primary_constraint" in o for o in result.overrides)
