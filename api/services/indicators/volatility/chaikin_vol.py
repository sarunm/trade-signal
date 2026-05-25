from services.indicators.common import VOLATILITY_SPECS, register_indicator

compute_chaikin_vol = register_indicator(VOLATILITY_SPECS["chaikin_vol"])
