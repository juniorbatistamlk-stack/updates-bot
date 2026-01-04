# utils/multi_provider_ai.py
"""
================================================================================
🤖 SISTEMA MULTI-PROVIDER DE IA COM AUTO-FALLBACK
================================================================================
Rotaciona automaticamente entre OpenRouter, Groq e Gemini quando uma API 
atinge rate limit. Mantém análise contínua sem interrupções.

Estratégia:
  1. Tenta provedor principal
  2. Se rate limit → tenta próximo provedor
  3. Se todos limitados → usa cache + fallback inteligente
  4. Cooldown por provedor (não tenta API em cooldown)
================================================================================
"""

import os
import time
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass
from openai import OpenAI

# Contextos avançados (opcionais) para a IA
try:
    from utils.mtf_helper import get_complete_analysis
    SR_MTF_AVAILABLE = True
except Exception:
    SR_MTF_AVAILABLE = False
    get_complete_analysis = None

try:
    from utils.price_movement_analyzer import analyze_movement
    MOVEMENT_ANALYZER_AVAILABLE = True
except Exception:
    MOVEMENT_ANALYZER_AVAILABLE = False
    analyze_movement = None


@dataclass
class ProviderConfig:
    """Configuração de um provedor de IA"""
    name: str
    base_url: str
    model: str
    api_key: str
    priority: int = 1
    cooldown_until: float = 0
    consecutive_errors: int = 0
    total_calls: int = 0
    rate_limit_hits: int = 0


@dataclass
class AnalysisCache:
    """Cache de análises recentes para fallback"""
    pair: str
    signal: str
    confidence: int
    reason: str
    timestamp: float
    ttl: float = 30.0  # 30 segundos de validade
    
    def is_valid(self) -> bool:
        return time.time() - self.timestamp < self.ttl


