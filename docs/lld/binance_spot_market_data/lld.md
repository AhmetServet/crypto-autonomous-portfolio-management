# Binance Spot Market Data LLD

## 1. Purpose
This document describes the low-level design of the first implemented market-data module in `src/capm`.

The module covers:
- historical OHLCV retrieval from Binance spot
- request validation and normalization
- page-by-page backfill across Binance kline limits
- a CLI entrypoint for manual retrieval
- unit tests for domain, service, and adapter behavior

This is the first implementation slice of Phase 1 and Phase 2 from `docs/implementation_design/design.md`.

## 2. Scope
Included in scope:
- public REST access to Binance `klines`
- symbol normalization such as `BTC/USDT` -> `BTCUSDT`
- supported interval validation
- UTC normalization for time boundaries
- pagination across bounded date ranges
- retry and backoff for transient request failures
- JSON serialization for CLI output

Out of scope for this module:
- persistence to PostgreSQL
- WebSocket streaming
- backfill gap detection against stored candles
- account, balance, or order endpoints
- signed/private Binance API integration
- scheduler integration

## 3. Module Layout
```text
src/capm/
├─ core/
│  ├─ config/settings.py
│  ├─ contracts/market_data.py
│  └─ errors/__init__.py
├─ domains/
│  └─ market_data/entities.py
├─ services/
│  └─ ingestion/historical.py
├─ infra/
│  └─ exchange/binance_spot.py
└─ main.py
```

## 4. Responsibilities

### 4.1 `core.config.settings.BinanceSettings`
Responsibilities:
- define runtime settings for Binance access
- choose demo or live mode
- read environment variables
- validate timeout, retry, and page-size constraints

Current environment variables:
- `CAPM_BINANCE_MODE`
- `CAPM_BINANCE_SPOT_REST_BASE_URL`
- `CAPM_BINANCE_TIMEOUT_SECONDS`
- `CAPM_BINANCE_RETRY_ATTEMPTS`
- `CAPM_BINANCE_RETRY_BACKOFF_SECONDS`
- `CAPM_BINANCE_TRUST_ENV`

Notes:
- `trust_env` is disabled by default so local proxy settings do not silently alter exchange requests.
- the REST base URL is configurable to avoid hard-coding environment assumptions into the rest of the module.

### 4.2 `core.contracts.market_data.HistoricalMarketDataPort`
Responsibilities:
- define the adapter contract used by ingestion services
- keep the service layer independent from a specific exchange SDK or HTTP implementation

Method:
- `fetch_ohlcv_page(...) -> list[OHLCV]`

### 4.3 `domains.market_data.entities`
Responsibilities:
- define the canonical candle model `OHLCV`
- define the validated request model `HistoricalOHLCRequest`
- normalize user-facing trading pair formats
- validate Binance interval values
- normalize datetimes into UTC

Key rules:
- `start_at` must be earlier than `end_at`
- `max_records_per_page` must stay within Binance's `1..1000` limit
- intervals must be explicitly supported
- symbols must be alphanumeric after normalization

### 4.4 `services.ingestion.historical.HistoricalMarketDataIngestionService`
Responsibilities:
- fetch all candles across a requested time range
- paginate using the exchange port
- deduplicate candles by `open_time`
- stop safely if the port returns no more data
- detect non-advancing pagination and fail fast

This service does not know about HTTP, Binance payload shapes, or CLI behavior.

### 4.5 `infra.exchange.binance_spot.BinanceSpotMarketDataAdapter`
Responsibilities:
- translate domain requests into Binance REST query parameters
- call `/api/v3/klines`
- retry transient failures with exponential backoff
- map raw Binance kline arrays into `OHLCV`
- surface application-specific errors for invalid responses or request failures

Important boundary:
- this adapter implements exchange-specific concerns only
- higher-level pagination remains in the service layer

