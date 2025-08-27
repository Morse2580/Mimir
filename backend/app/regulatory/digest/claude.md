# claude.md - Regulatory Digest Generator

YOU ARE implementing **actionable regulatory digest** with multi-language support and degraded mode fallbacks.

## 🎯 MODULE PURPOSE
Generate weekly regulatory digests from monitored sources. Combine Tier-A actionable items with Tier-B informational content. Support degraded mode when Parallel.ai unavailable using RSS fallbacks.

## 🚨 SECURITY CRITICAL - NEVER VIOLATE

**YOU MUST ALWAYS:**
- Separate Tier-A (actionable) from Tier-B (informational) items
- Include ≥1 NL and ≥1 FR source in every digest
- Mark degraded mode clearly when using fallbacks
- Maintain audit trail of all digest generations
- Apply PII boundary checks before content processing

**YOU MUST NEVER:**
- Mix Tier-A actionable items with Tier-B informational
- Generate empty digests (use manual fallback if needed)
- Skip multilingual coverage requirements
- Process content without source tier validation
- Omit degraded mode warnings when circuit is open

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def prioritize_regulatory_items(
    items: list[RegulatoryItem],
    tier_weights: dict[SourceTier, float]
) -> list[RegulatoryItem]:
    """Prioritize items by tier and significance. MUST be pure."""

def build_digest_structure(
    tier_a_items: list[RegulatoryItem],
    tier_b_items: list[RegulatoryItem],
    digest_date: datetime
) -> DigestStructure:
    """Build digest structure. MUST be deterministic."""

