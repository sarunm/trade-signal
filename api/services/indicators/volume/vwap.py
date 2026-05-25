from services.indicators.common import VOLUME_SPECS, register_indicator

compute_vwap = register_indicator(VOLUME_SPECS["vwap"])
