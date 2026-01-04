# utils/memory.py
"""
Sistema de Memória e Aprendizado do Bot
Salva histórico de operações e aprende com wins/losses
"""
import json
import os
from datetime import datetime

class TradingMemory:
    def __init__(self, memory_file="trade_history.json"):
        self.memory_file = memory_file
        self.history = []
        self.stats = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "patterns": {}  # Padroes e suas taxas de acerto
        }
        self.load_memory()
    
    def load_memory(self):
        """Carrega historico de operacoes"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.history = data.get("history", [])
                    loaded_stats = data.get("stats", {})
                    
                    # Garantir que todas as chaves existam
                    # Garantir que todas as chaves existam e sejam numeros validos
                    self.stats["total_trades"] = int(loaded_stats.get("total_trades") or 0)
                    self.stats["wins"] = int(loaded_stats.get("wins") or 0)
                    self.stats["losses"] = int(loaded_stats.get("losses") or 0)
                    self.stats["win_rate"] = float(loaded_stats.get("win_rate") or 0.0)
                    self.stats["patterns"] = loaded_stats.get("patterns") or {}
                    
                    print(f"[MEMORIA] Carregado: {self.stats['total_trades']} trades | Win Rate: {self.stats['win_rate']:.1f}%")
            except Exception as e:
                print(f"[MEMORIA] Arquivo corrompido ({e}), iniciando novo")
    
    def save_memory(self):
        """Salva historico de operacoes"""
        try:
            data = {
                "history": self.history[-500:],  # Mante ultimos 500 trades
                "stats": self.stats
            }
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MEMORIA] Erro ao salvar: {e}")
    
    def record_trade(self, pair, signal, pattern, result, profit, trend, zone_type=None):
        """
        Registra uma operacao
        
        Args:
            pair: Par operado (ex: EURUSD)
            signal: CALL ou PUT
            pattern: Padrao identificado (ex: "REVERSAO", "TENDENCIA ALTA")
            result: "WIN", "LOSS" ou "TIE"
            profit: Valor ganho/perdido
            trend: BULLISH, BEARISH, LATERAL
            zone_type: "support", "resistance" ou None
        """
        trade = {
            "timestamp": datetime.now().isoformat(),
            "pair": pair,
            "signal": signal,
            "pattern": pattern,
            "trend": trend,
            "zone": zone_type,
            "result": result,
            "profit": profit
        }
        
        self.history.append(trade)
        self.stats["total_trades"] += 1
        
        if result == "WIN":
            self.stats["wins"] += 1
        elif result == "LOSS":
            self.stats["losses"] += 1
        
        # Calcular win rate (com proteção contra None)
        total = int(self.stats.get("total_trades") or 0)
        wins = int(self.stats.get("wins") or 0)
        if total > 0:
            self.stats["win_rate"] = (wins / total) * 100
        
        # Atualizar estatisticas do padrao
        self._update_pattern_stats(pattern, result)
        
        # Salvar a cada 5 trades
        if self.stats["total_trades"] % 5 == 0:
            self.save_memory()
        
        return self.get_pattern_confidence(pattern)
    
    def _update_pattern_stats(self, pattern, result):
        """Atualiza estatisticas de um padrao especifico"""
        if pattern not in self.stats["patterns"]:
            self.stats["patterns"][pattern] = {"wins": 0, "losses": 0, "total": 0}
        
        self.stats["patterns"][pattern]["total"] += 1
        if result == "WIN":
            self.stats["patterns"][pattern]["wins"] += 1
        elif result == "LOSS":
            self.stats["patterns"][pattern]["losses"] += 1
    
    def get_pattern_confidence(self, pattern):
        """
        Retorna confianca do bot em um padrao baseado no historico
        
        Returns:
            float: 0-100 (confianca baseada em historico)
        """
        if pattern not in self.stats["patterns"]:
            return 70  # Padrao novo, confianca neutra
        
        p = self.stats["patterns"][pattern]
        total = int(p.get("total") or 0)
        wins = int(p.get("wins") or 0)
        
        if total < 5:
            return 70  # Poucos dados, confianca neutra
        
        # Proteção extra contra None
        wins = int(wins) if wins is not None else 0
        total = int(total) if total is not None else 1
        win_rate = (wins / max(total, 1)) * 100
        return min(95, max(40, win_rate))  # Limita entre 40-95%
    
    def should_skip_pattern(self, pattern):
        """
        Verifica se deve pular um padrao baseado no historico negativo
        
        Returns:
            bool: True se padrao tem win rate < 35% com mais de 10 trades
        """
        if pattern not in self.stats["patterns"]:
            return False
        
        p = self.stats["patterns"][pattern]
        if p["total"] < 10:
            return False  # Poucos dados
        
        wins = int(p.get("wins") or 0)
        total = int(p.get("total") or 1)
        win_rate = (wins / max(total, 1)) * 100
        return win_rate < 35  # Pula se win rate muito baixo
    
    def get_best_patterns(self, min_trades=5):
        """Retorna os melhores padroes ordenados por win rate"""
        patterns = []
        for name, data in self.stats["patterns"].items():
            if data.get("total") and int(data.get("total") or 0) >= min_trades:
                total = int(data.get("total") or 0)
                wins = int(data.get("wins") or 0)
                wins = int(wins) if wins is not None else 0
                total = int(total) if total is not None else 1
                win_rate = (wins / max(total, 1)) * 100
                patterns.append({
                    "name": name,
                    "win_rate": win_rate,
                    "trades": total
                })
        
        return sorted(patterns, key=lambda x: x["win_rate"], reverse=True)
    
    def get_summary(self):
        """Retorna resumo da memoria"""
        return {
            "total_trades": self.stats["total_trades"],
            "wins": self.stats["wins"],
            "losses": self.stats["losses"],
            "win_rate": self.stats["win_rate"],
            "best_patterns": self.get_best_patterns()[:5]
        }
