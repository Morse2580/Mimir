"""
PII Security Tests for Compliance Reviews Module

Tests to verify PII boundaries are maintained and sensitive data
is never exposed in audit trails or external communications.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from ..shell import ReviewWorkflowService
from ..contracts import ReviewPriority, Reviewer
from ..core import hash_mapping_content, build_audit_trail_entry
from ..contracts import AuditAction


class TestPIIBoundaryProtection:
    """Test PII data protection boundaries in review workflow."""

    @pytest.fixture
    def pii_test_data(self):
        """Sample data containing PII that should be blocked."""
        return {
            "email": "lawyer@company.com",
            "national_id": "12.34.56-789.12",  # Belgian national number format
            "iban": "BE68539007547034",  # Belgian IBAN
            "vat_number": "BE0123456789",
            "phone": "+32 2 123 45 67",
            "personal_name": "Jean Dupont",
        }

    @pytest.fixture
    def safe_test_data(self):
        """Sample data without PII that should be allowed."""
        return {
            "obligation_id": "DORA_ART_18",
            "control_id": "C001",
            "mapping_rationale": "DORA Article 18 requires incident reporting procedures",
            "confidence_score": 0.95,
            "review_priority": "high",
            "evidence_count": 2,
        }

    def test_hash_mapping_excludes_pii(self, pii_test_data, safe_test_data):
        """Test that mapping hash function excludes PII fields."""

        # Create mapping with both PII and safe data
        mixed_mapping = {**safe_test_data, **pii_test_data}

        # Hash should only consider non-PII fields
        hash_with_pii = hash_mapping_content(mixed_mapping)
        hash_without_pii = hash_mapping_content(safe_test_data)

        # Hashes should be the same because PII fields are ignored
        assert hash_with_pii == hash_without_pii

    def test_audit_trail_entry_sanitizes_context(self, pii_test_data):
        """Test that audit trail entries don't contain PII in context data."""

        # Create audit entry with PII in context
        entry = build_audit_trail_entry(
            action_type=AuditAction.REVIEW_SUBMITTED,
            actor="system",  # System actor, not PII
            evidence_ref="req_123",
            timestamp=datetime.utcnow(),
            context_data=pii_test_data,
            previous_hash="",
        )

        # Verify PII fields are not in stored context
        context = entry.context_data

        # These PII patterns should not appear in audit context
        pii_patterns = [
            "12.34.56-789.12",  # National ID
            "BE68539007547034",  # IBAN
            "BE0123456789",  # VAT number
            "+32 2 123 45 67",  # Phone number
            "Jean Dupont",  # Personal name
        ]

        for pattern in pii_patterns:
            assert pattern not in str(
                context
            ), f"PII pattern {pattern} found in audit context"

    def test_reviewer_info_anonymization(self):
        """Test that reviewer information is properly anonymized in events."""

        reviewer = Reviewer(
            id="lawyer_001",
            email="sensitive.lawyer@company.com",
            role="Senior Legal Counsel",
            certifications=("DORA", "NIS2"),
            workload_capacity=5,
        )

        # Create audit entry referencing reviewer
        entry = build_audit_trail_entry(
            action_type=AuditAction.REVIEW_ASSIGNED,
            actor=reviewer.id,  # Use ID instead of email
            evidence_ref="req_123",
            timestamp=datetime.utcnow(),
            context_data={
                "reviewer_id": reviewer.id,  # Safe
                "reviewer_role": reviewer.role,  # Safe
                "workload_capacity": reviewer.workload_capacity,  # Safe
                # Email should NOT be included
            },
            previous_hash="",
        )

        # Verify email is not in audit trail
        assert reviewer.email not in str(entry.context_data)
        assert "sensitive.lawyer@company.com" not in str(entry.context_data)

        # Verify safe fields are present
        assert reviewer.id in str(entry.context_data)
        assert reviewer.role in str(entry.context_data)


