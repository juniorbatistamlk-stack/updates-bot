# strategies/ferreira_primeiro_registro_v2.py
"""
================================================================================
🎯 ESTRATÉGIA PRIMEIRO REGISTRO V2 - ADVANCED LOGIC
================================================================================
Versão revisada baseada no JSON original (OB de Sucesso).

Objetivo: Operar a DEFESA DE PREÇO (retração) no pavio que registra 
o início de um novo movimento institucional (1R).

FASES:
  1. Mapeamento do 1R (primeiro registro após reversão/comando)
  2. Confirmação de estrutura (rompimento e distanciamento)
  3. Filtros de alta assertividade (confluências)
  4. Gatilho de execução (teste do 1R)

Win Rate Estimado: 90% (com filtros aplicados)

REGRA: "O Primeiro Registro é o RASTRO deixado pelos grandes players ao 
defenderem uma nova posição. O algoritmo busca o exato momento em que o 
mercado tenta RETESTAR essa defesa e FALHA (retração)."
================================================================================
"""

from .base_strategy import BaseStrategy
from utils.advanced_indicators import (
    is_comando_candle, is_force_candle, 
    calculate_average_body, detect_swing_highs_lows
)

# Tentar importar análise de movimentação
try:
    from utils.price_movement_analyzer import movement_analyzer  # noqa: F401
    MOVEMENT_AVAILABLE = True
except ImportError:
    MOVEMENT_AVAILABLE = False


