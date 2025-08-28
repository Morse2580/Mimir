"""
Cost tracking I/O operations - Redis, database, alerts.
All external interactions go here.
"""
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import uuid4

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .core import (
    calculate_api_cost,
    should_activate_kill_switch,
    calculate_budget_utilization,
    get_budget_status,
    MONTHLY_CAP_EUR,
    KILL_SWITCH_THRESHOLD_PERCENT
)
from .contracts import (
    CostEntry,
    BudgetState,
    PreFlightCheck,
    BudgetStatus,
    BudgetAlert,
    SpendLimits
)
from .events import (
    BudgetThresholdExceeded,
    KillSwitchActivated,
    CostRecorded,
    BudgetReset
)


logger = logging.getLogger(__name__)


class CostTracker:
    """Redis-based cost tracking with kill switch."""
    
    def __init__(self, redis_client: redis.Redis, db_session: AsyncSession):
        self.redis = redis_client
        self.db = db_session
        self.spend_limits = SpendLimits(
            monthly_cap_eur=MONTHLY_CAP_EUR,
            kill_switch_threshold_percent=KILL_SWITCH_THRESHOLD_PERCENT
        )
    
    def _get_monthly_key(self, tenant: str, month: Optional[str] = None) -> str:
        """Get Redis key for monthly spend tracking."""
        if month is None:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
        return f"cost:spend:{tenant}:{month}"
    
    def _get_kill_switch_key(self, tenant: str) -> str:
        """Get Redis key for kill switch state."""
        return f"cost:kill_switch:{tenant}"
    
    async def get_current_spend(self, tenant: str) -> Decimal:
        """Get current monthly spend from Redis."""
        key = self._get_monthly_key(tenant)
        spend_str = await self.redis.get(key)
        
        if spend_str is None:
            return Decimal("0.00")
        
        return Decimal(spend_str.decode())
    
    async def is_kill_switch_active(self, tenant: str) -> bool:
        """Check if kill switch is currently active."""
        key = self._get_kill_switch_key(tenant)
        active = await self.redis.get(key)
        return active == b"1" if active else False
    
    async def check_budget_before_call(
        self,
        api_type: str,
        processor: str,
        tenant: str,
        use_case: str = "default"
    ) -> PreFlightCheck:
        """
        Pre-flight budget check before API call.
        Must complete in <10ms per performance requirement.
        """
        # Check if kill switch is already active
        if await self.is_kill_switch_active(tenant):
            return PreFlightCheck(
                allowed=False,
                current_spend_eur=await self.get_current_spend(tenant),
                proposed_cost_eur=Decimal("0.00"),
                projected_spend_eur=Decimal("0.00"),
                utilization_after_percent=Decimal("0.00"),
                kill_switch_would_activate=True,
                reason="Kill switch already active"
            )
        
        # Calculate proposed cost
        try:
            proposed_cost = calculate_api_cost(api_type, processor)
        except ValueError as e:
            return PreFlightCheck(
                allowed=False,
                current_spend_eur=Decimal("0.00"),
                proposed_cost_eur=Decimal("0.00"),
                projected_spend_eur=Decimal("0.00"),
                utilization_after_percent=Decimal("0.00"),
                kill_switch_would_activate=False,
                reason=f"Invalid API parameters: {e}"
            )
        
        # Get current spend
        current_spend = await self.get_current_spend(tenant)
        projected_spend = current_spend + proposed_cost
        
        # Check kill switch threshold
        would_activate_kill_switch = should_activate_kill_switch(
            current_spend, proposed_cost
        )
        
        utilization_after = calculate_budget_utilization(projected_spend)
        
        if would_activate_kill_switch:
            # Activate kill switch immediately
            await self._activate_kill_switch(tenant, current_spend, proposed_cost)
            
            return PreFlightCheck(
                allowed=False,
                current_spend_eur=current_spend,
                proposed_cost_eur=proposed_cost,
                projected_spend_eur=projected_spend,
                utilization_after_percent=utilization_after,
                kill_switch_would_activate=True,
                reason=f"Would exceed 95% threshold (€{MONTHLY_CAP_EUR * Decimal('0.95'):.2f})"
            )
        
        return PreFlightCheck(
            allowed=True,
            current_spend_eur=current_spend,
            proposed_cost_eur=proposed_cost,
            projected_spend_eur=projected_spend,
            utilization_after_percent=utilization_after,
            kill_switch_would_activate=False
        )
    
    async def record_api_cost(
        self,
        api_type: str,
        processor: str,
        tenant: str,
        use_case: str,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CostEntry:
        """
        Record API cost after successful call.
        Must complete in <50ms per performance requirement.
        """
        # Calculate cost
        cost_eur = calculate_api_cost(api_type, processor)
        timestamp = datetime.now(timezone.utc)
        
        # Create cost entry
        cost_entry = CostEntry(
            id=str(uuid4()),
            tenant=tenant,
            api_type=api_type,
            processor=processor,
            cost_eur=cost_eur,
            use_case=use_case,
            timestamp=timestamp,
            request_id=request_id,
            metadata=metadata
        )
        
        # Update Redis spend total atomically
        key = self._get_monthly_key(tenant)
        pipe = self.redis.pipeline()
        
        # Increment spend and get new total
        pipe.incrbyfloat(key, float(cost_eur))
        pipe.expire(key, 32 * 24 * 3600)  # 32 days TTL
        results = await pipe.execute()
        
        new_total_spend = Decimal(str(results[0]))
        utilization = calculate_budget_utilization(new_total_spend)
        
        # Store in database for audit trail
        await self._store_cost_entry_db(cost_entry)
        
        # Emit cost recorded event
        await self._emit_event(CostRecorded(
            tenant=tenant,
            api_type=api_type,
            processor=processor,
            cost_eur=cost_eur,
            use_case=use_case,
            new_total_spend=new_total_spend,
            utilization_percent=utilization,
            timestamp=timestamp,
            request_id=request_id
        ))
        
        # Check for threshold crossings
        await self._check_threshold_alerts(tenant, new_total_spend - cost_eur, new_total_spend)
        
        logger.info(
            f"Recorded cost: {tenant} {api_type}:{processor} €{cost_eur:.3f} "
            f"(total: €{new_total_spend:.2f}, {utilization:.1f}%)"
        )
        
        return cost_entry
    
    async def get_budget_state(self, tenant: str) -> BudgetState:
        """Get current budget state for tenant."""
        current_spend = await self.get_current_spend(tenant)
        utilization = calculate_budget_utilization(current_spend)
        kill_switch_active = await self.is_kill_switch_active(tenant)
        
        # Map utilization to status
        status_str = get_budget_status(current_spend)
        status = BudgetStatus(status_str)
        
        return BudgetState(
            tenant=tenant,
            current_spend_eur=current_spend,
            monthly_cap_eur=MONTHLY_CAP_EUR,
            utilization_percent=utilization,
            status=status,
            kill_switch_active=kill_switch_active,
            last_updated=datetime.now(timezone.utc)
        )
    
    async def _activate_kill_switch(
        self,
        tenant: str,
        current_spend: Decimal,
        proposed_cost: Decimal
    ) -> None:
        """Activate kill switch immediately. Must complete in <1 second."""
        key = self._get_kill_switch_key(tenant)
        await self.redis.set(key, "1", ex=24*3600)  # 24h TTL
        
        utilization = calculate_budget_utilization(current_spend)
        
        # Emit kill switch activation event
        await self._emit_event(KillSwitchActivated(
            tenant=tenant,
            current_spend_eur=current_spend,
            proposed_cost_eur=proposed_cost,
            utilization_percent=utilization,
            kill_switch_threshold_percent=KILL_SWITCH_THRESHOLD_PERCENT,
            timestamp=datetime.now(timezone.utc)
        ))
        
        logger.critical(
            f"KILL SWITCH ACTIVATED: {tenant} - current: €{current_spend:.2f}, "
            f"proposed: €{proposed_cost:.3f}, utilization: {utilization:.1f}%"
        )
    
    async def _check_threshold_alerts(
        self,
        tenant: str,
        previous_spend: Decimal,
        current_spend: Decimal
    ) -> None:
        """Check if budget thresholds have been crossed."""
        previous_status = get_budget_status(previous_spend)
        current_status = get_budget_status(current_spend)
        
        if previous_status != current_status:
            utilization = calculate_budget_utilization(current_spend)
            
            # Map string status to enum
            prev_status_enum = BudgetStatus(previous_status)
            curr_status_enum = BudgetStatus(current_status)
            
            await self._emit_event(BudgetThresholdExceeded(
                tenant=tenant,
                threshold_percent=self._get_threshold_for_status(curr_status_enum),
                current_spend_eur=current_spend,
                utilization_percent=utilization,
                previous_status=prev_status_enum,
                new_status=curr_status_enum,
                timestamp=datetime.now(timezone.utc)
            ))
    
    def _get_threshold_for_status(self, status: BudgetStatus) -> Decimal:
        """Get threshold percentage for status."""
        thresholds = {
            BudgetStatus.WARNING: Decimal("50"),
            BudgetStatus.ALERT: Decimal("80"),
            BudgetStatus.ESCALATION: Decimal("90"),
            BudgetStatus.KILL_SWITCH: KILL_SWITCH_THRESHOLD_PERCENT
        }
        return thresholds.get(status, Decimal("0"))
    
    async def _store_cost_entry_db(self, entry: CostEntry) -> None:
        """Store cost entry in database for audit trail."""
        query = text("""
            INSERT INTO cost_entries 
            (id, tenant, api_type, processor, cost_eur, use_case, timestamp, request_id, metadata)
            VALUES 
            (:id, :tenant, :api_type, :processor, :cost_eur, :use_case, :timestamp, :request_id, :metadata)
        """)
        
        await self.db.execute(query, {
            "id": entry.id,
            "tenant": entry.tenant,
            "api_type": entry.api_type,
            "processor": entry.processor,
            "cost_eur": float(entry.cost_eur),
            "use_case": entry.use_case,
            "timestamp": entry.timestamp,
            "request_id": entry.request_id,
            "metadata": json.dumps(entry.metadata) if entry.metadata else None
        })
        
        await self.db.commit()
    
    async def _emit_event(self, event) -> None:
        """Emit domain event (placeholder - integrate with event bus)."""
        event_key = f"events:cost:{event.__class__.__name__}"
        event_data = json.dumps({
            "event_type": event.__class__.__name__,
            "data": event.__dict__,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, default=str)
        
        await self.redis.lpush(event_key, event_data)
        await self.redis.expire(event_key, 24*3600)  # 24h TTL
        
        logger.info(f"Emitted event: {event.__class__.__name__} for {getattr(event, 'tenant', 'unknown')}")


async def reset_monthly_budget(
    redis_client: redis.Redis,
    tenant: str,
    month: Optional[str] = None
) -> None:
    """Reset monthly budget (typically called by scheduled job)."""
    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    
    old_key = f"cost:spend:{tenant}:{month}"
    previous_spend_str = await redis_client.get(old_key)
    previous_spend = Decimal(previous_spend_str.decode()) if previous_spend_str else Decimal("0.00")
    
    # Clear spend tracking
    await redis_client.delete(old_key)
    
    # Clear kill switch
    kill_switch_key = f"cost:kill_switch:{tenant}"
    await redis_client.delete(kill_switch_key)
    
    # Emit reset event
    reset_event = BudgetReset(
        tenant=tenant,
        previous_spend_eur=previous_spend,
        reset_timestamp=datetime.now(timezone.utc),
        new_month=month
    )
    
    event_key = f"events:cost:{reset_event.__class__.__name__}"
    event_data = json.dumps({
        "event_type": reset_event.__class__.__name__,
        "data": reset_event.__dict__,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }, default=str)
    
    await redis_client.lpush(event_key, event_data)
    await redis_client.expire(event_key, 24*3600)
    
    logger.info(f"Reset monthly budget for {tenant}: previous €{previous_spend:.2f}")


async def manual_kill_switch_override(
    redis_client: redis.Redis,
    tenant: str,
    overridden_by: str,
    reason: str,
    approval_level: str = "c_level"
) -> bool:
    """Manually override kill switch (requires C-level approval)."""
    if approval_level not in ["c_level", "emergency"]:
        raise ValueError("Kill switch override requires C-level or emergency approval")
    
    kill_switch_key = f"cost:kill_switch:{tenant}"
    was_active = await redis_client.get(kill_switch_key)
    
    if not was_active:
        return False  # Kill switch wasn't active
    
    # Remove kill switch
    await redis_client.delete(kill_switch_key)
    
    # Get current spend for logging
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    spend_key = f"cost:spend:{tenant}:{month}"
    current_spend_str = await redis_client.get(spend_key)
    current_spend = Decimal(current_spend_str.decode()) if current_spend_str else Decimal("0.00")
    
    logger.critical(
        f"KILL SWITCH OVERRIDDEN: {tenant} by {overridden_by} "
        f"(approval: {approval_level}) - current spend: €{current_spend:.2f}"
    )
    
    return True