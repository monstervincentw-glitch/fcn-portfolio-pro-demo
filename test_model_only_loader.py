"""Ensure the live website loads only customer/holding facts from master ledger.

Synthetic rows; no spreadsheet writes, credentials or real client data.
"""
from sheets_backend import SheetsReader, DATA_RANGES


def test_live_model_only_loader_never_reads_duplicate_model_tabs():
    class FakeReader(SheetsReader):
        def read_many(self, ranges):
            assert ranges == [DATA_RANGES['customers'], DATA_RANGES['holdings']]
            return [
                [['customer_id', 'display_name', 'returned_principal_usd'],
                 ['測試甲*', '測試甲*', 999999]],
                [['holding_id', 'customer_id', 'product_id', 'currency',
                  'invested_amount', 'returned_principal_amount',
                  'estimated_principal_total', 'estimated_settlement_state'],
                 ['H-001', '測試甲*', 'SB04', 'USD', 150, 999999, 999999, 'OLD']],
            ]

    reader = FakeReader(master_sheet_id='synthetic', session=None)
    data = reader.portfolio(model_only=True)
    assert data['customers'] == [{'customer_id': '測試甲*', 'display_name': '測試甲*'}]
    assert data['holdings'] == [{
        'holding_id': 'H-001', 'customer_id': '測試甲*', 'product_id': 'SB04',
        'currency': 'USD', 'invested_amount': 150, 'trade_date': None,
    }]
    assert data['products'] == data['coupons'] == data['exceptions'] == []


def test_model_only_loader_does_not_require_legacy_projection_columns():
    class MinimalReader(SheetsReader):
        def read_many(self, ranges):
            return [
                [['customer_id', 'display_name'], ['測試乙*', '測試乙*']],
                [['holding_id', 'customer_id', 'product_id', 'currency',
                  'invested_amount'], ['H-002', '測試乙*', 'SP43', 'EUR', 200]],
            ]

    data = MinimalReader(master_sheet_id='synthetic', session=None).portfolio(model_only=True)
    assert data['holdings'][0]['invested_amount'] == 200
    assert data['holdings'][0]['product_id'] == 'SP43'
