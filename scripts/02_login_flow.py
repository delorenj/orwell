import asyncio
import os
import sys

from dotenv import load_dotenv
from camoufox.async_api import AsyncCamoufox

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


async def main():
    username = require_env("TRIUMPH_USERNAME")
    password = require_env("TRIUMPH_PASSWORD")

    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(TARGET, wait_until="networkidle")

        await page.fill("input[name='Username']", username)
        await page.fill("input[name='PasswordView']", password)

        # The form copies PasswordView into the hidden Password field on submit.
        await page.click("button[name='LoginButton']")
        await page.wait_for_load_state("networkidle")

        # Additional wait for any client-side routing/rendering.
        await page.wait_for_timeout(3000)

        await page.screenshot(path="outputs/portal_logged_in.png", full_page=True)
        print("Post-login URL:", page.url)
        print("Title:", await page.title())

        # Dump interactive elements on the post-login page for clock-action discovery.
        elements = await page.query_selector_all("input, button, a, select")
        print(f"\nFound {len(elements)} interactive elements. First 50:")
        for i, el in enumerate(elements[:50]):
            tag = await el.evaluate("e => e.tagName")
            text = await el.evaluate("e => (e.innerText || '').slice(0,80)")
            id_ = await el.get_attribute("id") or ""
            name = await el.get_attribute("name") or ""
            cls = await el.get_attribute("class") or ""
            type_ = await el.get_attribute("type") or ""
            print(
                f"[{i}] {tag} id={id_!r} name={name!r} class={cls!r} type={type_!r} text={text!r}"
            )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
