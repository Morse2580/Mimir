# claude.md

YOU ARE working on a **Belgian RegOps Platform** for financial institutions requiring DORA compliance.

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