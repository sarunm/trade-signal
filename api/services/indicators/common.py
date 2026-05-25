import math
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence, Tuple

import pandas as pd

from models.price_bar import PriceBar
from models.trade import Trade
from services.indicator_engine import IndicatorResult, matches_trade, register

VALID_DIRECTIONS = {"bullish", "bearish", "neutral"}


@dataclass(frozen=True)
class IndicatorSpec:
    slug: str
    group: str
    compute: Callable[[pd.DataFrame], Tuple[Optional[float], str, dict]]


def register_indicator(spec: IndicatorSpec):
    @register(spec.slug)
    def compute_indicator(
        trade: Trade,
        bars_by_tf: Mapping[str, Sequence[PriceBar]],
    ) -> IndicatorResult:
        timeframe, bars = _select_bars(bars_by_tf)
        if not bars:
            return _result(spec.slug, None, "neutral", trade, timeframe, {"reason": "no_bars"})

        df = _to_frame(bars)
        value, direction, metadata = spec.compute(df)
        if direction not in VALID_DIRECTIONS:
            direction = "neutral"
        metadata = {"group": spec.group, **metadata}
        return _result(spec.slug, value, direction, trade, timeframe, metadata)

    compute_indicator.__name__ = f"compute_{spec.slug}"
    return compute_indicator


def _result(slug: str, value: Optional[float], direction: str, trade: Trade, timeframe: str, metadata: dict):
    return IndicatorResult(
        slug=slug,
        value=_clean(value),
        direction=direction,
        matched=matches_trade(direction, trade.direction),
        timeframe=timeframe,
        metadata=metadata,
    )


def _select_bars(bars_by_tf: Mapping[str, Sequence[PriceBar]]) -> tuple[str, Sequence[PriceBar]]:
    if "H1" in bars_by_tf:
        return "H1", bars_by_tf["H1"]
    for timeframe, bars in bars_by_tf.items():
        return timeframe, bars
    return "H1", []


def _to_frame(bars: Sequence[PriceBar]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [float(bar.open) for bar in bars],
            "high": [float(bar.high) for bar in bars],
            "low": [float(bar.low) for bar in bars],
            "close": [float(bar.close) for bar in bars],
            "volume": [float(bar.volume or 0) for bar in bars],
            "time": [bar.time for bar in bars],
        }
    )


def _clean(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return float(value)


def _last(series: pd.Series, default: Optional[float] = None) -> Optional[float]:
    valid = series.dropna()
    if valid.empty:
        return default
    return _clean(float(valid.iloc[-1]))


def _prev(series: pd.Series, default: Optional[float] = None) -> Optional[float]:
    valid = series.dropna()
    if len(valid) < 2:
        return default
    return _clean(float(valid.iloc[-2]))


def _direction(value: Optional[float], bullish: Callable[[float], bool], bearish: Callable[[float], bool]) -> str:
    if value is None:
        return "neutral"
    if bullish(value):
        return "bullish"
    if bearish(value):
        return "bearish"
    return "neutral"


def _above_below(value: Optional[float], reference: Optional[float]) -> str:
    if value is None or reference is None:
        return "neutral"
    if value > reference:
        return "bullish"
    if value < reference:
        return "bearish"
    return "neutral"


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length, min_periods=length).mean()


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def _wma(series: pd.Series, length: int) -> pd.Series:
    weights = pd.Series(range(1, length + 1), dtype="float64")
    return series.rolling(length, min_periods=length).apply(
        lambda values: float((pd.Series(values) * weights).sum() / weights.sum()),
        raw=False,
    )


def _smma(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def _roc(series: pd.Series, length: int) -> pd.Series:
    shifted = series.shift(length)
    return (series - shifted) / shifted.replace(0, math.nan) * 100


def _mom(series: pd.Series, length: int) -> pd.Series:
    return series - series.shift(length)


def _tr(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def _atr(df: pd.DataFrame, length: int) -> pd.Series:
    return _tr(df).rolling(length, min_periods=length).mean()


def _rsi(series: pd.Series, length: int = 14, drift: int = 1) -> pd.Series:
    delta = series.diff(drift)
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(length, min_periods=length).mean()
    avg_loss = loss.rolling(length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, math.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100).where(avg_loss != 0, 100).where(avg_gain != 0, 0)


def _stoch(df: pd.DataFrame, length: int = 14) -> pd.Series:
    lowest = df["low"].rolling(length, min_periods=length).min()
    highest = df["high"].rolling(length, min_periods=length).max()
    return (df["close"] - lowest) / (highest - lowest).replace(0, math.nan) * 100


def _linreg_slope(series: pd.Series, length: int = 14) -> pd.Series:
    def slope(values):
        n = len(values)
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = sum(values) / n
        denom = sum((x - x_mean) ** 2 for x in xs)
        if denom == 0:
            return 0.0
        return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values)) / denom

    return series.rolling(length, min_periods=length).apply(slope, raw=True)


def _zlema(series: pd.Series, length: int) -> pd.Series:
    lag = max(math.floor((length - 1) / 2), 1)
    adjusted = series + (series - series.shift(lag))
    return _ema(adjusted, length)


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd = _ema(series, fast) - _ema(series, slow)
    signal_line = _ema(macd, signal)
    hist = macd - signal_line
    return macd, signal_line, hist


def _ao(df: pd.DataFrame) -> pd.Series:
    midpoint = (df["high"] + df["low"]) / 2
    return _sma(midpoint, 5) - _sma(midpoint, 34)


def _crossed_above(series: pd.Series, level: float, lookback: int = 3) -> bool:
    recent = series.dropna().tail(max(lookback + 1, 2))
    if len(recent) < 2:
        return False
    return any(recent.iloc[i - 1] <= level < recent.iloc[i] for i in range(1, len(recent)))


def _crossed_below(series: pd.Series, level: float, lookback: int = 3) -> bool:
    recent = series.dropna().tail(max(lookback + 1, 2))
    if len(recent) < 2:
        return False
    return any(recent.iloc[i - 1] >= level > recent.iloc[i] for i in range(1, len(recent)))


def _price_swing_direction(df: pd.DataFrame) -> str:
    slope = _last(_linreg_slope(df["close"], min(14, len(df))))
    return _direction(slope, lambda v: v > 0, lambda v: v < 0)


def _ma_result(df: pd.DataFrame, series: pd.Series, name: str):
    close = _last(df["close"])
    value = _last(series)
    return value, _above_below(close, value), {name: value, "close": close}


def _dema(series: pd.Series, length: int) -> pd.Series:
    ema1 = _ema(series, length)
    ema2 = _ema(ema1, length)
    return 2 * ema1 - ema2


def _tema(series: pd.Series, length: int) -> pd.Series:
    ema1 = _ema(series, length)
    ema2 = _ema(ema1, length)
    ema3 = _ema(ema2, length)
    return 3 * ema1 - 3 * ema2 + ema3


def _hma(series: pd.Series, length: int) -> pd.Series:
    half = max(int(length / 2), 1)
    root = max(int(math.sqrt(length)), 1)
    return _wma(2 * _wma(series, half) - _wma(series, length), root)


