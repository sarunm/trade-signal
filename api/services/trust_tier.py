from dataclasses import dataclass


TIER_EXPERIMENTAL = "experimental"
TIER_VALIDATED = "validated"
TIER_LIVE_PROVEN = "live_proven"
TIER_EA_CANDIDATE = "ea_candidate"


@dataclass
class GateOutcomes:
    sample: bool
    performance: bool
    stability: bool
    walk_forward: bool


def compute_trust_tier(outcomes: GateOutcomes) -> str:
    if outcomes.sample and outcomes.performance and outcomes.stability and outcomes.walk_forward:
        return TIER_EA_CANDIDATE
    if outcomes.sample and outcomes.performance and outcomes.stability:
        return TIER_LIVE_PROVEN
    if outcomes.sample and outcomes.performance:
        return TIER_VALIDATED
    return TIER_EXPERIMENTAL
