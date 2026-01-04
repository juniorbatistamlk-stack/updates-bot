from .base_strategy import BaseStrategy
from utils.indicators import calculate_ema, calculate_atr
import threading
# Strategy 6: Alavancagem Agressiva (Fluxo + Reversão)
# -----------------------------------------------------------------------------
# MODOS DE OPERAÇÃO:
# 1. NORMAL: Equilibrio entre filtros e sinais.
# 2. FLEXÍVEL (FLEX): 
#    - Lógica Híbrida Inteligente:
#      A) EM TENDÊNCIA LIMPA: Segue o fluxo agressivamente (Vela de força -> Entra).
#      B) EM SUPORTE/RESISTÊNCIA (S/R): 
#         - NUNCA antecipa o rompimento (não compra na cara da resistência).
#         - NUNCA antecipa a reversão (não vende só porque tocou).
#         - AGUARDA CONFIRMAÇÃO: Espera uma vela de força CONTRA a zona.
#         - ENTRA A FAVOR DA REVERSÃO: Só depois que o mercado virou.
#    - Filtros: Ajustados para filtrar ruído (+7% rigor) mas permitir fluxo rápido.
# 3. PITBULL: Modo ultra-agressivo para alavancagem rápida (alto risco).
# -----------------------------------------------------------------------------

import time


def _candle_stats(c):
    """Calcula estatísticas da vela: corpo, pavios, percentuais"""
    o = c.get("open")
    h = c.get("high")
    low = c.get("low")
    cl = c.get("close")
    if o is None or h is None or low is None or cl is None:
        return None
    total_range = h - low
    if total_range <= 0:
        return None
    body = abs(cl - o)
    upper_wick = h - max(o, cl)
    lower_wick = min(o, cl) - low
    is_green = cl > o
    is_red = cl < o
    return {
        "open": o,
        "high": h,
        "low": low,
        "close": cl,
        "range": total_range,
        "body": body,
        "upper": upper_wick,
        "lower": lower_wick,
        "green": is_green,
        "red": is_red,
        "body_pct": body / total_range,
    }


def _is_marubozu(stats, direction: str) -> bool:
    """Marubozu agressivo: corpo >75%, pavios curtos (<15%), força clara"""
    if not stats:
        return False
    if stats["body_pct"] < 0.75:
        return False
    if (stats["upper"] / stats["range"]) > 0.15:
        return False
    if (stats["lower"] / stats["range"]) > 0.15:
        return False
    return (direction == "BULL" and stats["green"]) or (direction == "BEAR" and stats["red"])


def _three_soldiers_or_crows(candles, direction: str) -> bool:
    """3 velas consecutivas agressivas: corpo >60%, pavio <25%, força crescente"""
    if len(candles) < 3:
        return False
    s = [_candle_stats(c) for c in candles[-3:]]
    if any(x is None for x in s):
        return False
    
    if direction == "BULL":
        if not all(x["green"] for x in s):
            return False
        # Closes DEVEM ser crescentes (força confirmada)
        if not (s[0]["close"] < s[1]["close"] < s[2]["close"]):
            return False
        # Corpos fortes: >60%
        if not all(x["body_pct"] >= 0.60 for x in s):
            return False
        # Pavios curtos: <25% do corpo
        if not all((x["upper"] + x["lower"]) < (x["body"] * 0.25) for x in s):
            return False
    else:  # BEAR
        if not all(x["red"] for x in s):
            return False
        if not (s[0]["close"] > s[1]["close"] > s[2]["close"]):
            return False
        if not all(x["body_pct"] >= 0.60 for x in s):
            return False
        if not all((x["upper"] + x["lower"]) < (x["body"] * 0.25) for x in s):
            return False
    
    return True


def _continuity_engulf(prev, curr, direction: str) -> bool:
    """Engolfo de Continuação agressivo: retomada após correção, corpo >55%"""
    sp = _candle_stats(prev)
    sc = _candle_stats(curr)
    if not sp or not sc:
        return False
    
    if direction == "BULL":
        # Verde forte engolindo vermelha
        if not (sc["green"] and sp["red"]):
            return False
        # Curr fecha bem acima abertura de prev (força)
        if not (sc["close"] > sp["open"] * 1.001):  # ~0.1% acima
            return False
        # Corpo forte (>55%)
        if sc["body_pct"] < 0.55:
            return False
        # Pavio curto <25% do corpo
        if (sc["upper"] + sc["lower"]) > (sc["body"] * 0.25):
            return False
    else:  # BEAR
        if not (sc["red"] and sp["green"]):
            return False
        if not (sc["close"] < sp["open"] * 0.999):
            return False
        if sc["body_pct"] < 0.55:
            return False
        if (sc["upper"] + sc["lower"]) > (sc["body"] * 0.25):
            return False
    
    return True


