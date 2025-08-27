# claude.md - Backend Commands

YOU ARE implementing backend modules using **Functional Core, Imperative Shell** pattern.

## 🚨 BACKEND RULES - NEVER BREAK

**FILE SEPARATION (MANDATORY):**
- `core.py` - ONLY pure functions (no async, no I/O, deterministic)
- `shell.py` - ALL I/O operations (databases, APIs, file system)
- `contracts.py` - Type definitions and protocols
- `events.py` - Domain events this module emits

**YOU MUST NEVER:**
- Put I/O operations in core.py
- Use exceptions in core functions (use Result types)
- Import shell modules from core modules
- Create circular event subscriptions
- Exceed 200 lines per file

## ⚡ DEVELOPMENT PATTERN

**FOR EVERY MODULE:**
1. **READ** the module's claude.md first
2. **WRITE** core.py with pure functions
3. **WRITE** shell.py with I/O operations
4. **TEST** core functions without mocks
5. **TEST** shell integration with mocks

## 📋 RESULT TYPE TEMPLATE

**USE THIS PATTERN:**
```python
from dataclasses import dataclass
from typing import Generic, TypeVar, Union

T = TypeVar('T')
E = TypeVar('E')

@dataclass(frozen=True)
class Success(Generic[T]):
    value: T

@dataclass(frozen=True)
class Failure(Generic[E]):
    error: E

Result = Union[Success[T], Failure[E]]
```

## 🎯 PERFORMANCE TARGETS

**Core Functions:**
- <1ms execution (pure computation only)
- Deterministic (same input = same output)
- No memory leaks (immutable data)

**Shell Operations:**
- Database queries: <50ms
- External APIs: <200ms
- Event publishing: <10ms

**MODULE INTEGRATION:**
- Event-driven communication only
- No direct module imports
- Async operations in shell layer only