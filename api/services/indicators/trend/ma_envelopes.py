from services.indicators.common import TREND_SPECS, register_indicator

compute_ma_envelopes = register_indicator(TREND_SPECS["ma_envelopes"])
