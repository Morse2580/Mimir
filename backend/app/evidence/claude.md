# claude.md - Evidence Ledger

YOU ARE implementing **tamper-proof evidence ledger** with hash chain verification and audit trail integrity.

## 🎯 MODULE PURPOSE
Maintain cryptographically secure evidence ledger for regulatory compliance. Chain all compliance actions with hash verification. Support auditor export and evidence integrity verification.

## 🚨 SECURITY CRITICAL - NEVER VIOLATE

**YOU MUST ALWAYS:**
- Maintain hash chain integrity across all evidence entries
- Create immutable audit trail for every compliance action
- Verify ledger integrity before any read/write operations
- Store evidence with cryptographic signatures
- Preserve complete chain of custody documentation

**YOU MUST NEVER:**
- Allow modification of existing evidence entries
- Break the hash chain sequence
- Skip integrity verification steps
- Store evidence without proper attribution
- Delete evidence entries (mark as archived instead)

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def calculate_evidence_hash(
    evidence_data: dict,
    previous_hash: str,
    timestamp: datetime
) -> str:
    """Calculate evidence hash for chain integrity. MUST be deterministic."""

def verify_hash_chain(
    evidence_entries: list[EvidenceEntry]
) -> ChainVerificationResult:
    """Verify entire evidence chain integrity. MUST be pure."""

