# claude.md

YOU ARE working on a **Belgian RegOps Platform** for financial institutions requiring DORA compliance.

## 📚 DOMAIN KNOWLEDGE

**DORA (EU Reg. 2022/2554):**
- Purpose: Make EU financial entities operationally resilient against ICT incidents
- Who: Banks, insurers, payment institutions, investment firms, critical ICT third-party providers
- Key duties: ICT risk management, incident reporting with hard deadlines, registers, testing, third-party oversight
- Why critical: Hard deadlines, auditable evidence required, failure = supervisory action/fines

**NIS2 (Directive):**  
- Purpose: Raise baseline cyber resilience across essential/important entities
- Core duties: Risk management, incident notification timelines, supply-chain oversight
- Penalties: Up to €10M or 2% revenue for essential entities

**Belgian Supervisors:**
- **NBB** (National Bank): Prudential supervisor, OneGate reporting portal (XML submissions)
- **FSMA**: Markets conduct/consumer protection
- **CCB/Safeonweb**: National cyber guidance, NIS2 hub
- **Languages**: Publications in NL/FR/EN - system must handle all three

**Why Mimir exists:** Automate continuous compliance + produce auditor-grade artifacts (cited digests, obligation mappings, OneGate-ready incident packs) within official deadlines.

## 🚨 CRITICAL RULES - NEVER VIOLATE

**YOU MUST NEVER:**
- Send PII to external APIs (emails, IDs, names, phone numbers)
- Skip `assert_parallel_safe()` validation before Parallel.ai calls
- Exceed €1,500 monthly spend cap
- Break audit trail integrity
- Modify cost guardrails without human approval

**YOU MUST ALWAYS:**
- Follow PLAN → IMPLEMENT → TEST → VERIFY → REPORT loop
- Keep commits <150 LOC
- Run acceptance tests before merging
- Emit domain events for state changes
- Use Result types, never exceptions in core logic

## 🛠️ DEVELOPMENT WORKFLOW (MANDATORY)

**EVERY TASK FOLLOWS THIS PATTERN:**
1. **PLAN** - Read module's claude.md, break into <150 LOC commits
2. **IMPLEMENT** - Write core.py (pure), shell.py (I/O), tests  
3. **TEST** - Run pytest, verify all acceptance criteria pass
4. **VERIFY** - Check audit trails preserved, no PII violations
5. **REPORT** - Summarize changes, test results, next steps

## ⚠️ STOP AND ASK APPROVAL FOR:
- Changes to `assert_parallel_safe()` function
- Budget/cost tracking modifications  
- Evidence chain or audit trail changes
- XSD schema or NBB integration changes
- Database schema migrations

## 📁 KEY MODULES (each has own claude.md)

**SECURITY LAYER:**
- `backend/app/parallel/common/` - PII boundary + circuit breaker
- `backend/app/cost/` - €1,500 budget enforcement + kill switch

**COMPLIANCE LAYER:**  
- `backend/app/incidents/rules/` - DORA classification (deterministic)
- `backend/app/compliance/reviews/` - Lawyer approval workflow
- `backend/app/regulatory/monitor/` - Multi-language source scanning

**CRITICAL FILES:**
- `infrastructure/onegate/schemas/dora_v2.xsd` - Official NBB schema
- `tests/acceptance/test_pii_injection.py` - 5 attack vectors
- `tests/acceptance/test_clock_matrix.py` - 32 DST scenarios

## ✅ ALLOWED TOOLS ONLY
- `pytest`, `black`, `ruff` - Testing and formatting
- `git`, `gh` - Version control (YOU MUST use gh for GitHub tasks)
- `uvicorn`, `httpx`, `lxml` - Development server, HTTP, XSD validation

## ❌ FORBIDDEN - ASK FIRST
- `rm -rf`, database migrations, schema changes
- Terraform, production deployments  
- Modifications to cost/guardrails.py or evidence/verify_ledger.py

## 🎯 SUCCESS CRITERIA (must achieve ALL)
- All 32 DST clock scenarios pass
- 5 PII injection attack vectors blocked
- NBB XSD test vectors validate  
- Cost tracking <€1,500 with kill switch functional
- Circuit breaker recovers from Parallel.ai failures

## 🚀 QUICK COMMANDS

**Start Working:**
```bash
# Run tests first
pytest tests/acceptance/ -v

# Start server
uvicorn backend.app.main:app --reload

# Verify XSD integrity  
cd infrastructure/onegate/schemas && sha256sum -c dora_v2.xsd.sha256
```

**Before Every Commit:**
```bash
# Check PII boundaries still work
pytest tests/acceptance/test_pii_injection.py -v

# Verify clock matrix passes
pytest tests/acceptance/test_clock_matrix.py -v

# Format code
black . && ruff check .
```

## 📋 COMMIT TEMPLATE

