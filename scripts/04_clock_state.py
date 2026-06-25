import asyncio
import json

from camoufox.async_api import AsyncCamoufox

from auth import log_in, navigate_to_timesheet
from clock_state import collect_clock_state, wait_for_clock_controls


async def detect_clock_state():
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        await log_in(page)
        await navigate_to_timesheet(page)
        await wait_for_clock_controls(page)

        state = await collect_clock_state(page)
        await page.screenshot(path="outputs/clock_state.png", full_page=True)
        print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(detect_clock_state())
