# utils/sr_zones.py
"""
Support and Resistance Zone Detection
Detects swing highs/lows and creates zones for Price Action validation
"""

def detect_swing_highs_lows(candles, window=3):
    """
    Detect swing highs and lows using fractal method
    
    Args:
        candles: List of candle dicts with OHLC
        window: Number of candles on each side to confirm swing
    
    Returns:
        dict: {'highs': [(index, price)], 'lows': [(index, price)]}
    """
    swings = {'highs': [], 'lows': []}
    
    if len(candles) < (window * 2 + 1):
        return swings
    
    # Start from window and go to len-window
    for i in range(window, len(candles) - window):
        current = candles[i]
        
        # Check if it's a swing high
        is_swing_high = True
        for j in range(1, window + 1):
            if candles[i - j]['high'] >= current['high'] or candles[i + j]['high'] >= current['high']:
                is_swing_high = False
                break
        
        if is_swing_high:
            swings['highs'].append((i, current['high']))
        
        # Check if it's a swing low
        is_swing_low = True
        for j in range(1, window + 1):
            if candles[i - j]['low'] <= current['low'] or candles[i + j]['low'] <= current['low']:
                is_swing_low = False
                break
        
        if is_swing_low:
            swings['lows'].append((i, current['low']))
    
    return swings

def create_sr_zones(swings, tolerance, max_zones=5):
    """
    Create S/R zones from swing points
    
    Args:
        swings: Output from detect_swing_highs_lows
        tolerance: Price tolerance for zone (e.g., ATR * 0.5)
        max_zones: Maximum number of zones to keep (most recent)
    
    Returns:
        list: [{'type': 'resistance', 'price': x, 'touches': n}, ...]
    """
    zones = []
    
    # Process resistance zones (swing highs)
    recent_highs = swings['highs'][-max_zones:] if len(swings['highs']) > max_zones else swings['highs']
    for idx, price in recent_highs:
        zones.append({
            'type': 'resistance',
            'price': price,
            'upper': price + tolerance,
            'lower': price - tolerance,
            'touches': 1
        })
    
    # Process support zones (swing lows)
    recent_lows = swings['lows'][-max_zones:] if len(swings['lows']) > max_zones else swings['lows']
    for idx, price in recent_lows:
        zones.append({
            'type': 'support',
            'price': price,
            'upper': price + tolerance,
            'lower': price - tolerance,
            'touches': 1
        })
    
    # Merge nearby zones (cluster detection)
    zones = merge_nearby_zones(zones, tolerance * 2)
    
    return zones

def merge_nearby_zones(zones, merge_distance):
    """Merge zones that are very close to each other"""
    if len(zones) <= 1:
        return zones
    
    merged = []
    zones_sorted = sorted(zones, key=lambda z: z['price'])
    
    current_zone = zones_sorted[0].copy()
    
    for i in range(1, len(zones_sorted)):
        next_zone = zones_sorted[i]
        
        # If same type and close enough, merge
        if current_zone['type'] == next_zone['type'] and abs(current_zone['price'] - next_zone['price']) < merge_distance:
            # Average the prices
            current_zone['price'] = (current_zone['price'] + next_zone['price']) / 2
            current_zone['touches'] += next_zone['touches']
            current_zone['upper'] = current_zone['price'] + merge_distance / 2
            current_zone['lower'] = current_zone['price'] - merge_distance / 2
        else:
            merged.append(current_zone)
            current_zone = next_zone.copy()
    
    merged.append(current_zone)
    return merged

def is_near_zone(price, zones, direction=None):
    """
    Check if price is near a S/R zone
    
    Args:
        price: Current price
        zones: List of zone dicts
        direction: 'support' or 'resistance' to filter, None for any
    
    Returns:
        dict or None: The zone if near, None otherwise
    """
    for zone in zones:
        if direction and zone['type'] != direction:
            continue
        
        if zone['lower'] <= price <= zone['upper']:
            return zone
    
    return None

def detect_trend_structure(candles, min_swings=2):
    """
    Detect trend based on swing structure
    
    Returns:
        str: 'BULLISH', 'BEARISH', or 'LATERAL'
    """
    swings = detect_swing_highs_lows(candles, window=3)
    
    if len(swings['highs']) < min_swings or len(swings['lows']) < min_swings:
        return 'LATERAL'
    
    # Get last 3 swings
    recent_highs = swings['highs'][-3:]
    recent_lows = swings['lows'][-3:]
    
    # Check if highs are ascending
    highs_ascending = all(recent_highs[i][1] < recent_highs[i+1][1] for i in range(len(recent_highs)-1))
    # Check if lows are ascending
    lows_ascending = all(recent_lows[i][1] < recent_lows[i+1][1] for i in range(len(recent_lows)-1))
    
    # Check if highs are descending
    highs_descending = all(recent_highs[i][1] > recent_highs[i+1][1] for i in range(len(recent_highs)-1))
    # Check if lows are descending
    lows_descending = all(recent_lows[i][1] > recent_lows[i+1][1] for i in range(len(recent_lows)-1))
    
    if highs_ascending and lows_ascending:
        return 'BULLISH'
    elif highs_descending and lows_descending:
        return 'BEARISH'
    else:
        return 'LATERAL'
