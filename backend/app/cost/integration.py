"""
Integration helpers for cost tracking with Parallel.ai calls.
Provides decorators and context managers for automatic cost enforcement.
"""
import functools
import logging
from typing import Callable, Any, Optional, Dict
from contextlib import asynccontextmanager

from .shell import CostTracker
from .contracts import PreFlightCheck


logger = logging.getLogger(__name__)


class BudgetExceededException(Exception):
    """Raised when API call would exceed budget limits."""
    
    def __init__(self, message: str, preflight_check: PreFlightCheck):
        super().__init__(message)
        self.preflight_check = preflight_check


def with_cost_tracking(
    api_type: str,
    processor: str,
    use_case: str = "default"
):
    """
    Decorator to add automatic cost tracking to Parallel.ai API calls.
    
    Usage:
        @with_cost_tracking("search", "pro", "regulatory_digest")
        async def search_regulations(query: str, tenant: str):
            # Your Parallel.ai call here
            return results
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract tenant from arguments (convention: last positional or 'tenant' kwarg)
            tenant = kwargs.get('tenant')
            if not tenant and args:
                # Try to find tenant in args (common pattern: last argument)
                tenant = args[-1] if len(args) > 0 else None
            
            if not tenant:
                raise ValueError("Tenant must be provided for cost tracking")
            
            # Get cost tracker from dependency injection or create
            cost_tracker = kwargs.pop('cost_tracker', None)
            if not cost_tracker:
                raise ValueError("CostTracker must be injected")
            
            # Pre-flight check
            preflight = await cost_tracker.check_budget_before_call(
                api_type=api_type,
                processor=processor,
                tenant=tenant,
                use_case=use_case
            )
            
            if not preflight.allowed:
                raise BudgetExceededException(
                    f"Budget limit exceeded: {preflight.reason}",
                    preflight
                )
            
            try:
                # Execute the actual API call
                result = await func(*args, **kwargs)
                
                # Record successful cost
                await cost_tracker.record_api_cost(
                    api_type=api_type,
                    processor=processor,
                    tenant=tenant,
                    use_case=use_case,
                    request_id=kwargs.get('request_id'),
                    metadata={
                        'function': func.__name__,
                        'preflight_cost': float(preflight.proposed_cost_eur)
                    }
                )
                
                return result
                
            except Exception as e:
                # API call failed - don't record cost, but log for monitoring
                logger.warning(
                    f"API call failed after preflight check: {func.__name__} "
                    f"for tenant {tenant} - {str(e)}"
                )
                raise
        
        return wrapper
    return decorator


@asynccontextmanager
async def cost_tracked_call(
    cost_tracker: CostTracker,
    api_type: str,
    processor: str,
    tenant: str,
    use_case: str = "default",
    request_id: Optional[str] = None
):
    """
    Context manager for cost-tracked API calls.
    
    Usage:
        async with cost_tracked_call(tracker, "task", "pro", "tenant1") as ctx:
            if not ctx.allowed:
                raise BudgetExceededException(ctx.reason, ctx.preflight)
            
            # Make your Parallel.ai call here
            result = await parallel_client.task(...)
            
            # Cost is automatically recorded on successful exit
    """
    class CostTrackingContext:
        def __init__(self, preflight_check: PreFlightCheck):
            self.allowed = preflight_check.allowed
            self.reason = preflight_check.reason
            self.preflight = preflight_check
    
    # Pre-flight check
    preflight = await cost_tracker.check_budget_before_call(
        api_type=api_type,
        processor=processor,
        tenant=tenant,
        use_case=use_case
    )
    
    ctx = CostTrackingContext(preflight)
    
    try:
        yield ctx
        
        # If we get here without exception, record the cost
        if ctx.allowed:
            await cost_tracker.record_api_cost(
                api_type=api_type,
                processor=processor,
                tenant=tenant,
                use_case=use_case,
                request_id=request_id,
                metadata={
                    'preflight_cost': float(preflight.proposed_cost_eur),
                    'context_manager': True
                }
            )
    except Exception as e:
        # Don't record cost on failure, but log
        logger.warning(
            f"Cost-tracked call failed: {api_type}:{processor} "
            f"for tenant {tenant} - {str(e)}"
        )
        raise


async def assert_parallel_safe(
    cost_tracker: CostTracker,
    payload: Dict[str, Any],
    tenant: str,
    api_type: str = "task",
    processor: str = "pro"
) -> None:
    """
    Enhanced assert_parallel_safe that includes cost checking.
    
    This function should be called before ANY Parallel.ai API call to ensure:
    1. No PII in payload (existing functionality)
    2. Budget limits not exceeded (new functionality)
    3. Payload size within limits
    
    Raises:
        BudgetExceededException: If call would exceed budget
        ValueError: If payload contains forbidden content or is too large
    """
    # Budget check first (fail fast)
    preflight = await cost_tracker.check_budget_before_call(
        api_type=api_type,
        processor=processor,
        tenant=tenant
    )
    
    if not preflight.allowed:
        raise BudgetExceededException(
            f"Budget check failed: {preflight.reason}",
            preflight
        )
    
    # Convert payload to string for size and content checking
    payload_str = str(payload)
    
    # Size check (15k chars limit from claude.md)
    if len(payload_str) > 15000:
        raise ValueError(f"Payload too large: {len(payload_str)} chars (max 15000)")
    
    # PII patterns (basic implementation - extend based on existing assert_parallel_safe)
    forbidden_patterns = [
        '@',  # Email addresses
        'IBAN',  # Bank accounts
        'VAT',   # VAT numbers
        '+32',   # Belgian phone numbers
        '0032'   # Belgian phone numbers
    ]
    
    payload_upper = payload_str.upper()
    for pattern in forbidden_patterns:
        if pattern in payload_upper:
            raise ValueError(f"Forbidden pattern detected in payload: {pattern}")
    
    logger.debug(
        f"Parallel safety check passed: {tenant} {api_type}:{processor} "
        f"({len(payload_str)} chars, €{preflight.proposed_cost_eur:.3f})"
    )