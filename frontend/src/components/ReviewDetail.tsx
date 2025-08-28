'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { reviewAPI } from '@/lib/api';
import { ReviewStatus, ReviewWithDetails } from '@/types/review';
import { 
  getPriorityColor, 
  getStatusColor, 
  formatDateTime, 
  getTimeRemaining 
} from '@/lib/utils';
import { 
  Clock, 
  AlertTriangle, 
  User, 
  FileText, 
  ExternalLink,
  CheckCircle,
  XCircle,
  MessageSquare,
  Lock,
  Unlock,
  Hash
} from 'lucide-react';
import { ReviewDecisionForm } from './ReviewDecisionForm';

interface ReviewDetailProps {
  reviewId: string;
}

export function ReviewDetail({ reviewId }: ReviewDetailProps) {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [concurrencyError, setConcurrencyError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: review, isLoading, error, refetch } = useQuery({
    queryKey: ['review', reviewId],
    queryFn: () => reviewAPI.getReview(reviewId),
    refetchInterval: 30000,
  });

  const claimMutation = useMutation({
    mutationFn: () => reviewAPI.claimReview(reviewId),
    onSuccess: (updatedReview) => {
      queryClient.setQueryData(['review', reviewId], updatedReview);
      queryClient.invalidateQueries({ queryKey: ['reviews'] });
    },
    onError: (error: any) => {
      if (error.status === 409) {
        setConcurrencyError('This review has been claimed by another reviewer');
        refetch();
      }
    },
  });

  const releaseMutation = useMutation({
    mutationFn: () => reviewAPI.releaseReview(reviewId),
    onSuccess: () => {
      refetch();
      queryClient.invalidateQueries({ queryKey: ['reviews'] });
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="card p-6 animate-pulse">
          <div className="h-6 bg-gray-200 rounded w-3/4 mb-4"></div>
          <div className="h-4 bg-gray-200 rounded w-1/2 mb-2"></div>
          <div className="h-4 bg-gray-200 rounded w-2/3"></div>
        </div>
        <div className="card p-6 animate-pulse">
          <div className="h-32 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  if (error || !review) {
    return (
      <div className="card p-6 text-center">
        <AlertTriangle className="w-8 h-8 text-danger-500 mx-auto mb-4" />
        <p className="text-gray-600 mb-4">Failed to load review details</p>
        <button onClick={() => refetch()} className="btn-primary">
          Retry
        </button>
      </div>
    );
  }

  const slaInfo = review.sla_deadline ? getTimeRemaining(review.sla_deadline) : null;
  const canTakeAction = review.status === ReviewStatus.PENDING || review.status === ReviewStatus.IN_REVIEW;
  const isAssignedToMe = review.reviewer?.email === 'current@user.com'; // Replace with actual user check

  return (
    <div className="space-y-6">
      {/* Header Card */}
      <div className="card p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-3">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${getPriorityColor(review.priority)}`}>
                {review.priority.toUpperCase()}
              </span>
              
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(review.status || ReviewStatus.PENDING)}`}>
                {(review.status || ReviewStatus.PENDING).replace('_', ' ')}
              </span>

              {slaInfo && (
                <div className={`flex items-center text-sm font-medium ${slaInfo.isOverdue ? 'text-danger-600' : 'text-warning-600'}`}>
                  <Clock className="w-4 h-4 mr-1" />
                  {slaInfo.isOverdue ? 
                    `${slaInfo.hours}h ${slaInfo.minutes}m OVERDUE` : 
                    `${slaInfo.hours}h ${slaInfo.minutes}m remaining`
                  }
                </div>
              )}
            </div>

            <h1 className="text-2xl font-bold text-gray-900 mb-2">
              Review Request: {review.id}
            </h1>
            <p className="text-gray-600">
              Mapping ID: {review.mapping_id}
            </p>
          </div>

          {/* Assignment Status */}
          <div className="text-right">
            <div className="flex items-center text-sm text-gray-600 mb-2">
              <User className="w-4 h-4 mr-1" />
              {review.reviewer ? review.reviewer.email : 'Unassigned'}
            </div>
            
            {canTakeAction && (
              <div className="space-x-2">
                {!review.reviewer && (
                  <button
                    onClick={() => claimMutation.mutate()}
                    disabled={claimMutation.isPending}
                    className="btn-primary text-sm"
                  >
                    <Lock className="w-4 h-4 mr-1" />
                    {claimMutation.isPending ? 'Claiming...' : 'Claim Review'}
                  </button>
                )}
                
                {review.reviewer && isAssignedToMe && (
                  <button
                    onClick={() => releaseMutation.mutate()}
                    disabled={releaseMutation.isPending}
                    className="btn-secondary text-sm"
                  >
                    <Unlock className="w-4 h-4 mr-1" />
                    {releaseMutation.isPending ? 'Releasing...' : 'Release'}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Concurrency Error */}
        {concurrencyError && (
          <div className="mb-4 p-3 bg-warning-50 border border-warning-200 rounded-lg">
            <div className="flex items-center text-warning-800">
              <AlertTriangle className="w-4 h-4 mr-2" />
              {concurrencyError}
            </div>
          </div>
        )}

        {/* Submission Details */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-gray-600">
          <div>
            <span className="font-medium">Submitted:</span> {formatDateTime(review.submitted_at)}
          </div>
          <div>
            <span className="font-medium">Submitted by:</span> {review.submitted_by}
          </div>
          <div className="md:col-span-2">
            <div className="flex items-center">
              <Hash className="w-4 h-4 mr-1" />
              <span className="font-medium">Version Hash:</span>
              <code className="ml-2 px-2 py-1 bg-gray-100 rounded text-xs font-mono">
                {review.mapping_version_hash}
              </code>
            </div>
          </div>
        </div>
      </div>

      {/* Rationale Card */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">
          Review Rationale
        </h2>
        <p className="text-gray-700 leading-relaxed">
          {review.rationale}
        </p>
      </div>

      {/* Mapping Details Card */}
      {review.mapping_details && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Mapping Details
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Obligation ID
              </label>
              <p className="text-gray-900">{review.mapping_details.obligation_id}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Control ID
              </label>
              <p className="text-gray-900">{review.mapping_details.control_id}</p>
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Mapping Rationale
              </label>
              <p className="text-gray-900">{review.mapping_details.mapping_rationale}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Confidence Score
              </label>
              <p className="text-gray-900">{(review.mapping_details.confidence_score * 100).toFixed(1)}%</p>
            </div>
          </div>
        </div>
      )}

      {/* Evidence Card */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Supporting Evidence
        </h2>
        {review.evidence_urls.length === 0 ? (
          <p className="text-gray-500 italic">No evidence files provided</p>
        ) : (
          <div className="space-y-3">
            {review.evidence_urls.map((url, index) => (
              <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center">
                  <FileText className="w-5 h-5 text-gray-400 mr-3" />
                  <span className="text-gray-900 font-medium">
                    Evidence Document {index + 1}
                  </span>
                </div>
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center text-primary-600 hover:text-primary-700 text-sm"
                >
                  View Document
                  <ExternalLink className="w-4 h-4 ml-1" />
                </a>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      {canTakeAction && isAssignedToMe && (
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              Review Decision
            </h2>
            <button
              onClick={() => setIsFormOpen(true)}
              className="btn-primary"
            >
              <MessageSquare className="w-4 h-4 mr-2" />
              Make Decision
            </button>
          </div>
        </div>
      )}

      {/* Decision Form Modal */}
      {isFormOpen && (
        <ReviewDecisionForm
          review={review}
          onClose={() => {
            setIsFormOpen(false);
            setConcurrencyError(null);
          }}
          onSuccess={() => {
            setIsFormOpen(false);
            refetch();
            queryClient.invalidateQueries({ queryKey: ['reviews'] });
          }}
          onConcurrencyError={(error) => {
            setConcurrencyError(error);
            setIsFormOpen(false);
            refetch();
          }}
        />
      )}
    </div>
  );
}