def _kama(series: pd.Series, length: int = 10, fast: int = 2, slow: int = 30) -> pd.Series:
    change = (series - series.shift(length)).abs()
    volatility = series.diff().abs().rolling(length, min_periods=length).sum()
    er = change / volatility.replace(0, math.nan)
    fast_sc = 2 / (fast + 1)
    slow_sc = 2 / (slow + 1)
    sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
    values = [float(series.iloc[0])]
    for i in range(1, len(series)):
        prev = values[-1]
        alpha = sc.iloc[i]
        if pd.isna(alpha):
            values.append(prev)
        else:
            values.append(prev + float(alpha) * (float(series.iloc[i]) - prev))
    return pd.Series(values, index=series.index)


def _mcgd(series: pd.Series, length: int = 14) -> pd.Series:
    values = [float(series.iloc[0])]
    for price in series.iloc[1:]:
        prev = values[-1]
        ratio = float(price) / prev if prev else 1.0
        values.append(prev + (float(price) - prev) / (length * (ratio ** 4)))
    return pd.Series(values, index=series.index)


def _t3(series: pd.Series, length: int = 5, a: float = 0.7) -> pd.Series:
    e1 = _ema(series, length)
    e2 = _ema(e1, length)
    e3 = _ema(e2, length)
    e4 = _ema(e3, length)
    e5 = _ema(e4, length)
    e6 = _ema(e5, length)
    c1 = -(a ** 3)
    c2 = 3 * (a ** 2) + 3 * (a ** 3)
    c3 = -6 * (a ** 2) - 3 * a - 3 * (a ** 3)
    c4 = 1 + 3 * a + a ** 3 + 3 * (a ** 2)
    return c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3


def _aroon(df: pd.DataFrame, length: int = 25):
    highs = df["high"].tail(length)
    lows = df["low"].tail(length)
    if len(highs) < length:
        return None, None
    periods_since_high = length - 1 - int(highs.reset_index(drop=True).idxmax())
    periods_since_low = length - 1 - int(lows.reset_index(drop=True).idxmin())
    up = ((length - periods_since_high) / length) * 100
    down = ((length - periods_since_low) / length) * 100
    return up, down


def _vortex(df: pd.DataFrame, length: int = 14):
    tr_sum = _tr(df).rolling(length, min_periods=length).sum()
    plus = (df["high"] - df["low"].shift(1)).abs().rolling(length, min_periods=length).sum() / tr_sum
    minus = (df["low"] - df["high"].shift(1)).abs().rolling(length, min_periods=length).sum() / tr_sum
    return plus, minus


def _alligator_lines(df: pd.DataFrame):
    median = (df["high"] + df["low"]) / 2
    jaw = _smma(median, 13)
    teeth = _smma(median, 8)
    lips = _smma(median, 5)
    return jaw, teeth, lips


def _trend_sma(df): return _ma_result(df, _sma(df["close"], 20), "sma")
def _trend_ema(df): return _ma_result(df, _ema(df["close"], 20), "ema")
def _trend_dema(df): return _ma_result(df, _dema(df["close"], 20), "dema")
def _trend_tema(df): return _ma_result(df, _tema(df["close"], 20), "tema")
def _trend_wma(df): return _ma_result(df, _wma(df["close"], 20), "wma")
def _trend_hma(df): return _ma_result(df, _hma(df["close"], 20), "hma")
def _trend_kama(df): return _ma_result(df, _kama(df["close"]), "kama")
def _trend_mcgd(df): return _ma_result(df, _mcgd(df["close"]), "mcgd")
def _trend_t3(df): return _ma_result(df, _t3(df["close"]), "t3")
def _trend_zlma(df): return _ma_result(df, _zlema(df["close"], 20), "zlma")


def _trend_macd(df):
    macd, signal, hist = _macd(df["close"])
    value = _last(hist)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {
        "macd": _last(macd),
        "signal": _last(signal),
        "histogram": value,
    }


def _trend_psar(df):
    trend = _price_swing_direction(df)
    value = _last(df["low"].rolling(3).min() if trend == "bullish" else df["high"].rolling(3).max())
    return value, trend, {"proxy": "rolling_extreme"}


def _trend_adx(df):
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
    atr = _atr(df, 14)
    dmp = 100 * plus_dm.rolling(14, min_periods=14).sum() / atr.replace(0, math.nan)
    dmn = 100 * minus_dm.rolling(14, min_periods=14).sum() / atr.replace(0, math.nan)
    dx = ((dmp - dmn).abs() / (dmp + dmn).replace(0, math.nan)) * 100
    adx = dx.rolling(14, min_periods=14).mean()
    value = _last(adx)
    dmp_last = _last(dmp)
    dmn_last = _last(dmn)
    direction = "neutral"
    if value is not None and value > 25:
        direction = _above_below(dmp_last, dmn_last)
    return value, direction, {"dmp": dmp_last, "dmn": dmn_last}


def _trend_ichimoku(df):
    tenkan = (df["high"].rolling(9).max() + df["low"].rolling(9).min()) / 2
    kijun = (df["high"].rolling(26).max() + df["low"].rolling(26).min()) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (df["high"].rolling(52).max() + df["low"].rolling(52).min()) / 2
    close = _last(df["close"])
    a = _last(senkou_a)
    b = _last(senkou_b)
    tenkan_last = _last(tenkan)
    kijun_last = _last(kijun)
    direction = "neutral"
    if None not in (close, a, b, tenkan_last, kijun_last):
        if close > max(a, b) and tenkan_last >= kijun_last:
            direction = "bullish"
        elif close < min(a, b) and tenkan_last <= kijun_last:
            direction = "bearish"
    return close, direction, {"tenkan": tenkan_last, "kijun": kijun_last, "senkou_a": a, "senkou_b": b}


def _trend_aroon(df):
    up, down = _aroon(df)
    direction = "neutral"
    if up is not None and down is not None:
        if up > 70 and down < 30:
            direction = "bullish"
        elif down > 70 and up < 30:
            direction = "bearish"
    return up - down if up is not None and down is not None else None, direction, {"up": up, "down": down}


def _trend_aroon_osc(df):
    up, down = _aroon(df)
    value = up - down if up is not None and down is not None else None
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"up": up, "down": down}


def _trend_supertrend(df):
    atr = _atr(df, 7)
    hl2 = (df["high"] + df["low"]) / 2
    upper = hl2 + 3 * atr
    lower = hl2 - 3 * atr
    close = _last(df["close"])
    direction = _price_swing_direction(df)
    band = _last(lower if direction == "bullish" else upper)
    return band, direction, {"supertrend_direction": 1 if direction == "bullish" else -1 if direction == "bearish" else 0, "close": close}


def _trend_alligator(df):
    jaw, teeth, lips = _alligator_lines(df)
    jaw_l, teeth_l, lips_l = _last(jaw), _last(teeth), _last(lips)
    direction = "neutral"
    if None not in (jaw_l, teeth_l, lips_l):
        if lips_l > teeth_l > jaw_l:
            direction = "bullish"
        elif lips_l < teeth_l < jaw_l:
            direction = "bearish"
    return lips_l, direction, {"jaw": jaw_l, "teeth": teeth_l, "lips": lips_l}


def _trend_vortex(df):
    plus, minus = _vortex(df)
    plus_l, minus_l = _last(plus), _last(minus)
    return plus_l - minus_l if plus_l is not None and minus_l is not None else None, _above_below(plus_l, minus_l), {"plus": plus_l, "minus": minus_l}


