# utils/backtester.py
"""
Sistema de Backtest para analisar estratégias com dados históricos
"""
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.console import Console

console = Console()

class Backtester:
    def __init__(self, api_handler):
        self.api = api_handler
        
    def run_backtest(self, pairs, strategies, timeframe=1, candle_count=100):
        """
        Executa backtest em todas as combinações de par/estratégia
        
        Args:
            pairs: Lista de paridades
            strategies: Lista de instâncias de estratégia
            timeframe: Timeframe em minutos
            candle_count: Quantidade de velas para testar
            
        Returns:
            dict: Resultados do backtest
        """
        results = {}
        total_tests = len(pairs) * len(strategies)
        current_test = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Backtesting..."),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[dim]{task.description}"),
        ) as progress:
            
            task = progress.add_task("", total=total_tests)
            
            for pair in pairs:
                results[pair] = {}
                
                # Obter velas historicas
                candles = self.api.get_candles(pair, timeframe, candle_count)
                
                if len(candles) < 30:
                    progress.update(task, advance=len(strategies), 
                                  description=f"{pair}: Dados insuficientes")
                    for strat in strategies:
                        results[pair][strat.name] = {"wins": 0, "losses": 0, "win_rate": 0}
                    continue
                
                for strategy in strategies:
                    current_test += 1
                    progress.update(task, advance=1, 
                                  description=f"{pair} | {strategy.name[:20]}")
                    
                    # Simular trades
                    wins = 0
                    losses = 0
                    
                    # Testar cada vela (exceto ultimas 3)
                    for i in range(30, len(candles) - 3):
                        # Criar slice de velas ate o ponto i
                        test_candles = candles[:i+1]
                        
                        # Simular check_signal com velas historicas
                        try:
                            signal = self._simulate_signal(strategy, test_candles)
                            
                            if signal:
                                # Verificar resultado (proxima vela)
                                next_candle = candles[i + 1]
                                is_green = next_candle['close'] > next_candle['open']
                                
                                if signal == 'CALL' and is_green:
                                    wins += 1
                                elif signal == 'PUT' and not is_green:
                                    wins += 1
                                else:
                                    losses += 1
                        except Exception:
                            pass
                    
                    # Calcular win rate
                    total = wins + losses
                    win_rate = (wins / total * 100) if total > 0 else 0
                    
                    results[pair][strategy.name] = {
                        "wins": wins,
                        "losses": losses,
                        "total": total,
                        "win_rate": win_rate
                    }
        
        return results
    
    def _simulate_signal(self, strategy, candles):
        """Simula geração de sinal com velas históricas"""
        if len(candles) < 20:
            return None
        
        current = candles[-2]  # Penultima vela (a ultima ainda nao fechou)
        
        # Calcular body ratio
        body = abs(current['close'] - current['open'])
        range_total = current['high'] - current['low']
        
        if range_total == 0:
            return None
        
        body_ratio = body / range_total
        
        if body_ratio <= 0.20:
            return None
        
        # Sinal baseado na vela
        if current['close'] > current['open']:
            return 'CALL'
        else:
            return 'PUT'
    
    def display_results(self, results, strategies):
        """Exibe resultados do backtest em tabela"""
        console.print("\n[bold cyan]📊 RESULTADOS DO BACKTEST[/bold cyan]\n")
        
        # Criar tabela
        table = Table(title="Win Rate por Par/Estratégia")
        table.add_column("Paridade", style="cyan")
        
        for strat in strategies:
            table.add_column(strat.name[:15], justify="center")
        
        table.add_column("Melhor", style="green", justify="center")
        
        # Adicionar linhas
        for pair, strat_results in results.items():
            row = [pair]
            best_rate = 0
            best_strat = ""
            
            for strat in strategies:
                rate = strat_results.get(strat.name, {}).get("win_rate", 0)
                total = strat_results.get(strat.name, {}).get("total", 0)
                
                # Colorir baseado no win rate
                if rate >= 60:
                    color = "green"
                elif rate >= 50:
                    color = "yellow"
                else:
                    color = "red"
                
                row.append(f"[{color}]{rate:.0f}%[/{color}] ({total})")
                
                if rate > best_rate:
                    best_rate = rate
                    best_strat = strat.name[:10]
            
            row.append(f"[bold]{best_strat}[/bold]")
            table.add_row(*row)
        
        console.print(table)
        
        # Recomendar melhor combinação
        best_combo = self._find_best_combo(results)
        if best_combo:
            console.print(f"\n[bold green]🎯 Recomendação: {best_combo['pair']} + {best_combo['strategy']} ({best_combo['win_rate']:.0f}%)[/bold green]")
        
        return best_combo
    
    def _find_best_combo(self, results):
        """Encontra melhor combinação par/estratégia"""
        best = None
        
        for pair, strat_results in results.items():
            for strat_name, data in strat_results.items():
                if data.get("total", 0) >= 10:  # Minimo 10 trades
                    if best is None or data["win_rate"] > best["win_rate"]:
                        best = {
                            "pair": pair,
                            "strategy": strat_name,
                            "win_rate": data["win_rate"]
                        }
        
        return best
