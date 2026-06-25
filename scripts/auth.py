import os
import sys

import pyotp
from dotenv import load_dotenv
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

load_dotenv()

BASE_URL = "https://secure5.saashr.com/ta/CH50003.home?showAdmin=1&Ext=login&sft=HOSCCFOFIU"
TIMESHEET_HASH = "time/timesheet/timesheets?tab=TIME_ENTRY"
LOGIN_FORM_SELECTOR = "input[name='Username']"
PASSWORD_INPUT_SELECTOR = "input[name='PasswordView']"
LOGIN_BUTTON_SELECTOR = "button[name='LoginButton']"
MFA_CODE_SELECTOR = "input[name='VerificationCode']"
INTERACTIVE_SELECTOR = "input, button, a, select"


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


async def log_in(page, username: str | None = None, password: str | None = None, attempts: int = 2):
    if username is None:
        username = require_env("TRIUMPH_USERNAME")
    if password is None:
        password = require_env("TRIUMPH_PASSWORD")

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            await navigate_to_login(page)
            await page.fill(LOGIN_FORM_SELECTOR, username)
            await page.fill(PASSWORD_INPUT_SELECTOR, password)
            await page.click(LOGIN_BUTTON_SELECTOR)
            await page.wait_for_load_state("networkidle")

            if await page.locator(MFA_CODE_SELECTOR).count() or "isMFALogin=true" in page.url:
                await _handle_mfa(page)

            await _wait_for_authenticated_page(page)
            return
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            try:
                await page.goto("about:blank", wait_until="load")
            except Exception:
                pass

    raise RuntimeError(f"Login failed after {attempts} attempts: {last_error}") from last_error


async def _handle_mfa(page):
    totp_code = get_totp_code()
    if not totp_code:
        raise RuntimeError("MFA required but TRIUMPH_TOTP_SECRET is not set")

    auth_radio = page.locator("#authRadio")
    if await auth_radio.count():
        await auth_radio.check(force=True)

    continue_button = page.locator("button#continueButton")
    if await continue_button.count():
        await _click_with_js_fallback(page, continue_button, "continueButton")

    await page.wait_for_load_state("networkidle")
    await page.wait_for_selector(MFA_CODE_SELECTOR, state="visible")
    await page.fill(MFA_CODE_SELECTOR, totp_code)

    try:
        await page.check("input#RememberDevice")
    except Exception:
        pass

    verify_button = page.locator("button#AuthenticateTOTPButton")
    await _click_with_js_fallback(page, verify_button, "AuthenticateTOTPButton", force_enable=True)
    await page.wait_for_load_state("networkidle")


async def _click_with_js_fallback(page, locator, element_id: str, force_enable: bool = False):
    try:
        await locator.click(timeout=5_000)
        return
    except Exception:
        pass

    await page.evaluate(
        """([elementId, forceEnable]) => {
            const btn = document.getElementById(elementId);
            if (!btn) {
                return;
            }
            if (forceEnable) {
                btn.disabled = false;
            }
            btn.click();
        }""",
        [element_id, force_enable],
    )


async def dump_interactive_elements(page, limit: int = 50):
    elements = await page.query_selector_all(INTERACTIVE_SELECTOR)
    print(f"\nFound {len(elements)} interactive elements. First {limit}:")
    for i, el in enumerate(elements[:limit]):
        tag = await el.evaluate("e => e.tagName")
        text = await el.evaluate("e => (e.innerText || '').slice(0,80)")
        id_ = await el.get_attribute("id") or ""
        name = await el.get_attribute("name") or ""
        cls = await el.get_attribute("class") or ""
        type_ = await el.get_attribute("type") or ""
        print(
            f"[{i}] {tag} id={id_!r} name={name!r} class={cls!r} type={type_!r} text={text!r}"
        )


async def _wait_for_authenticated_page(page):
    await page.wait_for_load_state("domcontentloaded")
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
        timeout=30_000,
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
    try:
        page_text = (await page.locator("body").inner_text(timeout=5_000)).lower()
    except PlaywrightTimeoutError:
        page_text = ""
    for message in login_errors:
        if message in page_text:
            raise RuntimeError(f"Login failed: portal reported '{message}'")
