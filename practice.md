# How we work on this project

Read [spec.md](spec.md) and [architecture.md](architecture.md) before making any change.

## The board

- **GitHub Project** with three columns: **To do → In progress → Done**. Every card is an Issue.
- **Milestones:** `v1 data` · `v2 dashboard` · `v3 agent`.
- **Labels:** `feature`, `bug`, `docs`.
- Every Issue uses this format:

```
Title         <one change a stranger could test>
Milestone     v1 / v2 / v3        Label  feature / bug
Why           spec.md §<n>: <the line it serves>
Done when     - <check from spec.md §7>
              - ...
Test          tests/test_<name>.py (model mocked)
Out of scope  <what this ticket does NOT do, with #numbers>
```

## On every ticket — 8 steps

1. **Read the issue.** Restate it in one line. If it is outside spec.md, or anything is unclear, stop and ask. Do not guess.
2. **Plan.** Write 3–5 lines and name the files. Wait for approval before building.
3. **Branch.** `git checkout -b <issue#>-<short-name>`, for example `1-load-data`. One ticket, one branch.
4. **Build** the smallest change that meets "Done when". Nothing beyond the ticket.
5. **Test.** Run `pytest`. Add the ticket's test, taken from "Done when". If the prompt, the tool or the model changed, also run `python evals/run_evals.py` before and after.
6. **Docs.** If a decision changed, update architecture.md (the Decisions table). If a feature changed, update spec.md.
7. **Commit** with the issue number, for example `Load Kaggle CSV into Postgres (#1)`. One ticket, one commit, or a few small ones on the same branch.
8. **PR** to `main`, with `Closes #<n>` and the three numbers pasted in:
   - tests passed (e.g. `12 passed`)
   - eval pass rate vs. the previous run (e.g. `9/10, was 7/10`)
   - tokens per eval run (e.g. `14.2k`)

   Merge only when CI is green. Delete the branch after merging.

## Side door: bugs found along the way

A bug that is not part of the current ticket must not be fixed silently in the wrong branch. Open a new Issue labelled `bug` (steps, expected, actual), link it to the ticket you were working on, and carry on. It gets its own branch, `<n>-fix-<short-name>`.

## Never

- push to `main` (it is protected; everything goes through a PR)
- edit or commit `.env`, or put a key or database URL in code
- edit anything in `data/raw/` (the Kaggle files) or `data/sales.csv` by hand. To change the data, change `mock_data.py`
- skip step 5 to get green
- let the agent run SQL it wrote itself

## When this process goes wrong

If a step gets skipped or done incorrectly, fix this file, not just the chat. This file is read every session, so a fix here holds for every future ticket.
