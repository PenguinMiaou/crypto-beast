"""Tests for AntiTrap false signal filtering."""

import pandas as pd
import pytest
from datetime import datetime

from core.models import TradeSignal, Direction, MarketRegime
from defense.anti_trap import AntiTrap


def _make_signal(direction: Direction = Direction.LONG, confidence: float = 0.7) -> TradeSignal:
    return TradeSignal(
        symbol="BTCUSDT",
        direction=direction,
        confidence=confidence,
        entry_price=50000.0,
        stop_loss=49000.0,
        take_profit=52000.0,
        strategy="test",
        regime=MarketRegime.TRENDING_UP,
        timeframe_score=5,
    )


def _make_klines(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class TestPinBarDetection:
    def test_long_upper_wick_traps_long(self):
        """Long upper wick on last candle -> trap for LONG signal."""
        trap = AntiTrap(pin_bar_ratio=2.5)
        klines = _make_klines([
            {"open": 100, "high": 105, "low": 99, "close": 101, "volume": 1000},
            {"open": 101, "high": 106, "low": 100, "close": 102, "volume": 1000},
            # Last candle: body=1, upper_wick=10 -> ratio=10 > 2.5
            {"open": 100, "high": 111, "low": 99, "close": 101, "volume": 1000},
        ])
        signal = _make_signal(Direction.LONG)
        assert trap.is_trap(signal, klines) is True

    def test_long_lower_wick_traps_short(self):
        """Long lower wick on last candle -> trap for SHORT signal."""
        trap = AntiTrap(pin_bar_ratio=2.5)
        klines = _make_klines([
            {"open": 100, "high": 105, "low": 99, "close": 101, "volume": 1000},
            {"open": 101, "high": 106, "low": 100, "close": 102, "volume": 1000},
            # Last candle: body=1, lower_wick=10 -> ratio=10 > 2.5
            {"open": 100, "high": 101, "low": 89, "close": 99, "volume": 1000},
        ])
        signal = _make_signal(Direction.SHORT)
        assert trap.is_trap(signal, klines) is True

    def test_no_pin_bar_normal(self):
        """Normal candle with small wicks -> no trap."""
        trap = AntiTrap(pin_bar_ratio=2.5)
        klines = _make_klines([
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
            {"open": 101, "high": 103, "low": 100, "close": 102, "volume": 1000},
            # Normal: body=2, upper_wick=1 -> ratio=0.5 < 2.5
            {"open": 100, "high": 103, "low": 99, "close": 102, "volume": 1000},
        ])
        signal = _make_signal(Direction.LONG)
        assert trap.is_trap(signal, klines) is False


class TestVolumeDivergence:
    def test_price_up_volume_declining_traps_long(self):
        """Price rising but volume declining -> trap for LONG."""
        trap = AntiTrap()
        klines = _make_klines([
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 3000},
            {"open": 101, "high": 103, "low": 100, "close": 102, "volume": 2000},
            {"open": 102, "high": 104, "low": 101, "close": 103, "volume": 1000},
        ])
        signal = _make_signal(Direction.LONG)
        assert trap.is_trap(signal, klines) is True

    def test_price_down_volume_declining_traps_short(self):
        """Price falling but volume declining -> trap for SHORT."""
        trap = AntiTrap()
        klines = _make_klines([
            {"open": 103, "high": 104, "low": 102, "close": 102, "volume": 3000},
            {"open": 102, "high": 103, "low": 101, "close": 101, "volume": 2000},
            {"open": 101, "high": 102, "low": 100, "close": 100, "volume": 1000},
        ])
        signal = _make_signal(Direction.SHORT)
        assert trap.is_trap(signal, klines) is True


class TestPumpDetection:
    def test_large_candle_detected_as_pump(self):
        """Candle with >3% change -> pump detected."""
        trap = AntiTrap(pump_threshold=0.03)
        klines = _make_klines([
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
            {"open": 101, "high": 103, "low": 100, "close": 102, "volume": 1000},
            # 4% move
            {"open": 100, "high": 105, "low": 99, "close": 104, "volume": 1000},
        ])
        signal = _make_signal(Direction.LONG)
        assert trap.is_trap(signal, klines) is True

    def test_normal_candle_not_pump(self):
        """Candle with <3% change -> no pump."""
        trap = AntiTrap(pump_threshold=0.03)
        klines = _make_klines([
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
            {"open": 101, "high": 103, "low": 100, "close": 102, "volume": 1000},
            # 1% move
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        ])
        signal = _make_signal(Direction.LONG)
        assert trap.is_trap(signal, klines) is False


class TestNormalSignal:
    def test_clean_signal_passes(self):
        """Normal candles with healthy volume -> no trap."""
        trap = AntiTrap()
        klines = _make_klines([
            {"open": 100, "high": 101.5, "low": 99.5, "close": 101, "volume": 1000},
            {"open": 101, "high": 102.5, "low": 100.5, "close": 102, "volume": 1100},
            {"open": 102, "high": 103.5, "low": 101.5, "close": 103, "volume": 1200},
        ])
        signal = _make_signal(Direction.LONG)
        assert trap.is_trap(signal, klines) is False

    def test_insufficient_data_passes(self):
        """Less than 3 candles -> not enough data, pass through."""
        trap = AntiTrap()
        klines = _make_klines([
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        ])
        signal = _make_signal(Direction.LONG)
        assert trap.is_trap(signal, klines) is False
