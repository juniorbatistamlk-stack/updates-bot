# utils/smart_trader.py
"""
Sistema de Trading Inteligente - Profissional
Analisa multiplos pares e prioriza o melhor sinal
COM VALIDAÇÃO DE IA INTEGRADA E APRENDIZADO
+ FILTRO ANTI-S/R: Bloqueia operações contra zonas fortes
"""
import time
from utils.trade_history import TradeHistory
from utils.indicators import calculate_atr
from utils.sr_zones import detect_swing_highs_lows, create_sr_zones, detect_trend_structure

# Tentar importar analisador avançado de S/R
try:
    from utils.sr_zones_analyzer import sr_analyzer
    SR_ANALYZER_ADVANCED = True
except ImportError:
    SR_ANALYZER_ADVANCED = False
    sr_analyzer = None

# Tentar importar analisador de movimentação Micro/Macro
try:
    from utils.price_movement_analyzer import analyze_movement
    MOVEMENT_ANALYZER_AVAILABLE = True
except ImportError:
    MOVEMENT_ANALYZER_AVAILABLE = False
    analyze_movement = None


class SmartTrader:
    def __init__(self, api, strategy, pairs, memory, pair_rankings=None, ai_analyzer=None):
        """
        Args:
            api: IQHandler
            strategy: Instancia da estrategia
            pairs: Lista de paridades
            memory: TradingMemory
            pair_rankings: Dict com win_rate por par (do backtest)
            ai_analyzer: AIAnalyzer para validacao com IA
        """
        self.api = api
        self.strategy = strategy
        self.pairs = pairs
        self.memory = memory
        self.pair_rankings = pair_rankings or {}
        self.ai_analyzer = ai_analyzer
        self.is_trading = False  # Lock para 1 trade por vez
        self.current_trade = None
        self.last_order_opened = False  # True apenas quando a ordem realmente abriu
        self.system_log_func = None  # Função para logs do sistema (IA/IQ)
        
        # Sistema de aprendizado
        self.trade_history = TradeHistory()

        # Throttle leve para não poluir demais o painel (a análise acontece em bursts)
        self._last_scan_log_ts = 0.0
        self._scan_log_min_interval = 2.0
        # Cooldown por par quando uma ordem não abre ou falha
        self._pair_cooldown = {}
        
        # SESSION LEARNING - Ajusta comportamento baseado na sessão
        self._session_consecutive_losses = 0
        self._session_consecutive_wins = 0
        self._min_score = 50  # Score mínimo para executar (50 = neutro)
        self._min_confidence = 55  # Confiança mínima (já implementado)

    def _fallback_signal(self, timeframe, exclude_pairs):
        """Fallback simples baseado em momentum para não ficar sem operações."""
        for pair in self.pairs:
            if pair in exclude_pairs:
                continue

            candles = self.api.get_candles(pair, timeframe, 80, timeout_s=4, connect_timeout_s=2)
            if not candles or len(candles) < 25:
                continue

            closes = [c.get("close") for c in candles if c.get("close") is not None]
            if len(closes) < 25:
                continue

            short = sum(closes[-5:]) / 5
            mid = sum(closes[-10:-5]) / 5
            long = sum(closes[-25:]) / 25
            slope = closes[-1] - closes[-5]
            momentum = closes[-1] - long

            # Threshold proporcional (evita ruído quando preço muito pequeno)
            threshold = max(0.00012, abs(long) * 0.00008)

            if short > mid > long and slope > threshold and momentum > 0:
                # 🆕 Filtro: não pegar continuidade após 4 velas da mesma cor
                streak_block = self._check_candle_streak_filter(pair, "CALL", timeframe, candles=candles)
                if streak_block:
                    continue
                trend_block = self._check_trend_alignment(pair, "CALL", timeframe, candles=candles)
                if trend_block:
                    continue
                sr_confirm_block = self._check_sr_reversal_confirmation(pair, "CALL", timeframe, candles=candles)
                if sr_confirm_block:
                    continue
                # 🆕 Verificar conflito S/R antes de retornar CALL
                sr_block = self._check_sr_conflict(pair, "CALL", timeframe)
                if sr_block:
                    continue  # Pular este par, tentar próximo
                
                return {
                    "pair": pair,
                    "signal": "CALL",
                    "desc": f"Fallback Momentum CALL | short {short:.5f} > mid {mid:.5f} > long {long:.5f}",
                    "pattern": "FALLBACK_MOMENTUM",
                    "confidence": 60,
                    "backtest_rate": 55,
                }

            if short < mid < long and slope < -threshold and momentum < 0:
                # 🆕 Filtro: não pegar continuidade após 4 velas da mesma cor
                streak_block = self._check_candle_streak_filter(pair, "PUT", timeframe, candles=candles)
                if streak_block:
                    continue
                trend_block = self._check_trend_alignment(pair, "PUT", timeframe, candles=candles)
                if trend_block:
                    continue
                sr_confirm_block = self._check_sr_reversal_confirmation(pair, "PUT", timeframe, candles=candles)
                if sr_confirm_block:
                    continue
                # 🆕 Verificar conflito S/R antes de retornar PUT
                sr_block = self._check_sr_conflict(pair, "PUT", timeframe)
                if sr_block:
                    continue  # Pular este par, tentar próximo
                
                return {
                    "pair": pair,
                    "signal": "PUT",
                    "desc": f"Fallback Momentum PUT | short {short:.5f} < mid {mid:.5f} < long {long:.5f}",
                    "pattern": "FALLBACK_MOMENTUM",
                    "confidence": 60,
                    "backtest_rate": 55,
                }

        return None
    
    def set_system_logger(self, log_func):
        """Define função para logar mensagens do sistema (IA, IQ)"""
        self.system_log_func = log_func
    
    def _log_system(self, msg):
        """Loga no painel de sistema"""
        if self.system_log_func:
            self.system_log_func(msg)
        else:
            pass # Evitar print direto para não quebrar UI

    def _check_sr_conflict(self, pair: str, signal: str, timeframe: int) -> str:
        """
        🆕 FILTRO ANTI-S/R: Verifica se o sinal vai CONTRA uma zona de S/R forte
        
        Regras:
        - PUT em zona de SUPORTE forte = BLOQUEADO (esperar reversão para CALL)
        - CALL em zona de RESISTÊNCIA forte = BLOQUEADO (esperar reversão para PUT)
        
        Returns:
            str: Motivo do bloqueio ou None se OK
        """
        try:
            candles = self.api.get_candles(pair, int(timeframe), 100, timeout_s=3)
            if not candles or len(candles) < 50:
                return None  # Sem dados suficientes, permite operação
            
            current_price = candles[-1]['close']
            atr = calculate_atr(candles[:-1], 14) or 0.0001
            
            # Margem para considerar "próximo" da zona (0.8x ATR - menos rigoroso)
            zone_proximity = atr * 0.8
            
            # Detectar zonas de S/R
            swings = detect_swing_highs_lows(candles[:-1], window=5)
            zones = create_sr_zones(swings, tolerance=atr * 0.5, max_zones=10)
            
            if not zones:
                return None  # Sem zonas detectadas
            
            # Separar suportes e resistências
            supports = []
            resistances = []
            
            for zone in zones:
                zone_price = zone.get('price', zone.get('level', 0))
                zone_touches = zone.get('touches', zone.get('strength', 1))
                
                if zone_price < current_price:
                    supports.append({'price': zone_price, 'touches': zone_touches})
                else:
                    resistances.append({'price': zone_price, 'touches': zone_touches})
            
            # Verificar suporte mais próximo - só bloqueia se MUITO forte (3+ toques)
            if signal == "PUT" and supports:
                nearest_support = max(supports, key=lambda x: x['price'])
                distance = current_price - nearest_support['price']
                
                # Se estamos MUITO PERTO do suporte E zona forte (3+ toques), bloquear PUT
                if distance <= zone_proximity and nearest_support['touches'] >= 3:
                    # Exceção: permitir rompimento quando houver evidência forte de impulso
                    if MOVEMENT_ANALYZER_AVAILABLE and analyze_movement:
                        try:
                            mv = analyze_movement(pair, candles)
                            micro_dir = (mv.get("micro") or {}).get("direction")
                            macro_dir = (mv.get("macro") or {}).get("direction")
                            micro_move = ((mv.get("micro") or {}).get("movement") or "").lower()
                            bearish_score = float(mv.get("bearish_score", 50) or 50)
                            div = mv.get("divergence") or {}
                            div_on = bool(div.get("detected"))
                            div_type = (div.get("type") or "").lower()

                            last = candles[-1] or {}
                            o = last.get("open")
                            c = last.get("close")
                            h = last.get("max", last.get("high"))
                            l = last.get("min", last.get("low"))
                            last_range = (h - l) if (h is not None and l is not None) else 0
                            last_body = abs((c - o)) if (c is not None and o is not None) else 0
                            last_body_pct = (last_body / last_range * 100) if last_range and last_range > 0 else 0
                            last_is_red = (c is not None and o is not None and c < o)

                            breakout_ok = (
                                micro_dir == "baixa"
                                and macro_dir == "baixa"
                                and micro_move in ("impulso_baixa", "acelerando")
                                and bearish_score >= 65
                                and (not div_on or div_type != "bullish")
                                and last_is_red
                                and last_body_pct >= 55
                            )
                            if breakout_ok:
                                return None
                        except Exception:
                            pass
                    return f"PUT bloqueado: SUPORTE forte {nearest_support['price']:.5f} ({nearest_support['touches']} toques)"
            
            # Verificar resistência mais próxima - só bloqueia se MUITO forte (3+ toques)
            if signal == "CALL" and resistances:
                nearest_resistance = min(resistances, key=lambda x: x['price'])
                distance = nearest_resistance['price'] - current_price
                
                # Se estamos MUITO PERTO da resistência E zona forte (3+ toques), bloquear CALL
                if distance <= zone_proximity and nearest_resistance['touches'] >= 3:
                    # Exceção: permitir rompimento quando houver evidência forte de impulso
                    if MOVEMENT_ANALYZER_AVAILABLE and analyze_movement:
                        try:
                            mv = analyze_movement(pair, candles)
                            micro_dir = (mv.get("micro") or {}).get("direction")
                            macro_dir = (mv.get("macro") or {}).get("direction")
                            micro_move = ((mv.get("micro") or {}).get("movement") or "").lower()
                            bullish_score = float(mv.get("bullish_score", 50) or 50)
                            div = mv.get("divergence") or {}
                            div_on = bool(div.get("detected"))
                            div_type = (div.get("type") or "").lower()

                            last = candles[-1] or {}
                            o = last.get("open")
                            c = last.get("close")
                            h = last.get("max", last.get("high"))
                            l = last.get("min", last.get("low"))
                            last_range = (h - l) if (h is not None and l is not None) else 0
                            last_body = abs((c - o)) if (c is not None and o is not None) else 0
                            last_body_pct = (last_body / last_range * 100) if last_range and last_range > 0 else 0
                            last_is_green = (c is not None and o is not None and c > o)

                            breakout_ok = (
                                micro_dir == "alta"
                                and macro_dir == "alta"
                                and micro_move in ("impulso_alta", "acelerando")
                                and bullish_score >= 65
                                and (not div_on or div_type != "bearish")
                                and last_is_green
                                and last_body_pct >= 55
                            )
                            if breakout_ok:
                                return None
                        except Exception:
                            pass
                    return f"CALL bloqueado: RESISTÊNCIA forte {nearest_resistance['price']:.5f} ({nearest_resistance['touches']} toques)"
            
            return None  # Nenhum conflito forte detectado
            
        except Exception:
            return None  # Em caso de erro, permitir operação

    def _candle_color(self, candle: dict):
        """Retorna 'GREEN', 'RED' ou None (doji/indefinido)."""
        try:
            o = candle.get("open")
            c = candle.get("close")
            if o is None or c is None:
                return None
            if c > o:
                return "GREEN"
            if c < o:
                return "RED"
            return None
        except Exception:
            return None

    def _non_doji_colors(self, candles, max_len: int = 20):
        colors = []
        for candle in candles[-max_len:]:
            col = self._candle_color(candle)
            if col:
                colors.append(col)
        return colors

    def _check_candle_streak_filter(self, pair: str, signal: str, timeframe: int, candles=None):
        """Filtro: não pegar continuidade após 4 velas da mesma cor.

        Regra principal:
        - CALL bloqueado se há 4+ velas VERDES consecutivas (ignorando doji).
        - PUT bloqueado se há 4+ velas VERMELHAS consecutivas (ignorando doji).

        Regra extra (após quebrar a sequência):
        - Se a vela oposta acabou de aparecer após 4+ velas, só libera operar na direção
          anterior se o Micro/Macro não indicar reversão.
        """
        try:
            if signal not in ("CALL", "PUT"):
                return None

            if candles is None:
                candles = self.api.get_candles(pair, int(timeframe), 60, timeout_s=3)
            if not candles or len(candles) < 10:
                return None

            colors = self._non_doji_colors(candles, max_len=20)
            if len(colors) < 5:
                return None

            desired = "GREEN" if signal == "CALL" else "RED"
            last = colors[-1]

            # run atual
            run_len = 1
            for i in range(len(colors) - 2, -1, -1):
                if colors[i] == last:
                    run_len += 1
                else:
                    break

            # 1) Bloquear continuidade após 4 velas
            if last == desired and run_len >= 4:
                return f"{signal} bloqueado: {run_len} velas {('VERDES' if desired=='GREEN' else 'VERMELHAS')} seguidas (aguarde 1 vela oposta)"

            # 2) Sequência quebrou: checar reversão antes de voltar a operar na direção anterior
            if last != desired:
                prev_color = None
                prev_len = 0

                j = len(colors) - run_len - 1
                if j >= 0:
                    prev_color = colors[j]
                    prev_len = 1
                    for k in range(j - 1, -1, -1):
                        if colors[k] == prev_color:
                            prev_len += 1
                        else:
                            break

                if prev_color == desired and prev_len >= 4:
                    if not MOVEMENT_ANALYZER_AVAILABLE:
                        return f"{signal} bloqueado: possível reversão após {prev_len} velas seguidas (aguarde confirmação)"

                    mv = analyze_movement(pair, candles)
                    macro_dir = (mv.get("macro") or {}).get("direction")
                    bearish_score = float(mv.get("bearish_score", 50) or 50)
                    bullish_score = float(mv.get("bullish_score", 50) or 50)
                    div = mv.get("divergence") or {}
                    div_type = (div.get("type") or "").lower()
                    div_on = bool(div.get("detected"))

                    if signal == "CALL":
                        reversal_risk = (macro_dir != "alta") or (bearish_score >= 60) or (div_on and div_type == "bearish")
                        if reversal_risk:
                            return f"CALL bloqueado: sequência de alta quebrou e há sinal de reversão (macro={macro_dir}, bear={bearish_score:.0f}%)"
                    else:
                        reversal_risk = (macro_dir != "baixa") or (bullish_score >= 60) or (div_on and div_type == "bullish")
                        if reversal_risk:
                            return f"PUT bloqueado: sequência de baixa quebrou e há sinal de reversão (macro={macro_dir}, bull={bullish_score:.0f}%)"

            return None
        except Exception:
            return None

    def _get_trend_label(self, candles) -> str:
        """Retorna 'UPTREND', 'DOWNTREND' ou 'LATERAL' a partir da estrutura."""
        try:
            struct = detect_trend_structure(candles[:-1])
            if struct == 'BULLISH':
                return 'UPTREND'
            if struct == 'BEARISH':
                return 'DOWNTREND'
            return 'LATERAL'
        except Exception:
            return 'LATERAL'

    def _check_trend_alignment(self, pair: str, signal: str, timeframe: int, candles=None):
        """Filtro: nunca operar contra a tendência (somente a favor)."""
        try:
            if signal not in ("CALL", "PUT"):
                return None

            expected_dir = "alta" if signal == "CALL" else "baixa"

            if candles is None:
                candles = self.api.get_candles(pair, int(timeframe), 80, timeout_s=3)
            if not candles or len(candles) < 30:
                return None

            # ✅ Sempre consultar Micro + Macro tendência (quando disponível)
            if MOVEMENT_ANALYZER_AVAILABLE and analyze_movement:
                try:
                    mv = analyze_movement(pair, candles)
                    micro_dir = (mv or {}).get("micro", {}).get("direction")
                    macro_dir = (mv or {}).get("macro", {}).get("direction")

                    # Se não vier direção válida, cai para fallback estrutural
                    if micro_dir in ("alta", "baixa", "lateral") and macro_dir in ("alta", "baixa", "lateral"):
                        if micro_dir == expected_dir and macro_dir == expected_dir:
                            return None

                        # Conservador: lateral ou desalinhado bloqueia
                        if micro_dir == "lateral" or macro_dir == "lateral":
                            return f"{signal} bloqueado: micro/macro lateral (micro={micro_dir}, macro={macro_dir})"
                        return f"{signal} bloqueado: micro/macro contra tendência (micro={micro_dir}, macro={macro_dir})"
                except Exception:
                    # Se o analisador falhar por qualquer motivo, mantemos um fallback simples
                    pass

            trend = self._get_trend_label(candles)

            if trend == 'UPTREND' and signal == 'CALL':
                return None
            if trend == 'DOWNTREND' and signal == 'PUT':
                return None

            if trend == 'LATERAL':
                return f"{signal} bloqueado: tendência lateral (sem direção clara)"
            return f"{signal} bloqueado: contra tendência ({trend})"
        except Exception:
            return None

    def _check_sr_reversal_confirmation(self, pair: str, signal: str, timeframe: int, candles=None):
        """Filtro S/R: em zonas de suporte/resistência, só operar após confirmação de reversão.

        - CALL perto de SUPORTE exige confirmação
        - PUT perto de RESISTÊNCIA exige confirmação
        """
        try:
            if signal not in ("CALL", "PUT"):
                return None

            if candles is None:
                candles = self.api.get_candles(pair, int(timeframe), 100, timeout_s=3)
            if not candles or len(candles) < 50:
                return None

            current_price = candles[-1].get('close')
            if current_price is None:
                return None

            atr = calculate_atr(candles[:-1], 14) or 0.0001
            zone_proximity = atr * 0.8

            swings = detect_swing_highs_lows(candles[:-1], window=5)
            zones = create_sr_zones(swings, tolerance=atr * 0.5, max_zones=10)
            if not zones:
                return None

            supports = []
            resistances = []
            for zone in zones:
                zone_price = zone.get('price', zone.get('level', 0))
                zone_touches = zone.get('touches', zone.get('strength', 1))
                if zone_price < current_price:
                    supports.append({'price': zone_price, 'touches': zone_touches})
                else:
                    resistances.append({'price': zone_price, 'touches': zone_touches})

            near_support = None
            if supports:
                ns = max(supports, key=lambda x: x['price'])
                if (current_price - ns['price']) <= zone_proximity:
                    near_support = ns

            near_resistance = None
            if resistances:
                nr = min(resistances, key=lambda x: x['price'])
                if (nr['price'] - current_price) <= zone_proximity:
                    near_resistance = nr

            needs_confirm = (signal == "CALL" and near_support is not None) or (signal == "PUT" and near_resistance is not None)
            if not needs_confirm:
                return None

            if not MOVEMENT_ANALYZER_AVAILABLE:
                return f"{signal} bloqueado: em zona de S/R — exige confirmação de reversão"

            mv = analyze_movement(pair, candles)
            micro = mv.get('micro') or {}
            patterns = (micro.get('patterns') or {})
            micro_dir = (micro.get('direction') or '').lower()
            micro_move = (micro.get('movement') or '').lower()

            div = mv.get('divergence') or {}
            div_on = bool(div.get('detected'))
            div_type = (div.get('type') or '').lower()

            want_dir = 'alta' if signal == 'CALL' else 'baixa'
            ok_dir = (micro_dir == want_dir)
            strong_pattern = bool(patterns.get('engulfing') or patterns.get('pin_bar'))
            is_reversal = (micro_move == 'reversao')
            div_ok = div_on and ((signal == 'CALL' and div_type == 'bullish') or (signal == 'PUT' and div_type == 'bearish'))

            if ok_dir and (strong_pattern or is_reversal or div_ok):
                return None

            zone_txt = "SUPORTE" if signal == 'CALL' else "RESISTÊNCIA"
            return f"{signal} bloqueado: próximo de {zone_txt} — aguarde confirmação de reversão"
        except Exception:
            return None

    def _explicar_entrada(self, desc: str, signal: str, pattern: str) -> str:
        """
        Gera explicação humanizada do motivo da entrada.
        Ex: 'Entrando em CALL devido fluxo de vela de alta com força compradora'
        """
        desc_upper = desc.upper()
        pattern_upper = pattern.upper()
        direcao = "alta" if signal == "CALL" else "baixa"
        
        # Detectar tipo de setup
        if "FLUXO" in desc_upper or "MOMENTUM" in pattern_upper:
            return f"Fluxo de vela de {direcao} detectado - força {'compradora' if signal == 'CALL' else 'vendedora'} dominante"
        
        elif "REVERSÃO" in desc_upper or "REVERSAL" in pattern_upper:
            if "SUPORTE" in desc_upper or "SUPPORT" in pattern_upper:
                return f"Reversão confirmada em zona de SUPORTE - preço rejeitou fundo e sinaliza {direcao}"
            elif "RESISTÊNCIA" in desc_upper or "RESIST" in pattern_upper:
                return f"Reversão confirmada em zona de RESISTÊNCIA - preço rejeitou topo e sinaliza {direcao}"
            else:
                return f"Padrão de reversão detectado - mercado mudando direção para {direcao}"
        
        elif "MARUBOZU" in pattern_upper:
            return f"Vela MARUBOZU de {direcao} - corpo cheio sem pavios indica força extrema"
        
        elif "THREE" in pattern_upper or "SOLDIERS" in pattern_upper or "CROWS" in pattern_upper:
            return f"Padrão 3 velas consecutivas de {direcao} - confirmação de tendência forte"
        
        elif "ENGULF" in pattern_upper or "ENGOLFO" in desc_upper:
            return f"Engolfo de {direcao} - vela atual engoliu anterior, sinalizando mudança de controle"
        
        elif "IMPULSE" in pattern_upper or "IMPULSO" in desc_upper:
            return f"Vela de impulso de {direcao} - aceleração do movimento com volume"
        
        elif "HAMMER" in pattern_upper or "MARTELO" in desc_upper:
            return "Martelo detectado em suporte - rejeição de preço mais baixo"
        
        elif "SHOOTING" in pattern_upper or "STAR" in pattern_upper:
            return "Shooting Star em resistência - rejeição de preço mais alto"
        
        elif "PIN_BAR" in pattern_upper:
            return f"Pin Bar de {direcao} - pavio longo indicando rejeição de nível"
        
        elif "MORNING" in pattern_upper:
            return "Morning Star - padrão de reversão de baixa para alta"
        
        elif "EVENING" in pattern_upper:
            return "Evening Star - padrão de reversão de alta para baixa"
        
        elif "BLACK" in desc_upper:
            return f"Setup BLACK FLEX a favor da tendência - fluxo institucional de {direcao}"
        
        elif "FALLBACK" in pattern_upper:
            return f"Momentum simples detectado - preço em movimento de {direcao}"
        
        else:
            # Fallback genérico
            return f"Setup técnico identificado para {signal} - condições favoráveis para {direcao}"
        
    def analyze_all_pairs(self, timeframe, exclude_pairs=None):
        """
        Analisa todos os pares e retorna o melhor sinal
        COM TIMEOUT para evitar travamentos
        
        Returns:
            dict: {pair, signal, desc, confidence} ou None
        """
        start_time = time.time()
        max_analysis_time = 25  # Máximo 25 segundos de análise para manter UI fluida
        
        signals = []
        exclude = set(exclude_pairs or [])

        # Excluir pares em cooldown antes da varredura
        for pair, cooldown_candles in list(self._pair_cooldown.items()):
            if cooldown_candles > 0:
                exclude.add(pair)

        # Logar que está varrendo todos os ativos
        now = time.time()
        if now - self._last_scan_log_ts >= self._scan_log_min_interval:
            total = len(self.pairs)
            skipped = len(exclude)
            if skipped:
                self._log_system(f"[AI] 🔎 Escaneando {total} ativos (M{timeframe})... (pulando {skipped})")
            else:
                self._log_system(f"[AI] 🔎 Escaneando {total} ativos (M{timeframe})...")
            self._last_scan_log_ts = now
        
        for idx, pair in enumerate(self.pairs):
            # TIMEOUT CHECK: se passou do tempo limite, abortar análise
            elapsed = time.time() - start_time
            if elapsed > max_analysis_time:
                self._log_system(f"[AI] ⏱️ TIMEOUT de análise ({elapsed:.0f}s). Usando melhor sinal encontrado.")
                break
            
            if pair in exclude:
                continue
            
            # TIMEOUT CHECK mais frequente: a cada par
            elapsed = time.time() - start_time
            if elapsed > max_analysis_time:
                self._log_system(f"[AI] ⏱️ TIMEOUT ({elapsed:.0f}s). Finalizando análise.")
                break
            
            # Mostrar claramente que está analisando cada par
            self._log_system(f"[AI] 🔎 Analisando: {pair} ({idx+1}/{len(self.pairs)})")
            
            try:
                signal, desc = self.strategy.check_signal(pair, timeframe)
            except Exception as e:
                # Se houver erro ao processar o par, continua para o próximo
                self._log_system(f"[AI] ⚠️ Erro ao analisar {pair}: {str(e)[:30]}")
                continue
            
            if signal:
                # 🆕 FILTRO ANTI-S/R: Não entrar CONTRA zonas fortes
                sr_blocked = self._check_sr_conflict(pair, signal, timeframe)
                if sr_blocked:
                    self._log_system(f"[AI] 🚫 {pair}: {sr_blocked}")
                    continue  # Pula este sinal - contra zona S/R

                # Buscar candles uma vez para os próximos filtros
                candles_for_filters = self.api.get_candles(pair, int(timeframe), 60, timeout_s=3)
                if not candles_for_filters or len(candles_for_filters) < 30:
                    continue

                # 🆕 FILTRO: nunca operar contra tendência
                trend_blocked = self._check_trend_alignment(pair, signal, timeframe, candles=candles_for_filters)
                if trend_blocked:
                    self._log_system(f"[AI] 🚫 {pair}: {trend_blocked}")
                    continue

                # 🆕 FILTRO 4 VELAS (MESMA COR): evitar continuidade após sequência longa
                streak_blocked = self._check_candle_streak_filter(pair, signal, timeframe, candles=candles_for_filters)
                if streak_blocked:
                    self._log_system(f"[AI] 🚫 {pair}: {streak_blocked}")
                    continue

                # 🆕 FILTRO S/R: em zonas, só operar após confirmação de reversão
                sr_confirm_blocked = self._check_sr_reversal_confirmation(pair, signal, timeframe, candles=candles_for_filters)
                if sr_confirm_blocked:
                    self._log_system(f"[AI] 🚫 {pair}: {sr_confirm_blocked}")
                    continue
                
                # 🆕 LOG: Mostrar que encontrou sinal neste par
                self._log_system(f"[AI] ✅ {pair}: {signal} detectado")
                
                # Calcular confianca baseado em:
                # 1. Backtest win rate (40%)
                # 2. Memoria historica (30%)
                # 3. Forca do padrao (30%)
                
                base_confidence = 50
                
                # Bonus do backtest
                backtest_rate = self.pair_rankings.get(pair, 50)
                if backtest_rate is None:
                    backtest_rate = 50
                backtest_bonus = (backtest_rate - 50) * 0.4  # +/- 20 pontos max
                
                # Bonus da memoria
                pattern = desc.split("|")[0].strip() if "|" in desc else desc
                memory_rate = self.memory.get_pattern_confidence(pattern)
                memory_bonus = (memory_rate - 50) * 0.3  # +/- 15 pontos max
                
                # Bonus do padrao (extrair do desc se possivel)
                pattern_bonus = 0
                if "REVERSAO" in desc.upper():
                    pattern_bonus = 10  # Reversoes tendem a ser mais confiaveis
                elif "TENDENCIA" in desc.upper():
                    pattern_bonus = 5
                
                # Boost para fluxo a favor da tendência
                if "FLUXO" in desc.upper() or "BREAKOUT" in desc.upper():
                    pattern_bonus += 8
                
                final_confidence = base_confidence + backtest_bonus + memory_bonus + pattern_bonus
                final_confidence = max(25, min(97, final_confidence))
                
                signals.append({
                    "pair": pair,
                    "signal": signal,
                    "desc": desc,
                    "pattern": pattern,
                    "confidence": final_confidence,
                    "backtest_rate": backtest_rate
                })
            else:
                # Log quando a estratégia não retorna sinal (diagnóstico)
                if desc:  # Se retornou descrição mas sem sinal (ex: "Aguardando setup")
                    pass  # Evitar poluir o log com "aguardando" a cada segundo
        
        if not signals:
            fallback = self._fallback_signal(timeframe, exclude)
            if fallback:
                self._log_system("[AI] ⚡ Nenhum sinal nas estratégias. Usando fallback momentum.")
                signals.append(fallback)
            else:
                self._log_system("[AI] ⏳ Nenhum sinal encontrado nesta varredura")
                return None
        
        # 🆕 LOG: Mostrar resumo dos sinais encontrados
        pairs_with_signals = [s['pair'] for s in signals]
        self._log_system(f"[AI] 📊 {len(signals)} sinais em: {', '.join(pairs_with_signals[:5])}")
        
        # Ordenar por confianca (maior primeiro)
        signals.sort(key=lambda x: x["confidence"], reverse=True)
        
        best = signals[0]
        self._log_system(f"[AI] 🎯 Melhor: {best['pair']} ({best['signal']}) conf={best['confidence']:.0f}%")
        
        # VERIFICAR APRENDIZADO - Evitar padrões que dão loss
        pattern = best.get("pattern", best.get("desc", ""))
        if self.trade_history.should_avoid_pattern(pattern):
            self._log_system(f"[AI] ⚠️ Padrão '{pattern[:20]}' tem histórico ruim - pulando...")
            if len(signals) > 1:
                best = signals[1]
            else:
                return None
        
        # VALIDAÇÃO COM IA (se disponível) - modo agressivo: IA é consultiva
        if self.ai_analyzer and getattr(self.ai_analyzer, 'is_enabled', lambda: True)():
            learning = self.trade_history.get_learning_summary()
            self._log_system(f"[AI] 🧠 IA ativa: validando entradas (M{timeframe})")
            self._log_system(f"[AI] Histórico: {learning.get('total_trades', 0)} trades | WR: {learning.get('win_rate', 0):.0f}%")

            if learning.get('avoid_patterns'):
                ap = learning.get('avoid_patterns') or []
                if ap:
                    self._log_system(f"[AI] ⚠️ Evitando: {', '.join(ap[:3])}")

            # Tenta validar o melhor sinal e, se rejeitar, percorre os próximos
            for candidate in signals:
                # TIMEOUT CHECK na validação IA também
                elapsed = time.time() - start_time
                if elapsed > max_analysis_time:
                    self._log_system("[AI] ⏱️ TIMEOUT na validação IA. Sem confirmação — não operar.")
                    return None
                
                pair = candidate["pair"]
                self._log_system(f"[AI] Analisando gráfico de {pair}...")

                candles = self.api.get_candles(pair, int(timeframe), 60)
                if not candles or len(candles) < 30:
                    continue

                streak_blocked = self._check_candle_streak_filter(pair, candidate.get("signal"), timeframe, candles=candles)
                if streak_blocked:
                    self._log_system(f"[AI] 🚫 {pair}: {streak_blocked}")
                    continue

                trend_blocked = self._check_trend_alignment(pair, candidate.get("signal"), timeframe, candles=candles)
                if trend_blocked:
                    self._log_system(f"[AI] 🚫 {pair}: {trend_blocked}")
                    continue

                sr_confirm_blocked = self._check_sr_reversal_confirmation(pair, candidate.get("signal"), timeframe, candles=candles)
                if sr_confirm_blocked:
                    self._log_system(f"[AI] 🚫 {pair}: {sr_confirm_blocked}")
                    continue

                # Zonas S/R: preferir cache da estratégia (quando existir), senão detectar por swings
                zones = []
                if hasattr(self.strategy, 'sr_zones') and isinstance(getattr(self.strategy, 'sr_zones'), dict):
                    cached = self.strategy.sr_zones.get(pair)
                    if cached:
                        zones = cached
                if not zones:
                    atr = calculate_atr(candles[:-1], 14) or 0.0001
                    swings = detect_swing_highs_lows(candles[:-1], window=5)
                    zones = create_sr_zones(swings, tolerance=atr * 0.5, max_zones=5)

                struct = detect_trend_structure(candles[:-1])
                if struct == 'BULLISH':
                    trend = 'UPTREND'
                elif struct == 'BEARISH':
                    trend = 'DOWNTREND'
                else:
                    trend = 'LATERAL'

                # Obter contexto estruturado da estratégia (se disponível)
                ai_ctx = {}
                if hasattr(self.strategy, 'get_last_ai_context'):
                    ai_ctx = self.strategy.get_last_ai_context()

                # SCORE PRÉ-ANÁLISE - Avaliação objetiva antes da IA
                if hasattr(self.ai_analyzer, 'calculate_trade_score'):
                    score, breakdown = self.ai_analyzer.calculate_trade_score(
                        candidate["signal"], trend, zones, candles, candidate["desc"]
                    )
                    # Ajustar score mínimo baseado em session learning
                    effective_min = self._min_score
                    if self._session_consecutive_losses >= 3:
                        effective_min = 60  # Mais conservador após 3 losses
                        self._log_system(f"[AI] ⚠️ Modo conservador ativo (3+ losses)")
                    
                    self._log_system(f"[AI] 📊 Score: {score}/{effective_min} | {' '.join(f'{k}:{v}' for k,v in list(breakdown.items())[:3])}")
                    
                    if score < effective_min:
                        self._log_system(f"[AI] 🛑 Score baixo ({score} < {effective_min}). Pulando {pair}...")
                        candidate["ai_rejected"] = True
                        candidate["ai_reason"] = f"Score {score} < {effective_min}"
                        continue  # Próximo candidato

                ai_confirm, ai_confidence, ai_reason = self.ai_analyzer.analyze_signal(
                    candidate["signal"], candidate["desc"], candles, zones, trend, pair, ai_context=ai_ctx
                )

                if ai_confirm:
                    self._log_system(f"[AI] ✅ Confirmado ({ai_confidence}%): {ai_reason}")
                    candidate["confidence"] = (candidate["confidence"] + ai_confidence) / 2
                    candidate["ai_reason"] = ai_reason
                    best = candidate
                    break
                else:
                    self._log_system(f"[AI] ❌ Rejeitado: {ai_reason}")
                    candidate["ai_rejected"] = True
                    candidate["ai_reason"] = ai_reason
            else:
