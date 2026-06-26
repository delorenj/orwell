import asyncio
import json
from datetime import datetime

from camoufox.async_api import AsyncCamoufox

from auth import log_in, navigate_to_timesheet
from clock_state import wait_for_clock_controls


def today_row_label() -> str:
    now = datetime.now()
    return f"{now:%a}".upper() + f" {now:%b} {now.day}"


async def main():
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        await log_in(page)
        await navigate_to_timesheet(page)
        await wait_for_clock_controls(page)

        # Wait for the timesheet data rows to actually render (not skeleton placeholders)
        label = today_row_label()
        print(f"Today row label: {label!r}")
        try:
            await page.wait_for_selector(f'tr[data-group-date="{label}"]', timeout=15_000)
        except Exception as exc:
            print(f"Timed out waiting for today's row: {exc}")
        await page.wait_for_timeout(2_000)

        # Dump all rows for today
        rows_info = await page.evaluate(
            """(label) => {
                const rows = Array.from(document.querySelectorAll(`tr[data-group-date="${label}"]`));
                return rows.map((row, index) => {
                    const inputs = Array.from(row.querySelectorAll('input[name]'));
                    return {
                        index,
                        className: row.className,
                        shiftId: row.getAttribute('data-shift-id') || '',
                        outerHTML: row.outerHTML.slice(0, 2000),
                        text: (row.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 500),
                        inputValues: inputs.map((input) => ({
                            name: input.name,
                            value: input.value,
                            id: input.id,
                        })),
                    };
                });
            }""",
            label,
        )
        print(f"Found {len(rows_info)} row(s) for today")
        for info in rows_info:
            print(f"\n--- Row {info['index']} ---")
            print(f"class={info['className']}")
            print(f"shiftId={info['shiftId']}")
            print(f"Text: {info['text']}")
            print(f"Inputs: {json.dumps(info['inputValues'], indent=2)}")
            print(f"HTML: {info['outerHTML']}")

        # Also dump the count of all tr elements with data-group-date
        all_labels = await page.evaluate(
            """() => {
                const rows = Array.from(document.querySelectorAll('tr[data-group-date]'));
                const counts = {};
                rows.forEach((row) => {
                    const label = row.getAttribute('data-group-date');
                    counts[label] = (counts[label] || 0) + 1;
                });
                return counts;
            }"""
        )
        print(f"\nAll data-group-date counts: {json.dumps(all_labels, indent=2, sort_keys=True)}")

        await page.screenshot(path="outputs/dump_today_row.png", full_page=True)
        print("\nScreenshot saved to outputs/dump_today_row.png")


if __name__ == "__main__":
    asyncio.run(main())