def _impulse_candle(curr, candles_before, direction: str) -> bool:
    """Break Candle agressivo: corpo >60%, aceleração além da média 10 velas, pavio <20%"""
    sc = _candle_stats(curr)
    if not sc:
        return False
    
    if len(candles_before) < 10:
        return False
    
    avg_body = sum(_candle_stats(c)["body"] for c in candles_before[-10:] if _candle_stats(c)) / 10
    
    if direction == "BULL":
        if not sc["green"]:
            return False
        # Corpo DEVE ser significativamente maior que média
        if sc["body"] < avg_body * 1.10:  # ~10% acima
            return False
        if sc["body_pct"] < 0.60:
            return False
        if sc["lower"] > sc["body"] * 0.20:
            return False
    else:  # BEAR
        if not sc["red"]:
            return False
        if sc["body"] < avg_body * 1.10:
            return False
        if sc["body_pct"] < 0.60:
            return False
        if sc["upper"] > sc["body"] * 0.20:
            return False
    
    return True


def _hammer_pattern(stats) -> bool:
    """Martelo agressivo: pavio inferior >2.0x corpo, corpo <30%, rejeição clara"""
    if not stats:
        return False
    if stats["lower"] < stats["body"] * 2.0:
        return False
    if stats["upper"] > stats["body"] * 0.4:
        return False
    if stats["body_pct"] > 0.30:
        return False
    if not stats["green"]:  # Deve fechar em alta
        return False
    return True


def _shooting_star_pattern(stats) -> bool:
    """Shooting Star agressiva: pavio superior >2.0x corpo, corpo <30%, rejeição clara"""
    if not stats:
        return False
    if stats["upper"] < stats["body"] * 2.0:
        return False
    if stats["lower"] > stats["body"] * 0.4:
        return False
    if stats["body_pct"] > 0.30:
        return False
    if not stats["red"]:  # Deve fechar em baixa
        return False
    return True


def _pin_bar_pattern(stats, direction: str) -> bool:
    """Pin Bar agressivo: pavio >60% do range, corpo <25%"""
    if not stats:
        return False
    if stats["body_pct"] > 0.25:
        return False
    
    if direction == "BULL":
        if not stats["green"]:
            return False
        if stats["lower"] < stats["range"] * 0.60:
            return False
    else:  # BEAR
        if not stats["red"]:
            return False
        if stats["upper"] < stats["range"] * 0.60:
            return False
    
    return True


def _morning_star_pattern(candles) -> bool:
    """Morning Star: 3 velas, reversão de baixa para alta"""
    if len(candles) < 3:
        return False
    s = [_candle_stats(c) for c in candles[-3:]]
    if any(x is None for x in s):
        return False
    
    # Primeira: vermelha forte
    if not s[0]["red"] or s[0]["body_pct"] < 0.40:
        return False
    # Segunda: corpo mínimo (indecisão/gap para baixo)
    if s[1]["body_pct"] > 0.35:
        return False
    # Terceira: verde forte fechando acima do meio da primeira
    if not s[2]["green"] or s[2]["body_pct"] < 0.40:
        return False
    if s[2]["close"] <= s[0]["open"]:
        return False
    
    return True


def _evening_star_pattern(candles) -> bool:
    """Evening Star: 3 velas, reversão de alta para baixa"""
    if len(candles) < 3:
        return False
    s = [_candle_stats(c) for c in candles[-3:]]
    if any(x is None for x in s):
        return False
    
    # Primeira: verde forte
    if not s[0]["green"] or s[0]["body_pct"] < 0.40:
        return False
    # Segunda: corpo mínimo (indecisão/gap para cima)
    if s[1]["body_pct"] > 0.35:
        return False
    # Terceira: vermelha forte fechando abaixo do meio da primeira
    if not s[2]["red"] or s[2]["body_pct"] < 0.40:
        return False
    if s[2]["close"] >= s[0]["open"]:
        return False
    
    return True


