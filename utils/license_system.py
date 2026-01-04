"""utils/license_system.py - SISTEMA DE ATIVAÇÃO (KEY 1X) + LICENÇA LOCAL (v3)

Requisitos:
- Primeira vez: pedir KEY de ativação.
- Após ativar: não pedir mais (salva licença local).
- A KEY é de uso único (após ativação não deve ser reutilizada).
- Aviso começando 3 dias antes do vencimento.
- Ao vencer: bloquear e orientar contato com suporte.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import secrets
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests


# URL DO BANCO DE LICENÇAS (somente leitura). O admin publica o JSON.
LICENSE_DB_URL = "https://raw.githubusercontent.com/juniorbatistamlk-stack/DarkBlackBot/main/license_database.json"

# Arquivo local da licença (persistente no PC do usuário)
LOCAL_LICENSE_FILE = ".dbbpro_license.json"

SUPPORT_CONTACT = "https://t.me/magoTrader_01"

# Segredo local para assinatura do arquivo de licença.
# Observação: isso NÃO é segurança forte (cliente pode editar o código),
# mas evita corrupção acidental e bloqueia edições simples do JSON.
_LOCAL_SIGNATURE_SECRET = b"darkblack_bot_pro_local_license_v3"


def _now() -> datetime:
    return datetime.now()


def _norm_key(key: str) -> str:
    return str(key or "").strip().upper().replace(" ", "")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _hmac_sig(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hmac.new(_LOCAL_SIGNATURE_SECRET, raw, hashlib.sha256).hexdigest()


def _parse_iso_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


@dataclass
class LicenseRecord:
    key: str
    name: str
    whatsapp: str
    created_at: str
    expiry_date: str
    status: str | None = None
    activated_hwid: str | None = None
    activated_at: str | None = None
    notes: str | None = None


class LicenseSystem:
    def __init__(self):
        self.device_id = self.get_hwid()
        self._here = Path(__file__).resolve()
        self._project_root = self._here.parent.parent

    def get_hwid(self) -> str:
        """Gera ID único do hardware (Windows)."""
        try:
            if platform.system() == "Windows":
                cmd = "wmic csproduct get uuid"
                uuid = subprocess.check_output(cmd).decode(errors="ignore").split("\n")[1].strip()
                if uuid:
                    return hashlib.sha256(uuid.encode()).hexdigest()[:32]
        except Exception:
            pass
        # Fallback: nome do PC
        return hashlib.sha256(platform.node().encode()).hexdigest()[:32]

    def check_license(self) -> bool:
        """Fluxo principal: valida licença local; se não existir, ativa com KEY 1x."""
        local = self._load_local_license()
        if local:
            ok, days_left, status_msg = self._validate_local_license(local)
            if not ok:
                self._show_expired_screen(days_left, status_msg)
                return False

            # Aviso 3 dias antes (inclusive)
            if days_left <= 3:
                self._show_warning_screen(days_left)
                time.sleep(2)
            return True

        # Sem licença local -> pedir ativação
        return self.request_activation()

    def request_activation(self) -> bool:
        """Solicita KEY ao usuário e cria licença local após validação."""
        print("\n" + "=" * 64)
        print("🔐 ATIVAÇÃO - DARK BLACK BOT PRO")
        print("=" * 64)
        print(f"ID do seu PC (HWID): {self.device_id}")
        print("\n📌 IMPORTANTE:")
        print("- A KEY é usada apenas para ATIVAR.")
        print("- Depois de ativar, a KEY é CONSUMIDA e não será solicitada novamente.")
        print("- Sua licença ficará salva neste computador.")
        print("- Para renovação/suporte: " + SUPPORT_CONTACT)
        print("-" * 64)

        while True:
            key = _norm_key(input("\n🔑 Digite sua KEY: "))
            if not key:
                continue

            print("⏳ Verificando KEY...")
            ok, msg, lic = self._validate_activation_key(key)
            if not ok or not lic:
                print(f"\n❌ {msg}")
                retry = input("Tentar novamente? (S/N): ").strip().upper()
                if retry != "S":
                    return False
                continue

            saved_ok, saved_msg = self._save_local_license_from_record(lic)
            if not saved_ok:
                print(f"\n❌ {saved_msg}")
                return False

            # Melhor esforço: marcar como usada no(s) banco(s) local(is) caso exista(m)
            self._try_mark_key_used_locally(key)

            print("\n✅ ATIVAÇÃO CONCLUÍDA!")
            print("⚠️ Sua KEY foi consumida após a ativação e não deverá ser reutilizada.")
            print("✅ A licença foi salva neste computador e o bot não pedirá a KEY novamente.")
            return True

    # -----------------
    # Local license file
    # -----------------

    def _local_license_path(self) -> Path:
        # Preferir salvar ao lado do executável/projeto
        try:
            return self._project_root / LOCAL_LICENSE_FILE
        except Exception:
            return Path.cwd() / LOCAL_LICENSE_FILE

    def _load_local_license(self) -> dict[str, Any] | None:
        path = self._local_license_path()
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            payload = raw.get("payload")
            sig = raw.get("sig")
            if not isinstance(payload, dict) or not isinstance(sig, str):
                return None
            if _hmac_sig(payload) != sig:
                return None
            return payload
        except Exception:
            return None

    def _save_local_license(self, payload: dict[str, Any]) -> tuple[bool, str]:
        try:
            path = self._local_license_path()
            wrapper = {"payload": payload, "sig": _hmac_sig(payload)}
            path.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
            return True, "ok"
        except Exception as e:
            return False, f"Erro ao salvar licença local: {e}"

    def _save_local_license_from_record(self, lic: LicenseRecord) -> tuple[bool, str]:
        expiry = _parse_iso_dt(lic.expiry_date)
        if not expiry:
            return False, "Licença com data inválida."

        payload: dict[str, Any] = {
            "version": 3,
            "license_fingerprint": _sha256(_norm_key(lic.key)),
            "name": lic.name,
            "whatsapp": lic.whatsapp,
            "hwid": self.device_id,
            "created_at": lic.created_at,
            "expires_at": expiry.isoformat(),
            "activated_at": _now().isoformat(),
        }
        return self._save_local_license(payload)

    def _validate_local_license(self, payload: dict[str, Any]) -> tuple[bool, int, str]:
        hwid = str(payload.get("hwid", "")).strip()
        if not hwid or hwid != self.device_id:
            return False, -9999, "Licença não pertence a este computador."

        expiry = _parse_iso_dt(payload.get("expires_at"))
        if not expiry:
            return False, -9999, "Licença corrompida (data inválida)."

        days_left = (expiry - _now()).days
        if days_left < 0:
            return False, days_left, "Licença expirada."

        return True, days_left, "Licença válida."

    # -----------------
    # DB lookup/validation
    # -----------------

    def _validate_activation_key(self, key: str) -> tuple[bool, str, LicenseRecord | None]:
        key_norm = _norm_key(key)
        if not key_norm:
            return False, "KEY vazia.", None

        # 1) Online (somente leitura)
        lic = self._find_license_online(key_norm)
        if lic:
            ok, msg = self._validate_license_record_for_activation(lic, key_norm)
            return ok, msg, lic if ok else None

        # 2) Offline (license_database.json local)
        local_hit = self._find_license_in_local_dbs(key_norm)
        if local_hit:
            lic, _src = local_hit
            ok, msg = self._validate_license_record_for_activation(lic, key_norm)
            return ok, (msg + " (offline)") if ok else msg, lic if ok else None

        return False, "KEY não encontrada no banco de licenças.", None

    def _find_license_online(self, key_norm: str) -> LicenseRecord | None:
        try:
            resp = requests.get(LICENSE_DB_URL, timeout=6)
            if resp.status_code != 200:
                return None
            db = resp.json()
            return self._find_license_in_db_obj(db, key_norm)
        except Exception:
            return None

    def _find_license_in_db_obj(self, db: Any, key_norm: str) -> LicenseRecord | None:
        if not isinstance(db, dict):
            return None
        items = db.get("licenses")
        if not isinstance(items, list):
            return None
        for row in items:
            if not isinstance(row, dict):
                continue
            k = _norm_key(row.get("key"))
            if k != key_norm:
                continue
            return LicenseRecord(
                key=key_norm,
                name=str(row.get("name") or ""),
                whatsapp=str(row.get("whatsapp") or ""),
                created_at=str(row.get("created_at") or ""),
                expiry_date=str(row.get("expiry_date") or row.get("expires_at") or ""),
                status=str(row.get("status") or "active"),
                activated_hwid=(str(row.get("activated_hwid")) if row.get("activated_hwid") else row.get("hwid")),
                activated_at=str(row.get("activated_at") or "") or None,
                notes=str(row.get("notes") or "") or None,
            )
        return None

    def _validate_license_record_for_activation(self, lic: LicenseRecord, key_norm: str) -> tuple[bool, str]:
        if lic.status and str(lic.status).lower() not in ("active", "ativo"):
            return False, "KEY desativada."

        expiry = _parse_iso_dt(lic.expiry_date)
        if not expiry:
            return False, "Licença com data inválida no banco."
        if expiry < _now():
            return False, "Esta KEY já expirou."

        # Uso único: se já tem hwid vinculado e for diferente, bloquear
        bound = str(lic.activated_hwid or "").strip()
        if bound and bound != self.device_id:
            return False, "KEY já foi usada e não pode ser ativada novamente."

        return True, "KEY validada com sucesso!"

    def _candidate_local_db_paths(self):
        # Mantém compatibilidade com o layout do projeto/instalador
        yield Path.cwd() / "license_database.json"
        yield self._project_root / "license_database.json"
        yield self._project_root / "INSTALADOR_FINAL" / "license_database.json"
        inst = self._project_root / "INSTALADOR_FINAL"
        if inst.exists() and inst.is_dir():
            try:
                for child in inst.iterdir():
                    if child.is_dir():
                        cand = child / "license_database.json"
                        yield cand
            except Exception:
                pass

    def _find_license_in_local_dbs(self, key_norm: str) -> tuple[LicenseRecord, str] | None:
        for p in self._candidate_local_db_paths():
            try:
                if not p.exists():
                    continue
                db = json.loads(p.read_text(encoding="utf-8"))
                lic = self._find_license_in_db_obj(db, key_norm)
                if lic:
                    return lic, str(p)
            except Exception:
                continue
        return None

    def _try_mark_key_used_locally(self, key_norm: str) -> None:
        """Melhor esforço: marca activated_hwid/activated_at no banco local.

        Isso não atualiza o GitHub (somente leitura), mas ajuda no cenário offline.
        """
        for p in self._candidate_local_db_paths():
            try:
                if not p.exists():
                    continue
                raw = json.loads(p.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or not isinstance(raw.get("licenses"), list):
                    continue
                changed = False
                for row in raw["licenses"]:
                    if not isinstance(row, dict):
                        continue
                    if _norm_key(row.get("key")) != key_norm:
                        continue
                    # Compat com esquema antigo (hwid) e novo (activated_hwid)
                    row["activated_hwid"] = self.device_id
                    row["activated_at"] = _now().isoformat()
                    row["hwid"] = self.device_id
                    row["used"] = True
                    changed = True
                    break
                if changed:
                    p.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                continue

    # -----------------
    # Screens/messages
    # -----------------

    def _show_warning_screen(self, days_left: int) -> None:
        print("\n" + "═" * 64)
        print(f"⚠️ ATENÇÃO: seu acesso expira em {days_left} dia(s)")
        print("═" * 64)
        print("Para não ficar sem operar, solicite a renovação antes do vencimento:")
        print("Suporte: " + SUPPORT_CONTACT)
        print("═" * 64 + "\n")

    def _show_expired_screen(self, days_left: int, reason: str) -> None:
        print("\n" + "█" * 64)
        print("🛑 ACESSO BLOQUEADO - LICENÇA EXPIRADA")
        print("█" * 64)
        if days_left != -9999:
            print(f"Seu acesso venceu há {abs(days_left)} dia(s).")
        else:
            print(f"Problema na licença: {reason}")
        print("\nPara renovar e continuar usando o DARK BLACK BOT PRO,")
        print("entre em contato com o suporte:")
        print("👉 " + SUPPORT_CONTACT)
        print("█" * 64 + "\n")


def check_license() -> bool:
    """API compatível com o main.py"""
    return LicenseSystem().check_license()

    def _find_license_in_local_dbs(self, key_norm: str):
        for path in self._iter_local_db_paths():
            try:
                if not path.exists() or not path.is_file():
                    continue
                with path.open("r", encoding="utf-8") as f:
                    db = json.load(f)
                lic = self._find_license_in_db(db, key_norm)
                if lic:
                    return lic, str(path)
            except Exception:
                continue
        return None

    def _iter_local_db_paths(self):
        try:
            yield Path.cwd() / "license_database.json"
        except Exception:
            pass

        yield self._project_root / "license_database.json"
        yield self._project_root / "INSTALADOR_FINAL" / "license_database.json"

        # Scan subfolders inside INSTALADOR_FINAL for any license_database.json
        try:
            base = self._project_root / "INSTALADOR_FINAL"
            if base.exists() and base.is_dir():
                for child in base.iterdir():
                    if child.is_dir():
                        cand = child / "license_database.json"
                        if cand.exists():
                            yield cand
        except Exception:
            pass

    def load_local(self):
        if not os.path.exists(LICENSE_FILE):
            return None
        try:
            with open(LICENSE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return None

    def save_local(self, data):
        with open(LICENSE_FILE, 'w') as f:
            json.dump(data, f)

# Função auxiliar para manter compatibilidade
def check_license():
    system = LicenseSystem()
    return system.check_license()
