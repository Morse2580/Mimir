/**
 * Recovery Progress Component
 * 
 * Shows progress of system recovery from degraded mode with real-time updates.
 */

import React, { useState, useEffect } from 'react';
import { 
  RefreshCw, 
  CheckCircle, 
  XCircle, 
  Clock,
  TrendingUp,
  AlertTriangle
} from 'lucide-react';

interface RecoveryStep {
  id: string;
  name: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  estimated_duration_seconds?: number;
}

interface RecoveryProgressProps {
  /** List of recovery steps */
  steps: RecoveryStep[];
  /** Overall recovery status */
  overallStatus: 'not_started' | 'in_progress' | 'completed' | 'failed';
  /** Estimated time remaining in seconds */
  estimatedTimeRemaining?: number;
  /** Whether to show detailed step information */
  showDetails?: boolean;
  /** Callback when user requests manual retry */
  onManualRetry?: () => void;
  /** Additional CSS classes */
  className?: string;
}

export const RecoveryProgress: React.FC<RecoveryProgressProps> = ({
  steps,
  overallStatus,
  estimatedTimeRemaining,
  showDetails = true,
  onManualRetry,
  className = ''
}) => {
  const [currentTime, setCurrentTime] = useState(new Date());

  // Update current time every second for real-time duration display
  useEffect(() => {
    const interval = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const getOverallStatusConfig = () => {
    switch (overallStatus) {
      case 'in_progress':
        return {
          icon: RefreshCw,
          iconClass: 'animate-spin text-blue-600',
          title: 'Recovery in Progress',
          bgClass: 'bg-blue-50 border-blue-200'
        };
      case 'completed':
        return {
          icon: CheckCircle,
          iconClass: 'text-green-600',
          title: 'Recovery Completed',
          bgClass: 'bg-green-50 border-green-200'
        };
      case 'failed':
        return {
          icon: XCircle,
          iconClass: 'text-red-600',
          title: 'Recovery Failed',
          bgClass: 'bg-red-50 border-red-200'
        };
      default:
        return {
          icon: Clock,
          iconClass: 'text-gray-600',
          title: 'Recovery Pending',
          bgClass: 'bg-gray-50 border-gray-200'
        };
    }
  };

  const getStepStatusIcon = (step: RecoveryStep) => {
    switch (step.status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-600" />;
      case 'in_progress':
        return <RefreshCw className="h-4 w-4 text-blue-600 animate-spin" />;
      default:
        return <Clock className="h-4 w-4 text-gray-400" />;
    }
  };

  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  const calculateStepDuration = (step: RecoveryStep): number => {
    if (!step.started_at) return 0;
    
    const startTime = new Date(step.started_at);
    const endTime = step.completed_at ? new Date(step.completed_at) : currentTime;
    
    return Math.floor((endTime.getTime() - startTime.getTime()) / 1000);
  };

  const calculateProgress = (): number => {
    if (steps.length === 0) return 0;
    
    const completedSteps = steps.filter(step => step.status === 'completed').length;
    return (completedSteps / steps.length) * 100;
  };

  const statusConfig = getOverallStatusConfig();
  const OverallIcon = statusConfig.icon;
  const progress = calculateProgress();

  return (
    <div 
      className={`
        border rounded-lg p-4 
        ${statusConfig.bgClass}
        ${className}
      `}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <OverallIcon className={`h-5 w-5 ${statusConfig.iconClass}`} />
          <div>
            <h3 className="text-sm font-medium text-gray-900">
              {statusConfig.title}
            </h3>
            {estimatedTimeRemaining && overallStatus === 'in_progress' && (
              <p className="text-xs text-gray-600 mt-1">
                Estimated time remaining: {formatDuration(estimatedTimeRemaining)}
              </p>
            )}
          </div>
        </div>
        
        {overallStatus === 'failed' && onManualRetry && (
          <button
            onClick={onManualRetry}
            className="
              inline-flex items-center px-3 py-1 rounded text-xs font-medium
              bg-red-600 text-white hover:bg-red-700
              focus:outline-none focus:ring-2 focus:ring-red-500
            "
          >
            <RefreshCw className="h-3 w-3 mr-1" />
            Retry
          </button>
        )}
      </div>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
          <span>Progress</span>
          <span>{progress.toFixed(0)}% complete</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Steps */}
      {showDetails && steps.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-gray-700 uppercase tracking-wide">
            Recovery Steps
          </h4>
          
          <div className="space-y-2">
            {steps.map((step, index) => (
              <div
                key={step.id}
                className="flex items-start space-x-3 p-2 rounded bg-white bg-opacity-50"
              >
                <div className="flex-shrink-0 mt-0.5">
                  {getStepStatusIcon(step)}
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-gray-900">
                      {step.name}
                    </p>
                    
                    {step.status === 'in_progress' && step.started_at && (
                      <span className="text-xs text-gray-600 whitespace-nowrap ml-2">
                        {formatDuration(calculateStepDuration(step))}
                      </span>
                    )}
                    
                    {step.status === 'completed' && step.started_at && step.completed_at && (
                      <span className="text-xs text-green-600 whitespace-nowrap ml-2">
                        {formatDuration(calculateStepDuration(step))}
                      </span>
                    )}
                  </div>
                  
                  {step.error_message && step.status === 'failed' && (
                    <div className="mt-1 flex items-start space-x-1">
                      <AlertTriangle className="h-3 w-3 text-red-600 flex-shrink-0 mt-0.5" />
                      <p className="text-xs text-red-600">
                        {step.error_message}
                      </p>
                    </div>
                  )}
                  
                  {step.status === 'in_progress' && step.estimated_duration_seconds && (
                    <div className="mt-1">
                      <div className="flex items-center space-x-1 text-xs text-gray-600">
                        <TrendingUp className="h-3 w-3" />
                        <span>
                          Est. {formatDuration(step.estimated_duration_seconds)} total
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary */}
      {overallStatus === 'completed' && (
        <div className="mt-4 p-3 bg-green-100 rounded border border-green-200">
          <div className="flex items-center space-x-2">
            <CheckCircle className="h-4 w-4 text-green-600" />
            <p className="text-sm text-green-800 font-medium">
              System recovery completed successfully
            </p>
          </div>
          <p className="text-xs text-green-700 mt-1">
            All services have been restored to normal operation.
          </p>
        </div>
      )}

      {overallStatus === 'failed' && (
        <div className="mt-4 p-3 bg-red-100 rounded border border-red-200">
          <div className="flex items-center space-x-2">
            <XCircle className="h-4 w-4 text-red-600" />
            <p className="text-sm text-red-800 font-medium">
              Recovery failed
            </p>
          </div>
          <p className="text-xs text-red-700 mt-1">
            Manual intervention may be required. Contact system administrators if the problem persists.
          </p>
        </div>
      )}
    </div>
  );
};

export default RecoveryProgress;