def _trend_stc(df):
    macd, _, _ = _macd(df["close"], 23, 50, 9)
    low = macd.rolling(10, min_periods=10).min()
    high = macd.rolling(10, min_periods=10).max()
    stc = (macd - low) / (high - low).replace(0, math.nan) * 100
    value = _last(stc)
    return value, _direction(value, lambda v: v > 50 or v > 25, lambda v: v < 50 or v < 75), {"stc": value}


def _trend_mama(df):
    mama = _kama(df["close"], 10, 2, 30)
    fama = _ema(mama, 10)
    mama_l, fama_l = _last(mama), _last(fama)
    return mama_l - fama_l if mama_l is not None and fama_l is not None else None, _above_below(mama_l, fama_l), {"mama": mama_l, "fama": fama_l}


def _trend_ma_envelopes(df):
    sma = _sma(df["close"], 20)
    upper = sma * 1.025
    lower = sma * 0.975
    close = _last(df["close"])
    upper_l, lower_l = _last(upper), _last(lower)
    direction = "neutral"
    if None not in (close, upper_l, lower_l):
        if close <= lower_l:
            direction = "bullish"
        elif close >= upper_l:
            direction = "bearish"
    return close, direction, {"upper": upper_l, "lower": lower_l}


def _trend_ma_ribbon(df):
    values = [_last(_ema(df["close"], period)) for period in [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]]
    direction = "neutral"
    if all(value is not None for value in values):
        if all(values[i] > values[i + 1] for i in range(len(values) - 1)):
            direction = "bullish"
        elif all(values[i] < values[i + 1] for i in range(len(values) - 1)):
            direction = "bearish"
    return values[0], direction, {"emas": values}


def _trend_linreg(df):
    slope = _last(_linreg_slope(df["close"], 14))
    return slope, _direction(slope, lambda v: v > 0, lambda v: v < 0), {"slope": slope}


def _trend_special_k(df):
    value_series = _wma(_roc(df["close"], 13), 10) + _wma(_roc(df["close"], 26), 15) + _wma(_roc(df["close"], 52), 20) + _wma(_roc(df["close"], 104), 30)
    value = _last(value_series)
    prev = _prev(value_series)
    direction = "neutral"
    if value is not None and prev is not None:
        if value > 0 and value > prev:
            direction = "bullish"
        elif value < 0 and value < prev:
            direction = "bearish"
    return value, direction, {"previous": prev}


def _trend_trendscore(df):
    close = _last(df["close"])
    mas = [_last(_sma(df["close"], period)) for period in [20, 50, 75, 100, 125, 150, 175, 200]]
    score = sum(1 for ma in mas if close is not None and ma is not None and close > ma)
    return score, _direction(score, lambda v: v >= 5, lambda v: v <= 3), {"max_score": 8}


def _trend_zlmacd(df):
    macd = _zlema(df["close"], 12) - _zlema(df["close"], 26)
    signal = _ema(macd, 9)
    value = _last(macd - signal)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"zlmacd": _last(macd), "signal": _last(signal)}


def _trend_tcf(df):
    gains = df["close"].diff().clip(lower=0).rolling(35, min_periods=35).sum()
    losses = (-df["close"].diff().clip(upper=0)).rolling(35, min_periods=35).sum()
    plus, minus = _last(gains), _last(losses)
    return plus - minus if plus is not None and minus is not None else None, _above_below(plus, minus), {"plus": plus, "minus": minus}


def _trend_chop(df):
    length = 14
    atr_sum = _tr(df).rolling(length, min_periods=length).sum()
    high_low = df["high"].rolling(length, min_periods=length).max() - df["low"].rolling(length, min_periods=length).min()
    chop = 100 * (atr_sum / high_low.replace(0, math.nan)).apply(lambda v: math.log10(v) if pd.notna(v) and v > 0 else math.nan) / math.log10(length)
    value = _last(chop)
    direction = _price_swing_direction(df) if value is not None and value < 38.2 else "neutral"
    return value, direction, {"trending": bool(value is not None and value < 38.2)}


TREND_SPECS = {
    "sma": IndicatorSpec("sma", "trend", _trend_sma),
    "ema": IndicatorSpec("ema", "trend", _trend_ema),
    "dema": IndicatorSpec("dema", "trend", _trend_dema),
    "tema": IndicatorSpec("tema", "trend", _trend_tema),
    "wma": IndicatorSpec("wma", "trend", _trend_wma),
    "hma": IndicatorSpec("hma", "trend", _trend_hma),
    "kama": IndicatorSpec("kama", "trend", _trend_kama),
    "mcgd": IndicatorSpec("mcgd", "trend", _trend_mcgd),
    "t3": IndicatorSpec("t3", "trend", _trend_t3),
    "zlma": IndicatorSpec("zlma", "trend", _trend_zlma),
    "macd": IndicatorSpec("macd", "trend", _trend_macd),
    "psar": IndicatorSpec("psar", "trend", _trend_psar),
    "adx": IndicatorSpec("adx", "trend", _trend_adx),
    "ichimoku": IndicatorSpec("ichimoku", "trend", _trend_ichimoku),
    "aroon": IndicatorSpec("aroon", "trend", _trend_aroon),
    "aroon_osc": IndicatorSpec("aroon_osc", "trend", _trend_aroon_osc),
    "supertrend": IndicatorSpec("supertrend", "trend", _trend_supertrend),
    "alligator": IndicatorSpec("alligator", "trend", _trend_alligator),
    "vortex": IndicatorSpec("vortex", "trend", _trend_vortex),
    "stc": IndicatorSpec("stc", "trend", _trend_stc),
    "mama": IndicatorSpec("mama", "trend", _trend_mama),
    "ma_envelopes": IndicatorSpec("ma_envelopes", "trend", _trend_ma_envelopes),
    "ma_ribbon": IndicatorSpec("ma_ribbon", "trend", _trend_ma_ribbon),
    "linreg": IndicatorSpec("linreg", "trend", _trend_linreg),
    "special_k": IndicatorSpec("special_k", "trend", _trend_special_k),
    "trendscore": IndicatorSpec("trendscore", "trend", _trend_trendscore),
    "zlmacd": IndicatorSpec("zlmacd", "trend", _trend_zlmacd),
    "tcf": IndicatorSpec("tcf", "trend", _trend_tcf),
    "chop": IndicatorSpec("chop", "trend", _trend_chop),
}


def _mom_rsi(df):
    value = _last(_rsi(df["close"], 14))
    return value, _direction(value, lambda v: v < 30, lambda v: v > 70), {"rsi": value}


def _mom_stoch(df):
    k = _last(_stoch(df, 14).rolling(3, min_periods=1).mean())
    return k, _direction(k, lambda v: v < 20, lambda v: v > 80), {"k": k}


def _mom_stochrsi(df):
    rsi = _rsi(df["close"], 14)
    low = rsi.rolling(14, min_periods=14).min()
    high = rsi.rolling(14, min_periods=14).max()
    stoch = (rsi - low) / (high - low).replace(0, math.nan)
    value = _last(stoch.rolling(3, min_periods=1).mean())
    return value, _direction(value, lambda v: v < 0.2, lambda v: v > 0.8), {"stochrsi_k": value}


def _mom_smi(df):
    midpoint = (df["high"].rolling(5).max() + df["low"].rolling(5).min()) / 2
    half_range = (df["high"].rolling(5).max() - df["low"].rolling(5).min()) / 2
    smi = _ema(_ema(df["close"] - midpoint, 3), 3) / _ema(_ema(half_range, 3), 3).replace(0, math.nan) * 100
    value = _last(smi)
    return value, _direction(value, lambda v: v < -40, lambda v: v > 40), {"smi": value}


