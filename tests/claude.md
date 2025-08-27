# claude.md - Testing Strategy

YOU ARE implementing **audit-grade tests** that prove regulatory compliance and catch common RegOps pitfalls.

## 🚨 TESTING CRITICAL - NEVER SKIP

**GOLDEN TESTS (MANDATORY):**
- All 32 DST clock scenarios must pass
- 3 NBB XSD official test vectors must validate
- 5 PII injection attack vectors must be blocked
- Evidence ledger integrity check must pass
- Circuit breaker recovery must be functional

**YOU MUST TEST:**
- Same input → same output (deterministic behavior)
- All state transitions (incident state machine)
- Multilingual sources (≥1 NL, ≥1 FR in digest)
- Degraded modes (circuit open, but system functional)

## 🛡️ PITFALLS AS TESTS

### 1. PII Leakage to Parallel
```python
def test_pii_injection_blocked():
    """All 5 attack vectors must be blocked."""
    vectors = [
        "Contact support@company.com",  # Direct email
        "Email: john dot doe at company dot com",  # Obfuscated  
        {"incident": "User ID 12345 affected"},  # Context injection
        "Phone: +32 2 123 4567",  # Phone number
        base64.encode("hidden@email.com")  # Encoded data
    ]
    for vector in vectors:
        with pytest.raises(PIIBoundaryViolation):
            assert_parallel_safe({"query": vector})
```

### 2. Wrong Clock Anchor / DST Bugs
```python
@pytest.mark.parametrize(
    "anchor_time,expected_initial_deadline,dst_scenario",
    [
        # Spring forward (lose 1 hour): March 31, 2024 at 1:30 AM
        (datetime(2024, 3, 31, 1, 30, tzinfo=tz_brussels), 
         datetime(2024, 3, 31, 5, 30, tzinfo=timezone.utc), "spring_forward"),
        
        # Fall back (gain 1 hour): October 27, 2024 at 2:30 AM  
        (datetime(2024, 10, 27, 2, 30, tzinfo=tz_brussels),
         datetime(2024, 10, 27, 6, 30, tzinfo=timezone.utc), "fall_back"),
         
        # Cross-midnight weekend
        (datetime(2024, 3, 30, 23, 30, tzinfo=tz_brussels),
         datetime(2024, 3, 31, 3, 30, tzinfo=timezone.utc), "weekend_midnight")
    ]
)
def test_dst_clock_matrix(anchor_time, expected_initial_deadline, dst_scenario):
    """All 32 DST scenarios must work correctly."""
    deadlines = calculate_deadlines(anchor_time, Severity.MAJOR)
    assert deadlines.initial_utc == expected_initial_deadline
    assert dst_scenario in deadlines.dst_transitions_handled
```

### 3. Over-reliance on LLM for Severity  
```python
def test_deterministic_classification():
    """Same input MUST produce same output with rule traceability."""
    incident = IncidentInput(
        clients_affected=5000,
        downtime_minutes=120,
        services_critical=("payment", "trading")
    )
    
    result1 = classify_incident(incident)
    result2 = classify_incident(incident)
    
    assert result1 == result2  # Deterministic
    assert result1.severity == Severity.MAJOR
    assert "mass_impact" in result1.criteria_matched  # Rule trace
    assert result1.confidence == 1.0  # Not probabilistic
```

### 4. Tier-B Treated as Binding
```python
def test_tier_policy_enforcement():
    """Only Tier-A sources can be actionable."""
    tier_b_item = RegulatoryItem(
        source="blog.compliance.eu", 
        tier=SourceTier.TIER_B,
        required_action=RequiredAction.UPDATE_CONTROL
    )
    
    with pytest.raises(TierPolicyViolation):
        digest_builder.mark_as_actionable(tier_b_item)
```

### 5. Link Rot & Citation Drift
```python
def test_snapshot_integrity():
    """Citations must be preserved with checksums."""
    url = "https://www.fsma.be/en/circular-123"
    snapshot = await snapshot_service.preserve_source(url)
    
    assert snapshot.sha256 is not None
    assert snapshot.immutable == True
    assert snapshot.timestamp <= datetime.utcnow()
    
    # Verify weekly drift detection
    report = await snapshot_verifier.verify_all_snapshots()
    assert len(report.failed) == 0  # No broken links
```

