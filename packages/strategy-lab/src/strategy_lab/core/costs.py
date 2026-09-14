"""Deterministic round-trip execution-cost model for strategy research.

No broker values are embedded here. Every backtest/replay experiment must supply
and version its own spread, slippage, and commission assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .trade_plan import TradeSide

BPS_DENOMINATOR = 10_000.0


class CostModelError(ValueError):
    """Raised when execution-cost inputs are malformed."""


@dataclass(frozen=True, slots=True)
class ExecutionCostAssumptions:
    """Versioned broker/instrument cost assumptions expressed in basis points."""

    profile_id: str
    version: str
    source: str
    spread_bps: float = 0.0
    entry_slippage_bps: float = 0.0
    exit_slippage_bps: float = 0.0
    commission_bps_per_side: float = 0.0

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise CostModelError("cost profile_id must be recorded")
        if not self.version.strip():
            raise CostModelError("cost profile version must be recorded")
        if not self.source.strip():
            raise CostModelError("cost assumption source must be recorded")

        values = {
            "spread_bps": self.spread_bps,
            "entry_slippage_bps": self.entry_slippage_bps,
            "exit_slippage_bps": self.exit_slippage_bps,
            "commission_bps_per_side": self.commission_bps_per_side,
        }
        for field_name, value in values.items():
            if not isfinite(value):
                raise CostModelError(f"{field_name} must be finite")
            if value < 0:
                raise CostModelError(f"{field_name} cannot be negative")

    @property
    def identity(self) -> str:
        return f"{self.profile_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class RoundTripExecution:
    """Reference-vs-executed round trip and per-unit P/L breakdown."""

    side: TradeSide
    reference_entry: float
    reference_exit: float
    executed_entry: float
    executed_exit: float
    gross_pnl_per_unit: float
    execution_price_cost_per_unit: float
    commission_cost_per_unit: float
    total_cost_per_unit: float
    net_pnl_per_unit: float
    cost_profile: str


def _validate_price(value: float, *, field_name: str) -> None:
    if not isfinite(value) or value <= 0:
        raise CostModelError(f"{field_name} must be finite and greater than zero")


def apply_round_trip_costs(
    *,
    side: TradeSide,
    reference_entry: float,
    reference_exit: float,
    assumptions: ExecutionCostAssumptions,
) -> RoundTripExecution:
    """Apply adverse spread/slippage plus per-side commission to one round trip.

    `spread_bps` is the full bid/ask spread, so half is paid at each execution.
    Slippage is adverse to the trade at both entry and exit.
    """

    _validate_price(reference_entry, field_name="reference_entry")
    _validate_price(reference_exit, field_name="reference_exit")

    half_spread_fraction = assumptions.spread_bps / (2.0 * BPS_DENOMINATOR)
    entry_slippage_fraction = assumptions.entry_slippage_bps / BPS_DENOMINATOR
    exit_slippage_fraction = assumptions.exit_slippage_bps / BPS_DENOMINATOR
    commission_fraction = assumptions.commission_bps_per_side / BPS_DENOMINATOR

    entry_half_spread = reference_entry * half_spread_fraction
    exit_half_spread = reference_exit * half_spread_fraction
    entry_slippage = reference_entry * entry_slippage_fraction
    exit_slippage = reference_exit * exit_slippage_fraction

    if side is TradeSide.BUY:
        executed_entry = reference_entry + entry_half_spread + entry_slippage
        executed_exit = reference_exit - exit_half_spread - exit_slippage
        gross_pnl = reference_exit - reference_entry
        execution_pnl = executed_exit - executed_entry
    else:
        executed_entry = reference_entry - entry_half_spread - entry_slippage
        executed_exit = reference_exit + exit_half_spread + exit_slippage
        gross_pnl = reference_entry - reference_exit
        execution_pnl = executed_entry - executed_exit

    commission_cost = (
        executed_entry * commission_fraction + executed_exit * commission_fraction
    )
    net_pnl = execution_pnl - commission_cost
    execution_price_cost = gross_pnl - execution_pnl
    total_cost = execution_price_cost + commission_cost

    return RoundTripExecution(
        side=side,
        reference_entry=reference_entry,
        reference_exit=reference_exit,
        executed_entry=executed_entry,
        executed_exit=executed_exit,
        gross_pnl_per_unit=gross_pnl,
        execution_price_cost_per_unit=execution_price_cost,
        commission_cost_per_unit=commission_cost,
        total_cost_per_unit=total_cost,
        net_pnl_per_unit=net_pnl,
        cost_profile=assumptions.identity,
    )
