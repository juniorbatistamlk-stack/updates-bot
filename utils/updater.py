"""
utils/updater.py - SISTEMA DE AUTO-UPDATE
Verifica e instala atualizações automaticamente
"""
import requests
import os
import shutil
import zipfile

# URL DO SEU REPOSITÓRIO DE RELEASES
UPDATE_SERVER = "https://raw.githubusercontent.com/juniorbatistamlk-stack/updates-bot/main/version.json"
DOWNLOAD_URL_BASE = "https://github.com/juniorbatistamlk-stack/updates-bot/raw/main/"

CURRENT_VERSION = "1.0.0"  # Versão atual do bot
VERSION_FILE = ".version"

def get_current_version():
    """Retorna versão atual instalada"""
    return CURRENT_VERSION

def check_for_updates(timeout=5):
    """
    Verifica se há atualizações disponíveis
    
    Returns:
        tuple: (has_update, new_version, changelog, download_url)
    """
    try:
        response = requests.get(UPDATE_SERVER, timeout=timeout)
        if response.status_code != 200:
            return False, None, None, None
        
        data = response.json()
        latest_version = data.get("version")
        changelog = data.get("changelog", "Melhorias e correções")
        download_url = data.get("download_url")
        
        # Comparar versões (simples)
        if latest_version != CURRENT_VERSION:
            return True, latest_version, changelog, download_url
        
        return False, None, None, None
        
    except Exception as e:
        print(f"Erro ao verificar updates: {e}")
        return False, None, None, None

def download_update(download_url, save_path="update.zip"):
    """
    Baixa arquivo de atualização
    
    Returns:
        bool: sucesso
    """
    try:
        print(f"Baixando atualização de {download_url}...")
        response = requests.get(download_url, stream=True, timeout=30)
        
        if response.status_code != 200:
            print("Erro ao baixar atualização!")
            return False
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\\rProgresso: {percent:.1f}%", end="", flush=True)
        
        print("\\n✅ Download concluído!")
        return True
        
    except Exception as e:
        print(f"Erro ao baixar: {e}")
        return False

def install_update(zip_path="update.zip", backup_dir="backup"):
    """
    Instala atualização (descompacta e substitui arquivos)
    
    Returns:
        bool: sucesso
    """
    try:
        # Fazer backup
        print("Criando backup...")
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        
        os.makedirs(backup_dir, exist_ok=True)
        
        # Backup de arquivos críticos
        for file in ["main.py", "config.py", "utils/", "strategies/"]:
            if os.path.exists(file):
                if os.path.isfile(file):
                    shutil.copy2(file, os.path.join(backup_dir, os.path.basename(file)))
                else:
                    shutil.copytree(file, os.path.join(backup_dir, os.path.basename(file)), dirs_exist_ok=True)
        
        print("Instalando atualização...")
        
        # Descompactar
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        
        # Remover zip
        os.remove(zip_path)
        
        print("✅ Atualização instalada com sucesso!")
        return True
        
    except Exception as e:
        print(f"Erro ao instalar: {e}")
        print("Restaurando backup...")
        
        # Restaurar do backup se der erro
        if os.path.exists(backup_dir):
            for item in os.listdir(backup_dir):
                src = os.path.join(backup_dir, item)
                dst = item
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                else:
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
        
        return False

def prompt_update(new_version, changelog):
    """
    Pergunta ao usuário se quer atualizar
    
    Returns:
        bool: aceita atualização
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm
    
    console = Console()
    
    console.print(Panel(
        f"[bold bright_cyan]🚀 NOVA VERSÃO DISPONÍVEL![/bold bright_cyan]\\n\\n"
        f"[white]Versão Atual:[/white] {CURRENT_VERSION}\\n"
        f"[green]Nova Versão:[/green] {new_version}\\n\\n"
        f"[bold]O que há de novo:[/bold]\\n"
        f"[dim]{changelog}[/dim]\\n\\n"
        f"[yellow]A atualização será instalada automaticamente.[/yellow]",
        border_style="bright_cyan"
    ))
    
    return Confirm.ask("Deseja atualizar agora?", default=True)

def check_and_update():
    """
    Função principal de verificação e instalação de updates
    
    Returns:
        bool: True se atualizou e precisa reiniciar
    """
    print("🔍 Verificando atualizações...")
    
    has_update, new_version, changelog, download_url = check_for_updates()
    
    if not has_update:
        print("✅ Você já está na versão mais recente!")
        return False
    
    if not download_url:
        print("⚠️ Atualização disponível mas URL de download não encontrada.")
        return False
    
    # Perguntar ao usuário
    if not prompt_update(new_version, changelog):
        print("⏭️ Atualização adiada.")
        return False
    
    # Baixar
    if not download_update(download_url):
        print("❌ Falha ao baixar atualização.")
        return False
    
    # Instalar
    if not install_update():
        print("❌ Falha ao instalar atualização.")
        return False
    
    print("\\n🎉 Atualização instalada! Por favor, reinicie o bot.")
    return True
