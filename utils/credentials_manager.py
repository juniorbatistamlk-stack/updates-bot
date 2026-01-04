"""
================================================================================
🔐 GERENCIADOR DE CREDENCIAIS
================================================================================
Salva e carrega credenciais do usuário de forma segura (com ofuscação básica)

IMPORTANTE: Este sistema usa ofuscação simples para não deixar a senha em texto
            puro no arquivo. Para produção real, considere usar keyring ou
            criptografia mais robusta.
================================================================================
"""

import json
import base64
from pathlib import Path
from typing import Optional, Dict


# Arquivo de configuração
CREDENTIALS_FILE = Path(__file__).parent.parent / "user_credentials.dat"


def _encode(text: str) -> str:
    """Ofusca o texto (não é criptografia forte, apenas evita texto puro)"""
    if not text:
        return ""
    # Ofuscação simples: base64 + inversão
    encoded = base64.b64encode(text.encode('utf-8')).decode('utf-8')
    return encoded[::-1]  # Inverte


def _decode(encoded: str) -> str:
    """Decodifica o texto ofuscado"""
    if not encoded:
        return ""
    try:
        # Desinverte + decodifica base64
        reversed_str = encoded[::-1]
        return base64.b64decode(reversed_str.encode('utf-8')).decode('utf-8')
    except Exception:
        return ""


def save_credentials(email: str, password: str, account_type: str = "PRACTICE") -> bool:
    """
    Salva as credenciais do usuário
    
    Args:
        email: Email da conta IQ Option
        password: Senha da conta
        account_type: Tipo de conta (PRACTICE ou REAL)
    
    Returns:
        True se salvou com sucesso
    """
    try:
        data = {
            "email": _encode(email),
            "password": _encode(password),
            "account_type": account_type,
            "saved_at": str(Path(__file__).stat().st_mtime) if Path(__file__).exists() else "0"
        }
        
        with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        return True
    except Exception as e:
        print(f"⚠️ Erro ao salvar credenciais: {e}")
        return False


def load_credentials() -> Optional[Dict[str, str]]:
    """
    Carrega as credenciais salvas
    
    Returns:
        Dict com 'email', 'password', 'account_type' ou None se não existir
    """
    try:
        if not CREDENTIALS_FILE.exists():
            return None
        
        with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        email = _decode(data.get("email", ""))
        password = _decode(data.get("password", ""))
        
        if not email or not password:
            return None
        
        return {
            "email": email,
            "password": password,
            "account_type": data.get("account_type", "PRACTICE")
        }
    except Exception:
        return None


def has_saved_credentials() -> bool:
    """Verifica se existem credenciais salvas"""
    return CREDENTIALS_FILE.exists() and load_credentials() is not None


def get_masked_email(email: str) -> str:
    """
    Retorna email parcialmente mascarado para exibição
    Ex: j***@gmail.com
    """
    if not email or "@" not in email:
        return "***"
    
    parts = email.split("@")
    user = parts[0]
    domain = parts[1]
    
    if len(user) <= 2:
        masked_user = user[0] + "***"
    else:
        masked_user = user[0] + "***" + user[-1]
    
    return f"{masked_user}@{domain}"


def clear_credentials() -> bool:
    """Remove as credenciais salvas"""
    try:
        if CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()
        return True
    except Exception:
        return False


# ==================== AI CREDENTIALS ====================

AI_CREDENTIALS_FILE = Path(__file__).parent.parent / "ai_credentials.dat"


def save_ai_credentials(provider: str, api_key: str) -> bool:
    """Salva credenciais da IA"""
    try:
        data = {
            "provider": provider,
            "api_key": _encode(api_key)
        }
        
        with open(AI_CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        return True
    except Exception:
        return False


def load_ai_credentials() -> Optional[Dict[str, str]]:
    """Carrega credenciais da IA"""
    try:
        if not AI_CREDENTIALS_FILE.exists():
            return None
        
        with open(AI_CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        api_key = _decode(data.get("api_key", ""))
        
        if not api_key:
            return None
        
        return {
            "provider": data.get("provider", "groq"),
            "api_key": api_key
        }
    except Exception:
        return None


def has_saved_ai_credentials() -> bool:
    """Verifica se existem credenciais de IA salvas"""
    return AI_CREDENTIALS_FILE.exists() and load_ai_credentials() is not None


def clear_ai_credentials() -> bool:
    """Remove credenciais de IA salvas"""
    try:
        if AI_CREDENTIALS_FILE.exists():
            AI_CREDENTIALS_FILE.unlink()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # Teste
    print("🔐 Teste do Gerenciador de Credenciais")
    print(f"Arquivo: {CREDENTIALS_FILE}")
    print(f"Credenciais salvas: {has_saved_credentials()}")
    
    if has_saved_credentials():
        creds = load_credentials()
        print(f"Email: {get_masked_email(creds['email'])}")
        print(f"Tipo: {creds['account_type']}")
