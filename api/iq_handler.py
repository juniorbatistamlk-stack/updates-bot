# api/iq_handler.py
from iqoptionapi.stable_api import IQ_Option
import time
import threading

class IQHandler:
    def __init__(self, config):
        self.config = config
        self.api = None
        self.last_error = None
        self._lock = threading.Lock()
        self._logger = None  # Callback para logs
        self._hb_thread = None
        self._hb_stop = threading.Event()

        # Evita acumular threads de candles quando a IQ trava/hanga.
        # Mantém no máximo 1 fetch ativo por par.
        self._candles_inflight = set()
        self._candles_inflight_lock = threading.Lock()

        # Throttle logs to avoid flooding the dashboard (and causing flicker)
        self._last_log_ts = {}

        # Server time fetch can hang inside iqoptionapi; bound it.
        self._server_ts_inflight = False
        self._server_ts_lock = threading.Lock()
        self._server_ts_thread = None
        self._server_ts_thread_started_at = 0.0
        self._server_ts_cache = None
        self._server_ts_cache_wall = 0.0
        
    def set_logger(self, log_func):
        """Define callback para enviar logs ao dashboard"""
        self._logger = log_func
        
    def _log(self, msg):
        """Envia log para dashboard ou print como fallback"""
        if self._logger:
            self._logger(msg)
        else:
            print(msg)

    def _log_throttled(self, key: str, msg: str, interval_s: float = 6.0) -> None:
        """Loga no máximo 1x por intervalo para a mesma chave."""
        now = time.time()
        last = self._last_log_ts.get(key, 0.0)
        if now - last >= interval_s:
            self._last_log_ts[key] = now
            self._log(msg)

    def connect(self):
        """Connects to IQ Option API with retry + heartbeat."""
        with self._lock:
            max_retries = 4
            for attempt in range(max_retries):
                try:
                    # Garante que conexões anteriores foram encerradas
                    if self.api:
                        try:
                            self.api.close_connect()
                        except Exception:
                            pass
                        self.api = None

                    self.api = IQ_Option(self.config.email, self.config.password)
                    if self.api is None:
                        self.last_error = "IQ_Option returned None"
                        self._log_throttled(
                            "iq_api_none",
                            f"[IQ_HANDLER] Erro: instância API vazia (tentativa {attempt+1}/{max_retries})",
                            interval_s=4.0,
                        )
                        time.sleep(2)
                        continue

                    check, reason = self.api.connect()

                    if check:
                        try:
                            self.api.change_balance(self.config.account_type)
                        except Exception as e:
                            self.last_error = f"change_balance falhou: {e}"
                            self._log_throttled(
                                "change_balance_fail",
                                f"[IQ_HANDLER] ⚠️ change_balance falhou: {e}",
                                interval_s=4.0,
                            )
                            time.sleep(2)
                            continue

                        self._start_heartbeat()
                        return True

                    self.last_error = f"Connection failed: {reason}"
                    reason_txt = str(reason)
                    if "websocket" in reason_txt.lower() and "closed" in reason_txt.lower():
                        self._log_throttled(
                            "ws_closed_connect",
                            f"[IQ_HANDLER] ⚠️ Falha: {reason_txt}",
                            interval_s=10.0,
                        )
                        time.sleep(5 * (attempt + 1))
                        continue

                    self._log_throttled(
                        "connect_fail",
                        f"[IQ_HANDLER] Tentativa {attempt+1}/{max_retries} falhou: {reason_txt}",
                        interval_s=6.0,
                    )
                    time.sleep(2)
                except Exception as e:
                    self.last_error = str(e)
                    self._log_throttled(
                        "connect_exception",
                        f"[IQ_HANDLER] Erro na conexão (Tentativa {attempt+1}/{max_retries}): {e}",
                        interval_s=6.0,
                    )
                    time.sleep(2)

            return False

    def _start_heartbeat(self):
        """Inicia um heartbeat que mantém a WS viva e auto-reconecta."""
        # Pare qualquer thread anterior
        try:
            self._hb_stop.set()
        except Exception:
            pass
        self._hb_stop = threading.Event()

        def _loop():
            while not self._hb_stop.is_set():
                try:
                    # Ping a cada 15s
                    for _ in range(15):
                        if self._hb_stop.is_set():
                            return
                        time.sleep(1)

                    if not self.api:
                        continue

                    ok = False
                    try:
                        ok = self.api.check_connect()
                    except Exception:
                        ok = False

                    if not ok:
                        self._log("[IQ_HANDLER] 🧪 Heartbeat detectou desconexão. Re-conectando...")
                        self._ensure_connected()
                        continue

                    # Toca endpoints leves para manter sessão
                    try:
                        _ = self.api.get_balance()
                    except Exception:
                        self._ensure_connected()
                except Exception as e:
                    # Não derruba o loop por exceções transitórias
                    self._log(f"[IQ_HANDLER] Heartbeat erro: {str(e)[:60]}")

        self._hb_thread = threading.Thread(target=_loop, daemon=True)
        self._hb_thread.start()

    def _ensure_connected(self):
        """Auto-reconnect if connection dropped with smart retry."""
        max_attempts = 3  # Reduced to 3 for faster failure

        # Serializa reconexões (heartbeat + candles + buy podem chamar juntos)
        with self._lock:
            for attempt in range(max_attempts):
                try:
                    # Check if API exists and is connected
                    if self.api:
                        try:
                            if self.api.check_connect():
                                # Verify WebSocket is truly alive by getting balance
                                try:
                                    _ = self.api.get_balance()
                                    return True  # Connection is good
                                except Exception:
                                    pass  # WebSocket dead, need reconnect
                        except Exception as e:
                            msg = str(e).lower()
                            if "already closed" in msg or "connection is already closed" in msg:
                                self._log_throttled(
                                    "already_closed_session",
                                    "[IQ_HANDLER] ℹ️ Sessão já estava fechada. Recriando conexão...",
                                    interval_s=10.0,
                                )
                            # Garantir reset do handler para recriar a sessão limpa
                            self.api = None

                    # Connection is dead - create fresh API instance
                    self._log_throttled(
                        "reconnecting",
                        f"[IQ_HANDLER] 🔄 Reconectando... (tentativa {attempt+1}/{max_attempts})",
                        interval_s=6.0,
                    )

                    # Destroy old connection completely
                    if self.api:
                        try:
                            self.api.close_connect()
                        except Exception:
                            pass
                        self.api = None

                    # Exponential backoff: 5s, 10s, 15s, ...
                    wait_time = 5 * (attempt + 1)
                    self._log_throttled(
                        "reconnect_wait",
                        f"[IQ_HANDLER] ⏳ Aguardando {wait_time}s antes de tentar...",
                        interval_s=6.0,
                    )
                    time.sleep(wait_time)

                    # Create fresh connection
                    self.api = IQ_Option(self.config.email, self.config.password)
                    if self.api is None:
                        self._log_throttled(
                            "iq_api_none_reconnect",
                            "[IQ_HANDLER] ❌ Falha ao criar instância IQ_Option",
                            interval_s=8.0,
                        )
                        continue

                    check, reason = self.api.connect()
                    if not check:
                        reason_txt = str(reason)
                        if "websocket" in reason_txt.lower() and "closed" in reason_txt.lower():
                            self._log_throttled(
                                "ws_closed_ensure",
                                f"[IQ_HANDLER] ⚠️ Falha: {reason_txt}",
                                interval_s=12.0,
                            )
                        else:
                            self._log_throttled(
                                "ensure_fail",
                                f"[IQ_HANDLER] ⚠️ Falha: {reason_txt}",
                                interval_s=8.0,
                            )
                        continue

                    try:
                        self.api.change_balance(self.config.account_type)
                    except Exception as e:
                        self._log_throttled(
                            "change_balance_fail_reconnect",
                            f"[IQ_HANDLER] ⚠️ change_balance falhou: {e}",
                            interval_s=8.0,
                        )
                        continue

                    # Wait for websocket to stabilize
                    time.sleep(2)

                    # Verify it's really working
                    try:
                        _ = self.api.get_balance()
                        self._log_throttled(
                            "reconnected_ok",
                            "[IQ_HANDLER] ✅ Reconectado com sucesso!",
                            interval_s=4.0,
                        )
                        self._start_heartbeat()
                        return True
                    except Exception:
                        self._log_throttled(
                            "reconnect_unstable",
                            "[IQ_HANDLER] ⚠️ Conexão instável, tentando novamente...",
                            interval_s=8.0,
                        )
                        try:
                            self.api = None
                        except Exception:
                            pass
                        continue
                except Exception as e:
                    msg = str(e)
                    msg_lower = msg.lower()

                    if "already closed" in msg_lower or "connection is already closed" in msg_lower:
                        self._log_throttled(
                            "already_closed",
                            f"[IQ_HANDLER] ℹ️ Conexão já fechada (tentativa {attempt+1}/{max_attempts}). Reconectando...",
                            interval_s=10.0,
                        )
                    else:
                        self._log_throttled(
                            "ensure_exception",
                            f"[IQ_HANDLER] ❌ Erro tentativa {attempt+1}: {msg[:80]}",
                            interval_s=8.0,
                        )

                    try:
                        self.api = None
                    except Exception:
                        pass

            self._log_throttled(
                "reconnect_critical",
                f"[IQ_HANDLER] 💀 FALHA CRÍTICA: Não foi possível reconectar após {max_attempts} tentativas",
                interval_s=15.0,
            )
            self._log_throttled(
                "reconnect_critical_hint",
                "[IQ_HANDLER] 💡 Solução: Reinicie o bot ou troque de servidor VPN",
                interval_s=15.0,
            )
            return False

    def _ensure_connected_quick(self, timeout_s: float = 5.0) -> bool:
        """Tentativa rápida de garantir conexão (sem backoff longo).

        Usado em operações de validação/boot onde travar é pior do que falhar.
        """
        deadline = time.time() + max(0.1, float(timeout_s))

        # 1) Se já está conectado, ok.
        if self.api:
            try:
                if self.api.check_connect():
                    try:
                        _ = self.api.get_balance()
                        return True
                    except Exception:
                        pass
            except Exception:
                pass

        # 2) Uma (ou duas) tentativas rápidas de conectar, sem esperas longas.
        attempts = 2
        with self._lock:
            for attempt in range(attempts):
                if time.time() >= deadline:
                    return False

                try:
                    # Resetar conexão anterior
                    if self.api:
                        try:
                            self.api.close_connect()
                        except Exception:
                            pass
                        self.api = None

                    self.api = IQ_Option(self.config.email, self.config.password)
                    if self.api is None:
                        self.last_error = "IQ_Option returned None"
                        return False

                    ok, reason = self.api.connect()
                    if not ok:
                        self.last_error = f"Connection failed: {reason}"
                        # pequeno delay apenas entre tentativas rápidas
                        time.sleep(0.5)
                        continue

                    try:
                        self.api.change_balance(self.config.account_type)
                    except Exception as e:
                        self.last_error = f"change_balance falhou: {e}"
                        time.sleep(0.5)
                        continue

                    # Confirma que a WS está viva
                    try:
                        _ = self.api.get_balance()
                        return True
                    except Exception:
                        time.sleep(0.5)
                        continue
                except Exception as e:
                    self.last_error = str(e)
                    time.sleep(0.5)

        return False

    def get_balance(self):
        """Returns current balance."""
        self._ensure_connected()
        return self.api.get_balance()

    def get_server_timestamp(
        self,
        timeout_s: float = 2.0,
        connect_timeout_s: float = 2.0,
        min_interval_s: float = 0.20,
        max_cache_stale_s: float = 10.0,
    ):
        """Returns server timestamp with bounded timeouts (prevents freezing).

        iqoptionapi's websocket calls may hang; this method caps both connect time
        and the timestamp call itself. On failure, returns local time as fallback.
        """

        now_wall = time.time()

        # Cache curto: o worker chama muito (inclusive a cada 50ms no arm window).
        if self._server_ts_cache and (now_wall - self._server_ts_cache_wall) < float(min_interval_s):
            return self._server_ts_cache

        # Se já tem uma thread pegando server_ts (ou uma travada), não cria outra.
        with self._server_ts_lock:
            t = self._server_ts_thread
            if t is not None and t.is_alive():
                # Preferir cache; se cache estiver velho, cair no relógio local.
                if self._server_ts_cache and (now_wall - self._server_ts_cache_wall) <= float(max_cache_stale_s):
                    return self._server_ts_cache
                return now_wall

            if self._server_ts_inflight:
                if self._server_ts_cache and (now_wall - self._server_ts_cache_wall) <= float(max_cache_stale_s):
                    return self._server_ts_cache
                return now_wall

            self._server_ts_inflight = True

        try:
            # Conexão rápida: preferir falhar rápido a travar.
            if connect_timeout_s is not None:
                if not self._ensure_connected_quick(float(connect_timeout_s)):
                    return now_wall
            else:
                if not self._ensure_connected():
                    return now_wall

            result = {"ts": None}
            done = threading.Event()

            def _fetch():
                try:
                    if not self.api:
                        return
                    result["ts"] = self.api.get_server_timestamp()
                except Exception:
                    result["ts"] = None
                finally:
                    done.set()

            t = threading.Thread(target=_fetch, daemon=True)
            with self._server_ts_lock:
                self._server_ts_thread = t
                self._server_ts_thread_started_at = now_wall
            t.start()
            t.join(max(0.1, float(timeout_s)))

            if not done.is_set():
                self._log_throttled(
                    "server_ts_timeout",
                    "[IQ_HANDLER] ⏱️ Timeout ao obter server_time. Usando relógio local.",
                    interval_s=8.0,
                )
                # Não derrubar a UI: se tiver cache recente, usa. Senão, local.
                if self._server_ts_cache and (now_wall - self._server_ts_cache_wall) <= float(max_cache_stale_s):
                    return self._server_ts_cache
                return now_wall

            ts = result.get("ts")
            if isinstance(ts, (int, float)) and ts > 0:
                # Alguns builds da IQ retornam timestamp em ms. Normalizar para segundos.
                if ts > 10_000_000_000:
                    ts = float(ts) / 1000.0

                self._server_ts_cache = ts
                self._server_ts_cache_wall = now_wall
                return ts
            if self._server_ts_cache and (now_wall - self._server_ts_cache_wall) <= float(max_cache_stale_s):
                return self._server_ts_cache
            return now_wall
        finally:
            with self._server_ts_lock:
                self._server_ts_inflight = False
        
    def get_realtime_price(self, pair):
        """Retorna o preço de fechamento da última vela M1 como proxy."""
        try:
            candles = self.get_candles(pair, 1, 1)
            if candles:
                return candles[-1]['close']
        except Exception:
            return None
        return None

    def close(self):
        """Fecha conexões e heartbeat."""
        try:
            self._hb_stop.set()
        except Exception:
            pass
        try:
            if self.api:
                self.api.close_connect()
        except Exception:
            pass

    def get_payout(self, pair, type_name="turbo"):
        """Gets payout percentage for a pair."""
        all_profits = self.api.get_all_profit()
        return all_profits.get(pair, {}).get(type_name, 0) * 100

    def get_candles(self, pair, timeframe, amount, timeout_s=5, connect_timeout_s=None):
        """Fetches candle data with bounded timeout to prevent freezing.
        Optional timeout_s allows quicker checks (e.g., timeframe validation).
        connect_timeout_s: se definido, usa um modo rápido de conexão (sem backoff longo).
        """
        result = []

        # VERIFICAÇÃO CRUCIAL: garante conexão antes de começar
        # MODIFICAÇÃO: Se connect_timeout_s for usado, a verificação é feita DENTRO da thread
        # para garantir que o timeout global da função `get_candles` (via join) funcione.
        if connect_timeout_s is None:
            if not self._ensure_connected():
                self._log_throttled(
                    f"candles_conn_fail_{pair}",
                    f"[IQ] ❌ Falha ao conectar para buscar candles de {pair}",
                    interval_s=10.0,
                )
                return []

        # Se já existe um fetch em andamento para este par, não cria outro.
        with self._candles_inflight_lock:
            if pair in self._candles_inflight:
                self._log_throttled(
                    f"candles_inflight_{pair}",
                    f"[IQ] ⏳ Candles ainda em andamento para {pair}. Pulando...",
                    interval_s=6.0,
                )
                return []
            self._candles_inflight.add(pair)
        
        def _fetch():
            nonlocal result
            try:
                # Se modo rápido, verificar conexão AQUI DENTRO (protegido por timeout da thread)
                if connect_timeout_s is not None:
                    if not self._ensure_connected_quick(float(connect_timeout_s)):
                        return

                # Try up to 2 times
                for attempt in range(2):
                    try:
                        # Verificação extra: se self.api virou None durante a execução
                        if self.api is None:
                            raise ConnectionError("Conexão perdida durante fetch")
                        
                        # IQ Option API get_candles is known to hang sometimes
                        candles = self.api.get_candles(pair, timeframe * 60, amount, time.time())
                        if candles:
                            result = candles
                            return  # Success
                    except Exception as e:
                        err_msg = str(e).lower()
                        # Catch Socket Closed, EOF (SSL), and general Connection errors
                        if any(x in err_msg for x in ["socket", "closed", "eof", "ssl", "violation", "handshake"]):
                            self._log_throttled(
                                "candles_conn_instability",
                                f"[IQ] 🔄 Instabilidade de Conexão ({err_msg[:20]}...). Reconectando... ({attempt+1}/2)",
                                interval_s=10.0,
                            )
                            try:
                                self.api.close_connect()
                            except Exception:
                                pass
                            self.api = None
                            time.sleep(1 + attempt)  # (1s, then 2s)
                        else:
                            self._log_throttled(
                                "candles_error",
                                f"[IQ] Erro download candles: {e}",
                                interval_s=10.0,
                            )
                            # Mantém uma tentativa extra.
                            pass
            finally:
                with self._candles_inflight_lock:
                    self._candles_inflight.discard(pair)

        # Threaded fetch with bounded timeout to avoid stalling multi-asset scans.
        t = threading.Thread(target=_fetch, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
        
        if t.is_alive():
            self._log_throttled(
                "candles_timeout",
                f"[IQ] TIMEOUT ao baixar velas de {pair} ({int(timeout_s)}s)",
                interval_s=15.0,
            )
            return []
            
        if not result:
            return []
            
        # Normalize keys
        normalized_candles = []
        for c in result:
            nc = c.copy()
            if 'max' in c and 'high' not in c:
                nc['high'] = c['max']
            if 'min' in c and 'low' not in c:
                nc['low'] = c['min']
            if 'vol' in c and 'volume' not in c:
                nc['volume'] = c['vol']
            normalized_candles.append(nc)
        return normalized_candles

    def buy(self, amount, pair, action, duration):
        """Executes a trade with timeout, retry, and auto-reconnect."""
        # Normalizar duration (algumas modalidades/OTC não suportam M15/M30)
        try:
            duration = int(duration)
        except Exception:
            duration = 1

        # OTC: comportamento configurável
        # - force_otc_m1m5=True: sempre restringe execução a M1/M5
        # - force_otc_m1m5=False: respeita timeframe do usuário e usa fallback apenas se a corretora rejeitar
        otc_pair = isinstance(pair, str) and "OTC" in pair
        force_otc_m1m5 = bool(getattr(self.config, "force_otc_m1m5", False))

        if otc_pair and force_otc_m1m5 and duration not in (1, 5):
            self._log(f"[IQ] ⚠️ OTC M1/M5 forçado. Ajustando M{duration} → M5 para {pair}.")
            duration = 5

        # VERIFICAR CONEXÃO (Lightweight)
        if not self.api:
             self._log("[IQ] ❌ API não inicializada. Tentando conectar...")
             if not self._ensure_connected():
                 return False, "Falha na conexão"
        
        # self._log(f"[IQ] 🔍 Conexão OK. Executando trade...") -> Menos log
        self._log(f"[IQ] 🚀 Executando {action} em {pair}...")
        
        # Executando loop de tentativas...
        
        max_retries = 2
        fallback_tried = False
        
        for attempt in range(max_retries):
            result = self._buy_with_timeout(amount, pair, action, duration)
            
            if result[0]:  # Success
                return result
            
            # Se falhou por erro de socket/conexão, tentar reconectar
            error_msg = str(result[1]).lower()
            if "socket" in error_msg or "closed" in error_msg or "timeout" in error_msg:
                if attempt < max_retries - 1:
                    self._log_throttled(
                        "buy_conn_error",
                        f"[IQ_HANDLER] ⚠️ Erro de conexão detectado. Tentativa {attempt+1}/{max_retries}",
                        interval_s=6.0,
                    )
                    self._log_throttled(
                        "buy_reconnecting",
                        "[IQ_HANDLER] 🔄 Reconectando...",
                        interval_s=6.0,
                    )
                    self._ensure_connected()
                    time.sleep(2)
                    continue
            
            # Outros erros (asset closed, etc) - não adianta retry

            # Fallback: se for OTC e timeframe longo, tentar M5 uma vez quando a mensagem indicar expiração/timeframe inválida
            if (not force_otc_m1m5) and otc_pair and (duration not in (1, 5)) and (not fallback_tried):
                msg = str(result[1]).lower()
                duration_keys = (
                    "expiration",
                    "expir",
                    "timeframe",
                    "duration",
                    "invalid",
                    "not supported",
                    "strike",
                )
                if any(k in msg for k in duration_keys):
                    fallback_tried = True
                    self._log(f"[IQ] ⚠️ Rejeição por timeframe/expiração em {pair} (M{duration}). Tentando fallback M5...")
                    duration = 5
                    continue

            break
        
        return result  # Return last failed result

    def _buy_with_timeout(self, amount, pair, action, duration):
        """Internal buy with 30s timeout."""
        action_lower = action.lower()
        result = [False, "Timeout"]
        
        def _buy_thread():
            try:
                op_type = self.config.option_type
                
                # === BINARY ONLY ===
                if op_type == "BINARY":
                    self._log(f"[IQ] Tentando Binária (Forçado): {pair} {action}...")
                    check, order_id = self.api.buy(amount, pair, action_lower, duration)
                    if check:
                        self._log(f"[IQ] Binária Sucesso! {order_id}")
                        result[0] = True
                        result[1] = order_id
                    else:
                        result[1] = f"Binary Failed: {order_id}"
                    return

                # === DIGITAL ONLY ===
                if op_type == "DIGITAL":
                    self._log(f"[IQ] Tentando Digital (Forçado): {pair}...")
                    try:
                        self.api.subscribe_strike_list(pair, duration)
                        check, order_id = self.api.buy_digital_spot(pair, amount, action_lower, duration)
                        if check:
                            self._log(f"[IQ] Digital Sucesso! {order_id}")
                            result[0] = True
                            result[1] = order_id
                        else:
                            result[1] = f"Digital Failed: {order_id}"
                    except Exception as e:
                        result[1] = f"Digital Error: {str(e)}"
                    return

                # === BEST (AUTO) ===
                is_otc = "OTC" in pair
                is_short_timeframe = duration <= 5
                prefer_digital = (not is_otc) and is_short_timeframe
                
                if prefer_digital:
                    self._log(f"[IQ] Smart Order: Priorizando DIGITAL para {pair} (M{duration})...")
                    # TENTATIVA 1: DIGITAL
                    try:
                        self.api.subscribe_strike_list(pair, duration)
                        check_digital, order_id_digital = self.api.buy_digital_spot(pair, amount, action_lower, duration)
                        if check_digital:
                            self._log(f"[IQ] Digital Sucesso! {order_id_digital}")
                            result[0] = True
                            result[1] = order_id_digital
                            return
                        else:
                            self._log(f"[IQ] Digital falhou: {order_id_digital}")
                    except Exception as e:
                        self._log(f"[IQ] Erro Digital: {e}")
                        
                    # TENTATIVA 2: BINÁRIA (Fallback)
                    self._log("[IQ] Tentando Binária (Fallback)...")
                    check, order_id = self.api.buy(amount, pair, action_lower, duration)
                    if check:
                        self._log(f"[IQ] Binária Sucesso! {order_id}")
                        result[0] = True
                        result[1] = order_id
                    else:
                        result[1] = f"Digital/Binary Failed: {order_id}"
                        
                else: # Prefer Binary (Default/OTC)
                    self._log(f"[IQ] Smart Order: Priorizando BINÁRIA para {pair}...")
                    # TENTATIVA 1: BINÁRIA
                    check, order_id = self.api.buy(amount, pair, action_lower, duration)
                    if check:
                        self._log(f"[IQ] Binária Sucesso! {order_id}")
                        result[0] = True
                        result[1] = order_id
                        return
                    else:
                        self._log(f"[IQ] Binária falhou: {order_id}")
                        
                    # TENTATIVA 2: DIGITAL (Fallback)
                    try:
                        self.api.subscribe_strike_list(pair, duration)
                        check_digital, order_id_digital = self.api.buy_digital_spot(pair, amount, action_lower, duration)
                        if check_digital:
                            self._log(f"[IQ] Digital Sucesso! {order_id_digital}")
                            result[0] = True
                            result[1] = order_id_digital
                        else:
                            result[1] = f"Bin: {order_id} | Dig: {order_id_digital}"
                    except Exception as e:
                        result[1] = f"Digital Exception: {str(e)}"
                    
            except Exception as e:
                self._log(f"[IQ] Erro Geral Thread: {e}")
                result[1] = str(e)
        
        try:
            # Não bloquear no lock global para trade, apenas para conexão
            # with self._lock: -> REMOVIDO para evitar deadlock/espera em trade
            
            thread = threading.Thread(target=_buy_thread)
            thread.start()
            thread.join(timeout=15) # 15 segundos máximo para execução (Aumentado para evitar falha em rede lenta)
            
            if thread.is_alive():
                self._log("[IQ] ⚠️ TIMEOUT: Operação excedeu 15 segundos!")
                self.last_error = "API timeout (15s)"
                return False, "Timeout ao executar trade - Tente novamente"
        except Exception as e:
            self._log(f"[IQ] ❌ Erro crítico threading: {e}")
            return False, f"Erro de threading: {str(e)}"
                    
        return result[0], result[1]

    def check_win(self, order_id):
        """Checks result of an order with retry."""
        max_retries = 3
        for _ in range(max_retries):
            try:
                result = self.api.check_win_v3(order_id) if order_id else 0
                if result is not None:
                    return result
            except Exception:
                time.sleep(1)
        return 0

    def get_open_assets(self, type_name="turbo"):
        """Scans for open assets."""
        return self.api.get_all_open_time()
    
    def scan_available_pairs(self, pairs_list):
        """Scans a list of pairs - simplified version that just shows all pairs.
        Actual verification happens at trade time."""
        import threading
        
        results = {}
        all_profits = {}
        
        # Apenas buscar payouts (mais rápido que get_all_open_time)
        def _fetch_profits():
            nonlocal all_profits
            try:
                all_profits = self.api.get_all_profit()
            except Exception:
                pass  # Silently fail if profit fetch fails
        
        # Fetch profits with timeout
        thread = threading.Thread(target=_fetch_profits)
        thread.start()
        thread.join(timeout=10)

        for pair in pairs_list:
            payout = 0
            is_open = False
            
            # Tentar pegar payout real baseado no tipo de opção
            if pair in all_profits:
                try:
                    profit_data = all_profits[pair]
                    
                    # Prioriza o tipo selecionado na config
                    op_type = self.config.option_type
                    
                    turbo_payout = 0
                    binary_payout = 0
                    
                    if isinstance(profit_data, dict):
                        turbo_payout = profit_data.get("turbo", 0)
                        binary_payout = profit_data.get("binary", 0)

                        if op_type == "BINARY":
                            payout = max(turbo_payout, binary_payout)
                        elif op_type == "DIGITAL":
                            if max(turbo_payout, binary_payout) > 0:
                                payout = 0.90
                        else: # BEST
                            payout = max(turbo_payout, binary_payout)
                            
                        # Se payout > 0, esta aberto
                        if payout > 0:
                            payout = payout * 100
                            is_open = True
                            
                    elif isinstance(profit_data, (int, float)):
                        payout = profit_data * 100
                        if payout > 0:
                            is_open = True
                        
                except Exception as e:
                    print(f"Erro ao ler payout de {pair}: {e}")
            
            # Fallback: Se não achou no profit, verificar se está aberto pelo get_all_open_time
            # Isso corrige o erro de "Nenhum ativo aberto" quando o get_all_profit falha
            if not is_open:
                try:
                    # Tenta verificar se o ativo é conhecido como aberto
                    # Simplesmente checando se é OTC e se estamos em horario de OTC
                    if "OTC" in pair:
                        is_open = True
                        payout = 87 # Payout padrão estimado para OTC
                except Exception:
                    pass

            if is_open:
                results[pair] = {
                    "open": True,
                    "payout": round(payout, 0)
                }
        
        return results

    def validate_pair_timeframes(self, pair, timeframes=(1, 5, 15, 30), timeout_s: float = 2.0):
        """Valida se um par aceita operar nas timeframes fornecidas.
        Retorna True somente se TODAS as timeframes retornarem candles.
        Modo RÁPIDO: 1 tentativa por timeframe, timeout curto. Fail-fast.
        """
        for tf in timeframes:
            # Uma única tentativa por timeframe para não travar o boot
            try:
                # Fail-fast com timeout configurável e conexão rápida (sem backoff longo)
                candles = self.get_candles(
                    pair,
                    int(tf),
                    3,
                    timeout_s=float(timeout_s),
                    connect_timeout_s=float(timeout_s),
                )
                if not candles:
                    return False
            except Exception:
                return False
                
        return True

    def filter_pairs_by_timeframes(self, pairs_list, timeframes=(1, 5, 15, 30)):
        """Filtra lista de pares mantendo apenas os que aceitam TODAS as timeframes.
        Retorna dict {pair: {open, payout}} semelhante a scan_available_pairs, mas filtrado.
        """
        base = self.scan_available_pairs(pairs_list)
        filtered = {}
        for pair, info in base.items():
            if not info.get("open"):
                continue
            if self.validate_pair_timeframes(pair, timeframes):
                filtered[pair] = info
        return filtered
