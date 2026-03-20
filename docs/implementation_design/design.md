# Implementation Design

## 1. Purpose

This document defines the implementation architecture and delivery plan for the autonomous crypto portfolio management system.

It complements `docs/requirements/requirements_analysis.md` (what the system must do) and `docs/hld/hld.png` (high-level structure) by explaining:

- How code should be organized in Python
- Why specific architectural choices are preferred
- How to implement incrementally without losing long-term scalability

Keeping an explicit implementation design helps the team preserve module boundaries, avoid ad-hoc coupling, and onboard future contributors faster.

## 2. Architectural Context

The requirements define a 24/7, event-driven trading system with:

- Per-minute data ingestion and decision cycles
- Nightly retraining and watchlist refresh jobs
- Multiple model families (statistical, ML, DL, DRL)
- LLM-based final decision making
- Hard-rule risk controls before execution
- PostgreSQL-based storage and logs

At current project maturity, a **modular monolith** is the best fit:

- Deployment is on a personal VPS (simpler operations preferred)
- Team size is limited (optimize for developer velocity and reliability)
- Clear module separation is still required (avoid big-ball-of-mud)
- Future migration to services should remain possible if throughput grows

## 3. Core Architecture Decisions

### 3.1 Monolith with Strict Module Boundaries

We keep one deployable backend runtime, but enforce separation with package boundaries and contracts.

Why:

- Lower operational complexity than microservices
- Easier local development and debugging
- Strong consistency for trading-critical flows
- Still scalable with internal concurrency and clear module ownership

### 3.2 Django REST for Interface Layer

Use Django + DRF only for API/interface concerns.

Why:

- Mature ecosystem for authentication/admin/API concerns
- Good fit for dashboard integration and operational endpoints
- Stable long-term framework with many integrations

Constraint:

- Domain logic must not live in views/serializers.

### 3.3 SQLAlchemy for Persistence Layer

Use SQLAlchemy + Alembic for domain persistence, independent from Django ORM.

Why:

- Explicit control over sessions, transactions, and query performance
- Better alignment with repository/unit-of-work patterns
- Easier handling for time-series partitioning strategy in PostgreSQL

### 3.4 APScheduler for Job Orchestration

Use APScheduler for minute and nightly jobs in worker runtime.

Why:

- Lightweight and sufficient for current scale
- Simple deployment on single VPS
- Easy to introduce job locks and schedule guards

Future path:

- Migrate to distributed scheduler/queue only if scaling or reliability needs require it.

## 4. Target Project Structure

```text
.
├─ apps/
│  ├─ api/                            # Django project (REST interface)
│  │  ├─ manage.py
│  │  ├─ config/                      # settings, urls, asgi/wsgi
│  │  └─ api/                         # DRF views/serializers/controllers
│  └─ worker/                         # APScheduler runtime entrypoint
│     └─ run_worker.py
├─ src/
│  └─ capm/
│     ├─ core/
│     │  ├─ orchestrator/             # minute_cycle.py, nightly_cycle.py
│     │  ├─ contracts/                # Protocols/ports
│     │  ├─ events/                   # event definitions + bus
│     │  ├─ config/                   # typed config/settings
│     │  ├─ logging/                  # structured logs + correlation ids
│     │  ├─ errors/                   # exception hierarchy
│     │  └─ telemetry/                # metrics/tracing hooks
│     ├─ domains/
│     │  ├─ universe/
│     │  ├─ market_data/
│     │  ├─ features/
│     │  ├─ signals/
│     │  ├─ decisioning/
│     │  ├─ risk/
│     │  ├─ execution/
│     │  ├─ portfolio/
│     │  └─ backtesting/
│     ├─ services/
│     │  ├─ ingestion/
│     │  ├─ inference/
│     │  ├─ training/
│     │  └─ paper_trading/
│     ├─ models/
│     │  ├─ statistical/
│     │  ├─ ml/
│     │  ├─ dl/
│     │  ├─ drl/
│     │  ├─ optional_transformers/
│     │  └─ registry.py
│     ├─ infra/
│     │  ├─ db/
│     │  │  ├─ sqlalchemy/
│     │  │  └─ migrations/
│     │  ├─ exchange/
│     │  └─ llm/
│     └─ policies/
│        ├─ retry.py
│        └─ idempotency.py
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ contract/
│  └─ e2e/
├─ configs/
│  ├─ base.yaml
│  ├─ dev.yaml
│  ├─ prod.yaml
│  └─ model_profiles.yaml
├─ scripts/
└─ docs/
```

## 5. Dependency and Boundary Rules

Boundary rules are mandatory to keep modules clean:

1. `domains/*` cannot import `infra/*`.
2. `apps/api` and `apps/worker` call orchestrators/services, not low-level adapters.
3. External systems (Binance, OpenRouter, PostgreSQL) are behind contract interfaces.
4. Dependency injection and object wiring happen at composition roots (`apps/api`, `apps/worker`, and `src/capm/main.py`).
5. Retries and network fault handling live in adapters/policies, not in domain entities.

These rules protect business logic from vendor lock-in and simplify testing.

## 6. Module Responsibilities

### 6.1 Core

- `orchestrator`: coordinates workflows and enforces execution order.
- `contracts`: defines ports such as `ExchangePort`, `LLMPort`, `MarketDataRepository`.
- `events`: standard event payloads (`candle_closed`, `signals_ready`, etc.).
- `config`: typed settings and environment mapping.
- `logging` and `telemetry`: consistent observability.

