# strategies/ferreira_price_action.py
from .base_strategy import BaseStrategy
from utils.advanced_indicators import (
    calculate_macd, detect_swing_highs_lows, get_wick_stats
)


class FerreiraPriceActionStrategy(BaseStrategy):
    """
    Estratégia 8: Price Action Dinâmico (Ferreira Trader)
    
    Setups:
    A) Fluxo de Continuidade - Rompimento de defesa
    B) Entrega Futura - Preenchimento de pavio
    C) Simetria - Reversão em níveis exatos
    
    Filtros: MACD, Fraqueza de velas
    """
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Price Action Dinâmico (Ferreira)"
    
    def check_signal(self, pair, timeframe_str):
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
        
        candles = self.api.get_candles(pair, timeframe, 100)
        if not candles or len(candles) < 50:
            return None, "Dados insuficientes"
        
        # Velas de análise
        v0 = candles[-2]  # Última vela fechada
        v_minus_1 = candles[-3]  # Vela anterior
        
        # Estatísticas
        stats_v0 = get_wick_stats(v0)
        stats_v_minus_1 = get_wick_stats(v_minus_1)
        
        # MACD
        macd_line, signal_line, histogram = calculate_macd(candles[:-1])
        macd_bullish = macd_line > signal_line and histogram > 0
        macd_bearish = macd_line < signal_line and histogram < 0
        
        # Topos e fundos
        swings = detect_swing_highs_lows(candles[:-2], window=5)
        recent_highs = swings["highs"][-20:] if len(swings["highs"]) > 0 else []
        recent_lows = swings["lows"][-20:] if len(swings["lows"]) > 0 else []
        
        signal = None
        desc = ""
        setup_type = None
        
        # === SETUP A: FLUXO DE CONTINUIDADE ===
        is_green_v_minus_1 = v_minus_1['close'] > v_minus_1['open']
        is_red_v_minus_1 = v_minus_1['close'] < v_minus_1['open']
        is_green_v0 = v0['close'] > v0['open']
        is_red_v0 = v0['close'] < v0['open']
        
        # CALL: vela anterior verde + v0 rompe máxima anterior + pavio superior pequeno
        if (is_green_v_minus_1 and 
            v0['close'] > v_minus_1['high'] and 
            stats_v0['upper'] < (stats_v0['body'] * 0.30) and
            macd_bullish):
            signal = "CALL"
            desc = "Setup A: Fluxo de Continuidade ALTA"
            setup_type = "FLOW_UP"
        
        # PUT: vela anterior vermelha + v0 rompe mínima anterior + pavio inferior pequeno
        elif (is_red_v_minus_1 and 
              v0['close'] < v_minus_1['low'] and 
              stats_v0['lower'] < (stats_v0['body'] * 0.30) and
              macd_bearish):
            signal = "PUT"
            desc = "Setup A: Fluxo de Continuidade BAIXA"
            setup_type = "FLOW_DOWN"
        
        # === SETUP B: ENTREGA FUTURA (PREENCHIMENTO DE PAVIO) ===
        if not signal:
            # CALL: Pavio inferior grande em v_minus_1 + v0 verde preenchendo
            if (stats_v_minus_1['lower'] > stats_v_minus_1['body'] and
                is_green_v0 and
                v0['close'] > (v_minus_1['low'] + stats_v_minus_1['lower'] * 0.50) and
                macd_bullish):
                signal = "CALL"
                desc = "Setup B: Entrega Futura (Preenchimento Pavio BAIXO)"
                setup_type = "WICK_FILL_UP"
            
            # PUT: Pavio superior grande em v_minus_1 + v0 vermelha preenchendo
            elif (stats_v_minus_1['upper'] > stats_v_minus_1['body'] and
                  is_red_v0 and
                  v0['close'] < (v_minus_1['high'] - stats_v_minus_1['upper'] * 0.50) and
                  macd_bearish):
                signal = "PUT"
                desc = "Setup B: Entrega Futura (Preenchimento Pavio ALTO)"
                setup_type = "WICK_FILL_DOWN"
        
        # === SETUP C: SIMETRIA (REVERSÃO EM NÍVEIS EXATOS) ===
        if not signal:
            tolerance = 0.00002
            
            # Verificar se v0 fechou em nível de topo anterior (PUT)
            for high in recent_highs:
                if abs(v0['close'] - high) <= tolerance or abs(v0['open'] - high) <= tolerance:
                    # Confirmar fraqueza: corpo menor que anterior
                    if stats_v0['body'] < stats_v_minus_1['body']:
                        signal = "PUT"
                        desc = f"Setup C: Simetria - Reversão em TOPO ({high:.5f})"
                        setup_type = "SYMMETRY_TOP"
                        break
            
            # Verificar se v0 fechou em nível de fundo anterior (CALL)
            if not signal:
                for low in recent_lows:
                    if abs(v0['close'] - low) <= tolerance or abs(v0['open'] - low) <= tolerance:
                        if stats_v0['body'] < stats_v_minus_1['body']:
                            signal = "CALL"
                            desc = f"Setup C: Simetria - Reversão em FUNDO ({low:.5f})"
                            setup_type = "SYMMETRY_BOTTOM"
                            break
        
        # === FILTRO DE FRAQUEZA/BLOQUEIO ===
        if signal:
            # Bloquear se corpo diminuiu E pavio de rejeição aumentou
            corpo_diminuiu = stats_v0['body'] < stats_v_minus_1['body']
            pavio_rejeicao_v0 = stats_v0['upper'] if signal == "PUT" else stats_v0['lower']
            pavio_rejeicao_v_minus_1 = stats_v_minus_1['upper'] if signal == "PUT" else stats_v_minus_1['lower']
            
            if corpo_diminuiu and pavio_rejeicao_v0 > pavio_rejeicao_v_minus_1:
                return None, "Filtro: Exaustão/Perda de força"
        
        # === VALIDAÇÃO COM IA (OBRIGATÓRIA) ===
        if signal and self.ai_analyzer:
            try:
                # Contexto para IA
                trend_context = {
                    "macd_bullish": macd_bullish,
                    "macd_bearish": macd_bearish,
                    "setup": setup_type,
                    "pattern": desc
                }
                
                zones = {
                    "resistance": [{"level": h, "touches": 1} for h in recent_highs[-5:]],
                    "support": [{"level": low_level, "touches": 1} for low_level in recent_lows[-5:]]
                }
                
                should_trade, confidence, ai_reason = self.validate_with_ai(
                    signal, desc, candles, zones, trend_context, pair
                )
                
                if not should_trade:
                    return None, f"🤖-❌ IA bloqueou: {ai_reason[:30]}"
                
                desc = f"{desc} | 🤖✓{confidence}%"
            except Exception:
                desc = f"{desc} | ⚠️ IA offline"
        
        return signal, desc
