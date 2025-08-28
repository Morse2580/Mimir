"""
Tests for Compliance Reviews Shell Module

Integration tests for I/O operations, database interactions,
event publishing, and audit trail persistence.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from ..shell import ReviewWorkflowService
from ..contracts import (
    ReviewRequest, ReviewDecision, ReviewStatus, ReviewPriority,
    Reviewer, AuditAction, ChainVerificationResult
)
from ..events import (
    ReviewRequested, ReviewAssigned, ReviewStarted, DecisionRecorded,
    MappingMarkedStale, ReviewSLABreached, ChainIntegrityVerified
)


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture 
def mock_event_publisher():
    """Mock event publisher."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    return publisher


@pytest.fixture
def mock_notification_service():
    """Mock notification service."""
    return AsyncMock()


@pytest.fixture
def review_service(mock_db_session, mock_event_publisher, mock_notification_service):
    """Create review workflow service with mocked dependencies."""
    return ReviewWorkflowService(
        db_session=mock_db_session,
        event_publisher=mock_event_publisher,
        notification_service=mock_notification_service
    )


@pytest.fixture
def sample_reviewer():
    """Sample reviewer for testing."""
    return Reviewer(
        id="lawyer_001",
        email="lawyer@company.com",
        role="Senior Legal Counsel",
        certifications=("DORA", "NIS2", "GDPR"),
        workload_capacity=5
    )


@pytest.fixture
def sample_mapping():
    """Sample mapping data for testing."""
    return {
        "mapping_id": "map_123",
        "obligation_id": "DORA_ART_18", 
        "control_id": "C001",
        "mapping_rationale": "DORA Article 18 requires incident reporting procedures",
        "evidence_urls": [
            "https://snapshots.blob.core.windows.net/regulatory/fsma_dora_guidance_2024.pdf",
            "https://snapshots.blob.core.windows.net/regulatory/nbb_technical_standards_2024.pdf"
        ],
        "confidence_score": 0.95
    }


class TestSubmitForReview:
    """Test review submission with audit trail creation."""
    
    @pytest.mark.asyncio
    async def test_submit_for_review_success(
        self, 
        review_service, 
        mock_event_publisher,
        sample_mapping
    ):
        """Test successful review submission."""
        
        # Mock dependencies
        review_service._get_mapping = AsyncMock(return_value=sample_mapping)
        review_service._store_review_request = AsyncMock()
        review_service._append_audit_entry = AsyncMock()
        review_service._attempt_auto_assignment = AsyncMock()
        
        # Submit review
        request = await review_service.submit_for_review(
            mapping_id="map_123",
            priority=ReviewPriority.HIGH,
            rationale="Requires legal review for DORA compliance",
            evidence_urls=(
                "https://snapshots.blob.core.windows.net/regulatory/fsma_dora_guidance_2024.pdf",
            ),
            submitted_by="compliance-officer@company.com"
        )
        
        # Verify request created
        assert request.mapping_id == "map_123"
        assert request.priority == ReviewPriority.HIGH
        assert request.submitted_by == "compliance-officer@company.com"
        assert len(request.id) > 0
        
        # Verify storage calls
        review_service._store_review_request.assert_called_once_with(request)
        review_service._append_audit_entry.assert_called_once()
        
        # Verify event published
        mock_event_publisher.publish.assert_called_once()
        published_event = mock_event_publisher.publish.call_args[0][0]
        assert isinstance(published_event, ReviewRequested)
        assert published_event.request_id == request.id
    
    @pytest.mark.asyncio
    async def test_submit_for_review_mapping_not_found(self, review_service):
        """Test review submission when mapping doesn't exist."""
        
        # Mock mapping not found
        review_service._get_mapping = AsyncMock(return_value=None)
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Mapping map_nonexistent not found"):
            await review_service.submit_for_review(
                mapping_id="map_nonexistent",
                priority=ReviewPriority.NORMAL,
                rationale="Test",
                evidence_urls=(),
                submitted_by="user@company.com"
            )


