# claude.md - Regulatory Snapshot Service

YOU ARE implementing **immutable content snapshots** with integrity verification and citation preservation.

## 🎯 MODULE PURPOSE
Create tamper-proof snapshots of regulatory sources for evidence preservation. Store in Azure Blob Storage with integrity hashes. Prevent citation drift and link rot in regulatory compliance.

## 🚨 SECURITY CRITICAL - NEVER VIOLATE

**YOU MUST ALWAYS:**
- Create immutable snapshots with SHA-256 integrity hashes
- Store original content without modification or translation
- Verify snapshot integrity before storage and retrieval
- Maintain audit trail of all snapshot operations
- Preserve exact source metadata (timestamp, URL, headers)

**YOU MUST NEVER:**
- Modify content during snapshot creation
- Skip integrity hash verification
- Allow mutable snapshot updates after creation
- Store snapshots without source attribution
- Delete snapshots without proper authorization audit

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def calculate_content_hash(
    content: bytes,
    url: str,
    timestamp: datetime
) -> str:
    """Calculate SHA-256 hash for content integrity. MUST be deterministic."""

def build_snapshot_metadata(
    url: str,
    content_hash: str,
    capture_timestamp: datetime,
    http_headers: dict[str, str]
) -> SnapshotMetadata:
    """Build snapshot metadata. MUST be pure."""

