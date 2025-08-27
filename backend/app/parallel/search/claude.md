# claude.md - Parallel Search API Integration

YOU ARE implementing **SECURE** Parallel.ai Search API integration for regulatory monitoring.

## 🎯 MODULE PURPOSE
Fast regulatory source scanning with PII protection. Handles real-time searches across Belgian/EU regulatory sources with automatic fallback to RSS when Parallel unavailable.

## 🚨 SECURITY CRITICAL - NEVER VIOLATE

**YOU MUST ALWAYS:**
- Run `assert_parallel_safe()` before EVERY search call
- Check budget with cost controller before API calls
- Use Tier-A source policy for official domains only
- Record actual API costs after successful calls
- Apply circuit breaker for all external calls

**YOU MUST NEVER:**
- Send PII to Parallel.ai (regulatory queries only)
- Skip cost pre-flight checks
- Search without source domain restrictions
- Bypass circuit breaker protection
- Cache results without expiration

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def build_search_objective(
    regulation_name: str,
    country_code: str = "BE",
    languages: tuple[str, ...] = ("nl", "fr", "en")
) -> str:
    """Build regulatory search objective. MUST be deterministic."""

def extract_regulatory_changes(
    search_results: list[dict]
) -> list[RegulatoryChange]:
    """Extract regulatory changes from results. MUST be pure."""

def calculate_search_cost(processor: str) -> float:
    """Calculate expected search cost. MUST be deterministic."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def search_regulatory_sources(
    objective: str,
    processor: str = "base",
    max_results: int = 10
) -> SearchResponse:
    """Execute search with full protection."""

async def search_with_fallback(
    objective: str,
    rss_sources: list[str]
) -> SearchResponse:
    """Search with RSS fallback when circuit open."""
```

## 🔧 SEARCH API CONFIGURATION

**PROCESSORS:**
- `base` - €0.004-€0.009 per call (fast, routine monitoring)
- `pro` - €0.015-€0.025 per call (deep regulatory searches)

**SOURCE POLICY (MANDATORY):**
```python
TIER_A_DOMAINS = [
    "europa.eu",
    "eur-lex.europa.eu", 
    "nbb.be",
    "fsma.be",
    "safeonweb.be",
    "ccb.belgium.be"
]

TIER_B_DOMAINS = [
    "eba.europa.eu",
    "esma.europa.eu", 
    "ecb.europa.eu"
]
```

**SEARCH OBJECTIVES:**
```python
# Belgian DORA updates
"Latest changes to DORA regulation implementation in Belgium NBB guidance"

# NIS2 national transposition  
"Belgian NIS2 transposition law updates essential entities obligations"

# Multi-language regulatory changes
"Nouvelles obligations DORA Belgique" (FR)
"DORA verplichtingen België" (NL)
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST:**
- PII detection blocks personal data in search queries
- Source policy restricts to approved domains only
- Cost calculation matches processor rates
- Circuit breaker activates on failures
- Multi-language search objectives work

**SEARCH SCENARIOS:**
```python
# Valid regulatory searches (MUST pass)
valid_searches = [
    "DORA technical standards NBB Belgium",
    "NIS2 essential entities Belgium obligations", 
    "EU AI Act high-risk systems financial services"
]

# Invalid searches (MUST be blocked)
invalid_searches = [
    "Customer john.doe@bank.com DORA compliance",  # PII
    "Employee ID 12345 incident report",  # PII
    "Internal system passwords security"  # Sensitive
]
```

## 🎯 PERFORMANCE REQUIREMENTS

**Search Execution:** <5 seconds for base processor
**Source Filtering:** <10ms per domain check
**PII Detection:** <50ms per query
**Cost Pre-flight:** <10ms per request

## 📋 FILE STRUCTURE (MANDATORY)

```
parallel/search/
├── claude.md           # This file
├── core.py            # Pure search logic + cost calculation
├── shell.py           # API calls + circuit breaker integration
├── contracts.py       # SearchResponse, RegulatoryChange types
├── events.py          # RegulatorySearchExecuted, SearchFailed events
└── tests/
    ├── test_core.py   # Search logic, cost calculations
    └── test_shell.py  # API integration, circuit breaker tests
```

## 🔗 INTEGRATION POINTS

**DEPENDS ON:**
- `parallel/common/` - PII boundary and circuit breaker
- `cost/` - Budget checking and cost recording
- Redis - Circuit breaker state
- PostgreSQL - Search result audit trail

**EMITS EVENTS:**
- `RegulatorySearchExecuted(objective, results_count, cost, processor)`
- `SearchFailed(objective, error_type, fallback_used)`
- `SourcePolicyViolationDetected(objective, blocked_domains)`

**SUCCESS CRITERIA:**
- [ ] All PII injection attempts blocked
- [ ] Source policy limits enforced
- [ ] Cost tracking accurate
- [ ] Circuit breaker functional
- [ ] Multi-language searches work