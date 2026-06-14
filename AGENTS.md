# AGENTS.md

Guidelines for AI coding agents working on the Knowledge Graph Engine repository.

## Build/Test Commands

```bash
# Install dependencies
pip install -e .

# Run all tests
pytest tests/

# Run single test file
pytest tests/test_extract.py -v

# Run specific test
pytest tests/test_extract.py::TestExtractor::test_extract -v

# Run with markers (unit/integration/extract/search)
pytest -m unit
pytest -m integration

# Start the gateway (KGE is a core library; gateway is a separate package)
python -m silvaengine_gateway

# Type checking (pyright configured in pyproject.toml)
pyright knowledge_graph_engine/
```

## Code Style

### File Headers
Every Python file must include:
```python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"
```

### Import Order
1. Standard library (`__future__`, `typing`, `logging`, etc.)
2. Third-party packages (`pendulum`, `graphene`, `neo4j`, etc.)
3. Internal modules (relative imports with `..`)

Example:
```python
from __future__ import print_function

import logging
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ..handlers.config import Config
from ..types.document import DocumentType
```

### Naming Conventions
- **Functions/Variables**: `snake_case` (e.g., `partition_key`, `extract_graph`)
- **Classes**: `PascalCase` (e.g., `KnowledgeGraphEngine`, `DocumentModel`)
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: Prefix with `_` (e.g., `_apply_partition_defaults`)
- **Type Variables**: Use `Type` suffix (e.g., `DocumentType`)

### Type Hints
- Always use type hints for function signatures
- Use `typing` imports: `from typing import Any, Dict, List, Optional`
- Use `Any` for flexible/dynamic types
- Return types: `-> Dict[str, Any]`, `-> None`, etc.

### Error Handling
- Raise specific exceptions (`ValueError`, `RuntimeError`)
- Log errors with context: `self.logger.error(f"message: {var}")`
- Use traceback for debugging: `traceback.format_exc()`
- Never swallow exceptions silently

### Partition Key
- **Critical**: Every request must use `partition_key = "{endpoint_id}#{part_id}"`
- Pass via context, never as client argument
- Validate presence: raise `ValueError` if missing

### GraphQL Patterns
- Define types in `types/` directory (e.g., `DocumentType`)
- Mutations in `mutations/` directory
- Queries in `queries/` directory
- Use `ResolveInfo` for context access
- Return `Promise` for async resolvers

### Model Patterns
- DynamoDB models inherit from `BaseModel`
- Use decorators: `@insert_update_decorator`, `@resolve_list_decorator`
- Local secondary indexes for query patterns
- Cache with `@method_cache` from `silvaengine_utility`

### Testing
- Unit tests: No external dependencies, mock everything
- Integration tests: Use `@pytest.mark.integration`
- Fixtures in `conftest.py` (mock_logger, mock_info, partition_key)
- Test markers: `unit`, `integration`, `extract`, `search`

### Documentation
- Docstrings for classes and public methods
- Describe flow/steps in complex methods
- Keep line length reasonable (100-120 chars)

### Key Rules
1. Always include file headers
2. Use relative imports for internal modules
3. Type hint all function signatures
4. Handle errors explicitly with logging
5. Validate `partition_key` before operations
6. Never expose `partition_key` as GraphQL argument
7. Use lazy imports in `__init__.py` for heavy dependencies
8. Follow existing file organization (handlers/models/types/mutations/queries/utils)
