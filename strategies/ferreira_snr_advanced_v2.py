# strategies/ferreira_snr_advanced_v2.py
"""
================================================================================
🎯 ESTRATÉGIA FERREIRA - SNR ADVANCED V2
================================================================================
Versão revisada baseada no JSON original.

Foco: Rompimento Falso em zonas SNR (NÃO toques diretos)
Filtro Anti-Box: Aguarda manipulação/caça de liquidez antes de entrar

Gatilhos:
  1. Rompimento Falso (False Breakout) - A MINA DE OURO
  2. Candle de Exaustão (corpo grande + perda de volume)
  3. Simetria Corpo-Pavio
  4. Engolfo na SNR

REGRA ANTI-BOX: "70% das regiões de S/R sofrem rompimentos falsos.
Não dê ordem no primeiro toque. Espere o mercado 'caçar liquidez'."
================================================================================
"""

from .base_strategy import BaseStrategy
from utils.advanced_indicators import (
    detect_swing_highs_lows, get_wick_stats, calculate_average_body,
    is_force_candle
)

# Tentar importar análise de movimentação
try:
    from utils.price_movement_analyzer import movement_analyzer
    MOVEMENT_AVAILABLE = True
except ImportError:
    MOVEMENT_AVAILABLE = False


class FerreiraSNRAdvancedV2Strategy(BaseStrategy):
    """
    Estratégia SNR Advanced V2 - Revisada
    """
    
    STRATEGY_LOGIC = """
ESTRATÉGIA FERREIRA SNR ADVANCED:

REGRA ANTI-BOX (FUNDAMENTAL):
- NÃO operar no primeiro toque à linha de S/R
- 70% dos S/R sofrem rompimento falso antes de reverter
- Aguardar a "caça de liquidez" dos institucionais

GATILHO 1 - ROMPIMENTO FALSO (MINA DE OURO):
- Preço ROMPE suporte/resistência
- Candle seguinte RETORNA para dentro da zona
- O rompimento foi "armadilha" para caçar stops
- ENTRADA: A favor da reversão

GATILHO 2 - CANDLE DE EXAUSTÃO:
- Candle MUITO GRANDE atinge a zona de S/R
- Pavio mostrando REJEIÇÃO no final
- Perda de força/volume = compradores/vendedores esgotados
- ENTRADA: Contra o candle de exaustão

GATILHO 3 - SIMETRIA CORPO-PAVIO:
- Corpo do candle comprador termina SIMÉTRICO ao pavio do vendedor anterior
- Indica equilíbrio onde o lado oposto assume controle
- ENTRADA: A favor da simetria

GATILHO 4 - ENGOLFO NA SNR:
- Candle ENGOLFA o anterior exatamente na zona de S/R
- Confirmação de reversão forte
- ENTRADA: A favor do engolfo

FILTRO DE ATAQUE:
- Se candle nasce e faz "ataque" contra SNR para depois retrair = CONFIRMAÇÃO
- Se candle nasce e NÃO testa a zona = ABORTAR ENTRADA
"""
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Ferreira SNR Advanced V2"
        self.snr_zones_cache = {}
    
    def check_signal(self, pair, timeframe_str):
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
        
        candles = self.api.get_candles(pair, timeframe, 100)
        if not candles or len(candles) < 50:
            return None, "Dados insuficientes"
        
        # Identificar zonas SNR predominantes
        swings = detect_swing_highs_lows(candles[:-2], window=5)
        snr_zones = {
            "resistance": self._cluster_levels(swings["highs"]),
            "support": self._cluster_levels(swings["lows"])
        }
        
        # Velas de análise
        v0 = candles[-2]  # Última fechada
        v_minus_1 = candles[-3]
        
        stats_v0 = get_wick_stats(v0)
        stats_v_minus_1 = get_wick_stats(v_minus_1)
        avg_body = calculate_average_body(candles[:-2], 10)
        
        # Análise de movimentação (opcional)
        if MOVEMENT_AVAILABLE:
            try:
                _ = movement_analyzer.analyze(pair, candles[:-1])
            except Exception:
                pass
        
        signal = None
        desc = ""
        setup_type = None
        tolerance = avg_body * 0.3  # Tolerância dinâmica baseada no ATR
        
        is_green_v0 = v0['close'] > v0['open']
        is_red_v0 = v0['close'] < v0['open']
        is_green_v_minus_1 = v_minus_1['close'] > v_minus_1['open']
        is_red_v_minus_1 = v_minus_1['close'] < v_minus_1['open']
        
        # ══════════════════════════════════════════════════════════════════
        # GATILHO 1: ROMPIMENTO FALSO (FALSE BREAKOUT) - MINA DE OURO
        # ══════════════════════════════════════════════════════════════════
        
        # False Breakout no SUPORTE → CALL
        for sup_zone in snr_zones["support"][:5]:
            sup_level = sup_zone["level"]
            
            # Preço ROMPEU suporte (v_minus_1) mas VOLTOU (v0)
            if (v_minus_1['close'] < sup_level and  # Fechou abaixo (rompeu)
                v0['close'] > sup_level and  # Voltou para dentro
                is_green_v0):  # Vela de confirmação verde
                
                signal = "CALL"
                desc = f"False Breakout SUPORTE ({sup_level:.5f})"
                setup_type = "FALSE_BREAK_SUP"
                break
        
        # False Breakout na RESISTÊNCIA → PUT
        if not signal:
            for res_zone in snr_zones["resistance"][:5]:
                res_level = res_zone["level"]
                
                if (v_minus_1['close'] > res_level and
                    v0['close'] < res_level and
                    is_red_v0):
                    
                    signal = "PUT"
                    desc = f"False Breakout RESISTÊNCIA ({res_level:.5f})"
                    setup_type = "FALSE_BREAK_RES"
                    break
        
        # ══════════════════════════════════════════════════════════════════
        # GATILHO 2: CANDLE DE EXAUSTÃO EM SNR
        # ══════════════════════════════════════════════════════════════════
        if not signal:
            # Exaustão em SUPORTE → CALL
            for sup_zone in snr_zones["support"][:5]:
                sup_level = sup_zone["level"]
                
                # Candle grande vendedor atingindo suporte com REJEIÇÃO
                if (abs(v0['low'] - sup_level) <= tolerance and
                    is_red_v0 and
                    is_force_candle(v0, avg_body, 1.5) and  # Candle grande
                    stats_v0['lower'] > stats_v0['body'] * 0.5):  # Pavio de rejeição
                    
                    signal = "CALL"
                    desc = f"Exaustão SUPORTE ({sup_level:.5f})"
                    setup_type = "EXHAUSTION_SUP"
                    break
            
            # Exaustão em RESISTÊNCIA → PUT
            if not signal:
                for res_zone in snr_zones["resistance"][:5]:
                    res_level = res_zone["level"]
                    
                    if (abs(v0['high'] - res_level) <= tolerance and
                        is_green_v0 and
                        is_force_candle(v0, avg_body, 1.5) and
                        stats_v0['upper'] > stats_v0['body'] * 0.5):
                        
                        signal = "PUT"
                        desc = f"Exaustão RESISTÊNCIA ({res_level:.5f})"
                        setup_type = "EXHAUSTION_RES"
                        break
        
        # ══════════════════════════════════════════════════════════════════
        # GATILHO 3: SIMETRIA CORPO-PAVIO
        # ══════════════════════════════════════════════════════════════════
        if not signal:
            # Corpo de V0 termina simétrico ao pavio de V_minus_1
            
            # CALL: Corpo de V0 (verde) fecha no nível do pavio inferior de V_minus_1
            if (is_green_v0 and is_red_v_minus_1 and
                abs(v0['close'] - (v_minus_1['low'] + stats_v_minus_1['lower'])) <= tolerance):
                
                for sup_zone in snr_zones["support"][:3]:
                    if abs(v0['low'] - sup_zone["level"]) <= tolerance * 2:
                        signal = "CALL"
                        desc = "Simetria Corpo-Pavio SUPORTE"
                        setup_type = "SYMMETRY_SUP"
                        break
            
            # PUT: Corpo de V0 (vermelho) fecha no nível do pavio superior de V_minus_1
            if not signal and is_red_v0 and is_green_v_minus_1:
                if abs(v0['close'] - (v_minus_1['high'] - stats_v_minus_1['upper'])) <= tolerance:
                    for res_zone in snr_zones["resistance"][:3]:
                        if abs(v0['high'] - res_zone["level"]) <= tolerance * 2:
                            signal = "PUT"
                            desc = "Simetria Corpo-Pavio RESISTÊNCIA"
                            setup_type = "SYMMETRY_RES"
                            break
        
        # ══════════════════════════════════════════════════════════════════
        # GATILHO 4: ENGOLFO NA SNR
        # ══════════════════════════════════════════════════════════════════
        if not signal:
            # Engolfo de ALTA em suporte
            for sup_zone in snr_zones["support"][:5]:
                sup_level = sup_zone["level"]
                
                if (abs(v0['low'] - sup_level) <= tolerance and
                    is_green_v0 and is_red_v_minus_1 and
                    v0['close'] > v_minus_1['open'] and  # Engolfa abertura
                    v0['open'] < v_minus_1['close'] and  # Abre abaixo do fechamento
                    stats_v0['body'] > stats_v_minus_1['body']):  # Corpo maior
                    
                    signal = "CALL"
                    desc = f"Engolfo SUPORTE ({sup_level:.5f})"
                    setup_type = "ENGULF_SUP"
                    break
            
            # Engolfo de BAIXA em resistência
            if not signal:
                for res_zone in snr_zones["resistance"][:5]:
                    res_level = res_zone["level"]
                    
                    if (abs(v0['high'] - res_level) <= tolerance and
                        is_red_v0 and is_green_v_minus_1 and
                        v0['close'] < v_minus_1['open'] and
                        v0['open'] > v_minus_1['close'] and
                        stats_v0['body'] > stats_v_minus_1['body']):
                        
                        signal = "PUT"
                        desc = f"Engolfo RESISTÊNCIA ({res_level:.5f})"
                        setup_type = "ENGULF_RES"
                        break
        
        # ══════════════════════════════════════════════════════════════════
        # FILTRO: Verificar se houve "ATAQUE" de teste
        # ══════════════════════════════════════════════════════════════════
        if signal:
            # Verificar se V0 testou a zona (fez "ataque")
            if signal == "CALL":
                # Deve ter tocado/passado pelo suporte
                zona_testada = any(
                    v0['low'] <= s["level"] + tolerance 
                    for s in snr_zones["support"][:5]
                )
                if not zona_testada:
                    return None, "🚫 Sem teste de zona (sem ataque)"
            else:
                zona_testada = any(
                    v0['high'] >= r["level"] - tolerance 
                    for r in snr_zones["resistance"][:5]
                )
                if not zona_testada:
                    return None, "🚫 Sem teste de zona (sem ataque)"
        
        # ══════════════════════════════════════════════════════════════════
        # VALIDAÇÃO COM IA
        # ══════════════════════════════════════════════════════════════════
        if signal and self.ai_analyzer:
            try:
                trend_context = {
                    "setup": setup_type,
                    "pattern": "SNR_ADVANCED"
                }
                
                zones = {
                    "resistance": snr_zones["resistance"][:5],
                    "support": snr_zones["support"][:5]
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
    
    def _cluster_levels(self, levels, tolerance_pct=0.0003):
        """Agrupa níveis próximos em zonas"""
        if not levels:
            return []
        
        levels = sorted(levels)
        zones = []
        current_cluster = [levels[0]]
        
        for level in levels[1:]:
            # Tolerância dinâmica (0.03% do preço)
            tolerance = level * tolerance_pct
            
            if level - current_cluster[-1] <= tolerance:
                current_cluster.append(level)
            else:
                zones.append({
                    "level": sum(current_cluster) / len(current_cluster),
                    "touches": len(current_cluster),
                    "strength": len(current_cluster)
                })
                current_cluster = [level]
        
        if current_cluster:
            zones.append({
                "level": sum(current_cluster) / len(current_cluster),
                "touches": len(current_cluster),
                "strength": len(current_cluster)
            })
        
        # Ordenar por força (mais toques = mais forte)
        zones.sort(key=lambda x: x["touches"], reverse=True)
        return zones[:10]
