from services.indicators.common import PATTERN_SPECS, register_indicator

compute_candle_pattern = register_indicator(PATTERN_SPECS["candle_pattern"])
