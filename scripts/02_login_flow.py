import asyncio

from camoufox.async_api import AsyncCamoufox

from auth import log_in


async def main():
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        await log_in(page)

        # Navigate to the target timesheet view now that we are authenticated.
        await page.evaluate(
            "() => { window.location.hash = 'time/timesheet/timesheets?tab=TIME_ENTRY&tsId=21935049240'; }"
        )
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(4000)

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
