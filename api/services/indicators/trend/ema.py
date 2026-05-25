from services.indicators.common import TREND_SPECS, register_indicator

compute_ema = register_indicator(TREND_SPECS["ema"])