def _mom_willr(df):
    high = df["high"].rolling(14).max()
    low = df["low"].rolling(14).min()
    willr = (high - df["close"]) / (high - low).replace(0, math.nan) * -100
    value = _last(willr)
    return value, _direction(value, lambda v: v < -80, lambda v: v > -20), {"willr": value}


def _mom_cci(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma = _sma(tp, 20)
    mean_dev = (tp - sma).abs().rolling(20, min_periods=20).mean()
    cci = (tp - sma) / (0.015 * mean_dev.replace(0, math.nan))
    value = _last(cci)
    return value, _direction(value, lambda v: v < -100, lambda v: v > 100), {"cci": value}


def _mom_mom(df):
    value = _last(_mom(df["close"], 10))
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"momentum": value}


def _mom_roc(df):
    value = _last(_roc(df["close"], 10))
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"roc": value}


def _mom_uo(df):
    prev_close = df["close"].shift(1)
    bp = df["close"] - pd.concat([df["low"], prev_close], axis=1).min(axis=1)
    tr = pd.concat([df["high"], prev_close], axis=1).max(axis=1) - pd.concat([df["low"], prev_close], axis=1).min(axis=1)
    avg7 = bp.rolling(7).sum() / tr.rolling(7).sum().replace(0, math.nan)
    avg14 = bp.rolling(14).sum() / tr.rolling(14).sum().replace(0, math.nan)
    avg28 = bp.rolling(28).sum() / tr.rolling(28).sum().replace(0, math.nan)
    uo = 100 * (4 * avg7 + 2 * avg14 + avg28) / 7
    value = _last(uo)
    return value, _direction(value, lambda v: v < 30, lambda v: v > 70), {"uo": value}


def _mom_demarker(df):
    demax = (df["high"] - df["high"].shift(1)).clip(lower=0)
    demin = (df["low"].shift(1) - df["low"]).clip(lower=0)
    dem = _sma(demax, 14) / (_sma(demax, 14) + _sma(demin, 14)).replace(0, math.nan)
    value = _last(dem)
    return value, _direction(value, lambda v: v < 0.3, lambda v: v > 0.7), {"demarker": value}


def _mom_ao(df):
    value = _last(_ao(df))
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"ao": value}


def _mom_ac(df):
    ao = _ao(df)
    ac = ao - _sma(ao, 5)
    value = _last(ac)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"ac": value}


def _mom_trix(df):
    triple = _ema(_ema(_ema(df["close"], 18), 18), 18)
    trix = triple.pct_change() * 100
    signal = _ema(trix, 9)
    value = _last(trix)
    sig = _last(signal)
    direction = _direction(value, lambda v: v > 0, lambda v: v < 0)
    if direction == "neutral":
        direction = _above_below(value, sig)
    return value, direction, {"signal": sig}


def _mom_tsi(df):
    pc = df["close"].diff()
    tsi = 100 * _ema(_ema(pc, 13), 25) / _ema(_ema(pc.abs(), 13), 25).replace(0, math.nan)
    value = _last(tsi)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"tsi": value}


def _mom_coppock(df):
    coppock = _wma(_roc(df["close"], 11) + _roc(df["close"], 14), 10)
    value = _last(coppock)
    direction = "bullish" if _crossed_above(coppock, 0) else "bearish" if _crossed_below(coppock, 0) else _direction(value, lambda v: v > 0, lambda v: v < 0)
    return value, direction, {"coppock": value}


def _mom_kst(df):
    kst = _sma(_roc(df["close"], 10), 10) + 2 * _sma(_roc(df["close"], 13), 13) + 3 * _sma(_roc(df["close"], 14), 14) + 4 * _sma(_roc(df["close"], 15), 15)
    signal = _sma(kst, 9)
    value, sig = _last(kst), _last(signal)
    return value, _above_below(value, sig), {"signal": sig}


def _mom_pmo(df):
    pmo = _ema(_ema(df["close"].pct_change() * 1000, 35), 20)
    signal = _ema(pmo, 10)
    value, sig = _last(pmo), _last(signal)
    return value, _above_below(value, sig), {"signal": sig}


def _mom_cmo(df):
    delta = df["close"].diff()
    up = delta.clip(lower=0).rolling(9).sum()
    down = (-delta.clip(upper=0)).rolling(9).sum()
    cmo = (up - down) / (up + down).replace(0, math.nan) * 100
    value = _last(cmo)
    return value, _direction(value, lambda v: v < -50, lambda v: v > 50), {"cmo": value}


def _mom_rmi(df):
    value = _last(_rsi(df["close"], 20, 5))
    return value, _direction(value, lambda v: v < 30, lambda v: v > 70), {"rmi": value}


def _mom_elder_ray(df):
    ema = _ema(df["close"], 13)
    bull = df["high"] - ema
    bear = df["low"] - ema
    bull_l, bull_p = _last(bull), _prev(bull)
    bear_l, bear_p = _last(bear), _prev(bear)
    direction = "neutral"
    if bear_l is not None and bear_p is not None and bear_l < 0 and bear_l > bear_p:
        direction = "bullish"
    elif bull_l is not None and bull_p is not None and bull_l > 0 and bull_l < bull_p:
        direction = "bearish"
    return bear_l if direction == "bullish" else bull_l, direction, {"bull_power": bull_l, "bear_power": bear_l}


def _mom_force_index(df):
    fi = _ema(df["close"].diff() * df["volume"], 13)
    value = _last(fi)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"efi": value}


def _mom_bop(df):
    bop = (df["close"] - df["open"]) / (df["high"] - df["low"]).replace(0, math.nan)
    value = _last(bop)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"bop": value}


def _mom_dpo(df):
    dpo = df["close"] - _sma(df["close"], 20).shift(11)
    value = _last(dpo)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"dpo": value}


def _mom_fisher(df):
    midpoint = (df["high"] + df["low"]) / 2
    low = midpoint.rolling(9).min()
    high = midpoint.rolling(9).max()
    value_series = 2 * ((midpoint - low) / (high - low).replace(0, math.nan) - 0.5)
    value_series = value_series.clip(-0.999, 0.999)
    fisher = 0.5 * ((1 + value_series) / (1 - value_series)).apply(lambda v: math.log(v) if pd.notna(v) and v > 0 else math.nan)
    value = _last(fisher)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"fisher": value}


def _mom_rvi(df):
    rvi = _ema(df["close"] - df["open"], 14) / _ema(df["high"] - df["low"], 14).replace(0, math.nan)
    signal = _sma(rvi, 4)
    value, sig = _last(rvi), _last(signal)
    return value, _above_below(value, sig), {"signal": sig}


def _mom_laguerre_rsi(df):
    gamma = 0.5
    l0 = l1 = l2 = l3 = float(df["close"].iloc[0])
    values = []
    for price in df["close"]:
        price = float(price)
        l0_old, l1_old, l2_old, l3_old = l0, l1, l2, l3
        l0 = (1 - gamma) * price + gamma * l0_old
        l1 = -gamma * l0 + l0_old + gamma * l1_old
        l2 = -gamma * l1 + l1_old + gamma * l2_old
        l3 = -gamma * l2 + l2_old + gamma * l3_old
        cu = sum(max(a - b, 0) for a, b in [(l0, l1), (l1, l2), (l2, l3)])
        cd = sum(max(b - a, 0) for a, b in [(l0, l1), (l1, l2), (l2, l3)])
        values.append(cu / (cu + cd) if cu + cd else 0.5)
    value = values[-1]
    return value, _direction(value, lambda v: v < 0.2, lambda v: v > 0.8), {"laguerre_rsi": value}


