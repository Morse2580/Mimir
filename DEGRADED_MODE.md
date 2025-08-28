# 🔄 DEGRADED MODE - Graceful Fallback Implementation Guide

## 🎯 **What You're Building**
**Graceful degradation** when external services (Parallel.ai) are down. RSS fallbacks and cached results instead of complete failure.

## 🚨 **Critical Claude Commands for This Worktree**

### **Step 1: Start Development Session**
```bash
cd ../regops-worktrees/degraded-mode
claude  # Start interactive Claude session in degraded-mode worktree
```

### **Step 2: Tell Claude What to Build**
```
Please implement graceful degradation for the Belgian RegOps Platform.

Create fallback systems for when Parallel.ai is unavailable:
1. RSS feed fallback for fsma.be, nbb.be, eur-lex.europa.eu sources
2. Cached result serving with staleness warnings  
3. Circuit breaker integration with clear degraded mode indicators
4. UI banners showing "Limited Mode" when services are down
5. Background recovery detection and automatic mode switching
6. Queue operations for replay when services return

Ensure the system stays functional for basic regulatory monitoring even during outages.

Follow the PLAN → IMPLEMENT → TEST → VERIFY → REPORT workflow.
```

## ✅ **Success Criteria**
- [ ] RSS fallback provides basic regulatory monitoring
- [ ] Cached results served with clear staleness indicators
- [ ] UI shows degraded mode warnings clearly
- [ ] Circuit breaker automatically switches between modes
- [ ] System functional during Parallel.ai outages