import os
import sys

import pyotp
from dotenv import load_dotenv

load_dotenv()

TARGET = (
    "https://secure5.saashr.com/ta/CH50003.home?rnd=TUZ&showAdmin=1"
    "&Ext=login&sft=HOSCCFOFIU&ActiveSessionId=25425500678#time/timesheet/timesheets"
    "?tab=TIME_ENTRY&tsId=21935049240"
)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Error: {name} is not set. Add it to .env.", file=sys.stderr)
        sys.exit(1)
    return value


def get_totp_code() -> str:
    secret = os.environ.get("TRIUMPH_TOTP_SECRET")
    if not secret:
        return ""
    return pyotp.TOTP(secret).now()


async def log_in(page, username: str | None = None, password: str | None = None):
    if username is None:
        username = require_env("TRIUMPH_USERNAME")
    if password is None:
        password = require_env("TRIUMPH_PASSWORD")

    await page.goto(TARGET, wait_until="networkidle")

    await page.fill("input[name='Username']", username)
    await page.fill("input[name='PasswordView']", password)
    await page.click("button[name='LoginButton']")
    await page.wait_for_load_state("networkidle")

    # Handle MFA challenge if presented.
    if "isMFALogin=true" in page.url:
        await _handle_mfa(page)

    # Allow client-side rendering to settle.
    await page.wait_for_timeout(3000)


async def _handle_mfa(page):
    totp_code = get_totp_code()
    if not totp_code:
        raise RuntimeError("MFA required but TRIUMPH_TOTP_SECRET is not set")

    # Select the authenticator-app option. The radios drive visibility via inline
    # onclick handlers, so mirror that logic directly and check the radio.
    await page.evaluate("""() => {
        const r = document.getElementById('authRadio');
        r.checked = true;
        const text = document.getElementById('text');
        const voice = document.getElementById('voice');
        const email = document.getElementById('email');
        const submitButton = document.getElementById('submitButton');
        const continueButton = document.getElementById('continueButton');
        const authenticator = document.getElementById('authenticator');
        const tandc = document.getElementById('tandc');
        if (text) text.style.display = 'none';
        if (voice) voice.style.display = 'none';
        if (email) email.style.display = 'none';
        if (submitButton) submitButton.style.display = 'none';
        if (continueButton) continueButton.style.display = 'block';
        if (authenticator) authenticator.style.display = 'block';
        if (tandc) tandc.style.display = 'none';
    }""")
    await page.wait_for_timeout(500)
    await page.click("button#continueButton", force=True)
    await page.wait_for_load_state("networkidle")

    # Wait for the verification-code input to appear.
    await page.wait_for_selector("input[name='VerificationCode']", state="visible")
    await page.fill("input[name='VerificationCode']", totp_code)

    # Remember this device so future logins skip MFA.
    try:
        await page.check("input#RememberDevice")
    except Exception:
        pass

    # The Verify button starts disabled; use a JS click to submit the form.
    await page.evaluate("""() => {
        const btn = document.getElementById('AuthenticateTOTPButton');
        if (btn) { btn.disabled = false; btn.click(); }
    }""")
    await page.wait_for_load_state("networkidle")
