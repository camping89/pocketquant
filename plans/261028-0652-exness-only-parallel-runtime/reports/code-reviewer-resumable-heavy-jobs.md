# Code review: resumable heavy jobs across a worker handover

Date: 2026-10-30. Reviewer: code-reviewer subagent (first diff). Resolution: controller session.

Result: nothing critical. Three medium findings and five low ones. Bar writes use `upsert=True`, so a duplicate write converges and no finding corrupts bar data.

## Findings and resolution

| # | Finding | Resolution |
|---|---------|------------|
| M1 | The cron run and the catch-up of one job have different APScheduler ids, so `max_instances=1` does not stop them running at once. | Fixed. `_RUNNING` is keyed by job name. A second run of a running job logs WARNING `job.already_running` and returns. |
| M2 | A claimed row had no owner. A stopped process could write `interrupted` or `completed` late onto a row the new worker had resumed. | Fixed. Every run write filters on `run_id`, and a resume gives the row a new `run_id`, so a late write under the old id changes nothing. `stop_running_jobs` logs ERROR `jobs.not_stopped` when a cancelled task is still alive after 5 s. |
| M3 | A later cron run could claim an older cycle's interrupted row and skip the symbols that cycle finished. | Fixed. Only the catch-up resumes (`resume=True`). A fresh heavy run, and every resume, closes the job's other interrupted rows (`failed`, `superseded`). |
| L1 | `$inc` totals in `record_finish` never took effect, and the comment and test described a path that does not exist. | Fixed. Back to `$set`. The test was replaced by a late-write test. |
| L2 | Every `CancelledError` was swallowed, and the comment named one cause of several. | Fixed. `_tracked` swallows it only when `task.cancelling()` is true. The comment names the worker stop, the lost lease and shutdown. A test proves that a stray `CancelledError` propagates. |
| L3 | A cancel before the body starts reaches APScheduler as a failure, and a claimed row stays `running` until the next takeover. | Accepted. The next takeover marks the row `interrupted` and a catch-up resumes it. |
| L4 | The web type did not know `interrupted`. | Fixed. `'interrupted'` was added to `JobRunStatus`. The row is transient: the catch-up resumes the same row under a new `run_id`. |
| L5 | `mark_symbol_done_failed` had no run id; on a resumed run, `duration_ms` covers only the last part; non-heavy bodies take an unused parameter. | Fixed (`run_id` is logged); the other two are accepted. |

## Checked facts (reviewer)

- APScheduler 3.11.2 counts `max_instances` per job id.
- `run_coroutine_job` catches `BaseException`.
- `AsyncIOExecutor.shutdown` cancels pending job tasks.
- A symbol is marked done only when all its intervals complete, or when its market is closed. An exception skips the mark, and a cancel in the middle of a symbol leaves it unmarked.
