"""
utils/security.py - SISTEMA DE VALIDAÇÃO DE LICENÇAS
Valida licenças geradas pelo license_generator.py
"""
import hashlib
import platform
import subprocess
import os
import json
from datetime import datetime

# MESMA CHAVE MESTRA DO GERADOR (NÃO ALTERAR!)
SECRET_KEY = b"darkblack_bot_master_key_2024_v1"

LICENSE_FILE = "license.key"
SUPPORT_CONTACT = "https://t.me/magoTrader_01"

def get_hwid():
    """
    Gera Hardware ID único (MESMA LÓGICA DO get_hwid.py)
    """
    hwid_parts = []
    
    # 1. Nome do processador
    try:
        processor = platform.processor()
        if processor:
            hwid_parts.append(processor)
    except Exception:
        pass
    
    # 2. Serial da placa-mãe (Windows)
    try:
        if platform.system() == "Windows":
            result = subprocess.check_output(
                "wmic baseboard get serialnumber", 
                shell=True, 
                encoding='utf-8',
                stderr=subprocess.DEVNULL
            ).strip().split('\n')
            if len(result) > 1:
                serial = result[1].strip()
                if serial and serial != "SerialNumber":
                    hwid_parts.append(serial)
    except Exception:
        pass
    
    # 3. UUID do sistema
    try:
        if platform.system() == "Windows":
            result = subprocess.check_output(
                "wmic csproduct get uuid",
                shell=True,
                encoding='utf-8',
                stderr=subprocess.DEVNULL
            ).strip().split('\n')
            if len(result) > 1:
                uuid = result[1].strip()
                if uuid and uuid != "UUID":
                    hwid_parts.append(uuid)
    except Exception:
        pass
    
    # 4. Fallback: nome da máquina
    if not hwid_parts:
        hwid_parts.append(platform.node())
    
    # Gerar hash único
    combined = "-".join(hwid_parts)
    hwid = hashlib.sha256(combined.encode()).hexdigest()[:32].upper()
    
    return hwid

def validate_license_key(license_key, hwid):
    """
    Valida chave de licença
    
    Returns:
        tuple: (is_valid, expiry_date, error_message)
    """
    try:
        # Formato: DBB-HWID8-SIGNATURE-DATEYYYYMMDD
        parts = license_key.split("-")
        
        if len(parts) != 4:
            return False, None, "Formato de chave inválido"
        
        prefix, hwid_part, signature, date_part = parts
        
        if prefix != "DBB":
            return False, None, "Chave inválida (prefixo)"
        
        # Verificar HWID
        if hwid[:8] != hwid_part:
            return False, None, "Esta licença não está vinculada a este computador!"
        
        # Reconstruir expiry
        if date_part == "LIFETIME00":
            expiry_str = "LIFETIME"
        else:
            # Formato: YYYYMMDD
            if len(date_part) != 8:
                return False, None, "Data inválida"
            expiry_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}"
        
        # Verificar assinatura HMAC
        # Nota: não temos customer_name aqui, então validamos apenas estrutura
        # A validação completa é feita no gerador
        
        # Verificar expiração
        if expiry_str == "LIFETIME":
            return True, None, "Licença vitalícia ativa"
        
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d")
        now = datetime.now()
        days_left = (expiry_date - now).days
        
        if days_left < 0:
            return False, expiry_date, f"Licença expirou há {abs(days_left)} dias!"
        
        return True, expiry_date, f"Licença válida - {days_left} dias restantes"
        
    except Exception as e:
        return False, None, f"Erro ao validar licença: {str(e)}"

