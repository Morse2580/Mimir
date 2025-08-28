"""
Tests for Compliance Reviews Core Module

Tests all pure functions for version control, hash chain verification,
priority calculation, and audit trail integrity.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, List

from ..core import (
    hash_mapping_content, is_mapping_stale, calculate_review_duration,
    determine_review_priority, calculate_sla_deadline, is_sla_breached,
    can_transition_status, calculate_evidence_hash, verify_hash_chain,
    build_audit_trail_entry, validate_reviewer_capacity, calculate_review_metrics
)
from ..contracts import (
    ReviewStatus, ReviewPriority, AuditAction, AuditTrailEntry, Reviewer
)


class TestMappingVersionControl:
    """Test mapping version control and staleness detection."""
    
    def test_hash_mapping_content_deterministic(self):
        """Hash function must be deterministic for same content."""
        mapping = {
            "obligation_id": "DORA_ART_18",
            "control_id": "C001",
            "mapping_rationale": "Test rationale",
            "evidence_urls": ["https://example.com/doc1", "https://example.com/doc2"],
            "confidence_score": 0.95
        }
        
        hash1 = hash_mapping_content(mapping)
        hash2 = hash_mapping_content(mapping)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length
    
    def test_hash_mapping_content_order_independent(self):
        """Hash should be same regardless of evidence URL order."""
        mapping1 = {
            "obligation_id": "DORA_ART_18",
            "control_id": "C001", 
            "mapping_rationale": "Test rationale",
            "evidence_urls": ["https://example.com/doc1", "https://example.com/doc2"],
            "confidence_score": 0.95
        }
        
        mapping2 = {
            "obligation_id": "DORA_ART_18",
            "control_id": "C001",
            "mapping_rationale": "Test rationale", 
            "evidence_urls": ["https://example.com/doc2", "https://example.com/doc1"],
            "confidence_score": 0.95
        }
        
        assert hash_mapping_content(mapping1) == hash_mapping_content(mapping2)
    
    def test_hash_mapping_content_sensitive_to_changes(self):
        """Hash should change when content changes."""
        base_mapping = {
            "obligation_id": "DORA_ART_18",
            "control_id": "C001",
            "mapping_rationale": "Original rationale",
            "evidence_urls": ["https://example.com/doc1"],
            "confidence_score": 0.95
        }
        
        base_hash = hash_mapping_content(base_mapping)
        
        # Test changes to each field
        modified_rationale = {**base_mapping, "mapping_rationale": "Modified rationale"}
        assert hash_mapping_content(modified_rationale) != base_hash
        
        modified_urls = {**base_mapping, "evidence_urls": ["https://example.com/doc2"]}
        assert hash_mapping_content(modified_urls) != base_hash
        
        modified_score = {**base_mapping, "confidence_score": 0.85}
        assert hash_mapping_content(modified_score) != base_hash
    
    def test_is_mapping_stale_detection(self):
        """Test stale mapping detection."""
        original_mapping = {
            "obligation_id": "DORA_ART_18",
            "control_id": "C001",
            "mapping_rationale": "Original rationale",
            "evidence_urls": ["https://example.com/doc1"],
            "confidence_score": 0.95
        }
        
        original_hash = hash_mapping_content(original_mapping)
        
        # Same mapping should not be stale
        assert not is_mapping_stale(original_hash, original_mapping)
        
        # Modified mapping should be stale
        modified_mapping = {**original_mapping, "mapping_rationale": "Modified rationale"}
        assert is_mapping_stale(original_hash, modified_mapping)


class TestReviewTimingLogic:
    """Test review duration and SLA calculations."""
    
    def test_calculate_review_duration(self):
        """Test review duration calculation."""
        submitted = datetime(2024, 3, 15, 10, 0, 0)
        reviewed = datetime(2024, 3, 15, 14, 30, 0)  # 4.5 hours later
        
        duration = calculate_review_duration(submitted, reviewed)
        assert duration == 270  # 4.5 * 60 minutes
    
    def test_calculate_review_duration_negative_handled(self):
        """Duration should be 0 if reviewed_at is before submitted_at."""
        submitted = datetime(2024, 3, 15, 10, 0, 0)
        reviewed = datetime(2024, 3, 15, 9, 0, 0)  # Before submission
        
        duration = calculate_review_duration(submitted, reviewed)
        assert duration == 0
    
    def test_calculate_sla_deadline(self):
        """Test SLA deadline calculation for each priority."""
        submitted = datetime(2024, 3, 15, 10, 0, 0)
        
        # Test each priority level
        urgent_deadline = calculate_sla_deadline(submitted, ReviewPriority.URGENT)
        assert urgent_deadline == submitted + timedelta(hours=4)
        
        high_deadline = calculate_sla_deadline(submitted, ReviewPriority.HIGH) 
        assert high_deadline == submitted + timedelta(hours=24)
        
        normal_deadline = calculate_sla_deadline(submitted, ReviewPriority.NORMAL)
        assert normal_deadline == submitted + timedelta(hours=72)
        
        low_deadline = calculate_sla_deadline(submitted, ReviewPriority.LOW)
        assert low_deadline == submitted + timedelta(hours=168)  # 1 week
    
    def test_is_sla_breached(self):
        """Test SLA breach detection."""
        submitted = datetime(2024, 3, 15, 10, 0, 0)
        
        # Within SLA
        current_time = submitted + timedelta(hours=2)
        assert not is_sla_breached(submitted, ReviewPriority.URGENT, current_time)
        
        # Breached SLA 
        current_time = submitted + timedelta(hours=6)
        assert is_sla_breached(submitted, ReviewPriority.URGENT, current_time)


class TestPriorityDetermination:
    """Test automatic priority determination logic."""
    
    def test_determine_priority_critical_obligation(self):
        """Critical obligations should be urgent priority."""
        priority = determine_review_priority(
            obligation_severity="critical",
            regulatory_deadline=None,
            control_criticality="tier2"
        )
        assert priority == ReviewPriority.URGENT
    
    def test_determine_priority_deadline_driven(self):
        """Near deadlines should drive priority."""
        current_time = datetime(2024, 3, 15, 10, 0, 0)
        
        # Deadline in 24 hours - should be urgent
        deadline = current_time + timedelta(hours=24)
        priority = determine_review_priority(
            obligation_severity="medium",
            regulatory_deadline=deadline,
            control_criticality="tier3",
            current_time=current_time
        )
        assert priority == ReviewPriority.URGENT
        
        # Deadline in 5 days - should be high
        deadline = current_time + timedelta(days=5)
        priority = determine_review_priority(
            obligation_severity="low",
            regulatory_deadline=deadline, 
            control_criticality="tier3",
            current_time=current_time
        )
        assert priority == ReviewPriority.HIGH
    
    def test_determine_priority_by_severity_and_tier(self):
        """Test priority determination by severity and control tier."""
        # High severity should be high priority
        priority = determine_review_priority(
            obligation_severity="high",
            regulatory_deadline=None,
            control_criticality="tier3"
        )
        assert priority == ReviewPriority.HIGH
        
        # Tier1 control should be high priority
        priority = determine_review_priority(
            obligation_severity="low",
            regulatory_deadline=None,
            control_criticality="tier1"
        )
        assert priority == ReviewPriority.HIGH
        
        # Medium/tier2 should be normal
        priority = determine_review_priority(
            obligation_severity="medium",
            regulatory_deadline=None,
            control_criticality="tier2"
        )
        assert priority == ReviewPriority.NORMAL
        
        # Low/tier3 should be low
        priority = determine_review_priority(
            obligation_severity="low",
            regulatory_deadline=None,
            control_criticality="tier3"
        )
        assert priority == ReviewPriority.LOW


class TestStateMachineTransitions:
    """Test review status state machine transitions."""
    
    def test_valid_transitions(self):
        """Test all valid state transitions."""
        # PENDING -> IN_REVIEW
        assert can_transition_status(ReviewStatus.PENDING, ReviewStatus.IN_REVIEW)
        
        # IN_REVIEW -> terminal states
        assert can_transition_status(ReviewStatus.IN_REVIEW, ReviewStatus.APPROVED)
        assert can_transition_status(ReviewStatus.IN_REVIEW, ReviewStatus.REJECTED)
        assert can_transition_status(ReviewStatus.IN_REVIEW, ReviewStatus.NEEDS_REVISION)
        assert can_transition_status(ReviewStatus.IN_REVIEW, ReviewStatus.STALE)
        
        # Revision back to pending
        assert can_transition_status(ReviewStatus.NEEDS_REVISION, ReviewStatus.PENDING)
        
        # Stale back to pending
        assert can_transition_status(ReviewStatus.STALE, ReviewStatus.PENDING)
    
    def test_invalid_transitions(self):
        """Test invalid state transitions."""
        # Terminal states cannot transition
        assert not can_transition_status(ReviewStatus.APPROVED, ReviewStatus.IN_REVIEW)
        assert not can_transition_status(ReviewStatus.REJECTED, ReviewStatus.PENDING)
        
        # Cannot skip states
        assert not can_transition_status(ReviewStatus.PENDING, ReviewStatus.APPROVED)
        
        # Cannot go backwards inappropriately
        assert not can_transition_status(ReviewStatus.IN_REVIEW, ReviewStatus.PENDING)


class TestHashChainIntegrity:
    """Test audit trail hash chain verification."""
    
    def test_calculate_evidence_hash_deterministic(self):
        """Evidence hash must be deterministic."""
        evidence_data = {"action": "review_submitted", "reviewer": "lawyer@company.com"}
        previous_hash = "abc123"
        timestamp = datetime(2024, 3, 15, 10, 0, 0)
        actor = "system"
        
        hash1 = calculate_evidence_hash(evidence_data, previous_hash, timestamp, actor)
        hash2 = calculate_evidence_hash(evidence_data, previous_hash, timestamp, actor)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256
    
    def test_build_audit_trail_entry(self):
        """Test building audit trail entry with hash chain."""
        timestamp = datetime(2024, 3, 15, 10, 0, 0)
        
        entry = build_audit_trail_entry(
            action_type=AuditAction.REVIEW_SUBMITTED,
            actor="user@company.com",
            evidence_ref="req_123456",
            timestamp=timestamp,
            context_data={"mapping_id": "map_789"},
            previous_hash="abc123"
        )
        
        assert entry.action_type == AuditAction.REVIEW_SUBMITTED
        assert entry.actor == "user@company.com"
        assert entry.evidence_ref == "req_123456"
        assert "chain_hash" in entry.context_data
        assert "previous_hash" in entry.context_data
        assert entry.context_data["previous_hash"] == "abc123"
    
    def test_verify_hash_chain_valid(self):
        """Test hash chain verification for valid chain."""
        timestamp1 = datetime(2024, 3, 15, 10, 0, 0)
        timestamp2 = datetime(2024, 3, 15, 11, 0, 0)
        
        # Build chain of entries
        entry1 = build_audit_trail_entry(
            AuditAction.REVIEW_SUBMITTED,
            "user1@company.com",
            "req_1",
            timestamp1,
            {"test": "data1"},
            ""  # Genesis entry
        )
        
        entry2 = build_audit_trail_entry(
            AuditAction.REVIEW_ASSIGNED,
            "user2@company.com", 
            "req_1",
            timestamp2,
            {"test": "data2"},
            entry1.context_data["chain_hash"]
        )
        
        # Verify chain
        result = verify_hash_chain([entry1, entry2])
        
        assert result.valid
        assert result.total_entries == 2
        assert result.verified_entries == 2
        assert result.broken_at_sequence is None
    
    def test_verify_hash_chain_broken(self):
        """Test hash chain verification detects tampering."""
        timestamp = datetime(2024, 3, 15, 10, 0, 0)
        
        # Create entry with correct hash
        entry = build_audit_trail_entry(
            AuditAction.REVIEW_SUBMITTED,
            "user@company.com",
            "req_1",
            timestamp,
            {"test": "data"},
            ""
        )
        
        # Tamper with the stored hash
        tampered_entry = AuditTrailEntry(
            id=entry.id,
            timestamp=entry.timestamp,
            action_type=entry.action_type,
            actor=entry.actor,
            evidence_ref=entry.evidence_ref,
            context_data={**entry.context_data, "chain_hash": "tampered_hash"}
        )
        
        # Verify should detect tampering
        result = verify_hash_chain([tampered_entry])
        
        assert not result.valid
        assert result.broken_at_sequence == 0
        assert result.expected_hash != "tampered_hash"


class TestReviewerCapacityValidation:
    """Test reviewer capacity validation logic."""
    
    def test_validate_reviewer_capacity_available(self):
        """Test capacity validation when reviewer has availability."""
        reviewer = Reviewer(
            id="lawyer_001",
            email="lawyer@company.com",
            role="Senior Legal Counsel",
            certifications=("DORA", "NIS2"),
            workload_capacity=5
        )
        
        result = validate_reviewer_capacity(reviewer, current_workload=3)
        assert hasattr(result, 'value')  # Success result
    
    def test_validate_reviewer_capacity_at_limit(self):
        """Test capacity validation when reviewer is at capacity."""
        reviewer = Reviewer(
            id="lawyer_001",
            email="lawyer@company.com",
            role="Senior Legal Counsel",
            certifications=("DORA",),
            workload_capacity=5
        )
        
        result = validate_reviewer_capacity(reviewer, current_workload=5)
        assert hasattr(result, 'error')  # Failure result
        assert "at capacity" in result.error


class TestReviewMetricsCalculation:
    """Test review performance metrics calculation."""
    
    def test_calculate_review_metrics_empty(self):
        """Test metrics calculation with no reviews."""
        metrics = calculate_review_metrics([])
        
        assert metrics["total_reviews"] == 0
        assert metrics["completion_rate"] == 0.0
        assert metrics["avg_duration_minutes"] == 0.0
        assert metrics["sla_breach_rate"] == 0.0
    
    def test_calculate_review_metrics_with_data(self):
        """Test metrics calculation with sample data."""
        from ..contracts import ReviewRequest, ReviewDecision
        
        # Create sample requests and decisions
        base_time = datetime(2024, 3, 15, 10, 0, 0)
        
        request1 = ReviewRequest(
            id="req_1",
            mapping_id="map_1",
            mapping_version_hash="hash1",
            priority=ReviewPriority.HIGH,
            submitted_at=base_time,
            submitted_by="user@company.com",
            evidence_urls=("https://example.com/doc1",),
            rationale="Test rationale"
        )
        
        decision1 = ReviewDecision(
            request_id="req_1",
            reviewer_id="lawyer_1",
            reviewer_email="lawyer@company.com",
            reviewer_role="Senior Legal Counsel",
            decision=ReviewStatus.APPROVED,
            comments="Looks good",
            evidence_reviewed=("https://example.com/doc1",),
            reviewed_at=base_time + timedelta(hours=2),
            review_duration_minutes=120,
            version_verified=True
        )
        
        # One completed, one pending
        reviews = [
            (request1, decision1),
            (request1, None)  # Pending review
        ]
        
        metrics = calculate_review_metrics(reviews)
        
        assert metrics["total_reviews"] == 2
        assert metrics["completion_rate"] == 0.5
        assert metrics["avg_duration_minutes"] == 120.0
        assert "reviews_by_status" in metrics