# CLAUDE.md

## Git workflow

- Keep branch history linear. When a feature branch falls behind `main`, use `git rebase origin/main`, not `git merge origin/main`.
- Never create merge commits on feature branches — they block GitHub's "Rebase and merge" option on the PR.
- After rebasing, push with `git push --force-with-lease origin <branch-name>`.
- `dashboard/index.html` is generated from `data/history.json` via `python3 scripts/build_dashboard.py`. On a rebase conflict in this file, don't hand-resolve conflict markers — re-run the build script after each conflicting commit is otherwise resolved, then `git add` the regenerated file and continue the rebase.
