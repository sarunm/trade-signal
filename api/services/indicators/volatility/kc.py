from services.indicators.common import VOLATILITY_SPECS, register_indicator

compute_kc = register_indicator(VOLATILITY_SPECS["kc"])
