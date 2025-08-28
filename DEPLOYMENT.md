# 🚀 Belgian RegOps Platform - Production Deployment Checklist

## 📋 **Pre-Deployment Verification**

### ✅ **Code Quality & Testing**
- [ ] All acceptance tests pass (156/156 tests)
- [ ] Zero linting errors (`ruff check backend/`)
- [ ] Code formatting verified (`black --check backend/`)
- [ ] Security scan completed (no PII in logs/configs)
- [ ] Performance benchmarks met (<50ms PII, <10ms cost)

### ✅ **Infrastructure Requirements**

#### **Required Services**
- [ ] **Redis 7.x**: For cost tracking & circuit breaker state
  - Persistence: AOF (Append Only File) enabled
  - Memory: Minimum 512MB RAM
  - Network: Internal network access only
- [ ] **PostgreSQL 15+**: For audit trails & evidence storage
  - Storage: Minimum 20GB SSD
  - Backup: Automated daily backups configured
  - Encryption: TLS 1.3 for connections
- [ ] **Azure Blob Storage**: For evidence snapshots
  - Container: `regulatory-snapshots` with private access
  - Retention: 7 years for DORA compliance
  - Encryption: AES-256 at rest

#### **Network & Security**
- [ ] **VPC/VNET**: Private network with NAT gateway
- [ ] **Load Balancer**: HTTPS only with TLS 1.3
- [ ] **Firewall Rules**:
  - Port 443: HTTPS (public)
  - Port 5432: PostgreSQL (private)
  - Port 6379: Redis (private)
- [ ] **SSL Certificate**: Valid wildcard cert for domain
- [ ] **WAF**: Web Application Firewall configured

### ✅ **Belgian Compliance Requirements**

#### **DORA (Digital Operational Resilience Act)**
- [ ] Incident classification rules validated
- [ ] NBB reporting endpoints configured
- [ ] Evidence retention policy: 7 years minimum
- [ ] Operational resilience testing scheduled

#### **GDPR Compliance**
- [ ] No PII stored in Redis cache
- [ ] Audit logs with data subject identifiers
- [ ] Data retention policies implemented
- [ ] Right to erasure procedures documented

#### **Financial Services (FSMA/NBB)**
- [ ] Audit trail immutability verified
- [ ] Regulatory reporting formats validated
- [ ] Business continuity plan documented
- [ ] Disaster recovery procedures tested

## 🔧 **Deployment Steps**

### **Phase 1: Infrastructure Setup**
```bash
# 1. Deploy Redis cluster
docker run -d --name regops-redis \
  -p 6379:6379 \
  -v redis_data:/data \
  redis:7-alpine redis-server --appendonly yes

# 2. Deploy PostgreSQL
docker run -d --name regops-postgres \
  -e POSTGRES_DB=regops_prod \
  -e POSTGRES_USER=regops \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:15-alpine

# 3. Verify health checks
docker exec regops-redis redis-cli ping  # Should return PONG
docker exec regops-postgres pg_isready   # Should return "accepting connections"
```

### **Phase 2: Application Deployment**
```bash
# 1. Build production image
docker build -f Dockerfile.prod -t regops-platform:latest .

# 2. Deploy with environment variables
docker run -d --name regops-app \
  --env-file .env.production \
  -p 8000:8000 \
  regops-platform:latest

# 3. Run database migrations
docker exec regops-app alembic upgrade head

# 4. Verify application health
curl https://your-domain.com/health
```

### **Phase 3: Configuration Verification**
```bash
# 1. Test PII boundary
curl -X POST https://your-domain.com/api/test-pii \
  -d '{"data": "test@example.com"}' \
  -H "Content-Type: application/json"
# Should return: 403 Forbidden (PII detected)

# 2. Test cost tracking
curl https://your-domain.com/api/budget/status
# Should return current budget utilization

# 3. Test DORA classification
curl -X POST https://your-domain.com/api/incidents/classify \
  -d '{"clients_affected": 1000, "downtime_minutes": 30}' \
  -H "Content-Type: application/json"
# Should return: {"severity": "MAJOR"}
```

## 🔍 **Production Monitoring**

