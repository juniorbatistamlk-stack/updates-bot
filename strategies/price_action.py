# strategies/price_action.py
from .base_strategy import BaseStrategy
from utils.indicators import calculate_sma
from utils.sr_zones import detect_swing_highs_lows

class PriceActionStrategy(BaseStrategy):
    """
    ESTRATÉGIA: Price Action Reversal Master
    
    Lógica:
    1. Foca puramente em padrões de reversão clássicos do Price Action.
    2. Mapeia Topos e Fundos (Swing Highs/Lows) como zonas de interesse.
    3. Entra em operações DEPOIS que o preço testa a zona e rejeita:
       - Martelo/Shooting Star (Rejeição clara).
       - Engolfo (Mudança de força dominante).
    4. Filtra operações contra a tendência principal (SMA 50).
    """
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Price Action Reversal Master 1.0"
        
    def check_signal(self, pair, timeframe_str):
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
            
        lookback = 100
        candles = self.api.get_candles(pair, timeframe, lookback)
        if not candles or len(candles) < 50:
            return None, "Aguardando dados..."

        current = candles[-2] # Vela sinal (fechada)
        prev = candles[-3]
        
        # === 1. FILTRO DE CONTEXTO (Macro Trend) ===
        # "Só operar compra se estrutura macro for de alta"
        
        # Simple Trend Filter with SMA 50 derived from Highs/Lows structure ideally, 
        # but User asked for "Topos e Fundos Ascendentes". 
        # Let's use a simpler proxy: Price > SMA50 AND SMA20 > SMA50
        
        sma50 = calculate_sma(candles[:-1], 50)
        
        trend = 'NEUTRAL'
        if not sma50:
            pass
        else:
            if current['close'] > sma50:
                trend = 'BULLISH'
            elif current['close'] < sma50:
                trend = 'BEARISH'
                
        # === 2. DETECTAR ZONAS (Fractais) ===
        swings = detect_swing_highs_lows(candles[:-1], window=5)
        
        # === 3. PADRÕES GATILHO ===
        signal = None
        desc = ""
        
        body_size = abs(current['close'] - current['open'])
        upper_wick = current['high'] - max(current['open'], current['close'])
        lower_wick = min(current['open'], current['close']) - current['low']
        total_size = current['high'] - current['low']
        
        if total_size == 0:
            return None, "Doji Zero"
        
        # A. MARTELO (Bullish Reversal)
        # - Pavio inferior >= 2x corpo
        # - Pavio superior pequeno
        # - Zona Suporte
        is_hammer = (lower_wick >= 2.0 * body_size) and \
                    (upper_wick <= body_size * 0.5) and \
                    (body_size > total_size * 0.1) # Not a doji
                    
        if is_hammer and trend == 'BULLISH':
            # Check Support validity
            if self.is_near_support(current['low'], swings['lows']):
                signal = "CALL"
                desc = "🔨 MARTELO em Suporte (Trend Alta)"

        # B. ESTRELA CADENTE (Bearish Reversal)
        # - Pavio superior >= 2x corpo
        # - Pavio inferior pequeno
        # - Zona Resistência
        is_shooting_star = (upper_wick >= 2.0 * body_size) and \
                           (lower_wick <= body_size * 0.5) and \
                           (body_size > total_size * 0.1)
                           
        if is_shooting_star and trend == 'BEARISH':
            # Check Resistance validity
            if self.is_near_resistance(current['high'], swings['highs']):
                signal = "PUT"
                desc = "🌠 ESTRELA CADENTE em Resistência (Trend Baixa)"

        # C. ENGOLFO DE ALTA
        # - Vela anterior negativa, Atual positiva
        # - Corpo atual "engole" corpo anterior
        is_engolfo_alta = (prev['close'] < prev['open']) and \
                          (current['close'] > current['open']) and \
                          (current['close'] > prev['open']) and \
                          (current['open'] < prev['close'])
                          
        if is_engolfo_alta and trend == 'BULLISH':
            # Check Support
            if self.is_near_support(current['low'], swings['lows']):
                signal = "CALL"
                desc = "🔥 ENGOLFO DE ALTA"

        # D. ENGOLFO DE BAIXA
        is_engolfo_baixa = (prev['close'] > prev['open']) and \
                           (current['close'] < current['open']) and \
                           (current['close'] < prev['open']) and \
                           (current['open'] > prev['close'])
                           
        if is_engolfo_baixa and trend == 'BEARISH':
            # Check Resistance
            if self.is_near_resistance(current['high'], swings['highs']):
                signal = "PUT"
                desc = "❄️ ENGOLFO DE BAIXA"

        # === 4. DOJI FILTER ===
        # "Abertura e fechamento quase iguais"
        if body_size <= (total_size * 0.1):
            return None, "Doji (Indecisão) - Validando..."
            
        # 🤖 VALIDAÇÃO IA
        if signal and self.ai_analyzer:
            try:
                zones = {"support": [], "resistance": []}
                trend_data = {"trend": "NEUTRAL", "setup": "REVERSAL", "pattern": desc[:20]}
                should_trade, confidence, ai_reason = self.validate_with_ai(signal, desc, candles, zones, trend_data, pair)
                if not should_trade:
                    return None, f"🤖-❌ IA bloqueou: {ai_reason[:30]}... ({confidence}%)"
                desc = f"{desc} | 🤖✓{confidence}%"
            except Exception:
                desc = f"{desc} | ⚠️ IA offline"
        return signal, desc

    def is_near_support(self, price, swing_lows, tolerance=0.00015):
        # swing_lows is list of (index, price)
        for _, level in swing_lows:
            if abs(level - price) <= tolerance:
                return True
        return False

    def is_near_resistance(self, price, swing_highs, tolerance=0.00015):
        for _, level in swing_highs:
            if abs(level - price) <= tolerance:
                return True
        return False
