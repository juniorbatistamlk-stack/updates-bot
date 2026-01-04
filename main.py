# main.py
import sys
import time
import threading
import logging
import traceback
import os
import socket
from datetime import datetime

# External Libs
from rich.console import Console
from rich.align import Align
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, FloatPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markup import escape
from rich.text import Text
from rich import box
from rich.padding import Padding
from rich.console import Group
from dotenv import load_dotenv
from openai import OpenAI

# Internal Modules
from config import Config
from api.iq_handler import IQHandler
from ui.dashboard import Dashboard
from ui.cli_style import menu_table, info_kv, print_panel, title_panel, section
from utils.ai_analyzer import AIAnalyzer
from utils.memory import TradingMemory
from utils.backtester import Backtester
from utils.smart_trader import SmartTrader
from utils.license_validator_v4 import validate_license
from utils.window_manager import set_console_icon, set_console_title
from utils.credentials_manager import (
    save_credentials, load_credentials,
    get_masked_email, clear_credentials,
)

# Strategies
from strategies.ferreira import FerreiraStrategy
from strategies.price_action import PriceActionStrategy
from strategies.logica_preco import LogicaPrecoStrategy
from strategies.ana_tavares import AnaTavaresStrategy
from strategies.conservador import ConservadorStrategy
from strategies.alavancagem import AlavancagemStrategy
from strategies.alavancagem_sr import AlavancagemSRStrategy
from strategies.ferreira_price_action import FerreiraPriceActionStrategy
from strategies.ferreira_snr_advanced import FerreiraSNRAdvancedStrategy
from strategies.ferreira_moving_avg import FerreiraMovingAvgStrategy
from strategies.ferreira_primeiro_registro import FerreiraPrimeiroRegistroStrategy
from strategies.trader_machado import TraderMachadoStrategy
from strategies.ai_god_mode import AiGodModeStrategy

# =============================================================================
# SETUP GLOBAL
# =============================================================================
load_dotenv()

# Timeout global para conexões (30s)
socket.setdefaulttimeout(30)

# Force UTF-8 for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Suppress internal logging
logging.disable(logging.CRITICAL)
logging.getLogger().setLevel(logging.CRITICAL)

# === CONFIGURAR ÍCONE E TÍTULO DA JANELA ===
set_console_title("Dark Black Bot - AI Powered")
set_console_icon("darkblackbot.ico")

console = Console(style="white on black")


def black_spacer(lines: int = 1) -> None:
    """Imprime linhas preenchidas com fundo preto para evitar faixas cinzas no terminal."""
    try:
        width = max(1, int(console.size.width))
    except Exception:
        width = 120
    for _ in range(max(0, int(lines))):
        console.print(" " * width, style="on black")


def _read_env_file(env_path: str = ".env") -> tuple[list[str], dict[str, int]]:
    """Lê .env preservando linhas; retorna (linhas, indice_por_chave)."""
    try:
        if not os.path.exists(env_path):
            return [], {}
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return [], {}

    key_to_index: dict[str, int] = {}
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _v = line.split("=", 1)
        k = k.strip()
        if k:
            key_to_index[k] = i
    return lines, key_to_index


def _write_env_file(updates: dict[str, str], env_path: str = ".env") -> bool:
    """Atualiza (ou cria) o .env substituindo chaves existentes, sem duplicar."""
    try:
        lines, key_to_index = _read_env_file(env_path)
        if not lines:
            lines = ["# Dark Black Bot - Configuração Local"]

        for key, value in updates.items():
            if value is None:
                continue
            safe_value = str(value)
            rendered = f'{key}="{safe_value}"'
            if key in key_to_index:
                lines[key_to_index[key]] = rendered
            else:
                lines.append(rendered)

        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception:
        return False


def _classify_ai_validation_error(e: Exception) -> tuple[bool, str]:
    msg = str(e)
    status_code = getattr(e, "status_code", None)
    if status_code is None:
        resp = getattr(e, "response", None)
        status_code = getattr(resp, "status_code", None)

    if status_code == 429 or "429" in msg or "rate" in msg.lower() or "quota" in msg.lower() or "resource_exhausted" in msg.lower():
        return True, "Chave OK, mas limite/QUOTA atingido (429)"

    if status_code in (401, 403) or "401" in msg or "403" in msg or "unauthorized" in msg.lower() or "permission" in msg.lower() or "api key" in msg.lower():
        return False, "Chave inválida/sem permissão (401/403)"

    if status_code == 404 or "404" in msg:
        return False, "Modelo não encontrado (404)"

    if status_code == 400 or "400" in msg or "bad request" in msg.lower():
        return False, "Requisição inválida (400) — verifique modelo/provedor"

    short = msg.replace("\n", " ").strip()
    if len(short) > 180:
        short = short[:180] + "..."
    return False, f"Erro ao validar: {short}"


def _validate_ai_key(provider: str, api_key: str) -> tuple[bool, str]:
    """Valida uma API key diretamente (sem depender do modo Multi-Provider)."""
    provider = (provider or "").lower().strip()
    if provider == "groq":
        base_url = "https://api.groq.com/openai/v1"
        model = os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile"
    elif provider == "gemini":
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        model = os.getenv("GEMINI_MODEL") or "gemini-2.0-flash"
    else:
        base_url = "https://openrouter.ai/api/v1"
        model = os.getenv("OPENROUTER_MODEL") or "meta-llama/llama-3.3-70b-instruct:free"

    try:
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=25.0)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "HI"}],
            max_tokens=5,
            temperature=0,
        )
        return True, "Conexão OK"
    except Exception as e:
        return _classify_ai_validation_error(e)


def _configure_three_ai_keys(console: Console) -> bool:
    """Wizard: configura até 3 chaves (Gemini -> Groq -> OpenRouter) e salva 1 vez.

    Se o usuário quiser trocar depois, deve rodar este wizard novamente.
    """
    choice = Prompt.ask(
        "  🤖 [bright_white]Deseja configurar suas 3 API Keys agora?[/bright_white]",
        choices=["s", "n"],
        default="s",
    )
    if choice.lower() != "s":
        return False

    providers = [
        ("gemini", "GEMINI_API_KEY", "GEMINI"),
        ("groq", "GROQ_API_KEY", "GROQ"),
        ("openrouter", "OPENROUTER_API_KEY", "OPENROUTER"),
    ]

    updates: dict[str, str] = {}
    configured_any = False

    for prov, env_key, label in providers:
        while True:
            black_spacer(1)
            console.print(Padding(f"[bold]Digite aqui a API Key do {label}[/bold]", (0, 0), style="on black", expand=True))
            console.print(Padding("[dim](ENTER para pular este provedor)[/dim]", (0, 0), style="on black", expand=True))
            input_key = Prompt.ask("API Key", password=True, default="").strip()

            if not input_key:
                console.print(Padding(f"[yellow]• {label}: pulado[/yellow]", (0, 0), style="on black", expand=True))
                break

            console.print(Padding("[dim]Validando chave... aguarde[/dim]", (0, 0), style="on black", expand=True))
            ok, msg = _validate_ai_key(prov, input_key)
            if ok:
                updates[env_key] = input_key
                configured_any = True
                console.print(Padding(f"[green]✓ {label}: chave válida ({msg})[/green]", (0, 0), style="on black", expand=True))
                break

            console.print(Padding(f"[bold red]❌ {label}: {msg}[/bold red]", (0, 0), style="on black", expand=True))
            if Prompt.ask("Deseja tentar novamente?", choices=["s", "n"], default="s") == "n":
                console.print(Padding(f"[yellow]• {label}: não configurado[/yellow]", (0, 0), style="on black", expand=True))
                break

    # Marcar que o wizard já foi executado (para não ficar perguntando sempre)
    updates["AI_KEYS_CONFIGURED"] = "1"

    if not _write_env_file(updates):
        console.print(Padding("[red]Erro ao salvar .env. As chaves valerão apenas nesta sessão.[/red]", (0, 0), style="on black", expand=True))
    else:
        # Atualizar env em runtime
        for k, v in updates.items():
            os.environ[k] = v
        try:
            load_dotenv(override=True)
        except Exception:
            pass
        if configured_any:
            console.print(Padding("[bright_green]✓ Configuração salva no .env (local deste PC).[/bright_green]", (0, 0), style="on black", expand=True))
        else:
            console.print(Padding("[yellow]⚠ Nenhuma chave foi configurada.[/yellow]", (0, 0), style="on black", expand=True))

    return configured_any