<<<<<<< Updated upstream
                # OPÇÃO B: Respeitar decisão da IA - não executar fallback
                self._log_system("[AI] 🛑 IA rejeitou todos os sinais. Aguardando melhor setup...")
                return None  # Não executar quando IA rejeita
=======
                self._log_system("[AI] 🚫 IA rejeitou todos os candidatos. Sem trade nesta varredura.")
                return None
>>>>>>> Stashed changes
        elif self.ai_analyzer:
            # IA existe mas foi desabilitada (ex: chave inválida)
            reason = getattr(self.ai_analyzer, 'disabled_reason', None)
            if reason:
                self._log_system(f"[AI] ⚠️ IA desabilitada: {reason}")
        
        # OPÇÃO B: Verificar confiança mínima antes de executar
        MIN_CONFIDENCE = 55
        if best.get("confidence", 0) < MIN_CONFIDENCE:
            self._log_system(f"[AI] ⚠️ Confiança baixa ({best.get('confidence', 0):.0f}% < {MIN_CONFIDENCE}%). Pulando...")
            return None
        
        return best
    
    def execute_trade(self, trade_info, cfg, log_func):
        """
        Executa um trade e aguarda resultado
        
        Args:
            trade_info: Dict com pair, signal, desc, confidence
            cfg: Config
            log_func: Funcao de log
            
        Returns:
            float: Lucro/prejuizo
        """
        # Garantir que lock sempre seja liberado
        try:
            # Reset lock no início para evitar travamento
            self.is_trading = False
            self.last_order_opened = False
            
            # VERIFICAR CONEXÃO ANTES DE EXECUTAR
            self._log_system("[IQ] 🔍 Verificando saúde da conexão...")
            if not self.api._ensure_connected():
                log_func("[bold red]❌ FALHA: Não foi possível estabelecer conexão[/bold red]")
                log_func("[yellow]⚠️ Verifique sua internet e tente novamente[/yellow]")
                return 0
            
            self._log_system("[IQ] ✓ Conexão verificada: OK")
            
            self.is_trading = True
            self.current_trade = trade_info
            
            pair = trade_info["pair"]
            signal = trade_info["signal"]
            desc = trade_info.get("desc", "")
            pattern = trade_info.get("pattern", desc)
            
            log_func(f"[green]💰 Executando ordem [{cfg.option_type}]: {signal} em {pair} (R${cfg.amount:.2f})[/green]")
            
            # === EXPLICAÇÃO DO MOTIVO DA ENTRADA ===
            motivo = self._explicar_entrada(desc, signal, pattern)
            log_func(f"[cyan]📝 MOTIVO: {motivo}[/cyan]")

            # === TRAVA DE TEMPO (VIRADA DE VELA) ===
            # Só permite abertura no INÍCIO da nova vela (primeiro 5s).
            # Motivo: na IQ, abrir no fim da vela pode gerar expiração curta (poucos segundos).
            entry_window_s = 5.0
            candle_duration = float(cfg.timeframe) * 60.0

            def _elapsed_in_candle(ts: float) -> float:
                return float(ts) % candle_duration

            try:
                st = self.api.get_server_timestamp()
                elapsed0 = _elapsed_in_candle(st)
                
                # Permitir primeiros 5s OU últimos 2s (antecipação 58s/59s)
                valid_window = (elapsed0 <= entry_window_s) or (elapsed0 >= candle_duration - 2.0)
                
                if not valid_window:
                    self.last_order_opened = False
                    log_func(
                        f"[yellow]⏳ Entrada bloqueada: estamos em {elapsed0:.2f}s da vela. "
                        f"Janela: 0-5s ou 58-60s.[/yellow]"
                    )
                    return 0
            except Exception:
                self.last_order_opened = False
                log_func("[yellow]⚠️ Não foi possível confirmar o timing do servidor. Entrada bloqueada.[/yellow]")
                return 0
            
            try:
                def _should_retry_open(reason: str) -> bool:
                    r = str(reason).lower()
                    # retry apenas em falhas transitórias (latência/conexão/rejeição momentânea)
                    transient_keys = (
                        "timeout",
                        "socket",
                        "closed",
                        "try",
                        "tempor",
                        "reconnect",
                        "not found",
                        "rejected",
                        "no such",
                        "unknown",
                    )
                    non_retry_keys = (
                        "asset",
                        "closed asset",
                        "market closed",
                        "not opened",
                        "insufficient",
                        "saldo",
                        "limit",
                        "min",
                        "max",
                    )
                    if any(k in r for k in non_retry_keys):
                        return False
                    return any(k in r for k in transient_keys)

                # Executar trade com pequenas tentativas (evita perder entrada por rejeição momentânea)
                max_open_attempts = 3
                check, order_id = False, ""
                for attempt in range(1, max_open_attempts + 1):
                    # Revalidar janela antes de cada tentativa para evitar abrir após virar.
                    try:
                        st_now = self.api.get_server_timestamp()
                        elapsed = _elapsed_in_candle(st_now)
                        # Permitir primeiros 5s OU últimos 2s (antecipação 58s/59s)
                        valid_window_retry = (elapsed <= entry_window_s) or (elapsed >= candle_duration - 2.0)
                        
                        if not valid_window_retry:
                            self._log_system(
                                f"[IQ] ⛔ Janela de entrada perdida (elapsed {elapsed:.2f}s). Abortando abertura."
                            )
                            check, order_id = False, "EntryWindowMissed"
                            break
                    except Exception:
                        check, order_id = False, "ServerTimeUnavailable"
                        break

                    self._log_system(f"[IQ] Tentando ({attempt}/{max_open_attempts}): {pair} {signal}...")
                    check, order_id = self.api.buy(cfg.amount, pair, signal, cfg.timeframe)
                    self._log_system(f"[IQ] Resposta: check={check}, id={order_id}")
                    if check:
                        break
                    if attempt < max_open_attempts and _should_retry_open(order_id):
                        # pequeno delay para não bater rate-limit e permitir reconexão
                        time.sleep(0.6)
                        continue
                    break
                
                if check:
                    self.last_order_opened = True
                    log_func(f"[green]✓ Ordem {order_id} aberta em {pair}. Aguardando resultado...[/green]")
                    
                    # Aguardar resultado
                    result = self.api.check_win(order_id)
                    
                    if result > 0:
                        log_func(f"[bold green]✅ WIN +R${result:.2f} | {pair}[/bold green]")
                        self.memory.record_trade(pair, signal, pattern, "WIN", result, "UNKNOWN")
                        
                        # SESSION LEARNING - Reset losses, increment wins
                        self._session_consecutive_losses = 0
                        self._session_consecutive_wins += 1
                        if self._session_consecutive_wins >= 3:
                            self._log_system(f"[AI] 🔥 Sequência positiva ({self._session_consecutive_wins} wins)")
                        
                        # Salvar para aprendizado da IA
                        self.trade_history.add_trade(trade_info, "win", result)
                        
                        return result
                        
                    elif result < 0:
                        log_func(f"[red]❌ LOSS -R${abs(result):.2f} | {pair}[/red]")
                        self.memory.record_trade(pair, signal, pattern, "LOSS", result, "UNKNOWN")
                        
                        # SESSION LEARNING - Increment losses, reset wins
                        self._session_consecutive_losses += 1
                        self._session_consecutive_wins = 0
                        if self._session_consecutive_losses >= 3:
                            self._log_system(f"[AI] ⚠️ ATENÇÃO: {self._session_consecutive_losses} losses seguidos. Aumentando filtros...")
                        
                        # Salvar para aprendizado da IA
                        self.trade_history.add_trade(trade_info, "loss", result)
                        log_func("[magenta]🧠 IA aprendendo com este loss...[/magenta]")
                        
                        # Martingale
                        martingale_profit = self._execute_martingale(
                            cfg, pair, signal, pattern, log_func
                        )
                        
                        return result + martingale_profit
                    else:
                        log_func(f"[yellow]🤝 EMPATE | {pair}[/yellow]")
                        return 0
                else:
                    self.last_order_opened = False
                    reason_msg = str(order_id)
                    log_func(f"[bold red]❌ FALHA AO ABRIR ORDEM: {reason_msg}[/bold red]")
                    
                    # Mensagens específicas para erros comuns
                    error_lower = reason_msg.lower()
                    if "socket" in error_lower or "closed" in error_lower:
                        log_func("[yellow]🔄 Erro de conexão detectado. O sistema tentará reconectar...[/yellow]")
                    elif "timeout" in error_lower:
                        log_func("[yellow]⏱️ Timeout: Operação demorou muito. Tente novamente.[/yellow]")
                    else:
                        log_func("[yellow]Verifique: Saldo, Ativo aberto, Limite de trades[/yellow]")
                    # Adiciona cooldown de 2 velas para este par
                    self._pair_cooldown[pair] = max(self._pair_cooldown.get(pair, 0), 2)
                    
                    return 0
                    
            except ConnectionError as e:
                self.last_order_opened = False
                log_func(f"[bold red]❌ ERRO DE CONEXÃO: {str(e)}[/bold red]")
                log_func("[yellow]🔄 Tentando reconectar...[/yellow]")
                self.api._ensure_connected()
                return 0
            except Exception as e:
                self.last_order_opened = False
                log_func(f"[bold red]❌ ERRO CRÍTICO: {str(e)}[/bold red]")
                import traceback
                error_trace = traceback.format_exc()
                
                # Logar apenas se for erro de socket
                if "socket" in error_trace.lower():
                    log_func("[yellow]🔄 Erro de WebSocket detectado. Reconectando...[/yellow]")
                    self.api._ensure_connected()
                else:
                    log_func(f"[dim]{error_trace}[/dim]")
                
                return 0
        finally:
            # SEMPRE liberar o lock, mesmo se der erro
            self.is_trading = False
    
    def _execute_martingale(self, cfg, pair, signal, pattern, log_func):
        """Executa martingale com timing preciso (Server Side)"""
        total_profit = 0
        curr_amount = cfg.amount
        
        for level in range(cfg.martingale_levels):
            # Calcular valor do Gale (Fator 2.2 padrão)
            curr_amount *= 2.2
            
            log_func(f"[yellow]🔄 GALE {level+1}: R${curr_amount:.2f} | Aguardando ponto de entrada...[/yellow]")
            
            # === TIMING (VIRADA DE VELA) ===
            # GALE também executa no início da vela (primeiro 5s).
            entry_window_s = 5.0
            candle_duration = float(cfg.timeframe) * 60.0

            def _elapsed_in_candle(ts: float) -> float:
                return float(ts) % candle_duration

            try:
                server_time = self.api.get_server_timestamp()
                elapsed0 = _elapsed_in_candle(server_time)
            except Exception:
                log_func("[yellow]⚠️ Não foi possível sincronizar tempo do servidor para GALE.[/yellow]")
                break

            # Se não estamos no começo, esperar a próxima vela virar
            if elapsed0 > entry_window_s:
                wait_time = candle_duration - elapsed0
                log_func(f"[dim]Aguardando {wait_time:.2f}s para virar e entrar no início da vela...[/dim]")
                target = server_time + wait_time
                while True:
                    now = self.api.get_server_timestamp()
                    if now >= target:
                        break
                    time.sleep(0.25)

            # Rechecar (evita disparar tarde)
            st2 = self.api.get_server_timestamp()
            elapsed2 = _elapsed_in_candle(st2)
            
            valid_window_gale = (elapsed2 <= entry_window_s) or (elapsed2 >= candle_duration - 2.0)
            
            if not valid_window_gale:
                log_func(f"[yellow]⛔ GALE bloqueado: janela perdida (elapsed {elapsed2:.2f}s).[/yellow]")
                break
            log_func("[green]⚡ GALE DISPARADO (abertura da vela)[/green]")
            
            # Executar gale
            check, order_id = self.api.buy(curr_amount, pair, signal, cfg.timeframe)
            
            if check:
                log_func(f"[dim]Gale {level+1} executado ({order_id}). Aguardando...[/dim]")
                result = self.api.check_win(order_id)
                
                if result > 0:
                    log_func(f"[bold green]✅ GALE WIN +R${result:.2f}[/bold green]")
                    self.memory.record_trade(pair, signal, f"GALE_{level+1}_{pattern}", "WIN", result, "UNKNOWN")
                    total_profit += result
                    break
                else:
                    log_func(f"[red]❌ GALE LOSS -R${abs(result):.2f}[/red]")
                    self.memory.record_trade(pair, signal, f"GALE_{level+1}_{pattern}", "LOSS", result, "UNKNOWN")
                    total_profit += result
                    # Continua para o próximo nível do loop
            else:
                log_func("[red]Erro ao entrar no Gale[/red]")
                break
        
        return total_profit
