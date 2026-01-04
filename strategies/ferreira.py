# strategies/ferreira.py
import pandas as pd

class FerreiraStrategy:
    def __init__(self, api, ai_analyzer=None):
        self.api = api
        self.ai_analyzer = ai_analyzer
        self.name = "Ferreira Trader Sniper"
        self.logger = None

    def set_logger(self, logger_func):
        self.logger = logger_func

    def log(self, msg):
        if self.logger:
            self.logger(f"[{self.name}] {msg}")

    def get_candles(self, pair, timeframe, limit=100):
        """Busca velas e converte para DataFrame"""
        candles = self.api.get_candles(pair, timeframe * 60, limit)
        if not candles:
            return None
        
        df = pd.DataFrame(candles)
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].astype(float)
        df['time'] = pd.to_datetime(df['from'], unit='s')
        return df

    def calculate_rsi(self, series, period=14):
        """Calcula RSI manualmente sem depender de libs externas"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        
        # Média Móvel Exponencial (Wilder)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def check_signal(self, pair, timeframe_str):
        try:
            # Converter timeframe para int se necessário
            try:
                timeframe = int(timeframe_str)
            except Exception:
                timeframe = 1

            df = self.get_candles(pair, timeframe)
            if df is None or len(df) < 50:
                return None, "Dados insuficientes"

            # === CÁLCULO MANUAL DOS INDICADORES ===
            
            # 1. Tendência (EMA 100 e EMA 20)
            df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            
            # 2. Volatilidade (Bollinger Bands 20, 2.5)
            sma = df['close'].rolling(window=20).mean()
            std = df['close'].rolling(window=20).std()
            df['bb_upper'] = sma + (std * 2.5)
            df['bb_lower'] = sma - (std * 2.5)
            
            # 3. Força (RSI 14)
            df['rsi'] = self.calculate_rsi(df['close'])

            # Analisar a última vela FECHADA
            last_candle = df.iloc[-2]
            
            # Dados auxiliares
            body_size = abs(last_candle['close'] - last_candle['open'])
            upper_wick = last_candle['high'] - max(last_candle['open'], last_candle['close'])
            lower_wick = min(last_candle['open'], last_candle['close']) - last_candle['low']
            total_size = last_candle['high'] - last_candle['low']

            signal = None
            desc = ""

            # Filtro básico de tamanho de vela (evitar doji/mercado parado)
            if total_size == 0 or (body_size / total_size) < 0.1:
                return None, "Doji/Vela pequena"

            # === LÓGICA DE OPERAÇÃO ===
            
            trend = "BULL" if last_candle['close'] > last_candle['ema100'] else "BEAR"

            # 1. PULLBACK NA EMA 20 (Favor da tendência)
            if trend == "BULL" and last_candle['low'] <= last_candle['ema20'] and last_candle['close'] > last_candle['ema20']:
                if last_candle['rsi'] < 70: # Não pode estar esticado
                    signal = "CALL"
                    desc = "Pullback EMA20 (Alta)"

            elif trend == "BEAR" and last_candle['high'] >= last_candle['ema20'] and last_candle['close'] < last_candle['ema20']:
                if last_candle['rsi'] > 30: # Não pode estar esticado
                    signal = "PUT"
                    desc = "Pullback EMA20 (Baixa)"

            # 2. REVERSÃO NAS BANDAS (Sniper)
            if not signal:
                # PUT: Tocou na banda superior + RSI alto + Deixou pavio
                if last_candle['high'] >= last_candle['bb_upper'] and last_candle['rsi'] >= 70:
                    if upper_wick > body_size * 0.5: 
                        signal = "PUT"
                        desc = "Reversão Banda Superior + RSI"

                # CALL: Tocou na banda inferior + RSI baixo + Deixou pavio
                elif last_candle['low'] <= last_candle['bb_lower'] and last_candle['rsi'] <= 30:
                    if lower_wick > body_size * 0.5:
                        signal = "CALL"
                        desc = "Reversão Banda Inferior + RSI"

            if signal:
                return signal, desc
            
            return None, ""

        except Exception as e:
            self.log(f"Erro: {e}")
            return None, f"Erro: {str(e)}"
