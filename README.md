# HDLCode — Verilog Judge (Streamlit)

A working LeetCode-style judge for Verilog FSM problems, with real accounts (signup/login),
a profile page, and a leaderboard. 4 problems are included, each with a verified reference
solution and hidden testbench that actually ran and passed against **real Icarus Verilog**
during development — not just described.

Problems: ATM PIN lockout (banking), Wayne Vault overlapping sequence detector (superheroes,
hard), traffic light with pedestrian + emergency priority (real-world), Infinity Stone vending
machine with greedy change-making (superheroes).

## Files

```
app/
  app.py                        Streamlit UI — auth gate, problem browser, editor, profile, leaderboard
  auth.py                       Signup/login: password hashing, temp-password generation, email sending
  problems.py                   Problem bank: statements, interfaces, starter code, hidden testbenches
  judge.py                      Compiles + simulates submissions with iverilog/vvp, 10s timeout
  db.py                         SQLite: users, submissions, solved problems, leaderboard
  requirements.txt              Python deps
  packages.txt                  apt package (iverilog) — used by Streamlit Community Cloud
  .streamlit/secrets.toml.example   Template for SMTP email config (copy & fill in, see below)
```

## 1. Run it locally

**Requirements:** Python 3.9+, Icarus Verilog.

Install Icarus Verilog:
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y iverilog
# macOS
brew install icarus-verilog
# Windows: download the installer from https://bleyer.org/icarus/
# (check "add to PATH" during install, then open a NEW terminal and run `iverilog -V` to confirm)
```

Install Python deps and run:
```bash
cd app
pip install -r requirements.txt
streamlit run app.py
```

## 2. Set up email for signup (optional but recommended)

On signup, HDLCode generates a temp password (`username` + 3 random digits) and emails it to the
address the user gave. To actually send that email, configure SMTP:

```bash
cd app
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit .streamlit/secrets.toml with real SMTP credentials (Gmail app password, SendGrid, etc.
# — instructions are in the file's comments)
```

**If you skip this step:** the app still works — signup falls back to showing the temp password
directly on-screen instead of emailing it. That's fine for testing locally by yourself, but it
means anyone who can see the signup screen sees the password, so don't rely on that fallback once
real strangers can reach the app.

On Streamlit Community Cloud, don't commit `secrets.toml` to GitHub — instead paste the same
`[smtp]` block into your app's **Settings → Secrets** in the Streamlit Cloud dashboard.

## 3. Make it public — free, no domain needed

1. **Push to GitHub** (from the folder containing `app/`):
   ```bash
   git init
   git add .
   git commit -m "HDLCode"
   git branch -M main
   git remote add origin https://github.com/<you>/hdlcode.git
   git push -u origin main
   ```
   Make sure `.streamlit/secrets.toml` (your real one, if you made it) is in `.gitignore` —
   never commit real credentials.

2. **Deploy on Streamlit Community Cloud** (share.streamlit.io):
   - Sign in with GitHub, click "New app", pick your repo, set **Main file path** to `app/app.py`.
   - Add your SMTP secrets under Settings → Secrets (same `[smtp]` block as the example file).
   - Deploy. You get a free public URL like `https://your-app-name.streamlit.app`.

3. **Free tier limits:** apps sleep after inactivity (cold start ~10-30s on next visit), and the
   SQLite file is not guaranteed to survive redeploys on that tier — for a permanent user
   database move to a hosted Postgres (Neon/Supabase free tier) later; only `db.py` would need
   to change.

## 4. Security status if you deploy this publicly — read this before you do

I built this with real password hashing and a sensible signup flow, but I want to be direct about
what is and isn't hardened, so you can decide what's acceptable for your use case (a few friends
vs. the open internet).

**What's solid:**
- Passwords are never stored in plaintext. They're hashed with PBKDF2-HMAC-SHA256, 100,000
  iterations, a random salt per user — this is a real, standard approach, not toy code.
- The temp password generated at signup exists in plaintext only transiently (in memory and in
  the outgoing email) — it's never written to disk.
- Users are forced to set their own password on first login, so the emailed temp password has a
  short useful life.
- The judge itself has a 10-second wall-clock timeout so a submitted infinite loop can't hang the
  server.
- Username changes cascade correctly to submission history and solved-problem records (tested).

**What's genuinely weak, and why:**
- **No email verification loop.** Signup emails the password to whatever address is typed in —
  there's no "click this link to confirm" step. In practice this means: (a) someone could sign up
  using an email address that isn't theirs, and the real owner would just receive an unsolicited
  password (annoying, not dangerous, since they can't log in without knowing the username too and
  the account is otherwise inert); (b) there's no protection against someone spamming the signup
  form to mass-email strangers. Consider adding a rate limit on signups per IP if you expect abuse.
- **No password reset flow.** If a user forgets their password after changing it from the temp
  one, there's currently no "forgot password" button — you'd need to reset it manually via the
  database. Worth adding before real users depend on this.
- **No rate limiting on login attempts.** Nothing currently stops repeated password guessing
  against a known username. For a small trusted group this is low risk; for a public deployment
  you'd want to add a lockout or delay after N failed attempts (this is a very solvable follow-up
  — same pattern as the ATM PIN lockout problem in the judge, incidentally).
- **HTTPS depends on your host, not this code.** Streamlit Community Cloud serves over HTTPS by
  default, so this is handled for you there. If you self-host on a bare VPS without a reverse
  proxy + TLS cert, passwords would travel in plaintext over the network — don't do that.
- **SQLite is a single file with no row-level access control.** Fine for a small judge; if this
  grows to handle sensitive data or many concurrent writers, move to a real database with proper
  connection pooling.
- **The judge compiles/runs whatever Verilog a logged-in user submits.** Icarus Verilog simulation
  is far more contained than arbitrary code execution (no filesystem/network syscalls available to
  simulated HDL), but it's still worth knowing that adding auth doesn't reduce this surface — it
  just tells you *who* submitted something. Streamlit Community Cloud already runs each app in its
  own sandboxed container, which helps here by default.

**Bottom line:** as shipped, this is appropriate for a personal project, a classroom, or a small
group of people who trust each other — which sounds like your actual use case. If you ever plan to
open this to the general public at scale, the two things I'd prioritize first are (1) a login
rate limit / lockout, and (2) an email-verification-before-account-is-usable step, since those are
the two gaps above that scale badly with a large, untrusted user base.

## 5. Adding more problems

Each entry in `problems.py`'s `PROBLEMS` list needs: `id`, `title`, `theme`, `difficulty`, `skill`,
`statement` (markdown), `interface` (exact module signature), `starter` (incomplete code with
TODOs), `testbench` (must print `RESULT:PASS` or `RESULT:FAIL` — that's the only contract
`judge.py` looks for), and `hints` (list of strings). Verify your reference solution against your
testbench with plain `iverilog -g2012 -o sim solution.v testbench.v && vvp sim` before adding it —
exactly how the 4 included problems were built and checked.