def _mom_double_stoch(df):
    first = _stoch(df, 14)
    second = (first - first.rolling(3).min()) / (first.rolling(3).max() - first.rolling(3).min()).replace(0, math.nan) * 100
    value = _last(second)
    return value, _direction(value, lambda v: v < 20, lambda v: v > 80), {"double_stoch": value}


def _mom_crsi(df):
    close = df["close"]
    rsi3 = _rsi(close, 3)
    streak = close.diff().apply(lambda v: 1 if v > 0 else -1 if v < 0 else 0)
    streak_rsi = _rsi(streak.cumsum(), 2)
    roc = _roc(close, 1)
    percent_rank = roc.rolling(100).apply(lambda values: pd.Series(values).rank(pct=True).iloc[-1] * 100)
    crsi = (rsi3 + streak_rsi + percent_rank) / 3
    value = _last(crsi)
    return value, _direction(value, lambda v: v < 20, lambda v: v > 80), {"crsi": value}


def _mom_mass_index(df):
    high_low = df["high"] - df["low"]
    mass = (_ema(high_low, 9) / _ema(_ema(high_low, 9), 9).replace(0, math.nan)).rolling(25).sum()
    value = _last(mass)
    prev = _prev(mass)
    direction = _price_swing_direction(df) if value is not None and prev is not None and prev > 27 and value < 26.5 else "neutral"
    return value, direction, {"previous": prev}


def _mom_pfe(df):
    length = 10
    direct = df["close"] - df["close"].shift(length)
    path = ((df["close"].diff() ** 2 + 1) ** 0.5).rolling(length).sum()
    pfe = direct.apply(lambda v: 1 if v > 0 else -1 if v < 0 else 0) * 100 * direct.abs() / path.replace(0, math.nan)
    value = _last(pfe)
    return value, _direction(value, lambda v: v > 50, lambda v: v < -50), {"pfe": value}


def _mom_disparity(df):
    sma = _sma(df["close"], 14)
    disparity = (df["close"] - sma) / sma.replace(0, math.nan) * 100
    value = _last(disparity)
    return value, _direction(value, lambda v: v < -2, lambda v: v > 2), {"disparity": value}


def _mom_inertia(df):
    value_series = _linreg_slope(_mom_rvi_series(df), 14)
    value = _last(value_series)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"inertia": value}


def _mom_rvi_series(df):
    return _ema(df["close"] - df["open"], 14) / _ema(df["high"] - df["low"], 14).replace(0, math.nan)


def _mom_tti(df):
    sma = _sma(df["close"], 20)
    above = (df["close"] > sma).rolling(20, min_periods=20).sum()
    tii = above / 20 * 100
    value = _last(tii)
    return value, _direction(value, lambda v: v > 80, lambda v: v < 20), {"tii": value}


def _mom_ewo(df):
    midpoint = (df["high"] + df["low"]) / 2
    ewo = _sma(midpoint, 5) - _sma(midpoint, 35)
    value = _last(ewo)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"ewo": value}


def _mom_gator(df):
    jaw, teeth, lips = _alligator_lines(df)
    upper = (jaw - teeth).abs()
    lower = -(teeth - lips).abs()
    ao = _last(_ao(df))
    expanding = (_last(upper) or 0) > (_prev(upper) or 0) and abs(_last(lower) or 0) > abs(_prev(lower) or 0)
    direction = "neutral"
    if expanding and ao is not None:
        direction = _direction(ao, lambda v: v > 0, lambda v: v < 0)
    return ao, direction, {"upper": _last(upper), "lower": _last(lower), "expanding": expanding}


def _mom_qqe(df):
    rsi_ma = _ema(_rsi(df["close"], 14), 5)
    trailing = _ema(rsi_ma, 14)
    value, trail = _last(rsi_ma), _last(trailing)
    return value, _above_below(value, trail), {"qqe_level": trail}


def _mom_cdmi(df):
    std5 = df["close"].rolling(5).std()
    std10 = df["close"].rolling(10).std()
    adaptive_period = int(max(5, min(30, round(14 * float((_last(std5) or 1) / ((_last(std10) or 1)))))))
    value = _last(_rsi(df["close"], adaptive_period))
    return value, _direction(value, lambda v: v < 30, lambda v: v > 70), {"period": adaptive_period}


def _mom_rainbow(df):
    layers = []
    current = df["close"]
    for _ in range(10):
        current = _sma(current, 2)
        layers.append(_last(current))
    close = _last(df["close"])
    direction = "neutral"
    if close is not None and all(layer is not None for layer in layers):
        if close > max(layers):
            direction = "bullish"
        elif close < min(layers):
            direction = "bearish"
    return close, direction, {"layers": layers}


def _mom_gann_swing(df):
    highs = df["high"].tail(3).tolist()
    lows = df["low"].tail(3).tolist()
    direction = "neutral"
    value = 0
    if len(highs) == 3 and highs[-1] > highs[-2] > highs[-3]:
        direction, value = "bullish", 1
    elif len(lows) == 3 and lows[-1] < lows[-2] < lows[-3]:
        direction, value = "bearish", -1
    return value, direction, {"swing": value}


MOMENTUM_SPECS = {
    "rsi": IndicatorSpec("rsi", "momentum", _mom_rsi),
    "stoch": IndicatorSpec("stoch", "momentum", _mom_stoch),
    "stochrsi": IndicatorSpec("stochrsi", "momentum", _mom_stochrsi),
    "smi": IndicatorSpec("smi", "momentum", _mom_smi),
    "willr": IndicatorSpec("willr", "momentum", _mom_willr),
    "cci": IndicatorSpec("cci", "momentum", _mom_cci),
    "mom": IndicatorSpec("mom", "momentum", _mom_mom),
    "roc": IndicatorSpec("roc", "momentum", _mom_roc),
    "uo": IndicatorSpec("uo", "momentum", _mom_uo),
    "demarker": IndicatorSpec("demarker", "momentum", _mom_demarker),
    "ao": IndicatorSpec("ao", "momentum", _mom_ao),
    "ac": IndicatorSpec("ac", "momentum", _mom_ac),
    "trix": IndicatorSpec("trix", "momentum", _mom_trix),
    "tsi": IndicatorSpec("tsi", "momentum", _mom_tsi),
    "coppock": IndicatorSpec("coppock", "momentum", _mom_coppock),
    "kst": IndicatorSpec("kst", "momentum", _mom_kst),
    "pmo": IndicatorSpec("pmo", "momentum", _mom_pmo),
    "cmo": IndicatorSpec("cmo", "momentum", _mom_cmo),
    "rmi": IndicatorSpec("rmi", "momentum", _mom_rmi),
    "elder_ray": IndicatorSpec("elder_ray", "momentum", _mom_elder_ray),
    "force_index": IndicatorSpec("force_index", "momentum", _mom_force_index),
    "bop": IndicatorSpec("bop", "momentum", _mom_bop),
    "dpo": IndicatorSpec("dpo", "momentum", _mom_dpo),
    "fisher": IndicatorSpec("fisher", "momentum", _mom_fisher),
    "rvi": IndicatorSpec("rvi", "momentum", _mom_rvi),
    "laguerre_rsi": IndicatorSpec("laguerre_rsi", "momentum", _mom_laguerre_rsi),
    "double_stoch": IndicatorSpec("double_stoch", "momentum", _mom_double_stoch),
    "crsi": IndicatorSpec("crsi", "momentum", _mom_crsi),
    "mass_index": IndicatorSpec("mass_index", "momentum", _mom_mass_index),
    "pfe": IndicatorSpec("pfe", "momentum", _mom_pfe),
    "disparity": IndicatorSpec("disparity", "momentum", _mom_disparity),
    "inertia": IndicatorSpec("inertia", "momentum", _mom_inertia),
    "tti": IndicatorSpec("tti", "momentum", _mom_tti),
    "ewo": IndicatorSpec("ewo", "momentum", _mom_ewo),
    "gator": IndicatorSpec("gator", "momentum", _mom_gator),
    "qqe": IndicatorSpec("qqe", "momentum", _mom_qqe),
    "cdmi": IndicatorSpec("cdmi", "momentum", _mom_cdmi),
    "rainbow": IndicatorSpec("rainbow", "momentum", _mom_rainbow),
    "gann_swing": IndicatorSpec("gann_swing", "momentum", _mom_gann_swing),
}