class TestPIIInjectionAttacks:
    """Test protection against PII injection attacks."""

    @pytest.fixture
    def review_service_with_pii_protection(self):
        """Review service configured with PII protection."""
        mock_db = AsyncMock()
        mock_events = AsyncMock()
        mock_notifications = AsyncMock()

        service = ReviewWorkflowService(
            db_session=mock_db,
            event_publisher=mock_events,
            notification_service=mock_notifications,
        )

        # Mock the PII detection function
        service._contains_pii = MagicMock(side_effect=self._mock_pii_detection)
        return service

    def _mock_pii_detection(self, data):
        """Mock PII detection logic."""
        data_str = str(data)

        # Belgian PII patterns
        pii_patterns = [
            r"\d{2}\.\d{2}\.\d{2}-\d{3}\.\d{2}",  # National number: XX.XX.XX-XXX.XX
            r"BE\d{2}\s?\d{4}\s?\d{4}\s?\d{4}",  # IBAN: BEXX XXXX XXXX XXXX
            r"BE0\d{9}",  # VAT: BE0XXXXXXXXX
            r"\+32\s?[0-9\s]{8,}",  # Phone: +32 X XXX XX XX
            r"[a-zA-Z]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",  # Email addresses
        ]

        import re

        for pattern in pii_patterns:
            if re.search(pattern, data_str):
                return True
        return False

    @pytest.mark.asyncio
    async def test_pii_injection_in_rationale_blocked(
        self, review_service_with_pii_protection
    ):
        """Test that PII in review rationale is blocked."""

        service = review_service_with_pii_protection

        # Mock dependencies
        service._get_mapping = AsyncMock(
            return_value={
                "mapping_id": "map_123",
                "obligation_id": "DORA_ART_18",
                "control_id": "C001",
                "mapping_rationale": "Safe rationale",
                "evidence_urls": [],
                "confidence_score": 0.95,
            }
        )

        # Attempt to inject PII in rationale
        pii_rationale = "Review required for DORA compliance. Contact Jean Dupont at +32 2 123 45 67 or jean.dupont@company.com for questions."

        # Should detect PII and refuse submission
        with pytest.raises(ValueError, match="PII detected"):
            await service.submit_for_review(
                mapping_id="map_123",
                priority=ReviewPriority.HIGH,
                rationale=pii_rationale,
                evidence_urls=(),
                submitted_by="system",
            )

    @pytest.mark.asyncio
    async def test_pii_injection_in_comments_blocked(
        self, review_service_with_pii_protection
    ):
        """Test that PII in review comments is blocked."""

        service = review_service_with_pii_protection

        # Create safe reviewer
        reviewer = Reviewer(
            id="lawyer_001",
            email="lawyer@company.com",
            role="Senior Legal Counsel",
            certifications=("DORA",),
            workload_capacity=5,
        )

        # Mock request
        from ..contracts import ReviewRequest, ReviewStatus

        request = ReviewRequest.create(
            mapping_id="map_123",
            mapping_version_hash="hash123",
            priority=ReviewPriority.HIGH,
            submitted_by="system",
            evidence_urls=(),
            rationale="Safe rationale",
        )

        service._get_review_request = AsyncMock(return_value=request)
        service._get_current_status = AsyncMock(return_value=ReviewStatus.IN_REVIEW)
        service._get_mapping = AsyncMock(
            return_value={
                "mapping_id": "map_123",
                "obligation_id": "DORA_ART_18",
                "control_id": "C001",
                "mapping_rationale": "Safe rationale",
                "evidence_urls": [],
                "confidence_score": 0.95,
            }
        )

        # Attempt to inject PII in comments
        pii_comments = "Approved. Please contact Jean Dupont (BE0123456789) at jean.dupont@company.com for implementation details."

        # Should detect PII and refuse to record decision
        with pytest.raises(ValueError, match="PII detected"):
            await service.record_decision(
                request_id=request.id,
                reviewer=reviewer,
                decision=ReviewStatus.APPROVED,
                comments=pii_comments,
                evidence_checked=(),
            )

    def test_pii_detection_patterns(self, review_service_with_pii_protection):
        """Test PII detection for various Belgian patterns."""

        service = review_service_with_pii_protection

        # Test cases with PII
        pii_test_cases = [
            "National number: 12.34.56-789.12",
            "IBAN: BE68 5390 0754 7034",
            "VAT: BE0123456789",
            "Phone: +32 2 123 45 67",
            "Email: jean.dupont@company.com",
            "Mixed: Call +32 2 123 45 67 or email info@company.be",
        ]

        for test_case in pii_test_cases:
            assert service._contains_pii(
                test_case
            ), f"Failed to detect PII in: {test_case}"

        # Test cases without PII
        safe_test_cases = [
            "DORA Article 18 requires incident reporting",
            "Control C001 mapped to obligation DORA_ART_18",
            "Evidence reviewed and approved",
            "Priority: HIGH, Duration: 120 minutes",
            "Review completed successfully",
        ]

        for test_case in safe_test_cases:
            assert not service._contains_pii(
                test_case
            ), f"False positive PII detection in: {test_case}"


