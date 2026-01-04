# strategies/ferreira_moving_avg.py
from .base_strategy import BaseStrategy
from utils.indicators import calculate_sma
from utils.advanced_indicators import is_force_candle, calculate_average_body
import numpy as np


class FerreiraMovingAvgStrategy(BaseStrategy):
    """
    Estratégia 10: Médias Móveis (Ferreira Trader)
    
    Lógica: Cruzamento EMA 5 x SMA 20 + Vela de Impulsão + Pullback
    
    Gatilhos:
    - CALL: EMA 5 cruza acima SMA 20 + vela verde forte + pullback
    - PUT: EMA 5 cruza abaixo SMA 20 + vela vermelha forte + pullback
    """
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Médias Móveis (Ferreira)"
    
    def check_signal(self, pair, timeframe_str):
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
        
        candles = self.api.get_candles(pair, timeframe, 60)
        if not candles or len(candles) < 30:
            return None, "Dados insuficientes"
        
        # Calcular médias
        closes = [c['close'] for c in candles[:-1]]
        ema5 = self._calculate_ema(closes, 5)
        sma20 = calculate_sma(candles[:-1], 20)
        
        if not ema5 or not sma20:
            return None, "Calculando médias..."
        
        # Velas de análise
        v0 = candles[-2]
        
        avg_body = calculate_average_body(candles[:-2], 10)
        
        # Estado das médias
        ema5_current = ema5[-1]
        ema5_prev = ema5[-2]
        
        # Detectar cruzamento
        crossed_up = ema5_prev <= sma20 and ema5_current > sma20
        crossed_down = ema5_prev >= sma20 and ema5_current < sma20
        
        signal = None
        desc = ""
        setup_type = None
        
        is_green_v0 = v0['close'] > v0['open']
        is_red_v0 = v0['close'] < v0['open']
        
        # === SINAL DE COMPRA (CALL) ===
        if crossed_up:
            # Verificar vela de impulsão (corpo expressivo)
            if is_green_v0 and is_force_candle(v0, avg_body, 1.2):
                # Verificar se não está em resistência imediata
                recent_highs = [c['high'] for c in candles[-20:-2]]
                max_recent = max(recent_highs) if recent_highs else v0['high']
                
                # Espaço para caminhar (não travado em resistência)
                if v0['close'] < max_recent * 0.998:  # Pelo menos 0.2% de espaço
                    signal = "CALL"
                    desc = "Cruzamento ALTA EMA5 > SMA20"
                    setup_type = "CROSS_UP"
        
        # === SINAL DE VENDA (PUT) ===
        elif crossed_down:
            # Verificar vela de impulsão
            if is_red_v0 and is_force_candle(v0, avg_body, 1.2):
                # Verificar se não está em suporte imediato
                recent_lows = [c['low'] for c in candles[-20:-2]]
                min_recent = min(recent_lows) if recent_lows else v0['low']
                
                # Espaço para caminhar
                if v0['close'] > min_recent * 1.002:  # Pelo menos 0.2% de espaço
                    signal = "PUT"
                    desc = "Cruzamento BAIXA EMA5 < SMA20"
                    setup_type = "CROSS_DOWN"
        
        # === ENTRADA EM PULLBACK (se já cruzou antes) ===
        if not signal:
            # Se EMA5 está acima SMA20 mas preço voltou à média (pullback)
            if ema5_current > sma20:
                # Preço tocou ou chegou próximo da EMA5
                if (abs(v0['low'] - ema5_current) <= ema5_current * 0.001 and
                    is_green_v0):
                    signal = "CALL"
                    desc = "Pullback na EMA5 (Tendência ALTA)"
                    setup_type = "PULLBACK_UP"
            
            # Se EMA5 está abaixo SMA20 mas preço voltou à média
            elif ema5_current < sma20:
                if (abs(v0['high'] - ema5_current) <= ema5_current * 0.001 and
                    is_red_v0):
                    signal = "PUT"
                    desc = "Pullback na EMA5 (Tendência BAIXA)"
                    setup_type = "PULLBACK_DOWN"
        
        # === FILTRO: Médias enroladas (mercado lateral) ===
        if signal:
            # Se as médias estão muito próximas, não operar
            if abs(ema5_current - sma20) / sma20 < 0.0005:  # Menos de 0.05% de diferença
                return None, "Mercado lateral (médias enroladas)"
        
        # === VALIDAÇÃO COM IA (OBRIGATÓRIA) ===
        if signal and self.ai_analyzer:
            try:
                trend_context = {
                    "ema5": ema5_current,
                    "sma20": sma20,
                    "setup": setup_type,
                    "trend": "UP" if ema5_current > sma20 else "DOWN"
                }
                
                # Sem zonas SNR específicas (estratégia de médias)
                zones = {"resistance": [], "support": []}
                
                should_trade, confidence, ai_reason = self.validate_with_ai(
                    signal, desc, candles, zones, trend_context, pair
                )
                
                if not should_trade:
                    return None, f"🤖-❌ IA bloqueou: {ai_reason[:30]}"
                
                desc = f"{desc} | 🤖✓{confidence}%"
            except Exception:
                desc = f"{desc} | ⚠️ IA offline"
        
        return signal, desc
    
    def _calculate_ema(self, prices, period):
        """Calcula EMA manualmente"""
        if len(prices) < period:
            return None
        
        prices_arr = np.array(prices)
        alpha = 2 / (period + 1)
        ema = np.zeros_like(prices_arr)
        ema[0] = prices_arr[0]
        
        for i in range(1, len(prices_arr)):
            ema[i] = alpha * prices_arr[i] + (1 - alpha) * ema[i-1]
        
        return ema.tolist()
