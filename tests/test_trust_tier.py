from services.trust_tier import (
    TIER_EA_CANDIDATE,
    TIER_EXPERIMENTAL,
    TIER_LIVE_PROVEN,
    TIER_VALIDATED,
    GateOutcomes,
    compute_trust_tier,
)


def test_experimental_when_no_gate_passed():
    g = GateOutcomes(sample=False, performance=False, stability=False, walk_forward=False)
    assert compute_trust_tier(g) == TIER_EXPERIMENTAL


def test_experimental_when_only_sample_passes():
    g = GateOutcomes(sample=True, performance=False, stability=False, walk_forward=False)
    assert compute_trust_tier(g) == TIER_EXPERIMENTAL


def test_validated_when_sample_and_performance_pass():
    g = GateOutcomes(sample=True, performance=True, stability=False, walk_forward=False)
    assert compute_trust_tier(g) == TIER_VALIDATED


def test_live_proven_when_stability_also_passes():
    g = GateOutcomes(sample=True, performance=True, stability=True, walk_forward=False)
    assert compute_trust_tier(g) == TIER_LIVE_PROVEN


def test_ea_candidate_when_all_pass():
    g = GateOutcomes(sample=True, performance=True, stability=True, walk_forward=True)
    assert compute_trust_tier(g) == TIER_EA_CANDIDATE


def test_walk_forward_alone_does_not_promote():
    g = GateOutcomes(sample=True, performance=False, stability=False, walk_forward=True)
    assert compute_trust_tier(g) == TIER_EXPERIMENTAL
