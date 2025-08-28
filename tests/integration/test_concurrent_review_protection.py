"""
Concurrent Review Protection Tests

This module tests protection against concurrent review scenarios where
two or more lawyers attempt to review the same obligation mapping simultaneously.
These tests ensure data integrity and audit trail consistency.
"""

import pytest
import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch
from concurrent.futures import ThreadPoolExecutor
import threading

from backend.app.compliance.reviews.contracts import (
    ObligationMapping,
    ReviewRequest,
    ReviewStatus,
    ReviewPriority,
    ReviewDecision,
    ReviewLockError,
    ConcurrentReviewError,
)


class MockReviewService:
    """Mock review service with locking mechanism."""
    
    def __init__(self):
        self.review_locks: Dict[str, Dict[str, Any]] = {}
        self.reviews: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
    
    async def acquire_review_lock(self, mapping_id: str, reviewer_email: str) -> Dict[str, Any]:
        """Acquire exclusive lock for review."""
        with self.lock:
            if mapping_id in self.review_locks:
                existing_lock = self.review_locks[mapping_id]
                if existing_lock["reviewer_email"] != reviewer_email:
                    raise ReviewLockError(
                        f"Mapping {mapping_id} already locked by {existing_lock['reviewer_email']}"
                    )
                # Extend existing lock
                existing_lock["expires_at"] = datetime.now(timezone.utc).timestamp() + 1800  # 30 min
                return existing_lock
            
            # Create new lock
            lock_data = {
                "mapping_id": mapping_id,
                "reviewer_email": reviewer_email,
                "locked_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc).timestamp() + 1800,  # 30 minutes
                "lock_id": str(uuid.uuid4())
            }
            self.review_locks[mapping_id] = lock_data
            return lock_data
    
    async def release_review_lock(self, mapping_id: str, reviewer_email: str) -> bool:
        """Release review lock."""
        with self.lock:
            if mapping_id not in self.review_locks:
                return False
            
            lock_data = self.review_locks[mapping_id]
            if lock_data["reviewer_email"] != reviewer_email:
                raise ReviewLockError(f"Lock owned by different reviewer")
            
            del self.review_locks[mapping_id]
            return True
    
    async def submit_review_decision(
        self, 
        mapping_id: str, 
        reviewer_email: str, 
        decision: ReviewStatus,
        comments: str = "",
        lock_id: str = None
    ) -> ReviewDecision:
        """Submit review decision with lock validation."""
        with self.lock:
            # Verify lock ownership
            if mapping_id not in self.review_locks:
                raise ConcurrentReviewError(f"No active lock for mapping {mapping_id}")
            
            lock_data = self.review_locks[mapping_id]
            if lock_data["reviewer_email"] != reviewer_email:
                raise ConcurrentReviewError(f"Review locked by different user")
            
            if lock_id and lock_data["lock_id"] != lock_id:
                raise ConcurrentReviewError(f"Invalid lock ID")
            
            # Check lock expiration
            if time.time() > lock_data["expires_at"]:
                del self.review_locks[mapping_id]
                raise ConcurrentReviewError(f"Review lock expired")
            
            # Create review decision
            review_decision = ReviewDecision(
                review_id=str(uuid.uuid4()),
                mapping_id=mapping_id,
                reviewer_email=reviewer_email,
                status=decision,
                review_comments=comments,
                reviewed_at=datetime.now(timezone.utc),
                lock_id=lock_data["lock_id"],
                review_duration_minutes=int((time.time() - lock_data["locked_at"].timestamp()) / 60)
            )
            
            # Store decision and release lock
            self.reviews[mapping_id] = review_decision
            del self.review_locks[mapping_id]
            
            return review_decision
    
    async def get_active_locks(self) -> List[Dict[str, Any]]:
        """Get all active review locks."""
        with self.lock:
            current_time = time.time()
            active_locks = []
            expired_locks = []
            
            for mapping_id, lock_data in self.review_locks.items():
                if current_time <= lock_data["expires_at"]:
                    active_locks.append(lock_data)
                else:
                    expired_locks.append(mapping_id)
            
            # Clean up expired locks
            for mapping_id in expired_locks:
                del self.review_locks[mapping_id]
            
            return active_locks


