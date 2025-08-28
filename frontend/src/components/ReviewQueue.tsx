'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { reviewAPI } from '@/lib/api';
import { ReviewStatus, ReviewPriority, ReviewWithDetails } from '@/types/review';
import { getPriorityColor, getStatusColor, formatDateTime, getTimeRemaining } from '@/lib/utils';
import { Clock, AlertTriangle, User, FileText, ChevronRight } from 'lucide-react';
import Link from 'next/link';

interface ReviewQueueProps {
  className?: string;
}

export function ReviewQueue({ className }: ReviewQueueProps) {
  const [statusFilter, setStatusFilter] = useState<ReviewStatus[]>([
    ReviewStatus.PENDING,
    ReviewStatus.IN_REVIEW
  ]);
  const [priorityFilter, setPriorityFilter] = useState<ReviewPriority[]>([]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['reviews', statusFilter, priorityFilter],
    queryFn: () => reviewAPI.getReviews({
      status: statusFilter,
      priority: priorityFilter.map(p => p.toString()),
      limit: 50,
    }),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const { data: stats } = useQuery({
    queryKey: ['review-stats'],
    queryFn: reviewAPI.getStats,
    refetchInterval: 60000, // Refresh every minute
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="card p-6 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
            <div className="h-3 bg-gray-200 rounded w-1/2"></div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-6 text-center">
        <AlertTriangle className="w-8 h-8 text-danger-500 mx-auto mb-4" />
        <p className="text-gray-600 mb-4">Failed to load reviews</p>
        <button onClick={() => refetch()} className="btn-primary">
          Retry
        </button>
      </div>
    );
  }

  const reviews = data?.reviews || [];

  return (
    <div className={className}>
      {/* Stats Row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-6">
          <div className="card p-4">
            <div className="text-2xl font-bold text-danger-600">{stats.urgent_count}</div>
            <div className="text-xs text-gray-600">Urgent</div>
          </div>
          <div className="card p-4">
            <div className="text-2xl font-bold text-warning-600">{stats.high_priority_count}</div>
            <div className="text-xs text-gray-600">High Priority</div>
          </div>
          <div className="card p-4">
            <div className="text-2xl font-bold text-danger-600">{stats.sla_breached_count}</div>
            <div className="text-xs text-gray-600">SLA Breached</div>
          </div>
          <div className="card p-4">
            <div className="text-2xl font-bold text-primary-600">{stats.total_pending}</div>
            <div className="text-xs text-gray-600">Total Pending</div>
          </div>
          <div className="card p-4">
            <div className="text-2xl font-bold text-success-600">{stats.my_assigned_count}</div>
            <div className="text-xs text-gray-600">My Assigned</div>
          </div>
          <div className="card p-4">
            <div className="text-2xl font-bold text-gray-900">{stats.avg_review_time_hours.toFixed(1)}h</div>
            <div className="text-xs text-gray-600">Avg Time</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="card p-4 mb-6">
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-700">Status:</span>
            <div className="flex gap-2">
              {Object.values(ReviewStatus).map((status) => (
                <label key={status} className="flex items-center">
                  <input
                    type="checkbox"
                    checked={statusFilter.includes(status)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setStatusFilter([...statusFilter, status]);
                      } else {
                        setStatusFilter(statusFilter.filter(s => s !== status));
                      }
                    }}
                    className="rounded mr-1"
                  />
                  <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(status)}`}>
                    {status.replace('_', ' ')}
                  </span>
                </label>
              ))}
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-700">Priority:</span>
            <div className="flex gap-2">
              {Object.values(ReviewPriority).map((priority) => (
                <label key={priority} className="flex items-center">
                  <input
                    type="checkbox"
                    checked={priorityFilter.includes(priority)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setPriorityFilter([...priorityFilter, priority]);
                      } else {
                        setPriorityFilter(priorityFilter.filter(p => p !== priority));
                      }
                    }}
                    className="rounded mr-1"
                  />
                  <span className={`px-2 py-1 rounded text-xs font-medium ${getPriorityColor(priority)}`}>
                    {priority}
                  </span>
                </label>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Reviews List */}
      <div className="space-y-4">
        {reviews.length === 0 ? (
          <div className="card p-8 text-center">
            <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600">No reviews match your current filters</p>
          </div>
        ) : (
          reviews.map((review) => (
            <ReviewCard key={review.id} review={review} />
          ))
        )}
      </div>
    </div>
  );
}

function ReviewCard({ review }: { review: ReviewWithDetails }) {
  const slaInfo = review.sla_deadline ? getTimeRemaining(review.sla_deadline) : null;

  return (
    <Link href={`/reviews/${review.id}`} className="card p-6 hover:shadow-md transition-shadow block">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <span className={`px-2 py-1 rounded text-xs font-medium ${getPriorityColor(review.priority)}`}>
              {review.priority.toUpperCase()}
            </span>
            
            <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(review.status || ReviewStatus.PENDING)}`}>
              {(review.status || ReviewStatus.PENDING).replace('_', ' ')}
            </span>

            {slaInfo && (
              <div className={`flex items-center text-xs ${slaInfo.isOverdue ? 'text-danger-600' : 'text-gray-600'}`}>
                <Clock className="w-3 h-3 mr-1" />
                {slaInfo.isOverdue ? 
                  `${slaInfo.hours}h ${slaInfo.minutes}m overdue` : 
                  `${slaInfo.hours}h ${slaInfo.minutes}m remaining`
                }
              </div>
            )}
          </div>

          <div className="mb-3">
            <h3 className="font-medium text-gray-900 mb-1">
              Mapping Review: {review.mapping_id}
            </h3>
            <p className="text-sm text-gray-600 line-clamp-2">
              {review.rationale}
            </p>
          </div>

          <div className="flex items-center gap-4 text-xs text-gray-500">
            <div className="flex items-center">
              <User className="w-3 h-3 mr-1" />
              {review.reviewer?.email || 'Unassigned'}
            </div>
            <div>
              Submitted: {formatDateTime(review.submitted_at)}
            </div>
            {review.evidence_urls.length > 0 && (
              <div>
                Evidence: {review.evidence_urls.length} file(s)
              </div>
            )}
          </div>
        </div>

        <ChevronRight className="w-5 h-5 text-gray-400" />
      </div>
    </Link>
  );
}