class MultiProviderAI:
    """
    Gerenciador Multi-Provider de IA com Auto-Fallback
    """
    
    # Cooldowns por tipo de erro
    COOLDOWN_RATE_LIMIT = 60  # 60s após rate limit
    COOLDOWN_ERROR = 30       # 30s após erro genérico
    COOLDOWN_AUTH = 3600      # 1h após erro de auth (chave inválida)
    MAX_CONSECUTIVE_ERRORS = 3
    
    def __init__(self, memory=None, logger=None):
        self.memory = memory
        self._logger = logger
        self.providers: Dict[str, ProviderConfig] = {}
        self.clients: Dict[str, OpenAI] = {}
        self.cache: Dict[str, AnalysisCache] = {}
        self.last_analysis_time = 0
        self.min_interval = 1.5  # Intervalo mínimo entre análises
        self.api = None  # API da corretora
        self._current_provider: str = None
        self._status = "INITIALIZING"
        
        # Inicializar provedores
        self._init_providers()
        
    def _init_providers(self):
        """Inicializa todos os provedores configurados"""
        
        # OpenRouter (Free tier)
        openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("AI_API_KEY")
        if openrouter_key:
            self.providers["openrouter"] = ProviderConfig(
                name="OpenRouter",
                base_url="https://openrouter.ai/api/v1",
                model=os.getenv("OPENROUTER_MODEL") or "meta-llama/llama-3.3-70b-instruct:free",
                api_key=openrouter_key,
                priority=1
            )
            self._log("[AI] ✅ OpenRouter configurado")
        
        # Groq (muito rápido, rate limits moderados)
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            self.providers["groq"] = ProviderConfig(
                name="Groq",
                base_url="https://api.groq.com/openai/v1",
                model=os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile",
                api_key=groq_key,
                priority=2
            )
            self._log("[AI] ✅ Groq configurado")
        
        # Gemini (Google, rate limits generosos)
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            self.providers["gemini"] = ProviderConfig(
                name="Gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                model=os.getenv("GEMINI_MODEL") or "gemini-2.0-flash",
                api_key=gemini_key,
                priority=3
            )
            self._log("[AI] ✅ Gemini configurado")
        
        # Criar clientes OpenAI para cada provedor
        for name, config in self.providers.items():
            try:
                self.clients[name] = OpenAI(
                    base_url=config.base_url,
                    api_key=config.api_key,
                    timeout=25.0
                )
            except Exception as e:
                self._log(f"[AI] ⚠️ Erro ao criar cliente {name}: {e}")
        
        if not self.providers:
            self._log("[AI] ⚠️ Nenhuma API de IA configurada!")
            self._status = "DISABLED"
        else:
            self._status = "READY"
            self._current_provider = self._get_best_provider()
            self._log(f"[AI] 🚀 Multi-Provider ativo: {len(self.providers)} APIs")
    
    def _log(self, msg: str):
        if self._logger:
            self._logger(msg)
        else:
            print(msg)
    
    def set_logger(self, log_func):
        self._logger = log_func
    
    def set_memory(self, memory):
        self.memory = memory
    
    def set_api(self, api):
        self.api = api

    def _format_ai_context(self, ai_context: dict | None) -> str:
        if not ai_context or not isinstance(ai_context, dict):
            return ""

        keys_order = [
            "setup",
            "pattern",
            "trend",
            "micro",
            "macro",
            "sr",
            "sr_strength",
            "notes",
        ]
        lines = []
        for k in keys_order:
            if k in ai_context and ai_context.get(k) is not None:
                v = ai_context.get(k)
                txt = str(v)
                if len(txt) > 220:
                    txt = txt[:220] + "..."
                lines.append(f"- {k}: {txt}")

        # Evitar prompt gigante
        if len(lines) > 10:
            lines = lines[:10] + ["- ..."]

        return "\n".join(lines)

    def _get_mtf_context(self, pair: str) -> str:
        if not SR_MTF_AVAILABLE or not self.api or not get_complete_analysis:
            return ""
        try:
            result = get_complete_analysis(self.api, pair)
            prompt = (result or {}).get("prompt") or ""
            if prompt:
                # Limitar tamanho (prompt completo pode ser grande)
                prompt = prompt.strip()
                if len(prompt) > 1400:
                    prompt = prompt[:1400] + "..."
                return "\n" + prompt
        except Exception:
            return ""
        return ""

    def _get_movement_context(self, pair: str, candles: list) -> str:
        if not MOVEMENT_ANALYZER_AVAILABLE or not analyze_movement:
            return ""
        if not candles or len(candles) < 20:
            return ""
        try:
            mv = analyze_movement(pair, candles)
            ctx = mv.get("context")
            if ctx and isinstance(ctx, str):
                ctx = ctx.strip()
                if len(ctx) > 1000:
                    ctx = ctx[:1000] + "..."
                return "\n" + ctx
        except Exception:
            return ""
        return ""
    
    def get_status(self) -> str:
        """Retorna status atual do sistema de IA"""
        available = sum(1 for p in self.providers.values() 
                       if p.cooldown_until < time.time())
        total = len(self.providers)
        
        if total == 0:
            return "DISABLED"
        elif available == total:
            return "READY"
        elif available > 0:
            return "DEGRADED"
        else:
            return "LIMITED"

    def check_connection(self) -> tuple[bool, str]:
        """Valida conectividade de pelo menos 1 provedor.

        - Se algum provedor responder: OK
        - Se todos estiverem em 429/quota: considera chave OK (mas limitado)
        - Se todos falharem por auth: inválido
        """
        if not self.providers:
            return False, "Nenhuma API configurada"

        saw_rate_limit = False
        saw_auth_error = False
        tried = 0

        for name, cfg in self.providers.items():
            client = self.clients.get(name)
            if not client:
                continue
            tried += 1
            try:
                client.chat.completions.create(
                    model=cfg.model,
                    messages=[{"role": "user", "content": "HI"}],
                    max_tokens=5,
                    temperature=0,
                )
                return True, f"{cfg.name} OK"
            except Exception as e:
                msg = str(e)
                if self._is_rate_limit_error(msg):
                    saw_rate_limit = True
                    continue
                if self._is_auth_error(msg):
                    saw_auth_error = True
                    continue

        if tried == 0:
            return False, "Nenhum cliente de IA disponível"

        if saw_rate_limit and not saw_auth_error:
            return True, "Chaves OK, mas limite/QUOTA atingido (429)"

        if saw_auth_error and not saw_rate_limit:
            return False, "Chave inválida/sem permissão (401/403)"

        # Misturado ou erro genérico
        return False, "Falha ao validar (provedores indisponíveis)"
    
    def _get_best_provider(self) -> Optional[str]:
        """Retorna o melhor provedor disponível (não em cooldown)"""
        now = time.time()
        available = [
            (name, cfg) for name, cfg in self.providers.items()
            if cfg.cooldown_until < now and cfg.consecutive_errors < self.MAX_CONSECUTIVE_ERRORS
        ]
        
        if not available:
            # Todos em cooldown - retorna o que sai primeiro do cooldown
            by_cooldown = sorted(
                self.providers.items(),
                key=lambda x: x[1].cooldown_until
            )
            if by_cooldown:
                return by_cooldown[0][0]
            return None
        
        # Ordenar por prioridade e menos erros
        available.sort(key=lambda x: (x[1].priority, x[1].consecutive_errors))
        return available[0][0]
    
    def _set_cooldown(self, provider_name: str, duration: float, reason: str = ""):
        """Coloca provedor em cooldown"""
        if provider_name in self.providers:
            self.providers[provider_name].cooldown_until = time.time() + duration
            self.providers[provider_name].consecutive_errors += 1
            self._log(f"[AI] ⏳ {provider_name} em cooldown {duration:.0f}s ({reason})")
    
    def _reset_provider_errors(self, provider_name: str):
        """Reseta contador de erros após sucesso"""
        if provider_name in self.providers:
            self.providers[provider_name].consecutive_errors = 0
            self.providers[provider_name].total_calls += 1
    
    def _is_rate_limit_error(self, error_msg: str) -> bool:
        """Verifica se é erro de rate limit"""
        indicators = [
            "rate", "429", "quota", "limit", "too many",
            "resource_exhausted", "throttl"
        ]
        error_lower = error_msg.lower()
        return any(ind in error_lower for ind in indicators)
    
    def _is_auth_error(self, error_msg: str) -> bool:
        """Verifica se é erro de autenticação"""
        indicators = ["401", "403", "unauthorized", "invalid key", "api key"]
        error_lower = error_msg.lower()
        return any(ind in error_lower for ind in indicators)
    
    def _get_cached_analysis(self, pair: str, signal: str) -> Optional[AnalysisCache]:
        """Busca análise em cache"""
        key = f"{pair}_{signal}"
        cached = self.cache.get(key)
        if cached and cached.is_valid():
            return cached
        return None
    
    def _cache_analysis(self, pair: str, signal: str, confidence: int, reason: str):
        """Salva análise no cache"""
        key = f"{pair}_{signal}"
        self.cache[key] = AnalysisCache(
            pair=pair,
            signal=signal,
            confidence=confidence,
            reason=reason,
            timestamp=time.time()
        )
    
    def _call_provider(self, provider_name: str, messages: List[dict]) -> Optional[str]:
        """Faz chamada para um provedor específico"""
        if provider_name not in self.clients:
            return None
        
        config = self.providers[provider_name]
        client = self.clients[provider_name]
        
        try:
            response = client.chat.completions.create(
                model=config.model,
                messages=messages,
                temperature=0.4,
                max_tokens=150
            )
            
            self._reset_provider_errors(provider_name)
            self._current_provider = provider_name
            
            return response.choices[0].message.content
            
        except Exception as e:
            error_msg = str(e)
            
            if self._is_rate_limit_error(error_msg):
                config.rate_limit_hits += 1
                self._set_cooldown(provider_name, self.COOLDOWN_RATE_LIMIT, "rate limit")
            elif self._is_auth_error(error_msg):
                self._set_cooldown(provider_name, self.COOLDOWN_AUTH, "auth error")
            else:
                self._set_cooldown(provider_name, self.COOLDOWN_ERROR, "error")
            
            return None
    
    def analyze_signal(
        self,
        signal: str,
        desc: str,
        candles: list,
        sr_zones: dict,
        trend: str,
        pair: str,
        ai_context: dict = None,
        strategy_logic: str = None
    ) -> Tuple[bool, int, str]:
        """
        Analisa sinal com auto-fallback entre provedores
        
        Returns:
            (confirm, confidence, reason)
        """
        # Rate limiting geral
        elapsed = time.time() - self.last_analysis_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        
        # Verificar cache primeiro
        cached = self._get_cached_analysis(pair, signal)
        if cached:
            return True, cached.confidence, f"{cached.reason} (cache)"
        
        if not self.providers:
            return True, 70, "IA não configurada"
        
        # Criar prompt (com contexto avançado quando disponível)
        mtf_context = self._get_mtf_context(pair)
        movement_context = self._get_movement_context(pair, candles)
        prompt = self._create_prompt(
            signal,
            desc,
            candles,
            sr_zones,
            trend,
            pair,
            strategy_logic,
            ai_context,
            mtf_context,
            movement_context,
        )
        messages = [
            {"role": "system", "content": "Voce e o Cerebro de um Bot de Trading de Elite. Sua missao e ENCONTRAR OPORTUNIDADES LUCRATIVAS. Seja agressivo mas tecnico. Se ver potencial, mande entrar!"},
            {"role": "user", "content": prompt}
        ]
        
        # Tentar cada provedor em ordem de prioridade
        tried_providers = []
        
        for _ in range(len(self.providers)):
            provider_name = self._get_best_provider()
            
            if not provider_name or provider_name in tried_providers:
                break
            
            tried_providers.append(provider_name)
            
            response = self._call_provider(provider_name, messages)
            
            if response:
                self.last_analysis_time = time.time()
                confirm, confidence, reason = self._parse_response(response)
                
                # Ajustar confiança pelo histórico
                confidence = self._adjust_confidence_by_winrate(confidence, desc)
                
                # Cachear resultado
                self._cache_analysis(pair, signal, confidence, reason)
                
                # Log sucesso
                self._log(f"[AI] ✅ {provider_name} respondeu")
                
                return confirm, confidence, reason
        
        # Todos os provedores falharam - usar fallback inteligente
        self._log("[AI] ⚠️ Todos os provedores ocupados - usando fallback")
        return self._smart_fallback(signal, desc, candles, sr_zones)
    
    def _smart_fallback(
        self,
        signal: str,
        desc: str,
        candles: list,
        sr_zones: dict
    ) -> Tuple[bool, int, str]:
        """
        Fallback inteligente quando todas as IAs estão indisponíveis
        Usa análise técnica básica + histórico de win rate
        """
        confidence = 75
        reasons = []
        
        # 1. Verificar histórico do padrão
        if self.memory:
            try:
                pattern = desc.split("|")[0].strip() if "|" in desc else desc
                stats = getattr(self.memory, 'stats', {})
                patterns = stats.get("patterns", {}) if isinstance(stats, dict) else {}
                
                if pattern in patterns:
                    p = patterns[pattern]
                    wins = int(p.get("wins") or 0)
                    total = int(p.get("total") or 0)
                    if total >= 5:
                        wr = (wins / total) * 100
                        if wr >= 60:
                            confidence += 15
                            reasons.append(f"WR {wr:.0f}%")
                        elif wr < 40:
                            confidence -= 10
                            reasons.append("WR baixo")
            except Exception:
                pass
        
        # 2. Análise de momentum das últimas velas
        if candles and len(candles) >= 5:
            last_5 = candles[-5:]
            greens = sum(1 for c in last_5 if c['close'] > c['open'])
            
            if signal == "CALL" and greens >= 3:
                confidence += 10
                reasons.append("momentum alta")
            elif signal == "PUT" and greens <= 2:
                confidence += 10
                reasons.append("momentum baixa")
        
        # 3. Verificar S/R
        if sr_zones:
            try:
                supports = len(sr_zones.get('support', []))
                resistances = len(sr_zones.get('resistance', []))
                if supports > 0 or resistances > 0:
                    reasons.append("S/R detectado")
            except Exception:
                pass
        
        reason = "Fallback: " + ", ".join(reasons) if reasons else "Fallback técnico"
        
        return True, min(100, max(50, confidence)), reason
    
    def _create_prompt(
        self,
        signal: str,
        desc: str,
        candles: list,
        sr_zones: dict,
        trend: str,
        pair: str,
        strategy_logic: str = None,
        ai_context: dict = None,
        mtf_context: str = "",
        movement_context: str = "",
    ) -> str:
        """Cria prompt para análise"""
        # Formatar velas
        candles_data = self._format_candles(candles[-10:]) if candles and len(candles) >= 10 else "Dados insuficientes"
        
        # Resumo S/R
        zones_summary = "0"
        try:
            if isinstance(sr_zones, dict):
                sup = len(sr_zones.get('support', []))
                res = len(sr_zones.get('resistance', []))
                zones_summary = f"S:{sup} R:{res}"
        except Exception:
            pass
        
        # Contexto da memória
        memory_context = self._get_memory_context(desc) if self.memory else ""

        extra_ctx = self._format_ai_context(ai_context)
        extra_ctx = f"\nCONTEXTO ESTRUTURADO (estratégia):\n{extra_ctx}\n" if extra_ctx else ""
        
        return f"""ANALISE RAPIDA DE TRADING

{memory_context}
{chr(10) + "ESTRATEGIA:" + chr(10) + strategy_logic[:500] if strategy_logic else ""}
    {extra_ctx}
    {mtf_context}
    {movement_context}

SINAL: {signal} em {pair}
Padrao: {desc}
Tendencia: {trend}
S/R: {zones_summary}
Velas: {candles_data}

⚠️ REGRA CRÍTICA:

- Por padrão, S/R forte tende a segurar e gerar reversões.
- Porém, pode haver ROMPIMENTO (breakout). Não rejeite automaticamente só por estar perto de S/R.
- Rejeite quando entrar contra S/R forte SEM evidência clara de rompimento.

EXCEÇÃO (BREAKOUT):
- CALL perto de resistência pode ser CONFIRMADO se houver impulso/momentum e tendência/micro+macro a favor, sem divergência contrária.
- PUT perto de suporte pode ser CONFIRMADO se houver impulso/momentum e tendência/micro+macro a favor, sem divergência contrária.

INSTRUCOES:
- Confirme se o setup é válido E respeita zonas S/R
- REJEITE se vai CONTRA zona de suporte/resistência forte SEM evidência clara de rompimento

RESPONDA:
DECISAO: CONFIRMAR ou REJEITAR
CONFIANCA: 0-100
MOTIVO: [curto]"""
    
    def _format_candles(self, candles: list) -> str:
        """Formata velas para prompt"""
        formatted = []
        for c in candles[-10:]:
            direction = "V" if c['close'] > c['open'] else "R"
            body = abs(c['close'] - c['open'])
            range_total = c['high'] - c['low']
            body_pct = int((body / range_total * 100)) if range_total > 0 else 0
            formatted.append(f"{direction}{body_pct}")
        return " ".join(formatted)
    
    def _get_memory_context(self, desc: str) -> str:
        """Obtém contexto da memória"""
        if not self.memory:
            return ""
        
        try:
            stats = getattr(self.memory, 'stats', {})
            total = stats.get('total_trades', 0)
            wr = stats.get('win_rate', 0)
            return f"Historico: {total} trades, WR: {wr:.1f}%"
        except Exception:
            return ""
    
    def _adjust_confidence_by_winrate(self, confidence: int, desc: str) -> int:
        """Ajusta confiança baseado no histórico"""
        if not self.memory:
            return confidence
        
        try:
            pattern = desc.split("|")[0].strip() if "|" in desc else desc
            stats = getattr(self.memory, 'stats', {})
            patterns = stats.get("patterns", {}) if isinstance(stats, dict) else {}
            
            if pattern not in patterns:
                return max(confidence, 60)
            
            p = patterns[pattern]
            wins = int(p.get("wins") or 0)
            total = int(p.get("total") or 0)
            
            if total == 0:
                return confidence
            
            wr = (wins / total) * 100
            
            if wr > 70:
                return min(100, confidence + 25)
            elif wr >= 60:
                return min(100, confidence + 15)
            else:
                return max(confidence, 60)
        except Exception:
            return confidence
    
    def _parse_response(self, response_text: str) -> Tuple[bool, int, str]:
        """Parseia resposta da IA"""
        text = response_text.upper()
        
        confirm = "CONFIRMAR" in text
        
        confidence = 70
        import re
        conf_match = re.search(r'CONFIANCA[:\s]*(\d+)', text)
        if conf_match:
            confidence = min(100, max(0, int(conf_match.group(1))))
        
        reason = "Análise IA"
        lines = response_text.split('\n')
        for line in lines:
            if 'MOTIVO' in line.upper():
                reason = line.split(':', 1)[-1].strip()[:50]
                break
        
        if not confirm:
            confidence = min(confidence, 45)
        
        return confirm, confidence, reason
    
    def is_enabled(self) -> bool:
        return len(self.providers) > 0 and self.get_status() != "DISABLED"
    
    def get_provider_stats(self) -> Dict:
        """Retorna estatísticas dos provedores"""
        stats = {}
        now = time.time()
        
        for name, config in self.providers.items():
            in_cooldown = config.cooldown_until > now
            cooldown_remaining = max(0, config.cooldown_until - now)
            
            stats[name] = {
                "status": "cooldown" if in_cooldown else "available",
                "cooldown_remaining": int(cooldown_remaining),
                "total_calls": config.total_calls,
                "rate_limit_hits": config.rate_limit_hits,
                "consecutive_errors": config.consecutive_errors,
                "is_current": name == self._current_provider
            }
        
        return stats


# Instância global para fácil acesso
multi_ai: Optional[MultiProviderAI] = None

def get_multi_ai(memory=None, logger=None) -> MultiProviderAI:
    """Obtém ou cria instância do Multi-Provider AI"""
    global multi_ai
    if multi_ai is None:
        multi_ai = MultiProviderAI(memory=memory, logger=logger)
    return multi_ai
