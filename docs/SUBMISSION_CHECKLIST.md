# Final submission checklist

## Code
- [ ] All branches merged into `main` through reviewed pull requests
- [ ] `python -m pytest -q` → all tests pass
- [ ] `python -m pyflakes app tests` → no warnings
- [ ] Fresh clone works: install → `.env` → `flask --app wsgi seed` → `flask --app wsgi run`
- [ ] No secrets in the repo: search for `AI_API_KEY=`, passwords, tokens; `.env` is not tracked
- [ ] `.gitignore` excludes `.env`, `instance/`, `uploads/*`, `.venv/`
- [ ] `requirements.txt` installs on a clean environment

## Features working (tick after seeing them work yourselves)
- [ ] Landing, discovery, event detail
- [ ] Register → Registration ID → QR
- [ ] QR scan: success, duplicate, invalid, wrong event
- [ ] Student registers, is verified by the Organizer, sees the blue badge
- [ ] Faculty manage the Organizer account; Organizer manages the Logistics account
- [ ] Organizer lifecycle: draft → submit → faculty approve → publish → complete → certificates
- [ ] PDF upload → AI answers from it → AI refuses unsupported question
- [ ] Logistics checklist and readiness percentage
- [ ] Certificates: issue, download, verify
- [ ] Volunteering, announcements, achievements, notifications
- [ ] Analytics for organizer and faculty
- [ ] 403 / 404 / 500 pages styled

## Documentation (all in this repository)
- [ ] `README.md` complete and accurate (screenshots added if wanted)
- [ ] `docs/USER_MANUAL.md`
- [ ] `docs/DEVELOPER_MANUAL.md`
- [ ] `docs/DEPLOYMENT_MANUAL.md` (limits re-checked on the day you deploy)
- [ ] `docs/GITHUB_MANUAL.md`
- [ ] `docs/FIVE_DAY_PLAN.md` updated with what you really did
- [ ] `docs/DEMO_SCRIPT.md` rehearsed twice with timing
- [ ] `docs/TESTING_CHECKLIST.md` completed, with issues for anything found
- [ ] `docs/DATABASE.md`

## GitHub evidence
- [ ] Issues created and closed through pull requests
- [ ] Genuine commits, made as you did the work, on feature branches
- [ ] Pull requests opened for each feature branch (you may review and merge your own; read the diff first)
- [ ] `main` protected (pull request required); Contributors page shows your account
- [ ] Release tag created (`git tag v1.0 && git push --tags`)

## Presentation
- [ ] Demo data reset right before presenting (`seed --reset`)
- [ ] Phone charged; QR page ready; camera permission tested on the demo device
- [ ] Backup plan: local run if the hosted site is slow; screenshots saved
- [ ] Everyone can explain their own area and one design decision
- [ ] Honest answers prepared for the limitations listed in the README
