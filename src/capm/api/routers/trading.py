"""Trading agent and Spot Demo routes."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from capm.core.config import BinanceSettings, LLMSettings
from capm.domains.trading import DecisionAction, PortfolioSnapshot, ProposedDecision
from capm.infra.exchange import BinanceSpotDemoTradingAdapter
from capm.main import (
    _agent_decision_payload,
    _build_live_cycle_service,
    _live_cycle_payload,
    _risk_config_from_args,
    build_repository,
    parse_datetime,
)
from capm.services.llm_decision_policy import LLMDecisionPolicy
from capm.services.trading_agent import TradingAgentService

from ..dependencies import SpotDemoAdapterDependency
from ..loop_registry import create_loop_job, get_loop_job, list_loop_jobs, stop_loop_job
from ..schemas import (
    AgentRunOnceRequest,
    JournalSummaryRequest,
    LiveCycleLoopRequest,
    LiveCycleRunOnceRequest,
    SpotDemoMarketBuyRequest,
    SpotDemoMarketSellRequest,
)
from ..shared import risk_args_from_request

router = APIRouter()


@router.post("/api/agent/run-once")
def agent_run_once(request: AgentRunOnceRequest) -> object:
    if request.policy == "threshold" and not request.symbol:
        raise HTTPException(status_code=400, detail="Threshold policy requires symbol.")
    repository = build_repository()
    portfolio = PortfolioSnapshot(
        available_usdt=request.dry_run_usdt_balance,
        base_asset_free=request.dry_run_base_asset_balance,
    )
    risk_config = _risk_config_from_args(risk_args_from_request(request))
    exchange_adapter = None
    if request.mode == "spot-demo":
        exchange_adapter = BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))
    service = TradingAgentService(repository=repository, exchange_adapter=exchange_adapter)
    try:
        if request.policy == "llm":
            llm_policy = LLMDecisionPolicy(LLMSettings.from_env())
            try:
                entries = service.run_llm_once(
                    interval=request.interval,
                    mode=request.mode,
                    portfolio=portfolio,
                    risk_config=risk_config,
                    llm_policy=llm_policy,
                )
            finally:
                llm_policy.close()
        else:
            entries = (
                service.run_once(
                    symbol=str(request.symbol),
                    interval=request.interval,
                    mode=request.mode,
                    portfolio=portfolio,
                    risk_config=risk_config,
                ),
            )
        payload = {"status": "ok", "decisions": [_agent_decision_payload(entry) for entry in entries]}
        if request.show_prompt:
            if request.policy != "llm":
                raise HTTPException(status_code=400, detail="show_prompt requires policy=llm.")
            batch = service.last_llm_batch
            if batch is None:
                raise HTTPException(status_code=500, detail="LLM prompt metadata was not produced.")
            payload["llm"] = {
                "system_prompt": batch.system_prompt,
                "prompt": batch.prompt,
                "raw_response": batch.raw_response,
                "attempts": batch.attempts,
                "model": batch.model,
                "provider_host": batch.provider_host,
                "latency_seconds": batch.latency_seconds,
                "usage": batch.usage,
            }
        return jsonable_encoder(payload)
    finally:
        if exchange_adapter is not None:
            exchange_adapter.close()


@router.post("/api/agent/journal/summary")
def agent_journal_summary(request: JournalSummaryRequest) -> object:
    repository = build_repository()
    summary = repository.summarize_agent_decision_journal(
        symbol=request.symbol,
        interval=request.interval,
        start_time=parse_datetime(request.start),
        end_time=parse_datetime(request.end),
    )
    return jsonable_encoder({"status": "ok", "summary": summary.to_dict()})


@router.get("/api/spot-demo/portfolio")
def spot_demo_portfolio(adapter: SpotDemoAdapterDependency, symbol: str = Query(default="BTCUSDT", min_length=1)) -> object:
    try:
        portfolio = adapter.get_portfolio(symbol)
        return jsonable_encoder({"status": "ok", "symbol": symbol, "portfolio": portfolio.to_dict()})
    finally:
        adapter.close()


@router.post("/api/spot-demo/market-buy")
def spot_demo_market_buy(adapter: SpotDemoAdapterDependency, request: SpotDemoMarketBuyRequest) -> object:
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Manual Spot Demo market buy requires confirm=true.")
    try:
        before = adapter.get_portfolio(request.symbol)
        order = adapter.submit_market_order(
            request.symbol,
            ProposedDecision(action=DecisionAction.BUY, requested_usdt_amount=request.usdt_amount),
        )
        after = adapter.get_portfolio(request.symbol)
        return jsonable_encoder(
            {
                "status": "ok",
                "symbol": request.symbol,
                "usdt_amount": request.usdt_amount,
                "portfolio_before": before.to_dict(),
                "order": order,
                "portfolio_after": after.to_dict(),
            }
        )
    finally:
        adapter.close()


@router.post("/api/spot-demo/market-sell")
def spot_demo_market_sell(adapter: SpotDemoAdapterDependency, request: SpotDemoMarketSellRequest) -> object:
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Manual Spot Demo market sell requires confirm=true.")
    try:
        before = adapter.get_portfolio(request.symbol)
        order = adapter.submit_market_order(
            request.symbol,
            ProposedDecision(action=DecisionAction.SELL, requested_quantity=request.quantity),
        )
        after = adapter.get_portfolio(request.symbol)
        return jsonable_encoder(
            {
                "status": "ok",
                "symbol": request.symbol,
                "quantity": request.quantity,
                "portfolio_before": before.to_dict(),
                "order": order,
                "portfolio_after": after.to_dict(),
            }
        )
    finally:
        adapter.close()


@router.post("/api/agent/run-live-once")
def agent_run_live_once(request: LiveCycleRunOnceRequest) -> object:
    args = SimpleNamespace(
        interval=request.interval,
        mode=request.mode,
        model_artifact=request.model_artifacts,
        market_data_mode=request.market_data_mode,
        max_inline_gap_minutes=request.max_inline_gap_minutes,
        max_model_age_days=request.max_model_age_days,
        allow_large_gap_recovery=request.allow_large_gap_recovery,
        allow_stale_models=request.allow_stale_models,
        max_trade_usdt=request.max_trade_usdt,
        max_position_usdt=request.max_position_usdt,
        emergency_stop=request.emergency_stop,
        max_daily_realized_loss_usdt=request.max_daily_realized_loss_usdt,
        max_orders_per_day=request.max_orders_per_day,
        order_cooldown_minutes=request.order_cooldown_minutes,
        max_total_exposure_usdt=request.max_total_exposure_usdt,
    )
    service, market_data_adapter, exchange_adapter, llm_policy = _build_live_cycle_service(args)
    try:
        return jsonable_encoder(_live_cycle_payload(service.run_once(interval=request.interval, mode=request.mode)))
    finally:
        llm_policy.close()
        market_data_adapter.close()
        if exchange_adapter is not None:
            exchange_adapter.close()


@router.get("/api/agent/loops")
def agent_loops() -> object:
    return jsonable_encoder(list_loop_jobs())


@router.get("/api/agent/loops/{loop_id}")
def agent_loop(loop_id: str) -> object:
    payload = get_loop_job(loop_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Live loop {loop_id} was not found.")
    return jsonable_encoder(payload)


@router.post("/api/agent/loops")
def start_agent_loop(request: LiveCycleLoopRequest) -> object:
    try:
        return jsonable_encoder(create_loop_job(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/agent/loops/{loop_id}/stop")
def stop_agent_loop(loop_id: str) -> object:
    payload = stop_loop_job(loop_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Live loop {loop_id} was not found.")
    return jsonable_encoder(payload)
