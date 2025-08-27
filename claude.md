# claude.md

## Project Overview

This Python project is a **Belgian RegOps Platform: Production-Hardened Pilot Implementation** designed to provide audit-grade Belgian compliance with circuit breakers, immutable snapshots, and real NBB XSD validation. Zero PII to Parallel.ai, full review audit trails, €1,500/month spend cap.

**Mission:** Enable Belgian financial institutions to maintain DORA compliance through automated regulatory monitoring, incident classification, and OneGate reporting with bulletproof audit trails.

## Core Principles

- **Security-First**: All external API calls must pass PII boundary checks
- **Audit-Grade**: Every action creates immutable audit records
- **Production-Hardened**: Circuit breakers, fallbacks, and failure mode handling
- **Cost-Controlled**: Hard €1,500/month cap with kill switch at 95%
- **Regulatory-Compliant**: NBB XSD validation, DORA mappings, DST-aware clocks

## Tech Stack

**Backend:**
- **Python 3.11+** with asyncio for concurrent operations
- **FastAPI** for REST APIs with automatic validation
- **SQLAlchemy** with **PostgreSQL** for audit-trail persistence
- **Redis** for webhook replay protection and caching
- **Azure Blob Storage** with immutability policies for snapshots
- **Azure Key Vault** for evidence chain signing
- **lxml** for NBB XSD validation

**External APIs:**
- **Parallel.ai** (Search/Task APIs) with PII boundaries
- **RSS feeds** as fallback when Parallel unavailable

**Testing:**
- **pytest** with parameterized tests for 32 clock scenarios
- **pytest-asyncio** for async test support
- Acceptance tests with official NBB test vectors

## Folder Structure

```
/
├── claude.md                           # This foundation file
├── backend/
│   ├── app/
│   │   ├── parallel/                   # Parallel.ai integration
│   │   │   ├── common/
│   │   │   │   ├── guard.py          # PII boundary enforcement  
│   │   │   │   ├── breaker.py        # Circuit breaker pattern
│   │   │   │   └── fallback.py       # RSS/sitemap fallback
│   │   │   ├── search/               # Search API wrapper
│   │   │   ├── task/                 # Task API wrapper
│   │   │   │   └── schema_gate.py    # ≤8 fields enforcer
│   │   │   └── webhooks/             # Webhook security
│   │   │       ├── security.py       # mTLS + HMAC + replay
│   │   │       └── replay_cache.py   # Redis nonce tracker
│   │   ├── regulatory/               # Regulatory monitoring
│   │   │   ├── monitor/
│   │   │   │   ├── sources.yaml      # Tier A/B + RSS fallback
│   │   │   │   └── language_matrix.py # NL/FR/EN handlers
│   │   │   ├── digest/
│   │   │   │   └── actionable.py     # Required actions engine
│   │   │   └── snapshot/             # Source preservation
│   │   │       ├── snapshot.py       # Azure immutable blobs
│   │   │       └── verifier.py       # Weekly drift detection
│   │   ├── compliance/               # DORA compliance
│   │   │   ├── obligations/          # Obligation mappings
│   │   │   └── reviews/              # Review workflow
│   │   │       ├── workflow.py       # Review state machine
│   │   │       └── audit_export.py   # review_log.json
│   │   ├── incidents/                # Incident management
│   │   │   ├── rules/
│   │   │   │   └── rules.yaml        # Clock anchors + fallbacks
│   │   │   └── clocks/
│   │   │       └── matrix_handler.py # UTC/CET/CEST × DST
│   │   ├── evidence/                 # Evidence chain
│   │   │   └── verify_ledger.py      # Chain verification
│   │   └── cost/                     # Cost management
│   │       ├── guardrails.py         # €1,500 cap enforcer
│   │       └── report_generator.py   # Weekly spend breakdown
├── infrastructure/
│   ├── onegate/                      # NBB OneGate integration
│   │   ├── schemas/
│   │   │   ├── dora_v2.xsd          # Official NBB schema
│   │   │   ├── dora_v2.xsd.sha256   # Checksum verification
│   │   │   ├── samples/             # Official test vectors
│   │   │   └── README.md            # Provenance documentation
│   │   └── profiles.yaml            # Export configuration
├── tests/
│   ├── acceptance/                   # Business acceptance tests
│   │   ├── test_onegate_vectors.py  # NBB official samples
│   │   ├── test_clock_matrix.py     # 32 DST scenarios
│   │   └── test_pii_injection.py    # 5 attack vectors
│   └── integration/                  # System integration tests
│       ├── test_circuit_breaker.py  # Parallel down scenario
│       └── test_fallback_rss.py     # Degraded mode validation
└── deliverables/                     # Audit deliverables
    ├── DPIA_one_pager.md            # Data protection proof
    ├── cost_report.md               # Weekly spend tracking
    └── pilot_acceptance.md          # Sign-off checklist
```

