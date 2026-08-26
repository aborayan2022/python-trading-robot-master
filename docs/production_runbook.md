# Production Runbook: Alpaca Paper First

This project is production-gated for US equities through Alpaca. Live trading is
disabled by default and must remain locked until the paper-trading acceptance
period is complete.

## Profiles

- `replay`: deterministic synthetic replay. No external credentials.
- `alpaca_paper`: Alpaca paper account, real market data polling, real paper orders.
- `alpaca_live_locked`: live Alpaca account. Fails unless
  `PYROBOT_ALLOW_LIVE_TRADING=true` is set explicitly.

## Start

Replay smoke test:

```powershell
$env:PYROBOT_PROFILE="replay"
$env:PYROBOT_SIGNAL_SOURCE="example"
python -m pyrobot.runtime.loop
```

Alpaca paper:

```powershell
$env:ALPACA_API_KEY="..."
$env:ALPACA_SECRET_KEY="..."
$env:PYROBOT_PROFILE="alpaca_paper"
$env:PYROBOT_SYMBOLS="MSFT,AAPL"
$env:PYROBOT_BAR_INTERVAL="60"
python -m pyrobot.runtime.loop
```

## Stop Conditions

The system must halt trading when any of these occur:

- stale or missing market data during the Alpaca polling profile
- position, cash, or unknown open-order mismatch during reconciliation
- daily loss, drawdown, or exposure limit breach
- audit ledger integrity failure
- repeated broker/order failures

## Daily Review

Review these artifacts after every session:

- audit ledger: `data/audit/ledger.jsonl`
- runtime metrics: `data/metrics/runtime_metrics.jsonl`
- daily report generated with `pyrobot.monitoring.build_daily_report`
- Alpaca paper account activity and open orders

No live capital should be enabled until 3-6 months of uninterrupted paper
operation show stable reconciliation, clean audit integrity, controlled
drawdowns, and out-of-sample model performance after costs.
