# 🧪 INTEGRATION TESTS - End-to-End Testing Implementation Guide

## 🎯 **What You're Building**
**Comprehensive end-to-end tests** with NBB golden vectors (if available) and complete incident → classification → OneGate export flow testing.

## 🚨 **Critical Claude Commands for This Worktree**

### **Step 1: Start Development Session**
```bash
cd ../regops-worktrees/integration-tests
claude  # Start interactive Claude session in integration-tests worktree
```

### **Step 2: Tell Claude What to Build**
```
Please implement comprehensive integration tests for the Belgian RegOps Platform.

Create:
1. End-to-end flow: Incident Input → DORA Classification → Review Workflow → OneGate Export
2. NBB XSD validation tests with golden vectors (create sample vectors if official ones unavailable)
3. Concurrent review protection tests (two lawyers reviewing same request)
4. Schema contract validation across all module boundaries  
5. Load testing for budget race conditions and circuit breaker scenarios
6. Complete DST deadline calculation validation across all 32 scenarios
7. PII injection attack testing against all 5 attack vectors

These tests must prove the entire system works correctly under all conditions.

Follow the PLAN → IMPLEMENT → TEST → VERIFY → REPORT workflow.
```

## ✅ **Success Criteria**
- [ ] Complete incident-to-export flow tested end-to-end
- [ ] NBB XSD validation with golden test vectors  
- [ ] Concurrent review conflicts properly handled
- [ ] All contract schemas validated at boundaries
- [ ] System handles race conditions and edge cases