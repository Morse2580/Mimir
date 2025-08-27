# claude.md - Regulatory Monitor Module

## Module Purpose
**Multi-language regulatory source monitoring** with intelligent fallbacks. Scans Tier-A sources (FSMA, NBB, ESMA) and Tier-B sources with RSS fallback when Parallel.ai unavailable.

## Core Contracts

```python
from typing import Protocol, NamedTuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class SourceTier(Enum):
    TIER_A = "tierA"  # Critical: FSMA, NBB, ESMA
    TIER_B = "tierB"  # Important: EBA, ECB, National
    
class Language(Enum):
    DUTCH = "nl"
    FRENCH = "fr"  
    ENGLISH = "en"

@dataclass(frozen=True)
class SourceDefinition:
    """Immutable source configuration."""
    name: str
    tier: SourceTier
    languages: tuple[Language, ...]
    primary_url: str
    rss_fallback: Optional[str]
    sitemap_fallback: Optional[str]
    scan_frequency_hours: int

@dataclass(frozen=True)
class ScanResult:
    """Individual document found during scan."""
    url: str
    title: str
    excerpt: str
    language: Language
    published_at: Optional[datetime]
    source: str
    tier: SourceTier
    fallback_mode: bool  # True if from RSS/sitemap
    relevance_score: float  # 0.0-1.0

class RegulatoryScanner(Protocol):
    """Core contract for regulatory monitoring."""
    
    def scan_source(
        self, 
        source: SourceDefinition,
        objective: str
    ) -> tuple[list[ScanResult], bool]:
        """Scan single source. Returns (results, used_fallback)."""
        ...
        
    def prioritize_results(
        self, 
        results: list[ScanResult]
    ) -> list[ScanResult]:
        """Pure function: prioritize by tier + relevance."""
        ...
```

## Functional Core (Pure Logic)

### Source Prioritization
```python
def calculate_source_priority(
    tier: SourceTier,
    language: Language,
    relevance_score: float,
    freshness_hours: float
) -> float:
    """Pure function: calculate source priority score.
    
    Formula: tier_weight * language_weight * relevance * freshness_decay
    """
    
def should_use_fallback(
    primary_failed: bool,
    circuit_open: bool,
    source_tier: SourceTier
) -> bool:
    """Pure function: decide fallback strategy."""
    
def merge_multilingual_results(
    dutch_results: list[ScanResult],
    french_results: list[ScanResult], 
    english_results: list[ScanResult]
) -> list[ScanResult]:
    """Pure function: deduplicate and merge language results."""
```

### Content Analysis
```python
def extract_key_terms(text: str, language: Language) -> tuple[str, ...]:
    """Pure function: extract regulatory key terms by language."""
    
def calculate_relevance(
    text: str,
    objective: str,
    language: Language
) -> float:
    """Pure function: relevance score 0.0-1.0."""
    
def detect_document_language(text: str) -> Language:
    """Pure function: language detection."""
```

## Imperative Shell (I/O Operations)

### Source Loading
- Load source definitions from YAML config
- Fetch RSS feeds with timeout/retry
- Parse sitemap.xml files
- HTTP client with proper headers

### Parallel.ai Integration  
- Search API calls with PII boundary checks
- Circuit breaker integration
- Cost tracking per API call
- Fallback coordination

### Result Persistence
- Store scan results with timestamps
- Maintain source scan history
- Track fallback usage statistics
- Update source health metrics

### Snapshot Coordination
- Trigger immutable snapshots for found content
- Schedule verification jobs
- Update snapshot inventory

## Source Configuration

### Tier-A Sources (Critical)
```yaml
tier_a_sources:
  fsma:
    name: "FSMA Belgium"
    languages: ["nl", "fr", "en"]
    primary_url: "https://www.fsma.be"
    rss_fallback: "https://www.fsma.be/en/rss.xml"
    scan_frequency_hours: 4
    
  nbb:
    name: "National Bank of Belgium"  
    languages: ["nl", "fr", "en"]
    primary_url: "https://www.nbb.be"
    rss_fallback: "https://www.nbb.be/en/rss"
    scan_frequency_hours: 6
    
  esma:
    name: "European Securities Markets Authority"
    languages: ["en"]
    primary_url: "https://www.esma.europa.eu"
    rss_fallback: "https://www.esma.europa.eu/rss"
    scan_frequency_hours: 8
```

