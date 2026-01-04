# strategies/ferreira_primeiro_registro.py
from .base_strategy import BaseStrategy
from utils.advanced_indicators import (
    is_comando_candle, is_force_candle, 
    calculate_average_body
)


class FerreiraPrimeiroRegistroStrategy(BaseStrategy):
    """
    Estratégia 11: Primeiro Registro V2 (OB de Sucesso)
    
    Lógica: Operar a defesa de preço (retração) no pavio que registra 
    o início de um novo movimento institucional (1R).
    
    Fases:
    1. Mapeamento do 1R (primeiro registro após reversão/comando)
    2. Rompimento da zona marcada
    3. Confirmação de estrutura
    4. Retorno e teste do 1R
    5. Execução no fechamento da vela de teste
    """
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Primeiro Registro V2 (Ferreira)"
        self.marked_1r = {}  # Cache de marcações 1R por par
    
    def check_signal(self, pair, timeframe_str):
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
        
        candles = self.api.get_candles(pair, timeframe, 100)
        if not candles or len(candles) < 50:
            return None, "Dados insuficientes"
        
        # Detectar e marcar 1R se ainda não existe
        if pair not in self.marked_1r or not self.marked_1r[pair]:
            self._detect_and_mark_1r(pair, candles)
        
        # Verificar se temos marcação válida
        if pair not in self.marked_1r or not self.marked_1r[pair]:
            return None, "Aguardando formação de  1R..."
        
        marca_1r = self.marked_1r[pair]
        v0 = candles[-2]

        
        signal = None
        desc = ""
        setup_type = None
        tolerance = marca_1r["atr"] * 0.5 if "atr" in marca_1r else 0.00005
        
        # === FASE 4: TESTE DO 1R (RETORNO À LINHA) ===
        
        if marca_1r["type"] == "CALL":
            # Linha 1R de CALL: está no topo do pavio da primeira vela verde
            linha_1r = marca_1r["level"]
            
            # Vela tocou a linha e fechou COM O CORPO ACIMA dela
            if (v0['low'] <= linha_1r + tolerance and
                v0['close'] > linha_1r):
                
                # Validação: corpo não pode ultrapassar muito a linha (consumir o pavio)
                if v0['close'] < linha_1r * 1.001:  # Margem de 0.1%
                    signal = "CALL"
                    desc = f"1R CALL Testado ({linha_1r:.5f})"
                    setup_type = "1R_DEFENSE_CALL"
        
        elif marca_1r["type"] == "PUT":
            # Linha 1R de PUT: está no fundo do pavio da primeira vela vermelha
            linha_1r = marca_1r["level"]
            
            # Vela tocou a linha e fechou COM O CORPO ABAIXO dela
            if (v0['high'] >= linha_1r - tolerance and
                v0['close'] < linha_1r):
                
                # Validação: corpo não pode ultrapassar muito a linha
                if v0['close'] > linha_1r * 0.999:
                    signal = "PUT"
                    desc = f"1R PUT Testado ({linha_1r:.5f})"
                    setup_type = "1R_DEFENSE_PUT"
        
        # === FILTRO: Vela de teste com corpo rompendo a linha = sinal inválido ===
        if signal:
            if marca_1r["type"] == "CALL" and v0['close'] < marca_1r["level"]:
                return None, "1R rompido (inválido)"
            elif marca_1r["type"] == "PUT" and v0['close'] > marca_1r["level"]:
                return None, "1R rompido (inválido)"
        
        # === VALIDAÇÃO COM IA (OBRIGATÓRIA) ===
        if signal and self.ai_analyzer:
            try:
                trend_context = {
                    "setup": setup_type,
                    "1r_level": marca_1r["level"],
                    "1r_type": marca_1r["type"],
                    "had_force_candle": marca_1r.get("had_force_candle", False)
                }
                
                zones = {
                    "resistance": [{"level": marca_1r["level"], "touches": 1}] if marca_1r["type"] == "PUT" else [],
                    "support": [{"level": marca_1r["level"], "touches": 1}] if marca_1r["type"] == "CALL" else []
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
    
    def _detect_and_mark_1r(self, pair, candles):
        """Detecta e marca o Primeiro Registro (1R)"""
        if len(candles) < 10:
            return
        
        # Procurar reversão recente ou comando
        for i in range(len(candles) - 5, len(candles) - 2):
            current = candles[i]
            prev = candles[i-1] if i > 0 else current
            
            is_green_curr = current['close'] > current['open']
            is_green_prev = prev['close'] > prev['open']
            
            # Reversão: mudança de cor
            reversed = (is_green_curr and not is_green_prev) or (not is_green_curr and is_green_prev)
            
            # Comando: vela sem pavio na abertura
            comando = is_comando_candle(current)
            
            if reversed or comando:
                # Marcar o 1R
                if is_green_curr:
                    # 1R de CALL: topo do pavio superior
                    self.marked_1r[pair] = {
                        "type": "CALL",
                        "level": current['high'],
                        "candle_idx": i,
                        "had_force_candle": False
                    }
                else:
                    # 1R de PUT: fundo do pavio inferior
                    self.marked_1r[pair] = {
                        "type": "PUT",
                        "level": current['low'],
                        "candle_idx": i,
                        "had_force_candle": False
                    }
                
                # Verificar se houve vela de força rompendo essa zona
                avg_body = calculate_average_body(candles[i-10:i], 10)
                for j in range(i+1, len(candles)-1):
                    if is_force_candle(candles[j], avg_body, 2.0):
                        self.marked_1r[pair]["had_force_candle"] = True
                        break
                
                return
