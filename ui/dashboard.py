# ui/dashboard.py - Professional Dashboard (ASCII-safe)
from __future__ import annotations

from datetime import datetime
import time

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


class Dashboard:
    def __init__(self, config):
        self.console = Console(style="white on black")
        self.config = config
        self.logs = []
        self.system_logs = []

        self.ai_state = "OFF"  # OFF | ONLINE | READY | DEGRADED | LIMITED
        self.ai_analyzer = None  # Referência ao AI Analyzer

        self._cached_vol = 55
        self._last_vol_update = 0.0

        self.layout = Layout()
        self._grid_left_ratio = 1
        self._grid_right_ratio = 1

        self.layout.split_column(
            Layout(name="top_bar", size=4),
            Layout(name="main_grid", ratio=1),
            Layout(name="footer", size=15),
        )
        self.layout["main_grid"].split_row(
            Layout(name="left_panel", ratio=self._grid_left_ratio),
            Layout(name="right_panel", ratio=self._grid_right_ratio),
        )
        self.layout["footer"].split_row(
            Layout(name="footer_left", ratio=self._grid_left_ratio),
            Layout(name="footer_right", ratio=self._grid_right_ratio),
        )
    
    def set_ai_analyzer(self, analyzer):
        """Define referência ao AI Analyzer para obter status real"""
        self.ai_analyzer = analyzer
    
    def update_ai_state(self):
        """Atualiza estado da IA baseado no analyzer"""
        if self.ai_analyzer:
            try:
                status = self.ai_analyzer.get_ai_status()
                self.ai_state = status
            except Exception:
                pass

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        msg_lower = message.lower()

        if "wait" in message or "aguardando proxima" in msg_lower:
            return

        if "[STRATEGY]" in message or "[FIA]" in message:
            if "resist" in msg_lower or "suport" in msg_lower:
                clean = message.split("]")[-1].strip()
                self.system_logs.append(f"[{timestamp}] [STR] {clean}")
            return

        if "[AI]" in message:
            clean = message.split("]")[-1].strip()
            if any(k in msg_lower for k in ("conectad", "ativa", "online")):
                self.ai_state = "ONLINE"
            if "desativ" in msg_lower or "chave" in msg_lower:
                self.ai_state = "OFF"
            if "timeout" in msg_lower or "rate" in msg_lower:
                self.ai_state = "DEGRADED"

            tag = "AI"
            if "confirm" in msg_lower:
                tag = "AI+"
            elif "rejeit" in msg_lower or "nao" in msg_lower:
                tag = "AI-"
            elif "evit" in msg_lower:
                tag = "AI!"

            self.system_logs.append(f"[{timestamp}] [{tag}] {clean}")
            return

        if "[IQ]" in message or "IQ_HANDLER" in message:
            if any(k in msg_lower for k in ("falha", "erro", "error")):
                self.system_logs.append(f"[{timestamp}] [IQ] {message}")
            return

        clean_msg = message
        if "WIN" in message:
            clean_msg = f"[green]WIN[/] {message}"
        elif "LOSS" in message:
            clean_msg = f"[red]LOSS[/] {message}"
        elif any(k in message for k in ("SINAL", "CALL", "PUT")):
            clean_msg = f"[cyan]SIGNAL[/] {message}"

        self.logs.append(f"[{timestamp}] {clean_msg}")
        if len(self.logs) > 15:
            self.logs.pop(0)
        if len(self.system_logs) > 15:
            self.system_logs.pop(0)

    def _bar(self, pct: float, length: int, *, color: str) -> str:
        filled = int((pct / 100) * length)
        filled = max(0, min(length, filled))
        empty = length - filled
        return f"[{color}]{'=' * filled}[/][dim]{'.' * empty}[/]"

    def _get_signal_strength(self) -> str:
        now = time.time()
        if now - self._last_vol_update > 10:
            phase = (now / 12.0) % (2 * 3.14159)
            target = 55 + int(30 * ((phase - 1.57079) / 1.57079))
            self._cached_vol = max(20, min(92, target))
            self._last_vol_update = now

        val = int(self._cached_vol)
        color = "green" if val > 70 else "bright_yellow" if val > 40 else "red"
        return f"{self._bar(val, 24, color=color)} [{color}]{val:>3d}%[/]"

    def _render_ai_badge(self) -> str:
        badges = {
            "ONLINE": "[bold green]AI ONLINE[/bold green]",
            "READY": "[bold green]AI ONLINE[/bold green]",
            "DEGRADED": "[bold yellow]AI DEGRADED[/bold yellow]",
            "LIMITED": "[bold red]AI LIMITED[/bold red]",
            "OFF": "[dim]AI OFF[/dim]",
            "DISABLED": "[dim]AI OFF[/dim]",
        }
        return badges.get(self.ai_state, "[dim]AI OFF[/dim]")

    def _render_candle_progress(self, time_to_close: int) -> str:
        duration = max(1, int(getattr(self.config, "timeframe", 1)) * 60)
        remaining = max(0, min(duration, int(time_to_close)))
        elapsed = max(0, duration - remaining)
        pct = int((elapsed / duration) * 100)
        color = "bright_cyan" if remaining > 10 else "bright_magenta"
        return f"{self._bar(pct, 24, color=color)} [{color}]{pct:>3d}%[/]"

    def _render_profit_bar(self, current_profit: float, goal: float) -> str:
        if goal <= 0:
            pct = 0
        else:
            pct = min(100, max(0, (current_profit / goal) * 100))
        if current_profit >= goal:
            color = "bold green"
        elif current_profit >= goal * 0.5:
            color = "bright_cyan"
        elif current_profit > 0:
            color = "bright_yellow"
        else:
            color = "red"
        return self._bar(pct, 24, color=color)

    def _render_risk_meter(self, current_loss: float, stop_loss: float) -> str:
        if stop_loss <= 0:
            return "[dim]N/A[/dim]"
        # Considera risco apenas quando estiver em perda no dia.
        # Se estiver positivo, risco = 0%.
        if current_loss >= 0:
            pct = 0
        else:
            pct = abs(current_loss / stop_loss) * 100
        color = "green" if pct < 33 else "bright_yellow" if pct < 66 else "red"
        return f"{self._bar(pct, 18, color=color)} [{color}]{pct:.0f}%[/]"

    def render(self, current_profit: float, time_to_close: int = 0, worker_status: str = ""):
        try:
            # 🆕 Atualizar estado da IA antes de renderizar
            self.update_ai_state()
            
            if time_to_close <= 0:
                try:
                    duration = int(getattr(self.config, "timeframe", 1)) * 60
                    now = time.time()
                    time_to_close = int(duration - (now % duration))
                    if time_to_close <= 0:
                        time_to_close = duration
                except Exception:
                    time_to_close = 60

            acc_type = "REAL" if self.config.account_type == "REAL" else "DEMO"
            acc_color = "bold bright_green" if acc_type == "REAL" else "bright_cyan"

            header = Table.grid(expand=True, padding=(0, 1))
            header.add_column()
            header.add_column(justify="center")
            header.add_column(justify="right")

            line_1 = "[bold white]DARK[/] [bold white]BLACK[/] [bold bright_magenta]BOT[/]"
            line_2 = f"[{acc_color}]ACCOUNT: {acc_type}[/]  |  {self._render_ai_badge()}"
            clock = datetime.now().strftime("%d/%m %H:%M:%S")
            header.add_row(line_1, line_2, clock)
            header.add_row("[dim]AI POWERED TRADING DASHBOARD[/dim]", "", "")

            self.layout["top_bar"].update(
                Panel(header, border_style="bright_magenta", box=box.DOUBLE, style="on black")
            )

            goal = getattr(self.config, "profit_goal", 100)
            stop_loss = getattr(self.config, "stop_loss", 0)

            fin_table = Table.grid(expand=True, padding=(0, 1))
            fin_table.add_column(min_width=18)
            fin_table.add_column(justify="right")

            balance_val = f"[bold white]R$ {self.config.balance:,.2f}[/]"
            fin_table.add_row("[bright_cyan]Saldo[/]", balance_val)

            p_color = "bright_green" if current_profit >= 0 else "bright_red"
            profit_val = f"[bold {p_color}]R$ {current_profit:+,.2f}[/]"
            fin_table.add_row("[bright_magenta]Resultado[/]", profit_val)

            pct = min(100, max(0, (current_profit / goal) * 100)) if goal > 0 else 0
            fin_table.add_row("[yellow]Progresso[/]", f"[bold {p_color}]{pct:.1f}%[/]")
            fin_table.add_row("", self._render_profit_bar(current_profit, goal))
            fin_table.add_row("", "")
            fin_table.add_row("[dim]Meta diaria[/]", f"[bold]R$ {goal:,.0f}[/]")
            fin_table.add_row("[dim]Stop loss[/]", f"[bold]R$ {stop_loss:,.0f}[/]")
            fin_table.add_row("", "")
            fin_table.add_row("[red]Risco[/]", self._render_risk_meter(current_profit, stop_loss))

            fin_panel = Panel(
                fin_table,
                title="[bold bright_cyan]FINANCEIRO[/]",
                border_style="bright_cyan",
                box=box.DOUBLE,
                padding=(1, 2),
                style="on black",
            )
            self.layout["left_panel"].update(fin_panel)

            mins = int(time_to_close) // 60
            secs = int(time_to_close) % 60
            timer_color = "white" if time_to_close > 30 else "bright_magenta" if time_to_close > 10 else "bold red"

            market_table = Table.grid(expand=True, padding=(0, 1))
            market_table.add_column(min_width=18)
            market_table.add_column(justify="right")

            market_table.add_row("[bright_magenta]Estrategia[/]", f"[bold]{self.config.strategy_name}[/]")
            market_table.add_row("[bright_cyan]Ativo(s)[/]", f"[bold white]{self.config.asset}[/]")
            market_table.add_row("[white]IA[/]", self._render_ai_badge())
            market_table.add_row("[yellow]Timeframe[/]", f"[bold bright_cyan]M{self.config.timeframe}[/]")
            market_table.add_row("", "")
            market_table.add_row(
                f"[{timer_color}]Fechamento[/]",
                f"[{timer_color}]{mins:02d}:{secs:02d}[/] [dim]restantes[/]",
            )
            market_table.add_row("", self._render_candle_progress(time_to_close))
            market_table.add_row("", "")
            market_table.add_row("[green]Volatilidade[/]", self._get_signal_strength())

            market_panel = Panel(
                market_table,
                title="[bold bright_magenta]MERCADO[/]",
                border_style="bright_magenta",
                box=box.DOUBLE,
                padding=(1, 2),
                style="on black",
            )
            self.layout["right_panel"].update(market_panel)

            status_bar = f"[bold white]STATUS:[/] [dim]{worker_status}[/]" if worker_status else ""
            log_txt = "\n".join(self.logs[-8:]) if self.logs else "[dim]Aguardando operacoes...[/]"
            content = Group(
                Text.from_markup(status_bar),
                Text("-" * 46, style="dim"),
                Text.from_markup(log_txt),
            )
            exec_panel = Panel(
                content,
                title="[bold bright_cyan]EXECUCAO[/]",
                border_style="bright_cyan",
                box=box.SQUARE,
                padding=(1, 2),
                style="on black",
            )
            self.layout["footer_left"].update(exec_panel)

            sys_txt = "\n".join(self.system_logs[-9:]) if self.system_logs else "[dim]Inicializando...[/]"
            sys_panel = Panel(
                sys_txt,
                title="[bold bright_white]SISTEMA[/]",
                border_style="bright_white",
                box=box.SQUARE,
                padding=(1, 2),
                style="on black",
            )
            self.layout["footer_right"].update(sys_panel)

            return self.layout
        except Exception as e:
            err_txt = Text(f"UI error: {e}", style="bold red")
            return Panel(err_txt, border_style="red", style="on black")
