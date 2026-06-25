import asyncio
from camoufox.async_api import AsyncCamoufox

from auth import BASE_URL, dump_interactive_elements


async def main():
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.screenshot(path="outputs/portal_initial.png", full_page=True)
        print("Title:", await page.title())
        print("URL:", page.url)

        await dump_interactive_elements(page)

if __name__ == "__main__":
    asyncio.run(main())
