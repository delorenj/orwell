import asyncio
import os
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

DANGEROUS_MODAL_HINTS = (
    "missing previous in punch",
    "missing previous out punch",
    "missing punch",
    "timesheet change request",
)


def compact_modal_text(text: str) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= 300 else f"{compact[:297]}..."


def modal_requires_manual_repair(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in DANGEROUS_MODAL_HINTS)


def allow_clock_out_repair_probe(action: str, state: dict) -> bool:
    return (
        action == "out"
        and os.environ.get("ORWELL_ALLOW_CLOCK_OUT_REPAIR_PROBE") == "1"
        and "clock out" in state.get("button_texts", [])
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
    """Confirm any warning/confirmation modal (missing punch, are-you-sure, etc.) by clicking Save."""
    modal_selectors = '[aria-modal="true"], [role="alertdialog"], [role="dialog"], .modal, .c-modal'
    keywords = ("are you sure", "missing previous", "missing punch", "warning")
    try:
        await page.wait_for_function(
            """(selectors) => {
                const els = Array.from(document.querySelectorAll(selectors));
                return els.some((el) => {
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const text = (el.innerText || '').toLowerCase();
                    return ['are you sure', 'missing previous', 'missing punch', 'warning']
                        .some((kw) => text.includes(kw));
                });
            }""",
            arg=modal_selectors,
            timeout=10_000,
        )
    except Exception:
        return False

    try:
        modal = await page.evaluate_handle(
            """(selectors) => {
                const els = Array.from(document.querySelectorAll(selectors));
                return els.find((el) => {
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const text = (el.innerText || '').toLowerCase();
                    return ['are you sure', 'missing previous', 'missing punch', 'warning']
                        .some((kw) => text.includes(kw));
                });
            }""",
            modal_selectors,
        )
        if not modal or await modal.evaluate("el => !el"):
            return False
        text = (await modal.inner_text()).lower()
        print(f"Confirming modal: {text[:200]!r}", file=sys.stderr)
        if modal_requires_manual_repair(text):
            raise RuntimeError(
                "Portal requires manual timesheet repair before an automated clock action can continue: "
                f"{compact_modal_text(text)}"
            )

        # Prefer the primary action button inside the modal; fall back to any Save.
        save_btn = await modal.query_selector("button.m-primary")
        if save_btn and not await save_btn.is_visible():
            save_btn = None
        if not save_btn:
            candidates = await modal.query_selector_all("button")
            for btn in candidates:
                label = (await btn.inner_text()).strip().lower()
                if label == "save" and await btn.is_visible():
                    save_btn = btn
                    break
        if not save_btn:
            return False
        await save_btn.click()
        print("Clicked modal Save button.", file=sys.stderr)
        # Wait for the modal to leave the DOM and the page to settle.
        await page.wait_for_function(
            """(selectors) => {
                const els = Array.from(document.querySelectorAll(selectors));
                return !els.some((el) => {
                    const style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden';
                });
            }""",
            arg=modal_selectors,
            timeout=10_000,
        )
        await page.wait_for_load_state("networkidle")
        print("Modal dismissed.", file=sys.stderr)
        return True
    except RuntimeError:
        raise
    except Exception as exc:
        print(f"Modal confirmation failed: {exc}", file=sys.stderr)
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
        repair_probe = allow_clock_out_repair_probe(action, before_state)
        if before_state["failures"] and not repair_probe:
            await page.screenshot(path=f"outputs/clock_{action}_blocked.png", full_page=True)
            raise RuntimeError(
                f"Portal already shows a punch error before clock-{action}: {state_summary(before_state)}"
            )
        if before_state["failures"] and repair_probe:
            print(
                "Clock-out repair probe continuing despite pre-existing row failures; "
                "missing-punch repair modals will not be confirmed.",
                file=sys.stderr,
            )

        target_status = "clocked_in" if action == "in" else "clocked_out"
        if before_state["derived_status"] == target_status:
            await page.screenshot(path=f"outputs/clock_{action}.png", full_page=True)
            print(f"Clock-{action} already satisfied; no action needed.")
            print("Final state:", state_summary(before_state))
            print("Final URL:", page.url)
            print("Title:", await page.title())
            return
        if not state_supports_action(before_state["derived_status"], action) and not repair_probe:
            await page.screenshot(path=f"outputs/clock_{action}_blocked.png", full_page=True)
            raise RuntimeError(
                f"Refusing clock-{action}: current state is not actionable. {state_summary(before_state)}"
            )

        candidates = await discover_clock_buttons(page)
        if not candidates:
            print("No clock buttons discovered. Saving page dump for inspection.", file=sys.stderr)
            await page.screenshot(path="outputs/clock_action_no_buttons.png", full_page=True)
            sys.exit(1)

        chosen = choose_clock_button(candidates, action)
        await chosen["button"].scroll_into_view_if_needed()
        await chosen["button"].click()
        await confirm_modal_if_present(page)

        # Read the post-action state from a freshly loaded timesheet so we
        # don't race the portal's save/reload animation.
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
