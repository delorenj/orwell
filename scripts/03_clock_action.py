import asyncio
import sys

from camoufox.async_api import AsyncCamoufox

from auth import log_in


async def discover_clock_buttons(page):
    """Return candidate clock-in/clock-out buttons by scanning button text."""
    buttons = await page.query_selector_all("button")
    candidates = []
    for i, btn in enumerate(buttons):
        text = (await btn.evaluate("e => (e.innerText || '').trim()")).lower()
        if any(k in text for k in ("clock in", "clock out", "clock-in", "clock-out", "punch in", "punch out")):
            candidates.append((i, btn, text))
    return candidates


async def perform_clock_action(action: str):
    assert action in ("in", "out"), "action must be 'in' or 'out'"

    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        await log_in(page)

        # Navigate to the timesheet view where the clock buttons live.
        await page.evaluate(
            "() => { window.location.hash = 'time/timesheet/timesheets?tab=TIME_ENTRY&tsId=21935049240'; }"
        )
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(4000)

        await page.screenshot(path="outputs/portal_logged_in.png", full_page=True)

        candidates = await discover_clock_buttons(page)
        if not candidates:
            print("No clock buttons discovered. Saving page dump for inspection.", file=sys.stderr)
            await page.screenshot(path="outputs/clock_action_no_buttons.png", full_page=True)
            sys.exit(1)

        # Prefer the button whose text contains the requested action.
        keyword = "in" if action == "in" else "out"
        chosen = None
        for _, btn, text in candidates:
            if keyword in text:
                chosen = btn
                break
        if chosen is None:
            chosen = candidates[0][1]

        await chosen.scroll_into_view_if_needed()
        await chosen.click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)

        # Confirm any "Are you sure?" / missing-punch modal.
        try:
            save_buttons = page.locator("button:has-text('Save')")
            count = await save_buttons.count()
            for i in range(count - 1, -1, -1):
                btn = save_buttons.nth(i)
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_load_state("networkidle")
                    await page.wait_for_timeout(2000)
                    break
        except Exception:
            pass

        await page.screenshot(path=f"outputs/clock_{action}.png", full_page=True)
        print(f"Clock-{action} screenshot saved to outputs/clock_{action}.png")
        print("Final URL:", page.url)
        print("Title:", await page.title())

        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("in", "out"):
        print("Usage: python scripts/03_clock_action.py <in|out>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(perform_clock_action(sys.argv[1]))
