# strategies/logica_preco.py
from .base_strategy import BaseStrategy

class LogicaPrecoStrategy(BaseStrategy):
    """
    ESTRATÉGIA: Lógica do Preço (Travamentos e Comandos)
    
    Lógica:
    1. Mapeia 'Velas de Comando' (Abertura = Máxima ou Mínima) como zonas fortes.
    2. Identifica 'Travamentos' (Preço fecha exatamente na zona, sem romper).
    3. Setup de Reversão:
       - Se trava em Suporte de Comando -> CALL.
       - Se trava em Resistência de Comando -> PUT.
    4. Opera a defesa da zona institucional.
    """
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Lógica do Preço (Travamentos)"
        self.buffer_travamento = 0.00001
        self.min_body_size = 0.000005 # 5 points approx on 5th decimal

    def check_signal(self, pair, timeframe_str):
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
            
        lookback = 100
        candles = self.api.get_candles(pair, timeframe, lookback)
        if not candles or len(candles) < 50:
            return None, "Aguardando dados..."
            
        # === 1. DEFINIÇÃO DAS VELAS ===
        previous = candles[-2] # A vela sinal que travou
        
        # === 2. MAPEAMENTO DE ZONAS (Command Candles) ===
        # Baseado nas ultimas 50 velas fechadas
        zones = self.map_command_zones(candles[:-2])
        
        if not zones:
            return None, "Sem zonas mapeadas"
        
        # === 3. LÓGICA DE ENTRADA (TRAVAMENTO) ===
        # Setup: O preço tenta romper, falha e trava o CORPO na linha.
        
        prev_close = previous['close']
        prev_body = abs(previous['close'] - previous['open'])
        
        # Validar tamanho minimo
        if prev_body < self.min_body_size:
            return None, "Vela anterior muito pequena (Doji)"
            
        nearest_zone = min(zones, key=lambda z: abs(z['price'] - prev_close))
        dist = abs(prev_close - nearest_zone['price'])
        
        # Verifica Travamento (Distância <= Buffer)
        if dist <= self.buffer_travamento:
            
            signal = None
            desc = ""

            # CASO VENDA (PUT)
            # Vela Verde (Bullish) travou na RESISTÊNCIA de um Comando Baixa (ou similar)
            if previous['close'] > previous['open']:
                if nearest_zone['type'] == 'RESISTANCE':
                    signal = "PUT"
                    desc = "🤐 TRAVAMENTO DE ALTA EM RESISTÊNCIA"
                    
            # CASO COMPRA (CALL)
            # Vela Vermelha (Bearish) travou no SUPORTE
            if previous['close'] < previous['open']:
                if nearest_zone['type'] == 'SUPPORT':
                    signal = "CALL"
                    desc = "🤐 TRAVAMENTO DE BAIXA EM SUPORTE"
            
            # 🤖 VALIDAÇÃO IA
            if signal and self.ai_analyzer:
                try:
                    trend_data = {"trend": "NEUTRAL", "setup": "LOCK", "pattern": desc[:20]}
                    should_trade, confidence, ai_reason = self.validate_with_ai(signal, desc, candles, {"support": zones, "resistance": zones}, trend_data, pair)
                    if not should_trade:
                        return None, f"🤖-❌ IA bloqueou: {ai_reason[:30]}... ({confidence}%)"
                    desc = f"{desc} | 🤖✓{confidence}%"
                except Exception:
                    desc = f"{desc} | ⚠️ IA offline"
            
            if signal:
                return signal, desc
                    
        return None, f"Monitorando Travamentos... (Zonas: {len(zones)})"

    def map_command_zones(self, candles):
        zones = []
        for c in candles:
            # Comando de Alta (Support)
            # Open == Low
            if c['close'] > c['open'] and abs(c['open'] - c['low']) <= 0.00001:
                zones.append({'price': c['open'], 'type': 'SUPPORT'})
                
            # Comando de Baixa (Resistance)
            # Open == High
            if c['close'] < c['open'] and abs(c['open'] - c['high']) <= 0.00001:
                zones.append({'price': c['open'], 'type': 'RESISTANCE'})
                
        return zones
