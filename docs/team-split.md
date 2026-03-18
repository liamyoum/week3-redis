# Team Split

## Ownership

- Team member 1: `app/core`, `tests/core`
- Team member 2: `app/engine`, `tests/engine`
- Team member 3: `app/api`, `tests/integration`
- Team member 4: `app/persistence`, `scripts`, `README.md`

## Shared Contract Area

The following files are shared contracts and should not be changed inside a
feature branch without a dedicated contract update PR:

- `app/domain/models.py`
- `app/domain/contracts.py`
- `app/domain/schemas.py`
- `pyproject.toml`
- `Makefile`

## Dependency Direction

- `app/api -> app/engine -> app/core`
- `app/persistence -> app/domain`
- `tests/integration -> public HTTP API`

Reverse imports are not allowed.

## Merge Rules

- Freeze the public API before implementation
- Avoid touching another member's package unless explicitly coordinated
- If a shared contract must change, land that change first in a separate PR
