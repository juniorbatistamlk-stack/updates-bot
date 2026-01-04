# strategies/trader_machado.py
from .base_strategy import BaseStrategy
from utils.advanced_indicators import (
    detect_price_lots, detect_symmetry, get_wick_stats
)


class TraderMachadoStrategy(BaseStrategy):
    """
    Estratégia 12: Trader Machado - A Lógica do Preço
    
    Pilares:
    1. Lotes de Preço - Primeira e última vela definem SNR
    2. Simetria - Alinhamento exato indica trava
    3. Nova Alta/Baixa - Continue as velas following Rompimento de pavio
    4. Taxa Dividida - Reversão de lote
    5. Preenchimento de Pavio - Ofertas não preenchidas
    
    Price Action Puro (sem indicadores)
    """
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Trader Machado (Lógica Preço)"
    
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
        
        is_green_v0 = v0['close'] > v0['open']
        is_red_v0 = v0['close'] < v0['open']

        is_green_v_minus_1 = v_minus_1['close'] > v_minus_1['open']
        is_red_v_minus_1 = v_minus_1['close'] < v_minus_1['open']
        
        signal = None
        desc = ""
        setup_type = None
        
        # === PILAR 1: NOVA ALTA / NOVA BAIXA (CONTINUIDADE) ===
        # Vela rompe pavio da anterior = interesse de busca
        
        nova_alta = v0['high'] > v_minus_1['high'] and is_green_v0
        nova_baixa = v0['low'] < v_minus_1['low'] and is_red_v0
        
        # Verificar se há espaço (vácuo) até próxima simetria
        simetria = detect_symmetry(v0, candles[-50:-2], tolerance=0.00002)
        
        if nova_alta and not simetria:
            signal = "CALL"
            desc = "Nova ALTA (Vácuo)"
            setup_type = "NEW_HIGH"
        
        elif nova_baixa and not simetria:
            signal = "PUT"
            desc = "Nova BAIXA (Vácuo)"
            setup_type = "NEW_LOW"
        
        # === PILAR 2: REVERSÃO POR SIMETRIA (TRAVA) ===
        if not signal and simetria:
            # Corpo fechou em simetria anterior = reversão
            if simetria["type"] == "body" and simetria["strength"] >= 2:
                # Verificar perda de volume/exaustão
                if stats_v0['body'] < stats_v_minus_1['body']:
                    # Se estava subindo e travou = PUT
                    if is_green_v_minus_1:
                        signal = "PUT"
                        desc = f"Simetria TRAVA (Topo {simetria['strength']}x)"
                        setup_type = "SYMMETRY_TOP"
                    # Se estava caindo e travou = CALL
                    elif is_red_v_minus_1:
                        signal = "CALL"
                        desc = f"Simetria TRAVA (Fundo {simetria['strength']}x)"
                        setup_type = "SYMMETRY_BOTTOM"
        
        # === PILAR 3: PREENCHIMENTO DE PAVIO ===
        if not signal:
            # Pavio grande em v_minus_1 = oferta deixada
            pavio_grande_superior = stats_v_minus_1['upper'] > stats_v_minus_1['body']
            pavio_grande_inferior = stats_v_minus_1['lower'] > stats_v_minus_1['body']
            
            # Se há pavio inferior grande e v0 está subindo (preenchendo)
            if pavio_grande_inferior and is_green_v0:
                # Preço está caminhando para preencher o pavio
                if v0['close'] > v_minus_1['low']:
                    signal = "CALL"
                    desc = "Preenchimento PAVIO Inferior"
                    setup_type = "WICK_FILL_UP"
            
            # Se há pavio superior grande e v0 está caindo (preenchendo)
            elif pavio_grande_superior and is_red_v0:
                if v0['close'] < v_minus_1['high']:
                    signal = "PUT"
                    desc = "Preenchimento PAVIO Superior"
                    setup_type = "WICK_FILL_DOWN"
        
        # === PILAR 4: DEFESA DE LOTE ===
        if not signal and len(lots) > 0:
            # Pegar o último lote
            last_lot = lots[-1]
            
            # Se o preço voltou para dentro do lote (reversão de lote)
            if last_lot["type"] == "bull":
                # Lote comprador - se preço volta para primeira vela do lote = PUT
                first_candle_low = last_lot["first_candle"]["low"]
                if v0['low'] <= first_candle_low and is_red_v0:
                    signal = "PUT"
                    desc = f"Reversão LOTE Comprador ({last_lot['size']} velas)"
                    setup_type = "LOT_REVERSAL_TOP"
            
            elif last_lot["type"] == "bear":
                # Lote vendedor - se preço volta para primeira vela do lote = CALL
                first_candle_high = last_lot["first_candle"]["high"]
                if v0['high'] >= first_candle_high and is_green_v0:
                    signal = "CALL"
                    desc = f"Reversão LOTE Vendedor ({last_lot['size']} velas)"
                    setup_type = "LOT_REVERSAL_BOTTOM"
        
        # === FILTRO: Vela sem pavio = fim de movimento ===
        if signal == "CALL" and stats_v0['upper'] == 0:
            return None, "Fim de movimento (sem pavio superior)"
        elif signal == "PUT" and stats_v0['lower'] == 0:
            return None, "Fim de movimento (sem pavio inferior)"
        
        # === VALIDAÇÃO COM IA (OBRIGATÓRIA) ===
        if signal and self.ai_analyzer:
            try:
                trend_context = {
                    "setup": setup_type,
                    "symmetry": simetria is not None,
                    "lot_count": len(lots)
                }
                
                # Usar zonas dos lotes como SNR
                zones = {"resistance": [], "support": []}
                for lot in lots[-5:]:
                    if lot["type"] == "bull":
                        zones["support"].append({
                            "level": lot["first_candle"]["low"],
                            "touches": lot["size"]
                        })
                    else:
                        zones["resistance"].append({
                            "level": lot["first_candle"]["high"],
                            "touches": lot["size"]
                        })
                
                should_trade, confidence, ai_reason = self.validate_with_ai(
                    signal, desc, candles, zones, trend_context, pair
                )
                
                if not should_trade:
                    return None, f"🤖-❌ IA bloqueou: {ai_reason[:30]}"
                
                desc = f"{desc} | 🤖✓{confidence}%"
            except Exception:
                desc = f"{desc} | ⚠️ IA offline"
        
        return signal, desc
