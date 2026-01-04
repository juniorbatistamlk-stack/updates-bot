# strategies/trader_machado_v2.py
"""
================================================================================
🎯 ESTRATÉGIA TRADER MACHADO - A LÓGICA DO PREÇO V2
================================================================================
Versão revisada baseada no JSON original.

Metodologia: A Lógica do Preço (Price Action PURO - Sem Indicadores)

PILARES FUNDAMENTAIS:
  1. Lotes de Preço - Agrupamento de velas define S/R extrema
  2. Simetria - Alinhamento exato indica travas ou exaustão
  3. Nova Alta/Nova Baixa - Rompimento de pavio = interesse de busca (vácuo)
  4. Taxa Dividida - Reversão de lote / abertura de novas posições
  5. Preenchimento de Pavio - Pavio = oferta não preenchida (imã)

REGRA: "O pavio é visto como uma OFERTA deixada pelo mercado. Se não houver 
travamento, o preço tende a caminhar para PREENCHER esse espaço."
================================================================================
"""

from .base_strategy import BaseStrategy
from utils.advanced_indicators import (
    detect_price_lots, detect_symmetry, get_wick_stats,
    calculate_average_body
)

# Tentar importar análise de movimentação
try:
    from utils.price_movement_analyzer import movement_analyzer
    MOVEMENT_AVAILABLE = True
except ImportError:
    MOVEMENT_AVAILABLE = False


