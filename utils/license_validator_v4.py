"""utils/license_validator_v4.py - Validador de Licenças (Cliente)"""

import json
import hashlib
import platform
import subprocess
import os
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path
try:
    from config_license import LICENSE_URL, SUPPORT_CONTACT, WARNING_DAYS, SECURITY_SALT, CLIENT_LICENSE_FILE
except ImportError:
    # Fallback caso config_license não esteja no path
    LICENSE_URL = "https://raw.githubusercontent.com/juniorbatistamlk-stack/DarkBlackBot/main/license_database.json"
    SUPPORT_CONTACT = "https://t.me/magoTrader_01"
    WARNING_DAYS = 3
    SECURITY_SALT = "black_bot_v4_secure_salt_2026"
    CLIENT_LICENSE_FILE = "license.key"

def get_hwid():
    """Gera ID único do hardware (Windows/Linux/Mac)."""
    try:
        if platform.system() == "Windows":
            cmd = "wmic csproduct get uuid"
            uuid = subprocess.check_output(cmd).decode(errors="ignore").split("\n")[1].strip()
            if uuid:
                return hashlib.sha256((uuid + SECURITY_SALT).encode()).hexdigest()[:32]
    except Exception:
        pass
    
    # Fallback robusto
    machine = platform.machine()
    node = platform.node()
    proc = platform.processor()
    system = platform.system()
    raw = f"{node}-{machine}-{proc}-{system}-{SECURITY_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def _normalize_key(key):
    return str(key).strip().upper().replace("-", "").replace(" ", "")

class LicenseValidator:
    def __init__(self):
        self.hwid = get_hwid()
        self.local_file = Path(CLIENT_LICENSE_FILE)
        self.support_link = SUPPORT_CONTACT

    def load_local_license(self):
        """Carrega licença salva localmente."""
        if not self.local_file.exists():
            return None
        try:
            data = json.loads(self.local_file.read_text(encoding="utf-8"))
            return data
        except Exception:
            return None

    def save_local_license(self, license_data):
        """Salva licença localmente."""
        try:
            # Adiciona metadados locais de segurança
            license_data["local_hwid"] = self.hwid
            license_data["install_date"] = datetime.now().isoformat()
            self.local_file.write_text(json.dumps(license_data, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def validate_online(self, key):
        """Valida a chave no banco de dados do GitHub."""
        try:
            print("⏳ Conectando ao servidor de licenças...")
            resp = requests.get(LICENSE_URL, timeout=10)
            if resp.status_code != 200:
                return False, "Erro de conexão com servidor (Github Offline?)."
            
            db = resp.json()
            norm_key = _normalize_key(key)
            
            # Buscar chave
            found_lic = None
            for lic in db.get("licenses", []):
                if _normalize_key(lic.get("key")) == norm_key:
                    found_lic = lic
                    break
            
            if not found_lic:
                return False, "Chave não encontrada ou inválida."
            
            # Verificar Status
            if str(found_lic.get("status")).lower() != "active":
                return False, "Esta licença foi bloqueada/revogada."
            
            # Verificar HWID (se já estiver vinculado)
            server_hwid = found_lic.get("activated_hwid")
            if server_hwid and server_hwid != self.hwid:
                return False, "Esta chave já está em uso em outro computador (1x user)."
            
            # Verificar Validade
            expiry_str = found_lic.get("expiry_date")
            if expiry_str:
                try:
                    expiry_dt = datetime.fromisoformat(expiry_str)
                    if datetime.now() > expiry_dt:
                        return False, "Licença expirada."
                except Exception:
                    pass # Data inválida ignora (assume vitalícia ou erro)

            return True, found_lic

        except Exception as e:
            return False, f"Erro ao validar online: {str(e)}"

    def check(self):
        """
        Fluxo principal de verificação ao iniciar o bot.
        Retorna: (True/False, Mensagem, DiasRestantes)
        """
        local_data = self.load_local_license()
        
        # 1. Se não tem licença local -> Pedir Ativação
        if not local_data:
            return self._activation_flow()
        
        # 2. Se tem licença local -> Validar Offline (Cache) e HWID
        saved_hwid = local_data.get("local_hwid") or local_data.get("activated_hwid")
        if saved_hwid and saved_hwid != self.hwid:
             print("\n🛑 ERRO DE HARDWARE ID")
             print("Esta licença pertence a outro computador.")
             return self._activation_flow() # Forçar re-ativação ou nova chave

        # 3. Verificar Validade Local
        expiry_str = local_data.get("expiry_date")
        remaining_days = 999
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str)
                delta = expiry_dt - datetime.now()
                remaining_days = delta.days
                
                if remaining_days < 0:
                     self._show_expired_message(local_data)
                     return False
            except:
                pass

        # 4. Avisos de Vencimento
        if remaining_days <= WARNING_DAYS:
            print("\n" + "═"*60)
            print(f"⚠️  AVISO: SUA LICENÇA VENCE EM {remaining_days} DIAS!")
            print(f"👉  Renove agora: {self.support_link}")
            print("═"*60 + "\n")
            time.sleep(3)
        
        return True

    def _activation_flow(self):
        """Solicita a chave ao usuário (apenas na primeira vez)."""
        print("\n" + "█"*60)
        print("🔐 DARK BLACK BOT PRO - ATIVAÇÃO ÚNICA")
        print("█"*60)
        print("⚠️  A chave será vinculada a este PC e não poderá ser usada em outro.")
        
        while True:
            key_input = input("\n🔑 Digite sua KEY de acesso: ").strip()
            if not key_input:
                continue
            
            # Validar Online
            ok, result = self.validate_online(key_input)
            
            if ok:
                # Sucesso! Salvar localmente
                # Injetar HWID atual no objeto salvo para travar neste PC
                result["activated_hwid"] = self.hwid 
                result["last_check"] = datetime.now().isoformat()
                
                if self.save_local_license(result):
                    print(f"\n✅ ATIVADO COM SUCESSO! Bem-vindo, {result.get('name')}.")
                    print(f"📅 Validade: {result.get('expiry_date') or 'Vitalício'}")
                    print("⚠️  AVISO: Esta key foi consumida e salva neste PC.")
                    time.sleep(2)
                    return True
                else:
                    print("❌ Erro ao salvar arquivo de licença local. Verifique permissões.")
                    return False
            else:
                print(f"❌ {result}")
                opt = input("Tentar novamente? (S/N): ").upper()
                if opt != 'S':
                    return False

    def _show_expired_message(self, data):
        print("\n" + "█"*60)
        print("🛑  ACESSO BLOQUEADO - LICENÇA EXPIRADA")
        print("█"*60)
        print(f"Opa, {data.get('name')}!")
        print("Seu acesso ao bot venceu.")
        print("\nPara continuar faturando muito no automatico,")
        print(f"chame o {self.support_link} para a renovação.")
        print("█"*60 + "\n")
        input("Pressione ENTER para sair...")

# Função helper para importação fácil
def validate_license():
    v = LicenseValidator()
    return v.check()

if __name__ == "__main__":
    # Teste isolado
    if validate_license():
        print("Bot iniciando...")
    else:
        print("Bot finalizado.")
