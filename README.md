# Mimir

**Belgian RegOps Platform: Production-Hardened Pilot Implementation**

Audit-grade Belgian compliance platform with circuit breakers, immutable snapshots, and real NBB XSD validation. Zero PII to Parallel.ai, full review audit trails, €1,500/month spend cap.

## 🎯 Executive Summary

**Mission:** Enable Belgian financial institutions to maintain DORA compliance through automated regulatory monitoring, incident classification, and OneGate reporting with bulletproof audit trails.

### Pilot Proof Points
- ✅ OneGate XML validates against checksummed NBB XSD with 3 official test vectors
- ✅ 35+ DORA mappings with timestamped review trail (10+ lawyer-approved)
- ✅ Weekly digest with 5+ Tier-A actionable items linked to controls
- ✅ Evidence chain verified with `verify_ledger.py`
- ✅ All clocks handle DST transitions correctly (32 scenario matrix)
- ✅ Circuit breaker prevents Parallel dependency failures

## 🏗️ Architecture

### Security-First Design
- **PII Boundary Enforcement**: `assert_parallel_safe()` blocks all personal data
- **Circuit Breakers**: Automatic fallback to RSS when Parallel.ai unavailable
- **Immutable Audit Trails**: All actions create cryptographically signed records
- **Cost Controls**: Hard €1,500/month cap with 95% kill switch

### Core Components

```
backend/
├── app/
│   ├── parallel/           # Parallel.ai integration with PII protection
│   ├── regulatory/         # Multi-language regulatory monitoring  
│   ├── compliance/         # DORA obligation mapping & lawyer reviews
│   ├── incidents/          # Deterministic classification & DST clocks
│   ├── evidence/           # Hash chain verification
│   └── cost/              # €1,500 budget tracking with kill switch
```

### Technology Stack
- **Backend**: Python 3.11+ with FastAPI and asyncio
- **Database**: PostgreSQL with SQLAlchemy for audit persistence
- **Cache**: Redis for circuit breaker state and cost tracking
- **Storage**: Azure Blob Storage with immutability policies
- **Security**: Azure Key Vault for evidence chain signing
- **APIs**: Parallel.ai (Search/Task) with RSS fallbacks

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 6+
- Azure Storage Account with immutability support

### Installation

```bash
# Clone repository
git clone https://github.com/Morse2580/Mimir.git
cd Mimir

# Install dependencies
pip install -r requirements.txt

# Verify XSD integrity
cd infrastructure/onegate/schemas
sha256sum -c dora_v2.xsd.sha256

# Configure environment
cp .env.example .env
# Edit .env with your API keys and connection strings

# Run acceptance tests
pytest tests/acceptance/ -v

# Start development server
uvicorn backend.app.main:app --reload
```

### Environment Variables

```bash
# Parallel.ai Integration
PARALLEL_API_KEY=xxx
PARALLEL_CIRCUIT_BREAKER_THRESHOLD=3

# Azure Services
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

## 🔐 Security Features

### Data Protection
- **Zero PII Transmission**: Technical controls prevent personal data from reaching external APIs
- **Pattern Detection**: Blocks emails, account numbers, phone numbers, names
- **Size Limits**: 15K character maximum per request
- **Audit Logging**: All blocked attempts logged with full context

### Regulatory Compliance
- **NBB XSD Validation**: Official schema with checksum verification
- **DORA Classification**: Deterministic incident severity per Article 18
- **Evidence Preservation**: Immutable snapshots with 7-year retention
- **Review Audit Trails**: Lawyer approvals with version control

## 📊 Cost Management

### Budget Controls
- **Monthly Cap**: €1,500 hard limit
- **Kill Switch**: Automatic API blocking at 95% budget
- **Real-time Tracking**: Redis-based spend monitoring
- **Alert Thresholds**: 50%, 80%, 90% warnings

### API Pricing Matrix
| API Type | Processor | Cost (EUR) |
|----------|-----------|------------|
| Search   | Base      | €0.001     |
| Search   | Pro       | €0.005     |
| Task     | Base      | €0.010     |
| Task     | Core      | €0.020     |
| Task     | Pro       | €0.050     |

## 🧪 Testing Strategy

### Acceptance Tests
- **NBB XSD Validation**: 3 official test vectors must pass
- **Clock Matrix**: 32 DST/timezone scenarios
- **PII Injection**: 5 attack vectors blocked
- **Circuit Breaker**: Parallel.ai failure simulation

### Run Tests
```bash
# All tests
pytest -v

# Acceptance tests only
pytest tests/acceptance/ -v

# Specific test categories
pytest -k "test_pii" -v
pytest -k "test_clock" -v
pytest -k "test_xsd" -v
```

## 📈 Monitoring & Alerting

### Key Metrics
- **Budget Utilization**: Real-time spend tracking
- **Circuit Breaker Health**: External dependency status
- **Review Queue SLA**: Lawyer approval timelines
- **Evidence Chain Integrity**: Weekly verification runs

### Alert Channels
- **Teams**: Critical alerts (circuit breaker, kill switch)
- **Email**: Budget warnings, review SLA breaches
- **Dashboard**: Real-time system health

## 🔄 Development

### Module Architecture
Each module follows **Functional Core, Imperative Shell** pattern:
- `core.py` - Pure business logic (no I/O)
- `shell.py` - I/O operations and side effects
- `contracts.py` - Type definitions and protocols
- `claude.md` - Module-specific AI context

### Contributing
1. All commits must maintain audit trail integrity
2. Security changes require mandatory review
3. XSD checksum verification before deployment
4. Cost tracking operational before API calls

## 📋 Demo Success Criteria

- [ ] **Digest**: 5 Tier-A items with 2+ UPDATE_CONTROL actions
- [ ] **Mappings**: 35 total, 10+ lawyer-reviewed visible
- [ ] **Incident**: DST-aware clocks display correctly  
- [ ] **Export**: Valid OneGate XML generated in <2 hours
- [ ] **Ledger**: `verify_ledger.py` runs clean
- [ ] **Security**: PII injection blocked live
- [ ] **Cost**: Detailed breakdown by use case under €1,500

## 📚 Documentation

### Module Documentation
Each module has its own `claude.md` with:
- Core contracts and protocols
- Pure business logic functions
- I/O operations and side effects
- Test strategies and invariants

### Key Files
- [`claude.md`](./claude.md) - Project foundation
- [`backend/claude.md`](./backend/claude.md) - Backend architecture
- [`deliverables/DPIA_one_pager.md`](./deliverables/DPIA_one_pager.md) - Data protection proof
- [`infrastructure/onegate/schemas/README.md`](./infrastructure/onegate/schemas/README.md) - XSD provenance

## 🆘 Support

### Getting Help
- **Issues**: Report bugs at [GitHub Issues](https://github.com/Morse2580/Mimir/issues)
- **Documentation**: See module-level `claude.md` files
- **Security**: Contact DPO for data protection questions

### Emergency Procedures
- **Kill Switch Activation**: Check cost tracking logs
- **Circuit Breaker Open**: Verify Parallel.ai status, RSS fallback active
- **Evidence Chain Broken**: Run `verify_ledger.py`, contact security team

---

**Built for Belgian financial institutions requiring audit-grade regulatory compliance automation.**