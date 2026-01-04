"""utils/publisher.py - Script de Publicação Automática (Deploy)"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Configurações dos Repositórios
REPOS = {
    "public": {
        "url": "https://github.com/juniorbatistamlk-stack/updates-bot.git",
        "branch": "main",
        "folder": "DEPLOY_PUBLIC",
        "include": [
            "main.py", "requirements.txt", "config_license.py", ".env.example",
            "utils", "strategies", "ui", "api", "dados", "testes"
        ],
        "exclude": [
            "utils/__pycache__", "utils/*.pyc",
            "utils/license_validator_v4.py"  # Incluir validador? SIM.
        ],
        "ignore_patterns": [
            "__pycache__", "*.pyc", "*.key", "license.key", "license_manager_v4.py", 
            "license_database.json", "license_generator.py", "key_gen.py", 
            "trade_history.json", ".env", "darkblackbot.ico"
        ]
    },
    "admin": {
        "url": "https://github.com/juniorbatistamlk-stack/DarkBlackBot-Admin.git",
        "branch": "main",
        "folder": "DEPLOY_ADMIN",
        "include": [
            "license_manager_v4.py", 
            "license_database.json",
            "config_license.py"
        ],
        "exclude": [],
        "ignore_patterns": ["__pycache__", "*.pyc", ".env"]
    }
}

def run_cmd(cmd, cwd=None):
    try:
        subprocess.run(cmd, check=True, cwd=cwd, shell=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erro no comando: {cmd}\n{e}")
        return False

def clean_folder(folder):
    """Limpa pasta de deploy mantendo o .git"""
    path = Path(folder)
    if not path.exists():
        path.mkdir()
        return

    for item in path.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

def copy_files(target):
    conf = REPOS[target]
    dest_dir = Path(conf["folder"])
    src_dir = Path(".")
    
    print(f"📦 Copiando arquivos para {dest_dir}...")
    
    # Copiar itens da whitelist
    for item_name in conf["include"]:
        src = src_dir / item_name
        dest = dest_dir / item_name
        
        if not src.exists():
            print(f"⚠️ Aviso: {item_name} não encontrado.")
            continue
            
        if src.is_dir():
            # Ignorar padrões específicos
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*conf["ignore_patterns"]))
        else:
            shutil.copy2(src, dest)
    
    # Verificar se licença validator está indo para Public
    if target == "public":
        # Garante que .ico vá se existir
        if (src_dir / "darkblackbot.ico").exists():
            shutil.copy2(src_dir / "darkblackbot.ico", dest_dir / "darkblackbot.ico")

def git_push(target):
    conf = REPOS[target]
    cwd = conf["folder"]
    url = conf["url"]
    
    print(f"🚀 Iniciando Git Push em {cwd}...")
    
    # Init se não existir
    if not (Path(cwd) / ".git").exists():
        run_cmd("git init", cwd=cwd)
        run_cmd(f"git remote add origin {url}", cwd=cwd)
        # Tentar pull primeiro para não dar conflito
        run_cmd(f"git pull origin {conf['branch']}", cwd=cwd)
    else:
        # Garantir URL correta
        run_cmd(f"git remote set-url origin {url}", cwd=cwd)

    # GARANTIR IDENTIDADE GIT (Evita erro "Please tell me who you are")
    run_cmd('git config user.email "admin@blackbot.local"', cwd=cwd)
    run_cmd('git config user.name "Dark Black Admin"', cwd=cwd)

    # Add, Commit, Push
    run_cmd("git add .", cwd=cwd)
    run_cmd('git commit -m "Auto-Update: version update"', cwd=cwd)
    run_cmd(f"git branch -M {conf['branch']}", cwd=cwd)
    
    # Tentar push normal. Se falhar, tentar pull rebase e push
    if not run_cmd(f"git push -u origin {conf['branch']}", cwd=cwd):
        print("⚠️ Push falhou. Tentando pull rebase...")
        run_cmd(f"git pull origin {conf['branch']} --rebase", cwd=cwd)
        if not run_cmd(f"git push -u origin {conf['branch']}", cwd=cwd):
            print("❌ ERRO FATAL NO PUSH. Verifique credenciais ou conflitos.")
            return False
            
    print(f"✅ {target.upper()} publicado com sucesso!")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in REPOS:
        print("Uso: python publisher.py [public|admin]")
        sys.exit(1)
        
    target = sys.argv[1]
    
    print(f"=== PUBLICADOR AUTOMÁTICO: {target.upper()} ===")
    clean_folder(REPOS[target]["folder"])
    copy_files(target)
    git_push(target)
