# Orwell

Orwell is headless, stealth browser automation for the Triumph (Saashr) clock-in/clock-out portal.

## Stack

- [Camoufox](https://camoufox.com/) — anti-detect Firefox fork (C++-level fingerprint spoofing)
- [Playwright](https://playwright.dev/python/) — browser control
- `python-dotenv` — local credential management
- `pyotp` — TOTP code generation for MFA

## Setup

```bash
mise x -- uv venv --python 3.12 .venv
mise x -- uv pip install --python .venv/bin/python -r requirements.txt pytest
.venv/bin/python -m camoufox fetch     # browser into ~/.cache/camoufox
.venv/bin/python -m pytest -q tests
```

The `.venv` is load-bearing: the n8n Orwell node runs `<repo>/.venv/bin/python`
and falls back to `python3` from n8n's PATH, which has none of these packages.
When the venv went missing, every Safe Clock-In/Out failed with
`ModuleNotFoundError: No module named 'camoufox'` (found 2026-11-06).
`requirements.txt` pins the versions verified against the portal.

## Configure credentials

```bash
cp .env.example .env
```

`.env` holds 1Password references, never values. `scripts/auth.py` resolves each
`op://` value with `op read` at run time, using `OP_SERVICE_ACCOUNT_TOKEN` (n8n's
launcher exports it) or your op session. The item is "Orwell - Triumph timesheet
portal (saashr)" in DeLoSecrets:

```dotenv
TRIUMPH_USERNAME="op://DeLoSecrets/hgtmc5r5l7f7w5iul3rwtljvsy/username"
TRIUMPH_PASSWORD="op://DeLoSecrets/hgtmc5r5l7f7w5iul3rwtljvsy/password"
TRIUMPH_TOTP_SECRET="op://DeLoSecrets/hgtmc5r5l7f7w5iul3rwtljvsy/totp secret"
```

## Usage

Inspect the portal and dump interactive elements:

```bash
python scripts/01_inspect_portal.py
```

Log in and capture a screenshot of the post-login view:

```bash
python scripts/02_login_flow.py
```

Clock in or clock out:

```bash
python scripts/03_clock_action.py in
python scripts/03_clock_action.py out
```

All screenshots are written to `outputs/`.

## n8n node

This repo now includes a custom n8n node package under `nodes/Orwell/` and `dist/`.

Build it with:

```bash
npm install
npm run build
```

The node exposes one Orwell node with two operations:

- `Clock In`
- `Clock Out`

Runtime parameters:

- `Repository Path` — absolute path to the Orwell repo
- `Python Path` — optional override for the Python executable
- `Timeout Seconds` — max wait for the browser automation run

The node executes `scripts/03_clock_action.py` and returns the action, paths, stdout, stderr, and screenshot path in the n8n item output.

### Scheduling

The weekday clock-in/out schedule that used to run from system `crontab` is now handled by the n8n workflow in `workflows/orwell-clock-in-out.json`.

- **Clock In** — weekdays at 08:27 with a random 0–23 min jitter, plus a retry at 08:52.
- **Clock Out** — weekdays at 16:00 with a random 0–23 min jitter, plus a retry at 16:25.

Each branch first reads the current Orwell state and only performs the action if the state supports it, so retries are safe.

To reinstall after changes:

```bash
n8n import:workflow --input=workflows/orwell-clock-in-out.json
```

Implementation notes:

- This uses n8n's documented programmatic node shape with a `description` object plus `execute()` method.
- The package registers its compiled node through the `n8n.nodes` array in `package.json`.

Sources:

- https://docs.n8n.io/integrations/creating-nodes/build/reference/node-base-files/structure
- https://docs.n8n.io/integrations/creating-nodes/build/programmatic-style-node
- https://github.com/n8n-io/n8n-nodes-starter

## Notes

- Credentials live in 1Password; `.env` carries only `op://` references.
- The login script fills the visible password field (`PasswordView`); the portal's JavaScript copies it into the hidden `Password` field before submission.
- MFA is handled automatically: the script selects the **Authenticator app** option, generates a TOTP code from `TRIUMPH_TOTP_SECRET`, and submits it.
- The clock-action script discovers buttons by text (`clock in`, `clock out`, etc.) and confirms any missing-punch warning dialog by clicking **Save**.
- To avoid re-entering MFA on every run, the script checks **Remember this device for 30 days** during MFA.
