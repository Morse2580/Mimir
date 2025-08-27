# claude.md - Backend Commands

YOU ARE implementing backend modules using **Functional Core, Imperative Shell** pattern.

## 🏗️ ARCHITECTURE RATIONALE

**Why Functional Core / Imperative Shell:**
- **Determinism for audit**: Rules, deadline math, XML builders are pure → reproducible, hashable
- **Testability**: Unit-test core (no I/O); golden vectors for law-driven logic (incl. DST)
- **Chain of custody**: Pure inputs → pure outputs → hash & sign → provable evidence
- **Safe change**: Update rules YAML + vectors; CI blocks until tests pass

**System Flow:**
1. **Regulatory Monitor** → Parallel Search (NL/FR/EN, Tier-A policy) → Task Extract → **Snapshot** (immutable) → Store
2. **Obligation Mapper** → Task Map → **Legal Review** (RBAC + review log) → **Evidence Ledger**
3. **Incident** → **Rules DSL (deterministic)** → Optional Task Enrich (no PII) → **OneGate XML** (XSD-validated) → ZIP
4. **Guardrails** → PII Boundary → Circuit Breaker (degraded modes) → Cost Tracker & **Kill Switch**
5. **Observability** → SLOs (export p95, digest by 09:00, error rates) + alerts; ledger weekly verification

## 🚨 BACKEND RULES - NEVER BREAK

**FILE SEPARATION (MANDATORY):**
- `core.py` - ONLY pure functions (no async, no I/O, deterministic)
- `shell.py` - ALL I/O operations (databases, APIs, file system)
- `contracts.py` - Type definitions and protocols
- `events.py` - Domain events this module emits

**YOU MUST NEVER:**
- Put I/O operations in core.py
- Use exceptions in core functions (use Result types)
- Import shell modules from core modules
- Create circular event subscriptions
- Exceed 200 lines per file

## ⚡ DEVELOPMENT PATTERN

**FOR EVERY MODULE:**
1. **READ** the module's claude.md first
2. **WRITE** core.py with pure functions
3. **WRITE** shell.py with I/O operations
4. **TEST** core functions without mocks
5. **TEST** shell integration with mocks

## 📋 RESULT TYPE TEMPLATE

**USE THIS PATTERN:**
```python
from dataclasses import dataclass
from typing import Generic, TypeVar, Union

T = TypeVar('T')
E = TypeVar('E')

@dataclass(frozen=True)
class Success(Generic[T]):
    value: T

@dataclass(frozen=True)
class Failure(Generic[E]):
    error: E

Result = Union[Success[T], Failure[E]]
```

## 🎯 PERFORMANCE TARGETS

**Core Functions:**
- <1ms execution (pure computation only)
- Deterministic (same input = same output)
- No memory leaks (immutable data)

**Shell Operations:**
- Database queries: <50ms
- External APIs: <200ms
- Event publishing: <10ms

**MODULE INTEGRATION:**
- Event-driven communication only
- No direct module imports
- Async operations in shell layer only

## 🎯 PILOT-READY HARDENING

**State Machine Pattern:**
- Model incidents as: `Detected → Classified → Notified(Initial) → Notified(Intermediate) → Finalized`
- Store `entered_at` timestamps per state (UTC + Brussels)
- Derive deadlines from state transitions, not free-form dates

**Contracts & Interfaces:**
- Define typed JSON schemas: `RegulatoryItem`, `ObligationMapping`, `IncidentInput`, `ClassificationResult`
- Validate on module boundaries (anti-regression net)
- Store in `/contracts/*.json` schema registry

**SLOs & Observability:**
- SLO-01: OneGate export p95 < 30 min (budget < 2h hard)
- SLO-02: Digest job completes by 09:00 CET daily
- SLO-03: Parallel error rate < 2% over 15m; else open breaker
- SLO-04: PII guard violations = 0; any event pages on-call

**Multilingual Determinism:**
- Store `source_lang`, `source_excerpt`, `translated_excerpt`
- Display both in UI/exports; never overwrite original
- Acceptance test: digest must include ≥1 NL and ≥1 FR Tier-A item

**Degraded Modes:**
- Digest = last known Tier-A + RSS delta, marked "degraded"
- Mapping = queue for review; allow manual URL paste with snapshot
- Incident = rules still run; enrichment skipped; export still valid