class TestAssignReviewer:
    """Test reviewer assignment with capacity validation."""
    
    @pytest.mark.asyncio
    async def test_assign_reviewer_success(
        self,
        review_service,
        mock_event_publisher,
        sample_reviewer
    ):
        """Test successful reviewer assignment."""
        
        # Create sample request
        request = ReviewRequest.create(
            mapping_id="map_123",
            mapping_version_hash="hash123",
            priority=ReviewPriority.HIGH,
            submitted_by="user@company.com",
            evidence_urls=("https://example.com/doc1",),
            rationale="Test review"
        )
        
        # Mock dependencies
        review_service._get_review_request = AsyncMock(return_value=request)
        review_service._get_reviewer = AsyncMock(return_value=sample_reviewer)
        review_service._get_reviewer_workload = AsyncMock(return_value=2)
        review_service._update_assignment = AsyncMock()
        review_service._append_audit_entry = AsyncMock()
        review_service._notify_reviewer_assigned = AsyncMock()
        
        # Assign reviewer
        success = await review_service.assign_reviewer(
            request_id=request.id,
            reviewer_id="lawyer_001",
            assigned_by="admin@company.com"
        )
        
        assert success
        
        # Verify assignment updated
        review_service._update_assignment.assert_called_once_with(
            request.id, "lawyer_001", "admin@company.com"
        )
        
        # Verify audit trail created
        review_service._append_audit_entry.assert_called_once()
        
        # Verify event published
        mock_event_publisher.publish.assert_called_once()
        published_event = mock_event_publisher.publish.call_args[0][0]
        assert isinstance(published_event, ReviewAssigned)
        assert published_event.reviewer_id == "lawyer_001"
    
    @pytest.mark.asyncio
    async def test_assign_reviewer_at_capacity(
        self,
        review_service,
        sample_reviewer
    ):
        """Test reviewer assignment when at capacity."""
        
        request = ReviewRequest.create(
            mapping_id="map_123",
            mapping_version_hash="hash123",
            priority=ReviewPriority.HIGH,
            submitted_by="user@company.com",
            evidence_urls=("https://example.com/doc1",),
            rationale="Test review"
        )
        
        # Mock reviewer at capacity
        review_service._get_review_request = AsyncMock(return_value=request)
        review_service._get_reviewer = AsyncMock(return_value=sample_reviewer)
        review_service._get_reviewer_workload = AsyncMock(return_value=5)  # At capacity
        
        # Assignment should fail
        success = await review_service.assign_reviewer(
            request_id=request.id,
            reviewer_id="lawyer_001",
            assigned_by="admin@company.com"
        )
        
        assert not success