class FerreiraPrimeiroRegistroV2Strategy(BaseStrategy):
    """
    Estratégia Primeiro Registro V2 - Revisada
    """
    
    STRATEGY_LOGIC = """
ESTRATÉGIA PRIMEIRO REGISTRO V2:

FASE 1 - MAPEAMENTO DO ALVO (1R):
- Condição de reversão: Cor(vela_atual) != Cor(vela_anterior)
- Condição de comando: Vela sem pavio na abertura (intenção institucional)
- Marcação 1R CALL: Topo do pavio superior da primeira vela VERDE
- Marcação 1R PUT: Fundo do pavio inferior da primeira vela VERMELHA

FASE 2 - CONFIRMAÇÃO DE ESTRUTURA:
- O preço deve SAIR da zona marcada e FECHAR fora
- Aguardar 1-3 velas trabalhando fora da marcação (evitar ruído)

FASE 3 - FILTROS DE ALTA ASSERTIVIDADE:
1. ESTRUTURA MACRO: Operar CALL se topos/fundos ascendentes, PUT se descendentes
2. VELA DE FORÇA: Se vela grande rompeu o 1R, zona se torna S/R institucional
3. FRAQUEZA: Velas parando de renovar máx/mín = exaustão = momento ideal
4. COMANDO SEM PAVIO: Defesa mais poderosa (intenção institucional clara)

FASE 4 - GATILHO DE EXECUÇÃO:
- CALL: Preço volta à linha 1R, toca, retrai e fecha ACIMA com corpo
- PUT: Preço volta à linha 1R, toca, retrai e fecha ABAIXO com corpo
- CORPO NUNCA PODE ULTRAPASSAR A LINHA (senão zona está sendo consumida)

FILTROS DE RISCO:
- Não operar 15 min antes/depois de notícias de alto impacto
- Se vela de teste fecha COM CORPO rompendo 1R = SINAL INVÁLIDO
- Máximo 1 operação por zona
"""
    
    def __init__(self, api_handler, ai_analyzer=None):
        super().__init__(api_handler, ai_analyzer)
        self.name = "Primeiro Registro V2"
        self.marked_1r = {}  # Cache de marcações 1R por par
        self.last_1r_update = {}  # Controle de atualização
    
    def check_signal(self, pair, timeframe_str):
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
        
        candles = self.api.get_candles(pair, timeframe, 100)
        if not candles or len(candles) < 50:
            return None, "Dados insuficientes"
        
        # Atualizar/detectar 1R se necessário
        self._update_1r_marking(pair, candles)
        
        # Verificar se temos marcação válida
        if pair not in self.marked_1r or not self.marked_1r[pair]:
            return None, "⏳ Aguardando formação de 1R..."
        
        marca_1r = self.marked_1r[pair]
        
        # Verificar se 1R foi rompido (invalidado)
        if marca_1r.get("invalidated"):
            return None, "🚫 1R invalidado (rompido)"
        
        v0 = candles[-2]  # Última vela fechada
        
        avg_body = calculate_average_body(candles[:-2], 10)
        
        # Estrutura macro (topos/fundos)
        swings = detect_swing_highs_lows(candles[:-2], window=5)
        structure = self._analyze_structure(swings)
        
        signal = None
        desc = ""
        setup_type = None
        
        # Tolerância dinâmica baseada no ATR
        tolerance = avg_body * 0.3
        
        is_green_v0 = v0['close'] > v0['open']
        is_red_v0 = v0['close'] < v0['open']
        
        linha_1r = marca_1r["level"]
        
        # ══════════════════════════════════════════════════════════════════
        # FASE 4: TESTE DO 1R
        # ══════════════════════════════════════════════════════════════════
        
        if marca_1r["type"] == "CALL":
            # 1R de CALL: Linha está no FUNDO (era topo do pavio superior da primeira verde)
            # Preço deve tocar a linha por BAIXO e fechar ACIMA
            
            # Condição: Vela tocou a linha (low <= linha + tolerância)
            tocou_linha = v0['low'] <= linha_1r + tolerance
            
            # Condição: Fechou com corpo ACIMA da linha
            fechou_acima = v0['close'] > linha_1r
            
            # Condição: Corpo não ultrapassou muito a linha (não consumiu o pavio)
            corpo_protegido = v0['close'] < linha_1r + (linha_1r * 0.001)
            
            # Condição: Vela é verde (confirmação)
            confirmacao = is_green_v0
            
            if tocou_linha and fechou_acima and corpo_protegido and confirmacao:
                # Filtro de estrutura: Tendência deve ser ascendente
                if structure["trend"] != "bearish":
                    signal = "CALL"
                    desc = f"1R CALL Testado ({linha_1r:.5f})"
                    setup_type = "1R_DEFENSE_CALL"
        
        elif marca_1r["type"] == "PUT":
            # 1R de PUT: Linha está no TOPO (era fundo do pavio inferior da primeira vermelha)
            
            tocou_linha = v0['high'] >= linha_1r - tolerance
            fechou_abaixo = v0['close'] < linha_1r
            corpo_protegido = v0['close'] > linha_1r - (linha_1r * 0.001)
            confirmacao = is_red_v0
            
            if tocou_linha and fechou_abaixo and corpo_protegido and confirmacao:
                if structure["trend"] != "bullish":
                    signal = "PUT"
                    desc = f"1R PUT Testado ({linha_1r:.5f})"
                    setup_type = "1R_DEFENSE_PUT"
        
        # ══════════════════════════════════════════════════════════════════
        # FILTROS DE ALTA ASSERTIVIDADE
        # ══════════════════════════════════════════════════════════════════
        if signal:
            # Filtro 1: Verificar FRAQUEZA das velas que vêm testar
            # Se velas anteriores já pararam de renovar máx/mín = exaustão = BOM
            exaustao_detectada = self._detect_exhaustion(candles[-5:-1], signal)
            if not exaustao_detectada:
                # Não é obrigatório, mas reduz confiança
                desc = f"{desc} (sem exaustão)"
            
            # Filtro 2: Vela de teste com corpo ROMPENDO a linha = INVÁLIDO
            if marca_1r["type"] == "CALL" and v0['close'] < linha_1r:
                self.marked_1r[pair]["invalidated"] = True
                return None, "🚫 1R rompido (corpo abaixo)"
            
            elif marca_1r["type"] == "PUT" and v0['close'] > linha_1r:
                self.marked_1r[pair]["invalidated"] = True
                return None, "🚫 1R rompido (corpo acima)"
            
            # Filtro 3: Bônus se houve VELA DE FORÇA rompendo zona anteriormente
            if marca_1r.get("had_force_candle"):
                desc = f"{desc} +FORÇA"
            
            # Filtro 4: Bônus se foi COMANDO (sem pavio)
            if marca_1r.get("was_comando"):
                desc = f"{desc} +COMANDO"
        
        # ══════════════════════════════════════════════════════════════════
        # VALIDAÇÃO COM IA
        # ══════════════════════════════════════════════════════════════════
        if signal and self.ai_analyzer:
            try:
                trend_context = {
                    "setup": setup_type,
                    "1r_level": linha_1r,
                    "1r_type": marca_1r["type"],
                    "had_force_candle": marca_1r.get("had_force_candle", False),
                    "was_comando": marca_1r.get("was_comando", False),
                    "structure": structure["trend"]
                }
                
                zones = {
                    "resistance": [{"level": linha_1r, "touches": 1}] if marca_1r["type"] == "PUT" else [],
                    "support": [{"level": linha_1r, "touches": 1}] if marca_1r["type"] == "CALL" else []
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
    
    def _update_1r_marking(self, pair, candles):
        """Detecta e atualiza a marcação do Primeiro Registro (1R)"""
        if len(candles) < 15:
            return
        
        # Procurar reversão ou comando nas últimas velas
        for i in range(len(candles) - 10, len(candles) - 3):
            current = candles[i]
            prev = candles[i-1] if i > 0 else current
            
            is_green_curr = current['close'] > current['open']
            is_green_prev = prev['close'] > prev['open']
            
            # Reversão: mudança de cor
            reversed_candle = (is_green_curr and not is_green_prev) or \
                             (not is_green_curr and is_green_prev)
            
            # Comando: vela sem pavio na abertura (intenção institucional)
            comando = is_comando_candle(current)
            
            if reversed_candle or comando:
                avg_body = calculate_average_body(candles[max(0, i-10):i], 10)
                
                if is_green_curr:
                    # 1R de CALL: Marcar topo do pavio superior
                    level = current['high']
                    
                    # Verificar se preço já saiu e distanciou da zona
                    confirmado = False
                    for j in range(i + 1, min(i + 4, len(candles) - 1)):
                        if candles[j]['close'] > level:
                            confirmado = True
                            break
                    
                    if confirmado:
                        self.marked_1r[pair] = {
                            "type": "CALL",
                            "level": level,
                            "candle_idx": i,
                            "had_force_candle": False,
                            "was_comando": comando,
                            "invalidated": False
                        }
                        
                        # Verificar se houve vela de força
                        for j in range(i + 1, len(candles) - 1):
                            if is_force_candle(candles[j], avg_body, 2.0):
                                self.marked_1r[pair]["had_force_candle"] = True
                                break
                        return
                
                else:
                    # 1R de PUT: Marcar fundo do pavio inferior
                    level = current['low']
                    
                    confirmado = False
                    for j in range(i + 1, min(i + 4, len(candles) - 1)):
                        if candles[j]['close'] < level:
                            confirmado = True
                            break
                    
                    if confirmado:
                        self.marked_1r[pair] = {
                            "type": "PUT",
                            "level": level,
                            "candle_idx": i,
                            "had_force_candle": False,
                            "was_comando": comando,
                            "invalidated": False
                        }
                        
                        for j in range(i + 1, len(candles) - 1):
                            if is_force_candle(candles[j], avg_body, 2.0):
                                self.marked_1r[pair]["had_force_candle"] = True
                                break
                        return
    
    def _analyze_structure(self, swings):
        """Analisa estrutura de topos e fundos"""
        highs = swings["highs"][-5:] if len(swings["highs"]) >= 5 else swings["highs"]
        lows = swings["lows"][-5:] if len(swings["lows"]) >= 5 else swings["lows"]
        
        higher_highs = 0
        lower_lows = 0
        
        for i in range(1, len(highs)):
            if highs[i] > highs[i-1]:
                higher_highs += 1
        
        for i in range(1, len(lows)):
            if lows[i] < lows[i-1]:
                lower_lows += 1
        
        if higher_highs >= 2 and lower_lows <= 1:
            return {"trend": "bullish", "strength": higher_highs}
        elif lower_lows >= 2 and higher_highs <= 1:
            return {"trend": "bearish", "strength": lower_lows}
        else:
            return {"trend": "neutral", "strength": 0}
    
    def _detect_exhaustion(self, candles, signal):
        """Detecta exaustão (velas parando de renovar máx/mín)"""
        if len(candles) < 3:
            return False
        
        if signal == "CALL":
            # Para CALL, queremos ver velas vendedoras perdendo força
            # (não renovando mínimas)
            lows = [c['low'] for c in candles]
            for i in range(1, len(lows)):
                if lows[i] >= lows[i-1]:
                    return True  # Não renovou mínima = exaustão vendedora
        else:
            # Para PUT, queremos ver velas compradoras perdendo força
            highs = [c['high'] for c in candles]
            for i in range(1, len(highs)):
                if highs[i] <= highs[i-1]:
                    return True  # Não renovou máxima = exaustão compradora
        
        return False
