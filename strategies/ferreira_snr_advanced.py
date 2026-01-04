# strategies/ferreira_snr_advanced.py
from .base_strategy import BaseStrategy
from utils.advanced_indicators import (
    detect_swing_highs_lows, get_wick_stats, calculate_average_body,
    is_force_candle
)


class FerreiraSNRAdvancedStrategy(BaseStrategy):
    """
    Estratégia 9: SNR Advanced (Ferreira Trader)
    
    Foco: Rompimento Falso em zonas SNR
    Filtro Anti-Box: Aguarda manipulação antes de entrar
    
    Gatilhos:
    - Rompimento Falso (False Breakout)
    - Exaustão em SNR
    - Simetria Corpo-Pavio
    - Engolfo em SNR
    """
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "SNR Advanced (Ferreira)"
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
        if pair not in self.snr_zones_cache:
            swings = detect_swing_highs_lows(candles[:-2], window=5)
            self.snr_zones_cache[pair] = {
                "resistance": self._cluster_levels(swings["highs"]),
                "support": self._cluster_levels(swings["lows"])
            }
        
        snr_zones = self.snr_zones_cache[pair]
        
        # Velas de análise
        v0 = candles[-2]  # Última fechada
        v_minus_1 = candles[-3]
        
        stats_v0 = get_wick_stats(v0)
        stats_v_minus_1 = get_wick_stats(v_minus_1)
        avg_body = calculate_average_body(candles[:-2], 10)
        
        signal = None
        desc = ""
        setup_type = None
        tolerance = 0.00005
        
        is_green_v0 = v0['close'] > v0['open']
        is_red_v0 = v0['close'] < v0['open']
        
        # === GATILHO 1: ROMPIMENTO FALSO NO SUPORTE ===
        for sup_zone in snr_zones["support"]:
            sup_level = sup_zone["level"]
            
            # Preço rompeu suporte mas voltou
            if (v_minus_1['low'] < sup_level and  # Rompeu
                v0['close'] > sup_level and  # Voltou para dentro
                is_green_v0 and
                abs(v0['close'] - sup_level) >= tolerance):  # Distância segura
                
                signal = "CALL"
                desc = f"Rompimento Falso SUPORTE ({sup_level:.5f})"
                setup_type = "FALSE_BREAKOUT_SUP"
                break
        
        # === GATILHO 2: ROMPIMENTO FALSO NA RESISTÊNCIA ===
        if not signal:
            for res_zone in snr_zones["resistance"]:
                res_level = res_zone["level"]
                
                # Preço rompeu resistência mas voltou
                if (v_minus_1['high'] > res_level and  # Rompeu
                    v0['close'] < res_level and  # Voltou para dentro
                    is_red_v0 and
                    abs(res_level - v0['close']) >= tolerance):
                    
                    signal = "PUT"
                    desc = f"Rompimento Falso RESISTÊNCIA ({res_level:.5f})"
                    setup_type = "FALSE_BREAKOUT_RES"
                    break
        
        # === GATILHO 3: EXAUSTÃO EM SUPORTE ===
        if not signal:
            for sup_zone in snr_zones["support"]:
                sup_level = sup_zone["level"]
                
                # Vela grande vendedora atinge suporte
                if (abs(v0['low'] - sup_level) <= tolerance and
                    is_force_candle(v0, avg_body, 1.5) and
                    is_red_v0 and
                    stats_v0['lower'] > stats_v0['body'] * 0.5):  # Pavio inferior (rejeição)
                    
                    signal = "CALL"
                    desc = f"Exaustão SUPORTE ({sup_level:.5f})"
                    setup_type = "EXHAUSTION_SUP"
                    break
        
        # === GATILHO 4: ENGOLFO EM SNR ===
        if not signal:
            # Engolfo de alta em suporte
            for sup_zone in snr_zones["support"]:
                sup_level = sup_zone["level"]
                
                if (abs(v0['low'] - sup_level) <= tolerance and
                    is_green_v0 and
                    v_minus_1['close'] < v_minus_1['open'] and  # Anterior vermelha
                    v0['close'] > v_minus_1['open'] and  # Engolfo
                    stats_v0['body'] > stats_v_minus_1['body']):
                    
                    signal = "CALL"
                    desc = f"Engolfo SUPORTE ({sup_level:.5f})"
                    setup_type = "ENGULF_SUP"
                    break
            
            # Engolfo de baixa em resistência
            if not signal:
                for res_zone in snr_zones["resistance"]:
                    res_level = res_zone["level"]
                    
                    if (abs(v0['high'] - res_level) <= tolerance and
                        is_red_v0 and
                        v_minus_1['close'] > v_minus_1['open'] and  # Anterior verde
                        v0['close'] < v_minus_1['open'] and  # Engolfo
                        stats_v0['body'] > stats_v_minus_1['body']):
                        
                        signal = "PUT"
                        desc = f"Engolfo RESISTÊNCIA ({res_level:.5f})"
                        setup_type = "ENGULF_RES"
                        break
        
        # === VALIDAÇÃO COM IA (OBRIGATÓRIA) ===
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
                    signal, desc, candles, zones, trend_context, pair
                )
                
                if not should_trade:
                    return None, f"🤖-❌ IA bloqueou: {ai_reason[:30]}"
                
                desc = f"{desc} | 🤖✓{confidence}%"
            except Exception:
                desc = f"{desc} | ⚠️ IA offline"
        
        return signal, desc
    
    def _cluster_levels(self, levels, tolerance=0.00005):
        """Agrupa níveis próximos em zonas"""
        if not levels:
            return []
        
        levels = sorted(levels)
        zones = []
        current_cluster = [levels[0]]
        
        for level in levels[1:]:
            if level - current_cluster[-1] <= tolerance:
                current_cluster.append(level)
            else:
                zones.append({
                    "level": sum(current_cluster) / len(current_cluster),
                    "touches": len(current_cluster)
                })
                current_cluster = [level]
        
        if current_cluster:
            zones.append({
                "level": sum(current_cluster) / len(current_cluster),
                "touches": len(current_cluster)
            })
        
        # Ordenar por força (mais toques = mais forte)
        zones.sort(key=lambda x: x["touches"], reverse=True)
        return zones[:10]