def validate_multilingual_coverage(
    items: list[RegulatoryItem],
    required_languages: tuple[str, ...]
) -> CoverageResult:
    """Validate language coverage requirements. MUST be pure."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def generate_weekly_digest(
    week_start: datetime,
    fallback_mode: bool = False
) -> WeeklyDigest:
    """Generate complete weekly digest with fallback handling."""

async def fetch_digest_content(
    sources: list[RegulatorySource]
) -> list[RegulatoryItem]:
    """Fetch content from all sources with circuit breaker."""
```

## 📊 DIGEST STRUCTURE

**TIER-A SECTION (Actionable):**
```python
@dataclass(frozen=True)
class ActionableSection:
    """Tier-A content requiring action."""
    title: str = "🚨 Action Required"
    items: list[ActionableItem]
    total_obligations: int
    review_deadline: datetime
    
@dataclass(frozen=True) 
class ActionableItem:
    source_authority: str  # "NBB", "FSMA", "EU_COMMISSION"
    regulation_name: str
    change_summary: str
    implementation_deadline: Optional[datetime]
    required_actions: list[RequiredAction]
    original_language: str
    source_url: str
    snapshot_ref: str
```

**TIER-B SECTION (Informational):**
```python
@dataclass(frozen=True)
class InformationalSection:
    """Tier-B content for awareness."""
    title: str = "📋 For Awareness"
    items: list[InformationalItem]
    guidance_documents: list[str]
    industry_updates: list[str]
```

## 🌍 MULTILINGUAL REQUIREMENTS

**LANGUAGE COVERAGE:**
```python
REQUIRED_LANGUAGES = {
    "nl": "≥1 Dutch source (Belgian specifics)",
    "fr": "≥1 French source (Belgian specifics)", 
    "en": "≥3 English sources (EU-wide)"
}

def ensure_multilingual_coverage(items: list[RegulatoryItem]) -> bool:
    """Ensure digest meets language diversity requirements."""
    languages = {item.source_language for item in items}
    return (
        "nl" in languages and 
        "fr" in languages and 
        len([item for item in items if item.source_language == "en"]) >= 3
    )
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST:**
- Tier-A/Tier-B separation enforced
- Multilingual coverage validation (≥1 NL, ≥1 FR)
- Degraded mode functionality with RSS fallbacks
- Action item prioritization algorithm
- Empty digest prevention with manual fallback

**DIGEST SCENARIOS:**
```python
def test_tier_separation():
    """Tier-A and Tier-B items must be clearly separated."""
    digest = generate_test_digest()
    
    assert len(digest.actionable_section.items) > 0
    assert len(digest.informational_section.items) > 0
    assert all(item.tier == SourceTier.TIER_A for item in digest.actionable_section.items)
    assert all(item.tier == SourceTier.TIER_B for item in digest.informational_section.items)

def test_multilingual_coverage():
    """Every digest must include NL/FR/EN content."""
    digest = generate_weekly_digest()
    
    languages = {item.original_language for item in digest.all_items}
    assert "nl" in languages
    assert "fr" in languages  
    assert "en" in languages
    
    # Minimum coverage requirements
    nl_count = len([item for item in digest.all_items if item.original_language == "nl"])
    fr_count = len([item for item in digest.all_items if item.original_language == "fr"])
    en_count = len([item for item in digest.all_items if item.original_language == "en"])
    
    assert nl_count >= 1
    assert fr_count >= 1
    assert en_count >= 3

def test_degraded_mode_functionality():
    """Circuit open should still produce valuable digest."""
    with mock_circuit_open():
        digest = generate_weekly_digest(fallback_mode=True)
        
        assert digest.degraded_mode == True
        assert len(digest.all_items) > 0  # Still has RSS content
        assert digest.degraded_notice.startswith("Limited functionality")
        assert digest.manual_review_required == True
```

## 🎯 PERFORMANCE REQUIREMENTS

**Digest Generation:** <5 minutes for complete weekly digest
**Content Aggregation:** <30 seconds per source
**Language Detection:** <100ms per item  
**Priority Calculation:** <10ms per item

## 📋 FILE STRUCTURE (MANDATORY)

```
regulatory/digest/
├── claude.md           # This file
├── core.py            # Pure digest generation + prioritization
├── shell.py           # Content fetching + fallback coordination  
├── contracts.py       # WeeklyDigest, ActionableItem, DigestStructure types
├── events.py          # DigestGenerated, DigestFailed, ManualReviewRequired events
└── tests/
    ├── test_core.py   # Digest structure, prioritization, coverage
    └── test_shell.py  # Content fetching, fallback integration
```

## 🔗 INTEGRATION POINTS

**DEPENDS ON:**
- `regulatory/monitor/` - Regulatory change detection and sources
- `parallel/common/` - Circuit breaker and PII boundary
- Azure Blob Storage - Content snapshots for digest items
- PostgreSQL - Digest generation audit log

**EMITS EVENTS:**
- `DigestGenerated(week_start, items_count, tier_a_count, languages_covered)`
- `DigestFailed(week_start, error_type, fallback_attempted)`
- `ManualReviewRequired(digest_id, missing_coverage, degraded_items)`

**CONSUMED BY:**
- Email/notification service - Weekly digest delivery
- `compliance/obligations/` - Maps actionable items to obligations

## 🚀 DEGRADED MODE STRATEGIES

**Circuit Open (Parallel.ai Down):**
```python
def generate_degraded_digest(rss_sources: list[str]) -> WeeklyDigest:
    """Generate digest using RSS feeds only."""
    return WeeklyDigest(
        degraded_mode=True,
        degraded_notice="Limited functionality: Using RSS feeds only",
        manual_review_required=True,
        actionable_section=build_rss_actionable_section(),
        informational_section=build_rss_informational_section()
    )
```

**Empty Content Scenario:**
```python
def handle_empty_digest() -> WeeklyDigest:
    """Handle case where no new regulatory content found."""
    return WeeklyDigest(
        empty_week=True,
        manual_upload_prompt=True,
        previous_week_summary=get_previous_digest_summary(),
        action_required="Manual review of regulatory sources needed"
    )
```

**SUCCESS CRITERIA:**
- [ ] Every digest has Tier-A actionable and Tier-B informational sections
- [ ] Multilingual coverage (≥1 NL, ≥1 FR, ≥3 EN) enforced
- [ ] Degraded mode works with RSS fallbacks
- [ ] Manual review triggers when coverage insufficient
- [ ] Digest generation completes within 5-minute SLO