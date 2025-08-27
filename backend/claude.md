# claude.md - Backend Architecture

## Development Philosophy
**Functional Core, Imperative Shell** with event sourcing and immutable audit trails.

## Core Principles
- **Pure Business Logic**: Core functions have no side effects
- **Controlled Side Effects**: I/O operations isolated in shell layer
- **Event Sourcing**: All state changes emit domain events
- **Immutable Records**: Audit trail append-only, never update
- **Result Types**: Explicit error handling, no exceptions in core

## Module Architecture Pattern

Each module follows this structure:
```
module/
├── claude.md          # Module context & contracts
├── __init__.py
├── core.py           # Pure business logic (no I/O)
├── shell.py          # I/O operations & side effects  
├── contracts.py      # Type definitions & protocols
├── events.py         # Domain events
└── tests/
    ├── test_core.py      # Unit tests (pure functions)
    └── test_shell.py     # Integration tests (I/O)
```

## Module Map

Each module has its own claude.md with specific contracts:

### Security & Integration Layer
- `/app/parallel/common/` - PII boundary enforcement & circuit breakers
- `/app/parallel/search/` - Search API wrapper with fallbacks
- `/app/parallel/task/` - Task API with schema validation
- `/app/parallel/webhooks/` - mTLS + HMAC + replay protection

### Regulatory Monitoring Layer
- `/app/regulatory/monitor/` - Multi-language source scanning
- `/app/regulatory/digest/` - Actionable weekly digests
- `/app/regulatory/snapshot/` - Immutable source preservation

### Compliance Management Layer
- `/app/compliance/obligations/` - DORA/NIS2 obligation mapping
- `/app/compliance/reviews/` - Lawyer review workflow with audit

### Incident Management Layer
- `/app/incidents/rules/` - DORA classification rules engine
- `/app/incidents/clocks/` - DST-aware deadline calculations

### Evidence & Cost Layer
- `/app/evidence/` - Hash chain verification
- `/app/cost/` - €1,500 spend tracking with kill switch

## Cross-Cutting Concerns

### Error Handling
```python
from typing import Union, TypeVar, Generic

T = TypeVar('T')
E = TypeVar('E')

class Result(Generic[T, E]):
    """Explicit error handling - no exceptions in core logic."""
    
@dataclass(frozen=True)
class Success(Result[T, E]):
    value: T
    
@dataclass(frozen=True) 
class Failure(Result[T, E]):
    error: E
```

### Event System
```python
@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""
    event_id: str
    occurred_at: datetime
    correlation_id: str
    
class EventBus(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
```

### Audit Logging
```python
@dataclass(frozen=True)
class AuditRecord:
    """Immutable audit entry."""
    id: str
    action: str
    actor: str
    timestamp: datetime
    data_hash: str
    previous_hash: Optional[str]
```

## Data Flow Patterns

### Read Operations
1. Shell receives request
2. Shell loads data from persistence
3. Core processes pure business logic
4. Shell returns result

### Write Operations
1. Shell receives command
2. Shell loads current state
3. Core validates & computes new state
4. Shell persists state + emits events
5. Shell returns result

### External API Calls
1. Pre-flight: Cost check + PII boundary validation
2. Circuit breaker: Check if service available
3. Execute: Make API call with timeout
4. Post-flight: Record cost + emit telemetry
5. Fallback: Use RSS/cache if API failed

## Security Boundaries

### PII Protection
- All external API calls must pass `assert_parallel_safe()`
- Pattern matching for account numbers, IDs, emails
- Size limits: 15K chars max per request
- Audit log all blocked attempts

### Cost Controls
- Pre-flight cost check before every API call
- Kill switch at 95% of €1,500 monthly cap
- Real-time spend tracking with Redis
- Weekly cost reports for audit

### Immutability
- Source snapshots use Azure immutable blobs
- Evidence chain uses cryptographic hashing
- Review audit trail is append-only
- All timestamps in UTC

## Testing Strategy

### Pure Core Testing
- Property-based testing for business rules
- Fast unit tests with no I/O
- Deterministic outputs for same inputs

### Shell Integration Testing
- Mock external services
- Test error handling & retries
- Verify event publishing

### Acceptance Testing
- End-to-end scenarios
- NBB XSD validation with official vectors
- 32 DST/timezone clock scenarios
- PII injection attack prevention

## Development Guidelines

### Code Organization
- Keep functions pure whenever possible
- Separate data transformations from I/O
- Use immutable data structures
- Explicit error handling with Result types

### Commit Standards
- `feat:` - New functionality
- `fix:` - Bug fixes  
- `security:` - Security improvements
- `audit:` - Audit trail changes
- `test:` - Test additions/changes

### Module Independence
- Modules communicate via events, not direct calls
- Each module owns its data model
- Shared types defined in contracts.py
- No circular dependencies

This architecture ensures audit-grade compliance while maintaining clean separation of concerns and testability.