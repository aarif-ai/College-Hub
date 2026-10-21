# Git and GitHub manual (beginner friendly)

## The words you need

| Word | Meaning |
|------|---------|
| **Repository (repo)** | The project folder plus its full history, stored on GitHub |
| **Clone** | Copy the repo from GitHub to your computer |
| **Branch** | A separate line of work so your changes do not disturb others |
| **Commit** | A saved snapshot with a message |
| **Push** | Send your commits to GitHub |
| **Pull** | Bring other people's new commits to your computer |
| **Pull request (PR)** | A request to merge your branch into `main`, where you read the diff before merging it |
| **Review** | Reading the *Files changed* tab line by line before merging (a classmate or mentor can review too) |
| **Merge** | Combine the branch into `main` |
| **Conflict** | Two people changed the same lines; you decide what to keep |
| **Issue** | A tracked task, bug or idea |

## One-time setup

```bash
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
git clone https://github.com/<owner>/collegehub.git
cd collegehub
```

You create the repo once and push the first commit. Optionally add a classmate or your mentor under **Settings → Collaborators** so they can review.

## Branches for this project

You are the only developer, so keep it simple: `main` always works, and each piece of work gets a short branch.

| Branch | Use for |
|--------|---------|
| `feature/<topic>` | a new feature, e.g. `feature/member-verification` |
| `fix/<topic>` | a bug fix, e.g. `fix/scanner-duplicate-message` |
| `docs/<topic>` | documentation only |

```bash
git checkout main
git pull
git checkout -b feature/member-verification
```

## Daily workflow

```bash
git checkout main && git pull                 # 1. start from the latest main
git checkout -b feature/<topic>               # 2. one branch per piece of work
# ...edit files...
git status                                    # 3. what changed?
git add app/templates/student/dashboard.html  # 4. stage specific files
git commit -m "feat: add attendance card to student dashboard"
git push -u origin feature/<topic>            # 5. publish (first time with -u)
```

Commit small and often. Stage files by name (not `git add .`) so you never commit `.env`, the database or uploads.

## Commit messages

Format: `type: short description in the present tense`.

| Type | Use for |
|------|---------|
| `feat` | a new feature |
| `fix` | a bug fix |
| `docs` | documentation only |
| `test` | adding or fixing tests |
| `refactor` | restructuring without changing behaviour |
| `chore` | tooling, dependencies, config |
| `style` | formatting or CSS-only changes |

Good: `fix: block duplicate QR scan for cancelled registration`. Bad: `changes`, `final`, `asdf`.

Commit history should be **genuine**: commit your own work as you do it. Do not back-date commits or rewrite history.

## Pull request, review, merge

1. Push your branch, then on GitHub press **Compare & pull request** (base: `main`).
2. Fill in the template: what changed, how you tested it, screenshots for UI.
3. Run `python -m pytest -q` first; the CI check must be green.
4. Read the **Files changed** tab yourself as if it were someone else's work (or ask a classmate or mentor to review). Look for secrets, stray files and missing tests.
5. When approved and green, press **Squash and merge** (or *Merge*). Delete the branch.
6. Locally: `git checkout main && git pull`.

**Reviewing**: Does it run? Is any secret or generated file included? Are tests added for new rules? Is the UI consistent with the design system?

## Conflicts

A conflict appears when you `git merge main` and both changed the same lines:

```
<<<<<<< HEAD
your version
=======
their version
>>>>>>> main
```

1. Open the file, decide the final text, delete the three marker lines.
2. `git add <file>` then `git commit` (Git writes the merge message).
3. Run the tests. If unsure which version is right, check the PR that introduced each side.

Working alone, conflicts are rare; they mostly happen when you edit the same file on two branches. Merge each branch before starting the next.

## Issues

Create an issue for every task or bug: a clear title, steps to reproduce (for bugs), and an assignee. Reference it in the PR with `Closes #12` so it closes on merge. Suggested labels: `backend`, `frontend`, `bug`, `docs`, `good first issue`.

## Protect `main`

Repository **Settings → Branches → Add rule** for `main`:
- Require a pull request before merging (set approvals to 0 if you are the only collaborator)
- Require status checks to pass (the *CI* workflow)
- Do not allow force pushes

Nobody commits straight to `main` after the first commit.

## What must never be committed

`.env`, API keys, `instance/*.db`, `uploads/*`, `.venv/`, `__pycache__/`. They are listed in `.gitignore`. If you commit a secret by mistake, **change the secret immediately**; deleting it in a later commit does not remove it from history.

## Cheat sheet

```bash
git status                  git log --oneline --graph -10
git diff                    git restore <file>        # discard unstaged edits
git stash / git stash pop   git branch -a
```