## Coding Guidelines

**Security & Data Protection:**
- NEVER send PII to external APIs - all data must pass `assert_parallel_safe()` 
- All external requests require pre-flight cost checks
- Webhook validation: mTLS + HMAC + replay protection
- Immutable audit records - no updates, only appends

**Async & Performance:**
- Use `async/await` for all I/O operations
- Prefer `httpx.AsyncClient` over requests
- Implement circuit breakers for external dependencies
- Graceful degradation with RSS fallbacks

**Testing Requirements:**
- All XSD validation must use official NBB test vectors
- Clock handling must pass all 32 DST/timezone scenarios  
- PII injection tests must block 5 attack vectors
- Cost tracking must enforce €1,500 monthly cap

**Error Handling:**
- Circuit breakers open after 3 consecutive failures
- All failures create audit records with timestamps
- Fallback to RSS when Parallel.ai unavailable
- Kill switch triggers at 95% of monthly spend cap

## Development Workflow

**Task Loop Structure (ALWAYS follow this pattern):**
1. **PLAN**: Analyze task, break into <150 LOC commits, identify risks
2. **IMPLEMENT**: Write code following security/audit guidelines  
3. **TEST**: Run relevant test suites, verify acceptance criteria
4. **VERIFY**: Check audit trails, cost tracking, evidence integrity
5. **REPORT**: Summarize changes, test outcomes, next steps

**Development Rules:**
- Split large changes into <150 LOC per commit
- Never run destructive operations without `--dry-run` first
- Always summarize diffs + test results after each change
- Prefer small, pure functions over deep class hierarchies
- Max 200 lines per file before splitting into modules

## Allowed Tools & Commands

**✅ APPROVED TOOLS:**
- `pytest`, `pytest-asyncio` - Testing framework
- `black`, `ruff` - Code formatting and linting
- `uvicorn` - Development server
- `git`, `gh` - Version control and GitHub operations
- `pip`, `poetry` - Dependency management
- `sqlalchemy`, `alembic` - Database operations (read-only queries)
- `httpx`, `asyncio` - HTTP client and async operations
- `lxml` - XSD validation
- `sha256sum` - Checksum verification

**❌ RESTRICTED OPERATIONS (require confirmation):**
- `rm -rf`, `sudo rm` - File deletion commands
- Database schema migrations (`alembic upgrade`)
- Production deployment commands
- Cost guardrail modifications (`backend/app/cost/guardrails.py`)
- Evidence ledger updates (`backend/app/evidence/verify_ledger.py`)
- XSD schema modifications

**⚠️ REQUIRES HUMAN APPROVAL:**
- Changes to security boundaries (`assert_parallel_safe()`)
- Circuit breaker threshold modifications
- Budget cap or kill switch logic changes
- Audit trail schema changes

## Review Triggers

**Automatic Human Review Required:**
- **Obligation Mappings** → Lawyer approval via review workflow
- **Schema Changes** → Senior engineer review
- **Security Controls** → Mandatory security team sign-off
- **Cost Guardrails** → Finance + engineering approval
- **Evidence Chain** → Audit team verification

