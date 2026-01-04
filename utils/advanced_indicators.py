# utils/advanced_indicators.py
"""
Advanced Technical Indicators and Pattern Detection
Used by Ferreira-based strategies
"""
import numpy as np
from typing import List, Dict, Tuple, Optional


def calculate_macd(candles: List[dict], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
    """
    Calcula MACD (Moving Average Convergence Divergence)
    
    Returns:
        (macd_line, signal_line, histogram)
    """
    if len(candles) < slow + signal:
        return 0.0, 0.0, 0.0
    
    closes = np.array([c['close'] for c in candles])
    
    # EMA rápida e lenta
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    
    # Linha MACD
    macd_line = ema_fast - ema_slow
    
    # Linha de sinal (EMA do MACD)
    signal_line = _ema(macd_line, signal)
    
    # Histograma
    histogram = macd_line - signal_line
    
    return float(macd_line[-1]), float(signal_line[-1]), float(histogram[-1])


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Calcula EMA (Exponential Moving Average)"""
    alpha = 2 / (period + 1)
    ema = np.zeros_like(data)
    ema[0] = data[0]
    
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
    
    return ema


def detect_swing_highs_lows(candles: List[dict], window: int = 5) -> Dict[str, List[float]]:
    """
    Detecta topos (swing highs) e fundos (swing lows)
    
    Args:
        candles: Lista de velas
        window: Janela de comparação (ex: 5 velas antes e depois)
    
    Returns:
        {"highs": [...], "lows": [...]}
    """
    highs = []
    lows = []
    
    for i in range(window, len(candles) - window):
        current_high = candles[i]['high']
        current_low = candles[i]['low']
        
        # Verificar se é swing high
        is_swing_high = True
        for j in range(i - window, i + window + 1):
            if j != i and candles[j]['high'] >= current_high:
                is_swing_high = False
                break
        
        if is_swing_high:
            highs.append(current_high)
        
        # Verificar se é swing low
        is_swing_low = True
        for j in range(i - window, i + window + 1):
            if j != i and candles[j]['low'] <= current_low:
                is_swing_low = False
                break
        
        if is_swing_low:
            lows.append(current_low)
    
    return {"highs": highs, "lows": lows}


def detect_symmetry(candle: dict, reference_candles: List[dict], tolerance: float = 0.00002) -> Optional[Dict]:
    """
    Detecta simetria entre a vela atual e velas anteriores
    
    Args:
        candle: Vela atual
        reference_candles: Velas de referência (últimas 20-50)
        tolerance: Tolerância de alinhamento (pips)
    
    Returns:
        {"type": "body"|"wick", "level": float, "strength": int} ou None
    """
    current_close = candle['close']
    current_high = candle['high']
    current_low = candle['low']
    
    body_symmetries = []
    wick_symmetries = []
    
    for ref in reference_candles:
        # Simetria de corpo
        if abs(current_close - ref['close']) <= tolerance:
            body_symmetries.append(ref['close'])
        if abs(current_close - ref['open']) <= tolerance:
            body_symmetries.append(ref['open'])
        
        # Simetria de pavio
        if abs(current_high - ref['high']) <= tolerance:
            wick_symmetries.append(ref['high'])
        if abs(current_low - ref['low']) <= tolerance:
            wick_symmetries.append(ref['low'])
    
    if len(body_symmetries) >= 2:
        return {
            "type": "body",
            "level": current_close,
            "strength": len(body_symmetries)
        }
    
    if len(wick_symmetries) >= 2:
        return {
            "type": "wick",
            "level": current_high if current_high in wick_symmetries else current_low,
            "strength": len(wick_symmetries)
        }
    
    return None


def detect_price_lots(candles: List[dict], min_lot_size: int = 2) -> List[Dict]:
    """
    Detecta lotes de preço (sequências de velas da mesma cor)
    
    Args:
        candles: Lista de velas
        min_lot_size: Tamanho mínimo do lote
    
    Returns:
        Lista de lotes: [{"start": idx, "end": idx, "type": "bull"|"bear", "first_candle": {...}, "last_candle": {...}}]
    """
    lots = []
    current_lot = None
    
    for i, candle in enumerate(candles):
        is_green = candle['close'] > candle['open']
        
        if current_lot is None:
            current_lot = {
                "start": i,
                "type": "bull" if is_green else "bear",
                "candles": [candle]
            }
        else:
            lot_is_bull = current_lot["type"] == "bull"
            same_direction = (is_green and lot_is_bull) or (not is_green and not lot_is_bull)
            
            if same_direction:
                current_lot["candles"].append(candle)
            else:
                # Finalizar lote anterior
                if len(current_lot["candles"]) >= min_lot_size:
                    lots.append({
                        "start": current_lot["start"],
                        "end": i - 1,
                        "type": current_lot["type"],
                        "first_candle": current_lot["candles"][0],
                        "last_candle": current_lot["candles"][-1],
                        "size": len(current_lot["candles"])
                    })
                
                # Iniciar novo lote
                current_lot = {
                    "start": i,
                    "type": "bull" if is_green else "bear",
                    "candles": [candle]
                }
    
    # Finalizar último lote
    if current_lot and len(current_lot["candles"]) >= min_lot_size:
        lots.append({
            "start": current_lot["start"],
            "end": len(candles) - 1,
            "type": current_lot["type"],
            "first_candle": current_lot["candles"][0],
            "last_candle": current_lot["candles"][-1],
            "size": len(current_lot["candles"])
        })
    
    return lots


def is_comando_candle(candle: dict, tolerance: float = 0.00001) -> str:
    """
    Verifica se a vela é um "Comando" (sem pavio na abertura)
    
    Returns:
        "BULL" se comando de alta, "BEAR" se comando de baixa, "" se não é comando
    """
    body_size = abs(candle['close'] - candle['open'])
    if body_size == 0:
        return ""
    
    is_green = candle['close'] > candle['open']
    
    if is_green:
        # Comando de alta: open próximo ao low
        if abs(candle['open'] - candle['low']) <= tolerance:
            return "BULL"
    else:
        # Comando de baixa: open próximo ao high
        if abs(candle['open'] - candle['high']) <= tolerance:
            return "BEAR"
    
    return ""


def is_force_candle(candle: dict, avg_body: float, multiplier: float = 1.5) -> bool:
    """
    Verifica se é uma Vela de Força (corpo grande)
    
    Args:
        candle: Vela a verificar
        avg_body: Média do tamanho dos corpos recentes
        multiplier: Multiplicador (ex: 1.5x maior que a média)
    """
    body = abs(candle['close'] - candle['open'])
    return body > (avg_body * multiplier)


def calculate_average_body(candles: List[dict], period: int = 10) -> float:
    """Calcula média do tamanho dos corpos das últimas N velas"""
    if len(candles) < period:
        period = len(candles)
    
    bodies = [abs(c['close'] - c['open']) for c in candles[-period:]]
    return sum(bodies) / len(bodies) if bodies else 0.0


def get_wick_stats(candle: dict) -> Dict[str, float]:
    """
    Retorna estatísticas dos pavios da vela
    
    Returns:
        {"upper": float, "lower": float, "body": float, "total_range": float}
    """
    body = abs(candle['close'] - candle['open'])
    upper_wick = candle['high'] - max(candle['open'], candle['close'])
    lower_wick = min(candle['open'], candle['close']) - candle['low']
    total_range = candle['high'] - candle['low']
    
    return {
        "upper": upper_wick,
        "lower": lower_wick,
        "body": body,
        "total_range": total_range
    }
