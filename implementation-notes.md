# Implementation Notes

## 2026-05-20

- The plan and design spec files for entry-context system discovery are present as untracked workspace inputs. I am treating them as user-provided source material, not as implementation output to commit unless explicitly requested.
- Task 1 migration will use `down_revision = "004"` because `api/alembic/versions/004_add_fib_levels.py` already exists in the current repo.
- Task 1 migration uses `sa.Boolean()` for `is_rescue`; the plan snippet used `sa.Boolean`, but Alembic column types should be instantiated.