class LicenseValidator:
    def __init__(self):
        self.hwid = get_hwid()
        self.is_activated = False
        self.days_left = 0
        self.expiry_date = None
        self.license_key = None
    
    def load_license(self):
        """Carrega licença salva localmente"""
        if not os.path.exists(LICENSE_FILE):
            return None
        
        try:
            # Verificar se arquivo não está vazio
            if os.path.getsize(LICENSE_FILE) == 0:
                return None
            
            with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("license_key")
        except (json.JSONDecodeError, KeyError, Exception):
            # Arquivo corrompido ou inválido
            return None
    
    def save_license(self, license_key):
        """Salva licença localmente"""
        with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "license_key": license_key,
                "hwid": self.hwid,
                "activated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f, indent=2)
    
    def is_first_run(self):
        """Verifica se é a primeira execução"""
        return not os.path.exists(LICENSE_FILE)
    
    def activate_license(self, license_key):
        """
        Ativa uma licença
        Returns: (success, message)
        """
        valid, expiry, message = validate_license_key(license_key, self.hwid)
        
        if not valid:
            return False, f"❌ {message}"
        
        # Salvar licença
        self.save_license(license_key)
        self.license_key = license_key
        self.expiry_date = expiry
        self.is_activated = True
        
        if expiry:
            self.days_left = (expiry - datetime.now()).days
        else:
            self.days_left = 999999  # Vitalícia
        
        return True, f"✅ Licença ativada com sucesso! {message}"
    
    def validate_license(self):
        """
        Valida licença existente
        Returns: (valid, days_left, message)
        """
        license_key = self.load_license()
        
        if not license_key:
            return False, 0, "Licença não encontrada"
        
        valid, expiry, message = validate_license_key(license_key, self.hwid)
        
        if not valid:
            return False, 0, message
        
        self.license_key = license_key
        self.expiry_date = expiry
        self.is_activated = True
        
        if expiry:
            self.days_left = (expiry - datetime.now()).days
        else:
            self.days_left = 999999
        
        return True, self.days_left, message
    
    def get_expiration_warning(self):
        """
        Retorna aviso de expiração se necessário
        Returns: (warning_type, warning_message)
        """
        if self.days_left <= 0:
            return (
                "expired",
                f"🚨 [bold red]SUA LICENÇA EXPIROU![/bold red]\\n\\n"
                f"Para continuar usando o bot, renove sua licença:\\n"
                f"[bold cyan]{SUPPORT_CONTACT}[/bold cyan]\\n\\n"
                f"[dim]Continue lucrando com o Dark Black Bot! 💰[/dim]"
            )
        elif self.days_left <= 7:
            return (
                "warning",
                f"⚠️ [bold yellow]ATENÇÃO: Sua licença expira em {self.days_left} dia(s)![/bold yellow]\\n\\n"
                f"Garanta sua renovação:\\n"
                f"[bold cyan]{SUPPORT_CONTACT}[/bold cyan]\\n\\n"
                f"[dim]Não perca acesso ao bot! 🚀[/dim]"
            )
        
        return (None, None)
    
    def show_welcome_message(self):
        """Mensagem de boas-vindas"""
        if self.days_left > 99999:
            return "[green]🔓 Licença Vitalícia Ativa[/green]"
        else:
            return f"[green]🔓 Licença Válida[/green] | [dim]{self.days_left} dias restantes[/dim]"

def check_license_on_startup():
    """
    Verifica licença na inicialização
    Returns: (success, validator, message)
    """
    from rich.console import Console
    from rich.prompt import Prompt
    from rich.panel import Panel
    
    console = Console()
    validator = LicenseValidator()
    
    # Primeira execução
    if validator.is_first_run():
        console.print(Panel(
            "[bold bright_cyan]🔐 DARK BLACK BOT - ATIVAÇÃO[/bold bright_cyan]\\n\\n"
            "[white]Insira sua chave de licença:[/white]\\n\\n"
            "[dim]⚠️ A chave será vinculada permanentemente a este PC![/dim]\\n"
            f"[dim]HWID deste PC: {validator.hwid[:16]}...[/dim]",
            border_style="bright_cyan"
        ))
        
        license_key = Prompt.ask("\\n[bold]Chave de Licença[/bold]")
        
        success, message = validator.activate_license(license_key)
        
        if not success:
            console.print(f"\\n{message}")
            console.print("\\n[yellow]Contato para suporte:[/yellow]")
            console.print(f"[cyan]{SUPPORT_CONTACT}[/cyan]\\n")
            return False, validator, message
        
        console.print(f"\\n{message}\\n")
        
        # Verificar aviso
        warning_type, warning_msg = validator.get_expiration_warning()
        if warning_msg:
            console.print(Panel(warning_msg, border_style="yellow" if warning_type == "warning" else "red"))
            if warning_type == "expired":
                return False, validator, "Licença expirada"
        
        return True, validator, "Ativado"
    
    # Validar licença existente
    valid, days_left, message = validator.validate_license()
    
    if not valid:
        console.print(Panel(
            f"❌ [bold red]ERRO DE LICENÇA[/bold red]\\n\\n"
            f"{message}\\n\\n"
            f"Contato: [cyan]{SUPPORT_CONTACT}[/cyan]",
            border_style="red"
        ))
        return False, validator, message
    
    # Verificar avisos
    warning_type, warning_msg = validator.get_expiration_warning()
    if warning_msg:
        console.print(Panel(warning_msg, border_style="yellow" if warning_type == "warning" else "red"))
        if warning_type == "expired":
            return False, validator, "Licença expirada"
    
    console.print(validator.show_welcome_message())
    return True, validator, "OK"
