# utils/indicators.py
import pandas as pd
import numpy as np

def calculate_sma(candles, period):
    """Calculates Simple Moving Average."""
    closes = [c['close'] for c in candles]
    return pd.Series(closes).rolling(window=period).mean().iloc[-1]

def calculate_ema(candles, period):
    """Calculates Exponential Moving Average."""
    if not candles or len(candles) < period:
        return 0.0
    closes = [c['close'] for c in candles]
    ema = pd.Series(closes).ewm(span=period, adjust=False).mean().iloc[-1]
    return ema if not pd.isna(ema) else 0.0

def calculate_atr(candles, period):
    """Calculates Average True Range."""
    if not candles or len(candles) < period:
        return 0.0001
        
    df = pd.DataFrame(candles)
    # Ensure columns exist
    if 'high' not in df or 'low' not in df or 'close' not in df:
        return 0.0001
        
    df['high-low'] = df['high'] - df['low']
    df['high-close'] = np.abs(df['high'] - df['close'].shift())
    df['low-close'] = np.abs(df['low'] - df['close'].shift())
    df['tr'] = df[['high-low', 'high-close', 'low-close']].max(axis=1)
    
    val = df['tr'].rolling(window=period).mean().iloc[-1]
    return val if not pd.isna(val) else 0.0001

def calculate_adx(candles, period=14):
    """Calculates Average Directional Index (ADX)."""
    if not candles or len(candles) < (period * 2):
        return 0.0
        
    df = pd.DataFrame(candles)
    if 'high' not in df or 'low' not in df or 'close' not in df:
        return 0.0
        
    # Calculate TR
    df['high-low'] = df['high'] - df['low']
    df['high-close'] = np.abs(df['high'] - df['close'].shift())
    df['low-close'] = np.abs(df['low'] - df['close'].shift())
    df['tr'] = df[['high-low', 'high-close', 'low-close']].max(axis=1)
    
    # Calculate +DM and -DM
    df['up_move'] = df['high'] - df['high'].shift()
    df['down_move'] = df['low'].shift() - df['low']
    
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    
    # Smooth TR, +DM, -DM (Wilder's Smoothing)
    # Using ewm with alpha=1/period is equivalent to Wilder's smoothing
    df['tr_smooth'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
    df['plus_dm_smooth'] = df['plus_dm'].ewm(alpha=1/period, adjust=False).mean()
    df['minus_dm_smooth'] = df['minus_dm'].ewm(alpha=1/period, adjust=False).mean()
    
    # Calculate +DI and -DI
    df['plus_di'] = 100 * (df['plus_dm_smooth'] / df['tr_smooth'])
    df['minus_di'] = 100 * (df['minus_dm_smooth'] / df['tr_smooth'])
    
    # Calculate DX
    df['dx'] = 100 * np.abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
    
    # Calculate ADX (Smooth DX)
    df['adx'] = df['dx'].ewm(alpha=1/period, adjust=False).mean()
    
    val = df['adx'].iloc[-1]
    return val if not pd.isna(val) else 0.0

def identify_pattern(candles):
    """Identifies basic patterns like Hammer, Shooting Star, Engulfing."""
    last = candles[-1]
    prev = candles[-2]
    
    body_size = abs(last['close'] - last['open'])
    upper_wick = last['high'] - max(last['close'], last['open'])
    lower_wick = min(last['close'], last['open']) - last['low']
    
    pattern = None
    
    # Hammer
    if lower_wick > 2 * body_size and upper_wick < body_size * 0.5:
        pattern = "HAMMER" if last['close'] > last['open'] else "INVERTED_HAMMER" # Simplified
        
    # Engulfing
    if last['close'] > last['open'] and prev['close'] < prev['open']:
        if last['close'] > prev['open'] and last['open'] < prev['close']:
            pattern = "BULLISH_ENGULFING"
            
    if last['close'] < last['open'] and prev['close'] > prev['open']:
        if last['close'] < prev['open'] and last['open'] > prev['close']:
            pattern = "BEARISH_ENGULFING"
            
    return pattern

def detect_snr_zones(candles, depth=20):
    """Simple Support/Resistance detection based on local min/max."""
    df = pd.DataFrame(candles)
    _ = df['high'].rolling(window=depth, center=True).max()
    _ = df['low'].rolling(window=depth, center=True).min()
    
    zones = []
    # Logic to extract unique levels causing turns
    # Simplified for this stage
    return zones

def calculate_rsi(candles, period=14):
    """Calculates Relative Strength Index (RSI)."""
    if not candles or len(candles) < period + 1:
        return 50.0  # Default neutral
    
    closes = [c['close'] for c in candles]
    df = pd.DataFrame({'close': closes})
    
    # Calculate price changes
    delta = df['close'].diff()
    
    # Separate gains and losses
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    
    # Calculate average gain/loss using EMA (Wilder's method)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    # Calculate RS and RSI with safety check
    # Avoid division by zero/None
    avg_loss_safe = avg_loss.replace(0, 0.0001)
    rs = avg_gain / avg_loss_safe
    rsi = 100 - (100 / (1 + rs))
    
    val = rsi.iloc[-1]
    return val if not pd.isna(val) else 50.0

