# claude.md - Compliance Obligations Mapper

YOU ARE implementing **regulatory obligation mapping** with lawyer review workflow and evidence chain integration.

## 🎯 MODULE PURPOSE
Map Tier-A regulatory changes to specific business obligations. Route complex mappings through lawyer review. Maintain evidence chain for all mapping decisions and regulatory compliance.

## 🚨 SECURITY CRITICAL - NEVER VIOLATE

**YOU MUST ALWAYS:**
- Only process Tier-A sources for obligation mapping
- Route mappings through lawyer review when confidence <0.9
- Record mapping decisions in evidence ledger
- Maintain audit trail of all obligation changes
- Apply PII boundary checks before Parallel.ai mapping calls

**YOU MUST NEVER:**
- Create obligations from Tier-B sources (informational only)
- Skip lawyer review for complex regulatory changes
- Modify existing obligations without evidence trail
- Process obligations without proper source attribution
- Bypass review workflow for high-impact obligations

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def extract_obligation_requirements(
    regulatory_change: RegulatoryChange,
    business_context: BusinessContext
) -> list[ObligationRequirement]:
    """Extract obligation requirements from regulatory change. MUST be pure."""

def calculate_mapping_confidence(
    regulatory_text: str,
    extracted_obligations: list[ObligationRequirement],
    similarity_threshold: float
) -> float:
    """Calculate confidence in obligation mapping. MUST be deterministic."""