def _configure_single_ai_key(console: Console, provider: str, env_key: str, label: str) -> bool:
    """Configura 1 chave específica e salva no .env."""
    while True:
        black_spacer(1)
        console.print(Padding(f"[bold]Digite aqui a API Key do {label}[/bold]", (0, 0), style="on black", expand=True))
        console.print(Padding("[dim](ENTER para cancelar)[/dim]", (0, 0), style="on black", expand=True))
        input_key = Prompt.ask("API Key", password=True, default="").strip()

        if not input_key:
            return False

        console.print(Padding("[dim]Validando chave... aguarde[/dim]", (0, 0), style="on black", expand=True))
        ok, msg = _validate_ai_key(provider, input_key)
        if ok:
            updates = {
                env_key: input_key,
                "AI_KEYS_CONFIGURED": "1",
            }
            if _write_env_file(updates):
                for k, v in updates.items():
                    os.environ[k] = v
                try:
                    load_dotenv(override=True)
                except Exception:
                    pass
                console.print(Padding(f"[green]✓ {label}: chave salva no .env ({msg})[/green]", (0, 0), style="on black", expand=True))
            else:
                os.environ[env_key] = input_key
                console.print(Padding(f"[yellow]⚠ {label}: não foi possível salvar no .env (usando só nesta sessão)[/yellow]", (0, 0), style="on black", expand=True))
            return True

        console.print(Padding(f"[bold red]❌ {label}: {msg}[/bold red]", (0, 0), style="on black", expand=True))
        if Prompt.ask("Deseja tentar novamente?", choices=["s", "n"], default="s") == "n":
            return False


def _manage_multi_ai_keys(console: Console) -> bool:
    """Menu para trocar API keys de todas as IAs (individual ou todas)."""
    changed = False
    while True:
        black_spacer(1)
        print_panel(
            console,
            menu_table(
                "Gerenciar API Keys (Multi-Provider)",
                [
                    ("1", "Trocar Gemini", "Atualiza GEMINI_API_KEY"),
                    ("2", "Trocar Groq", "Atualiza GROQ_API_KEY"),
                    ("3", "Trocar OpenRouter", "Atualiza OPENROUTER_API_KEY"),
                    ("4", "Trocar todas", "Gemini → Groq → OpenRouter"),
                    ("5", "Voltar", "Retornar ao menu anterior"),
                ],
                border_style="bright_cyan",
            ),
        )

        action = Prompt.ask("  🔑 [bright_white]Escolha[/bright_white]", choices=["1", "2", "3", "4", "5"], default="5")
        if action == "5":
            return changed

        if action == "1":
            changed = _configure_single_ai_key(console, "gemini", "GEMINI_API_KEY", "GEMINI") or changed
        elif action == "2":
            changed = _configure_single_ai_key(console, "groq", "GROQ_API_KEY", "GROQ") or changed
        elif action == "3":
            changed = _configure_single_ai_key(console, "openrouter", "OPENROUTER_API_KEY", "OPENROUTER") or changed
        elif action == "4":
            changed = _configure_three_ai_keys(console) or changed

# Shared State
current_profit = 0.0
worker_status = "Iniciando..."
stop_threads = False
bot_logs = []
ui_seconds_left = 0

def verify_license():
    """Verifica licença antes de iniciar"""
    # A validação v4 já printa mensagens e faz inputs se necessário
    # check() retorna Tuple (Ok, Msg) ou Bool? O v4 retorna Bool.
    # Se False, o v4 já lida com mensagens de expiração/erro/ativação loop.
    if not validate_license():
        sys.exit(1) # Sai se não validou
    return True

def log_msg(msg):
    global bot_logs
    timestamp = datetime.now().strftime("%H:%M:%S")
    bot_logs.append(f"[{timestamp}] {msg}")
    if len(bot_logs) > 10:
        bot_logs.pop(0)

def show_goal_achieved_screen(profit):
    """Tela especial de parabéns ao atingir a meta"""
    from rich.panel import Panel
    from rich.text import Text
    from rich.align import Align
    
    black_spacer(2)
    
    # Arte ASCII de troféu
    trophy = """
    ⠀⠀⠀⠀⠀⣀⣀⡀⠀⠀⠀⠀⠀
    ⠀⠀⠀⢰⣿⣿⣿⣿⡆⠀⠀⠀⠀
    ⠀⠀⠀⠘⣿⣿⣿⣿⠃⠀⠀⠀⠀
    ⠀⠀⠀⠀⠙⢿⡿⠋⠀⠀⠀⠀⠀
    ⠀⠀⠀⢠⣴⣶⣶⣦⡄⠀⠀⠀⠀
    ⠀⠀⠀⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀
    ⠀⠀⠀⠙⠻⠿⠿⠟⠋⠀⠀⠀⠀
    """
    
    message = Text()
    message.append("🎉 ", style="bold bright_yellow")
    message.append("PARABÉNS! META ATINGIDA!", style="bold bright_green")
    message.append(" 🎉", style="bold bright_yellow")
    
    profit_text = Text()
    profit_text.append("💰 Lucro do Dia: ", style="bold bright_white")
    profit_text.append(f"R$ {profit:.2f}", style="bold bright_green")
    
    motivation = [
        "✨ Você provou que disciplina e estratégia funcionam!",
        "🎯 A consistência é o segredo dos grandes traders.",
        "💎 Proteja esse lucro e volte amanhã ainda mais forte!",
        "🚀 Grandes resultados vêm de pequenas vitórias diárias.",
        "",
        "📊 Dica Profissional:",
        "   • Não tente recuperar mais - a ganância é inimiga do lucro",
        "   • Anote o que funcionou hoje para replicar amanhã",
        "   • Comemore essa vitória, você merece! 🍾"
    ]
    
    content = Text()
    content.append(trophy, style="bright_yellow", justify="center")
    content.append("\n\n")
    content.append(message, justify="center")
    content.append("\n\n")
    content.append(profit_text, justify="center")
    content.append("\n\n")
    for line in motivation:
        content.append(line + "\n", style="bright_white" if line else "")
    
    panel = Panel(
        Align.center(content),
        border_style="bright_green",
        padding=(1, 2),
        title="[bold bright_green]═══ MISSÃO CUMPRIDA ═══[/]",
        subtitle="[dim]O mercado recompensa os disciplinados[/]"
    )
    
    console.print(panel, style="on black")
    black_spacer(1)

def show_stop_loss_screen(loss):
    """Tela especial de motivação ao acionar stop loss"""
    from rich.panel import Panel
    from rich.text import Text
    from rich.align import Align
    
    black_spacer(2)
    
    message = Text()
    message.append("🛑 ", style="bold bright_red")
    message.append("STOP LOSS ACIONADO", style="bold bright_red")
    message.append(" 🛑", style="bold bright_red")
    
    loss_text = Text()
    loss_text.append("💸 Perda do Dia: ", style="bold bright_white")
    loss_text.append(f"R$ {abs(loss):.2f}", style="bold bright_red")
    
    motivation = [
        "",
        "💪 NÃO DESISTA! Todo trader passa por dias difíceis.",
        "",
        "🎯 O que separa vencedores de perdedores:",
        "   ✓ Vencedores aceitam o loss e voltam mais fortes",
        "   ✗ Perdedores tentam recuperar e quebram a banca",
        "",
        "🧠 Lições do Mercado:",
        "   • Este loss te protegeu de perdas maiores",
        "   • Traders profissionais têm dias ruins também",
        "   • O mercado estará aqui amanhã - sua banca não",
        "",
        "🌅 Amanhã é um novo dia:",
        "   📚 Revise o que deu errado hoje",
        "   🎮 Volte descansado e focado",
        "   💎 Preserve sua banca - ela é seu maior ativo",
        "",
        "🔥 Lembre-se: Trading é uma maratona, não uma corrida!",
        "   Cada dia é uma nova oportunidade de crescer."
    ]
    
    content = Text()
    content.append(message, justify="center")
    content.append("\n\n")
    content.append(loss_text, justify="center")
    content.append("\n")
    for line in motivation:
        if "NÃO DESISTA" in line:
            content.append(line + "\n", style="bold bright_yellow")
        elif line.startswith("   ✓"):
            content.append(line + "\n", style="bright_green")
        elif line.startswith("   ✗"):
            content.append(line + "\n", style="dim red")
        elif line.startswith("🔥"):
            content.append(line + "\n", style="bold bright_cyan")
        elif line.startswith(("🎯", "🧠", "🌅")):
            content.append(line + "\n", style="bold bright_white")
        else:
            content.append(line + "\n", style="bright_white" if line else "")
    
    panel = Panel(
        Align.center(content),
        border_style="bright_red",
        padding=(1, 2),
        title="[bold bright_red]═══ PROTEÇÃO ATIVADA ═══[/]",
        subtitle="[dim]Viva para operar outro dia[/]"
    )
    
    console.print(panel, style="on black")
    black_spacer(1)


