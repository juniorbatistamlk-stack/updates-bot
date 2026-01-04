# strategies/ferreira_price_action_v2.py
"""
================================================================================
🎯 ESTRATÉGIA FERREIRA TRADER - PRICE ACTION DINÂMICO V2
================================================================================
Versão revisada e otimizada baseada no JSON original.

Setups:
  A) Fluxo de Continuidade - Rompimento de defesa
  B) Entrega Futura - Preenchimento de pavio (imã de liquidez)
  C) Simetria - Reversão em níveis exatos de topos/fundos

Filtros:
  - MACD a favor do movimento
  - Fraqueza de velas (exaustão)
  - Pavio de rejeição (defesa forte)

REGRA DE OURO: "O segredo está na REJEIÇÃO. Se a vela atingir uma taxa e 
retrair rapidamente deixando pavio longo, NÃO seguir o fluxo."
================================================================================
"""

from .base_strategy import BaseStrategy
from utils.advanced_indicators import (
    calculate_macd, detect_swing_highs_lows, get_wick_stats
)

# Tentar importar análise de movimentação
try:
    from utils.price_movement_analyzer import movement_analyzer
    MOVEMENT_AVAILABLE = True
except ImportError:
    MOVEMENT_AVAILABLE = False


class FerreiraPriceActionV2Strategy(BaseStrategy):
    """
    Estratégia Ferreira Price Action V2 - Revisada
    """
    
    # Descrição da lógica para a IA
    STRATEGY_LOGIC = """
ESTRATÉGIA FERREIRA - PRICE ACTION DINÂMICO:

SETUP A - FLUXO DE CONTINUIDADE (Rompimento de Defesa):
- CALL: Vela anterior VERDE + Vela atual fecha ACIMA da máxima anterior + Pavio superior < 30% do corpo
- PUT: Vela anterior VERMELHA + Vela atual fecha ABAIXO da mínima anterior + Pavio inferior < 30% do corpo
- MACD deve confirmar a direção

SETUP B - ENTREGA FUTURA (Preenchimento de Pavio):
- Pavios longos funcionam como IMÃS de liquidez
- Se pavio > corpo da vela anterior, preço tende a preencher
- Entrada a favor do preenchimento + MACD confirmando

SETUP C - SIMETRIA (Reversão):
- Quando preço fecha em nível EXATO de topo/fundo anterior (tolerância 2 pips)
- Vela atual deve ter CORPO MENOR que a anterior (fraqueza)
- Entrada CONTRA a cor da vela atual

FILTRO DE REJEIÇÃO (BLOQUEIO):
- Se corpo diminuiu E pavio de rejeição aumentou = EXAUSTÃO = NÃO ENTRAR
- Pavio longo = defesa forte do lado oposto
"""
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Ferreira Price Action V2"
    
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
        
        # Estatísticas das velas
        stats_v0 = get_wick_stats(v0)
        stats_v_minus_1 = get_wick_stats(v_minus_1)
        
        # MACD
        macd_line, signal_line, histogram = calculate_macd(candles[:-1])
        macd_bullish = macd_line > signal_line and histogram > 0
        macd_bearish = macd_line < signal_line and histogram < 0
        
        # Histórico de topos/fundos (últimos 20)
        swings = detect_swing_highs_lows(candles[:-2], window=5)
        recent_highs = swings["highs"][-20:] if len(swings["highs"]) > 0 else []
        recent_lows = swings["lows"][-20:] if len(swings["lows"]) > 0 else []
        
        # Análise de movimentação MICRO/MACRO (se disponível)
        movement_context = None
        if MOVEMENT_AVAILABLE:
            try:
                movement_context = movement_analyzer.analyze(pair, candles[:-1])
            except Exception:
                pass
        
        signal = None
        desc = ""
        setup_type = None
        
        # Cores das velas
        is_green_v_minus_1 = v_minus_1['close'] > v_minus_1['open']
        is_red_v_minus_1 = v_minus_1['close'] < v_minus_1['open']
        is_green_v0 = v0['close'] > v0['open']
        is_red_v0 = v0['close'] < v0['open']
        
        # ══════════════════════════════════════════════════════════════════
        # SETUP A: FLUXO DE CONTINUIDADE (Rompimento de Defesa)
        # ══════════════════════════════════════════════════════════════════
        
        # CALL: Vela anterior verde + V0 rompe máxima + Pavio superior pequeno
        if (is_green_v_minus_1 and 
            v0['close'] > v_minus_1['high'] and  # Rompeu defesa
            stats_v0['upper'] < (stats_v0['body'] * 0.30) and  # Sem rejeição
            macd_bullish):
            
            # Filtro adicional: Movimento MICRO deve confirmar
            micro_ok = True
            if movement_context:
                micro_ok = movement_context.micro.direction.value == "alta"
            
            if micro_ok:
                signal = "CALL"
                desc = "Setup A: Fluxo Continuidade ALTA"
                setup_type = "FLOW_UP"
        
        # PUT: Vela anterior vermelha + V0 rompe mínima + Pavio inferior pequeno
        elif (is_red_v_minus_1 and 
              v0['close'] < v_minus_1['low'] and  # Rompeu defesa
              stats_v0['lower'] < (stats_v0['body'] * 0.30) and  # Sem rejeição
              macd_bearish):
            
            micro_ok = True
            if movement_context:
                micro_ok = movement_context.micro.direction.value == "baixa"
            
            if micro_ok:
                signal = "PUT"
                desc = "Setup A: Fluxo Continuidade BAIXA"
                setup_type = "FLOW_DOWN"
        
        # ══════════════════════════════════════════════════════════════════
        # SETUP B: ENTREGA FUTURA (Preenchimento de Pavio)
        # ══════════════════════════════════════════════════════════════════
        if not signal:
            # CALL: Pavio inferior grande (suporte) + V0 verde preenchendo
            if (stats_v_minus_1['lower'] > stats_v_minus_1['body'] and  # Pavio > corpo
                is_green_v0 and
                v0['close'] > (v_minus_1['low'] + stats_v_minus_1['lower'] * 0.50) and  # Preencheu 50%+
                macd_bullish):
                signal = "CALL"
                desc = "Setup B: Entrega Futura (Pavio Inferior)"
                setup_type = "WICK_FILL_UP"
            
            # PUT: Pavio superior grande (resistência) + V0 vermelha preenchendo
            elif (stats_v_minus_1['upper'] > stats_v_minus_1['body'] and
                  is_red_v0 and
                  v0['close'] < (v_minus_1['high'] - stats_v_minus_1['upper'] * 0.50) and
                  macd_bearish):
                signal = "PUT"
                desc = "Setup B: Entrega Futura (Pavio Superior)"
                setup_type = "WICK_FILL_DOWN"
        
        # ══════════════════════════════════════════════════════════════════
        # SETUP C: SIMETRIA (Reversão em Níveis Exatos)
        # ══════════════════════════════════════════════════════════════════
        if not signal:
            tolerance = 0.00002  # 2 pips
            
            # Verificar se V0 fechou em nível de TOPO anterior → PUT
            for high in recent_highs:
                if abs(v0['close'] - high) <= tolerance or abs(v0['open'] - high) <= tolerance:
                    # Condição de fraqueza: corpo menor que anterior
                    if stats_v0['body'] < stats_v_minus_1['body']:
                        signal = "PUT"
                        desc = f"Setup C: Simetria TOPO ({high:.5f})"
                        setup_type = "SYMMETRY_TOP"
                        break
            
            # Verificar se V0 fechou em nível de FUNDO anterior → CALL
            if not signal:
                for low in recent_lows:
                    if abs(v0['close'] - low) <= tolerance or abs(v0['open'] - low) <= tolerance:
                        if stats_v0['body'] < stats_v_minus_1['body']:
                            signal = "CALL"
                            desc = f"Setup C: Simetria FUNDO ({low:.5f})"
                            setup_type = "SYMMETRY_BOTTOM"
                            break
        
        # ══════════════════════════════════════════════════════════════════
        # FILTRO DE FRAQUEZA/BLOQUEIO (REGRA DE OURO)
        # ══════════════════════════════════════════════════════════════════
        if signal:
            corpo_diminuiu = stats_v0['body'] < stats_v_minus_1['body'] * 0.7  # 30% menor
            
            # Pavio de rejeição baseado na direção do sinal
            if signal == "CALL":
                pavio_rejeicao_v0 = stats_v0['upper']
                pavio_rejeicao_v_minus_1 = stats_v_minus_1['upper']
            else:
                pavio_rejeicao_v0 = stats_v0['lower']
                pavio_rejeicao_v_minus_1 = stats_v_minus_1['lower']
            
            # Se corpo diminuiu E pavio de rejeição aumentou = EXAUSTÃO
            if corpo_diminuiu and pavio_rejeicao_v0 > pavio_rejeicao_v_minus_1 * 1.5:
                return None, "🚫 Filtro: Exaustão (rejeição forte)"
            
            # Pavio muito longo = defesa forte do lado oposto
            if pavio_rejeicao_v0 > stats_v0['body'] * 0.5:
                return None, "🚫 Filtro: Pavio de rejeição > 50%"
        
        # ══════════════════════════════════════════════════════════════════
        # VALIDAÇÃO COM IA (OBRIGATÓRIA)
        # ══════════════════════════════════════════════════════════════════
        if signal and self.ai_analyzer:
            try:
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
                    signal, desc, candles, zones, trend_context, pair,
                    strategy_logic=self.STRATEGY_LOGIC
                )
                
                if not should_trade:
                    return None, f"🤖❌ {ai_reason[:30]}"
                
                desc = f"{desc} | 🤖✓{confidence}%"
                
            except Exception:
                desc = f"{desc} | ⚠️ IA offline"
        
        return signal, desc