class AlavancagemStrategy(BaseStrategy):
    """
    ESTRATÉGIA FIA - Fluxo Inteligente Agressivo (MODO ULTRA AGRESSIVO)
    
    Objetivo: Alavancar a banca em 40 minutos operando com a tendência principal
    e o fluxo de vela dominante, executando reversões apenas em zonas S/R extremas
    com confirmação visual.
    
    Perfil: Agressivo técnico, com entradas rápidas e controle de risco limitado.
    
    Timeframes:
    - M15: Tendência predominante (EMA20 > EMA50)
    - M5: Zonas de suporte e resistência
    - M1: Entradas baseadas em fluxo e rejeição
    
    ULTRA AGRESSIVO:
    - Corpo > 70% do range (força absoluta)
    - Pavio contrário < 10% do corpo (sem indecisão)
    - 3 velas fortes confirmadas (fluxo absoluto)
    - S/R extremas apenas (2+ toques fortes + ATR > média 10 velas)
    - Distância de zona < 0.15% para entrada
    """
    
    def __init__(self, api_handler, ai_analyzer=None, mode: str = "NORMAL"):
        super().__init__(api_handler, ai_analyzer)
        self.mode = (mode or "NORMAL").upper().strip()
        # Atualizar nome baseado no modo
        if self.mode == "BLACK":
            self.name = "BLACK FLEX - Alavancagem LTA/LTB"
        elif self.mode == "FLEX":
            self.name = "FLEX - Fluxo Inteligente Agressivo"
        elif self.mode == "PITBULL":
            self.name = "PITBULL - Ultra Agressivo"
        else:
            self.name = "ALAVANCAGEM - Normal"
        self.sr_zones = {}  # Cache de zonas S/R por par
        self.analyzed_pairs = set()
        self.pre_analysis_done = {}
        self._logger = None
        self._pre_analyze_inflight = set()
        self._pre_analyze_lock = threading.Lock()
        self._last_ai_ctx = {}

    def _params(self):
        # Parâmetros por modo (ajustes cirúrgicos para aumentar sinais sem virar "metralhadora")
        
        # MODO BLACK: Ultra-agressivo LTA/LTB - Apenas tendência + reversões S/R
        # META: Bater objetivo em 1 hora
        if self.mode == "BLACK":
            return {
                "vol_min_pct": 0.03,        # Baixíssimo filtro de volatilidade
                "min_range_atr": 0.04,      # Aceita velas pequenas se houver confirmação
                "flow_body_min": 0.30,      # Corpo de 30% já é suficiente para confirmação
                "sr_tol_mult": 0.008,       # Zona S/R mais ampla para capturar mais reversões
                "atr_valid_factor": 0.30,   # Validação mínima de ATR
                "sr_strength_min": 1,       # 1 toque já identifica zona
                "reversal_body_min": 0.30,  # Reversão precisa de corpo 30%+
                "allow_countertrend_sr_reversal": False,  # NUNCA opera contra tendência
                "allow_sr_breakout": False,  # Sem rompimentos - apenas reversões
                "strict_trend_only": True,   # Flag para forçar apenas operações a favor
            }
        
        if self.mode == "FLEX":
            return {
                "vol_min_pct": 0.0535,      # -1% adicional (Ajuste fino II)
                "min_range_atr": 0.0535,    # -1% adicional
                # Corpo: 42.9% -> 42.5%
                "flow_body_min": 0.425,     # -1% adicional
                "sr_tol_mult": 0.005,       # Mantido (zona de S/R)
                "atr_valid_factor": 0.535,  # -1% adicional
                "sr_strength_min": 1,       # 1 toque já serve de alerta
                "allow_countertrend_sr_reversal": True,
                "allow_sr_breakout": True,
            }
        # MODO PITBULL BRAVO (Correção de Lag + Agressividade Total)
        if self.mode == "PITBULL":
            return {
                "vol_min_pct": 0.01,        # Zero frescura com volatilidade
                "min_range_atr": 0.05,      # Qualquer vela serve se tiver direção
                "flow_body_min": 0.35,      # Aceita corpo pequeno (35%) se for a favor
                "sr_tol_mult": 0.50,        # CORREÇÃO: 0.5 * ATR (Meio ATR de tolerância) - Pega a zona real
                "atr_valid_factor": 0.40,   # Validação mínima
                "sr_strength_min": 1,       # 1 toque é barreira
                "allow_countertrend_sr_reversal": True,
                "allow_sr_breakout": True,
            }
        return {
            "vol_min_pct": 0.15,
            "min_range_atr": 0.15,
            "flow_body_min": 0.50,
            "sr_tol_mult": 0.003,
            "atr_valid_factor": 0.90,
            "sr_strength_min": 2,
            "allow_countertrend_sr_reversal": False,
            "allow_sr_breakout": False,
        }

    def set_logger(self, log_func):
        """Define callback para enviar logs ao dashboard"""
        self._logger = log_func

    def get_last_ai_context(self):
        """Retorna o contexto estruturado do último sinal analisado (para IA usar)"""
        return self._last_ai_ctx.copy()

    def _log(self, msg):
        """Envia log para dashboard ou print como fallback"""
        if self._logger:
            self._logger(msg)
        else:
            print(msg)

    def pre_analyze(self, pair, timeframe=1):
        """
        PRÉ-ANÁLISE: Detecta zonas de S/R baseado em 2+ toques e rejeições
        
        Critérios:
        - Dois ou mais toques na mesma região
        - Rejeição visível (pavio longo, corpo pequeno)
        - Confluência entre timeframes (M5 e M15)
        """
        self._log(f"[FIA] 📊 Pré-análise de {pair}...")

        candles = self.api.get_candles(pair, timeframe, 200)
        if not candles or len(candles) < 100:
            self._log(f"[FIA] ⚠️ Dados insuficientes para {pair}")
            return None

        # Detectar swing highs (topos) e lows (fundos)
        swing_highs = []
        swing_lows = []

        for i in range(5, len(candles) - 5):
            c_high = candles[i]["high"]
            c_low = candles[i]["low"]
            
            # Topo: máxima maior que 5 velas antes e depois
            is_swing_high = True
            for j in range(i - 5, i + 6):
                if j != i and candles[j]["high"] >= c_high:
                    is_swing_high = False
                    break
            if is_swing_high:
                swing_highs.append(c_high)
            
            # Fundo: mínima menor que 5 velas antes e depois
            is_swing_low = True
            for j in range(i - 5, i + 6):
                if j != i and candles[j]["low"] <= c_low:
                    is_swing_low = False
                    break
            if is_swing_low:
                swing_lows.append(c_low)

        # Agrupar níveis próximos em zonas
        atr = calculate_atr(candles[:-1], 14) or 0.0001
        tolerance = atr * 1.2

        resistance_zones = self._cluster_levels(swing_highs, tolerance)
        support_zones = self._cluster_levels(swing_lows, tolerance)

        # Salvar no cache
        self.sr_zones[pair] = {
            "resistance": resistance_zones,
            "support": support_zones,
            "atr": atr,
        }
        self.analyzed_pairs.add(pair)
        self.pre_analysis_done[pair] = time.time()

        self._log(
            f"[FIA] ✅ {pair}: {len(resistance_zones)} resistências | {len(support_zones)} suportes"
        )

        return {
            "resistance": resistance_zones,
            "support": support_zones,
        }

    def _kickoff_pre_analyze(self, pair, timeframe):
        """Dispara a pré-análise em background para não travar o scanner multi-ativos."""
        with self._pre_analyze_lock:
            if pair in self.analyzed_pairs or pair in self._pre_analyze_inflight:
                return
            self._pre_analyze_inflight.add(pair)

        def _job():
            try:
                self.pre_analyze(pair, timeframe)
            except Exception:
                # Não derrubar o loop por pré-análise.
                pass
            finally:
                with self._pre_analyze_lock:
                    self._pre_analyze_inflight.discard(pair)

        threading.Thread(target=_job, daemon=True).start()

    def _cluster_levels(self, levels, tolerance):
        """Agrupa níveis próximos em zonas baseado em força (número de toques)"""
        if not levels:
            return []

        levels = sorted(levels)
        zones = []
        current_zone = [levels[0]]

        for level in levels[1:]:
            if level - current_zone[-1] <= tolerance:
                current_zone.append(level)
            else:
                zones.append({
                    "level": sum(current_zone) / len(current_zone),
                    "touches": len(current_zone),
                })
                current_zone = [level]

        if current_zone:
            zones.append({
                "level": sum(current_zone) / len(current_zone),
                "touches": len(current_zone),
            })

        # Ordenar por força (mais toques = mais forte)
        zones.sort(key=lambda x: x["touches"], reverse=True)
        return zones[:5]

    def check_signal(self, pair, timeframe_str):
        """
        Verifica sinal de entrada segundo FIA:
        1. FLUXO (a favor tendência): 2+ velas + corpo > 65% + pavio < 20%
        2. REVERSÃO (contra tendência): apenas em S/R + padrão reversão
        3. PADRÕES: Marubozu, 3 Soldiers/Crows, Engolfo, Impulso, etc.
        """
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1

        # Disparar pré-análise em background
        if pair not in self.analyzed_pairs:
            self._kickoff_pre_analyze(pair, timeframe)

        try:
            candles = self.api.get_candles(pair, timeframe, 60)
        except Exception as e:
            # Se falhar ao buscar candles, retornar vazio
            return None, f"Erro: {str(e)[:20]}"
        
        if not candles or len(candles) < 30:
            return None, "Dados..."

        p = self._params()

        # Filtro de volatilidade global: evitar mercado morto (mais permissivo)
        avg_price = sum(c["close"] for c in candles[-20:]) / 20
        atr_tmp = calculate_atr(candles[:-1], 14)
        if atr_tmp and avg_price:
            vol_pct = (atr_tmp / avg_price) * 100
            if vol_pct < p["vol_min_pct"]:
                return None, "⏳ Baixa volatilidade"

        # Indicadores principais
        ema20 = calculate_ema(candles[:-1], 20)
        ema50 = calculate_ema(candles[:-1], 50)
        atr = calculate_atr(candles[:-1], 14)

        if not all([ema20, ema50, atr]):
            return None, "Calculando..."

        # Trabalhar com vela FECHADA (não real-time)
        current = candles[-2]
        prev = candles[-3] if len(candles) >= 3 else candles[-2]
        prev2 = candles[-4] if len(candles) >= 4 else candles[-3]

        price = current["close"]
        is_green = current["close"] > current["open"]
        is_red = current["close"] < current["open"]

        st = _candle_stats(current)
        if not st:
            return None, "Doji fraco"

        total_range = st["range"]

        # Filtro: vela muito pequena vs ATR (mais permissivo para aumentar sinais)
        if total_range < atr * p["min_range_atr"]:
            return None, "⏳ Vela fraca"

        # === ANÁLISE DE TENDÊNCIA (EMA20 > EMA50) ===
        # NORMAL: Cruzamento EMA20/50 (Mais seguro, mas atrasado)
        # PITBULL: Preço > EMA20 já considera tendência de curto prazo (CORREÇÃO DE LAG)
        if self.mode == "PITBULL":
            # Se preço está acima da média rápida, é alta. Sem conversa.
            is_uptrend = (ema20 > ema50) or (price > ema20 and prev["close"] > ema20)
            is_downtrend = (ema20 < ema50) or (price < ema20 and prev["close"] < ema20)
        else:
            is_uptrend = ema20 > ema50
            is_downtrend = ema20 < ema50

        is_lateral = not is_uptrend and not is_downtrend
        
        # BLACK pode operar em lateral (operando S/R), outros modos bloqueiam
        if is_lateral and self.mode not in ["FLEX", "PITBULL", "BLACK"]:
            return None, "⏳ Mercado lateral"

        # === ZONAS S/R EXTREMAS (apenas 2+ toques + ATR validação) ===
        sr_data = self.sr_zones.get(pair, {"resistance": [], "support": [], "atr": atr})
        resistance_zones = sr_data["resistance"]
        support_zones = sr_data["support"]
        sr_atr = sr_data.get("atr", atr)
        
        # Tolerância de zona mais ampla para permitir mais confirmações
        tolerance = sr_atr * p["sr_tol_mult"]
        
        # VALIDAÇÃO ULTRA: S/R extrema APENAS com 2+ toques forte + ATR > média 10 velas
        avg_atr = sum(calculate_atr(candles[i:i+14], 14) or atr for i in range(max(0, len(candles)-30), len(candles)-14)) / max(1, min(16, len(candles)-14))
        atr_valid = atr >= (avg_atr * p["atr_valid_factor"])  # Aceita se ATR acima do fator configurado
        
        at_resistance = any(
            abs(current["high"] - z["level"]) <= tolerance and z["touches"] >= 2 and atr_valid
            for z in resistance_zones
        )
        at_support = any(
            abs(current["low"] - z["level"]) <= tolerance and z["touches"] >= 2 and atr_valid
            for z in support_zones
        )

        resistance_strength = max(
            [z["touches"] for z in resistance_zones if abs(current["high"] - z["level"]) <= tolerance and atr_valid],
            default=0,
        )
        support_strength = max(
            [z["touches"] for z in support_zones if abs(current["low"] - z["level"]) <= tolerance and atr_valid],
            default=0,
        )

        # === PADRÕES DE FLUXO (continuação, a favor tendência) ===
        flow_pattern = None
        
        if _is_marubozu(st, "BULL" if is_uptrend else "BEAR"):
            flow_pattern = "MARUBOZU"
        elif _three_soldiers_or_crows([prev2, prev, current], "BULL" if is_uptrend else "BEAR"):
            flow_pattern = "THREE_SOLDIERS" if is_uptrend else "THREE_CROWS"
        elif _continuity_engulf(prev, current, "BULL" if is_uptrend else "BEAR"):
            flow_pattern = "ENGULF_CONT"
        elif _impulse_candle(current, candles[:-2], "BULL" if is_uptrend else "BEAR"):
            flow_pattern = "IMPULSE"

        # === PADRÕES DE REVERSÃO (contra tendência, em S/R) ===
        reversal_pattern = None
        
        if _hammer_pattern(st):
            reversal_pattern = "HAMMER"
        elif _shooting_star_pattern(st):
            reversal_pattern = "SHOOTING_STAR"
        elif _pin_bar_pattern(st, "BULL"):
            reversal_pattern = "PIN_BAR_BULL"
        elif _pin_bar_pattern(st, "BEAR"):
            reversal_pattern = "PIN_BAR_BEAR"
        elif _continuity_engulf(prev, current, "BULL"):
            reversal_pattern = "ENGULF_BULL"
        elif _continuity_engulf(prev, current, "BEAR"):
            reversal_pattern = "ENGULF_BEAR"
        elif _morning_star_pattern([prev2, prev, current]):
            reversal_pattern = "MORNING_STAR"
        elif _evening_star_pattern([prev2, prev, current]):
            reversal_pattern = "EVENING_STAR"

        signal = None
        desc = ""
        setup_kind = None
        setup_pattern = None

        # Define os padrões de reversão para facilitar a lógica
        bull_rev = {"HAMMER", "PIN_BAR_BULL", "MORNING_STAR"}
        bear_rev = {"SHOOTING_STAR", "PIN_BAR_BEAR", "EVENING_STAR"}
        if self.mode in ["FLEX", "PITBULL"]:
            bull_rev |= {"ENGULF_BULL"}
            bear_rev |= {"ENGULF_BEAR"}

        # =========================================================================
        # 🧠 LÓGICA CORE: PITBULL MODE
        # 1. FLUXO: Se não tem barreira (S/R), ataca a favor da tendência.
        # 2. S/R: Se tem barreira, ESPERA REVERSÃO.
        # =========================================================================

        # AJUSTE: Relaxar S/R check para modo NORMAL/FLEX
        # Só consideramos "at_resistance" se realmente estiver batendo nela.
        
        # --- CENÁRIO 1: TENDÊNCIA DE ALTA ---
        if is_uptrend:
            # BLACK MODE: APENAS A FAVOR DA TENDÊNCIA + REVERSÕES EM S/R
            # REGRA DE OURO: Nunca opera contra a tendência
            if self.mode == "BLACK":
                reversal_confirmed = is_red and st["body_pct"] >= p.get("reversal_body_min", 0.30)
                
                # 🚫 RESISTÊNCIA: Aguarda reversão para PUT
                if at_resistance and resistance_strength >= p["sr_strength_min"]:
                    if reversal_confirmed:
                        signal = "PUT"
                        desc = f"⚫ BLACK | Reversão Resistência ({resistance_strength}x)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "SR_REVERSAL"
                    else:
                        return None, f"⏳ BLACK | Resist ({resistance_strength}x) - Aguardando reversão"
                
                # ✅ SUPORTE: Aguarda reversão para CALL (a favor da tendência)
                elif at_support and support_strength >= p["sr_strength_min"]:
                    if is_green and st["body_pct"] >= p.get("reversal_body_min", 0.30):
                        signal = "CALL"
                        desc = f"⚫ BLACK | Reversão Suporte ({support_strength}x)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "SR_BOUNCE"
                    else:
                        return None, f"⏳ BLACK | Sup ({support_strength}x) - Aguardando reversão"
                
                # 🚀 FLUXO LIVRE: Segue a tendência de alta
                elif is_green and st["body_pct"] >= p["flow_body_min"]:
                    signal = "CALL"
                    desc = "⚫ BLACK | Fluxo Comprador"
                    setup_kind = "FLUXO"
                    setup_pattern = flow_pattern or "TREND_MOMENTUM"
                
                # Padrões de fluxo adicionais
                elif flow_pattern in {"MARUBOZU", "IMPULSE", "THREE_SOLDIERS", "ENGULF_CONT"} and is_green:
                    signal = "CALL"
                    desc = f"⚫ BLACK | Padrão {flow_pattern}"
                    setup_kind = "FLUXO"
                    setup_pattern = flow_pattern
                
                else:
                    return None, "⏳ BLACK | Aguardando setup"
            
            # FLEX MODE: Respeita S/R e só entra APÓS reversão confirmada
            elif self.mode == "FLEX":
                # 🚫 ZONA DE PERIGO: Resistência detectada
                if at_resistance and resistance_strength >= p["sr_strength_min"]:
                    # NÃO entra CALL (mesmo com vela verde) - aguarda reversão
                    # SÓ entra PUT se já reverteu (vela vermelha forte)
                    if is_red and st["body_pct"] >= 0.30:  # Reversão confirmada
                        signal = "PUT"
                        desc = f"🔻 REVERSÃO CONFIRMADA | Resistência ({resistance_strength}x)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "PRICE_REJECTION"
                    else:
                        return None, f"⏳ Resistência ({resistance_strength}x) - Aguardando reversão..."
                
                # ✅ CAMINHO LIVRE: Sem barreira, segue o fluxo
                else:
                    # Se tocar suporte e já reverteu (vela verde) → CALL
                    if at_support and support_strength >= p["sr_strength_min"] and is_green and st["body_pct"] >= 0.30:
                        signal = "CALL"
                        desc = f"🔺 REVERSÃO CONFIRMADA | Suporte ({support_strength}x)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "SUPPORT_BOUNCE"
                    # Fluxo normal: vela verde forte → CALL
                    elif is_green and st["body_pct"] >= p["flow_body_min"]:
                        signal = "CALL"
                        desc = "🚀 FLUXO COMPRADOR | FLEX Trend-Following"
                        setup_kind = "FLUXO"
                        setup_pattern = "MOMENTUM"
                    elif flow_pattern in {"MARUBOZU", "IMPULSE", "THREE_SOLDIERS", "ENGULF_CONT"} and is_green:
                        signal = "CALL"
                        desc = f"🚀 PADRÃO DE ALTA | {flow_pattern}"
                        setup_kind = "FLUXO"
                        setup_pattern = flow_pattern
                    else:
                        return None, "⏳ Aguardando setup comprador"
            
            # MODO NORMAL/PITBULL: Lógica original S/R
            else:
                # A) Estamos na cara do gol (Resistência)?
                if at_resistance:
                    # LÓGICA S/R: Não compra topo. Espera cair.
                    if reversal_pattern in {"SHOOTING_STAR", "PIN_BAR_BEAR", "EVENING_STAR", "ENGULF_BEAR"} or \
                       (is_red and st["body_pct"] > 0.40):
                        signal = "PUT"
                        desc = f"🔻 REVERSÃO NO TOPO | {reversal_pattern or 'Força Vendedora'}"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "PRICE_REJECTION"
                    else:
                        return None, f"⏳ Na Resistência ({resistance_strength}x) - Aguardando reversão..."
                
                # B) Caminho livre? FLUXO PURO
                else:
                    if at_support and support_strength >= p["sr_strength_min"] and reversal_pattern in bull_rev:
                        signal = "CALL"
                        desc = f"🔄 REVERSÃO S/R | {reversal_pattern} ({support_strength} toques)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern
                    elif is_green and st["body_pct"] >= p["flow_body_min"]:
                        signal = "CALL"
                        desc = "🚀 FLUXO COMPRADOR | Pitbull Attack"
                        setup_kind = "FLUXO"
                        setup_pattern = "MOMENTUM"
                    elif flow_pattern in {"MARUBOZU", "IMPULSE", "THREE_SOLDIERS", "ENGULF_CONT"} and is_green:
                        signal = "CALL"
                        desc = f"🚀 PADRÃO DE ALTA | {flow_pattern}"
                        setup_kind = "FLUXO"
                        setup_pattern = flow_pattern

        # --- CENÁRIO 2: TENDÊNCIA DE BAIXA ---
        elif is_downtrend:
            # BLACK MODE: APENAS A FAVOR DA TENDÊNCIA + REVERSÕES EM S/R
            # REGRA DE OURO: Nunca opera contra a tendência
            if self.mode == "BLACK":
                reversal_confirmed = is_green and st["body_pct"] >= p.get("reversal_body_min", 0.30)
                
                # 🚫 SUPORTE: Aguarda reversão para CALL
                if at_support and support_strength >= p["sr_strength_min"]:
                    if reversal_confirmed:
                        signal = "CALL"
                        desc = f"⚫ BLACK | Reversão Suporte ({support_strength}x)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "SR_BOUNCE"
                    else:
                        return None, f"⏳ BLACK | Sup ({support_strength}x) - Aguardando reversão"
                
                # ✅ RESISTÊNCIA: Aguarda reversão para PUT (a favor da tendência)
                elif at_resistance and resistance_strength >= p["sr_strength_min"]:
                    if is_red and st["body_pct"] >= p.get("reversal_body_min", 0.30):
                        signal = "PUT"
                        desc = f"⚫ BLACK | Reversão Resistência ({resistance_strength}x)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "SR_REVERSAL"
                    else:
                        return None, f"⏳ BLACK | Resist ({resistance_strength}x) - Aguardando reversão"
                
                # 🧨 FLUXO LIVRE: Segue a tendência de baixa
                elif is_red and st["body_pct"] >= p["flow_body_min"]:
                    signal = "PUT"
                    desc = "⚫ BLACK | Fluxo Vendedor"
                    setup_kind = "FLUXO"
                    setup_pattern = flow_pattern or "TREND_MOMENTUM"
                
                # Padrões de fluxo adicionais
                elif flow_pattern in {"MARUBOZU", "IMPULSE", "THREE_CROWS", "ENGULF_CONT"} and is_red:
                    signal = "PUT"
                    desc = f"⚫ BLACK | Padrão {flow_pattern}"
                    setup_kind = "FLUXO"
                    setup_pattern = flow_pattern
                
                else:
                    return None, "⏳ BLACK | Aguardando setup"
            
            # FLEX MODE: Respeita S/R e só entra APÓS reversão confirmada
            elif self.mode == "FLEX":
                # 🚫 ZONA DE PERIGO: Suporte detectado
                if at_support and support_strength >= p["sr_strength_min"]:
                    # NÃO entra PUT (mesmo com vela vermelha) - aguarda reversão
                    # SÓ entra CALL se já reverteu (vela verde forte)
                    if is_green and st["body_pct"] >= 0.30:  # Reversão confirmada
                        signal = "CALL"
                        desc = f"🔺 REVERSÃO CONFIRMADA | Suporte ({support_strength}x)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "SUPPORT_BOUNCE"
                    else:
                        return None, f"⏳ Suporte ({support_strength}x) - Aguardando reversão..."
                
                # ✅ CAMINHO LIVRE: Sem barreira, segue o fluxo
                else:
                    # Se tocar resistência e já reverteu (vela vermelha) → PUT
                    if at_resistance and resistance_strength >= p["sr_strength_min"] and is_red and st["body_pct"] >= 0.30:
                        signal = "PUT"
                        desc = f"🔻 REVERSÃO CONFIRMADA | Resistência ({resistance_strength}x)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "RESISTANCE_REJECTION"
                    # Fluxo normal: vela vermelha forte → PUT
                    elif is_red and st["body_pct"] >= p["flow_body_min"]:
                        signal = "PUT"
                        desc = "🧨 FLUXO VENDEDOR | FLEX Trend-Following"
                        setup_kind = "FLUXO"
                        setup_pattern = "MOMENTUM"
                    elif flow_pattern in {"MARUBOZU", "IMPULSE", "THREE_CROWS", "ENGULF_CONT"} and is_red:
                        signal = "PUT"
                        desc = f"🧨 PADRÃO DE BAIXA | {flow_pattern}"
                        setup_kind = "FLUXO"
                        setup_pattern = flow_pattern
                    else:
                        return None, "⏳ Aguardando setup vendedor"
            
            # MODO NORMAL/PITBULL: Lógica original S/R
            else:
                # A) Estamos no chão (Suporte)?
                if at_support:
                    # LÓGICA S/R: Não vende fundo. Espera subir.
                    if reversal_pattern in {"HAMMER", "PIN_BAR_BULL", "MORNING_STAR", "ENGULF_BULL"} or \
                       (is_green and st["body_pct"] > 0.40):
                        signal = "CALL"
                        desc = f"🔺 REVERSÃO NO FUNDO | {reversal_pattern or 'Força Compradora'}"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern or "PRICE_REJECTION"
                    else:
                        return None, f"⏳ No Suporte ({support_strength}x) - Aguardando reversão..."
                
                # B) Caminho livre? FLUXO PURO
                else:
                    if at_support and support_strength >= p["sr_strength_min"] and reversal_pattern in bull_rev:
                        signal = "CALL"
                        desc = f"🔄 REVERSÃO S/R | {reversal_pattern} ({support_strength} toques)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern
                    elif at_resistance and resistance_strength >= p["sr_strength_min"] and reversal_pattern in bear_rev:
                        signal = "PUT"
                        desc = f"🔄 REVERSÃO S/R | {reversal_pattern} ({resistance_strength} toques)"
                        setup_kind = "REVERSAO"
                        setup_pattern = reversal_pattern
                    elif is_red and st["body_pct"] >= p["flow_body_min"]:
                        signal = "PUT"
                        desc = "🧨 FLUXO VENDEDOR | Pitbull Attack"
                        setup_kind = "FLUXO"
                        setup_pattern = "MOMENTUM"
                    elif flow_pattern in {"MARUBOZU", "IMPULSE", "THREE_CROWS", "ENGULF_CONT"} and is_red:
                        signal = "PUT"
                        desc = f"🧨 PADRÃO DE BAIXA | {flow_pattern}"
                        setup_kind = "FLUXO"
                        setup_pattern = flow_pattern
        
        # 4. BLACK EM LATERAL: Opera S/R puro (ping-pong)
        if not signal and self.mode == "BLACK" and is_lateral:
            # Resistência + vela vermelha → PUT
            if at_resistance and resistance_strength >= p["sr_strength_min"] and is_red and st["body_pct"] >= p.get("reversal_body_min", 0.30):
                signal = "PUT"
                desc = f"⚫ BLACK LATERAL | Reversão Resist ({resistance_strength}x)"
                setup_kind = "REVERSAO"
                setup_pattern = "SR_REVERSAL"
            # Suporte + vela verde → CALL
            elif at_support and support_strength >= p["sr_strength_min"] and is_green and st["body_pct"] >= p.get("reversal_body_min", 0.30):
                signal = "CALL"
                desc = f"⚫ BLACK LATERAL | Reversão Sup ({support_strength}x)"
                setup_kind = "REVERSAO"
                setup_pattern = "SR_BOUNCE"
        
        # 5. PITBULL EXTRA: FLUXO EM LATERALIDADE FORTE
        if not signal and self.mode == "PITBULL" and is_lateral:
             if is_green and st["body_pct"] > 0.5 and not at_resistance:
                 signal = "CALL"
                 desc = "🚀 PITBULL LATERAL | Vela de Força"
             elif is_red and st["body_pct"] > 0.5 and not at_support:
                 signal = "PUT"
                 desc = "🧨 PITBULL LATERAL | Vela de Força"
        
        # --- CENÁRIO 3: LATERAL (Pitbull só opera se for FLEX e tiver muito claro) ---
        elif is_lateral and self.mode == "FLEX":
             # Em lateralidade, operamos extremos (Ping-Pong)
             if at_resistance and is_red:
                 signal = "PUT"
                 desc = "↔️ LATERAL: Venda na Resistência"
             elif at_support and is_green:
                 signal = "CALL"
                 desc = "↔️ LATERAL: Compra no Suporte"

        if not signal:
            trend_txt = "ALTA" if is_uptrend else "BAIXA" if is_downtrend else "LATERAL"
            return None, f"⏳ {trend_txt} | Aguardando setup"

        # Contexto enriquecido para IA
        self._last_ai_ctx = {
            "trend": "UP" if is_uptrend else "DOWN",
            "setup": setup_kind or "UNKNOWN",
            "pattern": setup_pattern or "UNKNOWN",
            "flow_pattern": flow_pattern or "NONE",
            "reversal_pattern": reversal_pattern or "NONE",
            "sr": "SUPPORT" if at_support else "RESIST" if at_resistance else "NONE",
            "sr_strength": int(max(support_strength, resistance_strength) or 0),
            "volatility": "HIGH" if (total_range > atr * 1.2) else "NORMAL",
        }

        # 🤖 VALIDAÇÃO IA (FLEX MODE): IA é o "juiz final" de cada entrada
        if self.mode == "FLEX" and self.ai_analyzer:
            try:
                # Preparar contexto completo para IA
                zones = {
                    "support": support_zones,
                    "resistance": resistance_zones,
                }
                
                # Consultar IA
                should_trade, confidence, ai_reason = self.validate_with_ai(
                    signal, desc, candles, zones, self._last_ai_ctx, pair
                )
                
                # IA reprovou?
                if not should_trade:
                    return None, f"🤖-❌ IA bloqueou: {ai_reason[:30]}... ({confidence}%)"
                
                # IA aprovou: adiciona confiança na descrição
                desc = f"{desc} | 🤖✓{confidence}%"
                
            except Exception:
                # Se IA falhar, continua sem ela (não bloqueia operação)
                desc = f"{desc} | ⚠️ IA offline"

        return signal, desc

    def get_sr_zones(self, pair):
        """Retorna zonas S/R analisadas para um par"""
        return self.sr_zones.get(pair, None)

    def on_win(self):
        pass

    def on_loss(self):
        pass