### 6. OneGate Schema Drift
```python
def test_nbb_xsd_validation():
    """Official NBB test vectors must validate."""
    vectors = ["major.xml", "significant.xml", "no_report.xml"]
    
    for vector_file in vectors:
        xml_content = load_test_vector(vector_file)
        assert validate_against_nbb_xsd(xml_content) == True
        
    # Verify checksum integrity
    assert verify_xsd_checksum() == True
```

### 7. Budget Blow-outs
```python
def test_cost_kill_switch():
    """95% budget threshold must trigger kill switch."""
    # Set current spend to €1,400 (93.3% of €1,500 cap)
    set_current_spend(1400.0)
    
    # €50 call would exceed 95% threshold (€1,425)
    assert should_activate_kill_switch(1400.0, 50.0, 1500.0, 95.0) == True
    
    # €20 call stays under threshold  
    assert should_activate_kill_switch(1400.0, 20.0, 1500.0, 95.0) == False
```

### 8. Webhook Security Gaps
```python
def test_webhook_security():
    """HMAC verification + replay protection required."""
    payload = {"event": "task_completed", "data": {}}
    timestamp = datetime.utcnow().isoformat()
    nonce = "test_nonce_123"
    
    # Valid signature should pass
    valid_signature = calculate_hmac(payload, timestamp, nonce, SECRET)
    assert validate_webhook(payload, valid_signature, timestamp, nonce) == True
    
    # Replay attempt should fail  
    assert validate_webhook(payload, valid_signature, timestamp, nonce) == False
```

### 9. Multilingual Blind Spots
```python
def test_multilingual_coverage():
    """Digest must include NL/FR sources, not just EN."""
    digest = generate_weekly_digest()
    
    languages = {item.language for item in digest.entries}
    assert Language.DUTCH in languages
    assert Language.FRENCH in languages  
    assert len([item for item in digest.entries if item.tier == SourceTier.TIER_A]) >= 5
```

### 10. Lawyer-reviewed Without Audit Trail
```python  
def test_review_audit_trail():
    """Every review must have who/when/version tracking."""
    mapping = create_test_mapping()
    review = submit_for_review(mapping.id, ReviewPriority.HIGH)
    
    decision = record_review_decision(
        review.id, 
        test_reviewer,
        ReviewStatus.APPROVED,
        "Mapping accurate per DORA Article 18",
        ["https://evidence.url"]
    )
    
    assert decision.reviewer_email == "lawyer@company.com"
    assert decision.mapping_version_hash is not None
    assert decision.review_duration_minutes > 0
```

### 11. Schema Bloat in Task Specs
```python
def test_task_schema_limits():
    """Task schemas must stay within practical limits."""
    oversized_schema = {f"field_{i}": "string" for i in range(15)}  # >8 fields
    
    with pytest.raises(TaskSchemaError):
        validate_task_schema(oversized_schema)
        
    # Large request should be rejected
    huge_request = {"query": "x" * 20000}  # >15K chars
    with pytest.raises(TaskSchemaError):
        validate_task_request(huge_request)
```

### 12. Fallbacks That Don't Actually Fallback
```python
def test_degraded_mode_functionality():
    """Circuit open should still deliver degraded value."""
    # Simulate Parallel.ai outage
    with mock_circuit_open():
        digest = generate_weekly_digest()
        
        assert digest.fallback_mode == True
        assert len(digest.entries) > 0  # Still has RSS content
        assert digest.degraded_notice.startswith("Limited functionality")
        
        # Manual upload should still work
        manual_item = upload_manual_evidence("https://nbb.be/circular")
        assert manual_item.snapshot_url is not None
```

## 🎯 ACCEPTANCE TEST REQUIREMENTS

**System-Level Tests:**
- End-to-end incident flow: create → classify → export → validate XML
- Regulatory monitoring: scan → extract → snapshot → digest
- Review workflow: submit → review → approve → export audit log
- Cost tracking: accumulate → threshold → kill switch → recovery

**Performance Tests:**  
- OneGate export p95 < 30 minutes
- PII detection < 50ms per request
- Cost check < 10ms per request
- Digest generation < 5 minutes

**Security Tests:**
- All PII injection vectors blocked
- Webhook replay attacks prevented  
- HMAC signature validation functional
- Circuit breaker state tampering prevented

**Evidence Tests:**
- Ledger integrity maintained across operations
- Snapshots immutable and verifiable
- Citation links preserved and accessible
- Review audit trail exportable

This testing strategy ensures the platform survives real pilot deployments and regulatory scrutiny.