**USE THIS FORMAT:**
```
feat(module): brief description

- What changed (specific functions/files)
- Test results: X/Y tests passing  
- Security: PII boundaries verified
- Cost: Budget impact €X.XX
- Next: what to implement next

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

**FINAL RULE:** When in doubt, ask. Better to confirm than break audit trails or exceed budget.

---

## 🤖 AGENTIC CODING WORKFLOWS

### 🎯 AUTONOMOUS IMPLEMENTATION STRATEGY

**WHEN USER SAYS "-p" (PROCEED):**
1. **ANALYZE** current todo list status
2. **SELECT** next pending task 
3. **READ** relevant module claude.md for implementation steps
4. **EXECUTE** the 5-step workflow automatically
5. **COMMIT** and **REPORT** results

**MODULE IMPLEMENTATION PATTERN:**
- Read module's claude.md FIRST (contains exact implementation steps)
- Follow the STEP 1/STEP 2 structure in module claude.md
- Write core.py (pure functions) before shell.py (I/O operations)  
- Test core functions without mocks, shell functions with mocks
- Commit each file separately (<150 LOC per commit)

### 🚦 AUTONOMOUS DECISION MAKING

**PROCEED WITHOUT ASKING WHEN:**
- Task has clear implementation steps in module claude.md
- Using only allowed tools (pytest, git, uvicorn, etc.)
- Commit size <150 LOC
- No approval gates triggered
- Following established patterns

**ASK FOR CONFIRMATION WHEN:**
- Multiple valid implementation approaches
- Approaching forbidden operations or approval gates
- Test failures indicating potential design issues  
- Unclear integration points between modules
- User requirements ambiguous

### 🔄 CONTINUOUS WORK LOOP

**FOR EXTENDED CODING SESSIONS:**
1. Complete current task following 5-step workflow
2. Update todo list status
3. **AUTO-SELECT** next highest priority pending task
4. Read that module's claude.md
5. Begin implementation without waiting for user input
6. Continue until blocked or all tasks complete

**REPORTING FORMAT:**
- Brief progress update after each commit
- Test results and security verification status
- What's next in the implementation queue
- Stop and ask if encountering blockers

---

## 🧱 PRODUCTION-READY TECH STACK

Here's the **production-ready tech stack** for Mimir (Belgian RegOps pilot), broken down by layer with concrete versions, rationale, and roles.

### 🧩 Core Choices
* **Language:** Python **3.11**
* **Architecture style:** **Functional Core / Imperative Shell**
* **Environments:** Local (Docker) → **Azure** (Container Apps)
* **Data residency:** EU regions only; immutable evidence in **Azure Blob** with legal hold

### 👩‍💻 Frontend (Auditor Cockpit + Ops UI)
* **Framework:** **Next.js 14** (React 18, App Router) + **TypeScript 5**
* **UI:** **Tailwind CSS 3**, **shadcn/ui**, **lucide-react** (clean, accessible components)
* **State/data:** **TanStack Query** (server cache), **Zustand** (local state)
* **Forms:** **react-hook-form** + **zod** (schema validation)
* **i18n:** **i18next** (EN/NL/FR UI labels; don't translate source excerpts)
* **Auth (OIDC):** **NextAuth** with **Azure AD (Entra ID)**
* **Build/dev:** **Vite** (dev) / Next build (prod), **ESLint**, **Prettier**
* **Why:** Fast to build, easy theming, good enterprise SSO story

### 🐍 Backend APIs & Services
* **Web framework:** **FastAPI** (ASGI) + **Uvicorn**
* **Schema/types:** **Pydantic v2**
* **DB ORM:** **SQLAlchemy 2** + **Alembic** (migrations)
* **Background jobs:** **Celery 5** + **Redis 7** (for Parallel Task orchestration, digest, snapshots)
* **Scheduling:** **APScheduler** (daily/weekly runs)
* **HTTP client:** **httpx** (async; Parallel, NBB, snapshots)
* **Time/tz:** **zoneinfo** (stdlib) + **pendulum** (clear DST math)
* **Validation/XSD:** **lxml** (OneGate XML build + schema validation)
* **PDF generation:** **WeasyPrint** (incident report PDF)
* **Crypto/signing:** **cryptography** (hash/sign), Azure SDK (Key Vault)
* **Why:** Async-first, typed, testable; pure core functions isolate compliance logic

### 🗂️ Data & Storage
* **Primary DB:** **PostgreSQL 15/16** (Azure Database for PostgreSQL Flexible Server)
  - Tables: `incidents`, `obligation_mappings`, `mapping_reviews`, `evidence_ledger`, `digests`, `parallel_usage`
* **Cache/queue:** **Redis 7** (Azure Cache for Redis)
* **Evidence & snapshots:** **Azure Blob Storage** (immutable, legal hold + versioning)
  - Container `evidence/` (hash-chained JSON, XML, PDF), `snapshots/` (HTML/PDF of sources)
* **Why:** Postgres for relational audit trails; Blob immutability for regulator-proof retention

### ☁️ Cloud & Platform (Azure)
* **Runtime:** **Azure Container Apps** (or App Service) for API & workers
* **Secrets:** **Azure Key Vault** (Parallel API key, signing keys)
* **Monitoring:** **Azure Application Insights** (traces, metrics, logs)
* **Auth / SSO:** **Azure AD (Entra ID)** (OIDC; groups ↔ RBAC)
* **IaC:** **Terraform** (rg, container apps, key vault, storage, redis, postgres)
* **Why:** Simple, managed, EU regions; scales enough for pilot

### 🤖 Parallel.ai Integration
* **APIs used:** **Search API** (fast retrieval), **Task API** (deep, structured research), **Webhooks** (async completion)
* **Client:** **httpx** (thin wrapper), optional Parallel Python SDK if available
* **Source policy:** allowlist **fsma.be**, **nbb.be**, **eur-lex.europa.eu**, **europa.eu**, **esma.europa.eu**, **eiopa.europa.eu**, **ccb.belgium.be**
* **Guards:** `assert_parallel_safe()` (forbidden keys/patterns; payload ≤ **15k chars**)
* **Circuit breaker:** custom (Redis counters + exponential backoff) → **fallback** to curated **RSS/sitemaps** + cached results
* **Cost control:** Redis tracker + **€1,500/month cap**; **kill switch at 95%**
* **Why:** Auto-citations + structured outputs; fallbacks ensure degraded but usable service

### 🔐 Security & Compliance
* **PII boundary:** hard block on sensitive fields/patterns before any external call
* **Webhooks:** **HMAC** signature + timestamp + **replay cache** (Redis TTL 5m); fail-closed
* **RBAC:** roles `Analyst`, `Reviewer(Legal)`, `Admin` (enforced in API + UI)
* **Evidence ledger:** SHA-256 **hash-linked** records; **Key Vault** signing; weekly `verify_ledger.py`
* **Retention:** Evidence/snapshots 7y immutable; app logs 1y; Parallel payloads 90d max
* **SAST/Deps:** **Bandit**, **Semgrep**, **pip-tools**, **Dependabot**; container scan with **Trivy**
* **Why:** Auditor-credible posture; least-privilege, tamper-evident artifacts

### 🧪 Testing & Quality
* **Unit/func tests:** **pytest**, **hypothesis**
* **HTTP mocks:** **respx** / **responses** (Parallel/NBB)
* **Golden vectors:** fixtures for **DST** edge cases (32-scenario matrix)
* **Contract tests:** Pydantic models for `RegulatoryItem`, `ClassificationResult`, `OneGateExport`
* **XSD tests:** Validate against **checksummed** NBB XSD + 3 sample vectors
* **PII red-team:** injection tests (emails, VAT, IBAN, nat. no.) must **raise**
* **CI:** **GitHub Actions** (lint, type, tests, docker build, security scan)
* **Why:** Locks down the "deterministic core" and schema fidelity

### 📈 Observability & SLOs
* **Metrics:** App Insights + OpenTelemetry (`parallel.calls`, `breaker.state`, `digest.tierA.count`, `clock.deadline.miss`, `ledger.verify.ok`)
* **Dashboards/alerts:** Digest job by **09:00 CET**, OneGate export **p95 < 30 min**, Parallel **5xx/429 >2%/15m** opens breaker, PII violations **= 0**
* **Why:** Early warning + pilot health visibility

### 🧰 Developer Tooling
* **Task runner:** **Make** or **just**; **pre-commit** hooks (Black, isort, Ruff/Flake8)
* **Packaging:** **pip-tools** (`requirements.in` → `requirements.txt`)
* **Containers:** **Docker**; `docker-compose.local.yml` for full stack
* **Docs:** Repo-wide **README.md**, module **claude.md**, **/docs/adr/** (architecture decisions)
* **Local secrets:** `.env` (dev only), **never** in prod

### 📦 Key Python Packages (Backend)
```
fastapi, uvicorn[standard], pydantic>=2, sqlalchemy>=2, alembic,
httpx[http2], lxml, weasyprint, cryptography, azure-identity,
azure-keyvault-keys, azure-storage-blob, redis, celery, apscheduler,
pendulum, python-dateutil, structlog, opentelemetry-sdk, pytest, 
hypothesis, respx
```

### 🔌 External Integrations
* **Azure AD (OIDC)** → auth & roles
* **NBB OneGate** → schema-checked **XML export** (pilot: export-only; no live submission)
* **Email/Chat** (optional) → Teams/SMTP for alerts
* **ServiceNow/Jira** (Phase 2) → tickets from digest/actions

### 🧭 Migration Switches (Local → Azure)
* **Feature flags:** `DEPLOY_ENV=LOCAL|AZURE`, `SUBMISSION_MODE=EXPORT_ONLY`, `PARALLEL_ENABLED=true|false`
* **Storage abstraction:** `EvidenceStore` (LocalFS impl vs Blob impl)
* **Secrets provider:** `.env` (dev) → **Key Vault** (prod)

### 📝 TL;DR Stack Summary
* **Python/FastAPI + Postgres/Redis** for a typed, testable core
* **Next.js/TypeScript** for a clean auditor cockpit
* **Azure** for managed, EU-resident services
* **Parallel.ai** for cited research with strict PII, cost, and resiliency guardrails
* **XSD + hash-linked evidence** to earn auditor trust from day one