def get_strategy(choice, api, ai_analyzer=None):
    strategies = {
        1: FerreiraStrategy,
        2: PriceActionStrategy,
        3: LogicaPrecoStrategy,
        4: AnaTavaresStrategy,
        5: ConservadorStrategy,
        6: AlavancagemStrategy,
        7: AlavancagemSRStrategy,
        8: FerreiraPriceActionStrategy,
        9: FerreiraSNRAdvancedStrategy,
        10: FerreiraMovingAvgStrategy,
        11: FerreiraPrimeiroRegistroStrategy,
        12: TraderMachadoStrategy,
        13: AiGodModeStrategy
    }
    strategy_cls = strategies.get(choice, FerreiraStrategy)
    return strategy_cls(api, ai_analyzer)

def select_pairs(api):
    from rich import box
    from rich.table import Table

    # print_panel(console, header_panel("Seleção de Mercado • OTC 24h")) -> REMOVIDO
    # console.print(Align.center("[bold white]SELEÇÃO DE MERCADO OTC[/]"))
    print_panel(console, title_panel("SELEÇÃO DE MERCADO OTC", "OTC 24h", border_style="bright_cyan"))
    
    # Lista Completa de Pares OTC (modo normal)
    target_assets = [
        "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC", "NZDUSD-OTC", "USDCHF-OTC",
        "EURJPY-OTC", "GBPJPY-OTC", "EURGBP-OTC", "AUDJPY-OTC", "XAUUSD-OTC"
    ]
    
    black_spacer(1)
    console.print("[dim]Escaneando paridades OTC disponíveis...[/dim]", style="on black")
    scan = api.scan_available_pairs(target_assets)
    
    open_assets = []
    for a in target_assets:
        if scan.get(a, {}).get("open"):
            open_assets.append((a, scan[a]['payout']))
            
    if not open_assets:
        print_panel(console, info_kv(
            "OTC",
            [("Status", "[bold bright_red]Nenhum ativo OTC encontrado[/]"), ("Dica", "[dim]Verifique se a corretora está online.[/]")],
            border_style="bright_cyan",
        ))
        return ["EURUSD-OTC"] # Fallback

    # Lista com linhas divisórias
    t = Table(box=box.MINIMAL, expand=True, show_lines=True)
    t.style = "on black"
    t.add_column("#", justify="center", style="dim", width=4)
    t.add_column("Ativo", justify="center", style="bold white")
    t.add_column("Payout", justify="center")
    for i, (asset, payout) in enumerate(open_assets):
        p_color = "bright_green" if payout >= 80 else "bright_magenta" if payout >= 70 else "white"
        t.add_row(str(i + 1), asset, f"[{p_color}]{payout:.0f}%[/]")

    # Cabeçalho da lista simples
    console.print(Align.center(f"[dim]Total: {len(open_assets)} ativos encontrados[/dim]"), style="on black")
    # print_panel(console, info_kv("Lista", [("Ativos", "")], border_style="white")) -> REMOVIDO
    console.print(t, style="on black")
    console.rule(style="dim on black") # Fechamento visual sutil
        
    choices = Prompt.ask("Escolha (ex: 1,2,3 ou 'todas')", default="todas")
    
    if choices.lower() in ['todas', 'all']:
        selected = [x[0] for x in open_assets]
    else:
        indices = [int(x)-1 for x in choices.split(",") if x.strip().isdigit()]
        selected = [open_assets[i][0] for i in indices if 0 <= i < len(open_assets)]
        
    return selected if selected else [open_assets[0][0]]