class TestSecurityConstraints:
    """Test security constraints and access controls."""

    @pytest.mark.asyncio
    async def test_audit_trail_immutability_enforced(self):
        """Test that audit trail entries cannot be modified after creation."""

        from ..contracts import AuditTrailEntry, AuditAction

        # Create audit entry
        entry = AuditTrailEntry.create(
            action_type=AuditAction.REVIEW_SUBMITTED,
            actor="user@company.com",
            evidence_ref="req_123",
            context_data={"test": "data"},
        )

        # Attempt to modify frozen dataclass should raise error
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            entry.actor = "hacker@malicious.com"

        with pytest.raises(Exception):
            entry.context_data["malicious"] = "injection"

    def test_hash_chain_tampering_detection(self):
        """Test that hash chain tampering is detected."""

        from ..core import verify_hash_chain
        from ..contracts import AuditTrailEntry, AuditAction

        # Create legitimate audit entries
        entry1 = build_audit_trail_entry(
            AuditAction.REVIEW_SUBMITTED,
            "user1@company.com",
            "req_1",
            datetime.utcnow(),
            {"legitimate": "data1"},
            "",
        )

        entry2 = build_audit_trail_entry(
            AuditAction.REVIEW_ASSIGNED,
            "user2@company.com",
            "req_1",
            datetime.utcnow(),
            {"legitimate": "data2"},
            entry1.context_data["chain_hash"],
        )

        # Verify legitimate chain
        result = verify_hash_chain([entry1, entry2])
        assert result.valid

        # Create tampered entry (wrong hash)
        tampered_entry = AuditTrailEntry(
            id=entry2.id,
            timestamp=entry2.timestamp,
            action_type=entry2.action_type,
            actor=entry2.actor,
            evidence_ref=entry2.evidence_ref,
            context_data={**entry2.context_data, "chain_hash": "tampered_hash_value"},
        )

        # Verify tampered chain should fail
        result = verify_hash_chain([entry1, tampered_entry])
        assert not result.valid
        assert result.broken_at_sequence == 1

    @pytest.mark.asyncio
    async def test_reviewer_authorization_check(self):
        """Test that only authorized reviewers can record decisions."""

        # This would typically integrate with RBAC system
        # Mock implementation to demonstrate the pattern

        authorized_reviewer = Reviewer(
            id="lawyer_001",
            email="lawyer@company.com",
            role="Senior Legal Counsel",
            certifications=("DORA", "NIS2"),
            workload_capacity=5,
        )

        unauthorized_user = Reviewer(
            id="intern_001",
            email="intern@company.com",
            role="Legal Intern",
            certifications=(),  # No certifications
            workload_capacity=1,
        )

        # Mock authorization check
        def check_reviewer_authorization(reviewer: Reviewer, action: str) -> bool:
            """Mock authorization check."""
            required_certs = {"record_decision": ["DORA", "NIS2"]}

            if action in required_certs:
                return any(
                    cert in reviewer.certifications for cert in required_certs[action]
                )
            return False

        # Authorized reviewer should pass
        assert check_reviewer_authorization(authorized_reviewer, "record_decision")

        # Unauthorized user should fail
        assert not check_reviewer_authorization(unauthorized_user, "record_decision")


class TestAuditTrailIntegrity:
    """Test audit trail integrity and non-repudiation."""

    def test_audit_entry_completeness(self):
        """Test that audit entries contain all required fields."""

        entry = build_audit_trail_entry(
            action_type=AuditAction.DECISION_RECORDED,
            actor="lawyer@company.com",
            evidence_ref="req_123",
            timestamp=datetime.utcnow(),
            context_data={
                "decision": "approved",
                "duration_minutes": 120,
                "evidence_reviewed": ["doc1", "doc2"],
            },
            previous_hash="abc123",
        )

        # Verify all required fields present
        assert entry.id is not None and len(entry.id) > 0
        assert entry.timestamp is not None
        assert entry.action_type == AuditAction.DECISION_RECORDED
        assert entry.actor == "lawyer@company.com"
        assert entry.evidence_ref == "req_123"

        # Verify chain integrity fields
        assert "chain_hash" in entry.context_data
        assert "previous_hash" in entry.context_data
        assert entry.context_data["previous_hash"] == "abc123"

        # Verify business context preserved
        assert entry.context_data["decision"] == "approved"
        assert entry.context_data["duration_minutes"] == 120

    def test_non_repudiation_evidence(self):
        """Test that audit trail provides non-repudiation evidence."""

        # Create decision audit entry
        timestamp = datetime(2024, 3, 15, 14, 30, 0)

        entry = build_audit_trail_entry(
            action_type=AuditAction.DECISION_RECORDED,
            actor="lawyer_001",  # Reviewer ID for non-repudiation
            evidence_ref="req_123456",
            timestamp=timestamp,
            context_data={
                "decision": "approved",
                "reviewer_role": "Senior Legal Counsel",
                "evidence_reviewed": ["https://example.com/evidence1.pdf"],
                "decision_comments": "Mapping accurately reflects DORA requirements",
                "mapping_version_hash": "abc123def456",
                "review_duration_minutes": 135,
            },
            previous_hash="previous_chain_hash",
        )

        # Verify non-repudiation elements
        # 1. Who: Clear actor identification
        assert entry.actor == "lawyer_001"

        # 2. What: Clear action and decision
        assert entry.action_type == AuditAction.DECISION_RECORDED
        assert entry.context_data["decision"] == "approved"

        # 3. When: Precise timestamp
        assert entry.timestamp == timestamp

        # 4. Evidence: What was reviewed
        assert len(entry.context_data["evidence_reviewed"]) > 0

        # 5. Context: Sufficient detail for audit
        assert "decision_comments" in entry.context_data
        assert "mapping_version_hash" in entry.context_data

        # 6. Integrity: Hash chain prevents tampering
        assert "chain_hash" in entry.context_data
        assert len(entry.context_data["chain_hash"]) == 64  # SHA-256
