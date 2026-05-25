from services.indicators.common import VOLUME_SPECS, register_indicator

compute_eom = register_indicator(VOLUME_SPECS["eom"])
