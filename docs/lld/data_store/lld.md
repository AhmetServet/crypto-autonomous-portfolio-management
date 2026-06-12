# Data Store LLD

## 1. Purpose
This document describes the low-level design for the OHLCV storage module implemented with SQLAlchemy and TimescaleDB.

The module covers:
- environment-backed database and schema configuration
- logical coinpair registry plus id-based physical table management
- CRUD operations for OHLCV candles
- coverage metadata for stored OHLCV and derived data ranges
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
- id-based physical table creation on demand
- date-range reads using half-open ranges `[start_time, end_time)`
- merged coverage tracking for stored ranges
- DB-first reads for fully or partially covered historical fetches
- idempotent create/update behavior for repeated backfills
- delete operations for repair and maintenance flows
- database and schema configuration via `.env`

Out of scope:
- Alembic migrations
- retention/compression policies
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

### 4.1 Coinpair Registry And Id-Based Tables
Each logical trading pair is registered once in a shared `coinpairs` table.

Registry columns:
- `id`
- `symbol`

The registry id is then used to derive physical table names:
- raw OHLCV table: `coinpair_<id>_ohlcv`
- derived indicator/feature table: `coinpair_<id>_feature`

Examples:
- `BTCUSDT` with id `1` maps to `coinpair_1_ohlcv` and `coinpair_1_feature`
- `ETHUSDT` with id `2` maps to `coinpair_2_ohlcv` and `coinpair_2_feature`

This keeps physical table names stable and machine-oriented while preserving a normalized logical `symbol` for callers and coverage metadata.

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

### 4.3 Derived Feature Table Per Coinpair
Each trading pair also has a dedicated derived-data table backed by the same coinpair id.

Examples:
- `coinpair_1_feature`
- `coinpair_2_feature`

Each feature table stores:
- `interval`
- `open_time`
- `is_ready`
- `feature_payload`
- `missing_outputs`

Primary key:
- `(interval, open_time)`

Notes:
- feature values are stored as a JSON payload keyed by stable indicator names
- raw OHLCV remains the source of truth, while the feature table stores recomputable derived values
- canonical ML rows are assembled by joining raw and derived data on `(symbol, interval, open_time)`

### 4.4 Coverage Tables
The storage layer maintains three metadata tables:
- `ohlcv_coverage`
- `indicator_coverage`
- `feature_coverage`

Each coverage row stores:
- `id`
- `coinpair_id`
- `table_name`
- `symbol`
- `interval`
- `start_open_time`
- `end_open_time`

Coverage semantics:
- `start_open_time` is inclusive
- `end_open_time` is the inclusive open time of the last contiguous stored row
- overlapping and adjacent ranges for the same `coinpair_id + interval` are merged into one row

Current meanings:
- `ohlcv_coverage` tracks contiguous raw candle availability
- `indicator_coverage` tracks contiguous derived indicator availability in the physical feature table
- `feature_coverage` tracks the intersection of raw and derived availability, which is where canonical `FeatureRow` reads can be assembled without gaps

## 5. ORM Design

### 5.1 Dynamic Model Factory
`src/capm/infra/database/models.py` exposes a dynamic SQLAlchemy model factory:
- `get_ohlcv_model(symbol)`
- `candle_to_record(entity)`
- `get_feature_model(symbol)`
- `indicator_to_record(entity)`

Behavior:
- symbols are normalized through the existing market-data domain rules
- one coinpair registry row exists per logical symbol
- dynamic ORM models are cached per physical table name
- each generated OHLCV model maps to `coinpair_<id>_ohlcv`
- each generated derived model maps to `coinpair_<id>_feature`
- `to_domain()` reconstructs logical `symbol` from the model class metadata instead of the physical table name
- coverage models expose domain-friendly range records for fetch planning

### 5.2 Why Dynamic Models
The repository must support user-selected symbols without pre-declaring every possible pair at code generation time. Dynamic models keep the service layer simple while allowing symbol-scoped tables.

## 6. Repository Design

### 6.1 `TimescaleMarketDataRepository`
`src/capm/infra/database/timescale.py` is the concrete SQLAlchemy repository.

Responsibilities:
- normalize PostgreSQL connection strings for SQLAlchemy + psycopg
- create coinpair registry and coverage tables inside the configured schema
- create id-based raw and feature tables lazily for each logical symbol
- bootstrap TimescaleDB hypertables on PostgreSQL
- expose create/read/update/delete methods for OHLCV candles and derived indicator rows
- maintain merged coverage metadata for raw, derived, and canonical feature reads
- expose joined feature-row reads for ML-facing window assembly
- return predictable results even when a symbol table does not exist yet

