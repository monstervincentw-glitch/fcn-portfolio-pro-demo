"""Bounded synthetic partial-batch regression; no live reads or updater calls."""
from datetime import date
import pytest
from central_catalog import STOCK_LIBRARY_ID, load_market_matrix
from central_live_pages import model_exposure_rows
from test_central_cutover import FakeReader
from v2_portfolio_adapter import load_models

D15, D16, D19 = (date(2026, 10, n) for n in (15, 16, 19))


class PartialBatchReader(FakeReader):
    def __init__(self, missing=None, *, exited=False, matured=False):
        super().__init__()
        self.missing, self.exited, self.matured = missing, exited, matured
        self.rows = [(100, 200), (110, 220) if exited else (95, 190), (120, 240)]

    def read(self, sheet_id, span):
        if sheet_id == STOCK_LIBRARY_ID:
            self.calls.append((sheet_id, span))
            if span.endswith('A1:TJ1'):
                return [['交易日期', 'AMD', 'NVDA']]
            if span.endswith('A2:A'):
                return [[d.isoformat()] for d in (D15, D16, D19)]
            index = {'B': 0, 'C': 1}[span.split('!')[1][0]]
            ticker = ('AMD', 'NVDA')[index]
            return [[None if i == 2 and ticker == self.missing else row[index]]
                    for i, row in enumerate(self.rows)]
        result = super().read(sheet_id, span)
        if span.startswith("'API_商品條款_V1'"):
            result[0] += ['latest_close']
            result[1] += [999999]  # Poison central stale close; must never be used.
            result[1][4] = '2026-10-16' if self.matured else '2026-10-20'
            result[1][5] = '2026-10-19' if self.matured else '2026-10-21'
        elif span.startswith("'API_標的_V1'"):
            result = [['product_id', 'leg_no', 'ticker', 'initial_price', 'latest_close'],
                      ['TEST01', 1, 'AMD', 100, 999999],
                      ['TEST01', 2, 'NVDA', 200, 999999]]
        elif span.startswith("'配息期'"):
            result[1][4] = '2026-10-16' if self.matured else '2026-10-20'
            result[1][5] = '2026-10-19' if self.matured else '2026-10-21'
        return result


@pytest.mark.parametrize('missing', ['AMD', 'NVDA'])
def test_partial_latest_row_blocks_events_but_preserves_last_complete_day(missing):
    reader = PartialBatchReader(missing)
    market, latest, _ = load_market_matrix(reader, {'AMD', 'NVDA'})
    assert latest == D19 and market[D19][missing] is None
    catalog, models = load_models(reader, today=D19)
    model = models['TEST01']
    assert model.latest_date == D16 and model.issues
    assert model.ko_date is None and model.ki_touched is None
    assert model.principal_ratio is None and model.category == '比價中'
    for quote in model.quote_rows:
        day = date.fromisoformat(quote['收盤日期'])
        # Individual last quotes retain their real dates; they are not forward-filled.
        assert quote['最新收盤價'] == market[day][quote['股票']]
        assert quote['最新收盤價'] != 999999
    exposure = model_exposure_rows(catalog, models, 'AMD', [{'product_id': 'TEST01'}])
    assert exposure[0]['最新行情日期'] == '2026/10/16'
    assert exposure[0]['存續曝險'] == '待確認（資料不足）'


def test_filling_shared_library_cell_advances_model_and_exposure_together():
    reader = PartialBatchReader()
    catalog, models = load_models(reader, today=D19)
    model = models['TEST01']
    assert not model.issues and model.latest_date == model.ko_date == D19
    assert model.principal_ratio == 1
    assert {q['收盤日期'] for q in model.quote_rows} == {'2026-10-19'}
    assert {q['最新收盤價'] for q in model.quote_rows} == {120, 240}
    exposure = model_exposure_rows(catalog, models, 'AMD', [{'product_id': 'TEST01'}])
    assert exposure[0]['存續曝險'] == '無（模型已出場）'
    assert exposure[0]['最新行情日期'] == '2026/10/19'


@pytest.mark.parametrize('exit_type', ['ko', 'maturity'])
def test_exited_product_does_not_extend_quotes_into_new_library_row(exit_type):
    reader = PartialBatchReader('AMD', exited=exit_type == 'ko',
                                matured=exit_type == 'maturity')
    _, models = load_models(reader, today=D19)
    model = models['TEST01']
    assert not model.issues and model.principal_ratio == 1
    assert model.latest_date == D16
    assert {q['收盤日期'] for q in model.quote_rows} == {'2026-10-16'}
    assert max(row['date'] for row in model.price_history) == D16