def verify_snapshot_integrity(
    stored_content: bytes,
    expected_hash: str
) -> IntegrityResult:
    """Verify snapshot hasn't been tampered. MUST be pure."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def create_immutable_snapshot(
    source_url: str,
    content: str,
    capture_metadata: dict
) -> SnapshotReference:
    """Create tamper-proof snapshot in Azure blob storage."""

async def retrieve_snapshot(
    snapshot_id: str,
    verify_integrity: bool = True
) -> SnapshotContent:
    """Retrieve and verify snapshot integrity."""
```

## 🔐 SNAPSHOT INTEGRITY

**Hash Calculation:**
```python
def calculate_snapshot_hash(content: bytes, metadata: SnapshotMetadata) -> str:
    """
    SHA-256 of: content + url + timestamp + content-type
    Ensures uniqueness and tamper detection.
    """
    hash_input = (
        content + 
        metadata.source_url.encode() +
        metadata.capture_timestamp.isoformat().encode() +
        metadata.content_type.encode()
    )
    return hashlib.sha256(hash_input).hexdigest()
```

**Verification Chain:**
```python
def verify_snapshot_chain(snapshots: list[SnapshotReference]) -> ChainVerification:
    """Verify integrity of entire snapshot chain."""
    for snapshot in snapshots:
        if not verify_individual_snapshot(snapshot):
            return ChainVerification(valid=False, broken_at=snapshot.id)
    return ChainVerification(valid=True)
```

## 💾 AZURE BLOB INTEGRATION

**Blob Storage Structure:**
```
regulatory-snapshots/
├── 2024/
│   ├── 03/
│   │   ├── nbb-circular-123-20240315T143000Z.html
│   │   └── fsma-news-456-20240315T143000Z.pdf
│   └── metadata/
│       ├── nbb-circular-123-metadata.json
│       └── fsma-news-456-metadata.json
└── integrity/
    └── weekly-verification-20240318.json
```

**Blob Properties:**
```python
BLOB_PROPERTIES = {
    "content_type": "application/octet-stream",  # Original type preserved in metadata
    "cache_control": "immutable",
    "access_tier": "Cool",  # Cost optimization for archival
    "immutability_policy": {
        "period_days": 2555,  # 7 years regulatory retention
        "policy_mode": "locked"
    }
}
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST:**
- Snapshot immutability enforcement
- Integrity hash calculation consistency
- Content preservation without modification
- Metadata completeness and accuracy
- Retrieval with integrity verification

**SNAPSHOT SCENARIOS:**
```python
def test_snapshot_immutability():
    """Snapshots must be truly immutable after creation."""
    original_content = "Original regulatory content"
    snapshot = create_immutable_snapshot("https://nbb.be/test", original_content)
    
    # Verify content cannot be modified
    retrieved = retrieve_snapshot(snapshot.id)
    assert retrieved.content == original_content
    assert retrieved.integrity_verified == True
    
    # Verify modification attempts fail
    with pytest.raises(ImmutabilityViolation):
        modify_snapshot(snapshot.id, "Modified content")

def test_integrity_verification():
    """Integrity verification must detect tampering."""
    content = b"Regulatory document content"
    expected_hash = calculate_content_hash(content, "https://test.url", datetime.utcnow())
    
    # Valid content should pass
    assert verify_snapshot_integrity(content, expected_hash).valid == True
    
    # Tampered content should fail
    tampered_content = b"Tampered regulatory content"
    assert verify_snapshot_integrity(tampered_content, expected_hash).valid == False

def test_metadata_preservation():
    """All source metadata must be preserved exactly."""
    metadata = {
        "url": "https://fsma.be/circular-123",
        "content_type": "application/pdf",
        "server": "nginx/1.18.0",
        "last_modified": "Wed, 15 Mar 2024 14:30:00 GMT"
    }
    
    snapshot = create_immutable_snapshot("https://fsma.be/circular-123", "content", metadata)
    retrieved_metadata = get_snapshot_metadata(snapshot.id)
    
    assert retrieved_metadata.source_url == metadata["url"]
    assert retrieved_metadata.content_type == metadata["content_type"]
    assert retrieved_metadata.http_headers["server"] == metadata["server"]
    assert retrieved_metadata.http_headers["last-modified"] == metadata["last_modified"]
```

## 🎯 PERFORMANCE REQUIREMENTS

**Snapshot Creation:** <10 seconds per regulatory document
**Integrity Verification:** <2 seconds per snapshot
**Blob Upload:** <30 seconds for documents up to 10MB
**Retrieval:** <5 seconds for snapshot access

## 📋 FILE STRUCTURE (MANDATORY)

```
regulatory/snapshot/
├── claude.md           # This file
├── core.py            # Pure hash calculation + integrity verification
├── shell.py           # Azure blob operations + snapshot management
├── contracts.py       # SnapshotReference, SnapshotMetadata, IntegrityResult types
├── events.py          # SnapshotCreated, IntegrityViolation, SnapshotRetrieved events
└── tests/
    ├── test_core.py   # Hash calculation, integrity verification
    └── test_shell.py  # Azure blob integration, snapshot lifecycle
```

## 🔗 INTEGRATION POINTS

**DEPENDS ON:**
- Azure Blob Storage - Immutable content storage
- Azure Key Vault - Snapshot encryption keys
- PostgreSQL - Snapshot reference tracking
- `regulatory/monitor/` - Triggered by content changes

**EMITS EVENTS:**
- `SnapshotCreated(url, snapshot_id, content_hash, storage_location)`
- `IntegrityViolationDetected(snapshot_id, expected_hash, actual_hash)`
- `SnapshotRetrieved(snapshot_id, requester, integrity_verified)`

**CONSUMED BY:**
- `regulatory/digest/` - Links to snapshot references
- `evidence/` - Evidence preservation chain
- `compliance/reviews/` - Regulatory source citations

## 🛡️ RETENTION & COMPLIANCE

**Retention Policy:**
```python
RETENTION_RULES = {
    "tier_a_sources": timedelta(days=2555),  # 7 years for critical regulatory sources
    "tier_b_sources": timedelta(days=1825),  # 5 years for informational sources  
    "incident_evidence": timedelta(days=3650), # 10 years for incident documentation
}
```

**Weekly Integrity Verification:**
```python
async def weekly_integrity_check() -> IntegrityReport:
    """Verify all snapshots maintain integrity."""
    report = IntegrityReport()
    
    for snapshot_ref in get_all_snapshots():
        verification = await verify_snapshot_integrity_async(snapshot_ref)
        if not verification.valid:
            report.add_violation(snapshot_ref, verification.error)
            await alert_integrity_violation(snapshot_ref)
    
    return report
```

**SUCCESS CRITERIA:**
- [ ] All snapshots immutable with integrity hashes
- [ ] Content preserved exactly without modification
- [ ] Weekly integrity verification passes for all snapshots
- [ ] Retrieval works with integrity verification
- [ ] Retention policies correctly enforced