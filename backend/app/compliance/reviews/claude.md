# claude.md - Compliance Reviews Module

## Module Purpose
**Lawyer review workflow** with immutable audit trails for obligation mappings. Ensures legal sign-off with full version control and prevents stale approvals.

## Core Contracts

```python
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib

class ReviewStatus(Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    STALE = "stale"  # Mapping changed since review started

class ReviewPriority(Enum):
    URGENT = "urgent"      # <4 hours response
    HIGH = "high"         # <24 hours response  
    NORMAL = "normal"     # <72 hours response
    LOW = "low"           # <1 week response

@dataclass(frozen=True)
class ReviewRequest:
    """Immutable review request."""
    id: str
    mapping_id: str
    mapping_version_hash: str
    priority: ReviewPriority
    submitted_at: datetime
    submitted_by: str
    evidence_urls: tuple[str, ...]
    rationale: str

@dataclass(frozen=True)
class ReviewDecision:
    """Immutable review decision."""
    request_id: str
    reviewer_id: str
    reviewer_email: str
    reviewer_role: str
    decision: ReviewStatus
    comments: str
    evidence_reviewed: tuple[str, ...]
    reviewed_at: datetime
    review_duration_minutes: int

class ReviewWorkflow(Protocol):
    """Core contract for review process."""
    
    def submit_for_review(
        self,
        mapping_id: str,
        priority: ReviewPriority,
        rationale: str
    ) -> ReviewRequest:
        """Submit mapping for lawyer review."""
        ...
        
    def record_decision(
        self,
        request_id: str,
        reviewer: Reviewer,
        decision: ReviewStatus,
        comments: str,
        evidence_checked: list[str]
    ) -> ReviewDecision:
        """Record review decision with audit trail."""
        ...
```

## Functional Core (Pure Logic)

### Version Control Logic
```python
def hash_mapping_content(mapping: Dict[str, Any]) -> str:
    """Pure function: create version hash for mapping."""
    content = {
        "obligation_id": mapping["obligation_id"],
        "control_id": mapping["control_id"],
        "mapping_rationale": mapping["mapping_rationale"],
        "evidence_urls": sorted(mapping["evidence_urls"]),
        "confidence_score": mapping["confidence_score"]
    }
    
    content_json = json.dumps(content, sort_keys=True)
    return hashlib.sha256(content_json.encode()).hexdigest()

def is_mapping_stale(
    original_hash: str,
    current_mapping: Dict[str, Any]
) -> bool:
    """Pure function: check if mapping changed since review started."""
    current_hash = hash_mapping_content(current_mapping)
    return original_hash != current_hash

def calculate_review_duration(
    submitted_at: datetime,
    reviewed_at: datetime
) -> int:
    """Pure function: calculate review time in minutes."""
    return int((reviewed_at - submitted_at).total_seconds() / 60)
```

### Priority Logic
```python
def determine_review_priority(
    obligation_severity: str,
    regulatory_deadline: Optional[datetime],
    control_criticality: str
) -> ReviewPriority:
    """Pure function: auto-determine review priority."""
    
def calculate_sla_deadline(
    submitted_at: datetime,
    priority: ReviewPriority
) -> datetime:
    """Pure function: calculate review SLA deadline."""
    
def is_sla_breached(
    submitted_at: datetime,
    priority: ReviewPriority,
    current_time: datetime
) -> bool:
    """Pure function: check if review SLA breached."""
```

## Imperative Shell (I/O Operations)

### Queue Management
- Assign reviews to available lawyers
- Load balancing by reviewer workload
- Priority queue with SLA tracking
- Notification scheduling

### Audit Trail Persistence
- Immutable review records
- Version history maintenance  
- Evidence URL preservation
- Reviewer activity logging

### Integration Points
- Email notifications to reviewers
- Teams/Slack integration for urgent reviews
- Calendar integration for deadlines
- Dashboard updates for status

### Export Functions
- Generate review audit reports
- Export for compliance audits
- Review performance analytics
- Legal team workload reports

## Review Process State Machine

```python
class ReviewStateMachine:
    """Manages review lifecycle transitions."""
    
    VALID_TRANSITIONS = {
        ReviewStatus.PENDING: [ReviewStatus.IN_REVIEW],
        ReviewStatus.IN_REVIEW: [
            ReviewStatus.APPROVED,
            ReviewStatus.REJECTED, 
            ReviewStatus.NEEDS_REVISION,
            ReviewStatus.STALE
        ],
        ReviewStatus.NEEDS_REVISION: [ReviewStatus.PENDING],
        ReviewStatus.STALE: [ReviewStatus.PENDING],
        # Terminal states
        ReviewStatus.APPROVED: [],
        ReviewStatus.REJECTED: []
    }
```

## Audit Trail Schema

