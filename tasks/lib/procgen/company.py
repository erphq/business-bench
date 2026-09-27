"""Build Northgate Valve Co. as of a scenario start date: master data, opening balances, and twelve months of
history. Deterministic for a given seed."""
from __future__ import annotations

from bberp import setup
from bberp.core import add_days, parse_day, period_of

from . import history
from .northgate import COMPANY, Company, master_data, opening_balances

HOLIDAYS = {'2025-11-27': 'Thanksgiving', '2025-11-28': 'Day after Thanksgiving', '2025-12-24': 'Christmas Eve',
            '2025-12-25': 'Christmas Day', '2026-01-01': "New Year's Day", '2026-05-25': 'Memorial Day',
            '2026-07-03': 'Independence Day (observed)', '2026-09-07': 'Labor Day', '2026-11-26': 'Thanksgiving',
            '2026-11-27': 'Day after Thanksgiving', '2026-12-24': 'Christmas Eve', '2026-12-25': 'Christmas Day'}


def _month_shift(day: str, months: int) -> str:
    d = parse_day(day).replace(day=1)
    y, m = d.year, d.month + months
    while m <= 0:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return f'{y:04d}-{m:02d}-01'


def build(path: str, seed: int = 0, start: str = '2026-10-05', months: int = 12,
          close_through: str | None = None) -> Company:
    """The company on the morning of `start`, with history from the first day of the month `months` earlier."""
    hist_start = _month_shift(start, -months)
    last_period = period_of(_month_shift(start, 3))
    if close_through is None:
        close_through = period_of(_month_shift(start, -1))
    erp = setup.new_company(path, COMPANY, hist_start, period_of(hist_start), last_period, holidays=HOLIDAYS)
    with erp.tx():
        tokens = master_data(erp, seed, hist_start)
        need = history.monthly_component_need()
        for sku, monthly in need.items():
            erp.update('items', {'sku': sku}, {'safety_stock': round(monthly / 4.3 / 10) * 10})
        opening_balances(erp, hist_start, need)
    history.run(erp, seed, hist_start, add_days(start, -1), close_through)
    with erp.tx():
        erp.set_today(start)
    return Company(erp=erp, seed=seed, start=start, tokens=tokens)
