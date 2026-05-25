from services.indicators.common import VOLUME_SPECS, register_indicator

compute_volume_raw = register_indicator(VOLUME_SPECS["volume_raw"])
