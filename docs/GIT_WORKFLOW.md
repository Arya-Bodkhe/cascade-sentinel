# Git workflow for two people

Branches: `main` (always demo-able, tagged) <- `develop` (integration) <- `feat/<area>-<name>` (one per task, short-lived).

## One-time setup
```bash
# Person A (after creating an EMPTY remote repo)
git init -b main
git add . && git commit -m "chore: import scaffold"
git remote add origin <URL>
git push -u origin main
git switch -c develop && git push -u origin develop

# Person B
git clone <URL> && cd cascade-sentinel
git switch develop
git config user.name "Person B" && git config user.email "b@example.com"
```
Add the teammate as a collaborator (GitHub: Settings -> Collaborators). Protect `main`: require PR + passing CI.

## Daily loop (both people)
```bash
git switch develop && git pull --rebase origin develop      # start from the latest
git switch -c feat/sim-twin-generator                        # A example
# ... edit, run `python tests/run_tests.py` ...
git add -p                                                   # stage deliberately
git commit -m "feat(sim): twin generator with identical 7-minute prefix"
git fetch origin && git rebase origin/develop                # replay your work on top of theirs
git push -u origin feat/sim-twin-generator
# open a Pull Request into develop; the other person reviews; squash-merge
git switch develop && git pull --rebase origin develop
git branch -d feat/sim-twin-generator
```

## Branch names each person will use
| Person A | Person B |
|---|---|
| `feat/sim-world`, `feat/sim-stressors`, `feat/sim-twins` | `feat/belief-grid-filter`, `feat/belief-gateway-rumor`, `feat/belief-calibration` |
| `feat/ingest-quarantine`, `feat/ledger-hashchain` | `feat/policy-cost-hysteresis`, `feat/foresight-causal` |
| `feat/ui-panels`, `feat/ui-replay-lab`, `docs/readme-demo` | `feat/learning-trust-bocpd`, `feat/eval-baselines`, `feat/eval-report` |

## Commit message convention
`feat(scope): ...`, `fix(scope): ...`, `test(scope): ...`, `docs: ...`, `chore: ...`, `perf(scope): ...`
Examples: `feat(belief): gateway common-cause node`, `fix(sim): twin prefix ids identical`, `test(ingest): shuffle invariance`.

## Sync points (merge `develop` into `main` and tag)
```bash
git switch main && git pull --rebase origin main
git merge --no-ff develop -m "release: S1 engine runs on simulator"
git tag -a s1 -m "sync point 1" && git push origin main --tags
git switch develop
```

## Conflicts
```bash
git fetch origin && git rebase origin/develop
# on conflict: edit files, remove <<<<<<< markers
git add <file> && git rebase --continue          # or: git rebase --abort
```
Because directories have single owners, conflicts should only appear in `src/common/model.py` and `src/runtime.py`. Message each other before touching those.

## Useful safety commands
```bash
git status -sb                      # what changed
git log --oneline --graph --all -20 # history picture
git stash push -m "wip" && git stash pop
git restore <file>                  # discard local edits to a file
git revert <commit>                 # undo a merged commit safely (never force-push main)
git tag -a v1.0 -m "final demo" && git push origin v1.0
```
Never commit: `.env`, API keys, large raw datasets (put them in `data/` and list sources/licences in `docs/DATA_NOTES.md`).
