# ⚖️ LAWYER-UI - Review Interface Implementation Guide

## 🎯 **What You're Building**
**Minimal but usable lawyer interface** for the review workflow so lawyers can actually approve/reject mappings instead of just API calls.

## 🚨 **Critical Claude Commands for This Worktree**

### **Step 1: Start Development Session**
```bash
cd ../regops-worktrees/lawyer-ui
claude  # Start interactive Claude session in lawyer-ui worktree
```

### **Step 2: Tell Claude What to Build**
```
Please implement a minimal lawyer review interface for the Belgian RegOps Platform.

Create a Next.js 14 application with:
1. Review queue page with SLA indicators (Urgent <4h, High <24h warnings)
2. Review detail page with evidence preview and one-click approve/reject
3. Comments required for rejection/revision decisions
4. Concurrent review protection (optimistic locking)
5. Belgian/EU styling (clean, professional, multi-language ready)
6. Integration with existing FastAPI backend review endpoints

Keep it minimal but production-ready. Focus on usability over features.

Follow the PLAN → IMPLEMENT → TEST → VERIFY → REPORT workflow.
```

## ✅ **Success Criteria**
- [ ] Review queue shows pending requests with SLA warnings
- [ ] One-click approve/reject with mandatory comments
- [ ] Evidence documents preview without external requests
- [ ] Concurrent review conflicts handled gracefully  
- [ ] Clean, professional UI suitable for legal professionals