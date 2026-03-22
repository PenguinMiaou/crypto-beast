"""AltcoinRadar: Coin selection with liquidity and maturity filters."""

from typing import List, Dict, Optional

from loguru import logger


class AltcoinRadar:
    """Select altcoins for trading based on volume, momentum, and maturity.

    Filters:
    - Min 24h volume > $100M (liquidity)
    - Min 30 days of trading history (excludes new/manipulated coins)
    - Score by volume (40%) + momentum (30%) + BTC decorrelation (30%)
    """

    MIN_VOLUME_24H = 100_000_000  # $100M minimum
    MIN_KLINE_COUNT = 8640  # 30 days of 5m bars (288/day × 30)

    BASE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def __init__(self, max_alts: int = 3) -> None:
        self.max_alts = max_alts
        self._scores: Dict[str, float] = {}
        self._filtered_out: Dict[str, str] = {}  # symbol -> reason

    def score_coin(
        self,
        symbol: str,
        volume_24h: float,
        price_change_24h: float,
        btc_correlation: float = 0.5,
        kline_count: int = 0,
    ) -> Optional[float]:
        """Score a coin. Returns None if filtered out.

        Args:
            symbol: e.g. "BNBUSDT"
            volume_24h: 24h quote volume in USD
            price_change_24h: 24h price change percentage
            btc_correlation: correlation with BTC (0-1)
            kline_count: number of available 5m klines (for maturity check).
                         0 (default) means not provided — maturity check is skipped.
        """
        # Filter: minimum volume
        if volume_24h < self.MIN_VOLUME_24H:
            self._filtered_out[symbol] = f"low_volume ({volume_24h/1e6:.0f}M < 100M)"
            return None

        # Filter: new coin (not enough history) — only when kline_count was explicitly provided
        if 0 < kline_count < self.MIN_KLINE_COUNT:
            self._filtered_out[symbol] = f"new_coin ({kline_count} bars < {self.MIN_KLINE_COUNT})"
            return None

        # Score: volume (40%) + momentum (30%) + decorrelation (30%)
        vol_score = min(1.0, volume_24h / 1_000_000_000)  # Normalize by $1B
        momentum_score = max(-1.0, min(1.0, price_change_24h / 10))  # Normalize by 10%
        corr_score = 1.0 - abs(btc_correlation)

        score = vol_score * 0.4 + abs(momentum_score) * 0.3 + corr_score * 0.3
        self._scores[symbol] = round(score, 4)
        return self._scores[symbol]

    def get_top_alts(self) -> List[str]:
        """Return top N altcoins by score (excluding base symbols)."""
        filtered = {k: v for k, v in self._scores.items() if k not in self.BASE_SYMBOLS}
        sorted_coins = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
        return [coin for coin, _ in sorted_coins[:self.max_alts]]

    def get_scores(self) -> Dict[str, float]:
        return self._scores.copy()

    def get_filtered_out(self) -> Dict[str, str]:
        return self._filtered_out.copy()