### Review Request Record
```json
{
  "id": "req_123456",
  "mapping_id": "map_789012", 
  "mapping_version_hash": "a1b2c3d4...",
  "priority": "high",
  "submitted_at": "2024-03-15T10:30:00Z",
  "submitted_by": "system@company.com",
  "evidence_urls": [
    "https://snapshots.blob.core.windows.net/regulatory/fsma_dora_guidance_2024.pdf",
    "https://snapshots.blob.core.windows.net/regulatory/nbb_technical_standards_2024.pdf"
  ],
  "rationale": "DORA Article 18 requires incident reporting procedures"
}
```

### Review Decision Record
```json
{
  "request_id": "req_123456",
  "reviewer_id": "lawyer_001",
  "reviewer_email": "lawyer@company.com", 
  "reviewer_role": "Senior Legal Counsel",
  "decision": "approved",
  "comments": "Mapping accurately reflects DORA requirements. Evidence URLs reviewed and verified.",
  "evidence_reviewed": [
    "https://snapshots.blob.core.windows.net/regulatory/fsma_dora_guidance_2024.pdf"
  ],
  "reviewed_at": "2024-03-15T14:45:00Z",
  "review_duration_minutes": 255,
  "version_verified": true
}
```

## Test Strategy

### State Machine Testing
```python
def test_review_state_transitions():
    """Test valid and invalid state transitions."""
    assert can_transition(PENDING, IN_REVIEW) == True
    assert can_transition(APPROVED, IN_REVIEW) == False
    assert can_transition(IN_REVIEW, STALE) == True

def test_stale_detection():
    """Test detection of changed mappings."""
    original_mapping = {"control_id": "C001", "rationale": "Original"}
    modified_mapping = {"control_id": "C001", "rationale": "Modified"}
    
    original_hash = hash_mapping_content(original_mapping)
    assert is_mapping_stale(original_hash, modified_mapping) == True
```

### Audit Trail Testing
```python
def test_audit_immutability():
    """Verify audit records cannot be modified."""
    decision = create_review_decision()
    
    # Attempt to modify should fail
    with pytest.raises(FrozenInstanceError):
        decision.decision = ReviewStatus.REJECTED

def test_version_tracking():
    """Verify version hashes track changes."""
    mapping_v1 = create_test_mapping()
    hash_v1 = hash_mapping_content(mapping_v1)
    
    mapping_v2 = {**mapping_v1, "rationale": "Updated rationale"}
    hash_v2 = hash_mapping_content(mapping_v2)
    
    assert hash_v1 != hash_v2
```

### Integration Testing
```python
@pytest.mark.integration
async def test_end_to_end_review():
    """Test complete review workflow."""
    # Submit for review
    request = await workflow.submit_for_review(
        mapping_id="test_mapping",
        priority=ReviewPriority.HIGH,
        rationale="Test review"
    )
    
    # Record decision
    decision = await workflow.record_decision(
        request.id,
        test_reviewer,
        ReviewStatus.APPROVED,
        "Looks good",
        ["evidence_url_1"]
    )
    
    # Verify audit trail
    audit_record = await db.get_review_audit(request.id)
    assert audit_record.decision == ReviewStatus.APPROVED
```

## SLA & Performance Metrics

### Review SLA Targets
- **Urgent**: 4 hours (regulatory deadlines)
- **High**: 24 hours (major obligations)
- **Normal**: 72 hours (standard mappings)
- **Low**: 1 week (minor updates)

### Quality Metrics
- Review accuracy (post-review issues)
- Evidence coverage (% URLs reviewed)
- Decision consistency (similar mappings)
- Stale review rate (version conflicts)

### Performance Targets
- Queue assignment: <1 minute
- Status updates: Real-time
- Export generation: <30 seconds
- Audit query response: <5 seconds

## Module Dependencies

### READ Operations
- Obligation mappings from database
- Reviewer profiles and workloads
- Evidence snapshots from Azure
- Historical review performance

### WRITE Operations  
- Review audit records (immutable)
- Reviewer assignment updates
- Notification queue entries
- Performance metrics

### EMIT Events
- `ReviewRequested(mapping_id, priority, reviewer)`
- `ReviewCompleted(request_id, decision, reviewer)`
- `ReviewSLABreached(request_id, hours_overdue)`
- `MappingApproved(mapping_id, reviewer, approval_date)`

## Export Functions

### Audit Report Generation
```python
def export_review_log(
    date_range: tuple[datetime, datetime],
    reviewer_filter: Optional[str] = None
) -> str:
    """Generate audit-grade review log in JSON format."""
```

### Compliance Reporting
- Review completion rates by priority
- Average review duration by reviewer
- Evidence coverage statistics
- Stale review frequency analysis

This module ensures **lawyer-approved** mappings with **bulletproof audit trails** for regulatory compliance.