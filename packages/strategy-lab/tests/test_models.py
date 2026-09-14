import pytest

from strategy_lab.core.models import AcdLevels, RiskReward


def test_valid_acd_level_order_is_accepted() -> None:
    levels = AcdLevels(
        c_up=106.0,
        a_up=104.0,
        or_up=102.0,
        or_down=100.0,
        a_down=98.0,
        c_down=96.0,
        source="external-indicator:v0.1",
    )

    assert levels.a_down == 98.0


def test_invalid_acd_level_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="ACD levels must satisfy"):
        AcdLevels(
            c_up=106.0,
            a_up=104.0,
            or_up=102.0,
            or_down=100.0,
            a_down=101.0,
            c_down=96.0,
            source="external-indicator:v0.1",
        )


def test_acd_level_source_is_required() -> None:
    with pytest.raises(ValueError, match="source"):
        AcdLevels(
            c_up=106.0,
            a_up=104.0,
            or_up=102.0,
            or_down=100.0,
            a_down=98.0,
            c_down=96.0,
            source="   ",
        )


def test_risk_reward_minimum_is_one_to_two() -> None:
    below = RiskReward(risk=10.0, reward=19.99)
    minimum = RiskReward(risk=10.0, reward=20.0)
    above = RiskReward(risk=10.0, reward=25.0)

    assert not below.meets_acd_v01_minimum
    assert minimum.meets_acd_v01_minimum
    assert above.meets_acd_v01_minimum
    assert minimum.ratio == 2.0
