# 🔐 SECURITY - Production Hardening Implementation Guide

## 🎯 **What You're Building**
**Enterprise-grade security** with Azure Key Vault secrets management, HMAC webhook validation, and proper RBAC enforcement.

## 🚨 **Critical Claude Commands for This Worktree**

### **Step 1: Start Development Session**
```bash
cd ../regops-worktrees/security-hardening
claude  # Start interactive Claude session in security worktree
```

### **Step 2: Tell Claude What to Build**
```
Please implement production security hardening for the Belgian RegOps Platform.

Create:
1. Azure Key Vault integration for all secrets (API keys, signing keys)
2. HMAC-SHA256 webhook validation with timestamp + replay protection
3. RBAC matrix: Analyst/Legal_Reviewer/Admin roles with proper enforcement
4. Secrets rotation every 90 days with automatic updates
5. Audit logging for all privileged operations
6. Remove all .env dependencies and hardcode secret references

Ensure no PII is ever logged and all security controls are fail-closed.

Follow the PLAN → IMPLEMENT → TEST → VERIFY → REPORT workflow.
```

## ✅ **Success Criteria**
- [ ] All secrets moved to Azure Key Vault
- [ ] Webhook HMAC validation with replay protection working
- [ ] RBAC enforced at every API endpoint
- [ ] Security audit trail for all privileged operations
- [ ] Zero secrets in environment variables or logs