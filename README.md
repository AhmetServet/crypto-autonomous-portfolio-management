# Autonomous Portfolio Management in Crypto Spot Markets: Experimental Analysis and Development of Hybrid Artificial Intelligence Approaches

This is the monorepo of our graduation project. Everything including docs, analyses and source code stays here.

## Our Team
- Ahmet Servet Polat
- Kenan Koçoğlu
- Mehmet Enes Odabaş

## Python Workspace
The first implementation slice now includes a Python package under `src/capm` for Binance spot market-data ingestion.

### Documentation
- Binance market-data LLD: `docs/lld/binance_spot_market_data/lld.md`
- Data-store LLD: `docs/lld/data_store/lld.md`

### Setup
```bash
uv sync
```

Create a local environment file before running the storage example:
```bash
cp .env.example .env
```

Initialize the CAPM schema before the first ingestion run:
```bash
uv run capm-init-db --symbol BTCUSDT
```

Bootstrap now creates the shared `coinpairs`, `ohlcv_coverage`, `feature_coverage`, and `indicator_coverage` tables. Logical symbols are still passed as `BTCUSDT`, but the physical raw/derived tables are created with id-based names such as `coinpair_1_ohlcv` and `coinpair_1_feature`.

### Fetch OHLC Data
The CLI currently supports historical OHLCV retrieval from Binance spot demo mode or live mode.

```bash
uv run capm fetch-ohlc \
  --symbol BTC/USDT \
  --interval 1m \
  --start 2024-01-01T00:00:00Z \
  --end 2024-01-01T01:00:00Z \
  --mode demo
```

Notes:
- `--start` is inclusive.
- `--end` is exclusive.
- Supported intervals currently include `1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, and `1w`.
- In repository-backed ingestion flows, stored coverage is checked first so fully covered ranges are served from DB and only missing gaps are fetched from Binance.

### Tests
```bash
uv run python -m unittest discover -s tests -t . -v
```