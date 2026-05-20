# Implementation Notes

## 2026-05-20

- The plan and design spec files for entry-context system discovery are present as untracked workspace inputs. I am treating them as user-provided source material, not as implementation output to commit unless explicitly requested.
- Task 1 migration will use `down_revision = "004"` because `api/alembic/versions/004_add_fib_levels.py` already exists in the current repo.
- Task 1 migration uses `sa.Boolean()` for `is_rescue`; the plan snippet used `sa.Boolean`, but Alembic column types should be instantiated.
- Task 4 cannot produce a failing test first without undoing Task 3 because the Task 3 plan skeleton already implements `_fill_entry_candle`. I am following the plan's Task 4 expected result (tests pass after adding them) and recording this as a TDD deviation.
- Task 6 kept GET `/api/trades` default `limit` at 50 instead of changing it to 20, preserving the existing API behavior while adding `offset`.
- Task 11 uses the existing `_assign_session` boundaries with ICT-converted hours. The plan comment says UTC 10:00 / ICT 17:00 is London, but the existing classifier maps hour 17 to NY, so the test avoids asserting the session label.
- Task 11 normalizes naive datetimes to UTC before ICT conversion because SQLite test rows can lose `tzinfo`; this matches the existing `time_bias` UTC interpretation.