def run_trading_session(api, strategy, pairs, cfg, memory, ai_analyzer):
    global current_profit, worker_status, stop_threads, bot_logs, ui_seconds_left
    
    current_profit = 0.0
    stop_threads = False
    bot_logs = []
    # Valor inicial para o timer não começar em 00:00
    try:
        ui_seconds_left = int(getattr(cfg, "timeframe", 1)) * 60
    except Exception:
        ui_seconds_left = 60
    
    cfg.asset = ", ".join(pairs) if len(pairs) > 1 else pairs[0]
    dashboard = Dashboard(cfg)
    
    def log_system_msg(msg):
        dashboard.log(msg)
    
    # Conectando loggers
    if hasattr(api, 'set_logger'):
        api.set_logger(log_system_msg)
        
    smart_trader = SmartTrader(api, strategy, pairs, memory, {}, ai_analyzer)
    smart_trader.set_system_logger(log_system_msg)

    # Conectar logger da IA ao painel do sistema (se existir)
    if ai_analyzer and hasattr(ai_analyzer, 'set_logger'):
        ai_analyzer.set_logger(log_system_msg)
        dashboard.set_ai_analyzer(ai_analyzer)  # 🆕 Conectar analyzer ao dashboard
        dashboard.log("[AI] ✅ IA conectada ao painel")
    elif not ai_analyzer:
        dashboard.log("[AI] ⚠️ IA desativada nesta sessão")
    
    if hasattr(strategy, 'set_logger'):
        strategy.set_logger(log_system_msg)
    
    console.print(
        Panel(
            f"[bold green]🚀 ROBÔ INICIADO - {strategy.name}[/bold green]\nParidades: {', '.join(pairs)}",
            border_style="green",
            style="on black",
            expand=True,
        ),
        style="on black",
    )
    
    def worker():
        global current_profit, worker_status, stop_threads, ui_seconds_left
        last_candle_traded = None
        cached_signal = None

        failed_pairs_this_candle = set()
        
        log_msg(f"[green]✅ Trader Ativo: {strategy.name}[/green]")
        
        while not stop_threads:
            try:
                # === VERIFICAR LIMITES ===
                if cfg.profit_goal > 0 and current_profit >= cfg.profit_goal:
                    stop_threads = True
                    show_goal_achieved_screen(current_profit)
                    break
                
                if current_profit <= -cfg.stop_loss:
                    stop_threads = True
                    show_stop_loss_screen(current_profit)
                    break
                
                # === CALCULAR TIMING ===
                candle_duration = cfg.timeframe * 60
                
                # Obter timestamp seguro com tratamento de erro
                try:
                    server_time = api.get_server_timestamp()
                except Exception:
                    # Se falhar (desconexão/sync), força None para cair na validação abaixo
                    server_time = 0
                
                # Sincronização básica
                if server_time <= 0:
                    worker_status = "⚠️ Sincronizando relógio..."
                    # Fallback local para manter o timer do painel vivo
                    try:
                        ui_seconds_left = (cfg.timeframe * 60) - (time.time() % (cfg.timeframe * 60))
                    except Exception:
                        ui_seconds_left = 0
                    time.sleep(1)
                    continue

                # Validar que é um número válido antes de qualquer conta
                if not isinstance(server_time, (int, float)) or server_time <= 0:
                    worker_status = "⚠️ Tempo inválido, aguardando..."
                    # Fallback local para manter o timer do painel vivo
                    try:
                        ui_seconds_left = (cfg.timeframe * 60) - (time.time() % (cfg.timeframe * 60))
                    except Exception:
                        ui_seconds_left = 0
                    time.sleep(2)
                    continue

                # CRITICAL FIX: Ensure no NoneType math
                candle_start = int(server_time) - (int(server_time) % int(candle_duration))
                candle_end = candle_start + candle_duration
                seconds_left = candle_end - server_time
                seconds_elapsed = server_time - candle_start

                # Compartilhar tempo restante (server-side) com o loop da UI.
                try:
                    ui_seconds_left = float(seconds_left)
                except Exception:
                    ui_seconds_left = 0
                
                # ID único da vela atual
                current_candle = candle_start
                
                # Resetar blacklist quando muda a vela
                if last_candle_traded != current_candle and seconds_elapsed < 2:
                    failed_pairs_this_candle.clear()
                
                # Já operou nesta vela? Aguardar próxima
                if last_candle_traded == current_candle:
                    worker_status = f"⏳ Aguardando próxima vela ({int(seconds_left)}s)"
                    time.sleep(1)
                    continue
                
                # OTIMIZAÇÃO DE IA (ECONOMIA DE TOKENS)
                # M1: Analisa nos últimos 15s | M5+: Analisa no último 45s (mais sinais)
                ai_window = 15 if cfg.timeframe == 1 else 45
                
                if seconds_left > ai_window:
                    cached_signal = None
                    wait_t = int(seconds_left - ai_window)
                    worker_status = f"⏳ Aguardando Janela IA | M{cfg.timeframe} ({wait_t}s)"
                    time.sleep(1)
                    continue
                
                # PERÍODO DE ANÁLISE E EXECUÇÃO (30-60s)
                # Buscar sinal se não tem
                if cached_signal is None:
                    worker_status = f"🔍 Analisando {len(pairs)} pares..."
                    analysis_start = time.time()
                    try:
                        cached_signal = smart_trader.analyze_all_pairs(cfg.timeframe, exclude_pairs=failed_pairs_this_candle)
                    except Exception as e:
                        analysis_elapsed = time.time() - analysis_start
                        log_msg(f"[yellow]⚠️ Erro na análise ({analysis_elapsed:.1f}s): {str(e)[:50]}[/yellow]")
                        cached_signal = None
                    
                    analysis_elapsed = time.time() - analysis_start
                    if cached_signal:
                        log_msg(f"[cyan]📊 SINAL: {cached_signal['pair']} {cached_signal['signal']} ({analysis_elapsed:.1f}s)[/cyan]")
                        log_msg(f"[yellow]📋 {escape(str(cached_signal.get('desc', '')))}[/yellow]")
                    elif analysis_elapsed > 20:
                        log_msg(f"[yellow]⏱️ Análise demorou {analysis_elapsed:.1f}s - pode haver gargalo[/yellow]")

                # ARMAR no último 2s e EXECUTAR no segundo 59 (1s antes da virada).
                # Motivo: Antecipar a virada para pegar a abertura exata.
                arm_window = 2.0
                open_window = 5.0 # Janela permissiva para delay

                if cached_signal and (0 < seconds_left <= arm_window):
                    worker_status = "⏱️ SINAL ARMADO! Aguardando ponto de disparo (59s)..."

                    # Espera server-side até segundo 59 (1s antes do fim)
                    target_turn = candle_end - 1
                    while True:
                        try:
                            now_ts = api.get_server_timestamp()
                        except Exception:
                            now_ts = 0
                        if isinstance(now_ts, (int, float)) and now_ts >= target_turn:
                            break
                        time.sleep(0.05)

                    # Confirmar que estamos dentro da janela inicial da nova vela
                    try:
                        now_ts = api.get_server_timestamp()
                    except Exception:
                        now_ts = 0

                    if not isinstance(now_ts, (int, float)) or now_ts <= 0:
                        worker_status = "⚠️ Tempo inválido na virada. Abortando entrada."
                        cached_signal = None
                        time.sleep(0.5)
                        continue

                    new_elapsed = now_ts - target_turn
                    if not (0.0 <= new_elapsed <= open_window):
                        worker_status = f"⛔ Perdeu a virada ({new_elapsed:.2f}s). Abortando entrada."
                        cached_signal = None
                        time.sleep(0.5)
                        continue

                    worker_status = "⚡ EXECUTANDO (abertura da nova vela)!"
                    log_msg(f"[bold green]🚀 DISPARANDO: {cached_signal['pair']} {cached_signal['signal']}[/bold green]")
                    log_msg(f"[cyan]📋 MOTIVO: {escape(str(cached_signal.get('desc', '')))}[/cyan]")
                    
                    profit = smart_trader.execute_trade(cached_signal, cfg, log_msg)

                    # Se a ordem NÃO abriu (ex: ativo indisponível), não travar a vela inteira.
                    # Marca o par como falho nesta vela e tenta outro setup.
                    if not getattr(smart_trader, 'last_order_opened', False):
                        failed_pairs_this_candle.add(cached_signal.get('pair'))
                        cached_signal = None
                        worker_status = "⚠️ Ordem não abriu. Tentando outro ativo..."
                        time.sleep(0.5)
                        continue

                    # Ordem abriu: atualizar saldo e marcar a vela como operada.
                    current_profit += profit
                    cfg.balance = api.get_balance()
                    
                    last_candle_traded = current_candle
                    cached_signal = None
                    log_msg(f"[dim]Trade finalizado. Lucro: R${profit:.2f}[/dim]")
                    time.sleep(2)
                
                elif cached_signal:
                    worker_status = f"🎯 SINAL PRONTO! Disparando quando faltar 1s ({int(seconds_left)}s)"
                    time.sleep(0.5)
                
                else:
                    worker_status = f"📊 Buscando setup ({int(seconds_elapsed)}s)"
                    time.sleep(1)
                    
            except Exception as e:
                # Log full traceback for debugging
                tb = traceback.format_exc()
                log_msg(f"[yellow]Erro: {e}[/yellow]")
                log_msg(f"[dim]{tb[:500]}[/dim]")  # Mostrar traceback no dashboard
                time.sleep(2)

    # Start Worker
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    
    # UI Loop - Otimizado para evitar flickering
    try:
        # screen=True ajuda a manter a interface fixa e evita 'rolagem' por prints externos
        with Live(
            dashboard.render(current_profit),
            auto_refresh=False,
            screen=True,
            redirect_stdout=True,
            redirect_stderr=True,
            console=dashboard.console,
        ) as live:
            last_render = time.time()
            last_render_error = 0.0
            while not stop_threads:
                now_render = time.time()
                # Limitar atualizações para no máximo 2/s (suave e responsivo)
                if now_render - last_render < 0.5:
                    time.sleep(0.05)
                    continue
                last_render = now_render

                # Snapshot de logs (evita race na renderização)
                dashboard.logs = list(bot_logs)

                # SEMPRE calcular tempo restante usando relógio LOCAL
                # Isso garante que o timer nunca trava em 00:00
                try:
                    duration = int(getattr(cfg, "timeframe", 1)) * 60
                    now_local = time.time()
                    # Timer de 0 a 60 (tempo decorrido, não restante)
                    elapsed = int(now_local % duration)
                    if elapsed < 0 or elapsed >= duration:
                        elapsed = 0
                    remaining = elapsed  # Mantém nome da variável para compatibilidade
                except Exception:
                    remaining = 0  # Fallback 0s

                # Atualizar display (auto_refresh=False exige refresh=True)
                try:
                    live.update(dashboard.render(current_profit, remaining, worker_status), refresh=True)
                except Exception as e:
                    # Se o render travar, continuar sem atualizar visual
                    now_err = time.time()
                    if now_err - last_render_error > 5:
                        last_render_error = now_err
                        try:
                            dashboard.log(f"[SYS] Render error: {e}")
                        except Exception:
                            pass
                
        console.print("\n[yellow]Sessão Encerrada. Pressione Enter para voltar...[/yellow]", style="on black")
        input()
        
    except KeyboardInterrupt:
        stop_threads = True
        console.print("\n[yellow]Parando...[/yellow]", style="on black")