### 6.2 CRUD Methods
`save_ohlcv_batch(candles)`:
- groups candles by symbol
- creates missing coinpair registry rows and raw tables on first write
- uses PostgreSQL `ON CONFLICT DO UPDATE` when the backend is PostgreSQL
- falls back to ORM `merge()` for non-PostgreSQL test environments
- updates `ohlcv_coverage`
- refreshes `feature_coverage`

`save_indicator_batch(records)`:
- groups derived rows by symbol
- creates missing feature tables on first write
- upserts by `(interval, open_time)`
- stores feature names and values in a JSON payload
- updates `indicator_coverage`
- refreshes `feature_coverage`

`get_candles(symbol, interval, start_time, end_time)`:
- returns candles ordered by `open_time ASC`
- uses half-open range semantics `[start_time, end_time)`
- returns an empty list if the symbol table does not exist

`plan_candle_fetch(symbol, interval, start_time, end_time)`:
- reads overlapping `ohlcv_coverage` rows
- returns the covered subranges plus any missing gap ranges
- treats adjacent stored coverage as reusable for one logical request

`get_candle(symbol, interval, open_time)`:
- reads exactly one candle by key
- returns `None` if no row exists

`get_latest_candle_time(symbol, interval)`:
- returns the latest stored `open_time`
- returns `None` if no rows exist

`delete_candles(symbol, interval, start_time, end_time)`:
- deletes candles in a half-open range
- returns the deleted row count
- rebuilds `ohlcv_coverage` from persisted rows
- refreshes `feature_coverage`

`get_indicator_batch(symbol, interval, start_time, end_time)`:
- returns derived rows ordered by `open_time ASC`
- uses half-open range semantics `[start_time, end_time)`
- returns an empty list if the feature table does not exist

`get_indicator_set(symbol, interval, open_time)`:
- reads exactly one derived row by key
- returns `None` if no row exists

`get_latest_indicator_time(symbol, interval)`:
- returns the latest stored derived-row `open_time`
- returns `None` if no rows exist

`delete_indicator_batch(symbol, interval, start_time, end_time)`:
- deletes derived rows in a half-open range
- returns the deleted row count
- rebuilds `indicator_coverage` from persisted rows
- refreshes `feature_coverage`

`get_feature_rows(symbol, interval, start_time, end_time)`:
- reads raw candles and aligned derived rows
- joins them in repository code to produce canonical feature rows
- returns placeholder non-ready rows when raw candles exist but derived rows are missing

`get_latest_complete_window(symbol, interval, window_size, required_features)`:
- reads the latest raw and derived rows for one symbol
- returns an incomplete window with an explicit gap reason when derived rows are missing
- returns a complete canonical window only when all required features are present

### 6.3 Schema Bootstrap
`initialize_schema(symbols)`:
- loads the TimescaleDB extension when using PostgreSQL
- creates the configured schema if needed
- ensures `coinpairs`, `ohlcv_coverage`, `indicator_coverage`, and `feature_coverage` exist
- ensures each requested raw and feature table exists
- converts each table into a hypertable

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
`src/capm/services/ingestion/historical.py` now:
- checks `ohlcv_coverage` before hitting the exchange
- serves fully covered requests directly from DB
- serves partially covered requests by reading covered ranges from DB and fetching only missing gaps
- persists only fetched candles that are inside the requested time range and not duplicates by `open_time`

This keeps storage semantics aligned with the service output while avoiding unnecessary refetches.

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
- dynamic coinpair table creation
- coverage table creation
- CRUD round-trips for a repository instance
- update behavior for repeated writes
- merged coverage after overlapping or adjacent writes
- gap planning for partially covered reads
- coverage repair after delete operations
- ingestion-service persistence semantics
- dotenv-backed database settings loading

Test command:
```bash
uv run python -m unittest discover -s tests -t . -v
```

## 10. Known Limitations
- per-coinpair physical tables still make cross-symbol analytics more complex than a single shared hypertable
- there is no migration layer yet
- there are no live integration tests against TimescaleDB in this slice
- compression, retention, and archival policies are not implemented yet

## 10.1 Current Dashboard/API Integration
The dashboard now exposes storage operations through FastAPI:

```text
POST /api/database/init
GET  /api/data/coverage
```

The Data tab can initialize symbols, inspect OHLCV/indicator/feature coverage, and display missing ranges. The dashboard uses the same repository and coverage tables as the CLI, so it does not introduce a separate data source.

## 11. Next Steps
1. Add integration tests against a real PostgreSQL + TimescaleDB instance.
2. Introduce explicit migration support once the schema stabilizes.
3. Evaluate whether feature payload JSON should remain the long-term storage shape or be partially normalized for large-scale ML jobs.