**Code Review Guidelines:**
- All security-related changes require 2 approvals
- PII boundary changes require security team review
- Cost tracking logic requires finance team review
- XSD validation changes require compliance review

## Success Metrics & Quality Gates

**Per Iteration Targets:**
- 90%+ of existing tests remain passing
- No new PII boundary violations logged
- Cost tracking accuracy within 0.001 EUR
- All acceptance criteria met before merge

**Quality Gates:**
- All 32 DST scenarios pass
- Official NBB test vectors validate
- 5 PII injection attack vectors blocked  
- Circuit breaker recovery functional
- Evidence chain integrity verified

**Performance Requirements:**
- API response times <200ms (95th percentile)
- XSD validation <5 seconds
- Cost check <10ms
- Audit record creation <50ms

## Development Practices

**Commit Rules:**
- Prefix: `feat:`, `fix:`, `security:`, `audit:`, `test:`
- All commits must maintain audit trail integrity
- Security changes require mandatory review
- Include test results in commit message when significant

**Code Style:**
- Use `async/await` for all I/O operations
- Prefer composition over inheritance
- Pure functions for business logic (no side effects)
- Explicit error handling with Result types
- Immutable data structures where possible

**Review Process:**
- Lawyer review required for obligation mappings
- All reviews create immutable audit entries
- Review state machine prevents stale approvals
- Security changes require dual approval

**Production Deployment:**
- XSD checksum verification before deployment
- Evidence ledger integrity check required
- All 32 clock scenarios must pass
- Cost tracking operational before API calls

## Critical Failure Modes

**Data Boundary Violations:**
- PII sent to Parallel.ai → Immediate alert + kill switch
- Audit chain broken → Incident response required
- XSD tampering detected → Emergency rollback

**System Dependencies:**
- Parallel.ai down → Automatic RSS fallback
- Azure unavailable → Local backup mode
- PostgreSQL down → Redis emergency logging

**Cost Overruns:**
- 80% budget → Warning alerts
- 95% budget → Automatic kill switch activation
- Manual override requires C-level approval

## Environment Variables

```bash
# Parallel.ai Integration
PARALLEL_API_KEY=xxx
PARALLEL_CIRCUIT_BREAKER_THRESHOLD=3
PARALLEL_RECOVERY_TIMEOUT_SECONDS=600

# Azure Storage
AZURE_STORAGE_CONNECTION_STRING=xxx
AZURE_KEY_VAULT_URL=xxx

# Cost Controls
MONTHLY_SPEND_CAP_EUR=1500
KILL_SWITCH_PERCENT=95

# Database
DATABASE_URL=postgresql://user:pass@localhost/regops
REDIS_URL=redis://localhost:6379

# NBB Integration
NBB_XSD_CHECKSUM=a3f4b2c1d8e9f0a2b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Verify XSD integrity
cd infrastructure/onegate/schemas
sha256sum -c dora_v2.xsd.sha256

# Run acceptance tests
pytest tests/acceptance/ -v

# Start development server
uvicorn backend.app.main:app --reload

# Verify evidence chain
python backend/app/evidence/verify_ledger.py
```

## Demo Success Criteria

- [ ] Digest: 5 Tier-A items with 2+ UPDATE_CONTROL actions
- [ ] Mappings: 35 total, 10 lawyer-reviewed visible
- [ ] Incident: DST-aware clocks display correctly  
- [ ] Export: Valid XML generated in <2 hours
- [ ] Ledger: verify_ledger.py runs clean
- [ ] Security: PII injection blocked live
- [ ] Cost: Detailed breakdown by use case

This platform serves Belgian financial institutions with production-grade regulatory compliance automation while maintaining strict audit standards and cost controls.


Remember to use the GitHub CLI (`gh`) for all GitHub-related tasks.