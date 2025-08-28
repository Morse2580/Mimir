'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { reviewAPI } from '@/lib/api';
import { ReviewStatus, ReviewWithDetails } from '@/types/review';
import { X, CheckCircle, XCircle, AlertTriangle, MessageSquare } from 'lucide-react';

interface ReviewDecisionFormProps {
  review: ReviewWithDetails;
  onClose: () => void;
  onSuccess: () => void;
  onConcurrencyError: (error: string) => void;
}

export function ReviewDecisionForm({ 
  review, 
  onClose, 
  onSuccess, 
  onConcurrencyError 
}: ReviewDecisionFormProps) {
  const [decision, setDecision] = useState<ReviewStatus | null>(null);
  const [comments, setComments] = useState('');
  const [evidenceReviewed, setEvidenceReviewed] = useState<string[]>([]);

  const submitMutation = useMutation({
    mutationFn: (data: {
      decision: ReviewStatus;
      comments: string;
      evidence_reviewed: string[];
      version_hash: string;
    }) => reviewAPI.submitDecision(review.id, data),
    onSuccess: () => {
      onSuccess();
    },
    onError: (error: any) => {
      if (error.status === 409) {
        onConcurrencyError('The mapping has been modified since you started this review. Please refresh and try again.');
      } else {
        console.error('Failed to submit decision:', error);
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!decision) return;
    
    if ((decision === ReviewStatus.REJECTED || decision === ReviewStatus.NEEDS_REVISION) && !comments.trim()) {
      alert('Comments are required for rejection or revision requests');
      return;
    }

    submitMutation.mutate({
      decision,
      comments: comments.trim(),
      evidence_reviewed: evidenceReviewed,
      version_hash: review.mapping_version_hash,
    });
  };

  const handleEvidenceToggle = (url: string) => {
    if (evidenceReviewed.includes(url)) {
      setEvidenceReviewed(evidenceReviewed.filter(u => u !== url));
    } else {
      setEvidenceReviewed([...evidenceReviewed, url]);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-gray-900">
              Review Decision
            </h2>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Decision Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-3">
                Decision *
              </label>
              <div className="space-y-3">
                <label className="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50">
                  <input
                    type="radio"
                    value={ReviewStatus.APPROVED}
                    checked={decision === ReviewStatus.APPROVED}
                    onChange={(e) => setDecision(e.target.value as ReviewStatus)}
                    className="mr-3"
                  />
                  <CheckCircle className="w-5 h-5 text-success-500 mr-2" />
                  <div>
                    <div className="font-medium text-gray-900">Approve</div>
                    <div className="text-sm text-gray-600">
                      The mapping is accurate and compliant
                    </div>
                  </div>
                </label>

                <label className="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50">
                  <input
                    type="radio"
                    value={ReviewStatus.NEEDS_REVISION}
                    checked={decision === ReviewStatus.NEEDS_REVISION}
                    onChange={(e) => setDecision(e.target.value as ReviewStatus)}
                    className="mr-3"
                  />
                  <AlertTriangle className="w-5 h-5 text-warning-500 mr-2" />
                  <div>
                    <div className="font-medium text-gray-900">Needs Revision</div>
                    <div className="text-sm text-gray-600">
                      Minor changes required, can be resubmitted
                    </div>
                  </div>
                </label>

                <label className="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50">
                  <input
                    type="radio"
                    value={ReviewStatus.REJECTED}
                    checked={decision === ReviewStatus.REJECTED}
                    onChange={(e) => setDecision(e.target.value as ReviewStatus)}
                    className="mr-3"
                  />
                  <XCircle className="w-5 h-5 text-danger-500 mr-2" />
                  <div>
                    <div className="font-medium text-gray-900">Reject</div>
                    <div className="text-sm text-gray-600">
                      The mapping is incorrect or non-compliant
                    </div>
                  </div>
                </label>
              </div>
            </div>

            {/* Comments */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Comments {(decision === ReviewStatus.REJECTED || decision === ReviewStatus.NEEDS_REVISION) && '*'}
              </label>
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                rows={4}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                placeholder={
                  decision === ReviewStatus.APPROVED
                    ? "Optional: Add any additional notes..."
                    : "Required: Explain the issues and required changes..."
                }
              />
              <p className="mt-1 text-xs text-gray-600">
                Your comments will be part of the audit trail
              </p>
            </div>

            {/* Evidence Reviewed */}
            {review.evidence_urls.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Evidence Reviewed
                </label>
                <div className="space-y-2">
                  {review.evidence_urls.map((url, index) => (
                    <label key={index} className="flex items-center">
                      <input
                        type="checkbox"
                        checked={evidenceReviewed.includes(url)}
                        onChange={() => handleEvidenceToggle(url)}
                        className="mr-3"
                      />
                      <span className="text-sm text-gray-700">
                        Evidence Document {index + 1}
                      </span>
                    </label>
                  ))}
                </div>
                <p className="mt-1 text-xs text-gray-600">
                  Select which evidence documents you reviewed
                </p>
              </div>
            )}

            {/* Version Warning */}
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <div className="flex items-start">
                <AlertTriangle className="w-4 h-4 text-blue-500 mr-2 mt-0.5" />
                <div className="text-sm text-blue-800">
                  <div className="font-medium">Version Control</div>
                  <div>
                    This decision will be linked to mapping version:{' '}
                    <code className="font-mono text-xs">
                      {review.mapping_version_hash.substring(0, 8)}...
                    </code>
                  </div>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={onClose}
                className="btn-secondary"
                disabled={submitMutation.isPending}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!decision || submitMutation.isPending}
                className="btn-primary flex items-center"
              >
                <MessageSquare className="w-4 h-4 mr-2" />
                {submitMutation.isPending ? 'Submitting...' : 'Submit Decision'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}