### 6.2 Domains

- `universe`: inventory + top20 merge and lifecycle constraints.
- `features`: indicator computations and feature matrix contracts.
- `signals`: model output normalization/aggregation.
- `decisioning`: prompt construction, schema validation, retry-aware parsing.
- `risk`: hard rule validation with machine-readable violation reasons.
- `execution`: order intent lifecycle and result modeling.
- `portfolio`: holdings and balance snapshots.
- `backtesting`: simulation engine and metric outputs.

### 6.3 Services

- `ingestion`: historical REST backfill + WebSocket close-candle stream.
- `inference`: parallel model execution with timeout budget.
- `training`: nightly retraining and model version updates.
- `paper_trading`: testnet-first execution and health validation.

### 6.4 Infrastructure

- `infra/db/sqlalchemy`: engine, session factory, repositories, Alembic integration.
- `infra/exchange`: Binance REST and WebSocket clients.
- `infra/llm`: OpenRouter client and request/response plumbing.

## 7. Runtime Flow Design

### 7.1 Per-Minute Cycle

1. Receive closed-candle event.
2. Build `scan_universe = inventory_coins U top20_watchlist`.
3. Compute technical indicators and persist feature rows.
4. Run enabled models in parallel per coin.
5. Aggregate signals and perform one LLM decision call.
6. Retry malformed LLM responses up to 3 total attempts.
7. Validate every action in risk control layer.
8. Execute approved orders on exchange adapter.
9. Persist cycle logs, risk violations, and execution outcomes.

Design rationale:

- Keeps decision latency within one-minute budget.
- Isolates risk checks from model/LLM uncertainty.
- Produces full audit trail for post-incident analysis.

### 7.2 Nightly Cycle

1. Refresh top20 watchlist by 24h volume.
2. Backfill historical data for newly added symbols.
3. Append previous day data and regenerate training windows.
4. Retrain models (sliding window primary; incremental optional comparison).
5. Register selected active model versions.
6. Emit training performance and duration metrics.

Design rationale:

- Decouples heavy training jobs from real-time execution.
- Preserves deterministic deployment of model versions.

## 8. Data and Persistence Strategy

- PostgreSQL is the single source of truth for market, features, decisions, and orders.
- Partition strategy should support high-volume time series (symbol + time partitions).
- Use repository pattern plus unit-of-work for transaction integrity.
- Use idempotency keys for order submission and cycle processing safety.

## 9. Reliability, Security, and Observability

- Retries with exponential backoff for transient network/API failures only.
- Fail closed for risk or parsing ambiguity (skip unsafe order execution).
- Structured logs with correlation IDs per cycle.
- Metrics: cycle latency, inference timeout count, LLM retry count, risk reject count, order success rate.
- Secrets are env-based only; never logged.

## 10. Testing Strategy

- `unit`: pure domain logic (fast, deterministic, no external I/O).
- `integration`: repository + DB + adapter integration.
- `contract`: verify adapter behavior against port expectations.
- `e2e`: minute and nightly flow scenarios in test environment.

Core expectation:

- Critical risk rules and LLM response parsing paths require exhaustive test coverage.

## 11. Implementation Phases

### Phase 1: Foundation

- Create package skeleton and dependency boundaries.
- Implement config, logging, errors, contracts, and composition root.
- Initialize test scaffolding and CI quality checks.

### Phase 2: Data and Universe

- Implement SQLAlchemy models, repositories, and Alembic migrations.
- Implement Binance ingestion (historical + streaming).
- Implement scan universe logic and bootstrap behavior.

### Phase 3: Features and Inference

- Implement indicator pipeline and feature persistence.
- Implement model registry and parallel inference engine.
- Add timeout policies and partial-failure handling.

### Phase 4: Decision, Risk, Execution

- Implement LLM prompt/response module with retry handling.
- Implement hard risk rules and violation reporting.
- Implement paper-trading order execution adapter.

### Phase 5: Scheduler and Nightly Training

- Implement APScheduler runtime worker and job guards.
- Implement nightly refresh/backfill/retraining flow.
- Persist model versions and rollout metadata.

### Phase 6: API and Backtesting

- Implement Django REST endpoints for system state, controls, and logs.
- Implement backtesting engine and reporting outputs.

### Phase 7: Hardening

- Load/failure tests, operational runbooks, and alerting thresholds.
- Performance tuning for minute-cycle SLA on target VPS.

## 12. Risks and Mitigations

- **Risk:** Nightly DRL training exceeds time budget.
  - **Mitigation:** Make DRL optional/weekly; prioritize CPU-efficient models.
- **Risk:** LLM malformed output causes unstable decisions.
  - **Mitigation:** strict schema parsing, retry policy, fail-safe skip.
- **Risk:** Coupling between Django and domain logic.
  - **Mitigation:** keep Django thin, enforce domain package ownership.
- **Risk:** Database growth and query slowdowns.
  - **Mitigation:** partitioning, indexes, retention strategy, query profiling.

## 13. Definition of Done for Initial Architecture

Initial architecture is considered ready when:

1. Module skeleton and boundaries are enforced in code.
2. Minute and nightly orchestrators run end-to-end in dry mode.
3. Contract tests exist for exchange, LLM, and repository adapters.
4. Structured logs and metrics are emitted for each cycle.
5. Documentation and run instructions are updated.
