import os
import sys

import pyotp
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://secure5.saashr.com/ta/CH50003.home?showAdmin=1&Ext=login&sft=HOSCCFOFIU"
TIMESHEET_HASH = "time/timesheet/timesheets?tab=TIME_ENTRY"
LOGIN_FORM_SELECTOR = "input[name='Username']"
LOGIN_BUTTON_SELECTOR = "button[name='LoginButton']"
MFA_CODE_SELECTOR = "input[name='VerificationCode']"


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


async def navigate_to_login(page):
    await page.goto(BASE_URL, wait_until="domcontentloaded")
    await page.wait_for_selector(LOGIN_FORM_SELECTOR, state="visible")


async def navigate_to_timesheet(page):
    await page.evaluate(
        "(hash) => { window.location.hash = hash; }",
        TIMESHEET_HASH,
    )
    await page.wait_for_function(
        "(hash) => window.location.hash.includes(hash)",
        arg=TIMESHEET_HASH,
    )
    await page.wait_for_load_state("networkidle")
    await _wait_for_authenticated_page(page)


async def log_in(page, username: str | None = None, password: str | None = None):
    if username is None:
        username = require_env("TRIUMPH_USERNAME")
    if password is None:
        password = require_env("TRIUMPH_PASSWORD")

    await navigate_to_login(page)

    await page.fill("input[name='Username']", username)
    await page.fill("input[name='PasswordView']", password)
    await page.click(LOGIN_BUTTON_SELECTOR)
    await page.wait_for_load_state("networkidle")

    # Handle MFA challenge if presented.
    if await page.locator(MFA_CODE_SELECTOR).count() or "isMFALogin=true" in page.url:
        await _handle_mfa(page)

    await _wait_for_authenticated_page(page)


async def _handle_mfa(page):
    totp_code = get_totp_code()
    if not totp_code:
        raise RuntimeError("MFA required but TRIUMPH_TOTP_SECRET is not set")

    auth_radio = page.locator("#authRadio")
    if await auth_radio.count():
        await auth_radio.check(force=True)

    continue_button = page.locator("button#continueButton")
    if await continue_button.count():
        try:
            await continue_button.click(timeout=5_000)
        except Exception:
            await page.evaluate("""() => {
                const btn = document.getElementById('continueButton');
                if (btn) btn.click();
            }""")

    await page.wait_for_load_state("networkidle")

    await page.wait_for_selector(MFA_CODE_SELECTOR, state="visible")
    await page.fill(MFA_CODE_SELECTOR, totp_code)

    try:
        await page.check("input#RememberDevice")
    except Exception:
        pass

    verify_button = page.locator("button#AuthenticateTOTPButton")
    try:
        await verify_button.click(timeout=5_000)
    except Exception:
        await page.evaluate("""() => {
            const btn = document.getElementById('AuthenticateTOTPButton');
            if (btn) {
                btn.disabled = false;
                btn.click();
            }
        }""")

    await page.wait_for_load_state("networkidle")


async def _wait_for_authenticated_page(page):
    await page.wait_for_function(
        """([loginSelector, mfaSelector]) => {
            const loginInput = document.querySelector(loginSelector);
            const mfaInput = document.querySelector(mfaSelector);

            if (mfaInput && mfaInput.offsetParent !== null) {
                return false;
            }

            if (loginInput && loginInput.offsetParent !== null) {
                return false;
            }

            return Boolean(document.body && document.body.innerText.trim().length > 0);
        }""",
        arg=[LOGIN_FORM_SELECTOR, MFA_CODE_SELECTOR],
        timeout=20_000,
    )

    login_input = page.locator(LOGIN_FORM_SELECTOR).first
    if await login_input.count() and await login_input.is_visible():
        raise RuntimeError("Login did not complete; username field is still visible")

    login_errors = [
        "invalid username or password",
        "authentication failed",
        "verification code is invalid",
        "unable to sign in",
        "login failed",
    ]
    page_text = (await page.locator("body").inner_text()).lower()
    for message in login_errors:
        if message in page_text:
            raise RuntimeError(f"Login failed: portal reported '{message}'")
