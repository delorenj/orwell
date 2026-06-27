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


async def wait_for_group_rows(page, timeout: int = 20_000):
    """Wait until the timesheet rows have rendered in the DOM."""
    await page.wait_for_function(
        "() => document.querySelectorAll('tr[data-group-date]').length > 0",
        timeout=timeout,
    )


async def collect_group_rows(page) -> list[dict[str, Any]]:
    """Return all timesheet group rows with their input values.

    Uses JS evaluation because Camoufox/Playwright attribute selectors can fail
    to match rows that are rendered lazily after the clock controls appear.
    """
    return await page.evaluate(
        """() => {
            const readAmpm = (input) => {
                const fc = input && input.closest('.c-form-control');
                const btn = fc && fc.querySelector('.c-time-input-ampm-button');
                return btn ? btn.textContent.trim().toLowerCase() : '';
            };
            const rows = Array.from(document.querySelectorAll('tr[data-group-date]'));
            return rows.map((row) => {
                const group = row.getAttribute('data-group-date');
                const isFooter = row.classList.contains('m-footer');
                const hasDelete = row.querySelector('button[aria-label*="Delete"], button.icon-delete, i.icon-delete') !== null;
                const startInputs = Array.from(row.querySelectorAll('input[name="start_time"]'));
                const endInputs = Array.from(row.querySelectorAll('input[name="end_time"]'));
                const firstNonEmpty = (inputs) => {
                    for (const input of inputs) {
                        const v = input.value.trim();
                        if (v) return v;
                    }
                    return inputs[0] ? inputs[0].value.trim() : '';
                };
                const start = firstNonEmpty(startInputs);
                const end = firstNonEmpty(endInputs);
                const startInput = startInputs.find(i => i.value.trim() === start) || startInputs[0];
                const endInput = endInputs.find(i => i.value.trim() === end) || endInputs[0];
                const startAmpm = start ? readAmpm(startInput) : '';
                const endAmpm = end ? readAmpm(endInput) : '';
                const totalEl = row.querySelector('.c-table__content-inactive, .u-medium-font');
                const total = totalEl ? totalEl.innerText.trim() : '';
                return {
                    group,
                    isFooter,
                    hasDelete,
                    start_time: start ? (startAmpm ? `${start} ${startAmpm}` : start) : '',
                    end_time: end ? (endAmpm ? `${end} ${endAmpm}` : end) : '',
                    total,
                };
            });
        }"""
    )


def find_active_and_last_completed_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the in-progress punch row and the most recent completed row."""
    active_row = None
    last_completed_row = None
    for row in reversed(rows):
        if row.get("isFooter"):
            continue
        start = (row.get("start_time") or "").strip()
        end = (row.get("end_time") or "").strip()
        if start and end:
            if last_completed_row is None:
                last_completed_row = row
            continue
        # Active row: has a delete button (unsaved/in-progress entry) and is
        # not fully punched out. A placeholder open punch has both fields empty.
        if row.get("hasDelete") and active_row is None:
            active_row = row
    return active_row, last_completed_row


async def collect_clock_state(page) -> dict[str, Any]:
    candidates = await discover_clock_buttons(page)
    button_texts = [candidate["text"] for candidate in candidates]
    body_text = (await page.locator("body").inner_text()).lower()
    messages = [hint for hint in SUCCESS_HINTS if hint in body_text]
    failures = [hint for hint in FAILURE_HINTS if hint in body_text]

    await wait_for_group_rows(page)
    rows = await collect_group_rows(page)
    active_row, last_completed_row = find_active_and_last_completed_rows(rows)

    representative_row = active_row or last_completed_row
    today_row = None
    if representative_row:
        today_row = {
            "start_time": representative_row["start_time"],
            "end_time": representative_row["end_time"],
            "total": representative_row["total"],
            "group": representative_row["group"],
        }

    return {
        "button_texts": button_texts,
        "messages": messages,
        "failures": failures,
        "today_row": today_row,
        "derived_status": derive_clock_status(active_row, last_completed_row, failures),
    }


def derive_clock_status(
    active_row: dict[str, Any] | None,
    last_completed_row: dict[str, Any] | None,
    failures: list[str],
) -> str:
    if failures:
        return "error"
    if active_row:
        return "clocked_in"
    if last_completed_row:
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
