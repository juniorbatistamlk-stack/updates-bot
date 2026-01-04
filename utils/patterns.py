# utils/patterns.py
"""
Price Action Pattern Detection
Implements: Pin Bar, Engulfing, Fakeout, Inside Bar
"""

def is_doji(candle, max_body_pct=0.12, min_range=0.0):
    """Detecta Doji simples (corpo muito pequeno em relação ao range)."""
    range_total = candle['high'] - candle['low']
    if range_total <= min_range:
        return False
    body = abs(candle['close'] - candle['open'])
    return body <= (range_total * max_body_pct)

def is_harami(prev_candle, curr_candle):
    """Detecta Harami (corpo atual dentro do corpo anterior).

    Returns:
        str or None: 'BULLISH_HARAMI' ou 'BEARISH_HARAMI'
    """
    prev_top = max(prev_candle['open'], prev_candle['close'])
    prev_bot = min(prev_candle['open'], prev_candle['close'])
    curr_top = max(curr_candle['open'], curr_candle['close'])
    curr_bot = min(curr_candle['open'], curr_candle['close'])

    # Corpo atual precisa ficar dentro do corpo anterior
    if not (curr_top <= prev_top and curr_bot >= prev_bot):
        return None

    # Bullish harami: prev vermelho e curr verde
    if prev_candle['close'] < prev_candle['open'] and curr_candle['close'] > curr_candle['open']:
        return 'BULLISH_HARAMI'

    # Bearish harami: prev verde e curr vermelho
    if prev_candle['close'] > prev_candle['open'] and curr_candle['close'] < curr_candle['open']:
        return 'BEARISH_HARAMI'

    return None

def is_morning_star(candles, doji_body_pct=0.12):
    """Detecta Morning Star (reversão bullish) em 3 velas."""
    if len(candles) < 3:
        return False
    a, b, c = candles[-3:]
    # 1) queda (vermelha)
    if not (a['close'] < a['open']):
        return False
    # 2) indecisão (doji/pequena)
    if not is_doji(b, max_body_pct=doji_body_pct):
        return False
    # 3) retomada (verde) fechando acima do meio da 1a vela
    mid_a = (a['open'] + a['close']) / 2
    if not (c['close'] > c['open'] and c['close'] > mid_a):
        return False
    return True

def is_evening_star(candles, doji_body_pct=0.12):
    """Detecta Evening Star (reversão bearish) em 3 velas."""
    if len(candles) < 3:
        return False
    a, b, c = candles[-3:]
    # 1) alta (verde)
    if not (a['close'] > a['open']):
        return False
    # 2) indecisão
    if not is_doji(b, max_body_pct=doji_body_pct):
        return False
    # 3) queda (vermelha) fechando abaixo do meio da 1a vela
    mid_a = (a['open'] + a['close']) / 2
    if not (c['close'] < c['open'] and c['close'] < mid_a):
        return False
    return True

def is_pin_bar(candle, direction='any'):
    """
    Detect Pin Bar (Hammer or Shooting Star)
    
    Args:
        candle: Dict with OHLC
        direction: 'bullish' (hammer), 'bearish' (shooting star), or 'any'
    
    Returns:
        str or None: 'HAMMER', 'SHOOTING_STAR', or None
    """
    range_total = candle['high'] - candle['low']
    if range_total == 0:
        return None
    
    body = abs(candle['close'] - candle['open'])
    upper_wick = candle['high'] - max(candle['open'], candle['close'])
    lower_wick = min(candle['open'], candle['close']) - candle['low']
    
    # Body must be small
    if body > 0.35 * range_total:
        return None
    
    # HAMMER (Bullish Pin Bar)
    if direction in ['bullish', 'any']:
        if lower_wick >= 0.55 * range_total and upper_wick <= 0.25 * range_total:
            # Prefer green candle
            if candle['close'] >= candle['open']:
                return 'HAMMER'
    
    # SHOOTING STAR (Bearish Pin Bar)
    if direction in ['bearish', 'any']:
        if upper_wick >= 0.55 * range_total and lower_wick <= 0.25 * range_total:
            # Prefer red candle
            if candle['close'] <= candle['open']:
                return 'SHOOTING_STAR'
    
    return None

def is_engulfing(prev_candle, curr_candle):
    """
    Detect Engulfing Pattern
    
    Returns:
        str or None: 'BULLISH_ENGULFING', 'BEARISH_ENGULFING', or None
    """
    prev_body_top = max(prev_candle['open'], prev_candle['close'])
    prev_body_bot = min(prev_candle['open'], prev_candle['close'])
    
    curr_body_top = max(curr_candle['open'], curr_candle['close'])
    curr_body_bot = min(curr_candle['open'], curr_candle['close'])
    
    # BULLISH ENGULFING
    if curr_candle['close'] > curr_candle['open']:  # Current is green
        if prev_candle['close'] < prev_candle['open']:  # Previous was red
            # Current engulfs previous
            if curr_body_top >= prev_body_top and curr_body_bot <= prev_body_bot:
                return 'BULLISH_ENGULFING'
    
    # BEARISH ENGULFING
    if curr_candle['close'] < curr_candle['open']:  # Current is red
        if prev_candle['close'] > prev_candle['open']:  # Previous was green
            # Current engulfs previous
            if curr_body_top >= prev_body_top and curr_body_bot <= prev_body_bot:
                return 'BEARISH_ENGULFING'
    
    return None

