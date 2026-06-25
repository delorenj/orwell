import asyncio
import sys

from camoufox.async_api import AsyncCamoufox

from auth import log_in, navigate_to_timesheet
from clock_state import (
    ACTION_LABELS,
    collect_clock_state,
    discover_clock_buttons,
    state_summary,
    state_supports_action,
    wait_for_clock_controls,
)


def _pick_unique_candidate(candidates, predicate, action: str, match_kind: str):
    matches = [candidate for candidate in candidates if predicate(candidate)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        if len({candidate["text"] for candidate in matches}) == 1:
            return matches[0]
        raise RuntimeError(
            f"Ambiguous {action} action: found multiple {match_kind} matches {[c['text'] for c in matches]}"
        )
    return None


def choose_clock_button(candidates, action: str):
    labels = ACTION_LABELS[action]
    exact = _pick_unique_candidate(candidates, lambda candidate: candidate["text"] in labels, action, "exact")
    if exact:
        return exact

    partial = _pick_unique_candidate(
        candidates,
        lambda candidate: any(label in candidate["text"] for label in labels),
        action,
        "partial",
    )
    if partial:
        return partial

    available = [candidate["text"] for candidate in candidates]
    raise RuntimeError(f"No visible {action} button found. Available candidates: {available}")


def clock_action_succeeded(after: dict, action: str) -> bool:
    if after["failures"]:
        return False

    status = after["derived_status"]
    return (action == "in" and status == "clocked_in") or (action == "out" and status == "clocked_out")


async def confirm_modal_if_present(page):
    """Confirm any 'Are you sure?' / missing-punch modal by clicking its Save button."""
    try:
        await page.wait_for_function(
            """() => {
                const text = document.body.innerText || '';
                return text.includes('Are you sure') || text.includes('Missing previous');
            }""",
            timeout=10_000,
        )
    except Exception:
        return False

    try:
        save_buttons = page.locator("button:has-text('Save')")
        count = await save_buttons.count()
        visible = []
        for i in range(count):
            btn = save_buttons.nth(i)
            if not await btn.is_visible():
                continue
            box = await btn.bounding_box()
            if not box:
                continue
            visible.append((box["y"], btn))

        if not visible:
            return False

        _, save_btn = max(visible, key=lambda item: item[0])
        await save_btn.click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_function(
            """() => {
                const text = document.body.innerText || '';
                return !text.includes('Are you sure') && !text.includes('Missing previous');
            }""",
            timeout=10_000,
        )
        return True
    except Exception:
        return False


async def collect_stable_clock_state(page):
    await navigate_to_timesheet(page)
    await wait_for_clock_controls(page)
    return await collect_clock_state(page)


async def perform_clock_action(action: str):
    assert action in ("in", "out"), "action must be 'in' or 'out'"

    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        await log_in(page)
        await navigate_to_timesheet(page)
        await wait_for_clock_controls(page)

        await page.screenshot(path="outputs/portal_logged_in.png", full_page=True)

        before_state = await collect_stable_clock_state(page)
        if before_state["failures"]:
            await page.screenshot(path=f"outputs/clock_{action}_blocked.png", full_page=True)
            raise RuntimeError(
                f"Portal already shows a punch error before clock-{action}: {state_summary(before_state)}"
            )

        if not state_supports_action(before_state["derived_status"], action):
            raise RuntimeError(
                f"Refusing clock-{action}: current state says no action needed. {state_summary(before_state)}"
            )

        candidates = await discover_clock_buttons(page)
        if not candidates:
            print("No clock buttons discovered. Saving page dump for inspection.", file=sys.stderr)
            await page.screenshot(path="outputs/clock_action_no_buttons.png", full_page=True)
            sys.exit(1)

        chosen = choose_clock_button(candidates, action)
        await chosen["button"].scroll_into_view_if_needed()
        await chosen["button"].click()
        await page.wait_for_load_state("networkidle")
        await confirm_modal_if_present(page)

        after_state = await collect_stable_clock_state(page)
        if not clock_action_succeeded(after_state, action):
            await page.screenshot(path=f"outputs/clock_{action}_unverified.png", full_page=True)
            raise RuntimeError(
                f"Clock-{action} could not be verified. "
                f"Before={state_summary(before_state)} After={state_summary(after_state)}"
            )

        await page.screenshot(path=f"outputs/clock_{action}.png", full_page=True)
        print(f"Clock-{action} screenshot saved to outputs/clock_{action}.png")
        print("Final state:", state_summary(after_state))
        print("Final URL:", page.url)
        print("Title:", await page.title())


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("in", "out"):
        print("Usage: python scripts/03_clock_action.py <in|out>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(perform_clock_action(sys.argv[1]))
