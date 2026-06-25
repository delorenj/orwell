import asyncio
import sys

from camoufox.async_api import AsyncCamoufox

sys.path.insert(0, "/home/delorenj/code/clockin/scripts")
from auth import log_in, navigate_to_timesheet


async def main():
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        await log_in(page)
        await navigate_to_timesheet(page)

        # Wait for clock buttons
        await page.wait_for_function(
            """() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                return buttons.some((b) => (b.innerText || '').toLowerCase().includes('clock out'));
            }""",
            timeout=20_000,
        )

        # Click clock out
        clock_out_btn = page.locator("button:has-text('Clock Out')").first
        await clock_out_btn.click()
        await page.wait_for_load_state("networkidle")

        # Wait for modal
        await page.wait_for_function(
            """() => {
                const text = document.body.innerText || '';
                return text.includes('Are you sure') || text.includes('Missing previous');
            }""",
            timeout=10_000,
        )

        await page.screenshot(path="outputs/debug_modal_visible.png", full_page=True)

        # Dump HTML of the modal/dialog
        modal_html = await page.evaluate(
            """() => {
                const modal = document.querySelector('[role="dialog"], .modal, .modal-dialog, .modal-content')
                    || Array.from(document.querySelectorAll('div')).find((el) => {
                        const text = el.innerText || '';
                        return (text.includes('Are you sure') || text.includes('Missing previous')) && text.includes('Save');
                    });
                return modal ? modal.outerHTML : 'No modal found';
            }"""
        )

        with open("outputs/debug_modal_html.html", "w") as f:
            f.write(modal_html)

        print("Modal HTML saved to outputs/debug_modal_html.html")
        print("Modal screenshot saved to outputs/debug_modal_visible.png")


if __name__ == "__main__":
    asyncio.run(main())
