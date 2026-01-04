# strategies/ana_tavares.py
from .base_strategy import BaseStrategy
from utils.indicators import calculate_sma, calculate_atr

class AnaTavaresStrategy(BaseStrategy):
    """
    ESTRATÉGIA: Ana Tavares (Sistema de Retração)
    
    Lógica:
    1. Baseada no princípio do 'Efeito Elástico' em M5.
    2. Regra de Ouro: Pico de vela nos primeiros 50% do tempo (2m30s).
    3. Filtro de Explosão: Vela deve esticar rápido (Pico).
    4. Gatilho: Toque na zona SNR ou Médias Móveis com rejeição.
    5. Anti-Trator: Evita entrar se velas anteriores foram muito pequenas (acumulação).
    """
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Ana Tavares Retraction System"
        
    def check_signal(self, pair, timeframe_str):
        # Force M5 ideally, but respect user choice if they really want M1
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 5 
            
        lookback = 100
        candles = self.api.get_candles(pair, timeframe, lookback)
        if not candles or len(candles) < 50:
            return None, "Aguardando dados..."
            
        # === VELA ATIVA (Retração opera na vela aberta) ===
        current_candle = candles[-1]
        
        # 1. FILTRO DE TEMPO
        # "Regra de Ouro: < 50% do tempo"
        candle_duration = timeframe * 60
        allow_entry_until = candle_duration * 0.5 # 2m30s for M5
        
        server_time = self.api.api.get_server_timestamp()
        elapsed = server_time - current_candle['at']
        
        # Ajuste para delay de rede/clock
        if elapsed < 0:
            elapsed = 0
        
        if elapsed > allow_entry_until:
            return None, f"Tempo de Retração Esgotado ({elapsed}s)"
            
        # 2. INDICADORES
        sma20 = calculate_sma(candles[:-1], 20)
        atr = calculate_atr(candles[:-1], 14)
        if not atr:
            atr = 0.0001
        
        current_price = self.api.get_realtime_price(pair)
        if not current_price:
            return None, "Sem preço real"
        
        open_price = current_candle['open']
        
        # 3. FÍSICA DA VELA (Pico/Explosão)
        # Vela deve ter esticado RÁPIDO.
        # Check size vs ATR allowed for the time elapsed
        current_size = abs(current_price - open_price)
        
        # Se esticou 70% do ATR em 30% do tempo -> Explosão
        # Simplificação: Se tamanho > 50% ATR dentro do tempo permitido
        is_explosive = current_size > (atr * 0.5)
        
        if not is_explosive:
             return None, "Sem explosão de vela"
             
        # 4. GATILHOS (Toque na Zona SMA 20 ou Fractais)
        
        signal = None
        desc = ""
        
        # Tendência
        trend = 'NEUTRAL'
        if sma20:
            if calculate_sma(candles[:-2], 20) < sma20:
                trend = 'BULLISH' # Rising
            else:
                trend = 'BEARISH'
            
        # Validar Toque na SMA 20 (Suporte/Resistencia Dinamico)
        dist_sma = abs(current_price - sma20)
        hit_sma = dist_sma <= 0.00015
        
        if hit_sma:
            # Se preço está (ou foi) abaixo da SMA e SMA está subindo -> Call
            # Precisamos ver se o candle 'tocou' a linha
            
            if trend == 'BULLISH':
                # Preço desceu até a SMA? (Pullback na alta)
                if current_price <= (sma20 + 0.0001):
                    # Check ANTI-TRATOR (Velas anteriores pequenas)
                    if self.check_anti_trator(candles[-3:-1], atr):
                        signal = "CALL"
                        desc = "🎯 RETRAÇÃO: Pico na SMA20 (Trend Alta)"
                        
            elif trend == 'BEARISH':
                 # Preço subiu até a SMA? (Pullback na baixa)
                 if current_price >= (sma20 - 0.0001):
                     if self.check_anti_trator(candles[-3:-1], atr):
                         signal = "PUT"
                         desc = "🎯 RETRAÇÃO: Pico na SMA20 (Trend Baixa)"

        # === 5. FILTRO DE PROXIMIDADE (Nascendo na cara da zona) ===
        # Se abriu muito perto da SMA, não tem "elástico".
        dist_open_sma = abs(open_price - sma20)
        if dist_open_sma < (atr * 0.2):
            return None, "Filtro: Nasceu muito perto da zona"
            
        # 🤖 VALIDAÇÃO IA
        if signal and self.ai_analyzer:
            try:
                zones = {"support": [], "resistance": []}
                trend_data = {"trend": "NEUTRAL", "setup": "RETRACTION", "pattern": desc[:20]}
                should_trade, confidence, ai_reason = self.validate_with_ai(signal, desc, candles, zones, trend_data, pair)
                if not should_trade:
                    return None, f"🤖-❌ IA bloqueou: {ai_reason[:30]}... ({confidence}%)"
                desc = f"{desc} | 🤖✓{confidence}%"
            except Exception:
                desc = f"{desc} | ⚠️ IA offline"
        return signal, desc

    def check_anti_trator(self, prev_candles, atr):
        # "Se as 2 velas anteriores foram muito pequenas... abortar"
        for c in prev_candles:
            body = abs(c['close'] - c['open'])
            if body < (atr * 0.3):
                return False # É trator (acumulação), perigo de rompimento
        return True
