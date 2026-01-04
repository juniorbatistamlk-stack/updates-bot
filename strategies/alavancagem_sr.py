# strategies/alavancagem_sr.py
# -----------------------------------------------------------------------------
# ⛔ PROTECTED FILE - DO NOT EDIT WITHOUT EXPLICIT USER PERMISSION
# Strategy 7: Alavancagem SR Sniper
# -----------------------------------------------------------------------------

from .base_strategy import BaseStrategy
from utils.indicators import calculate_atr, calculate_ema
from utils.sr_zones import detect_swing_highs_lows, create_sr_zones, is_near_zone
from utils.patterns import is_pin_bar, is_engulfing

class AlavancagemSRStrategy(BaseStrategy):
    """
    ESTRATÉGIA: Alavancagem S/R Sniper
    
    Lógica:
    1. Identifica zonas de Suporte e Resistência baseadas em Swing Highs/Lows.
    2. Espera o preço chegar próximo a uma zona (+/- tolerância).
    3. Confirma a entrada com Padrões de Candle (Martelo, Engolfo, Marubozu).
    4. Filtra transações contra a tendência macro (EMA 20/50).
    """
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Alavancagem S/R Sniper (+5 Padrões)"
        
        self.cycle_wins = 0
        self.last_entry_price = None
        self.sr_zones = []
        
        self.swing_window = 3
        self.atr_period = 14

    def check_signal(self, pair, timeframe):
        lookback = 100
        candles = self.api.get_candles(pair, timeframe, lookback)
        
        if not candles or len(candles) < 50:
            return None, "Aguardando dados..."
        
        # Contexto
        self.update_sr_zones(candles[:-1])
        if len(self.sr_zones) < 2:
            return None, "Sem zonas S/R suficientes"


        current_candle = candles[-2] # Vela FECHADA
        prev_candle = candles[-3] if len(candles) > 2 else None
        current_price = current_candle['close']
        atr = calculate_atr(candles[:-1], self.atr_period)
        
        # 1. VERIFICAR PROXIMIDADE DE ZONAS S/R
        near_support = False
        near_resistance = False
        
        for zone in self.sr_zones:
            if is_near_zone(current_price, zone, atr * 0.5):
                if zone['type'] == 'SUPPORT':
                    near_support = True
                elif zone['type'] == 'RESISTANCE':
                    near_resistance = True
        
        # 2. IDENTIFICAR TENDÊNCIA (FLUXO) - RIGOROSO
        # EMA 20 e EMA 50 para definir tendência macro e micro
        ema20 = calculate_ema(candles[:-1], 20)
        ema50 = calculate_ema(candles[:-1], 50)
        
        trend = 'NEUTRAL'
        if ema20 and ema50:
            if current_price > ema20 and current_price > ema50:
                trend = 'BULLISH'
            elif current_price < ema20 and current_price < ema50:
                trend = 'BEARISH'
                
        # Validação de Topos e Fundos (Action Price)
        structure = self.detect_trend_structure(candles[:-1])
        
        # Filtro Global de Tendência:
        # Se tendência definida, proibir contra-tendência
        allow_call = trend != 'BEARISH' and structure != 'BEARISH'
        allow_put = trend != 'BULLISH' and structure != 'BULLISH'

        signal = None
        desc = ""
        
        # === ANÁLISE EM SUPORTE (CALL) ===
        # REGRA: Só compra se NÃO estiver em tendência de baixa forte
        if near_support and allow_call:
            # Padrões de Confirmação (obrigatórios)
            pattern_found = False
            pattern_name = ""
            
            if is_pin_bar(current_candle, 'bullish') == 'HAMMER':
                pattern_found = True
                pattern_name = "Martelo"
            elif prev_candle and is_engulfing(prev_candle, current_candle) == 'BULLISH_ENGULFING':
                pattern_found = True
                pattern_name = "Engolfo"
            elif self.is_marubozu(current_candle, 'bullish'):
                pattern_found = True
                pattern_name = "Marubozu"
            
            if pattern_found:
                signal = 'CALL'
                desc = f"Sniper: {pattern_name} em Suporte (Trend: {trend}) | Wins: {self.cycle_wins}"

        # === ANÁLISE EM RESISTÊNCIA (PUT) ===
        # REGRA: Só vende se NÃO estiver em tendência de alta forte
        elif near_resistance and allow_put:
             # Padrões de Confirmação (obrigatórios)
            pattern_found = False
            pattern_name = ""
            
            if is_pin_bar(current_candle, 'bearish') == 'SHOOTING_STAR':
                pattern_found = True
                pattern_name = "Shooting Star"
            elif prev_candle and is_engulfing(prev_candle, current_candle) == 'BEARISH_ENGULFING':
                pattern_found = True
                pattern_name = "Engolfo"
            elif self.is_marubozu(current_candle, 'bearish'):
                pattern_found = True
                pattern_name = "Marubozu"
            
            if pattern_found:
                signal = 'PUT'
                desc = f"Sniper: {pattern_name} em Resistência (Trend: {trend}) | Wins: {self.cycle_wins}"
            
        # PROIBIR REVERSÃO SEM CONTEXTO CLARO
        if not signal:
            return None, f"Monitorando... Trend: {trend} | Supp: {near_support} RES: {near_resistance}"

        # Bloqueio Final de Segurança (Redundância)
        if signal == 'CALL' and (trend == 'BEARISH' or current_price < ema20):
             return None, "Cancelado: Filtro EMA (Tendência de Baixa)"
        if signal == 'PUT' and (trend == 'BULLISH' or current_price > ema20):
             return None, "Cancelado: Filtro EMA (Tendência de Alta)"

        # === FILTROS DE CANCELAMENTO ===
        if signal:
            # 1. Exaustão
            body = abs(current_candle['close'] - current_candle['open'])
            if body > atr * 3.5:
                return None, "Cancelado: Vela de Exaustão"
            
            # 2. Pavio Contra (exceto Pin Bar)
            if "Marubozu" in desc or "Soldados" in desc or "Impulsão" in desc:
                 range_total = current_candle['high'] - current_candle['low']
                 upper_wick = current_candle['high'] - max(current_candle['open'], current_candle['close'])
                 lower_wick = min(current_candle['open'], current_candle['close']) - current_candle['low']
                 
                 if signal == 'CALL' and upper_wick > range_total * 0.35:
                     return None, "Cancelado: Rejeição Superior"
                 if signal == 'PUT' and lower_wick > range_total * 0.35:
                     return None, "Cancelado: Rejeição Inferior"
            
            # 3. Repeat
            if self.last_entry_price and abs(current_price - self.last_entry_price) < atr * 0.2:
                return None, "Cancelado: Entrada Repetida"

            self.last_entry_price = current_price
            
        # 🤖 VALIDAÇÃO IA
        if signal and self.ai_analyzer:
            try:
                zones = {"support": [], "resistance": []}
                trend_data = {"trend": "NEUTRAL", "setup": "SR_LEVERAGE", "pattern": desc[:20]}
                should_trade, confidence, ai_reason = self.validate_with_ai(signal, desc, candles, zones, trend_data, pair)
                if not should_trade:
                    return None, f"🤖-❌ IA bloqueou: {ai_reason[:30]}... ({confidence}%)"
                desc = f"{desc} | 🤖✓{confidence}%"
            except Exception:
                desc = f"{desc} | ⚠️ IA offline"
        return signal, desc

    # --- HELPERS ---
    def is_marubozu(self, candle, direction):
        body = abs(candle['close'] - candle['open'])
        range_total = candle['high'] - candle['low']
        if range_total == 0:
            return False
        
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        
        is_solid = body > 0.7 * range_total
        small_wicks = upper_wick < 0.15 * range_total and lower_wick < 0.15 * range_total
        
        if direction == 'bullish':
            return is_solid and small_wicks and candle['close'] > candle['open']
        if direction == 'bearish':
            return is_solid and small_wicks and candle['close'] < candle['open']
        return False

    def is_three_soldiers(self, candles):
        if len(candles) < 3:
            return False
        last_3 = candles[-3:]
        return all(c['close'] > c['open'] for c in last_3) and \
               (last_3[0]['close'] < last_3[1]['close'] < last_3[2]['close'])

    def is_three_crows(self, candles):
        if len(candles) < 3:
            return False
        last_3 = candles[-3:]
        return all(c['close'] < c['open'] for c in last_3) and \
               (last_3[0]['close'] > last_3[1]['close'] > last_3[2]['close'])

    def is_impulse_candle(self, context_candles, current_candle, direction):
        if len(context_candles) < 3:
            return False
        avg_range = sum(c['high'] - c['low'] for c in context_candles) / len(context_candles)
        
        corrections = context_candles[-2:]
        small_correction = all(abs(c['close'] - c['open']) < avg_range * 0.7 for c in corrections)
        
        curr_body = abs(current_candle['close'] - current_candle['open'])
        is_big = curr_body > avg_range * 1.1
        
        if direction == 'bullish':
            return small_correction and is_big and current_candle['close'] > current_candle['open']
        if direction == 'bearish':
            return small_correction and is_big and current_candle['close'] < current_candle['open']
        return False

    def update_sr_zones(self, candles):
        swings = detect_swing_highs_lows(candles, self.swing_window)
        atr = calculate_atr(candles, self.atr_period)
        tolerance = atr * 0.5
        self.sr_zones = create_sr_zones(swings, tolerance, max_zones=5)

    def get_stake_percentage(self):
        stake_map = {0: 2.0, 1: 4.0, 2: 7.0, 3: 12.0, 4: 20.0}
        return stake_map.get(self.cycle_wins, 2.0)

    def on_win(self):
        self.cycle_wins += 1
        if self.cycle_wins >= 5:
            self.cycle_wins = 0

    def on_loss(self):
        if self.cycle_wins >= 3:
            return "STOP_SESSION"
        self.cycle_wins = 0
        return "RESET_CYCLE"
    
    def detect_trend_structure(self, candles):
        """Detecta tendência por estrutura de topos e fundos"""
        if len(candles) < 20:
            return 'NEUTRAL'
        
        recent = candles[-20:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        # Tendência de alta: topos e fundos ascendentes
        if highs[-1] > highs[-10] and lows[-1] > lows[-10]:
            return 'BULLISH'
        # Tendência de baixa: topos e fundos descendentes
        elif highs[-1] < highs[-10] and lows[-1] < lows[-10]:
            return 'BEARISH'
        
        return 'NEUTRAL'