class TestRecordDecision:
    """Test decision recording with immutable audit trail."""
    
    @pytest.mark.asyncio
    async def test_record_decision_approved(
        self,
        review_service,
        mock_event_publisher,
        sample_reviewer,
        sample_mapping
    ):
        """Test recording approved decision."""
        
        # Create sample request
        submitted_at = datetime.utcnow() - timedelta(hours=2)
        request = ReviewRequest(
            id="req_123",
            mapping_id="map_123",
            mapping_version_hash="hash123",
            priority=ReviewPriority.HIGH,
            submitted_at=submitted_at,
            submitted_by="user@company.com",
            evidence_urls=("https://example.com/doc1",),
            rationale="Test review"
        )
        
        # Mock dependencies
        review_service._get_review_request = AsyncMock(return_value=request)
        review_service._get_current_status = AsyncMock(return_value=ReviewStatus.IN_REVIEW)
        review_service._get_mapping = AsyncMock(return_value=sample_mapping)
        review_service._store_review_decision = AsyncMock()
        review_service._update_review_status = AsyncMock()
        review_service._append_audit_entry = AsyncMock(return_value=MagicMock(id="audit_123"))
        review_service._notify_decision_recorded = AsyncMock()
        
        # Record decision
        decision = await review_service.record_decision(
            request_id="req_123",
            reviewer=sample_reviewer,
            decision=ReviewStatus.APPROVED,
            comments="Mapping accurately reflects DORA requirements",
            evidence_checked=("https://example.com/doc1",)
        )
        
        # Verify decision details
        assert decision.request_id == "req_123"
        assert decision.decision == ReviewStatus.APPROVED
        assert decision.reviewer_id == sample_reviewer.id
        assert decision.review_duration_minutes == 120  # 2 hours
        assert decision.version_verified is True
        
        # Verify storage calls
        review_service._store_review_decision.assert_called_once_with(decision)
        review_service._update_review_status.assert_called_once_with("req_123", ReviewStatus.APPROVED)
        
        # Verify event published
        mock_event_publisher.publish.assert_called_once()
        published_event = mock_event_publisher.publish.call_args[0][0]
        assert isinstance(published_event, DecisionRecorded)
        assert published_event.decision == ReviewStatus.APPROVED
    
    @pytest.mark.asyncio 
    async def test_record_decision_mapping_stale(
        self,
        review_service,
        sample_reviewer,
        sample_mapping
    ):
        """Test decision recording when mapping has become stale."""
        
        request = ReviewRequest(
            id="req_123",
            mapping_id="map_123", 
            mapping_version_hash="old_hash",  # Different from current
            priority=ReviewPriority.HIGH,
            submitted_at=datetime.utcnow() - timedelta(hours=1),
            submitted_by="user@company.com",
            evidence_urls=("https://example.com/doc1",),
            rationale="Test review"
        )
        
        # Mock stale mapping (hash won't match)
        review_service._get_review_request = AsyncMock(return_value=request)
        review_service._get_current_status = AsyncMock(return_value=ReviewStatus.IN_REVIEW)
        review_service._get_mapping = AsyncMock(return_value=sample_mapping)  # Will have different hash
        review_service._mark_mapping_stale = AsyncMock()
        
        # Should raise ValueError for stale mapping
        with pytest.raises(ValueError, match="Mapping has changed since review started"):
            await review_service.record_decision(
                request_id="req_123",
                reviewer=sample_reviewer,
                decision=ReviewStatus.APPROVED,
                comments="Test",
                evidence_checked=()
            )
        
        # Verify stale marking called
        review_service._mark_mapping_stale.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_record_decision_invalid_transition(
        self,
        review_service,
        sample_reviewer
    ):
        """Test decision recording with invalid state transition."""
        
        request = ReviewRequest(
            id="req_123",
            mapping_id="map_123",
            mapping_version_hash="hash123",
            priority=ReviewPriority.HIGH,
            submitted_at=datetime.utcnow(),
            submitted_by="user@company.com", 
            evidence_urls=(),
            rationale="Test"
        )
        
        # Mock invalid current state
        review_service._get_review_request = AsyncMock(return_value=request)
        review_service._get_current_status = AsyncMock(return_value=ReviewStatus.APPROVED)  # Terminal state
        
        # Should raise ValueError for invalid transition
        with pytest.raises(ValueError, match="Invalid status transition"):
            await review_service.record_decision(
                request_id="req_123",
                reviewer=sample_reviewer,
                decision=ReviewStatus.REJECTED,  # Cannot transition from APPROVED
                comments="Test",
                evidence_checked=()
            )


class TestSLABreachDetection:
    """Test SLA breach detection and event emission."""
    
    @pytest.mark.asyncio
    async def test_check_sla_breaches(
        self,
        review_service,
        mock_event_publisher
    ):
        """Test SLA breach detection."""
        
        # Create overdue request
        overdue_time = datetime.utcnow() - timedelta(hours=6)  # 6 hours ago
        overdue_request = ReviewRequest(
            id="req_overdue", 
            mapping_id="map_123",
            mapping_version_hash="hash123",
            priority=ReviewPriority.URGENT,  # 4 hour SLA
            submitted_at=overdue_time,
            submitted_by="user@company.com",
            evidence_urls=(),
            rationale="Urgent review"
        )
        
        # Mock active reviews with one overdue
        review_service._get_active_reviews = AsyncMock(return_value=[
            (overdue_request, "lawyer_001")
        ])
        review_service._get_current_status = AsyncMock(return_value=ReviewStatus.IN_REVIEW)
        
        # Check for breaches
        breached_events = await review_service.check_sla_breaches()
        
        assert len(breached_events) == 1
        breach_event = breached_events[0]
        assert isinstance(breach_event, ReviewSLABreached)
        assert breach_event.request_id == "req_overdue"
        assert breach_event.priority == ReviewPriority.URGENT
        assert breach_event.hours_overdue > 2.0  # Should be ~2 hours overdue
        
        # Verify event published
        mock_event_publisher.publish.assert_called_once()