def is_fakeout(zone, candle, direction):
    """
    Detect Fakeout (False Breakout)
    
    Args:
        zone: Dict with 'type', 'upper', 'lower'
        candle: Current candle
        direction: Expected fakeout direction ('support' or 'resistance')
    
    Returns:
        bool: True if fakeout detected
    """
    if direction == 'support':
        # Wick went below zone but closed above
        if candle['low'] < zone['lower'] and candle['close'] > zone['lower']:
            return True
    
    elif direction == 'resistance':
        # Wick went above zone but closed below
        if candle['high'] > zone['upper'] and candle['close'] < zone['upper']:
            return True
    
    return False

def is_inside_bar(prev_candle, curr_candle):
    """
    Detect Inside Bar (compression pattern)
    
    Returns:
        bool: True if inside bar
    """
    if curr_candle['high'] <= prev_candle['high'] and curr_candle['low'] >= prev_candle['low']:
        return True
    return False

def validate_confirmation(pattern_candle, confirmation_candle, pattern_type, direction):
    """
    Validate N+1 confirmation candle
    
    Args:
        pattern_candle: The candle where pattern was detected
        confirmation_candle: The next candle (N+1)
        pattern_type: Type of pattern detected
        direction: Expected direction ('CALL' or 'PUT')
    
    Returns:
        bool: True if confirmed
    """
    if direction == 'CALL':
        # For buy, confirmation must close above pattern high or above midpoint
        pattern_mid = (pattern_candle['high'] + pattern_candle['low']) / 2
        if confirmation_candle['close'] > pattern_candle['high']:
            return True
        if confirmation_candle['close'] > pattern_mid and confirmation_candle['close'] > confirmation_candle['open']:
            return True
    
    elif direction == 'PUT':
        # For sell, confirmation must close below pattern low or below midpoint
        pattern_mid = (pattern_candle['high'] + pattern_candle['low']) / 2
        if confirmation_candle['close'] < pattern_candle['low']:
            return True
        if confirmation_candle['close'] < pattern_mid and confirmation_candle['close'] < confirmation_candle['open']:
            return True
    
    return False

# --- Continuation & Extended Patterns ---
def is_marubozu(candle, direction='any'):
    """Detecta Marubozu (corpo cheio com pavios pequenos)."""
    range_total = candle['high'] - candle['low']
    if range_total <= 0:
        return False
    body = abs(candle['close'] - candle['open'])
    upper_wick = candle['high'] - max(candle['open'], candle['close'])
    lower_wick = min(candle['open'], candle['close']) - candle['low']
    is_solid = body > 0.7 * range_total
    small_wicks = upper_wick < 0.15 * range_total and lower_wick < 0.15 * range_total
    is_bull = candle['close'] > candle['open']
    is_bear = candle['close'] < candle['open']
    if direction in ['bullish', 'any'] and is_bull:
        return is_solid and small_wicks
    if direction in ['bearish', 'any'] and is_bear:
        return is_solid and small_wicks
    return False

def is_three_white_soldiers(candles):
    """Detecta 'Three White Soldiers' nas 3 ultimas velas."""
    if len(candles) < 3:
        return False
    c1, c2, c3 = candles[-3:]
    if not (c1['close'] > c1['open'] and c2['close'] > c2['open'] and c3['close'] > c3['open']):
        return False
    return (c1['close'] < c2['close'] < c3['close'])

def is_three_black_crows(candles):
    """Detecta 'Three Black Crows' nas 3 ultimas velas."""
    if len(candles) < 3:
        return False
    c1, c2, c3 = candles[-3:]
    if not (c1['close'] < c1['open'] and c2['close'] < c2['open'] and c3['close'] < c3['open']):
        return False
    return (c1['close'] > c2['close'] > c3['close'])

def is_rising_three_methods(candles):
    """Padrão de continuidade: alta com 3 velas pequenas de correção dentro do range da vela inicial."""
    if len(candles) < 5:
        return False
    a, b, c, d, e = candles[-5:]
    if not (a['close'] > a['open'] and e['close'] > e['open']):
        return False
    a_high, a_low = a['high'], a['low']
    corrections = [b, c, d]
    inside = all(x['high'] <= a_high and x['low'] >= a_low for x in corrections)
    small_bodies = all(abs(x['close'] - x['open']) < (a['high'] - a['low']) * 0.6 for x in corrections)
    continuation = e['close'] > a['close']
    return inside and small_bodies and continuation

def is_falling_three_methods(candles):
    """Padrão de continuidade: baixa com 3 velas pequenas de correção dentro do range da vela inicial."""
    if len(candles) < 5:
        return False
    a, b, c, d, e = candles[-5:]
    if not (a['close'] < a['open'] and e['close'] < e['open']):
        return False
    a_high, a_low = a['high'], a['low']
    corrections = [b, c, d]
    inside = all(x['high'] <= a_high and x['low'] >= a_low for x in corrections)
    small_bodies = all(abs(x['close'] - x['open']) < (a['high'] - a['low']) * 0.6 for x in corrections)
    continuation = e['close'] < a['close']
    return inside and small_bodies and continuation

def classify_continuation(candles):
    """Classifica padrao de continuidade recente.
    Retorna str ou None: 'BULLISH_MARUBOZU', 'THREE_SOLDIERS', 'RISING_THREE_METHODS',
    'BEARISH_MARUBOZU', 'THREE_CROWS', 'FALLING_THREE_METHODS'.
    """
    if len(candles) < 3:
        return None
    curr = candles[-1]
    if is_marubozu(curr, 'bullish'):
        return 'BULLISH_MARUBOZU'
    if is_marubozu(curr, 'bearish'):
        return 'BEARISH_MARUBOZU'
    if is_three_white_soldiers(candles):
        return 'THREE_SOLDIERS'
    if is_three_black_crows(candles):
        return 'THREE_CROWS'
    if is_rising_three_methods(candles):
        return 'RISING_THREE_METHODS'
    if is_falling_three_methods(candles):
        return 'FALLING_THREE_METHODS'
    return None
