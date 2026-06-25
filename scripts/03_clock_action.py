import asyncio
import sys
from datetime import datetime

from camoufox.async_api import AsyncCamoufox

from auth import log_in, navigate_to_timesheet

ACTION_LABELS = {
    "in": ("clock in", "clock-in", "punch in"),
    "out": ("clock out", "clock-out", "punch out"),
}
ALL_ACTION_LABELS = tuple(label for labels in ACTION_LABELS.values() for label in labels)

SUCCESS_HINTS = (
    "success",
    "saved",
    "clocked in",
    "clocked out",
    "punch accepted",
    "time entry saved",
)

FAILURE_HINTS = (
    "could not 'punch in'",
    "could not 'punch out'",
    "missing previous out punch",
)


async def _button_snapshot(button):
    return await button.evaluate(
        """(el) => {
            const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            return {
                text,
                disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
            };
        }"""
    )


def _button_label_score(text: str) -> int:
    score = 0
    for labels in ACTION_LABELS.values():
        if text in labels:
            score = max(score, 3)
        elif any(label in text for label in labels):
            score = max(score, 2)
    return score


async def discover_clock_buttons(page):
    """Return visible, enabled clock action buttons ranked by label quality."""
    buttons = await page.query_selector_all("button")
    candidates = []
    for btn in buttons:
        snapshot = await _button_snapshot(btn)
        text = snapshot["text"].lower()
        try:
            is_visible = await btn.is_visible()
            is_enabled = await btn.is_enabled()
            box = await btn.bounding_box()
        except Exception:
            continue

        if not box or box["y"] < 0 or box["width"] <= 0 or box["height"] <= 0:
            continue

        if not is_visible or not is_enabled or snapshot["disabled"]:
            continue
        if text in {"save", "cancel", "close"}:
            continue

        score = _button_label_score(text)
        if score:
            candidates.append({"button": btn, "text": text, "score": score})

    candidates.sort(key=lambda item: (item["score"], len(item["text"])), reverse=True)
    return candidates


async def collect_clock_state(page):
    candidates = await discover_clock_buttons(page)
    button_texts = [candidate["text"] for candidate in candidates]
    body_text = (await page.locator("body").inner_text()).lower()
    messages = [hint for hint in SUCCESS_HINTS if hint in body_text]
    failures = [hint for hint in FAILURE_HINTS if hint in body_text]
    today_row = await collect_today_row_state(page)
    return {
        "button_texts": button_texts,
        "messages": messages,
        "failures": failures,
        "today_row": today_row,
    }


def today_row_label() -> str:
    now = datetime.now()
    return f"{now:%a}".upper() + f" {now:%b} {now.day}"


async def collect_today_row_state(page):
    rows = page.locator(f'tr[data-group-date="{today_row_label()}"]')
    if await rows.count() == 0:
        return None

    return await rows.first.evaluate(
        """(el) => {
            const read = (name) => {
                const input = el.querySelector(`input[name="${name}"]`);
                return input ? input.value.trim() : '';
            };
            return {
                start_time: read('start_time'),
                end_time: read('end_time'),
                total: read('total'),
            };
        }"""
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

    if after["messages"]:
        return True

    today_row = after.get("today_row") or {}
    if action == "in" and today_row.get("start_time") and not today_row.get("end_time"):
        return True
    if action == "out" and today_row.get("start_time") and today_row.get("end_time"):
        return True

    opposite_action = "out" if action == "in" else "in"
    opposite_labels = ACTION_LABELS[opposite_action]
    current_labels = ACTION_LABELS[action]

    gained_opposite = any(text in opposite_labels for text in after["button_texts"])
    lost_current = all(text not in current_labels for text in after["button_texts"])

    return gained_opposite and lost_current


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


async def wait_for_clock_controls(page):
    await page.wait_for_function(
        """(labels) => {
            const buttons = Array.from(document.querySelectorAll('button'));
            return buttons.some((button) => {
                const text = (button.innerText || button.textContent || '').trim().toLowerCase();
                const style = window.getComputedStyle(button);
                const rect = button.getBoundingClientRect();
                const visible = style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                return visible && labels.some((label) => text.includes(label));
            });
        }""",
        arg=ALL_ACTION_LABELS,
        timeout=20_000,
    )


async def perform_clock_action(action: str):
    assert action in ("in", "out"), "action must be 'in' or 'out'"

    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        await log_in(page)
        await navigate_to_timesheet(page)
        await wait_for_clock_controls(page)

        await page.screenshot(path="outputs/portal_logged_in.png", full_page=True)

        candidates = await discover_clock_buttons(page)
        if not candidates:
            print("No clock buttons discovered. Saving page dump for inspection.", file=sys.stderr)
            await page.screenshot(path="outputs/clock_action_no_buttons.png", full_page=True)
            sys.exit(1)

        before_state = await collect_clock_state(page)
        chosen = choose_clock_button(candidates, action)

        await chosen["button"].scroll_into_view_if_needed()
        await chosen["button"].click()
        await page.wait_for_load_state("networkidle")
        await confirm_modal_if_present(page)

        after_state = await collect_clock_state(page)
        if not clock_action_succeeded(after_state, action):
            await page.screenshot(path=f"outputs/clock_{action}_unverified.png", full_page=True)
            raise RuntimeError(
                f"Clock-{action} could not be verified. "
                f"Before={before_state['button_texts']} After={after_state['button_texts']}"
            )

        await page.screenshot(path=f"outputs/clock_{action}.png", full_page=True)
        print(f"Clock-{action} screenshot saved to outputs/clock_{action}.png")
        print("Final URL:", page.url)
        print("Title:", await page.title())


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("in", "out"):
        print("Usage: python scripts/03_clock_action.py <in|out>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(perform_clock_action(sys.argv[1]))