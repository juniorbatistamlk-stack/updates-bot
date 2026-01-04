from .base_strategy import BaseStrategy
from .ferreira import FerreiraStrategy
from .price_action import PriceActionStrategy
from .logica_preco import LogicaPrecoStrategy
from .ana_tavares import AnaTavaresStrategy
from .conservador import ConservadorStrategy
from .alavancagem import AlavancagemStrategy
from .alavancagem_sr import AlavancagemSRStrategy
from .ferreira_price_action import FerreiraPriceActionStrategy
from .ferreira_snr_advanced import FerreiraSNRAdvancedStrategy
from .ferreira_moving_avg import FerreiraMovingAvgStrategy
from .ferreira_primeiro_registro import FerreiraPrimeiroRegistroStrategy
from .trader_machado import TraderMachadoStrategy

import time

class AiGodModeStrategy(BaseStrategy):
    """
    ESTRATÉGIA: AI God Mode (12-in-1 Arbitrage)
    
    Lógica:
    1. Instancia TODAS as 12 estratégias como sub-agentes (sem AI individual).
    2. A cada tick/candle, consulta todos os sub-agentes.
    3. Coleta os sinais gerados (Candidatos).
    4. Envia o relatório de candidatos para a IA "Deus".
    5. A IA decide qual estratégia seguir baseada no contexto atual.
    """
    def __init__(self, api, ai_analyzer=None):
        super().__init__(api, ai_analyzer)
        self.name = "AI God Mode (12-in-1)"
        
        # Instanciar sub-estratégias SEM IA (apenas geradores de sinal)
        # Isso economiza tokens e tempo, deixando a decisão final para este God Mode
        self.strategies = [
            FerreiraStrategy(api, None),
            PriceActionStrategy(api, None),
            LogicaPrecoStrategy(api, None),
            AnaTavaresStrategy(api, None),
            ConservadorStrategy(api, None),
            AlavancagemStrategy(api, None),
            AlavancagemSRStrategy(api, None),
            FerreiraPriceActionStrategy(api, None),
            FerreiraSNRAdvancedStrategy(api, None),
            FerreiraMovingAvgStrategy(api, None),
            FerreiraPrimeiroRegistroStrategy(api, None),
            TraderMachadoStrategy(api, None)
        ]
        
        # Cache para evitar re-instanciação ou calc pesado
        self.last_scan_time = 0

    def _fallback_momentum_signal(self, candles, pair):
        """Gera sinal simples baseado em momentum quando nenhuma estratégia vota."""
        if not candles or len(candles) < 20:
            return None

        closes = [c.get("close") for c in candles if c.get("close") is not None]
        if len(closes) < 20:
            return None

        short = sum(closes[-5:]) / 5
        mid = sum(closes[-10:-5]) / 5
        long = sum(closes[-20:]) / 20

        slope = closes[-1] - closes[-5]

        threshold = max(0.00015, abs(long) * 0.00012)

        if short > mid > long and slope > threshold:
            desc = (
                f"Fallback Momentum CALL {pair} | short {short:.5f} > mid {mid:.5f} > long {long:.5f}"
            )
            return "CALL", desc

        if short < mid < long and slope < -threshold:
            desc = (
                f"Fallback Momentum PUT {pair} | short {short:.5f} < mid {mid:.5f} < long {long:.5f}"
            )
            return "PUT", desc

        return None

    def check_signal(self, pair, timeframe_str):
        # Rate limit local para não sobrecarregar
        if time.time() - self.last_scan_time < 0.5:
            return None, "Aguardando ciclo..."
        
        self.last_scan_time = time.time()
        
        candidates = []
        
        # 1. ESCANEAR TODOS OS SUB-AGENTES
        # Nota: Alguns podem demorar um pouco se puxarem dados, 
        # mas como usam a mesma API e cache interno de velas, deve ser rápido.
        
        # Precisamos das velas para o God Mode também
        try:
            timeframe = int(timeframe_str)
        except Exception:
            timeframe = 1
            
        candles = self.api.get_candles(pair, timeframe, 100)
        if not candles:
            return None, "Sem dados"

        # Iterar estratégias
        for strat in self.strategies:
            try:
                # Passa o mesmo pair e timeframe
                sig, desc = strat.check_signal(pair, timeframe_str)
                
                # Se houver sinal válido
                if sig and sig in ["CALL", "PUT"]:
                    # Ignorar status de erro/wait (que vem como None ou descritivo sem sig)
                    candidates.append({
                        "strategy": strat.name,
                        "signal": sig,
                        "desc": desc
                    })
            except Exception as e:
                print(f"[GOD MODE] Erro na sub-estratégia {strat.name}: {e}")
                continue

        if not candidates:
            fallback = self._fallback_momentum_signal(candles, pair)
            if fallback:
                fallback_signal, fallback_desc = fallback
                if self.ai_analyzer:
                    should_trade, confidence, reason = self.ai_analyzer.analyze_signal(
                        fallback_signal,
                        fallback_desc,
                        candles,
                        [],
                        "GOD_MODE_FALLBACK",
                        pair,
                    )
                    if should_trade:
                        return fallback_signal, f"Fallback Momentum aprovado ({confidence}%) | {reason}"
                    return None, f"Fallback rejeitado: {reason}"
                return fallback_signal, fallback_desc
            return None, "Scanning 12 strategies... No signals."

        # 2. CONSTRUIR RELATÓRIO PARA A IA
        # Se houver candidatos, a IA decide o melhor.
        
        report = "CANDIDATOS ENCONTRADOS:\n"
        for c in candidates:
            report += f"- [{c['strategy']}] sugere {c['signal']} ({c['desc']})\n"
            
        # Contexto de mercado básico para dar à IA
        # (A IA receberá candles/trend via analyze_signal normalmente, 
        # aqui adicionamos o log das outras strats como 'desc')
        
        if self.ai_analyzer:
            # Usamos o 'desc' como veículo para passar o relatório
            # O 'signal' principal pode ser o da maioria ou do primeiro, 
            # mas vamos deixar como "PENDING_AI_DECISION" para a IA arbitrar.
            # Como analyze_signal espera CALL/PUT, vamos fazer um truque:
            
            # Contagem de votos
            calls = len([c for c in candidates if c['signal'] == 'CALL'])
            puts = len([c for c in candidates if c['signal'] == 'PUT'])
            
            primary_signal = "CALL" if calls >= puts else "PUT"
            
            final_desc = f"GOD MODE ARBITRAGE ({len(candidates)} signals) | {report}"
            
            # Buscar definição específica do God Mode (se existir)
            from strategies.definitions import STRATEGY_DEFINITIONS
            god_logic = STRATEGY_DEFINITIONS.get(self.name, "")
            
            # IA ANALISA
            # Passamos o report na descrição para ela ler
            should_trade, confidence, reason = self.ai_analyzer.analyze_signal(
                primary_signal, 
                final_desc, 
                candles, 
                [], # Zones (opcional, sub-strats ja viram)
                "GOD_MODE_SCAN", 
                pair,
                strategy_logic=god_logic
            )
            
            if should_trade:
                # Se IA aprovou, ela concordou com o primary_signal ou com a lógica geral.
                # Retornamos o sinal majoritário validado.
                return primary_signal, f"GOD MODE: {reason} ({confidence}%) | {len(candidates)} Votes"
            else:
                return None, f"🤖 GOD MODE vetou: {reason}"
        
        return None, "IA necessária para God Mode"
