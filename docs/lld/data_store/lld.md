# Data Store LLD

## 1. Purpose
This document describes the low-level design for the OHLCV storage module implemented with SQLAlchemy and TimescaleDB.

The module covers:
- environment-backed database and schema configuration
- symbol-scoped table management such as `BTCUSDT`
- CRUD operations for OHLCV candles
- TimescaleDB hypertable bootstrap for each symbol table
- repository behavior used by ingestion services
- unit-test strategy for the storage layer

This document complements:
- `docs/requirements/requirements_analysis.md`
- `docs/implementation_design/design.md`
- `docs/lld/binance_spot_market_data/lld.md`

## 2. Scope
Included in scope:
- storage of Binance OHLCV candles by symbol pair
- symbol-specific table creation on demand
- date-range reads using half-open ranges `[start_time, end_time)`
- idempotent create/update behavior for repeated backfills
- delete operations for repair and maintenance flows
- database and schema configuration via `.env`

Out of scope:
- Alembic migrations
- retention/compression policies
- feature-matrix persistence
- cross-symbol analytics queries
- integration tests against a live TimescaleDB instance

## 3. Module Layout
```text
src/capm/
├─ core/
│  └─ config/settings.py
└─ infra/
   └─ database/
      ├─ models.py
      └─ timescale.py
```

## 4. Storage Strategy

### 4.1 Table Per Symbol
Each trading pair is stored in its own table.

Examples:
- `BTCUSDT`
- `ETHUSDT`
- `BNBUSDT`

This satisfies the expected operational model where a symbol can be backfilled and queried independently with a dedicated table name.

### 4.2 Table Schema
Each symbol table stores:
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

Primary key:
- `(interval, open_time)`

Notes:
- the symbol is implied by the table name and reconstructed when mapping rows back to the domain `OHLCV`
- `open_time` stays in the primary key to match TimescaleDB uniqueness expectations for time-series tables
- a single symbol table can hold multiple intervals if needed later

## 5. ORM Design

### 5.1 Dynamic Model Factory
`src/capm/infra/database/models.py` exposes a dynamic SQLAlchemy model factory:
- `get_ohlcv_model(symbol)`
- `candle_to_record(entity)`

Behavior:
- symbols are normalized through the existing market-data domain rules
- one ORM model class is cached per symbol
- each generated model maps to a table named after that normalized symbol
- `to_domain()` reconstructs `OHLCV` using the symbol encoded in the model class

### 5.2 Why Dynamic Models
The repository must support user-selected symbols without pre-declaring every possible pair at code generation time. Dynamic models keep the service layer simple while allowing symbol-scoped tables.

## 6. Repository Design

### 6.1 `TimescaleMarketDataRepository`
`src/capm/infra/database/timescale.py` is the concrete SQLAlchemy repository.

Responsibilities:
- normalize PostgreSQL connection strings for SQLAlchemy + psycopg
- create symbol tables lazily inside the configured schema
- bootstrap TimescaleDB hypertables on PostgreSQL
- expose create/read/update/delete methods for OHLCV candles
- return predictable results even when a symbol table does not exist yet

### 6.2 CRUD Methods
`save_ohlcv_batch(candles)`:
- groups candles by symbol
- creates missing symbol tables on first write
- uses PostgreSQL `ON CONFLICT DO UPDATE` when the backend is PostgreSQL
- falls back to ORM `merge()` for non-PostgreSQL test environments

`get_candles(symbol, interval, start_time, end_time)`:
- returns candles ordered by `open_time ASC`
- uses half-open range semantics `[start_time, end_time)`
- returns an empty list if the symbol table does not exist

`get_candle(symbol, interval, open_time)`:
- reads exactly one candle by key
- returns `None` if no row exists

`get_latest_candle_time(symbol, interval)`:
- returns the latest stored `open_time`
- returns `None` if no rows exist

`delete_candles(symbol, interval, start_time, end_time)`:
- deletes candles in a half-open range
- returns the deleted row count

### 6.3 Schema Bootstrap
`initialize_schema(symbols)`:
- loads the TimescaleDB extension when using PostgreSQL
- creates the configured schema if needed
- ensures each requested symbol table exists
- converts each symbol table into a hypertable

The repository also creates tables lazily during writes, so ingestion can persist a new symbol without a separate migration step.

### 6.4 First-Run Bootstrap
`src/capm/init_db.py` provides the first-run bootstrap flow.

Responsibilities:
- connect to the configured PostgreSQL database
- create the configured schema if it does not exist yet
- initialize the Timescale extension
- optionally create schema-scoped symbol tables before ingestion starts

Recommended first-run command:
```bash
uv run capm-init-db --symbol BTCUSDT
```

## 7. Ingestion Boundary
`src/capm/services/ingestion/historical.py` persists only candles that are:
- inside the requested time range
- not duplicates by `open_time`

This keeps storage semantics aligned with the service output returned to callers.

## 8. Configuration

### 8.1 Settings
`src/capm/core/config/settings.py` contains:
- `BinanceSettings`
- `DatabaseSettings`

Both settings classes load `.env` values automatically via `python-dotenv`.

### 8.2 Environment Variables
Primary database variable:
- `CAPM_DATABASE_URL`

Primary schema variable:
- `CAPM_DATABASE_SCHEMA`

Compatibility fallback:
- `DATABASE_URL`

Reference values live in:
- `.env.example`

## 9. Testing Strategy
Current automated coverage should include:
- model/domain round-trip behavior
- dynamic symbol table creation
- CRUD round-trips for a repository instance
- update behavior for repeated writes
- ingestion-service persistence semantics
- dotenv-backed database settings loading

Test command:
```bash
uv run python -m unittest discover -s tests -t . -v
```

## 10. Known Limitations
- per-symbol tables make cross-symbol analytics more complex than a single shared hypertable
- there is no migration layer yet
- there are no live integration tests against TimescaleDB in this slice
- compression, retention, and archival policies are not implemented yet

## 11. Next Steps
1. Add integration tests against a real PostgreSQL + TimescaleDB instance.
2. Introduce explicit migration support once the schema stabilizes.
3. Evaluate whether feature rows should live beside raw OHLCV or in separate symbol-scoped tables.
