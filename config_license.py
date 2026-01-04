"""config_license.py - Configuração Centralizada do Sistema de Licenças v4"""

import os

# =============================================================================
# CONFIGURAÇÕES GERAIS
# =============================================================================

# URL do banco de dados no GitHub (Raw)
# ATENÇÃO: Substitua pelo seu usuário/repo correto se mudar
GITHUB_USER = "juniorbatistamlk-stack"
GITHUB_REPO = "DarkBlackBot-Admin" # Repositório PRIVADO (Onde fica a database)
LICENSE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/license_database.json"

# Arquivos Locais
LOCAL_LICENSE_DB = "license_database.json"       # Banco de dados completo (Admin/Server)
CLIENT_LICENSE_FILE = "license.key"              # Arquivo de licença do cliente (1x ativado)
ADMIN_GENERATOR_FILE = "license_manager_v4.py"   # Nome do script do admin

# Contatos de Suporte (Aparecem nas mensagens de erro/renovação)
SUPPORT_CONTACT = "https://t.me/magoTrader_01"
SUPPORT_NAME = "Mago Trader"

# =============================================================================
# SEGURANÇA
# =============================================================================

# Salt para geração de hash (não compartilhe isso publicamente se possível)
# Como o código é Python aberto, isso é apenas uma ofuscação básica.
SECURITY_SALT = "black_bot_v4_secure_salt_2026"

# Dias para aviso de vencimento
WARNING_DAYS = 3
