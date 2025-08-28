# 📈 OBSERVABILITY - Production Monitoring Implementation Guide

## 🎯 **What You're Building**
**Comprehensive observability** with metrics, traces, and logs to prove the system works as intended for auditors and compliance officers.

## 🚨 **Critical Claude Commands for This Worktree**

### **Step 1: Start Development Session**
```bash
cd ../regops-worktrees/observability
claude  # Start interactive Claude session in observability worktree
```

### **Step 2: Tell Claude What to Build**
```
Please implement comprehensive observability for the Belgian RegOps Platform.

Create:
1. Business metrics: parallel.calls, digest.tierA.count, clock.deadline.miss, ledger.verify.ok
2. Security metrics: pii.violations=0, budget.utilization, circuit.breaker.state  
3. Performance SLOs: PII detection <50ms, Cost checking <10ms, OneGate export <30min
4. Dashboards: business_overview.json, performance_slos.json, security_monitoring.json
5. Alerting: Budget >95%, PII violations, deadline misses
6. OpenTelemetry integration for traces and spans

Add metrics collection points to all existing modules without breaking functionality.

Follow the PLAN → IMPLEMENT → TEST → VERIFY → REPORT workflow.
```

## ✅ **Success Criteria**
- [ ] All business metrics instrumented and collecting
- [ ] Security alerts fire on violations (PII, budget, deadlines)  
- [ ] Performance SLOs tracked and alerting
- [ ] Dashboards show real-time compliance status
- [ ] Auditors can prove system working as intended