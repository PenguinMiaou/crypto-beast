"""AltcoinRadar: Coin selection and BTC-altcoin correlation tracking."""

from typing import List, Dict, Optional


class AltcoinRadar:
    """Coin selection and BTC-altcoin correlation tracking."""

    DEFAULT_WATCHLIST = [
        "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
        "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "MATICUSDT",
    ]

    def __init__(self, max_alts: int = 3) -> None:
        self.max_alts = max_alts
        self._scores: Dict[str, float] = {}

    def score_coin(
        self,
        symbol: str,
        volume_24h: float,
        price_change_24h: float,
        btc_correlation: float = 0.5,
    ) -> float:
        """Score a coin based on volume, momentum, and BTC correlation.

        Higher volume + moderate correlation + positive momentum = better.
        Low correlation is good for diversification.
        """
        vol_score = min(1.0, volume_24h / 1_000_000_000)  # Normalize by $1B
        momentum_score = max(-1.0, min(1.0, price_change_24h / 10))  # Normalize by 10%
        # Lower correlation = better diversification (inverted)
        corr_score = 1.0 - abs(btc_correlation)

        score = vol_score * 0.4 + abs(momentum_score) * 0.3 + corr_score * 0.3
        self._scores[symbol] = round(score, 4)
        return self._scores[symbol]

    def get_top_alts(self) -> List[str]:
        """Return top N altcoins by score."""
        sorted_coins = sorted(
            self._scores.items(), key=lambda x: x[1], reverse=True
        )
        return [coin for coin, _ in sorted_coins[: self.max_alts]]

    def get_scores(self) -> Dict[str, float]:
        return self._scores.copy()
