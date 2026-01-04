# strategies/ferreira_moving_avg_v2.py
"""
================================================================================
🎯 ESTRATÉGIA FERREIRA - MÉDIAS MÓVEIS V2
================================================================================
Versão revisada baseada no JSON original.

Indicadores:
  - SMA 20 (Roxo) - Filtro de tendência macro / S/R móvel
  - EMA 5 (Verde) - Gatilho de entrada / Acompanhamento de momento

Lógica: Cruzamento + Vela de Impulsão + Pullback + Alvo de Preço

REGRA: "O cruzamento sozinho não basta. É necessário que o candle que cruza 
demonstre INTENÇÃO INSTITUCIONAL (Vela de Impulsão) e que haja ALVO 
(distância segura até a próxima barreira de preço)."
================================================================================
"""

from .base_strategy import BaseStrategy
from utils.advanced_indicators import (
    get_wick_stats, is_force_candle, calculate_average_body,
    detect_swing_highs_lows
)
import numpy as np

# Tentar importar análise de movimentação
try:
    from utils.price_movement_analyzer import movement_analyzer
    MOVEMENT_AVAILABLE = True
except ImportError:
    MOVEMENT_AVAILABLE = False


class FerreiraMovingAvgV2Strategy(BaseStrategy):
    """
    Estratégia Médias Móveis V2 - Revisada
    """
    
    STRATEGY_LOGIC = """
ESTRATÉGIA FERREIRA - MÉDIAS MÓVEIS:

CONFIGURAÇÃO:
- SMA 20 (Roxo): Linha de equilíbrio / S/R móvel
- EMA 5 (Verde): Gatilho de entrada / Momento

FLUXO DE DECISÃO:
1. Identificar CRUZAMENTO das médias (EMA 5 cruza SMA 20)
2. Analisar VELA DE IMPULSÃO (corpo grande = intenção institucional)
3. Verificar ALVO DE PREÇO (distância até próximo S/R)
4. Aguardar CORREÇÃO (ruído) para melhor taxa de entrada
5. EXECUTAR a favor do cruzamento

GATILHO CALL:
- EMA 5 cruza ACIMA da SMA 20
- Vela de rompimento VERDE com corpo expressivo
- Preço NÃO está travado em resistência imediata

GATILHO PUT:
- EMA 5 cruza ABAIXO da SMA 20
- Vela de rompimento VERMELHA com força
- Ausência de suporte imediato

FILTROS DE SEGURANÇA:
- Mercado LATERAL (médias enroladas) = NÃO OPERAR
- Velas com muitos PAVIOS de rejeição = NÃO OPERAR
- S/R FORTE imediato sem espaço = NÃO OPERAR

ENTRADA EM PULLBACK:
- Se já cruzou e preço volta à EMA 5 = Oportunidade de entrada
- Melhor taxa que entrada no cruzamento
"""
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Ferreira Médias Móveis V2"
    
    def check_signal(self, pair, timeframe_str):
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
        
        candles = self.api.get_candles(pair, timeframe, 80)
        if not candles or len(candles) < 55:
            return None, "Dados insuficientes"
        
        # Calcular médias
        closes = [c['close'] for c in candles[:-1]]
        ema5 = self._calculate_ema(closes, 5)
        sma20 = self._calculate_sma(closes, 20)
        
        if not ema5 or not sma20 or len(ema5) < 3:
            return None, "Calculando médias..."
        
        # Velas de análise
        v0 = candles[-2]
        
        stats_v0 = get_wick_stats(v0)
        avg_body = calculate_average_body(candles[:-2], 10)
        
        # Detectar zonas de S/R para verificar alvos
        swings = detect_swing_highs_lows(candles[:-2], window=5)
        recent_highs = [h for h in swings["highs"][-10:]]
        recent_lows = [low_level for low_level in swings["lows"][-10:]]
        
        # Estado das médias
        ema5_current = ema5[-1]
        ema5_prev = ema5[-2]
        sma20_current = sma20[-1]
        sma20_prev = sma20[-2]
        
        # Detectar cruzamento
        crossed_up = ema5_prev <= sma20_prev and ema5_current > sma20_current
        crossed_down = ema5_prev >= sma20_prev and ema5_current < sma20_current
        
        # Tendência atual
        ema_above_sma = ema5_current > sma20_current
        ema_below_sma = ema5_current < sma20_current
        
        signal = None
        desc = ""
        setup_type = None
        
        is_green_v0 = v0['close'] > v0['open']
        is_red_v0 = v0['close'] < v0['open']
        
        # ══════════════════════════════════════════════════════════════════
        # FILTRO PRINCIPAL: Médias Enroladas (Mercado Lateral)
        # ══════════════════════════════════════════════════════════════════
        diff_medias = abs(ema5_current - sma20_current)
        diff_pct = diff_medias / sma20_current if sma20_current > 0 else 0
        
        if diff_pct < 0.0005:  # Menos de 0.05% de diferença
            return None, "⚠️ Mercado lateral (médias enroladas)"
        
        # ══════════════════════════════════════════════════════════════════
        # SINAL DE COMPRA (CALL) - Cruzamento
        # ══════════════════════════════════════════════════════════════════
        if crossed_up:
            # Verificar VELA DE IMPULSÃO (corpo expressivo)
            if is_green_v0 and is_force_candle(v0, avg_body, 1.2):
                
                # Verificar ALVO DE PREÇO (espaço até próxima resistência)
                max_recent = max(recent_highs) if recent_highs else v0['high'] * 1.01
                espaco_disponivel = (max_recent - v0['close']) / v0['close']
                
                # Pelo menos 0.2% de espaço para o preço caminhar
                if espaco_disponivel > 0.002:
                    signal = "CALL"
                    desc = "Cruzamento ALTA (EMA5 > SMA20)"
                    setup_type = "CROSS_UP"
                else:
                    return None, "🚫 Sem alvo (resistência muito próxima)"
        
        # ══════════════════════════════════════════════════════════════════
        # SINAL DE VENDA (PUT) - Cruzamento
        # ══════════════════════════════════════════════════════════════════
        elif crossed_down:
            if is_red_v0 and is_force_candle(v0, avg_body, 1.2):
                
                min_recent = min(recent_lows) if recent_lows else v0['low'] * 0.99
                espaco_disponivel = (v0['close'] - min_recent) / v0['close']
                
                if espaco_disponivel > 0.002:
                    signal = "PUT"
                    desc = "Cruzamento BAIXA (EMA5 < SMA20)"
                    setup_type = "CROSS_DOWN"
                else:
                    return None, "🚫 Sem alvo (suporte muito próximo)"
        
        # ══════════════════════════════════════════════════════════════════
        # ENTRADA EM PULLBACK (se já cruzou antes)
        # ══════════════════════════════════════════════════════════════════
        if not signal:
            # Pullback na ALTA (preço volta à EMA5 em tendência de alta)
            if ema_above_sma:
                # Preço tocou ou chegou próximo da EMA5
                touch_distance = abs(v0['low'] - ema5_current) / ema5_current
                
                if touch_distance <= 0.001 and is_green_v0:
                    # Verificar que não está em exaustão
                    if stats_v0['lower'] < stats_v0['body']:  # Sem pavio de rejeição
                        signal = "CALL"
                        desc = "Pullback EMA5 (Tendência ALTA)"
                        setup_type = "PULLBACK_UP"
            
            # Pullback na BAIXA
            elif ema_below_sma:
                touch_distance = abs(v0['high'] - ema5_current) / ema5_current
                
                if touch_distance <= 0.001 and is_red_v0:
                    if stats_v0['upper'] < stats_v0['body']:
                        signal = "PUT"
                        desc = "Pullback EMA5 (Tendência BAIXA)"
                        setup_type = "PULLBACK_DOWN"
        
        # ══════════════════════════════════════════════════════════════════
        # FILTROS DE SEGURANÇA
        # ══════════════════════════════════════════════════════════════════
        if signal:
            # Filtro: Velas com muitos pavios de rejeição
            pavio_total = stats_v0['upper'] + stats_v0['lower']
            if pavio_total > stats_v0['body'] * 2:
                return None, "🚫 Muita rejeição (pavios grandes)"
            
            # Filtro: Verificar confluência com movimento MACRO
            if MOVEMENT_AVAILABLE:
                try:
                    movement = movement_analyzer.analyze(pair, candles[:-1])
                    
                    # Se Macro está contra, reduzir confiança mas não bloquear
                    if signal == "CALL" and movement.macro.direction.value == "baixa":
                        if movement.macro.trend_strength > 70:
                            return None, "🚫 Macro contra (tendência de baixa forte)"
                    
                    elif signal == "PUT" and movement.macro.direction.value == "alta":
                        if movement.macro.trend_strength > 70:
                            return None, "🚫 Macro contra (tendência de alta forte)"
                except Exception:
                    pass
        
        # ══════════════════════════════════════════════════════════════════
        # VALIDAÇÃO COM IA
        # ══════════════════════════════════════════════════════════════════
        if signal and self.ai_analyzer:
            try:
                trend_context = {
                    "ema5": ema5_current,
                    "sma20": sma20_current,
                    "setup": setup_type,
                    "trend": "UP" if ema_above_sma else "DOWN"
                }
                
                zones = {
                    "resistance": [{"level": h, "touches": 1} for h in recent_highs[-5:]],
                    "support": [{"level": low_level, "touches": 1} for low_level in recent_lows[-5:]]
                }
                
                should_trade, confidence, ai_reason = self.validate_with_ai(
                    signal, desc, candles, zones, trend_context, pair,
                    strategy_logic=self.STRATEGY_LOGIC
                )
                
                if not should_trade:
                    return None, f"🤖❌ {ai_reason[:30]}"
                
                desc = f"{desc} | 🤖✓{confidence}%"
                
            except Exception:
                desc = f"{desc} | ⚠️ IA offline"
        
        return signal, desc
    
    def _calculate_ema(self, prices, period):
        """Calcula EMA"""
        if len(prices) < period:
            return None
        
        prices_arr = np.array(prices)
        alpha = 2 / (period + 1)
        ema = np.zeros_like(prices_arr, dtype=float)
        
        # Primeira EMA é SMA
        ema[period-1] = np.mean(prices_arr[:period])
        
        for i in range(period, len(prices_arr)):
            ema[i] = alpha * prices_arr[i] + (1 - alpha) * ema[i-1]
        
        return ema[period-1:]
    
    def _calculate_sma(self, prices, period):
        """Calcula SMA"""
        if len(prices) < period:
            return None
        
        sma = []
        for i in range(period - 1, len(prices)):
            sma.append(np.mean(prices[i - period + 1:i + 1]))
        
        return sma
