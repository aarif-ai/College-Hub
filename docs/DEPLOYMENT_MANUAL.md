# Deployment manual

Author: Aarif Mushtaq. A step-by-step PDF version, including the GitHub push for a solo developer, is `CollegeHub_Deployment_Guide.pdf` (delivered with the project).

Pick the route that matches your goal:

| Goal | Route |
|------|-------|
| Demo on your own laptop (recommended for the final presentation) | **A. Local deployment** |
| A public link to share | **B. Render + Neon (free tiers)** |

> Free-tier limits change. The figures below were checked against the providers' own pages on **21 October 2026**. Re-check them before you rely on them (links at the end).

---

## A. Local deployment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then set SECRET_KEY
flask --app wsgi seed
flask --app wsgi run --host 0.0.0.0 --port 5000
```

- Other devices on the same Wi-Fi can open `http://<your-laptop-ip>:5000`.
- The QR **camera** needs HTTPS or `localhost`. On a phone over plain HTTP, use the manual registration-ID box, or present from the laptop's own browser on `localhost`.
- For a production-like local run: `APP_ENV=production gunicorn wsgi:app` (Linux/macOS). On Windows use `waitress-serve --port 5000 wsgi:app` after `pip install waitress`. In production mode `SECRET_KEY` is mandatory and cookies are marked `Secure`, so use it only behind HTTPS.

---

## B. Render (web service) + Neon (PostgreSQL), both free

### What the free tiers actually give you

**Render free web service** (render.com/docs/free)
- Spins down after **15 minutes** without traffic; the next request takes about **1 minute** to wake it.
- **750 free instance hours** per month per workspace; if they run out, free services are suspended until next month.
- **Ephemeral filesystem**: local files are lost on every redeploy, restart *and spin-down*. No persistent disks.
- No SSH shell and no one-off jobs. **Outbound SMTP ports 25, 465 and 587 are blocked**, so CollegeHub cannot send password-reset e-mails from Render's free tier (see consequence 6).
- Rollbacks are limited to the two most recent previous deploys; Render may restart the service at any time.
- Render's own docs say not to use free services for production applications.

**Render free PostgreSQL**: 1 GB, but it **expires 30 days after creation**, with a 14-day grace period before the data is deleted. That is why this manual uses Neon for the database.

**Neon free plan** (neon.com/pricing): 1 GB storage per project (up to 100 projects), 100 compute-unit-hours per project, compute suspends after 5 minutes idle and this cannot be turned off (first query after idle is slower), no credit card, and the plan is described as permanent, not a trial.

### Consequences for CollegeHub

1. **Use an external PostgreSQL** (Neon). Do not use SQLite on Render: the database file would be wiped at every spin-down.
2. **Uploaded PDFs and cover images will disappear** when Render restarts or spins down. The text extracted from PDFs is stored in the database, so the **AI assistant keeps answering**, but the "Download" link for a PDF and uploaded cover images will break. For a demo: upload the documents shortly before presenting, or deploy locally. Long term: move uploads to object storage.
3. **Seeding must run from your own computer** (Render's free tier has no shell). Point `DATABASE_URL` at Neon on your machine and run `flask --app wsgi seed` there.
4. **Warm the site up** a minute before the demo by opening it once.
5. The login throttle is per process and resets on restart. This is acceptable for a demo.
6. **Password-reset e-mails cannot be sent** from the free tier (SMTP is blocked). Reset links are written to the Render log instead. For a short, supervised demo you may set `DEMO_SHOW_RESET_LINK=1` to show the link on screen, but this is **insecure** (anyone who knows a student's e-mail could reset the password); switch it off straight after. A real deployment needs an e-mail provider that allows SMTP on an open port or an HTTP e-mail API (not implemented in this project), or a paid host.

### Step by step

**1. Put the code on GitHub.** Make sure `.env`, `instance/` and `uploads/*` are not committed (they are in `.gitignore`).

**2. Create the database on Neon.**
1. Sign up at neon.com (no card needed), create a project, region close to your Render region.
2. Copy the connection string (`postgresql://user:password@host/dbname?sslmode=require`).

**3. Seed the database from your laptop.**
```bash
export DATABASE_URL="postgresql://...neon connection string..."
export DEMO_PASSWORD="choose-a-demo-password"      # do not keep the default on a public site
flask --app wsgi seed          # demo data (public demo only). NEVER use --reset on a database that holds real data: it drops every table.
# Real deployment without demo data: create the first Faculty Mentor instead
flask --app wsgi create-faculty --username dr_example --email faculty@your-college.example --name "Dr. Example"
```
(Windows PowerShell: `$env:DATABASE_URL="..."`.)

**4. Create the web service on Render.**
1. Render dashboard → **New → Web Service** → connect your GitHub repository.
2. Settings:
   - **Runtime**: Python
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `gunicorn wsgi:app --workers 2 --timeout 60`
   - **Instance type**: Free
3. **Environment variables**:

| Key | Value |
|-----|-------|
| `APP_ENV` | `production` |
| `SECRET_KEY` | a long random string (`python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | the Neon connection string |
| `PYTHON_VERSION` | a 3.11+ version supported by Render (check Render's Python docs for the current list) |
| `AI_API_KEY` | optional; leave unset for offline demo mode |

4. Click **Create Web Service**.

**5. Check it.** Open `https://<your-service>.onrender.com/healthz`. It should return `{"status":"ok"}`. Then log in with a demo account.

### Logs, updates and redeployment

- **Logs**: Render dashboard → your service → **Logs**.
- **Update**: push to the branch Render tracks (usually `main`). Render rebuilds and redeploys automatically. Manual redeploy: **Manual Deploy → Deploy latest commit**.
- **Rollback**: Render keeps previous deploys; choose an earlier one and redeploy it.
- **Upgrading from the earlier version**: the user table changed (`username`, `account_status`, `verification_status`, audit log, one-Organizer/one-Logistics indexes). Re-seed a demo database; for real data you must write an Alembic migration.
- **Changing models**: `create_all()` creates *new* tables but does not alter existing ones. If you add a column after the database holds data, use a migration tool (Alembic/Flask-Migrate) or re-seed a demo database.

### Production configuration checklist

- [ ] `APP_ENV=production` (hides debug pages, sets `Secure` cookies)
- [ ] Strong `SECRET_KEY` (the app refuses to start in production without one)
- [ ] `DATABASE_URL` points to PostgreSQL
- [ ] `DEMO_PASSWORD` changed before seeding, or demo accounts removed after the demo
- [ ] `DEMO_SHOW_RESET_LINK` unset (it shows reset links on screen)
- [ ] SMTP (`MAIL_*`) configured so students receive reset links; otherwise links go only to the server log
- [ ] `RESET_TOKEN_MAX_AGE` reviewed (default 1 hour)
- [ ] No `.env` or API key committed to Git
- [ ] `/healthz` returns ok

### Why not SQLite on cloud hosting?

SQLite stores everything in one file on the server's disk. On platforms with an ephemeral filesystem that file is erased on restart. Even where the disk persists, SQLite allows one writer at a time and cannot be shared by several server instances. PostgreSQL is a separate server that keeps data safely and serves many connections.

### Other hosts

PythonAnywhere's free account currently offers one web app that **expires after one month** (renewal needed), 512 MiB disk and 100 CPU-seconds, and its page does not state its database or outbound-network rules for free accounts. Check its documentation before choosing it.

### Sources checked

- Render free tier: https://render.com/docs/free
- Render free-tier overview: https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026
- Neon pricing: https://neon.com/pricing
- PythonAnywhere free accounts: https://help.pythonanywhere.com/pages/FreeAccountsFeatures/