### Tier-B Sources (Important)
```yaml
tier_b_sources:
  eba:
    name: "European Banking Authority"
    languages: ["en"]
    rss_fallback: "https://www.eba.europa.eu/rss"
    scan_frequency_hours: 12
    
  ecb:
    name: "European Central Bank" 
    languages: ["en"]
    rss_fallback: "https://www.ecb.europa.eu/rss"
    scan_frequency_hours: 12
```

## Language Handling Strategy

### Multi-Language Scanning
- **Dutch (NL)**: Primary for Belgian-specific content
- **French (FR)**: Secondary for Belgian content  
- **English (EN)**: EU-wide regulations and international standards

### Language Priority
1. **Objective Language**: Match query language when possible
2. **Source Native**: Use source's primary language
3. **Fallback Chain**: EN → FR → NL for coverage

### Translation Coordination  
- No automatic translation (regulatory accuracy critical)
- Flag multi-language content for manual review
- Preserve original language in audit trail

## Test Strategy

### Source Integration Testing
```python
@pytest.mark.integration
async def test_tier_a_sources():
    """Verify all Tier-A sources accessible."""
    for source in tier_a_sources:
        results = await scanner.scan_source(source, "DORA compliance")
        assert len(results) > 0
        assert not any(r.fallback_mode for r in results)
```

### Fallback Testing
```python
@pytest.mark.integration 
async def test_rss_fallback():
    """Test RSS fallback when Parallel unavailable."""
    # Mock Parallel circuit breaker open
    with mock_circuit_open():
        results = await scanner.scan_source(fsma_source, "new regulations")
        assert all(r.fallback_mode for r in results)
        assert len(results) > 0
```

### Language Testing
```python
def test_language_detection():
    nl_text = "Belgische regelgeving voor financiële instellingen"
    fr_text = "Réglementation belge pour les institutions financières"
    en_text = "Belgian regulation for financial institutions"
    
    assert detect_document_language(nl_text) == Language.DUTCH
    assert detect_document_language(fr_text) == Language.FRENCH  
    assert detect_document_language(en_text) == Language.ENGLISH
```

## Monitoring & Alerting

### Source Health Metrics
- Scan success rate per source
- Fallback usage frequency
- Average response times
- Content freshness lag

### Quality Indicators
- Results per scan (trend analysis)
- Relevance score distribution
- Language coverage completeness
- False positive rates

### Alert Conditions
- Tier-A source unavailable >1 hour
- Fallback mode activated >24 hours
- Zero results for >3 consecutive scans
- Relevance scores consistently low (<0.3)

## Module Dependencies

### READ Operations
- Source definitions from YAML config
- Circuit breaker state from common module  
- Language models/dictionaries for detection
- Historical scan results for trend analysis

### WRITE Operations
- Scan results to database
- Source health metrics to monitoring
- Snapshot requests to snapshot service
- Audit trail entries

### EMIT Events
- `SourceScanned(source, results_count, fallback_used)`
- `FallbackActivated(source, reason)`
- `SourceHealthChanged(source, status)`
- `RelevantContentFound(source, url, relevance_score)`

## Performance Characteristics

### Scanning Speed
- Target: Complete Tier-A scan <5 minutes
- Parallel requests: Max 3 concurrent per source
- Timeout: 30s per HTTP request
- Retry: 2 attempts with exponential backoff

### Memory Usage
- Streaming RSS parsing (no full DOM load)
- Result batching (max 100 results in memory)
- Language model caching
- Connection pooling for HTTP clients

This module provides **reliable, multi-language regulatory intelligence** with graceful degradation capabilities.