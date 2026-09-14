import math

import pytest

from strategy_lab.core.costs import (
    CostModelError,
    ExecutionCostAssumptions,
    apply_round_trip_costs,
)
from strategy_lab.core.trade_plan import TradeSide


def _zero_costs() -> ExecutionCostAssumptions:
    return ExecutionCostAssumptions(
        profile_id="zero-cost-baseline",
        version="v1",
        source="research_baseline",
    )


def test_zero_cost_buy_matches_reference_pnl() -> None:
    result = apply_round_trip_costs(
        side=TradeSide.BUY,
        reference_entry=100.0,
        reference_exit=110.0,
        assumptions=_zero_costs(),
    )

    assert result.executed_entry == 100.0
    assert result.executed_exit == 110.0
    assert result.gross_pnl_per_unit == 10.0
    assert result.total_cost_per_unit == 0.0
    assert result.net_pnl_per_unit == 10.0


def test_zero_cost_sell_matches_reference_pnl() -> None:
    result = apply_round_trip_costs(
        side=TradeSide.SELL,
        reference_entry=100.0,
        reference_exit=90.0,
        assumptions=_zero_costs(),
    )

    assert result.gross_pnl_per_unit == 10.0
    assert result.net_pnl_per_unit == 10.0


def test_buy_costs_are_adverse_on_both_sides() -> None:
    costs = ExecutionCostAssumptions(
        profile_id="example",
        version="v1",
        source="test_fixture",
        spread_bps=10.0,
        entry_slippage_bps=5.0,
        exit_slippage_bps=5.0,
        commission_bps_per_side=2.0,
    )
    result = apply_round_trip_costs(
        side=TradeSide.BUY,
        reference_entry=100.0,
        reference_exit=110.0,
        assumptions=costs,
    )

    assert result.executed_entry > 100.0
    assert result.executed_exit < 110.0
    assert result.total_cost_per_unit > 0.0
    assert result.net_pnl_per_unit < result.gross_pnl_per_unit
    assert result.cost_profile == "example@v1"


def test_sell_costs_are_adverse_on_both_sides() -> None:
    costs = ExecutionCostAssumptions(
        profile_id="example",
        version="v1",
        source="test_fixture",
        spread_bps=10.0,
        entry_slippage_bps=5.0,
        exit_slippage_bps=5.0,
        commission_bps_per_side=2.0,
    )
    result = apply_round_trip_costs(
        side=TradeSide.SELL,
        reference_entry=100.0,
        reference_exit=90.0,
        assumptions=costs,
    )

    assert result.executed_entry < 100.0
    assert result.executed_exit > 90.0
    assert result.total_cost_per_unit > 0.0
    assert result.net_pnl_per_unit < result.gross_pnl_per_unit


def test_commission_is_explicit_in_cost_breakdown() -> None:
    costs = ExecutionCostAssumptions(
        profile_id="commission-only",
        version="v1",
        source="test_fixture",
        commission_bps_per_side=10.0,
    )
    result = apply_round_trip_costs(
        side=TradeSide.BUY,
        reference_entry=100.0,
        reference_exit=110.0,
        assumptions=costs,
    )

    assert result.execution_price_cost_per_unit == 0.0
    assert result.commission_cost_per_unit == pytest.approx(0.21)
    assert result.total_cost_per_unit == pytest.approx(0.21)
    assert result.net_pnl_per_unit == pytest.approx(9.79)


def test_costs_can_turn_small_gross_profit_negative() -> None:
    costs = ExecutionCostAssumptions(
        profile_id="high-cost-fixture",
        version="v1",
        source="test_fixture",
        spread_bps=20.0,
        entry_slippage_bps=10.0,
        exit_slippage_bps=10.0,
        commission_bps_per_side=10.0,
    )
    result = apply_round_trip_costs(
        side=TradeSide.BUY,
        reference_entry=100.0,
        reference_exit=100.1,
        assumptions=costs,
    )

    assert result.gross_pnl_per_unit > 0.0
    assert result.net_pnl_per_unit < 0.0


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("spread_bps", -1.0),
        ("entry_slippage_bps", -1.0),
        ("exit_slippage_bps", -1.0),
        ("commission_bps_per_side", -1.0),
        ("spread_bps", math.inf),
    ],
)
def test_invalid_cost_assumptions_are_rejected(field_name: str, value: float) -> None:
    kwargs = {field_name: value}

    with pytest.raises(CostModelError):
        ExecutionCostAssumptions(
            profile_id="bad",
            version="v1",
            source="test_fixture",
            **kwargs,
        )


def test_invalid_reference_price_is_rejected() -> None:
    with pytest.raises(CostModelError, match="reference_entry"):
        apply_round_trip_costs(
            side=TradeSide.BUY,
            reference_entry=0.0,
            reference_exit=100.0,
            assumptions=_zero_costs(),
        )