class TestAuditChainVerification:
    """Test audit trail integrity verification."""
    
    @pytest.mark.asyncio
    async def test_verify_audit_chain_integrity_valid(
        self,
        review_service,
        mock_event_publisher
    ):
        """Test audit chain verification with valid chain."""
        
        # Mock valid audit entries
        from ..contracts import AuditTrailEntry, AuditAction
        
        entry1 = AuditTrailEntry.create(
            action_type=AuditAction.REVIEW_SUBMITTED,
            actor="user@company.com",
            evidence_ref="req_1",
            context_data={"chain_hash": "valid_hash_1", "previous_hash": ""}
        )
        
        entry2 = AuditTrailEntry.create(
            action_type=AuditAction.REVIEW_ASSIGNED,
            actor="admin@company.com",
            evidence_ref="req_1",
            context_data={"chain_hash": "valid_hash_2", "previous_hash": "valid_hash_1"}
        )
        
        review_service._get_all_audit_entries = AsyncMock(return_value=[entry1, entry2])
        
        # Mock verification logic to return valid result
        with patch('backend.app.compliance.reviews.shell.verify_hash_chain') as mock_verify:
            mock_verify.return_value = ChainVerificationResult(
                valid=True,
                total_entries=2,
                verified_entries=2
            )
            
            # Verify chain integrity
            result = await review_service.verify_audit_chain_integrity()
            
            assert result.valid
            assert result.total_entries == 2
            assert result.verified_entries == 2
        
        # Verify integrity event published
        mock_event_publisher.publish.assert_called_once()
        published_event = mock_event_publisher.publish.call_args[0][0]
        assert isinstance(published_event, ChainIntegrityVerified)
        assert published_event.hash_chain_valid is True
    
    @pytest.mark.asyncio
    async def test_verify_audit_chain_integrity_broken(
        self,
        review_service,
        mock_event_publisher
    ):
        """Test audit chain verification with broken chain."""
        
        review_service._get_all_audit_entries = AsyncMock(return_value=[])
        
        # Mock verification to return broken chain
        with patch('backend.app.compliance.reviews.shell.verify_hash_chain') as mock_verify:
            mock_verify.return_value = ChainVerificationResult(
                valid=False,
                total_entries=2,
                verified_entries=1,
                broken_at_sequence=1,
                expected_hash="expected_hash",
                actual_hash="wrong_hash"
            )
            
            # Verify chain integrity
            result = await review_service.verify_audit_chain_integrity()
            
            assert not result.valid
            assert result.broken_at_sequence == 1
        
        # Should publish both integrity event and violation event
        assert mock_event_publisher.publish.call_count == 2


class TestAuditTrailExport:
    """Test audit trail export for regulatory compliance."""
    
    @pytest.mark.asyncio
    async def test_export_audit_trail(
        self,
        review_service
    ):
        """Test complete audit trail export."""
        
        start_date = datetime(2024, 3, 1)
        end_date = datetime(2024, 3, 31)
        
        # Mock dependencies
        review_service._get_audit_entries_by_date = AsyncMock(return_value=[])
        review_service._get_reviews_by_date = AsyncMock(return_value=[])
        review_service._get_reviewer_activity_stats = AsyncMock(return_value={
            "lawyer_001": {
                "reviews_completed": 5,
                "avg_duration_hours": 2.5,
                "approval_rate": 0.8
            }
        })
        review_service._store_audit_export = AsyncMock()
        
        # Export audit trail
        report = await review_service.export_audit_trail(
            start_date=start_date,
            end_date=end_date,
            requester="auditor@regulatory-body.gov"
        )
        
        # Verify report structure
        assert report.generated_by == "auditor@regulatory-body.gov"
        assert report.date_range == (start_date, end_date)
        assert len(report.report_id) > 0
        assert "lawyer_001" in report.reviewers_activity
        
        # Verify export stored
        review_service._store_audit_export.assert_called_once_with(report, [])


class TestPrivateHelperMethods:
    """Test private helper methods with mocked database operations."""
    
    @pytest.mark.asyncio
    async def test_mark_mapping_stale(
        self,
        review_service,
        mock_event_publisher,
        sample_mapping
    ):
        """Test marking mapping as stale."""
        
        request = ReviewRequest.create(
            mapping_id="map_123",
            mapping_version_hash="old_hash",
            priority=ReviewPriority.HIGH,
            submitted_by="user@company.com",
            evidence_urls=(),
            rationale="Test"
        )
        
        # Mock dependencies
        review_service._update_review_status = AsyncMock()
        review_service._append_audit_entry = AsyncMock()
        
        # Mark as stale
        await review_service._mark_mapping_stale(request, sample_mapping)
        
        # Verify status updated
        review_service._update_review_status.assert_called_once_with(
            request.id, ReviewStatus.STALE
        )
        
        # Verify audit entry created
        review_service._append_audit_entry.assert_called_once()
        
        # Verify event published
        mock_event_publisher.publish.assert_called_once()
        published_event = mock_event_publisher.publish.call_args[0][0]
        assert isinstance(published_event, MappingMarkedStale)
        assert published_event.request_id == request.id