class TestConcurrentReviewProtection:
    """Test concurrent review protection mechanisms."""
    
    @pytest.fixture
    def review_service(self):
        """Create mock review service."""
        return MockReviewService()
    
    @pytest.fixture
    def sample_mapping(self):
        """Create sample obligation mapping."""
        return ObligationMapping(
            mapping_id="MAP-2024-CONCURRENT-001",
            incident_id="INC-2024-001",
            obligation_text="DORA Article 19 - incident notification requirements",
            regulatory_source="EU Regulation 2022/2554",
            tier="TIER_A",
            confidence_score=0.9,
            supporting_evidence=["https://eur-lex.europa.eu/eli/reg/2022/2554/oj"]
        )
    
    @pytest.mark.asyncio
    async def test_basic_review_lock_acquisition(self, review_service, sample_mapping):
        """Test basic review lock acquisition and release."""
        reviewer_email = "lawyer1@company.com"
        
        # Acquire lock
        lock_data = await review_service.acquire_review_lock(
            sample_mapping.mapping_id, reviewer_email
        )
        
        assert lock_data["mapping_id"] == sample_mapping.mapping_id
        assert lock_data["reviewer_email"] == reviewer_email
        assert lock_data["lock_id"] is not None
        assert isinstance(lock_data["locked_at"], datetime)
        
        # Verify lock is active
        active_locks = await review_service.get_active_locks()
        assert len(active_locks) == 1
        assert active_locks[0]["mapping_id"] == sample_mapping.mapping_id
        
        # Release lock
        released = await review_service.release_review_lock(
            sample_mapping.mapping_id, reviewer_email
        )
        
        assert released is True
        
        # Verify lock is released
        active_locks = await review_service.get_active_locks()
        assert len(active_locks) == 0
        
        print("✅ Basic review lock acquisition and release works correctly")
    
    @pytest.mark.asyncio
    async def test_concurrent_lock_acquisition_blocked(self, review_service, sample_mapping):
        """Test that second reviewer cannot acquire lock while first holds it."""
        reviewer1 = "lawyer1@company.com"
        reviewer2 = "lawyer2@company.com"
        
        # First reviewer acquires lock
        lock1 = await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer1)
        assert lock1["reviewer_email"] == reviewer1
        
        # Second reviewer attempts to acquire lock - should fail
        with pytest.raises(ReviewLockError) as exc_info:
            await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer2)
        
        assert f"already locked by {reviewer1}" in str(exc_info.value)
        
        # Verify only one active lock
        active_locks = await review_service.get_active_locks()
        assert len(active_locks) == 1
        assert active_locks[0]["reviewer_email"] == reviewer1
        
        print("✅ Concurrent lock acquisition properly blocked")
    
    @pytest.mark.asyncio
    async def test_lock_extension_for_same_reviewer(self, review_service, sample_mapping):
        """Test that same reviewer can extend their existing lock."""
        reviewer_email = "lawyer1@company.com"
        
        # Acquire initial lock
        lock1 = await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer_email)
        initial_expires_at = lock1["expires_at"]
        
        # Wait a moment
        await asyncio.sleep(0.1)
        
        # Same reviewer "re-acquires" lock (should extend)
        lock2 = await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer_email)
        
        assert lock2["reviewer_email"] == reviewer_email
        assert lock2["lock_id"] == lock1["lock_id"]  # Same lock
        assert lock2["expires_at"] > initial_expires_at  # Extended
        
        print("✅ Lock extension for same reviewer works correctly")
    
    @pytest.mark.asyncio
    async def test_concurrent_review_decision_submission(self, review_service, sample_mapping):
        """Test protection against concurrent review decision submission."""
        reviewer1 = "lawyer1@company.com"
        reviewer2 = "lawyer2@company.com"
        
        # Reviewer 1 acquires lock and starts review
        lock1 = await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer1)
        
        # Simulate reviewer 2 somehow bypassing UI and attempting direct submission
        with pytest.raises(ConcurrentReviewError) as exc_info:
            await review_service.submit_review_decision(
                sample_mapping.mapping_id,
                reviewer2,  # Different reviewer
                ReviewStatus.APPROVED,
                "Unauthorized attempt"
            )
        
        assert "Review locked by different user" in str(exc_info.value)
        
        # Verify no review decision was created
        assert sample_mapping.mapping_id not in review_service.reviews
        
        # Legitimate reviewer can submit
        decision = await review_service.submit_review_decision(
            sample_mapping.mapping_id,
            reviewer1,
            ReviewStatus.APPROVED,
            "Approved after thorough review",
            lock_id=lock1["lock_id"]
        )
        
        assert decision.reviewer_email == reviewer1
        assert decision.status == ReviewStatus.APPROVED
        assert decision.lock_id == lock1["lock_id"]
        
        print("✅ Concurrent review decision submission properly protected")
    
    @pytest.mark.asyncio
    async def test_expired_lock_cleanup_and_reacquisition(self, review_service, sample_mapping):
        """Test that expired locks are cleaned up and can be reacquired."""
        reviewer1 = "lawyer1@company.com"
        reviewer2 = "lawyer2@company.com"
        
        # Acquire lock with short expiration (modify for testing)
        lock1 = await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer1)
        
        # Manually expire the lock for testing
        review_service.review_locks[sample_mapping.mapping_id]["expires_at"] = time.time() - 1
        
        # Attempt to use expired lock - should fail
        with pytest.raises(ConcurrentReviewError) as exc_info:
            await review_service.submit_review_decision(
                sample_mapping.mapping_id,
                reviewer1,
                ReviewStatus.APPROVED,
                "Using expired lock"
            )
        
        assert "Review lock expired" in str(exc_info.value)
        
        # Different reviewer should now be able to acquire lock
        lock2 = await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer2)
        assert lock2["reviewer_email"] == reviewer2
        assert lock2["lock_id"] != lock1["lock_id"]
        
        print("✅ Expired lock cleanup and reacquisition works correctly")
    
    @pytest.mark.asyncio
    async def test_high_concurrency_lock_acquisition(self, review_service, sample_mapping):
        """Test lock acquisition under high concurrency."""
        num_reviewers = 10
        reviewers = [f"lawyer{i}@company.com" for i in range(num_reviewers)]
        
        results = []
        errors = []
        
        async def attempt_lock_acquisition(reviewer_email: str):
            """Attempt to acquire lock for a reviewer."""
            try:
                lock = await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer_email)
                results.append((reviewer_email, lock))
                # Hold lock briefly
                await asyncio.sleep(0.01)
                # Release lock
                await review_service.release_review_lock(sample_mapping.mapping_id, reviewer_email)
            except ReviewLockError as e:
                errors.append((reviewer_email, str(e)))
        
        # Start all reviewers simultaneously
        tasks = [attempt_lock_acquisition(reviewer) for reviewer in reviewers]
        await asyncio.gather(*tasks)
        
        # Verify exactly one reviewer succeeded, others failed with lock errors
        assert len(results) == 1, f"Expected 1 successful lock, got {len(results)}"
        assert len(errors) == num_reviewers - 1, f"Expected {num_reviewers - 1} failures, got {len(errors)}"
        
        # Verify all errors are about existing locks
        for reviewer_email, error_msg in errors:
            assert "already locked by" in error_msg
        
        # Verify no active locks remain
        active_locks = await review_service.get_active_locks()
        assert len(active_locks) == 0
        
        print(f"✅ High concurrency test passed: 1 success, {len(errors)} properly blocked")
    
    @pytest.mark.asyncio
    async def test_review_workflow_with_lock_validation(self, review_service, sample_mapping):
        """Test complete review workflow with proper lock validation."""
        reviewer_email = "legal.expert@company.com"
        
        # Step 1: Submit for review (creates reviewable item)
        review_request = ReviewRequest(
            mapping_id=sample_mapping.mapping_id,
            submitted_by="system@company.com",
            priority=ReviewPriority.HIGH,
            review_notes="Critical DORA mapping requires legal validation"
        )
        
        # Step 2: Reviewer acquires lock
        lock_data = await review_service.acquire_review_lock(
            sample_mapping.mapping_id, reviewer_email
        )
        
        # Step 3: Reviewer performs review (simulate review time)
        review_start = time.time()
        await asyncio.sleep(0.1)  # Simulate review process
        
        # Step 4: Reviewer submits decision with valid lock
        decision = await review_service.submit_review_decision(
            mapping_id=sample_mapping.mapping_id,
            reviewer_email=reviewer_email,
            decision=ReviewStatus.APPROVED,
            comments="Mapping correctly identifies DORA Article 19 requirements. "
                    "Supporting evidence is comprehensive and regulatory references are accurate.",
            lock_id=lock_data["lock_id"]
        )
        
        # Verify decision properties
        assert decision.mapping_id == sample_mapping.mapping_id
        assert decision.reviewer_email == reviewer_email
        assert decision.status == ReviewStatus.APPROVED
        assert decision.lock_id == lock_data["lock_id"]
        assert decision.review_duration_minutes >= 0
        assert len(decision.review_comments) > 0
        
        # Verify lock was automatically released
        active_locks = await review_service.get_active_locks()
        assert len(active_locks) == 0
        
        # Verify decision is stored
        assert sample_mapping.mapping_id in review_service.reviews
        stored_decision = review_service.reviews[sample_mapping.mapping_id]
        assert stored_decision.reviewer_email == reviewer_email
        
        print("✅ Complete review workflow with lock validation successful")
    
    @pytest.mark.asyncio
    async def test_audit_trail_integrity_under_concurrency(self, review_service):
        """Test that audit trail remains intact under concurrent access."""
        mappings = [
            f"MAP-2024-AUDIT-{i:03d}" for i in range(5)
        ]
        reviewers = [
            "senior.lawyer@company.com",
            "junior.lawyer@company.com", 
            "external.counsel@lawfirm.com"
        ]
        
        completed_reviews = []
        
        async def review_mapping(mapping_id: str, reviewer_email: str, decision: ReviewStatus):
            """Complete review process for a mapping."""
            try:
                # Acquire lock
                lock = await review_service.acquire_review_lock(mapping_id, reviewer_email)
                
                # Simulate review work
                await asyncio.sleep(0.01)
                
                # Submit decision
                review_decision = await review_service.submit_review_decision(
                    mapping_id=mapping_id,
                    reviewer_email=reviewer_email,
                    decision=decision,
                    comments=f"Review completed by {reviewer_email}",
                    lock_id=lock["lock_id"]
                )
                
                completed_reviews.append(review_decision)
                
            except (ReviewLockError, ConcurrentReviewError) as e:
                # Some reviewers may fail due to concurrency - this is expected
                pass
        
        # Create concurrent review tasks
        tasks = []
        for mapping_id in mappings:
            for reviewer in reviewers:
                decision = ReviewStatus.APPROVED if "senior" in reviewer else ReviewStatus.NEEDS_REVISION
                task = review_mapping(mapping_id, reviewer, decision)
                tasks.append(task)
        
        # Execute all tasks concurrently
        await asyncio.gather(*tasks)
        
        # Verify audit trail integrity
        assert len(completed_reviews) == len(mappings), \
            f"Expected {len(mappings)} completed reviews, got {len(completed_reviews)}"
        
        # Verify each mapping was reviewed exactly once
        reviewed_mappings = {review.mapping_id for review in completed_reviews}
        assert len(reviewed_mappings) == len(mappings)
        
        # Verify all reviews have complete audit information
        for review in completed_reviews:
            assert review.reviewer_email is not None
            assert review.reviewed_at is not None
            assert review.lock_id is not None
            assert review.review_duration_minutes >= 0
            assert len(review.review_comments) > 0
        
        # Verify no active locks remain
        active_locks = await review_service.get_active_locks()
        assert len(active_locks) == 0
        
        print(f"✅ Audit trail integrity maintained under concurrency: {len(completed_reviews)} reviews completed")
    
    @pytest.mark.asyncio
    async def test_invalid_lock_id_rejection(self, review_service, sample_mapping):
        """Test that submissions with invalid lock IDs are rejected."""
        reviewer_email = "lawyer@company.com"
        
        # Acquire legitimate lock
        lock = await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer_email)
        
        # Attempt submission with wrong lock ID
        with pytest.raises(ConcurrentReviewError) as exc_info:
            await review_service.submit_review_decision(
                mapping_id=sample_mapping.mapping_id,
                reviewer_email=reviewer_email,
                decision=ReviewStatus.APPROVED,
                comments="Trying with wrong lock ID",
                lock_id="invalid-lock-id-12345"
            )
        
        assert "Invalid lock ID" in str(exc_info.value)
        
        # Verify no decision was stored
        assert sample_mapping.mapping_id not in review_service.reviews
        
        # Verify lock is still active
        active_locks = await review_service.get_active_locks()
        assert len(active_locks) == 1
        assert active_locks[0]["lock_id"] == lock["lock_id"]
        
        print("✅ Invalid lock ID properly rejected")
    
    @pytest.mark.asyncio
    async def test_lock_timeout_configuration(self, review_service, sample_mapping):
        """Test that lock timeout is properly configurable and enforced."""
        reviewer_email = "lawyer@company.com"
        
        # Acquire lock (30-minute default timeout)
        lock = await review_service.acquire_review_lock(sample_mapping.mapping_id, reviewer_email)
        
        # Verify timeout is approximately 30 minutes (1800 seconds)
        current_time = time.time()
        timeout_duration = lock["expires_at"] - current_time
        
        assert 1790 <= timeout_duration <= 1810, \
            f"Lock timeout should be ~1800s, got {timeout_duration}s"
        
        # Verify lock is currently active
        active_locks = await review_service.get_active_locks()
        assert len(active_locks) == 1
        
        print(f"✅ Lock timeout properly configured: {timeout_duration:.0f} seconds")