def _volume_price_direction(df):
    close = _last(df["close"])
    prev_close = _prev(df["close"])
    open_ = _last(df["open"])
    reference = prev_close if prev_close is not None else open_
    return _above_below(close, reference)


def _money_flow_volume(df):
    spread = (df["high"] - df["low"]).replace(0, math.nan)
    multiplier = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / spread
    return multiplier.fillna(0) * df["volume"]


def _vol_obv(df):
    signs = df["close"].diff().apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
    obv = (signs * df["volume"]).cumsum()
    signal = _ema(obv, 20)
    value = _last(obv)
    return value, _above_below(value, _last(signal)), {"ema": _last(signal)}


def _vol_vwap(df):
    typical = (df["high"] + df["low"] + df["close"]) / 3
    if "time" in df:
        session = pd.to_datetime(df["time"]).dt.date
        cumulative_value = (typical * df["volume"]).groupby(session).cumsum()
        cumulative_volume = df["volume"].groupby(session).cumsum()
    else:
        cumulative_value = (typical * df["volume"]).cumsum()
        cumulative_volume = df["volume"].cumsum()
    vwap = cumulative_value / cumulative_volume.replace(0, math.nan)
    value = _last(vwap)
    return value, _above_below(_last(df["close"]), value), {"close": _last(df["close"])}


def _vol_avwap(df):
    typical = (df["high"] + df["low"] + df["close"]) / 3
    window = min(len(df), 100)
    anchored_tp = typical.tail(window)
    anchored_vol = df["volume"].tail(window)
    value = float((anchored_tp * anchored_vol).sum() / anchored_vol.sum()) if anchored_vol.sum() else None
    return value, _above_below(_last(df["close"]), value), {"anchor_bars": window, "close": _last(df["close"])}


def _vol_ad(df):
    ad = _money_flow_volume(df).cumsum()
    value = _last(ad)
    prev = _prev(ad)
    return value, _above_below(value, prev), {"previous": prev}


def _vol_cmf(df):
    mfv = _money_flow_volume(df)
    cmf = mfv.rolling(20, min_periods=20).sum() / df["volume"].rolling(20, min_periods=20).sum().replace(0, math.nan)
    value = _last(cmf)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"cmf": value}


def _vol_chaikin_osc(df):
    ad = _money_flow_volume(df).cumsum()
    osc = _ema(ad, 3) - _ema(ad, 10)
    value = _last(osc)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"oscillator": value}


def _vol_mfi(df):
    typical = (df["high"] + df["low"] + df["close"]) / 3
    raw_flow = typical * df["volume"]
    positive = raw_flow.where(typical.diff() > 0, 0)
    negative = raw_flow.where(typical.diff() < 0, 0)
    ratio = positive.rolling(14, min_periods=14).sum() / negative.rolling(14, min_periods=14).sum().replace(0, math.nan)
    mfi = 100 - (100 / (1 + ratio))
    value = _last(mfi.fillna(100).where(negative.rolling(14, min_periods=14).sum() != 0, 100))
    return value, _direction(value, lambda v: v < 20, lambda v: v > 80), {"mfi": value}


def _vol_vpt(df):
    pct = df["close"].pct_change().fillna(0)
    vpt = (df["volume"] * pct).cumsum()
    signal = _ema(vpt, 20)
    value = _last(vpt)
    return value, _above_below(value, _last(signal)), {"ema": _last(signal)}


def _vol_kvo(df):
    typical = df["high"] + df["low"] + df["close"]
    trend = typical.diff().apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
    volume_force = df["volume"] * trend
    kvo = _ema(volume_force, 34) - _ema(volume_force, 55)
    signal = _ema(kvo, 13)
    value = _last(kvo)
    return value, _above_below(value, _last(signal)), {"signal": _last(signal)}


def _vol_eom(df):
    midpoint_move = ((df["high"] + df["low"]) / 2).diff()
    box_ratio = df["volume"] / (df["high"] - df["low"]).replace(0, math.nan)
    eom = _sma(midpoint_move / box_ratio.replace(0, math.nan), 14)
    value = _last(eom)
    return value, _direction(value, lambda v: v > 0, lambda v: v < 0), {"eom": value}


def _volume_index(df, use_positive_volume):
    values = [1000.0]
    for i in range(1, len(df)):
        volume_condition = df["volume"].iloc[i] > df["volume"].iloc[i - 1]
        if volume_condition == use_positive_volume:
            change = (df["close"].iloc[i] - df["close"].iloc[i - 1]) / df["close"].iloc[i - 1]
            values.append(values[-1] + change * values[-1])
        else:
            values.append(values[-1])
    return pd.Series(values, index=df.index)


def _vol_pvi(df):
    pvi = _volume_index(df, True)
    signal = _ema(pvi, 255)
    value = _last(pvi)
    return value, _above_below(value, _last(signal)), {"signal": _last(signal)}


def _vol_nvi(df):
    nvi = _volume_index(df, False)
    signal = _ema(nvi, 255)
    value = _last(nvi)
    return value, _above_below(value, _last(signal)), {"signal": _last(signal)}


def _vol_vrsi(df):
    value = _last(_rsi(df["volume"], 14))
    price_direction = _volume_price_direction(df)
    direction = price_direction if value is not None and value > 50 else "neutral"
    return value, direction, {"price_direction": price_direction}


def _vol_rvol(df):
    avg_volume = _sma(df["volume"], 20)
    value = _last(df["volume"] / avg_volume.replace(0, math.nan))
    price_direction = _volume_price_direction(df)
    direction = price_direction if value is not None and value > 1.5 else "neutral"
    return value, direction, {"average_volume": _last(avg_volume)}


def _vol_pvo(df):
    slow = _ema(df["volume"], 26)
    pvo = (_ema(df["volume"], 12) - slow) / slow.replace(0, math.nan) * 100
    signal = _ema(pvo, 9)
    value = _last(pvo)
    price_direction = _volume_price_direction(df)
    direction = price_direction if value is not None and value > 0 else "neutral"
    return value, direction, {"signal": _last(signal), "histogram": value - (_last(signal) or 0) if value is not None else None}


