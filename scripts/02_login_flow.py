import asyncio

from camoufox.async_api import AsyncCamoufox

from auth import dump_interactive_elements, log_in, navigate_to_timesheet


async def main():
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        await log_in(page)

        await navigate_to_timesheet(page)

        await page.screenshot(path="outputs/portal_logged_in.png", full_page=True)
        print("Post-login URL:", page.url)
        print("Title:", await page.title())

        # Dump interactive elements on the post-login page for clock-action discovery.
        await dump_interactive_elements(page)

if __name__ == "__main__":
    asyncio.run(main())
