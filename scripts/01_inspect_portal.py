import asyncio
from camoufox.async_api import AsyncCamoufox

TARGET = (
    "https://secure5.saashr.com/ta/CH50003.home?rnd=TUZ&showAdmin=1"
    "&Ext=login&sft=HOSCCFOFIU&ActiveSessionId=25425500678#time/timesheet/timesheets"
    "?tab=TIME_ENTRY&tsId=21935049240"
)


async def main():
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(TARGET, wait_until="networkidle")
        await page.screenshot(path="outputs/portal_initial.png", full_page=True)
        print("Title:", await page.title())
        print("URL:", page.url)

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