### 4.6 `main.py`
Responsibilities:
- act as the composition root for this slice
- parse CLI arguments
- convert CLI datetime strings to UTC-aware `datetime`
- build settings, adapter, service, and validated request
- print serialized candle data as JSON

## 5. Runtime Flow

### 5.1 CLI Flow
1. User runs `uv run capm fetch-ohlc ...`
2. `main.py` parses CLI arguments.
3. `parse_datetime()` converts `--start` and `--end` into UTC-aware datetimes.
4. `fetch_ohlcv()` builds `BinanceSettings`, `BinanceSpotMarketDataAdapter`, and `HistoricalMarketDataIngestionService`.
5. `HistoricalOHLCRequest` validates the symbol, interval, and date range.
6. The ingestion service loops over the requested range page by page.
7. The adapter calls Binance `/api/v3/klines`.
8. Binance payload rows are mapped into `OHLCV`.
9. The service deduplicates candles and advances the pagination cursor.
10. The final candle list is serialized to JSON and printed.

### 5.2 Pagination Algorithm
The ingestion service uses the request interval to estimate how many candles remain in the range, then requests:

`limit = min(max_records_per_page, remaining_candles)`

After a page returns:
- the service sets the next cursor to `last_page_open_time + interval_delta`
- duplicate `open_time` values are ignored
- candles outside the requested half-open range `[start_at, end_at)` are skipped

Guard condition:
- if the next cursor does not move forward, the service raises `PaginationError` to avoid an infinite loop

## 6. Data Contracts

### 6.1 `HistoricalOHLCRequest`
Fields:
- `symbol`
- `interval`
- `start_at`
- `end_at`
- `max_records_per_page`

Derived property:
- `interval_delta`

Normalization behavior:
- symbol input is uppercased and separators are removed
- naive datetimes are treated as UTC
- aware datetimes are converted to UTC

### 6.2 `OHLCV`
Fields:
- `symbol`
- `interval`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `quote_asset_volume`
- `trade_count`
- `taker_buy_base_asset_volume`
- `taker_buy_quote_asset_volume`

Serialization:
- numeric values are converted to strings in `to_dict()` to preserve decimal precision in JSON output

## 7. Error Handling Strategy
Application-specific exceptions live under `core.errors`.

Current error types used by this module:
- `ConfigurationError`
- `ValidationError`
- `ExchangeAPIError`
- `PaginationError`

Rules:
- invalid user input fails before network access
- malformed exchange payloads fail in the adapter
- repeated transient request failures are retried, then wrapped in `ExchangeAPIError`
- non-advancing pages fail in the service

HTTP behavior:
- `4xx` responses other than `429` are treated as immediate request rejection
- network and retryable failures are retried with exponential backoff

## 8. Test Coverage
Current unit tests:
- `tests/unit/test_market_data_domain.py`
  - request normalization
  - unsupported interval rejection
- `tests/unit/test_historical_ingestion.py`
  - multi-page retrieval
  - cursor advancement
  - deduplicated range assembly
- `tests/unit/test_binance_spot_adapter.py`
  - request construction
  - symbol normalization
  - payload mapping

Current test command:
```bash
uv run python -m unittest discover -s tests -t . -v
```

## 9. Security and Authentication
- this module currently uses only public market-data endpoints
- no API key or secret is required for historical klines retrieval
- signed/private Binance endpoints are intentionally out of scope for this slice
- secrets remain environment-based once private endpoints are introduced later

## 10. Known Limitations
- no persistence layer yet, so all fetched data is in-memory only
- no WebSocket stream handling yet
- no gap-repair against stored historical datasets yet
- no rate-limit budgeting beyond basic retries
- no structured logging or metrics yet
- no integration or contract tests against a live Binance environment

## 11. Next Integration Steps
Recommended follow-up work:
1. add SQLAlchemy models and repositories for raw candles
2. persist backfilled candles idempotently
3. add exchange metadata discovery for valid symbols
4. implement WebSocket close-candle ingestion for `1m`
5. add integration tests that exercise the configured Binance base URL
