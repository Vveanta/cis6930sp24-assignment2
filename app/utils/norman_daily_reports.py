"""Norman PD daily incident summary PDF URLs (department activity reports).

The live Drupal site stores files under ``documents/YYYY-MM/`` where the folder
reflects the *media upload batch*, not "month before the report date":
- Most days use the **same calendar month** as the report date (e.g. 2026-03-15 → …/2026-03/).
- Reports on the **27th or later** are uploaded into the **next** month's folder while the
  filename still uses the actual report date (e.g. 2026-03-30 → …/2026-04/2026-03-30_…).

We emit a small ordered list of candidate URLs and try them until one returns HTTP 200.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterator

from dateutil.relativedelta import relativedelta


def _folder_month_for_report_date(d: date) -> date:
    """First day of the Drupal folder month (YYYY-MM) for this report date."""
    first = d.replace(day=1)
    if d.day >= 27:
        return first + relativedelta(months=1)
    return first


def iter_daily_incident_summary_urls(d: date) -> Iterator[str]:
    """
    Yield candidate URLs most likely to work first (same pattern as normanok.gov HTML).
    Includes one fallback (alternate month) for edge cases.
    """
    base = "https://www.normanok.gov/sites/default/files/documents"
    primary = _folder_month_for_report_date(d)
    ym_p = primary.strftime("%Y-%m")
    yield f"{base}/{ym_p}/{d:%Y-%m-%d}_daily_incident_summary.pdf"

    # Fallback: other common layout (same month only when day>=27 already used next month)
    first = d.replace(day=1)
    if primary == first:
        alt = first + relativedelta(months=1)
    else:
        alt = first
    ym_a = alt.strftime("%Y-%m")
    if ym_a != ym_p:
        yield f"{base}/{ym_a}/{d:%Y-%m-%d}_daily_incident_summary.pdf"


def daily_summary_pdf_url(d: date) -> str:
    """First (preferred) incident summary URL for a report date."""
    return next(iter_daily_incident_summary_urls(d))


def selectable_date_bounds() -> tuple[date, date]:
    today = date.today()
    end = today - timedelta(days=7)
    start = today.replace(day=1) - relativedelta(months=2)
    if end < start:
        return start, start
    return start, end


def iter_selectable_dates() -> Iterator[date]:
    start, end = selectable_date_bounds()
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def parse_iso_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def is_allowed_report_date(d: date) -> bool:
    start, end = selectable_date_bounds()
    return start <= d <= end
