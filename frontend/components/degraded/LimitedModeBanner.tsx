/**
 * Limited Mode Banner Component
 * 
 * Displays warning banner when system is operating in degraded mode
 * with fallback systems active.
 */

import React, { useState, useEffect } from 'react';
import { AlertTriangle, Wifi, WifiOff, RefreshCw, X } from 'lucide-react';

interface DegradedModeStatus {
  active: boolean;
  activated_at: string | null;
  trigger_reason: string;
  active_fallbacks: string[];
  estimated_coverage_percentage: number;
  recovery_detection_active: boolean;
}

interface LimitedModeBannerProps {
  /** Current degraded mode status */
  degradedModeStatus: DegradedModeStatus;
  /** Callback when user dismisses banner */
  onDismiss?: () => void;
  /** Whether banner can be dismissed */
  dismissible?: boolean;
  /** Additional CSS classes */
  className?: string;
}

export const LimitedModeBanner: React.FC<LimitedModeBannerProps> = ({
  degradedModeStatus,
  onDismiss,
  dismissible = false,
  className = ''
}) => {
  const [isDismissed, setIsDismissed] = useState(false);

  // Reset dismissed state when degraded mode becomes active
  useEffect(() => {
    if (degradedModeStatus.active) {
      setIsDismissed(false);
    }
  }, [degradedModeStatus.active]);

  const handleDismiss = () => {
    setIsDismissed(true);
    onDismiss?.();
  };

  // Don't render if not in degraded mode or if dismissed
  if (!degradedModeStatus.active || isDismissed) {
    return null;
  }

  const formatCoverage = (coverage: number): string => {
    return `${Math.round(coverage * 100)}%`;
  };

  const formatFallbacks = (fallbacks: string[]): string => {
    const fallbackNames = fallbacks.map(fallback => {
      switch (fallback) {
        case 'rss_feeds': return 'RSS Feeds';
        case 'cache': return 'Cached Data';
        case 'manual_input': return 'Manual Input';
        default: return fallback.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
      }
    });
    
    if (fallbackNames.length <= 2) {
      return fallbackNames.join(' and ');
    }
    return fallbackNames.slice(0, -1).join(', ') + ', and ' + fallbackNames.slice(-1);
  };

  const getSeverityClass = (): string => {
    if (degradedModeStatus.estimated_coverage_percentage >= 0.7) {
      return 'bg-yellow-50 border-yellow-200 text-yellow-800';
    } else if (degradedModeStatus.estimated_coverage_percentage >= 0.4) {
      return 'bg-orange-50 border-orange-200 text-orange-800';
    } else {
      return 'bg-red-50 border-red-200 text-red-800';
    }
  };

  const getIconColor = (): string => {
    if (degradedModeStatus.estimated_coverage_percentage >= 0.7) {
      return 'text-yellow-600';
    } else if (degradedModeStatus.estimated_coverage_percentage >= 0.4) {
      return 'text-orange-600';
    } else {
      return 'text-red-600';
    }
  };

  return (
    <div
      className={`
        border-l-4 p-4 mb-4 rounded-r-md shadow-sm
        ${getSeverityClass()}
        ${className}
      `}
      role="alert"
      aria-live="assertive"
    >
      <div className="flex items-start">
        <div className="flex-shrink-0">
          <AlertTriangle 
            className={`h-5 w-5 ${getIconColor()}`} 
            aria-hidden="true"
          />
        </div>
        
        <div className="ml-3 flex-1">
          <h3 className="text-sm font-medium">
            Limited Mode Active
          </h3>
          
          <div className="mt-2 text-sm">
            <p>
              The system is currently operating in degraded mode due to: <strong>{degradedModeStatus.trigger_reason}</strong>
            </p>
            
            <div className="mt-2 space-y-1">
              <div className="flex items-center space-x-2">
                <WifiOff className="h-4 w-4" />
                <span>
                  Coverage: <strong>{formatCoverage(degradedModeStatus.estimated_coverage_percentage)}</strong> of normal functionality
                </span>
              </div>
              
              <div className="flex items-center space-x-2">
                <Wifi className="h-4 w-4" />
                <span>
                  Active fallbacks: <strong>{formatFallbacks(degradedModeStatus.active_fallbacks)}</strong>
                </span>
              </div>
              
              {degradedModeStatus.recovery_detection_active && (
                <div className="flex items-center space-x-2">
                  <RefreshCw className="h-4 w-4" />
                  <span>Automatic recovery detection is active</span>
                </div>
              )}
            </div>
            
            <div className="mt-3 p-3 bg-white bg-opacity-50 rounded border">
              <h4 className="text-xs font-medium uppercase tracking-wide mb-1">
                What this means:
              </h4>
              <ul className="text-xs space-y-1">
                <li>• Data freshness and coverage may be limited</li>
                <li>• Some features may be unavailable or delayed</li>
                <li>• RSS feeds are being used as primary data source</li>
                <li>• System will automatically recover when services are restored</li>
              </ul>
            </div>
          </div>
        </div>
        
        {dismissible && (
          <div className="ml-auto pl-3">
            <div className="-mx-1.5 -my-1.5">
              <button
                type="button"
                onClick={handleDismiss}
                className={`
                  inline-flex rounded-md p-1.5 hover:bg-black hover:bg-opacity-10 
                  focus:outline-none focus:ring-2 focus:ring-offset-2 
                  ${getIconColor()} hover:${getIconColor()}
                `}
                aria-label="Dismiss banner"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LimitedModeBanner;