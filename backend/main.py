"""
Minimal FastAPI backend for lawyer review interface testing.
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

from app.compliance.reviews.contracts import (
    ReviewStatus, 
    ReviewPriority, 
    ReviewRequest, 
    ReviewDecision,
    Reviewer
)

app = FastAPI(
    title="Belgian RegOps - Lawyer Review API",
    description="API for legal compliance reviews under DORA and NIS2 regulations",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock data for testing
MOCK_REVIEWS = [
    {
        "id": "req_urgent001",
        "mapping_id": "map_dora_001",
        "mapping_version_hash": "a1b2c3d4e5f6789012345678901234567890abcd",
        "priority": ReviewPriority.URGENT,
        "submitted_at": (datetime.now() - timedelta(hours=2)).isoformat() + "Z",
        "submitted_by": "system@regops.be",
        "evidence_urls": [
            "https://snapshots.blob.core.windows.net/regulatory/dora_article_18.pdf",
            "https://snapshots.blob.core.windows.net/regulatory/nbb_guidance_2024.pdf"
        ],
        "rationale": "DORA Article 18 requires incident reporting procedures within 4 hours for major incidents. This mapping needs urgent legal review to ensure compliance with NBB requirements.",
        "status": ReviewStatus.PENDING,
        "sla_deadline": (datetime.now() + timedelta(hours=2)).isoformat() + "Z",
        "mapping_details": {
            "obligation_id": "DORA-18-1",
            "control_id": "INC-RPT-001",
            "mapping_rationale": "Incident reporting control directly implements DORA Article 18 notification requirements",
            "confidence_score": 0.95
        }
    },
    {
        "id": "req_high002",
        "mapping_id": "map_nis2_005",
        "mapping_version_hash": "f7e8d9c0b1a2345678901234567890abcdef1234",
        "priority": ReviewPriority.HIGH,
        "submitted_at": (datetime.now() - timedelta(hours=8)).isoformat() + "Z",
        "submitted_by": "mapper@regops.be",
        "evidence_urls": [
            "https://snapshots.blob.core.windows.net/regulatory/nis2_directive_2022.pdf"
        ],
        "rationale": "NIS2 Directive Article 23 mandates cybersecurity risk management measures. This control mapping requires legal validation for Belgian implementation.",
        "status": ReviewStatus.IN_REVIEW,
        "assigned_to": "lawyer@regops.be",
        "reviewer": {
            "id": "lawyer_001",
            "email": "lawyer@regops.be",
            "role": "Senior Legal Counsel",
            "certifications": ["Belgian Bar", "EU Regulatory Law"],
            "workload_capacity": 10
        },
        "sla_deadline": (datetime.now() + timedelta(hours=16)).isoformat() + "Z",
        "mapping_details": {
            "obligation_id": "NIS2-23-2",
            "control_id": "RISK-MGMT-003",
            "mapping_rationale": "Risk management framework aligns with NIS2 cybersecurity requirements",
            "confidence_score": 0.87
        }
    },
    {
        "id": "req_normal003",
        "mapping_id": "map_gdpr_012",
        "mapping_version_hash": "1234567890abcdef1234567890abcdef12345678",
        "priority": ReviewPriority.NORMAL,
        "submitted_at": (datetime.now() - timedelta(days=1)).isoformat() + "Z",
        "submitted_by": "compliance@regops.be",
        "evidence_urls": [],
        "rationale": "Standard GDPR data processing mapping for customer onboarding procedures. Regular compliance review required.",
        "status": ReviewStatus.PENDING,
        "sla_deadline": (datetime.now() + timedelta(days=2)).isoformat() + "Z",
        "mapping_details": {
            "obligation_id": "GDPR-6-1",
            "control_id": "DATA-PROC-001",
            "mapping_rationale": "Customer onboarding data processing has legal basis under GDPR Article 6(1)(b)",
            "confidence_score": 0.92
        }
    }
]

MOCK_STATS = {
    "total_pending": 5,
    "urgent_count": 1,
    "high_priority_count": 2,
    "sla_breached_count": 0,
    "my_assigned_count": 3,
    "avg_review_time_hours": 4.2
}

@app.get("/api/reviews")
async def get_reviews(
    status: List[ReviewStatus] = None,
    priority: List[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get reviews with optional filters."""
    
    filtered_reviews = MOCK_REVIEWS.copy()
    
    # Apply filters
    if status:
        filtered_reviews = [r for r in filtered_reviews if r["status"] in status]
    
    if priority:
        priority_enums = [ReviewPriority(p) for p in priority if p in [p.value for p in ReviewPriority]]
        filtered_reviews = [r for r in filtered_reviews if r["priority"] in priority_enums]
    
    if assigned_to:
        filtered_reviews = [r for r in filtered_reviews if r.get("assigned_to") == assigned_to]
    
    # Apply pagination
    total = len(filtered_reviews)
    reviews = filtered_reviews[offset:offset + limit]
    
    return {
        "reviews": reviews,
        "total": total
    }