def main():
    global stop_threads
    
    # 1. License Check - Sistema Simplificado
    if not verify_license():
        return
    
    # Set window title and icon AFTER console is ready
    set_console_title("Dark Black Bot - AI Powered")
    time.sleep(0.1)  # Small delay to ensure console is ready
    set_console_icon("darkblackbot.ico")
    
    # Evitar "faixas" cinzas: imprimir espaçador com fundo preto
    black_spacer(1)

    # Cabeçalho limpo (apenas espaço)
    # print_panel(console, header_panel("v3.5 • Smart Execution • AI Assisted")) -> REMOVIDO PARA LIMPEZA
    
    # Modern Professional Startup Banner
    startup_banner = """
[bold bright_white]DARK[/][bold white]BLACK[/] [bold bright_magenta]AI[/]
[dim]Professional Trading Intelligence[/dim]
"""
    
    # Banner com fundo 100% preto (sem áreas cinzas fora do texto)
    banner_text = Text.from_markup(startup_banner.strip("\n"), justify="center")
    console.print(Align.center(banner_text), style="on black")
    black_spacer(1)
    
    # Loading Animation
    with Progress(
        SpinnerColumn("dots", style="bright_cyan"),
        TextColumn("[bright_cyan]{task.description}"),
        transient=True
    ) as progress:
        task = progress.add_task("[bright_cyan]Inicializando sistema...", total=None)
        time.sleep(0.8)
    
    # 2. Config & Login
    cfg = Config()
    
    print_panel(console, title_panel("CONEXÃO IQ OPTION", border_style="bright_cyan"))

    # Verificar se existem credenciais salvas
    saved_creds = load_credentials()
    use_saved = False
    
    if saved_creds:
        masked_email = get_masked_email(saved_creds['email'])
        saved_acc_type = saved_creds.get('account_type', 'PRACTICE')
        acc_label = "REAL" if saved_acc_type == "REAL" else "TREINAMENTO"
        
        console.print(Padding("\n  [bright_green]🔐 Credenciais salvas encontradas![/bright_green]", (0,0), style="on black", expand=True))
        console.print(Padding(f"  [dim]Email:[/dim] [bright_white]{masked_email}[/bright_white]", (0,0), style="on black", expand=True))
        console.print(Padding(f"  [dim]Tipo:[/dim] [bright_cyan]{acc_label}[/bright_cyan]\n", (0,0), style="on black", expand=True))
        
        print_panel(
            console,
            menu_table(
                "USAR CREDENCIAIS SALVAS?",
                [
                    ("1", "SIM, ENTRAR AUTOMATICAMENTE", f"Usar {masked_email}"),
                    ("2", "NÃO, DIGITAR NOVAS", "Inserir outro email/senha"),
                    ("3", "APAGAR CREDENCIAIS SALVAS", "Limpar dados salvos"),
                ],
                border_style="bright_green",
            ),
        )
        
        cred_choice = IntPrompt.ask("  Opção", choices=["1", "2", "3"], default=1)
        
        if cred_choice == 1:
            # Usar credenciais salvas
            cfg.email = saved_creds['email']
            cfg.password = saved_creds['password']
            use_saved = True
            
            # Perguntar tipo de conta
            print_panel(
                console,
                menu_table(
                    "TIPO DE CONTA",
                    [
                        ("1", "TREINAMENTO (PRACTICE)", "Modo seguro para testar"),
                        ("2", "CONTA REAL", "Use com gestão e disciplina"),
                    ],
                    border_style="bright_magenta",
                ),
            )
            acc_choice = IntPrompt.ask("  Opção", choices=["1", "2"], default=1 if saved_acc_type == "PRACTICE" else 2)
            cfg.account_type = "REAL" if acc_choice == 2 else "PRACTICE"
            
        elif cred_choice == 3:
            # Apagar credenciais
            clear_credentials()
            console.print(Padding("  [yellow]🗑️ Credenciais removidas![/yellow]\n", (0,0), style="on black", expand=True))
            saved_creds = None
    
    # Se não usou credenciais salvas, pedir novas
    if not use_saved:
        print_panel(
            console,
            menu_table(
                "TIPO DE CONTA",
                [
                    ("1", "TREINAMENTO (PRACTICE)", "Modo seguro para testar configurações"),
                    ("2", "CONTA REAL", "Use apenas com gestão e disciplina"),
                ],
                border_style="bright_magenta",
            ),
        )
        
        acc_choice = IntPrompt.ask("  Opção", choices=["1", "2"], default=1)
        cfg.account_type = "REAL" if acc_choice == 2 else "PRACTICE"
        
        cfg.email = os.getenv("IQ_EMAIL") or Prompt.ask("  📧 [bright_white]Email[/bright_white]")
        cfg.password = os.getenv("IQ_PASSWORD") or Prompt.ask("  🔑 [bright_white]Senha[/bright_white]", password=True)

    api = None
    try:
        # Connection with progress bar
        black_spacer(1)
        with Progress(
            SpinnerColumn("dots", style="bright_cyan"),
            TextColumn("[bright_cyan]{task.description}"),
            transient=True
        ) as progress:
            task = progress.add_task("[bright_cyan]Conectando ao servidor IQ Option...", total=None)
            api = IQHandler(cfg)
            if not api.connect():
                console.print(Padding("[bold red]✗ Falha na autenticação![/bold red]", (0,0), style="on black", expand=True))
                return
            time.sleep(1.5)
            
        console.print(Padding("[bright_green]✓ Conectado com sucesso![/bright_green]", (0,0), style="on black", expand=True))
        
        # Salvar credenciais se não estava usando credenciais salvas
        if not use_saved:
            save_creds = Prompt.ask(
                "  💾 [bright_white]Salvar credenciais para próximo acesso?[/bright_white]",
                choices=["s", "n"],
                default="s"
            )
            if save_creds.lower() == "s":
                if save_credentials(cfg.email, cfg.password, cfg.account_type):
                    console.print(Padding("  [bright_green]✓ Credenciais salvas![/bright_green]", (0,0), style="on black", expand=True))
                else:
                    console.print(Padding("  [yellow]⚠ Não foi possível salvar[/yellow]", (0,0), style="on black", expand=True))
        else:
            # Atualizar tipo de conta se mudou
            if saved_creds and saved_creds.get('account_type') != cfg.account_type:
                save_credentials(cfg.email, cfg.password, cfg.account_type)
            
        cfg.balance = api.get_balance()
        
        # Show correct balance type
        acc_label = "REAL" if cfg.account_type == "REAL" else "TREINAMENTO"
        color = "bright_green" if cfg.account_type == "REAL" else "bright_cyan"
        
        console.print(Padding(f"[bright_white]  💰 Saldo ({acc_label}):[/bright_white] [{color}]R$ {cfg.balance:.2f}[/{color}]", (0,0), style="on black", expand=True))
        black_spacer(1)
        
        # 3. IA Setup
        ai_analyzer = None
        print_panel(console, title_panel("INTEGRAÇÃO COM IA", "Validação inteligente de entradas", border_style="bright_cyan"))
        black_spacer(1)
        console.print(Padding("  [dim]Validação inteligente de entradas com contexto gráfico.[/dim]", (0,0), style="on black", expand=True))

        # 1) Se ainda não configurou, oferecer wizard de 3 chaves (executa 1 vez)
        ai_keys_configured = os.getenv("AI_KEYS_CONFIGURED") in ("1", "true", "TRUE", "yes", "YES")

        # 2) Verificar quantas APIs existem
        groq_key = os.getenv("GROQ_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        apis_count = sum([1 if groq_key else 0, 1 if gemini_key else 0, 1 if openrouter_key else 0])

        # Caso não exista nenhuma chave, sempre permitir configurar (mesmo que flag esteja setada)
        if apis_count == 0 and Prompt.ask(
            "  🤖 [bright_white]Deseja configurar suas API Keys agora?[/bright_white]",
            choices=["s", "n"],
            default="s",
        ) == "s":
            _configure_three_ai_keys(console)
            groq_key = os.getenv("GROQ_API_KEY")
            gemini_key = os.getenv("GEMINI_API_KEY")
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            apis_count = sum([1 if groq_key else 0, 1 if gemini_key else 0, 1 if openrouter_key else 0])
            ai_keys_configured = os.getenv("AI_KEYS_CONFIGURED") in ("1", "true", "TRUE", "yes", "YES")

        # 3) Se tem 2+ APIs, usar Multi-Provider automaticamente
        if apis_count >= 2:
            console.print(Padding(f"[green]✅ {apis_count} APIs detectadas no .env - Multi-Provider ATIVO![/green]", (0,0), style="on black", expand=True))
            console.print(Padding("[dim]O bot usará Groq → Gemini → OpenRouter automaticamente[/dim]", (0,0), style="on black", expand=True))

            options = [
                ("1", "Usar Multi-Provider", f"Automático com {apis_count} APIs"),
                ("2", "Desativar IA", "Continuar sem validação de IA"),
                ("3", "Trocar API Keys", "Gerenciar Gemini/Groq/OpenRouter"),
            ]
            if ai_keys_configured:
                options.append(("4", "Reconfigurar 3 API Keys", "Refazer o processo (substituir chaves)"))

            print_panel(
                console,
                menu_table(
                    "IA Multi-Provider",
                    options,
                    border_style="bright_magenta",
                ),
            )

            action_choices = ["1", "2", "3"] + (["4"] if ai_keys_configured else [])
            action = Prompt.ask("  🤖 [bright_white]Escolha[/bright_white]", choices=action_choices, default="1")

            if action == "3":
                _manage_multi_ai_keys(console)
                groq_key = os.getenv("GROQ_API_KEY")
                gemini_key = os.getenv("GEMINI_API_KEY")
                openrouter_key = os.getenv("OPENROUTER_API_KEY")
                apis_count = sum([1 if groq_key else 0, 1 if gemini_key else 0, 1 if openrouter_key else 0])

            if action == "4":
                _configure_three_ai_keys(console)
                groq_key = os.getenv("GROQ_API_KEY")
                gemini_key = os.getenv("GEMINI_API_KEY")
                openrouter_key = os.getenv("OPENROUTER_API_KEY")
                apis_count = sum([1 if groq_key else 0, 1 if gemini_key else 0, 1 if openrouter_key else 0])
                # manter fluxo: depois de reconfigurar, tentar usar IA se houver chaves

            if apis_count >= 2 and action != "2":
                current_key = groq_key or gemini_key or openrouter_key
                current_provider = "groq" if groq_key else ("gemini" if gemini_key else "openrouter")
                use_ai = "s"
            else:
                use_ai = "n"
                current_key = None
                current_provider = os.getenv("AI_PROVIDER", "openrouter")

            should_configure = False

        else:
            # Fallback: uma ou nenhuma API - comportamento antigo
            current_key = os.getenv("AI_API_KEY") or openrouter_key or groq_key or gemini_key
            current_provider = os.getenv("AI_PROVIDER", "openrouter")

            if not os.getenv("AI_API_KEY"):
                if groq_key:
                    current_provider = "groq"
                elif gemini_key:
                    current_provider = "gemini"

            should_configure = False
            use_ai = "n"

            if current_key:
                display_prov = current_provider.upper() if current_provider else "IA"
                console.print(Padding(f"[dim]Configuração detectada: {display_prov}[/dim]", (0,0), style="on black", expand=True))

                options = [
                    ("1", f"Usar {display_prov}", "Manter a chave atual"),
                    ("2", "Configurar novo (1 chave)", "Inserir uma nova API Key"),
                    ("3", "Desativar", "Continuar sem validação de IA"),
                ]
                if ai_keys_configured:
                    options.append(("4", "Reconfigurar 3 API Keys", "Refazer o processo (substituir chaves)"))

                print_panel(
                    console,
                    menu_table(
                        "IA • Opções",
                        options,
                        border_style="bright_magenta",
                    ),
                )

                action_choices = ["1", "2", "3"] + (["4"] if ai_keys_configured else [])
                action = Prompt.ask(
                    "  🤖 [bright_white]Escolha uma opção[/bright_white]",
                    choices=action_choices,
                    default="1",
                )

                if action == "4":
                    _configure_three_ai_keys(console)
                    groq_key = os.getenv("GROQ_API_KEY")
                    gemini_key = os.getenv("GEMINI_API_KEY")
                    openrouter_key = os.getenv("OPENROUTER_API_KEY")
                    apis_count = sum([1 if groq_key else 0, 1 if gemini_key else 0, 1 if openrouter_key else 0])
                    if apis_count >= 2:
                        current_key = groq_key or gemini_key or openrouter_key
                        current_provider = "groq" if groq_key else ("gemini" if gemini_key else "openrouter")
                        use_ai = "s"
                    else:
                        current_key = os.getenv("AI_API_KEY") or openrouter_key or groq_key or gemini_key
                        if current_key:
                            use_ai = "s"
                    should_configure = False
                elif action == "2":
                    should_configure = True
                elif action == "1":
                    use_ai = "s"
                else:
                    use_ai = "n"
            else:
                console.print(Padding("[yellow]Nenhuma chave de IA detectada.[/yellow]", (0,0), style="on black", expand=True))
                if not ai_keys_configured:
                    if Prompt.ask("  🤖 [bright_white]Deseja configurar suas 3 API Keys?[/bright_white]", choices=["s", "n"], default="s") == "s":
                        _configure_three_ai_keys(console)
                        groq_key = os.getenv("GROQ_API_KEY")
                        gemini_key = os.getenv("GEMINI_API_KEY")
                        openrouter_key = os.getenv("OPENROUTER_API_KEY")
                        apis_count = sum([1 if groq_key else 0, 1 if gemini_key else 0, 1 if openrouter_key else 0])
                        if apis_count >= 2:
                            current_key = groq_key or gemini_key or openrouter_key
                            current_provider = "groq" if groq_key else ("gemini" if gemini_key else "openrouter")
                            use_ai = "s"
                        elif os.getenv("AI_API_KEY") or openrouter_key or groq_key or gemini_key:
                            current_key = os.getenv("AI_API_KEY") or openrouter_key or groq_key or gemini_key
                            current_provider = os.getenv("AI_PROVIDER", "openrouter")
                            use_ai = "s"
                else:
                    if Prompt.ask("  🤖 [bright_white]Deseja configurar a IA agora?[/bright_white]", choices=["s", "n"], default="s") == "s":
                        should_configure = True

        # SETUP WIZARD
        if should_configure:
            black_spacer(1)
            black_spacer(1)
            print_panel(
                console,
                menu_table(
                    "Escolha o Provedor",
                    [
                        ("1", "OpenRouter", "Padrão • Llama 3.3"),
                        ("2", "Groq", "Ultra rápido • Llama 3"),
                        ("3", "Gemini", "Google • Gemini Flash"),
                    ],
                    border_style="bright_cyan",
                ),
            )
            
            p_map = {"1": "openrouter", "2": "groq", "3": "gemini"}
            choice = Prompt.ask("Opção", choices=["1", "2", "3"], default="1")
            current_provider = p_map[choice]
            
            while True:
                black_spacer(1)
                console.print(Padding(f"[bold]Cole sua API Key do {current_provider.upper()}:[/bold]", (0,0), style="on black", expand=True))
                console.print(Padding("[dim](Clique com botão direito para colar | ENTER para cancelar)[/dim]", (0,0), style="on black", expand=True))
                input_key = Prompt.ask("API Key", password=True)
                
                if not input_key:
                    should_configure = False
                    use_ai = "n"
                    break
                    
                input_key = input_key.strip()
                
                input_key = input_key.strip()
                
                console.print(Padding("\n[dim]Validando chave... aguarde[/dim]", (0,0), style="on black", expand=True))
                try:
                    # Validar chave antes de salvar (direto no provedor)
                    is_valid, msg = _validate_ai_key(current_provider, input_key)
                    
                    if is_valid:
                        current_key = input_key
                        # Salvar no arquivo .env
                        try:
                            _write_env_file({
                                "AI_PROVIDER": current_provider,
                                "AI_API_KEY": current_key,
                                "AI_KEYS_CONFIGURED": os.getenv("AI_KEYS_CONFIGURED") or "1",
                            })
                            os.environ["AI_PROVIDER"] = current_provider
                            os.environ["AI_API_KEY"] = current_key
                            console.print(Padding(f"[green]✓ Chave válida ({msg})! Configuração salva.[/green]\n", (0,0), style="on black", expand=True))
                            use_ai = "s"
                            break
                        except Exception:
                            console.print(Padding("[red]Erro ao salvar .env (usando apenas nesta sessão)[/red]", (0,0), style="on black", expand=True))
                            use_ai = "s"
                            break
                    else:
                        console.print(Padding(f"[bold red]❌ CHAVE INVÁLIDA: {msg}[/bold red]", (0,0), style="on black", expand=True))
                        if Prompt.ask("Deseja tentar novamente?", choices=["s", "n"], default="s") == "n":
                            should_configure = False
                            use_ai = "n"
                            break
                except Exception as e:
                    console.print(Padding(f"[red]Erro na validação: {e}[/red]", (0,0), style="on black", expand=True))
                    if Prompt.ask("Deseja tentar novamente?", choices=["s", "n"], default="s") == "n":
                        use_ai = "n"
                        break

        if use_ai == "s" and current_key:
            try:
                with Progress(
                    SpinnerColumn("dots", style="bright_magenta"),
                    TextColumn("[bright_magenta]{task.description}"),
                    transient=True
                ) as progress:
                    task = progress.add_task(f"[bright_magenta]Conectando ao {current_provider.upper()}...", total=None)
                    ai_analyzer = AIAnalyzer(current_key, provider=current_provider)
                    time.sleep(1.5)
                
                console.print(Padding("[bright_green]✓ IA inicializada com sucesso![/bright_green]", (0,0), style="on black", expand=True))
                console.print(Padding(f"  [dim]Modelo: {ai_analyzer.model} | Status: Online[/dim]", (0,0), style="on black", expand=True))
            except Exception as e:
                console.print(Padding(f"\n[red]Erro ao conectar IA: {e}[/red]\n", (0,0), style="on black", expand=True))
                ai_analyzer = None
                console.print(Padding(f"[bright_red]  ✗ Falha ao inicializar IA: {e}[/bright_red]", (0,0), style="on black", expand=True))
                console.print(Padding("[bright_cyan]  ⚠️  Continuando sem validação de IA...[/bright_cyan]\n", (0,0), style="on black", expand=True))
        else:
            console.print(Padding("[dim]IA desativada para esta sessão.[/dim]\n", (0,0), style="on black", expand=True))

        # === MENU LOOP ===
        while True:
            print_panel(console, title_panel("MENU PRINCIPAL", border_style="white"))

            print_panel(
                console,
                menu_table(
                    "Escolha uma Ação",
                    [
                        ("1", "Iniciar Operações (Live Trading)", "Operar em tempo real (OTC)"),
                        ("2", "Simulador (Backtest)", "Testar estratégias com dados históricos"),
                        ("3", "Sair", "Encerrar com segurança"),
                    ],
                    border_style="bright_cyan",
                ),
            )
            
            mode = IntPrompt.ask("Opção", choices=["1", "2", "3"], default=1)
            
            if mode == 3:
                break
            
            if mode == 1:  # LIVE TRADING
                from rich.table import Table

                strategies_table = Table(box=box.DOUBLE, expand=True, show_lines=True)
                strategies_table.style = "on black"
                strategies_table.add_column("#", justify="right", style="dim", width=4)
                strategies_table.add_column("Estratégia", style="bold white")
                strategies_table.add_column("Perfil", style="bright_cyan", width=16)
                strategies_table.add_column("Resumo", style="dim")

                strategies_table.add_row(
                    "1",
                    "🎯 FERREIRA TRADER",
                    "CONSERVADOR",
                    "Tendência + canais | WR: 65-70% | Sinais: Médio | Risco: ●●○○○",
                )
                strategies_table.add_row(
                    "2",
                    "🔄 PRICE ACTION REVERSAL",
                    "CONSERVADOR",
                    "Reversão em liquidez/SR | WR: 68-72% | Sinais: Baixo | Risco: ●○○○○",
                )
                strategies_table.add_row(
                    "3",
                    "📊 LÓGICA DO PREÇO",
                    "MODERADO",
                    "Candlestick | WR: 62-68% | Sinais: Alto | Risco: ●●●○○",
                )
                strategies_table.add_row(
                    "4",
                    "⚡ ANA TAVARES RETRACTION",
                    "MODERADO",
                    "Tendência + retração | WR: 65-70% | Sinais: Médio | Risco: ●●●○○",
                )
                strategies_table.add_row(
                    "5",
                    "🛡️ CONSERVADOR HIGH PRECISION",
                    "MODERADO",
                    "Ultra seletivo | WR: 75-80% | Sinais: Muito baixo | Risco: ●○○○○",
                )
                strategies_table.add_row(
                    "6",
                    "🧨 ALAVANCAGEM LTA/LTB",
                    "AGRESSIVO",
                    "Tendência + S/R | WR: 60-68% | Sinais: Alto | Risco: ●●●●○",
                )
                strategies_table.add_row(
                    "7",
                    "🎯 ALAVANCAGEMSIMBOL SR",
                    "AGRESSIVO",
                    "S/R Extremo | WR: 62-70% | Sinais: Médio | Risco: ●●●●○",
                )
                strategies_table.add_row(
                    "8",
                    "⚡ PRICE ACTION DINÂMICO",
                    "AVANÇADO",
                    "Fluxo + Pavio + Simetria + MACD | WR: 70-75% | Risco: ●●●○○",
                )
                strategies_table.add_row(
                    "9",
                    "🔥 SNR ADVANCED",
                    "AVANÇADO",
                    "Rompimento Falso + Exaustão | WR: 72-78% | Risco: ●●○○○",
                )
                strategies_table.add_row(
                    "10",
                    "📈 MÉDIAS MÓVEIS",
                    "MODERADO",
                    "EMA5 x SMA20 + Pullback | WR: 68-73% | Risco: ●●●○○",
                )
                strategies_table.add_row(
                    "11",
                    "🎖️ PRIMEIRO REGISTRO V2",
                    "AVANÇADO",
                    "Defesa 1R + Vela Força | WR: 80-90% | Risco: ●○○○○",
                )
                strategies_table.add_row(
                    "12",
                    "🧠 TRADER MACHADO",
                    "EXPERT",
                    "Lotes + Simetria + Lógica Preço | WR: 85-90% | Risco: ●○○○○",
                )
                strategies_table.add_row(
                    "13",
                    "💎 AI GOD MODE (12-in-1)",
                    "GOD MODE",
                    "Arbitragem de todas as 12 estratégias via IA | WR: 90%+ | Risco: ●○○○○",
                )

                print_panel(console, title_panel("CENTRAL DE ESTRATÉGIAS", "Escolha seu perfil", border_style="bright_cyan"))

                strat_content = Group(
                    Text("Conservador • Moderado • Agressivo", style="dim"),
                    strategies_table,
                )
                print_panel(console, section("Estratégias Disponíveis", strat_content, border_style="bright_cyan"))
                
                sc = IntPrompt.ask("[bright_white]Selecione a Estratégia (1-13)[/bright_white]", choices=["1","2","3","4","5","6","7","8","9","10","11","12","13"])
                
                # Warning Risk
                if sc == 6:
                    risk_rows = [
                        ("Stakes", "[bold bright_magenta]Progressivos[/] (2% → 5% → 10% → 20%)"),
                        ("Gestão", "[bold]Agressiva[/] (até 20% da banca em 1 trade)"),
                        ("Risco", "[bold bright_red]Ruína elevada[/] em sequência de perdas"),
                        ("Ideal", "[dim]Traders experientes • Conta teste • Capital de risco[/]"),
                    ]
                    print_panel(console, info_kv(
                        "⚠️ Aviso de Risco Elevado",
                        risk_rows,
                        border_style="bright_red",
                    ))
                    if IntPrompt.ask("Aceitar risco? [1=Sim, 2=Não]", choices=["1", "2"], default=2) == 2:
                        console.print("[green]Decisão prudente! Retornando ao menu...[/green]", style="on black")
                        continue
                
                
                # Estratégia 6: escolher perfil de filtros/sinais
                if sc == 6:
                    print_panel(console, title_panel("ESTRATÉGIA 6 • MODO DE OPERAÇÃO", border_style="bright_red"))

                    print_panel(
                        console,
                        menu_table(
                            "Modo de Operação",
                            [
                                ("1", "Normal (Seletivo)", "Mais filtros • Menos sinais"),
                                ("2", "Flexível (Mais sinais)", "Menos filtros • Mais oportunidades"),
                                ("3", "Pitbull Bravo (Ultra agressivo)", "Máximo volume • Alto risco"),
                                ("4", "⚫ BLACK FLEX - LTA/LTB", "🎯 Apenas tendência + S/R | Meta 1h | Ultra Agressivo"),
                            ],
                            border_style="bright_red",
                        ),
                    )
                    mode_choice = IntPrompt.ask("Opção", choices=["1", "2", "3", "4"], default=1)
                    
                    if mode_choice == 4:
                        cfg.alavancagem_mode = "BLACK"
                    elif mode_choice == 3:
                        cfg.alavancagem_mode = "PITBULL"
                    elif mode_choice == 2:
                        cfg.alavancagem_mode = "FLEX"
                    else:
                        cfg.alavancagem_mode = "NORMAL"

                    strategy = AlavancagemStrategy(api, ai_analyzer, mode=cfg.alavancagem_mode)
                    strategy.name = f"{strategy.name} ({cfg.alavancagem_mode})"
                else:
                    strategy = get_strategy(sc, api, ai_analyzer)
                print_panel(console, title_panel("RESUMO DA SELEÇÃO", border_style="white"))
                summary_rows = [("Estratégia", f"[cyan]{strategy.name}[/cyan]")]
                if sc == 6:
                    summary_rows.append(("Modo", f"{getattr(cfg, 'alavancagem_mode', '—')}"))
                print_panel(console, info_kv("Seleção", summary_rows, border_style="bright_cyan"))
                
                pairs = select_pairs(api)
                
                # Parametros
                print_panel(console, title_panel("CONFIGURAÇÃO DE PARÂMETROS", border_style="bright_magenta"))
                console.print(Padding("[dim]  Defina entrada, timeframe e gerenciamento.[/dim]", (0,0), style="on black", expand=True))
                
                console.print("\n[bold]1. Valor da Entrada Inicial[/bold]", style="on black")
                console.print(Padding("   [dim]Valor investido no primeiro trade (R$)[/dim]", (0,0), style="on black", expand=True))
                cfg.amount = FloatPrompt.ask("   Valor", default=10.0)

                console.print("\n[bold white]1. TIPO DE OPÇÃO[/]", style="on black") # Subtitulo simples
                
                op_menu = Group(
                    Text("  [1] ⚡ Binárias (Expiração fixa)"),
                    Text("  [2] 📈 Digitais (Payout variável)"),
                    Text("  [3] 🤖 Melhor Payout (Auto)")
                )
                console.print(Padding(op_menu, (0,0), style="on black", expand=True))
                op_type = IntPrompt.ask("   Opção", choices=["1", "2", "3"], default=3)
                
                if op_type == 1:
                    cfg.option_type = "BINARY"
                elif op_type == 2:
                    cfg.option_type = "DIGITAL"
                else:
                    cfg.option_type = "BEST"
                
                console.print("\n[bold]2. Timeframe (Período de Análise)[/bold]", style="on black")
                console.print("   [dim]1 = M1 (1 min) | 5 = M5 (5 min) | 15 = M15 (15 min) | 30 = M30 (30 min)[/dim]", style="on black")
                console.print("   [bright_green]✨ Recomendado: M5 (melhor relação sinal/ruído)[/bright_green]", style="on black")
                
                while True:
                    cfg.timeframe = IntPrompt.ask("   Timeframe", default=5)
                    
                    # AVISO CRÍTICO PARA M1
                    if cfg.timeframe == 1:
                        warn_rows = [
                            ("Ruído", "[dim]Movimentos aleatórios e entradas falsas[/]"),
                            ("Latência", "[dim]Spread e atraso impactam mais o resultado[/]"),
                            ("Recomendado", "[bold bright_cyan]M5[/] • M15 • M30"),
                            ("Nota", "[bold bright_red]M1 é por sua conta e risco[/]"),
                        ]
                        print_panel(console, info_kv(
                            "⚠️ Aviso Importante (M1)",
                            warn_rows,
                            border_style="bright_magenta",
                        ))
                        
                        escolha = IntPrompt.ask(
                            "[bold]Deseja continuar mesmo assim?[/bold]\n   [1] Sim, aceito os riscos do M1\n   [2] Não, quero escolher outro timeframe",
                            choices=["1", "2"],
                            default=2
                        )
                        
                        if escolha == 2:
                            console.print("\n[green]✓ Decisão sábia! Escolha um timeframe mais adequado:[/green]\n", style="on black")
                            continue  # Volta para escolher outro timeframe
                        else:
                            console.print("\n[yellow]⚠️  Você escolheu prosseguir com M1. Boa sorte![/yellow]", style="on black")
                            console.print("[dim]Lembre-se: Discipline > Emoção | Stop Loss é seu amigo[/dim]\n", style="on black")
                            break
                    else:
                        # Timeframe válido (M5, M15, M30, etc)
                        break

                console.print("\n[bold]2.1 OTC: Restringir Timeframe (Opcional)[/bold]", style="on black")
                console.print("   [dim]1. Ativado: o robô executa OTC apenas em M1/M5 para máxima compatibilidade.[/dim]", style="on black")
                console.print("   [dim]2. Desativado: respeita M1/M5/M15/M30 e tenta fallback só se a corretora rejeitar.[/dim]", style="on black")
                otc_tf_mode = IntPrompt.ask("   Forçar OTC para M1/M5?", choices=["1", "2"], default=2)
                cfg.force_otc_m1m5 = (otc_tf_mode == 1)

                if cfg.force_otc_m1m5 and cfg.timeframe not in (1, 5):
                    console.print(
                        f"[yellow]⚠️ Forçando OTC para M1/M5: ajustando M{cfg.timeframe} → M5[/yellow]",
                        style="on black",
                    )
                    cfg.timeframe = 5
                
                console.print("\n[bold]3. Meta de Lucro Diária[/bold]", style="on black")
                console.print("   [dim]O robô para automaticamente ao atingir este valor (R$)[/dim]", style="on black")
                cfg.profit_goal = FloatPrompt.ask("   Meta", default=100.0)
                
                console.print("\n[bold]4. Stop Loss (Limite de Perda)[/bold]", style="on black")
                console.print("   [dim]O robô para automaticamente ao atingir este prejuízo (R$)[/dim]", style="on black")
                cfg.stop_loss = FloatPrompt.ask("   Stop Loss", default=50.0)
                
                console.print("\n[bold]5. Níveis de Martingale (Gales)[/bold]", style="on black")
                console.print("   [dim]Quantas tentativas de recuperação após perda[/dim]", style="on black")
                console.print("   [dim]Cada gale multiplica a entrada por 2.2x[/dim]", style="on black")
                console.print("   [bright_magenta]⚠️  Mais gales = maior risco[/bright_magenta]", style="on black")
                cfg.martingale_levels = IntPrompt.ask("   Gales", default=2)
                
                cfg.strategy_name = strategy.name
                cfg.stop_win = cfg.profit_goal  # Auto-sync
                
                print_panel(console, title_panel("CONFIGURAÇÃO FINALIZADA", border_style="bright_green"))
                
                final_config = Group(
                    Text(f"  ✓ Estratégia: {cfg.strategy_name}", style="bright_green"),
                    Text(f"  ✓ Timeframe: M{cfg.timeframe}", style="bright_green"),
                    Text(f"  ✓ Tipo: {cfg.option_type}", style="bright_green"),
                    Text(f"  ✓ OTC: {'M1/M5 (forçado)' if getattr(cfg, 'force_otc_m1m5', False) else 'Livre'}", style="bright_green")
                )
                console.print(Padding(final_config, (0,0), style="on black", expand=True))
                console.rule(style="bright_green on black")
                black_spacer(1)
                
                # Memory Link
                mem = TradingMemory()
                if ai_analyzer:
                    ai_analyzer.set_memory(mem)
                
                # === VALIDAÇÃO FINAL DE PARES (Para evitar congelamentos) ===
                console.print(Padding(f"\n[dim]Validando compatibilidade de Timeframe (M{cfg.timeframe})...[/dim]", (0,0), style="on black", expand=True))
                valid_pairs = []
                with Progress(
                    SpinnerColumn("dots", style="bright_yellow"),
                    TextColumn("[bright_yellow]{task.description}"),
                    transient=True,
                    console=console
                ) as progress:
                    task = progress.add_task("[bright_yellow]Verificando ativos...", total=len(pairs))
                    
                    for p in pairs:
                        progress.update(task, description=f"[bright_yellow]Verificando {p}...")
                        # Valida apenas o timeframe escolhido (timeout 12s) — remove e segue se travar
                        if api.validate_pair_timeframes(p, [cfg.timeframe], timeout_s=12.0):
                            valid_pairs.append(p)
                            progress.console.print(f"  [green]✓ {p} OK[/green]", style="on black")
                        else:
                            progress.console.print(f"  [red]✗ {p} removido (Sem resposta/M{cfg.timeframe})[/red]", style="on black")
                        progress.advance(task)
                        
                if not valid_pairs:
                    console.print(f"\n[bold red]❌ Nenhum dos pares selecionados suporta M{cfg.timeframe}![/bold red]", style="on black")
                    console.print("[yellow]Pressione ENTER para retornar ao menu...[/yellow]", style="on black")
                    input()
                    continue
                
                if len(valid_pairs) < len(pairs):
                    console.print(f"\n[yellow]⚠️ Lista ajustada: {len(pairs)} -> {len(valid_pairs)} ativos válidos[/yellow]", style="on black")
                    time.sleep(2)
                
                run_trading_session(api, strategy, valid_pairs, cfg, mem, ai_analyzer)
                
            elif mode == 2: # BACKTEST
                pairs = select_pairs(api)
                tf = IntPrompt.ask("Timeframe", default=1)

                print_panel(console, menu_table(
                    "Backtest",
                    [("", "Rodando simulação", "Testando estratégias em dados históricos")],
                    border_style="bright_magenta",
                ))
                # Test all strategies
                strats = [
                    FerreiraStrategy(api), PriceActionStrategy(api), 
                    LogicaPrecoStrategy(api), AnaTavaresStrategy(api),
                    ConservadorStrategy(api), AlavancagemStrategy(api),
                    AlavancagemSRStrategy(api)
                ]
                bt = Backtester(api)
                res = bt.run_backtest(pairs, strats, tf, 100)
                bt.display_results(res, strats)
                console.print("\n[dim]Pressione ENTER para voltar...[/dim]", style="on black")
                input()
    finally:
        # Graceful shutdown da conexão com a corretora
        try:
            if 'api' in locals() and api:
                api.close()
                console.print("\n[dim]Conexão encerrada com segurança.[/dim]", style="on black")
        except Exception:
            pass

if __name__ == "__main__":
    main()
