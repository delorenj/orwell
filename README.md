# Orwell

Orwell is headless, stealth browser automation for the Triumph (Saashr) clock-in/clock-out portal.

## Stack

- [Camoufox](https://camoufox.com/) — anti-detect Firefox fork (C++-level fingerprint spoofing)
- [Playwright](https://playwright.dev/python/) — browser control
- `python-dotenv` — local credential management
- `pyotp` — TOTP code generation for MFA

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
camoufox fetch
```

## Configure credentials

```bash
cp .env.example .env
# edit .env with your Triumph credentials and TOTP secret
```

The `.env` needs three values:

```dotenv
TRIUMPH_USERNAME=your_username
TRIUMPH_PASSWORD=your_password
TRIUMPH_TOTP_SECRET=YOUR_TOTP_SECRET
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

Implementation notes:

- This uses n8n's documented programmatic node shape with a `description` object plus `execute()` method.
- The package registers its compiled node through the `n8n.nodes` array in `package.json`.

Sources:

- https://docs.n8n.io/integrations/creating-nodes/build/reference/node-base-files/structure
- https://docs.n8n.io/integrations/creating-nodes/build/programmatic-style-node
- https://github.com/n8n-io/n8n-nodes-starter

## Notes

- Credentials are read from `.env` and never committed (see `.gitignore`).
- The login script fills the visible password field (`PasswordView`); the portal's JavaScript copies it into the hidden `Password` field before submission.
- MFA is handled automatically: the script selects the **Authenticator app** option, generates a TOTP code from `TRIUMPH_TOTP_SECRET`, and submits it.
- The clock-action script discovers buttons by text (`clock in`, `clock out`, etc.) and confirms any missing-punch warning dialog by clicking **Save**.
- To avoid re-entering MFA on every run, the script checks **Remember this device for 30 days** during MFA.