@app.get("/api/reviews/{review_id}")
async def get_review(review_id: str):
    """Get single review by ID."""
    
    review = next((r for r in MOCK_REVIEWS if r["id"] == review_id), None)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Add some computed fields for testing
    review_copy = review.copy()
    if review_copy.get("sla_deadline"):
        deadline = datetime.fromisoformat(review_copy["sla_deadline"].replace("Z", "+00:00"))
        now = datetime.now(deadline.tzinfo)
        hours_remaining = (deadline - now).total_seconds() / 3600
        review_copy["hours_remaining"] = max(0, hours_remaining)
        review_copy["is_sla_breached"] = hours_remaining < 0
    
    return review_copy

@app.post("/api/reviews/{review_id}/claim")
async def claim_review(review_id: str):
    """Claim review for current user."""
    
    review = next((r for r in MOCK_REVIEWS if r["id"] == review_id), None)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if review.get("assigned_to"):
        raise HTTPException(status_code=409, detail="Review already assigned")
    
    # Mock assignment
    review["assigned_to"] = "current@user.com"
    review["status"] = ReviewStatus.IN_REVIEW
    review["reviewer"] = {
        "id": "current_user",
        "email": "current@user.com",
        "role": "Legal Counsel",
        "certifications": ["Belgian Bar"],
        "workload_capacity": 8
    }
    
    return review

@app.post("/api/reviews/{review_id}/release")
async def release_review(review_id: str):
    """Release review assignment."""
    
    review = next((r for r in MOCK_REVIEWS if r["id"] == review_id), None)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    review["assigned_to"] = None
    review["status"] = ReviewStatus.PENDING
    review["reviewer"] = None
    
    return {"message": "Review released successfully"}

@app.post("/api/reviews/{review_id}/decision")
async def submit_decision(review_id: str, decision_data: dict):
    """Submit review decision."""
    
    review = next((r for r in MOCK_REVIEWS if r["id"] == review_id), None)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Check version hash for optimistic locking
    if decision_data.get("version_hash") != review["mapping_version_hash"]:
        raise HTTPException(status_code=409, detail="Mapping has been modified")
    
    # Create mock decision record
    decision = {
        "request_id": review_id,
        "reviewer_id": "current_user",
        "reviewer_email": "current@user.com",
        "reviewer_role": "Legal Counsel",
        "decision": decision_data["decision"],
        "comments": decision_data["comments"],
        "evidence_reviewed": decision_data["evidence_reviewed"],
        "reviewed_at": datetime.now().isoformat() + "Z",
        "review_duration_minutes": 120,
        "version_verified": True
    }
    
    # Update review status
    review["status"] = ReviewStatus(decision_data["decision"])
    
    return decision

@app.get("/api/reviews/stats")
async def get_stats():
    """Get review statistics."""
    return MOCK_STATS

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)