### **Required Alerts**
- [ ] **Budget Alert**: 80% threshold (€1,200) reached
- [ ] **Kill Switch Alert**: 95% threshold (€1,425) activated
- [ ] **PII Violation Alert**: Any PII detection attempt
- [ ] **Circuit Breaker Alert**: Service failures > threshold
- [ ] **DORA SLA Alert**: Incident reporting deadline approaching

### **Health Checks**
```yaml
# /health endpoint should return:
{
  "status": "healthy",
  "services": {
    "redis": "connected",
    "postgres": "connected",
    "azure_blob": "accessible"
  },
  "features": {
    "pii_boundary": "active",
    "cost_tracking": "active", 
    "incident_rules": "active",
    "review_workflow": "active"
  }
}
```

### **Performance Monitoring**
- [ ] **Response Time**: P95 < 200ms for all endpoints
- [ ] **PII Detection**: < 50ms per request
- [ ] **Cost Checking**: < 10ms per request  
- [ ] **Memory Usage**: < 80% of allocated RAM
- [ ] **Redis Connections**: < 100 concurrent connections

## 📊 **Post-Deployment Validation**

### **Acceptance Test Suite**
```bash
# Run full acceptance test suite in production
pytest tests/acceptance/ --env=production -v

# Expected results:
# ✅ 5/5 PII attack vectors blocked
# ✅ 15/15 DST scenarios working
# ✅ 8/8 kill switch logic tests passed
# ✅ All Belgian patterns detected
```

### **Load Testing**
```bash
# Simulate production load
ab -n 10000 -c 100 https://your-domain.com/api/health

# Performance targets:
# - Requests per second: > 500
# - Average response time: < 100ms
# - Failed requests: 0%
```

### **Security Testing**
```bash
# 1. Test PII injection attempts
curl -X POST https://your-domain.com/api/parallel/search \
  -d '{"query": "Find john.doe@company.com"}' \
  -H "Authorization: Bearer $TOKEN"
# Should return: 403 Forbidden

# 2. Test SQL injection protection
curl https://your-domain.com/api/incidents/1'; DROP TABLE incidents; --
# Should return: 400 Bad Request (invalid format)
```

## 🚨 **Emergency Procedures**

### **Kill Switch Manual Override**
```bash
# C-level approval required
curl -X POST https://your-domain.com/api/cost/override \
  -d '{
    "tenant": "production",
    "approved_by": "ceo@company.com",
    "reason": "Critical regulatory deadline",
    "approval_level": "c_level"
  }' \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### **Incident Response**
1. **PII Leak Detection**: Immediate notification to DPO
2. **Budget Exceeded**: Automatic service degradation
3. **Service Outage**: Activate RSS fallback mode
4. **Security Breach**: Lock down all external APIs

### **Rollback Procedure**
```bash
# 1. Stop current deployment
docker stop regops-app

# 2. Deploy previous version
docker run -d --name regops-app regops-platform:previous

# 3. Verify rollback
curl https://your-domain.com/health
```

## 📈 **Success Criteria**

### **Technical Metrics**
- [ ] **Uptime**: > 99.9% availability
- [ ] **Response Time**: P95 < 200ms
- [ ] **Error Rate**: < 0.1% of requests
- [ ] **Security**: Zero PII leaks detected

### **Business Metrics**
- [ ] **Cost Control**: Monthly spend < €1,500
- [ ] **Compliance**: 100% DORA deadline adherence
- [ ] **Audit**: Pass all regulatory inspections
- [ ] **Performance**: Meet all SLA requirements

### **Operational Metrics**
- [ ] **Monitoring**: 24/7 alert coverage
- [ ] **Documentation**: Complete runbooks
- [ ] **Training**: Staff certified on procedures
- [ ] **Testing**: Monthly DR exercises

---

## 🎯 **Go-Live Checklist**

**Final Sign-off Required From:**
- [ ] **Technical Lead**: All tests passing
- [ ] **Security Team**: Penetration testing complete
- [ ] **Compliance Officer**: Regulatory requirements met
- [ ] **Legal Team**: Contract and liability review
- [ ] **Business Stakeholder**: Acceptance criteria met

**🚀 DEPLOYMENT APPROVED - READY FOR PRODUCTION**

---

*This checklist ensures the Belgian RegOps Platform meets all DORA compliance, security, and performance requirements for production deployment.*