def _vol_tvi(df):
    typical = (df["high"] + df["low"] + df["close"]) / 3
    signs = typical.diff().apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
    tvi = (signs * df["volume"]).cumsum()
    value = _last(tvi)
    prev = _prev(tvi)
    return value, _above_below(value, prev), {"previous": prev}


def _vol_vol_profile(df):
    prices = df["close"]
    bins = min(20, max(4, len(df) // 10))
    bucket = pd.cut(prices, bins=bins, duplicates="drop")
    volume_by_bucket = df.groupby(bucket, observed=False)["volume"].sum()
    if volume_by_bucket.empty:
        return None, "neutral", {"reason": "no_profile"}
    poc_interval = volume_by_bucket.idxmax()
    poc = float((poc_interval.left + poc_interval.right) / 2)
    ordered = volume_by_bucket.sort_index()
    cumulative = ordered.cumsum() / ordered.sum()
    val_interval = cumulative[cumulative >= 0.15].index[0]
    vah_interval = cumulative[cumulative >= 0.85].index[0]
    val = float((val_interval.left + val_interval.right) / 2)
    vah = float((vah_interval.left + vah_interval.right) / 2)
    close = _last(df["close"])
    direction = "neutral"
    if close is not None:
        if close <= val:
            direction = "bullish"
        elif close >= vah:
            direction = "bearish"
    return poc, direction, {"poc": poc, "vah": vah, "val": val, "close": close}


def _vol_smi_vol(df):
    session_move = df["close"] - df["open"]
    smi = session_move.rolling(5, min_periods=5).sum()
    value = _last(smi)
    prev = _prev(smi)
    return value, _above_below(value, prev), {"previous": prev}


def _vol_volume_raw(df):
    avg_volume = _sma(df["volume"], 20)
    value = _last(df["volume"])
    spike = value is not None and _last(avg_volume) is not None and value > _last(avg_volume) * 2
    candle_direction = _above_below(_last(df["close"]), _last(df["open"]))
    direction = candle_direction if spike else "neutral"
    return value, direction, {"average_volume": _last(avg_volume), "spike": spike}


VOLUME_SPECS = {
    "obv": IndicatorSpec("obv", "volume", _vol_obv),
    "vwap": IndicatorSpec("vwap", "volume", _vol_vwap),
    "avwap": IndicatorSpec("avwap", "volume", _vol_avwap),
    "ad": IndicatorSpec("ad", "volume", _vol_ad),
    "cmf": IndicatorSpec("cmf", "volume", _vol_cmf),
    "chaikin_osc": IndicatorSpec("chaikin_osc", "volume", _vol_chaikin_osc),
    "mfi": IndicatorSpec("mfi", "volume", _vol_mfi),
    "vpt": IndicatorSpec("vpt", "volume", _vol_vpt),
    "kvo": IndicatorSpec("kvo", "volume", _vol_kvo),
    "eom": IndicatorSpec("eom", "volume", _vol_eom),
    "pvi": IndicatorSpec("pvi", "volume", _vol_pvi),
    "nvi": IndicatorSpec("nvi", "volume", _vol_nvi),
    "vrsi": IndicatorSpec("vrsi", "volume", _vol_vrsi),
    "rvol": IndicatorSpec("rvol", "volume", _vol_rvol),
    "pvo": IndicatorSpec("pvo", "volume", _vol_pvo),
    "tvi": IndicatorSpec("tvi", "volume", _vol_tvi),
    "vol_profile": IndicatorSpec("vol_profile", "volume", _vol_vol_profile),
    "smi_vol": IndicatorSpec("smi_vol", "volume", _vol_smi_vol),
    "volume_raw": IndicatorSpec("volume_raw", "volume", _vol_volume_raw),
}


def _bbands_components(close: pd.Series, length: int = 20, std: float = 2.0):
    mid = _sma(close, length)
    sd = close.rolling(length, min_periods=length).std(ddof=0)
    upper = mid + std * sd
    lower = mid - std * sd
    return lower, mid, upper


def _vlt_bbands(df):
    lower, mid, upper = _bbands_components(df["close"])
    close = _last(df["close"])
    upper_l, mid_l, lower_l = _last(upper), _last(mid), _last(lower)
    direction = "neutral"
    if None not in (close, upper_l, lower_l):
        if close < lower_l:
            direction = "bullish"
        elif close > upper_l:
            direction = "bearish"
    return mid_l, direction, {"upper": upper_l, "lower": lower_l, "close": close}


def _vlt_bbw(df):
    lower, mid, upper = _bbands_components(df["close"])
    bbw = (upper - lower) / mid.replace(0, math.nan) * 100
    value = _last(bbw)
    valid = bbw.dropna().tail(252)
    threshold = float(valid.quantile(0.10)) if len(valid) >= 20 else None
    squeeze = value is not None and threshold is not None and value < threshold
    direction = _price_swing_direction(df) if squeeze else "neutral"
    return value, direction, {"squeeze": bool(squeeze), "p10": threshold}


def _vlt_atr(df):
    atr = _atr(df, 14)
    avg = _sma(atr, 20)
    value = _last(atr)
    avg_l = _last(avg)
    expanding = value is not None and avg_l is not None and value > avg_l
    direction = _price_swing_direction(df) if expanding else "neutral"
    return value, direction, {"atr_avg20": avg_l, "expanding": bool(expanding)}


def _vlt_kc(df):
    mid = _ema(df["close"], 20)
    atr = _atr(df, 10)
    upper = mid + 2 * atr
    lower = mid - 2 * atr
    close = _last(df["close"])
    upper_l, lower_l, mid_l = _last(upper), _last(lower), _last(mid)
    direction = "neutral"
    if None not in (close, upper_l, lower_l):
        if close < lower_l:
            direction = "bullish"
        elif close > upper_l:
            direction = "bearish"
    return mid_l, direction, {"upper": upper_l, "lower": lower_l, "close": close}


def _vlt_donchian(df):
    upper = df["high"].rolling(20, min_periods=20).max()
    lower = df["low"].rolling(20, min_periods=20).min()
    close = _last(df["close"])
    prev_upper = _prev(upper)
    prev_lower = _prev(lower)
    upper_l, lower_l = _last(upper), _last(lower)
    direction = "neutral"
    if close is not None and prev_upper is not None and close > prev_upper:
        direction = "bullish"
    elif close is not None and prev_lower is not None and close < prev_lower:
        direction = "bearish"
    mid = (upper_l + lower_l) / 2 if upper_l is not None and lower_l is not None else None
    return mid, direction, {"upper": upper_l, "lower": lower_l, "close": close}


def _vlt_stdev(df):
    sd = df["close"].rolling(20, min_periods=20).std(ddof=0)
    avg = _sma(sd, 20)
    value = _last(sd)
    avg_l = _last(avg)
    expanding = value is not None and avg_l is not None and value > avg_l
    direction = _price_swing_direction(df) if expanding else "neutral"
    return value, direction, {"stdev_avg20": avg_l, "expanding": bool(expanding)}


def _vlt_chaikin_vol(df):
    hl = df["high"] - df["low"]
    ema_hl = _ema(hl, 10)
    cv = _roc(ema_hl, 10)
    value = _last(cv)
    expanding = value is not None and value > 0
    direction = _price_swing_direction(df) if expanding else "neutral"
    return value, direction, {"expanding": bool(expanding)}


def _vlt_starc(df):
    mid = _sma(df["close"], 5)
    atr = _atr(df, 15)
    upper = mid + atr * 1.33
    lower = mid - atr * 1.33
    close = _last(df["close"])
    upper_l, lower_l, mid_l = _last(upper), _last(lower), _last(mid)
    direction = "neutral"
    if None not in (close, upper_l, lower_l):
        if close <= lower_l:
            direction = "bullish"
        elif close >= upper_l:
            direction = "bearish"
    return mid_l, direction, {"upper": upper_l, "lower": lower_l, "close": close}


def _vlt_adr(df):
    daily_range = df["high"] - df["low"]
    adr = _sma(daily_range, 14)
    value = _last(adr)
    move = None
    if value is not None and value > 0:
        close = _last(df["close"])
        open_ = _last(df["open"])
        if close is not None and open_ is not None:
            move = (close - open_) / value
    expanding = move is not None and abs(move) > 0.5
    direction = "neutral"
    if expanding:
        direction = "bullish" if move > 0 else "bearish"
    return value, direction, {"move_ratio": move, "expanding": bool(expanding)}


def _vlt_hv(df):
    log_returns = (df["close"] / df["close"].shift(1)).apply(
        lambda v: math.log(v) if pd.notna(v) and v > 0 else math.nan
    )
    sd = log_returns.rolling(20, min_periods=20).std(ddof=0)
    hv = sd * math.sqrt(252) * 100
    value = _last(hv)
    valid = hv.dropna().tail(252)
    threshold = float(valid.quantile(0.25)) if len(valid) >= 20 else None
    low_vol = value is not None and threshold is not None and value < threshold
    direction = _price_swing_direction(df) if low_vol else "neutral"
    return value, direction, {"low_vol": bool(low_vol), "p25": threshold}


def _vlt_ulcer(df):
    length = 14
    rolling_max = df["close"].rolling(length, min_periods=length).max()
    drawdown = (df["close"] - rolling_max) / rolling_max.replace(0, math.nan) * 100
    sq = drawdown.pow(2)
    ui = sq.rolling(length, min_periods=length).mean().pow(0.5)
    value = _last(ui)
    prev = _prev(ui)
    direction = "neutral"
    if value is not None and prev is not None and value < prev:
        direction = "bullish"
    return value, direction, {"previous": prev}


def _vlt_ttm_squeeze(df):
    lower_bb, _, upper_bb = _bbands_components(df["close"], 20, 2.0)
    mid_kc = _ema(df["close"], 20)
    atr_kc = _atr(df, 20)
    upper_kc = mid_kc + 1.5 * atr_kc
    lower_kc = mid_kc - 1.5 * atr_kc
    sqz_on_series = (lower_bb >= lower_kc) & (upper_bb <= upper_kc)
    sqz_on = bool(sqz_on_series.iloc[-1]) if len(sqz_on_series.dropna()) else False
    sqz_on_prev = bool(sqz_on_series.iloc[-2]) if len(sqz_on_series.dropna()) >= 2 else False
    sqz_off = sqz_on_prev and not sqz_on
    midpoint = ((df["high"].rolling(20).max() + df["low"].rolling(20).min()) / 2 + _sma(df["close"], 20)) / 2
    momentum = _linreg_slope(df["close"] - midpoint, 20)
    mom_value = _last(momentum)
    direction = "neutral"
    if sqz_off and mom_value is not None:
        if mom_value > 0:
            direction = "bullish"
        elif mom_value < 0:
            direction = "bearish"
    return mom_value, direction, {"squeeze_on": sqz_on, "squeeze_released": bool(sqz_off)}


def _vlt_pctb(df):
    lower, _, upper = _bbands_components(df["close"])
    band_width = (upper - lower).replace(0, math.nan)
    pctb = (df["close"] - lower) / band_width
    value = _last(pctb)
    direction = "neutral"
    if value is not None:
        if value < 0:
            direction = "bullish"
        elif value > 1:
            direction = "bearish"
    return value, direction, {"upper": _last(upper), "lower": _last(lower)}


def _vlt_adr_pct(df):
    daily_range = df["high"] - df["low"]
    adr = _sma(daily_range, 14)
    close = _last(df["close"])
    adr_l = _last(adr)
    value = (adr_l / close * 100) if close and adr_l is not None else None
    direction = "neutral"
    if value is not None and adr_l is not None:
        move = _last(df["close"]) - _last(df["open"]) if _last(df["open"]) is not None else None
        if move is not None and abs(move) < adr_l:
            direction = "bullish" if move > 0 else "bearish" if move < 0 else "neutral"
    return value, direction, {"adr": adr_l, "close": close}


def _vlt_linreg_channel(df):
    length = 20
    series = df["close"].tail(length).reset_index(drop=True)
    if len(series) < length:
        return None, "neutral", {"reason": "insufficient_bars"}
    xs = pd.Series(range(length), dtype="float64")
    x_mean = xs.mean()
    y_mean = series.mean()
    denom = ((xs - x_mean) ** 2).sum()
    if denom == 0:
        return None, "neutral", {"reason": "zero_variance"}
    slope = ((xs - x_mean) * (series - y_mean)).sum() / denom
    intercept = y_mean - slope * x_mean
    fitted = intercept + slope * xs
    residuals = series - fitted
    stderr = float((residuals ** 2).sum() / (length - 2)) ** 0.5 if length > 2 else 0.0
    upper = float(fitted.iloc[-1]) + 2 * stderr
    lower = float(fitted.iloc[-1]) - 2 * stderr
    close = _last(df["close"])
    direction = "neutral"
    if close is not None:
        if close <= lower:
            direction = "bullish"
        elif close >= upper:
            direction = "bearish"
    return float(fitted.iloc[-1]), direction, {"upper": upper, "lower": lower, "slope": float(slope)}


VOLATILITY_SPECS = {
    "bbands": IndicatorSpec("bbands", "volatility", _vlt_bbands),
    "bbw": IndicatorSpec("bbw", "volatility", _vlt_bbw),
    "atr": IndicatorSpec("atr", "volatility", _vlt_atr),
    "kc": IndicatorSpec("kc", "volatility", _vlt_kc),
    "donchian": IndicatorSpec("donchian", "volatility", _vlt_donchian),
    "stdev": IndicatorSpec("stdev", "volatility", _vlt_stdev),
    "chaikin_vol": IndicatorSpec("chaikin_vol", "volatility", _vlt_chaikin_vol),
    "starc": IndicatorSpec("starc", "volatility", _vlt_starc),
    "adr": IndicatorSpec("adr", "volatility", _vlt_adr),
    "hv": IndicatorSpec("hv", "volatility", _vlt_hv),
    "ulcer": IndicatorSpec("ulcer", "volatility", _vlt_ulcer),
    "ttm_squeeze": IndicatorSpec("ttm_squeeze", "volatility", _vlt_ttm_squeeze),
    "pctb": IndicatorSpec("pctb", "volatility", _vlt_pctb),
    "adr_pct": IndicatorSpec("adr_pct", "volatility", _vlt_adr_pct),
    "linreg_channel": IndicatorSpec("linreg_channel", "volatility", _vlt_linreg_channel),
}