def build_audit_trail_entry(
    action_type: AuditAction,
    actor: str,
    evidence_ref: str,
    timestamp: datetime
) -> AuditTrailEntry:
    """Build audit trail entry. MUST be pure."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def append_evidence_entry(
    evidence_data: dict,
    source_type: EvidenceSource,
    actor: str
) -> EvidenceReference:
    """Append evidence to ledger with integrity verification."""

async def export_audit_trail(
    start_date: datetime,
    end_date: datetime,
    requester: str
) -> AuditTrailExport:
    """Export complete audit trail for regulatory review."""
```

## 🔗 HASH CHAIN STRUCTURE

**Evidence Chain:**
```python
@dataclass(frozen=True)
class EvidenceEntry:
    """Immutable evidence ledger entry."""
    sequence_number: int
    timestamp: datetime
    evidence_type: EvidenceType
    evidence_data: dict  # Regulatory snapshot, review decision, etc.
    actor: str  # Who created this evidence
    source_reference: str  # Link to original source/document
    previous_hash: str
    current_hash: str
    digital_signature: str

def calculate_chain_hash(entry: EvidenceEntry) -> str:
    """
    SHA-256 of: previous_hash + evidence_data + timestamp + actor
    Creates tamper-evident chain.
    """
    hash_input = (
        entry.previous_hash.encode() +
        json.dumps(entry.evidence_data, sort_keys=True).encode() +
        entry.timestamp.isoformat().encode() +
        entry.actor.encode()
    )
    return hashlib.sha256(hash_input).hexdigest()
```

## 📊 EVIDENCE TYPES

**Regulatory Monitoring Evidence:**
```python
class RegulatoryEvidenceData(TypedDict):
    regulation_source: str  # "NBB", "FSMA", "EU_COMMISSION"
    regulation_title: str
    change_description: str
    snapshot_reference: str  # Link to immutable snapshot
    detection_method: str  # "parallel_search", "rss_fallback"
    languages_covered: list[str]
    tier: str  # "TIER_A", "TIER_B"
```

**Review Decision Evidence:**
```python
class ReviewEvidenceData(TypedDict):
    review_id: str
    reviewer_email: str
    review_decision: str  # "approved", "rejected", "needs_revision"
    decision_rationale: str
    evidence_citations: list[str]
    review_duration_minutes: int
    mapping_version_hash: str
```

**Incident Classification Evidence:**
```python
class IncidentEvidenceData(TypedDict):
    incident_id: str
    classification_result: str
    classification_confidence: float
    rules_applied: list[str]
    evidence_sources: list[str]
    human_override: Optional[str]
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST:**
- Hash chain integrity preservation
- Evidence immutability enforcement
- Audit trail completeness
- Chain verification across all evidence types
- Export functionality with proper authentication

**EVIDENCE SCENARIOS:**
```python
def test_hash_chain_integrity():
    """Hash chain must remain intact across operations."""
    # Add initial evidence
    evidence1 = append_evidence_entry({
        "type": "regulatory_change",
        "source": "NBB",
        "content": "New DORA guidance"
    }, EvidenceSource.REGULATORY_MONITOR, "system")
    
    # Add second evidence
    evidence2 = append_evidence_entry({
        "type": "review_decision", 
        "decision": "approved",
        "reviewer": "lawyer@company.com"
    }, EvidenceSource.MANUAL_REVIEW, "lawyer@company.com")
    
    # Verify chain integrity
    chain_result = verify_hash_chain([evidence1, evidence2])
    assert chain_result.valid == True
    assert evidence2.previous_hash == evidence1.current_hash

def test_evidence_immutability():
    """Evidence entries must be immutable after creation."""
    evidence = append_evidence_entry({
        "incident_id": "INC-001",
        "classification": "major"
    }, EvidenceSource.INCIDENT_CLASSIFIER, "system")
    
    # Verify modification attempts fail
    with pytest.raises(ImmutabilityViolation):
        modify_evidence_entry(evidence.id, {"classification": "minor"})
    
    # Verify original evidence unchanged
    retrieved = get_evidence_entry(evidence.id)
    assert retrieved.evidence_data["classification"] == "major"

def test_audit_trail_completeness():
    """Every action must leave complete audit trail."""
    # Perform evidence operations
    evidence_ref = append_evidence_entry({
        "action": "obligation_mapped",
        "mapping_id": "MAP-123"
    }, EvidenceSource.OBLIGATION_MAPPER, "compliance-officer@company.com")
    
    # Export audit trail
    audit_export = export_audit_trail(
        datetime.utcnow() - timedelta(hours=1),
        datetime.utcnow(),
        "auditor@regulatory-body.gov"
    )
    
    # Verify completeness
    assert len(audit_export.entries) >= 1
    assert any(entry.evidence_ref == evidence_ref.id for entry in audit_export.entries)
    assert all(entry.actor is not None for entry in audit_export.entries)
    assert all(entry.timestamp is not None for entry in audit_export.entries)
```

## 🎯 PERFORMANCE REQUIREMENTS

**Evidence Append:** <100ms per entry with hash verification
**Chain Verification:** <5 seconds for 10,000 entries  
**Audit Trail Export:** <30 seconds for 1-year period
**Integrity Check:** <10 seconds for complete ledger

## 📋 FILE STRUCTURE (MANDATORY)

```
evidence/
├── claude.md           # This file
├── core.py            # Pure hash chain + verification logic
├── shell.py           # Database operations + export generation
├── contracts.py       # EvidenceEntry, AuditTrailEntry, ChainVerificationResult types
├── events.py          # EvidenceAdded, ChainIntegrityViolation, AuditTrailExported events
├── ledger.py          # Hash chain management
└── tests/
    ├── test_core.py   # Hash calculation, chain verification
    └── test_shell.py  # Database integration, export functionality
```

## 🔗 INTEGRATION POINTS

**DEPENDS ON:**
- PostgreSQL - Evidence storage with JSONB support
- Azure Key Vault - Digital signature keys
- Certificate authority - Evidence signing certificates

**EMITS EVENTS:**
- `EvidenceAdded(entry_id, evidence_type, chain_position, integrity_verified)`
- `ChainIntegrityViolation(broken_at_sequence, expected_hash, actual_hash)`
- `AuditTrailExported(requester, start_date, end_date, entries_count)`

**CONSUMED BY:**
- All compliance modules - Must record evidence for all actions
- Regulatory reporting - Uses evidence for compliance reports
- External auditors - Access through audit trail exports

## 📜 REGULATORY COMPLIANCE FEATURES

**GDPR Article 30 (Records of Processing):**
```python
def export_gdpr_processing_record() -> ProcessingRecord:
    """Export processing activities record for GDPR compliance."""
    return ProcessingRecord(
        controller="Company Name",
        purposes=["Regulatory compliance", "Incident management"],
        categories_of_data=["Regulatory change data", "Review decisions"],
        retention_periods=RETENTION_RULES,
        security_measures=["Hash chain integrity", "Digital signatures"]
    )
```

**DORA Article 19 (ICT Risk Documentation):**
```python
def export_dora_evidence_documentation() -> DORAEvidenceExport:
    """Export evidence supporting DORA compliance."""
    return DORAEvidenceExport(
        risk_assessments=get_evidence_by_type(EvidenceType.RISK_ASSESSMENT),
        control_implementations=get_evidence_by_type(EvidenceType.CONTROL_UPDATE),
        incident_responses=get_evidence_by_type(EvidenceType.INCIDENT_RESPONSE),
        testing_results=get_evidence_by_type(EvidenceType.TESTING_EVIDENCE)
    )
```

**Weekly Integrity Verification:**
```python
async def weekly_ledger_verification() -> LedgerIntegrityReport:
    """Weekly verification job for evidence ledger integrity."""
    all_evidence = await get_all_evidence_entries()
    verification_result = verify_hash_chain(all_evidence)
    
    if not verification_result.valid:
        await alert_integrity_violation(verification_result)
    
    return LedgerIntegrityReport(
        total_entries=len(all_evidence),
        chain_integrity=verification_result.valid,
        last_verified=datetime.utcnow(),
        next_verification=datetime.utcnow() + timedelta(days=7)
    )
```

**SUCCESS CRITERIA:**
- [ ] Hash chain integrity maintained across all operations
- [ ] All compliance actions recorded with evidence
- [ ] Audit trail export works for regulatory review
- [ ] Weekly integrity verification passes
- [ ] Evidence entries truly immutable after creation