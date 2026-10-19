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
| **Pull request (PR)** | A request to merge your branch into `main`, where teammates review it |
| **Review** | A teammate reads your changes and approves or asks for fixes |
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

The repository owner creates the repo once, pushes the first commit, and adds teammates under **Settings → Collaborators**.

## Branches for this project

| Person | Branch |
|--------|--------|
| Aarif | `feature/aarif-backend` |
| Abrar | `feature/abrar-frontend` |
| Mishar | `feature/mishar-organizer` |
| Hameem | `feature/hameem-faculty` |

Create yours once, then keep working on it:

```bash
git checkout main
git pull
git checkout -b feature/abrar-frontend
```

For small separate tasks you may also create short branches such as `fix/scanner-duplicate-message` or `docs/user-manual`.

## Daily workflow

```bash
git checkout main && git pull                 # 1. start from the latest main
git checkout feature/abrar-frontend           # 2. go to your branch
git merge main                                # 3. bring main's news into your branch
# ...edit files...
git status                                    # 4. what changed?
git add app/templates/student/dashboard.html  # 5. stage specific files
git commit -m "feat: add attendance card to student dashboard"
git push -u origin feature/abrar-frontend     # 6. publish (first time with -u)
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

Commit history should be **genuine**: each person commits their own work as they do it. Do not rewrite or fabricate history.

## Pull request, review, merge

1. Push your branch, then on GitHub press **Compare & pull request** (base: `main`).
2. Fill in the template: what changed, how you tested it, screenshots for UI.
3. Run `python -m pytest -q` first; the CI check must be green.
4. Request a review from a teammate. Reviewers read the **Files changed** tab, comment on lines, then **Approve** or **Request changes**.
5. When approved and green, press **Squash and merge** (or *Merge*). Delete the branch.
6. Everyone runs `git checkout main && git pull`.

**Reviewing**: Does it run? Does it follow the file-ownership map? Is any secret or generated file included? Are tests added for new rules? Is the UI consistent with the design system?

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
3. Run the tests. If unsure, ask the other person; do not just pick your side.

The ownership map in `docs/FIVE_DAY_PLAN.md` exists to make conflicts rare. Shared files (`app/static/css/app.css`, `app/templates/components/macros.html`, `app/models.py`) change only through a short PR that others review quickly.

## Issues

Create an issue for every task or bug: a clear title, steps to reproduce (for bugs), and an assignee. Reference it in the PR with `Closes #12` so it closes on merge. Suggested labels: `backend`, `frontend`, `bug`, `docs`, `good first issue`.

## Protect `main`

Repository **Settings → Branches → Add rule** for `main`:
- Require a pull request before merging (1 approval)
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
