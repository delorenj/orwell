from __future__ import annotations

from datetime import datetime
from typing import Any

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
    "missing previous in punch",
    "missing punch",
    "punch exception",
)


def today_row_label() -> str:
    now = datetime.now()
    return f"{now:%a}".upper() + f" {now:%b} {now.day}"


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


def button_label_score(text: str) -> int:
    score = 0
    for labels in ACTION_LABELS.values():
        if text in labels:
            score = max(score, 3)
        elif any(label in text for label in labels):
            score = max(score, 2)
    return score


async def discover_clock_buttons(page):
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

        score = button_label_score(text)
        if score:
            candidates.append({"button": btn, "text": text, "score": score})

    candidates.sort(key=lambda item: (item["score"], len(item["text"])), reverse=True)
    return candidates


async def collect_today_row_state(page):
    label = today_row_label()

    # The timesheet renders rows asynchronously after the clock buttons appear.
    # Wait for today's group rows to exist before reading them.
    try:
        await page.wait_for_selector(f'tr[data-group-date="{label}"]', timeout=15_000)
        await page.wait_for_timeout(500)
    except Exception:
        pass

    rows = page.locator(f'tr[data-group-date="{label}"]')
    if await rows.count() == 0:
        return None

    candidates = await rows.evaluate_all(
        """(rowEls) => {
            const read = (el, name) => {
                for (const input of el.querySelectorAll(`input[name="${name}"]`)) {
                    const value = input.value.trim();
                    if (!value) continue;
                    const formControl = input.closest('.c-form-control');
                    const ampmBtn = formControl && formControl.querySelector('.c-time-input-ampm-button');
                    const ampm = ampmBtn ? ampmBtn.textContent.trim().toLowerCase() : '';
                    return ampm ? `${value} ${ampm}` : value;
                }
                return '';
            };
            return rowEls.map((row) => ({
                isFooter: row.classList.contains('m-footer'),
                start_time: read(row, 'start_time'),
                end_time: read(row, 'end_time'),
                total: read(row, 'total'),
            }));
        }"""
    )

    # Ignore footer/summary rows and rows with no punch data.
    punch_rows = [
        row for row in candidates
        if not row["isFooter"] and (row["start_time"] or row["end_time"])
    ]
    if not punch_rows:
        return None

    # Prefer the currently-open punch (started but not yet ended).
    for row in punch_rows:
        if row["start_time"] and not row["end_time"]:
            return {"start_time": row["start_time"], "end_time": row["end_time"], "total": row["total"]}

    # No open punch: return the last completed punch for today.
    last = punch_rows[-1]
    return {"start_time": last["start_time"], "end_time": last["end_time"], "total": last["total"]}


async def collect_clock_state(page) -> dict[str, Any]:
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
        "derived_status": derive_clock_status(today_row, button_texts, failures),
    }


def derive_clock_status(today_row: dict[str, str] | None, button_texts: list[str], failures: list[str]) -> str:
    if failures:
        return "error"

    row = today_row or {}
    start_time = (row.get("start_time") or "").strip()
    end_time = (row.get("end_time") or "").strip()

    if start_time and not end_time:
        return "clocked_in"
    if start_time and end_time:
        return "clocked_out"

    if any(text in ACTION_LABELS["out"] for text in button_texts):
        return "clocked_in"
    if any(text in ACTION_LABELS["in"] for text in button_texts):
        return "clocked_out"

    return "unknown"


def state_supports_action(status: str, action: str) -> bool:
    if action == "in":
        return status in {"clocked_out", "unknown"}
    if action == "out":
        return status in {"clocked_in", "unknown"}
    raise ValueError(f"Unknown action: {action}")


def state_summary(state: dict[str, Any]) -> str:
    return (
        f"status={state['derived_status']} "
        f"today_row={state.get('today_row')} "
        f"buttons={state.get('button_texts')} "
        f"failures={state.get('failures')}"
    )


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
