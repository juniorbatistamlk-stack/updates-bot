# utils/trade_history.py
"""
📊 HISTÓRICO DE TRADES - SISTEMA DE APRENDIZADO
Armazena os últimos 40 trades (20 wins + 20 losses) para a IA aprender.
"""
import json
import os
from datetime import datetime

HISTORY_FILE = "trade_history.json"

class TradeHistory:
    def __init__(self):
        self.max_wins = 20
        self.max_losses = 20
        self.data = self._load()
    
    def _load(self):
        """Carrega histórico do arquivo"""
        default_stats = {
            "total_trades": 0,
            "total_wins": 0,
            "total_losses": 0,
            "win_rate": 0
        }
        
        default_data = {
            "wins": [],
            "losses": [],
            "stats": default_stats
        }
        
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Validar estrutura completa
                if not isinstance(data, dict):
                    return default_data
                if "wins" not in data:
                    data["wins"] = []
                if "losses" not in data:
                    data["losses"] = []
                if "stats" not in data:
                    data["stats"] = default_stats
                else:
                    # Garantir todas as chaves de stats
                    for key in default_stats:
                        if key not in data["stats"]:
                            data["stats"][key] = default_stats[key]
                    
                return data
            except Exception:
                pass
        
        return default_data
    
    def _save(self):
        """Salva histórico no arquivo"""
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def add_trade(self, trade_info, result, profit):
        """
        Adiciona um trade ao histórico.
        
        Args:
            trade_info: dict com pair, signal, desc, pattern, etc
            result: 'win' ou 'loss'
            profit: valor do lucro/prejuízo
        """
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "pair": trade_info.get("pair", "UNKNOWN"),
            "signal": trade_info.get("signal", "UNKNOWN"),
            "pattern": trade_info.get("pattern", trade_info.get("desc", "")),
            "desc": trade_info.get("desc", ""),
            "confidence": trade_info.get("confidence", 50),
            "ai_reason": trade_info.get("ai_reason", ""),
            "profit": profit,
            "result": result
        }
        
        if result == "win":
            self.data["wins"].insert(0, trade_record)
            self.data["wins"] = self.data["wins"][:self.max_wins]
            self.data["stats"]["total_wins"] += 1
        else:
            self.data["losses"].insert(0, trade_record)
            self.data["losses"] = self.data["losses"][:self.max_losses]
            self.data["stats"]["total_losses"] += 1
        
        self.data["stats"]["total_trades"] += 1
        total = int(self.data["stats"].get("total_wins") or 0) + int(self.data["stats"].get("total_losses") or 0)
        if total > 0:
            wins = int(self.data["stats"].get("total_wins") or 0)
            self.data["stats"]["win_rate"] = (wins / total) * 100
        
        self._save()
    
    def get_recent_wins(self, limit=20):
        """Retorna os últimos wins"""
        return self.data["wins"][:limit]
    
    def get_recent_losses(self, limit=20):
        """Retorna os últimos losses"""
        return self.data["losses"][:limit]
    
    def get_all_recent(self):
        """Retorna todos os trades recentes (wins + losses)"""
        return {
            "wins": self.data["wins"],
            "losses": self.data["losses"],
            "stats": self.data["stats"]
        }
    
    def get_patterns_that_lose(self):
        """Analisa padrões que mais dão loss"""
        patterns = {}
        for loss in self.data["losses"]:
            pattern = loss.get("pattern", "UNKNOWN")
            if pattern not in patterns:
                patterns[pattern] = 0
            patterns[pattern] += 1
        
        # Ordenar por frequência
        sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)
        return sorted_patterns[:5]
    
    def get_patterns_that_win(self):
        """Analisa padrões que mais dão win"""
        patterns = {}
        for win in self.data["wins"]:
            pattern = win.get("pattern", "UNKNOWN")
            if pattern not in patterns:
                patterns[pattern] = 0
            patterns[pattern] += 1
        
        sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)
        return sorted_patterns[:5]
    
    def get_pair_performance(self):
        """Analisa performance por par"""
        pairs = {}
        
        for trade in self.data["wins"] + self.data["losses"]:
            pair = trade.get("pair", "UNKNOWN")
            if pair not in pairs:
                pairs[pair] = {"wins": 0, "losses": 0}
            
            if trade["result"] == "win":
                pairs[pair]["wins"] += 1
            else:
                pairs[pair]["losses"] += 1
        
        # Calcular win rate por par
        for pair in pairs:
            total = pairs[pair]["wins"] + pairs[pair]["losses"]
            pairs[pair]["win_rate"] = (pairs[pair]["wins"] / total * 100) if total > 0 else 0
        
        return pairs
    
    def should_avoid_pattern(self, pattern):
        """Verifica se um padrão deve ser evitado (muitos losses)"""
        loss_count = sum(1 for loss_item in self.data["losses"] if pattern in loss_item.get("pattern", ""))
        win_count = sum(1 for w in self.data["wins"] if pattern in w.get("pattern", ""))
        
        if loss_count + win_count >= 5:  # Pelo menos 5 trades com esse padrão
            total = max(loss_count + win_count, 1)  # Proteção contra divisão por zero
            win_rate = (win_count / total) * 100
            return win_rate < 40  # Se win rate < 40%, evitar
        
        return False
    
    def get_learning_summary(self):
        """Gera um resumo para a IA usar no aprendizado"""
        losing_patterns = self.get_patterns_that_lose()
        winning_patterns = self.get_patterns_that_win()
        pair_perf = self.get_pair_performance()
        
        summary = {
            "total_trades": self.data["stats"]["total_trades"],
            "win_rate": self.data["stats"]["win_rate"],
            "avoid_patterns": [p[0] for p in losing_patterns if p[1] >= 3],
            "prefer_patterns": [p[0] for p in winning_patterns if p[1] >= 2],
            "best_pairs": [p for p, s in pair_perf.items() if s["win_rate"] >= 60],
            "worst_pairs": [p for p, s in pair_perf.items() if s["win_rate"] < 40],
            "recent_losses": [loss_item.get("desc", "") for loss_item in self.data["losses"][:5]],
            "recent_wins": [w.get("desc", "") for w in self.data["wins"][:5]]
        }
        
        return summary
