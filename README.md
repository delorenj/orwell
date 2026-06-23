# Triumph Clock-In Automation

Headless, stealth browser automation for the Triumph (Saashr) clock-in/clock-out portal.

## Stack

- [Camoufox](https://camoufox.com/) — anti-detect Firefox fork (C++-level fingerprint spoofing)
- [Playwright](https://playwright.dev/python/) — browser control
- `python-dotenv` — local credential management

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
# edit .env with your Triumph credentials
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

## Notes

- Credentials are read from `.env` and never committed (see `.gitignore`).
- The login script fills the visible password field (`PasswordView`); the portal's JavaScript copies it into the hidden `Password` field before submission.
- The clock-action script discovers buttons by text (`clock in`, `clock out`, etc.) so it can adapt if selectors change.