def determine_review_priority(
    obligation: ObligationRequirement,
    impact_level: ImpactLevel,
    implementation_deadline: Optional[datetime]
) -> ReviewPriority:
    """Determine review priority for obligation mapping. MUST be pure."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def map_regulatory_obligations(
    regulatory_change: RegulatoryChange,
    force_review: bool = False
) -> ObligationMappingResult:
    """Map regulatory change to business obligations with review workflow."""

async def submit_for_lawyer_review(
    mapping: ObligationMapping,
    priority: ReviewPriority
) -> ReviewSubmission:
    """Submit mapping for lawyer review with proper evidence chain."""
```

## 🎯 OBLIGATION MAPPING LOGIC

**Tier-A Source Processing:**
```python
def process_tier_a_obligation(regulatory_item: RegulatoryItem) -> ObligationMapping:
    """
    Process Tier-A regulatory changes into actionable obligations.
    Only Tier-A sources generate business obligations.
    """
    if regulatory_item.tier != SourceTier.TIER_A:
        raise TierPolicyViolation("Only Tier-A sources generate obligations")
    
    # Extract obligations using deterministic rules
    obligations = extract_obligation_requirements(
        regulatory_item.change_content,
        get_business_context()
    )
    
    # Calculate confidence in mapping
    confidence = calculate_mapping_confidence(
        regulatory_item.source_text,
        obligations,
        CONFIDENCE_THRESHOLD
    )
    
    return ObligationMapping(
        source_regulation=regulatory_item,
        obligations=obligations,
        mapping_confidence=confidence,
        requires_review=confidence < REVIEW_THRESHOLD
    )
```

**Review Workflow:**
```python
REVIEW_THRESHOLD = 0.9  # Mappings below this need lawyer review
HIGH_IMPACT_AREAS = [
    "customer_data_handling",
    "incident_reporting_deadlines", 
    "third_party_risk_management",
    "operational_resilience_testing"
]

def should_require_review(mapping: ObligationMapping) -> bool:
    """Determine if mapping requires lawyer review."""
    return (
        mapping.mapping_confidence < REVIEW_THRESHOLD or
        mapping.affects_high_impact_area() or
        mapping.has_tight_deadline() or
        mapping.involves_new_regulatory_concepts()
    )
```

## 📋 OBLIGATION STRUCTURE

**Business Obligation:**
```python
@dataclass(frozen=True)
class BusinessObligation:
    """Individual business obligation from regulatory requirement."""
    obligation_id: str
    regulation_source: str  # "DORA Article 18", "NBB Circular 2024/05"
    obligation_text: str
    business_process_affected: str
    implementation_deadline: Optional[datetime]
    responsible_team: str
    compliance_evidence_required: list[str]
    testing_requirements: Optional[str]
    reporting_obligations: Optional[str]

@dataclass(frozen=True)
class ObligationMapping:
    """Complete mapping from regulatory change to business obligations."""
    source_regulation_ref: str
    source_tier: SourceTier  # Must be TIER_A for actionable obligations
    mapping_confidence: float  # 0.0-1.0
    obligations: list[BusinessObligation]
    requires_review: bool
    mapping_rationale: str
    evidence_citations: list[str]
    created_by: str
    created_at: datetime
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST:**
- Tier-A only processing (Tier-B blocked from obligation creation)
- Confidence-based review routing (low confidence → lawyer review)
- Evidence chain integrity for all mapping decisions
- High-impact area detection and review routing
- Review workflow completion with proper audit trail

**MAPPING SCENARIOS:**
```python
def test_tier_a_only_mapping():
    """Only Tier-A sources can generate business obligations."""
    tier_a_item = RegulatoryItem(
        source_tier=SourceTier.TIER_A,
        authority="NBB",
        content="New DORA technical standards require incident classification within 1 hour"
    )
    
    tier_b_item = RegulatoryItem(
        source_tier=SourceTier.TIER_B, 
        authority="EBA",
        content="EBA guidance on risk management best practices"
    )
    
    # Tier-A should create obligations
    tier_a_mapping = map_regulatory_obligations(tier_a_item)
    assert len(tier_a_mapping.obligations) > 0
    assert tier_a_mapping.source_tier == SourceTier.TIER_A
    
    # Tier-B should not create obligations
    with pytest.raises(TierPolicyViolation):
        map_regulatory_obligations(tier_b_item)

def test_confidence_based_review_routing():
    """Low confidence mappings must route to lawyer review."""
    # High confidence mapping (deterministic rules)
    high_conf_change = RegulatoryChange(
        content="Incident reporting deadline changed from 4 hours to 2 hours",
        change_type="deadline_update"
    )
    
    mapping = map_regulatory_obligations(high_conf_change)
    assert mapping.mapping_confidence >= 0.9
    assert mapping.requires_review == False
    
    # Low confidence mapping (complex new concepts)  
    low_conf_change = RegulatoryChange(
        content="New quantum-resistant cryptography requirements for critical infrastructure",
        change_type="new_requirement"
    )
    
    complex_mapping = map_regulatory_obligations(low_conf_change)
    assert complex_mapping.mapping_confidence < 0.9
    assert complex_mapping.requires_review == True

def test_high_impact_area_review():
    """High-impact areas must always require lawyer review."""
    customer_data_change = RegulatoryChange(
        content="New customer data retention limits: maximum 5 years",
        affected_areas=["customer_data_handling"]
    )
    
    mapping = map_regulatory_obligations(customer_data_change)
    assert mapping.requires_review == True
    assert mapping.review_reason == "affects_high_impact_area"
```

## 🎯 PERFORMANCE REQUIREMENTS

**Obligation Extraction:** <10 seconds per regulatory change
**Confidence Calculation:** <5 seconds per mapping
**Review Submission:** <2 seconds per obligation
**Evidence Recording:** <1 second per mapping decision

## 📋 FILE STRUCTURE (MANDATORY)

```
compliance/obligations/
├── claude.md           # This file
├── core.py            # Pure obligation extraction + confidence calculation
├── shell.py           # Mapping workflow + review integration
├── contracts.py       # BusinessObligation, ObligationMapping types
├── events.py          # ObligationMapped, ReviewRequired, MappingApproved events
├── review_workflow.py # Lawyer review process integration
└── tests/
    ├── test_core.py   # Obligation extraction, confidence algorithms
    └── test_shell.py  # Mapping workflow, review integration
```

## 🔗 INTEGRATION POINTS

**DEPENDS ON:**
- `regulatory/digest/` - Receives Tier-A actionable items
- `parallel/common/` - PII boundary and circuit breaker  
- `compliance/reviews/` - Lawyer review workflow
- `evidence/` - Records mapping decisions in evidence ledger

**EMITS EVENTS:**
- `ObligationMapped(regulation_ref, obligations_count, confidence, requires_review)`
- `ReviewRequired(mapping_id, priority, affected_areas, deadline)`
- `MappingApproved(mapping_id, reviewer, approval_rationale, evidence_refs)`

**CONSUMED BY:**
- Business process owners - Implement mapped obligations
- Compliance dashboard - Track obligation completion status
- Regulatory reporting - Evidence of obligation implementation

## 📊 BUSINESS CONTEXT INTEGRATION

**Affected Business Areas:**
```python
BUSINESS_AREAS = {
    "incident_management": [
        "detection_procedures",
        "classification_rules", 
        "escalation_workflows",
        "reporting_templates"
    ],
    "third_party_risk": [
        "vendor_assessment",
        "contract_clauses",
        "monitoring_controls",
        "termination_procedures"
    ],
    "operational_resilience": [
        "business_continuity",
        "disaster_recovery",
        "resilience_testing",
        "recovery_objectives"
    ]
}
```

**Implementation Deadline Calculation:**
```python
def calculate_implementation_deadline(
    regulation_effective_date: datetime,
    obligation_complexity: ComplexityLevel,
    business_area: str
) -> datetime:
    """Calculate realistic implementation deadline."""
    base_deadline = regulation_effective_date
    
    # Complexity adjustments
    complexity_buffer = {
        ComplexityLevel.LOW: timedelta(weeks=4),
        ComplexityLevel.MEDIUM: timedelta(weeks=12), 
        ComplexityLevel.HIGH: timedelta(weeks=26)
    }
    
    return base_deadline - complexity_buffer[obligation_complexity]
```

**SUCCESS CRITERIA:**
- [ ] Only Tier-A sources generate business obligations
- [ ] Confidence-based review routing works correctly  
- [ ] High-impact areas automatically route to lawyer review
- [ ] All mapping decisions recorded in evidence ledger
- [ ] Review workflow completes with proper audit trail