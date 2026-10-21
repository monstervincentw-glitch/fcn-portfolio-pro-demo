# PR #2 focused release review — 2026-10-21

Base: `5abffa1c80cb0cb97f0240dfe8ac70c60483fd46`.
Reviewed PR head: `6dae68c7565209231528fef91d8b1543c1b75485`.
Formula fix: `80994c7e83854009e95297287b4a3ea0aaa9d616`.

## Result

The model-only change passes focused review with one adapter fix: a valid active
holding now reports recovered principal `0.0`, not `None`, on both customer pages.
Unavailable inputs remain `None`; known subtotals retain per-measure missing counts
and the UI explicitly warns that they are not complete portfolio totals.

Reviewed `currency_summary`, `enrich_new_holdings`, `model_one`, `calculate_v2`,
`portfolio(model_only=True)`, both customer views and the native catalog entry.
Principal recovery is holding capital times the model ratio; terminated loss is
not outstanding exposure. Active capital stays outstanding. Earned coupon uses
completed periods or KO prorating; forecast coupon remains separate. Models run
once per product, then apply to each holding. USD/EUR/JPY are separate.

Canonical V2 KO redeems at par; loss redemption is tested at maturity. A separate
defensive adapter test confirms it honors a supplied partial recovery ratio even
when a synthetic model has a KO label; this does not assert such a real contract.

Live master reads are limited to customer and holding facts. Product terms and
market data are loaded from the existing central catalog and shared stock library.
Legacy receipt/projection values, old product tabs, coupon cache and exception
overrides are excluded. No changes to V2 mechanics, PIN, Secrets, updater or Sheets.

## Executed validation

Initial focused baseline: 25 passed, 8 deselected.
Adapter formula fix: 11 passed.
Final affected suite: 89 passed, 8 deselected (15.27 seconds):

```sh
python -m pytest -q test_model_only_overview.py test_model_only_loader.py \
  test_price_source_p0.py test_ko_lifecycle.py test_ko_pages.py \
  test_v2_redemption.py test_e2e_acceptance.py \
  -k 'not history and not http' --tb=short
```

Additional direct-entry PIN checks: 2 passed, 25 deselected:

```sh
python -m pytest -q test_e2e_acceptance.py -k direct_entry --tb=short
```

Final validation comprises 91 distinct relevant cases. Includes full KO recovery,
maturity par/loss, valid active holdings, missing quotes/terms, repeated product
holdings, currency separation, partial totals, customer switching, refresh, stale
result removal, source isolation, masking, logout/session expiry and PIN-before-read
on both application entry points. Updated obsolete lifecycle assertions and fake
reader signature to match the intentional model-only contract.

All customer fixtures are fictional. Existing public product/price evidence is
replayed offline for integration tests. No production financial values or secrets
are included. These results are local integration evidence, not live-site acceptance.

## Deployment handoff

PR #2 must be merged only at the reviewed and tested head. Confirm the deployed
Streamlit SHA independently after merge. Real client principal recovery, current
updater executions and PIN-protected pages require an authorized live session;
do not report them as passed from these tests.
