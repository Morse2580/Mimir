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

## Development Practices

**Commit Rules:**
- Prefix: `feat:`, `fix:`, `security:`, `audit:`, `test:`
- All commits must maintain audit trail integrity
- Security changes require mandatory review

**Review Process:**
- Lawyer review required for obligation mappings
- All reviews create immutable audit entries
- Review state machine prevents stale approvals

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