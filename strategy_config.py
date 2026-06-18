from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_BRAIN_PATH = PROJECT_DIR / "config.txt"


@dataclass(frozen=True)
class BrainRuleConfig:
    use_local_brain_rules: bool
    top_n_values: tuple[int, ...]
    max_price: float
    min_avg_volume_5d: float
    price_breakout_days: int
    revenue_ma_months: int
    revenue_ma_high_months: int
    broker_net_days: int
    broker_lag_days: int
    broker_score_weight: float
    min_institutional_net_buy_values: tuple[float | None, ...]
    require_foreign_net_buy_values: tuple[bool, ...]
    require_investment_trust_net_buy_values: tuple[bool, ...]
    daytrade_lag_days: int
    daytrade_rank_discount: float
    eps_quality_clip_low: float
    eps_quality_clip_high: float
    stop_loss: float
    take_profit: float


def load_brain_rule_config() -> BrainRuleConfig:
    # The local brain file is intentionally ignored by git. Its presence enables
    # the private rule set without leaking the source text into the repository.
    use_local = LOCAL_BRAIN_PATH.exists()
    return BrainRuleConfig(
        use_local_brain_rules=use_local,
        top_n_values=(10,) if use_local else (5, 10),
        max_price=200.0,
        min_avg_volume_5d=50_000.0,
        price_breakout_days=120,
        revenue_ma_months=2,
        revenue_ma_high_months=12,
        broker_net_days=10,
        broker_lag_days=1,
        broker_score_weight=1.0,
        min_institutional_net_buy_values=(None, 0.0, 100_000.0, 500_000.0),
        require_foreign_net_buy_values=(False, True),
        require_investment_trust_net_buy_values=(False, True),
        daytrade_lag_days=1,
        daytrade_rank_discount=0.4,
        eps_quality_clip_low=-0.5,
        eps_quality_clip_high=2.0,
        stop_loss=0.2,
        take_profit=0.8,
    )
