"""Regression: shared stock-library cells can be real Google Sheets DATE values.

The Oct 20 entry is the Sheets serial 46315 in UNFORMATTED_VALUE even though
the spreadsheet displays 2026-10-20. Synthetic prices only; no Sheets writes.
"""
from datetime import date
import pytest
import price_library_trial as trial


def test_mixed_iso_and_sheets_date_serials_preserve_price_alignment():
    dates = [["2026-10-19"], [46315]]
    columns = [
        [[100.0], [102.0]],
        [[200.0], [201.0]],
    ]
    frame, provenance = trial.parse_prices(
        ("AAPL", "NVDA"), ["交易日期", "AAPL", "NVDA"],
        dates, columns, date(2026, 10, 19), date(2026, 10, 20)
    )
    assert provenance.last == date(2026, 10, 20)
    assert provenance.joint_days == 2
    latest = frame[frame["date"].dt.date == date(2026, 10, 20)]
    assert dict(zip(latest["stock"], latest["ratio"])) == {"AAPL": 102.0, "NVDA": 201.0}


def test_latest_day_accepts_date_serial_without_rewriting_library(monkeypatch):
    class FakeReader:
        def read(self, spreadsheet, cell_range):
            return [["2026-10-19"], [46315.0]]
    monkeypatch.setattr(trial.SheetsReader, "from_secrets",
                        lambda *args: FakeReader())
    assert trial.latest_available_day({"synthetic": True}) == date(2026, 10, 20)


@pytest.mark.parametrize("bad", [46315.5, True, -1, 1e25, "46315", "2026/10/20", "2026-02-30"])
def test_invalid_day_data_fails_closed(bad):
    with pytest.raises(trial.PriceLibraryError):
        trial._trading_day(bad, 704)


def test_duplicated_dates_detected_across_iso_and_date_serial():
    with pytest.raises(trial.PriceLibraryError, match="重複交易日"):
        trial.parse_prices(
            ("AAPL",), ["交易日期", "AAPL"],
            [["2026-10-20"], [46315]], [[[100], [101]]],
            date(2026, 10, 19), date(2026, 10, 20),
        )


def test_missing_stock_close_remains_absent_not_forward_filled():
    dates = [["2026-10-19"], [46315]]
    with pytest.raises(trial.PriceLibraryError, match="共同有效交易日不足兩日"):
        trial.parse_prices(
            ("AAPL", "NVDA"), ["交易日期", "AAPL", "NVDA"],
            dates, [[[100], [102]], [[200], []]],
            date(2026, 10, 19), date(2026, 10, 20),
        )
