"""Fundamental ratio computation and health/valuation scoring.

All scores are normalized to the range [-100, +100]:
  positive  -> favourable (profitable, growing, attractively priced)
  negative  -> unfavourable

The scoring uses smooth banding functions so slight changes in a metric map to
small score changes instead of hard cliffs.
"""
from __future__ import annotations

import math

from app.data.base import FundamentalData


def _clamp(x: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _band(value: float, mid: float, scale: float) -> float:
    """Map value -> -100..100 via a soft logistic centred at `mid`."""
    if value is None or (value != value):  # NaN guard
        return 0.0
    return _clamp(100.0 * math.tanh((value - mid) / max(scale, 1e-9)))


def _inv_band(value: float, mid: float, scale: float) -> float:
    """Inverse logistic ('lower is better'), used for valuation multiples."""
    return -_band(value, mid, scale)


# --------------------------------------------------------------- health
def _proft_sc(metrics: dict) -> dict[str, float]:
    """Profitability components."""
    return {
        "roe": _band(metrics.get("roe"), 0.15, 0.20),
        "roa": _band(metrics.get("roa"), 0.07, 0.12),
        "net_margin": _band(metrics.get("net_margin"), 0.12, 0.15),
        "gross_margin": _band(metrics.get("gross_margin"), 0.35, 0.30),
        "operating_margin": _band(metrics.get("operating_margin"), 0.15, 0.20),
    }


def _liquidity_sc(metrics: dict) -> dict[str, float]:
    """Liquidity: higher is safer, but extreme is mediocre."""
    cur = metrics.get("current_ratio")
    quick = metrics.get("quick_ratio")
    cur_sc = _band(cur, 1.5, 1.0) * (1 - min(abs((cur or 0) - 1.5), 6) / 40) if cur else 0.0
    quick_sc = _band(quick, 1.0, 0.8) * (1 - min(abs((quick or 0) - 1.0), 6) / 40) if quick else 0.0
    cash = metrics.get("cash_per_share")
    price = metrics.get("last_price")
    cash_sc = _band(cash / price, 0.10, 0.25) if (cash and price) else 0.0
    return {"current_ratio": _clamp(cur_sc), "quick_ratio": _clamp(quick_sc), "cash_buffer": _clamp(cash_sc)}


def _solvency_sc(metrics: dict) -> dict[str, float]:
    d_e = metrics.get("debt_equity")
    d_e_sc = 0.0
    if d_e is not None and d_e >= 0:
        d_e_sc = _inv_band(d_e, 0.8, 1.5)
    debt = metrics.get("total_debt")
    cash = metrics.get("total_cash")
    net = (cash or 0) - (debt or 0)
    net_sc = _band(net / (metrics.get("market_cap") or (cash if cash else 1)) or 0, 0.0, 0.25) if (debt is not None or cash is not None) else 0.0
    return {"debt_equity": _clamp(d_e_sc), "net_cash_position": _clamp(net_sc)}


def _growth_sc(metrics: dict) -> dict[str, float]:
    return {
        "revenue_growth": _band(metrics.get("revenue_growth") or metrics.get("revenue_q_growth"), 0.12, 0.25),
        "earnings_growth": _band(metrics.get("earnings_growth") or metrics.get("earnings_q_growth"), 0.15, 0.30),
    }


def _cashflow_sc(metrics: dict) -> dict[str, float]:
    mcap = metrics.get("market_cap")
    fcf = metrics.get("free_cashflow")
    if fcf is not None and mcap:
        return {"fcf_yield": _band(fcf / mcap, 0.05, 0.10)}
    return {"fcf_yield": 0.0}


def health_components(metrics: dict) -> dict[str, float]:
    comp = {}
    comp.update(_proft_sc(metrics))
    comp.update(_liquidity_sc(metrics))
    comp.update(_solvency_sc(metrics))
    comp.update(_growth_sc(metrics))
    comp.update(_cashflow_sc(metrics))
    return comp


def health_score(metrics: dict) -> float:
    comp = health_components(metrics)
    if not comp:
        return 0.0
    weights = {
        # profitability
        "roe": 1.5,
        "roa": 1.2,
        "net_margin": 1.5,
        "gross_margin": 1.0,
        "operating_margin": 1.1,
        # liquidity
        "current_ratio": 0.9,
        "quick_ratio": 0.7,
        "cash_buffer": 0.6,
        # solvency
        "debt_equity": 1.4,
        "net_cash_position": 1.0,
        # growth
        "revenue_growth": 1.2,
        "earnings_growth": 1.4,
        # cash flow
        "fcf_yield": 1.3,
    }
    num = sum(comp.get(k, 0.0) * w for k, w in weights.items())
    den = sum(weights.values())
    return _clamp(num / den)


# ------------------------------------------------------------- valuation
def valuation_components(metrics: dict) -> dict[str, float]:
    comp = {}
    pe = metrics.get("pe_trailing")
    if pe is not None and pe > 0:
        comp["pe"] = _inv_band(pe, 14.0, 12.0)
    fpe = metrics.get("pe_forward")
    if fpe is not None and fpe > 0:
        comp["pe_forward"] = _inv_band(fpe, 12.0, 10.0)
    pb = metrics.get("pb")
    if pb is not None and pb > 0:
        comp["pb"] = _inv_band(pb, 1.6, 1.8)
    ps = metrics.get("ps_trailing")
    if ps is not None and ps > 0:
        comp["ps"] = _inv_band(ps, 2.0, 3.0)
    ev_ebitda = metrics.get("ev_ebitda")
    if ev_ebitda is not None and ev_ebitda > 0:
        comp["ev_ebitda"] = _inv_band(ev_ebitda, 9.0, 8.0)
    dy = metrics.get("dividend_yield")
    if dy is not None:
        comp["dividend_yield"] = _band(dy, 0.04, 0.03)
    return comp


def valuation_score(metrics: dict) -> float:
    comp = valuation_components(metrics)
    if not comp:
        return 0.0
    return _clamp(sum(comp.values()) / len(comp))


# ------------------------------------------------------------ composite
def compute_fundamentals(fd: FundamentalData) -> FundamentalData:
    """Fill in the health / valuation / composite scores on the record."""
    m = fd.metrics
    fd.health_score = round(health_score(m), 1)
    fd.valuation_score = round(valuation_score(m), 1)
    fd.fundamental_score = round(0.62 * fd.health_score + 0.38 * fd.valuation_score, 1)
    fd.details = {
        "health_components": {k: round(v, 1) for k, v in health_components(m).items()},
        "valuation_components": {k: round(v, 1) for k, v in valuation_components(m).items()},
        "metrics": {k: round(v, 4) for k, v in m.items() if isinstance(v, (int, float))},
    }
    return fd