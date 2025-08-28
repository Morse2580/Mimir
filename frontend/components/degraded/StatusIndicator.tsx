/**
 * System Status Indicator Component
 * 
 * Shows current system status with real-time updates for degraded mode.
 */

import React, { useState, useEffect } from 'react';
import { 
  CheckCircle, 
  AlertCircle, 
  XCircle, 
  Clock,
  Loader2,
  TrendingUp,
  TrendingDown
} from 'lucide-react';

export enum SystemStatus {
  NORMAL = 'normal',
  DEGRADED = 'degraded', 
  CRITICAL = 'critical',
  RECOVERING = 'recovering',
  UNKNOWN = 'unknown'
}

interface StatusData {
  status: SystemStatus;
  coverage_percentage: number;
  active_fallbacks: string[];
  last_update: string;
  estimated_recovery_time?: string;
}

interface StatusIndicatorProps {
  /** Current status data */
  statusData: StatusData;
  /** Whether to show detailed info */
  detailed?: boolean;
  /** Size variant */
  size?: 'sm' | 'md' | 'lg';
  /** Additional CSS classes */
  className?: string;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  statusData,
  detailed = false,
  size = 'md',
  className = ''
}) => {
  const [isAnimating, setIsAnimating] = useState(false);

  // Animate when status changes
  useEffect(() => {
    setIsAnimating(true);
    const timer = setTimeout(() => setIsAnimating(false), 300);
    return () => clearTimeout(timer);
  }, [statusData.status]);

  const getStatusConfig = () => {
    switch (statusData.status) {
      case SystemStatus.NORMAL:
        return {
          icon: CheckCircle,
          label: 'Normal',
          color: 'text-green-600',
          bgColor: 'bg-green-100',
          borderColor: 'border-green-200',
          description: 'All systems operational'
        };
      case SystemStatus.DEGRADED:
        return {
          icon: AlertCircle,
          label: 'Limited Mode',
          color: 'text-yellow-600',
          bgColor: 'bg-yellow-100',
          borderColor: 'border-yellow-200',
          description: 'Operating with fallback systems'
        };
      case SystemStatus.CRITICAL:
        return {
          icon: XCircle,
          label: 'Critical',
          color: 'text-red-600',
          bgColor: 'bg-red-100',
          borderColor: 'border-red-200',
          description: 'Major service disruption'
        };
      case SystemStatus.RECOVERING:
        return {
          icon: TrendingUp,
          label: 'Recovering',
          color: 'text-blue-600',
          bgColor: 'bg-blue-100',
          borderColor: 'border-blue-200',
          description: 'Services coming back online'
        };
      default:
        return {
          icon: Clock,
          label: 'Unknown',
          color: 'text-gray-600',
          bgColor: 'bg-gray-100',
          borderColor: 'border-gray-200',
          description: 'Status unavailable'
        };
    }
  };

  const getSizeClasses = () => {
    switch (size) {
      case 'sm':
        return {
          container: 'px-2 py-1',
          icon: 'h-4 w-4',
          text: 'text-xs',
          badge: 'text-xs px-2 py-0.5'
        };
      case 'lg':
        return {
          container: 'px-4 py-3',
          icon: 'h-6 w-6',
          text: 'text-base',
          badge: 'text-sm px-3 py-1'
        };
      default: // md
        return {
          container: 'px-3 py-2',
          icon: 'h-5 w-5',
          text: 'text-sm',
          badge: 'text-xs px-2 py-1'
        };
    }
  };

  const config = getStatusConfig();
  const sizeClasses = getSizeClasses();
  const IconComponent = config.icon;

  const formatLastUpdate = (timestamp: string): string => {
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      
      if (diffMins < 1) return 'just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      
      return date.toLocaleDateString();
    } catch {
      return 'unknown';
    }
  };

  const formatCoverage = (coverage: number): string => {
    return `${Math.round(coverage * 100)}%`;
  };

  return (
    <div 
      className={`
        inline-flex items-center rounded-lg border
        ${config.bgColor} ${config.borderColor}
        ${sizeClasses.container}
        ${isAnimating ? 'transition-all duration-300 scale-105' : ''}
        ${className}
      `}
    >
      <div className="flex items-center space-x-2">
        <IconComponent 
          className={`${sizeClasses.icon} ${config.color}`}
          aria-hidden="true"
        />
        
        <div className="flex items-center space-x-2">
          <span className={`font-medium ${config.color} ${sizeClasses.text}`}>
            {config.label}
          </span>
          
          {statusData.status === SystemStatus.DEGRADED && (
            <span 
              className={`
                inline-flex items-center rounded-full 
                bg-white bg-opacity-75 font-medium
                ${config.color} ${sizeClasses.badge}
              `}
            >
              {formatCoverage(statusData.coverage_percentage)}
            </span>
          )}
        </div>
      </div>

      {detailed && (
        <div className="ml-4 pl-4 border-l border-gray-200 border-opacity-50">
          <div className={`${sizeClasses.text} ${config.color} space-y-1`}>
            <div className="font-medium">
              {config.description}
            </div>
            
            {statusData.active_fallbacks.length > 0 && (
              <div className="text-xs opacity-75">
                Fallbacks: {statusData.active_fallbacks.join(', ')}
              </div>
            )}
            
            <div className="text-xs opacity-75">
              Updated {formatLastUpdate(statusData.last_update)}
            </div>
            
            {statusData.estimated_recovery_time && statusData.status !== SystemStatus.NORMAL && (
              <div className="text-xs opacity-75 flex items-center space-x-1">
                <Clock className="h-3 w-3" />
                <span>ETA: {statusData.estimated_recovery_time}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

/**
 * Compact status dot for minimal space usage
 */
export const StatusDot: React.FC<{
  status: SystemStatus;
  className?: string;
}> = ({ status, className = '' }) => {
  const getStatusColor = () => {
    switch (status) {
      case SystemStatus.NORMAL: return 'bg-green-500';
      case SystemStatus.DEGRADED: return 'bg-yellow-500';
      case SystemStatus.CRITICAL: return 'bg-red-500';
      case SystemStatus.RECOVERING: return 'bg-blue-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div 
      className={`
        w-2 h-2 rounded-full ${getStatusColor()}
        ${status === SystemStatus.RECOVERING ? 'animate-pulse' : ''}
        ${className}
      `}
      title={`System status: ${status}`}
    />
  );
};

export default StatusIndicator;