class TestConcurrentReviewPerformance:
    """Test performance under concurrent review scenarios."""
    
    @pytest.mark.asyncio
    async def test_lock_acquisition_performance(self):
        """Test lock acquisition performance under load."""
        review_service = MockReviewService()
        num_operations = 100
        
        start_time = time.time()
        
        # Sequential lock acquisitions and releases
        for i in range(num_operations):
            mapping_id = f"MAP-PERF-{i:03d}"
            reviewer = "performance.tester@company.com"
            
            lock = await review_service.acquire_review_lock(mapping_id, reviewer)
            await review_service.release_review_lock(mapping_id, reviewer)
        
        total_time = time.time() - start_time
        avg_time_per_operation = (total_time / num_operations) * 1000  # milliseconds
        
        # Performance requirement: <10ms per lock operation
        assert avg_time_per_operation < 10, \
            f"Lock operations took {avg_time_per_operation:.1f}ms/op (limit: 10ms)"
        
        print(f"✅ Lock acquisition performance: {avg_time_per_operation:.1f}ms per operation")
    
    @pytest.mark.asyncio
    async def test_concurrent_lock_contention_performance(self):
        """Test performance under high lock contention."""
        review_service = MockReviewService()
        mapping_id = "MAP-CONTENTION-001"
        num_contestants = 50
        
        successful_acquisitions = []
        failed_acquisitions = []
        
        async def contend_for_lock(contestant_id: int):
            """Contestant attempting to acquire lock."""
            reviewer = f"contestant{contestant_id}@company.com"
            start_time = time.time()
            
            try:
                lock = await review_service.acquire_review_lock(mapping_id, reviewer)
                acquisition_time = (time.time() - start_time) * 1000
                successful_acquisitions.append(acquisition_time)
                
                # Hold briefly then release
                await asyncio.sleep(0.001)
                await review_service.release_review_lock(mapping_id, reviewer)
                
            except ReviewLockError:
                failure_time = (time.time() - start_time) * 1000
                failed_acquisitions.append(failure_time)
        
        # Start all contestants simultaneously
        start_time = time.time()
        tasks = [contend_for_lock(i) for i in range(num_contestants)]
        await asyncio.gather(*tasks)
        total_time = (time.time() - start_time) * 1000
        
        # Verify exactly one success
        assert len(successful_acquisitions) == 1
        assert len(failed_acquisitions) == num_contestants - 1
        
        # Performance requirements
        assert total_time < 1000, f"Contention resolution took {total_time:.1f}ms (limit: 1000ms)"
        assert successful_acquisitions[0] < 100, f"Successful acquisition took {successful_acquisitions[0]:.1f}ms (limit: 100ms)"
        
        avg_failure_time = sum(failed_acquisitions) / len(failed_acquisitions)
        assert avg_failure_time < 50, f"Average failure detection took {avg_failure_time:.1f}ms (limit: 50ms)"
        
        print(f"✅ Lock contention performance: {total_time:.1f}ms total, "
              f"{successful_acquisitions[0]:.1f}ms success, {avg_failure_time:.1f}ms avg failure")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])