class TraderMachadoV2Strategy(BaseStrategy):
    """
    Estratégia Trader Machado V2 - A Lógica do Preço (Revisada)
    """
    
    STRATEGY_LOGIC = """
ESTRATÉGIA TRADER MACHADO - A LÓGICA DO PREÇO:

PILAR 1 - LOTES DE PREÇO:
- Agrupamento de velas de MESMA COR
- Primeira vela do lote = SUPORTE extremo
- Última vela do lote = RESISTÊNCIA extrema
- Reversão de lote = Preço volta para primeira vela = ENTRADA

PILAR 2 - SIMETRIA:
- Corpo ou pavio de V0 alinhado EXATAMENTE com vela anterior
- Indica TRAVA ou EXAUSTÃO
- Se travou em simetria + perda de volume = REVERSÃO
- ENTRADA: Contra o movimento atual

PILAR 3 - NOVA ALTA / NOVA BAIXA:
- Vela rompe PAVIO da anterior = Novo registro de preço
- Indica INTERESSE DE BUSCA (vácuo)
- Se não há travamento à esquerda = CONTINUIDADE
- ENTRADA: A favor do rompimento + aguardar margem

PILAR 4 - TAXA DIVIDIDA:
- Zona de reversão de lote ou abertura de nova posição
- Preço reage fortemente nessas zonas
- ENTRADA: A favor da reação

PILAR 5 - PREENCHIMENTO DE PAVIO:
- Pavio = OFERTA deixada pelo mercado
- Se não há travamento, preço tende a PREENCHER
- Pavio grande = imã de liquidez
- ENTRADA: A favor do preenchimento

FILTRO CRÍTICO:
- Vela SEM PAVIO = FIM de movimento
- CALL sem pavio superior = NÃO ENTRAR
- PUT sem pavio inferior = NÃO ENTRAR

MARGEM DE SEGURANÇA:
- Aguardar "pulo" do preço contra a direção para melhor taxa
"""
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Trader Machado V2 (Lógica Preço)"
    
    def check_signal(self, pair, timeframe_str):
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
        
        candles = self.api.get_candles(pair, timeframe, 100)
        if not candles or len(candles) < 50:
            return None, "Dados insuficientes"
        
        # Detectar lotes de preço
        lots = detect_price_lots(candles[:-2], min_lot_size=2)
        
        # Velas de análise
        v0 = candles[-2]
        v_minus_1 = candles[-3]
        
        stats_v0 = get_wick_stats(v0)
        stats_v_minus_1 = get_wick_stats(v_minus_1)
        avg_body = calculate_average_body(candles[:-2], 10)
        
        is_green_v0 = v0['close'] > v0['open']
        is_red_v0 = v0['close'] < v0['open']
        is_green_v_minus_1 = v_minus_1['close'] > v_minus_1['open']
        is_red_v_minus_1 = v_minus_1['close'] < v_minus_1['open']
        
        signal = None
        desc = ""
        setup_type = None
        tolerance = avg_body * 0.2
        
        # ══════════════════════════════════════════════════════════════════
        # PILAR 3: NOVA ALTA / NOVA BAIXA (CONTINUIDADE)
        # ══════════════════════════════════════════════════════════════════
        
        # Nova ALTA: V0 rompe máxima de V_minus_1 (interesse de busca)
        nova_alta = v0['high'] > v_minus_1['high'] and is_green_v0
        
        # Nova BAIXA: V0 rompe mínima de V_minus_1
        nova_baixa = v0['low'] < v_minus_1['low'] and is_red_v0
        
        # Verificar se há VÁCUO (espaço até próxima simetria/trava)
        simetria = detect_symmetry(v0, candles[-50:-2], tolerance=tolerance)
        
        if nova_alta and not simetria:
            signal = "CALL"
            desc = "Nova ALTA (Vácuo)"
            setup_type = "NEW_HIGH"
        
        elif nova_baixa and not simetria:
            signal = "PUT"
            desc = "Nova BAIXA (Vácuo)"
            setup_type = "NEW_LOW"
        
        # ══════════════════════════════════════════════════════════════════
        # PILAR 2: SIMETRIA (REVERSÃO POR TRAVA)
        # ══════════════════════════════════════════════════════════════════
        if not signal and simetria:
            # Corpo/pavio fechou em simetria anterior
            
            # Verificar perda de volume/exaustão
            corpo_diminuiu = stats_v0['body'] < stats_v_minus_1['body'] * 0.8
            
            if simetria["type"] in ["body", "wick"] and simetria["strength"] >= 2:
                if corpo_diminuiu:
                    # Se estava SUBINDO e travou = PUT
                    if is_green_v_minus_1:
                        signal = "PUT"
                        desc = f"Simetria TRAVA (Topo {simetria['strength']}x)"
                        setup_type = "SYMMETRY_TOP"
                    
                    # Se estava CAINDO e travou = CALL
                    elif is_red_v_minus_1:
                        signal = "CALL"
                        desc = f"Simetria TRAVA (Fundo {simetria['strength']}x)"
                        setup_type = "SYMMETRY_BOTTOM"
        
        # ══════════════════════════════════════════════════════════════════
        # PILAR 5: PREENCHIMENTO DE PAVIO
        # ══════════════════════════════════════════════════════════════════
        if not signal:
            # Pavio grande em V_minus_1 = oferta não preenchida
            pavio_grande_superior = stats_v_minus_1['upper'] > stats_v_minus_1['body']
            pavio_grande_inferior = stats_v_minus_1['lower'] > stats_v_minus_1['body']
            
            # CALL: Pavio inferior grande + V0 verde preenchendo
            if pavio_grande_inferior and is_green_v0:
                # Verificar se está preenchendo (caminhando para o pavio)
                if v0['close'] > v_minus_1['low']:
                    signal = "CALL"
                    desc = "Preenchimento PAVIO Inferior"
                    setup_type = "WICK_FILL_UP"
            
            # PUT: Pavio superior grande + V0 vermelha preenchendo
            elif pavio_grande_superior and is_red_v0:
                if v0['close'] < v_minus_1['high']:
                    signal = "PUT"
                    desc = "Preenchimento PAVIO Superior"
                    setup_type = "WICK_FILL_DOWN"
        
        # ══════════════════════════════════════════════════════════════════
        # PILAR 1 e 4: DEFESA DE LOTE / TAXA DIVIDIDA
        # ══════════════════════════════════════════════════════════════════
        if not signal and len(lots) > 0:
            last_lot = lots[-1]
            
            if last_lot["type"] == "bull":
                # Lote COMPRADOR
                first_candle = last_lot["first_candle"]
                last_candle = last_lot["last_candle"]
                
                # Reversão de lote: Preço volta para primeira vela = PUT
                if v0['low'] <= first_candle['low'] + tolerance and is_red_v0:
                    signal = "PUT"
                    desc = f"Reversão LOTE Comprador ({last_lot['size']} velas)"
                    setup_type = "LOT_REVERSAL_TOP"
                
                # Defesa de lote: Preço testa última vela e segura = CALL
                elif (abs(v0['low'] - last_candle['low']) <= tolerance and
                      is_green_v0 and
                      stats_v0['lower'] > stats_v0['body'] * 0.5):  # Pavio de defesa
                    signal = "CALL"
                    desc = f"Defesa LOTE Comprador ({last_lot['size']} velas)"
                    setup_type = "LOT_DEFENSE_UP"
            
            elif last_lot["type"] == "bear":
                # Lote VENDEDOR
                first_candle = last_lot["first_candle"]
                last_candle = last_lot["last_candle"]
                
                # Reversão de lote: Preço volta para primeira vela = CALL
                if v0['high'] >= first_candle['high'] - tolerance and is_green_v0:
                    signal = "CALL"
                    desc = f"Reversão LOTE Vendedor ({last_lot['size']} velas)"
                    setup_type = "LOT_REVERSAL_BOTTOM"
                
                # Defesa de lote: Preço testa última vela e segura = PUT
                elif (abs(v0['high'] - last_candle['high']) <= tolerance and
                      is_red_v0 and
                      stats_v0['upper'] > stats_v0['body'] * 0.5):
                    signal = "PUT"
                    desc = f"Defesa LOTE Vendedor ({last_lot['size']} velas)"
                    setup_type = "LOT_DEFENSE_DOWN"
        
        # ══════════════════════════════════════════════════════════════════
        # FILTRO CRÍTICO: Vela SEM PAVIO = FIM DE MOVIMENTO
        # ══════════════════════════════════════════════════════════════════
        if signal:
            # CALL sem pavio superior = compradores exaustos
            if signal == "CALL" and stats_v0['upper'] == 0:
                return None, "🚫 Fim de movimento (sem pavio superior)"
            
            # PUT sem pavio inferior = vendedores exaustos
            elif signal == "PUT" and stats_v0['lower'] == 0:
                return None, "🚫 Fim de movimento (sem pavio inferior)"
            
            # Filtro adicional: Verificar confluência com movimento
            if MOVEMENT_AVAILABLE:
                try:
                    movement = movement_analyzer.analyze(pair, candles[:-1])
                    
                    # Se há divergência MICRO vs MACRO, pode ser reversão
                    if movement.has_divergence:
                        if movement.divergence_type == "bullish" and signal == "CALL":
                            desc = f"{desc} +DIV"
                        elif movement.divergence_type == "bearish" and signal == "PUT":
                            desc = f"{desc} +DIV"
                except Exception:
                    pass
                
        
        # ══════════════════════════════════════════════════════════════════
        # VALIDAÇÃO COM IA
        # ══════════════════════════════════════════════════════════════════
        if signal and self.ai_analyzer:
            try:
                trend_context = {
                    "setup": setup_type,
                    "symmetry": simetria is not None,
                    "lot_count": len(lots),
                    "pattern": desc
                }
                
                # Usar zonas dos lotes como S/R
                zones = {"resistance": [], "support": []}
                for lot in lots[-5:]:
                    if lot["type"] == "bull":
                        zones["support"].append({
                            "level": lot["first_candle"]["low"],
                            "touches": lot["size"]
                        })
                        zones["resistance"].append({
                            "level": lot["last_candle"]["high"],
                            "touches": lot["size"]
                        })
                    else:
                        zones["resistance"].append({
                            "level": lot["first_candle"]["high"],
                            "touches": lot["size"]
                        })
                        zones["support"].append({
                            "level": lot["last_candle"]["low"],
                            "touches": lot["size"]
                        })
                
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
