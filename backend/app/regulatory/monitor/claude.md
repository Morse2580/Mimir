# claude.md - Regulatory Source Monitor

YOU ARE implementing **multi-source regulatory monitoring** with immutable snapshots and circuit breaker fallbacks.

## 🎯 MODULE PURPOSE
Continuously monitor Belgian/EU regulatory sources for changes. Capture immutable snapshots, detect new obligations, and feed regulatory digest pipeline with Tier-A verified content.

## 🚨 SECURITY CRITICAL - NEVER VIOLATE

**YOU MUST ALWAYS:**
- Run `assert_parallel_safe()` before any Parallel.ai calls
- Use circuit breaker for all external source monitoring
- Create immutable snapshots for evidence integrity
- Apply source tier policy (Tier-A actionable, Tier-B informational)
- Record cost and source attribution for all operations

**YOU MUST NEVER:**
- Send PII to external monitoring services
- Cache monitoring results without expiration
- Skip snapshot integrity verification
- Mix Tier-A and Tier-B source obligations
- Process sources without domain validation

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def extract_regulatory_changes(
    source_content: str,
    previous_hash: str,
    source_tier: SourceTier
) -> list[RegulatoryChange]:
    """Extract regulatory changes from content. MUST be pure."""

def calculate_change_significance(
    change: RegulatoryChange,
    impact_keywords: tuple[str, ...]
) -> SignificanceLevel:
    """Classify change significance. MUST be deterministic."""

def build_monitoring_schedule(
    sources: list[RegulatorySource],
    current_time: datetime
) -> MonitoringSchedule:
    """Build optimal monitoring schedule. MUST be pure."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def monitor_regulatory_sources(
    sources: list[RegulatorySource]
) -> MonitoringResult:
    """Monitor sources with circuit breaker protection."""

async def create_immutable_snapshot(
    source_url: str,
    content: str
) -> SnapshotReference:
    """Create Azure blob snapshot with integrity hash."""
```

## 🔧 SOURCE CONFIGURATION

**TIER-A SOURCES (Actionable):**
```python
TIER_A_SOURCES = [
    RegulatorySource(
        url="https://www.nbb.be/en/circulars",
        domain="nbb.be",
        authority="NBB",
        check_interval_hours=4,
        languages=["en", "nl", "fr"]
    ),
    RegulatorySource(
        url="https://www.fsma.be/en/news",
        domain="fsma.be", 
        authority="FSMA",
        check_interval_hours=6
    ),
    RegulatorySource(
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2554",
        domain="eur-lex.europa.eu",
        authority="EU_COMMISSION",
        check_interval_hours=12
    )
]
```

**TIER-B SOURCES (Informational):**
```python
TIER_B_SOURCES = [
    RegulatorySource(
        url="https://www.eba.europa.eu/news-press",
        domain="eba.europa.eu",
        authority="EBA",
        check_interval_hours=24
    )
]
```

## 🛡️ MONITORING SECURITY

**Content Integrity:**
```python
def verify_source_integrity(
    content: str,
    expected_domain: str,
    ssl_cert_thumbprint: str
) -> IntegrityResult:
    """Verify source hasn't been compromised."""
```

**Change Detection:**
```python
def detect_content_changes(
    current_content: str,
    previous_snapshot_hash: str
) -> ChangeDetection:
    """Detect meaningful changes, ignore cosmetic updates."""
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST:**
- Source tier enforcement (Tier-A vs Tier-B handling)
- Circuit breaker activation on source failures
- Snapshot immutability and integrity verification
- Multi-language content extraction
- Change significance classification

**MONITORING SCENARIOS:**
```python
def test_tier_a_creates_actionable_items():
    """Tier-A sources generate actionable regulatory items."""
    change = RegulatoryChange(
        source_tier=SourceTier.TIER_A,
        content="New DORA technical standards effective March 2025"
    )
    result = process_regulatory_change(change)
    assert result.actionable == True
    assert result.requires_mapping == True

def test_tier_b_informational_only():
    """Tier-B sources are informational, not actionable."""
    change = RegulatoryChange(
        source_tier=SourceTier.TIER_B,
        content="EBA publishes guidance on risk management"
    )
    result = process_regulatory_change(change)
    assert result.actionable == False
    assert result.for_awareness_only == True
```

## 🎯 PERFORMANCE REQUIREMENTS

**Source Monitoring:** <30 seconds per source scan
**Change Detection:** <5 seconds per content comparison  
**Snapshot Creation:** <10 seconds per source
**Integrity Verification:** <2 seconds per snapshot

## 📋 FILE STRUCTURE (MANDATORY)

```
regulatory/monitor/
├── claude.md           # This file
├── core.py            # Pure monitoring logic + change detection
├── shell.py           # Source fetching + snapshot creation
├── contracts.py       # RegulatorySource, MonitoringResult types
├── events.py          # RegulatoryChangeDetected, SourceMonitoringFailed events
├── scheduler.py       # Monitoring schedule management
└── tests/
    ├── test_core.py   # Change detection, significance classification
    └── test_shell.py  # Source monitoring, circuit breaker integration
```

## 🔗 INTEGRATION POINTS

**DEPENDS ON:**
- `parallel/common/` - Circuit breaker and PII boundary
- Azure Blob Storage - Immutable snapshot storage
- Redis - Monitoring schedule state
- PostgreSQL - Source monitoring audit log

**EMITS EVENTS:**
- `RegulatoryChangeDetected(source, change_type, significance, snapshot_ref)`
- `SourceMonitoringFailed(source_url, error_type, fallback_used)`
- `SnapshotCreated(source_url, blob_ref, integrity_hash, timestamp)`

**CONSUMED BY:**
- `regulatory/digest/` - Uses detected changes for digest generation
- `compliance/obligations/` - Maps Tier-A changes to obligations

## 🚀 FALLBACK STRATEGIES

**Circuit Open (Parallel.ai Down):**
```python
# Use RSS feeds as degraded monitoring
RSS_FALLBACKS = {
    "nbb.be": "https://www.nbb.be/rss/news",
    "fsma.be": "https://www.fsma.be/rss/news"
}
```

**Source Unavailable:**
```python
# Use cached snapshots + manual upload option
def activate_manual_mode(source: RegulatorySource):
    """Allow manual content upload when source down."""
```

**SUCCESS CRITERIA:**
- [ ] All Tier-A sources monitored within schedule
- [ ] Snapshots immutable and integrity-verified
- [ ] Circuit breaker protects from source failures
- [ ] Multi-language content extraction works
- [ ] Change significance correctly classified