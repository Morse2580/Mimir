export enum ReviewStatus {
  PENDING = 'pending',
  IN_REVIEW = 'in_review',
  APPROVED = 'approved',
  REJECTED = 'rejected',
  NEEDS_REVISION = 'needs_revision',
  STALE = 'stale',
}

export enum ReviewPriority {
  URGENT = 'urgent',
  HIGH = 'high', 
  NORMAL = 'normal',
  LOW = 'low',
}

export interface ReviewRequest {
  id: string;
  mapping_id: string;
  mapping_version_hash: string;
  priority: ReviewPriority;
  submitted_at: string;
  submitted_by: string;
  evidence_urls: string[];
  rationale: string;
  status?: ReviewStatus;
  assigned_to?: string;
  sla_deadline?: string;
}

export interface ReviewDecision {
  request_id: string;
  reviewer_id: string;
  reviewer_email: string;
  reviewer_role: string;
  decision: ReviewStatus;
  comments: string;
  evidence_reviewed: string[];
  reviewed_at: string;
  review_duration_minutes: number;
  version_verified: boolean;
}

export interface Reviewer {
  id: string;
  email: string;
  role: string;
  certifications: string[];
  workload_capacity: number;
  current_workload?: number;
}

export interface ReviewWithDetails extends ReviewRequest {
  reviewer?: Reviewer;
  hours_remaining?: number;
  is_sla_breached?: boolean;
  mapping_details?: {
    obligation_id: string;
    control_id: string;
    mapping_rationale: string;
    confidence_score: number;
  };
}