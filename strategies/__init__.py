# strategies/__init__.py
"""
================================================================================
📊 REGISTRO DE ESTRATÉGIAS - ANTIGRAVITY BOT
================================================================================
"""

# Estratégias V1 (Originais)
from .base_strategy import BaseStrategy
from .conservador import ConservadorStrategy
from .ana_tavares import AnaTavaresStrategy
from .alavancagem import AlavancagemStrategy
from .alavancagem_sr import AlavancagemSRStrategy
from .price_action import PriceActionStrategy
from .ai_god_mode import AiGodModeStrategy
from .logica_preco import LogicaPrecoStrategy

# Estratégias Ferreira V1
from .ferreira import FerreiraStrategy
from .ferreira_price_action import FerreiraPriceActionStrategy
from .ferreira_snr_advanced import FerreiraSNRAdvancedStrategy
from .ferreira_moving_avg import FerreiraMovingAvgStrategy
from .ferreira_primeiro_registro import FerreiraPrimeiroRegistroStrategy
from .trader_machado import TraderMachadoStrategy

# ══════════════════════════════════════════════════════════════════════════════
# ESTRATÉGIAS V2 (REVISADAS E OTIMIZADAS)
# ══════════════════════════════════════════════════════════════════════════════
from .ferreira_price_action_v2 import FerreiraPriceActionV2Strategy
from .ferreira_snr_advanced_v2 import FerreiraSNRAdvancedV2Strategy
from .ferreira_moving_avg_v2 import FerreiraMovingAvgV2Strategy
from .ferreira_primeiro_registro_v2 import FerreiraPrimeiroRegistroV2Strategy
from .trader_machado_v2 import TraderMachadoV2Strategy

# Dicionário de estratégias disponíveis
AVAILABLE_STRATEGIES = {
    # V1 Originais
    "conservador": ConservadorStrategy,
    "ana_tavares": AnaTavaresStrategy,
    "alavancagem": AlavancagemStrategy,
    "alavancagem_sr": AlavancagemSRStrategy,
    "price_action": PriceActionStrategy,
    "ai_god_mode": AiGodModeStrategy,
    "logica_preco": LogicaPrecoStrategy,
    "ferreira": FerreiraStrategy,
    "ferreira_price_action": FerreiraPriceActionStrategy,
    "ferreira_snr_advanced": FerreiraSNRAdvancedStrategy,
    "ferreira_moving_avg": FerreiraMovingAvgStrategy,
    "ferreira_primeiro_registro": FerreiraPrimeiroRegistroStrategy,
    "trader_machado": TraderMachadoStrategy,
    
    # V2 Revisadas (RECOMENDADAS)
    "ferreira_price_action_v2": FerreiraPriceActionV2Strategy,
    "ferreira_snr_advanced_v2": FerreiraSNRAdvancedV2Strategy,
    "ferreira_moving_avg_v2": FerreiraMovingAvgV2Strategy,
    "ferreira_primeiro_registro_v2": FerreiraPrimeiroRegistroV2Strategy,
    "trader_machado_v2": TraderMachadoV2Strategy,
}

# Estratégias V2 (mais recentes e otimizadas)
V2_STRATEGIES = {
    "ferreira_price_action_v2": FerreiraPriceActionV2Strategy,
    "ferreira_snr_advanced_v2": FerreiraSNRAdvancedV2Strategy,
    "ferreira_moving_avg_v2": FerreiraMovingAvgV2Strategy,
    "ferreira_primeiro_registro_v2": FerreiraPrimeiroRegistroV2Strategy,
    "trader_machado_v2": TraderMachadoV2Strategy,
}

# Nomes amigáveis para UI
STRATEGY_NAMES = {
    # V1
    "conservador": "🛡️ Conservador",
    "ana_tavares": "👩 Ana Tavares",
    "alavancagem": "📈 Alavancagem",
    "alavancagem_sr": "📈 Alavancagem S/R",
    "price_action": "📊 Price Action",
    "ai_god_mode": "🤖 AI God Mode",
    "logica_preco": "💰 Lógica do Preço",
    "ferreira": "🎯 Ferreira Trader",
    "ferreira_price_action": "🎯 Ferreira Price Action",
    "ferreira_snr_advanced": "🎯 Ferreira S/R Advanced",
    "ferreira_moving_avg": "🎯 Ferreira Moving Avg",
    "ferreira_primeiro_registro": "🎯 Ferreira 1º Registro",
    "trader_machado": "🔧 Trader Machado",
    
    # V2 Revisadas
    "ferreira_price_action_v2": "⭐ Ferreira Price Action V2",
    "ferreira_snr_advanced_v2": "⭐ Ferreira S/R V2 (Anti-Box)",
    "ferreira_moving_avg_v2": "⭐ Ferreira EMA/SMA V2",
    "ferreira_primeiro_registro_v2": "⭐ Ferreira 1R V2",
    "trader_machado_v2": "⭐ Machado V2 (Lógica Preço)",
}


def get_strategy(name: str, api_handler, ai_analyzer=None):
    """
    Retorna uma instância da estratégia pelo nome
    
    Args:
        name: Nome da estratégia
        api_handler: Handler da API (IQ Option)
        ai_analyzer: Analisador AI opcional
    
    Returns:
        Instância da estratégia ou None
    """
    strategy_class = AVAILABLE_STRATEGIES.get(name)
    if strategy_class:
        return strategy_class(api_handler, ai_analyzer)
    return None


def get_v2_strategies():
    """Retorna apenas as estratégias V2 (recomendadas)"""
    return V2_STRATEGIES


def list_strategies():
    """Lista todas as estratégias disponíveis"""
    return list(AVAILABLE_STRATEGIES.keys())


def list_v2_strategies():
    """Lista apenas estratégias V2"""
    return list(V2_STRATEGIES.keys())


__all__ = [
    # Classes base
    "BaseStrategy",
    
    # V1
    "ConservadorStrategy",
    "AnaTavaresStrategy", 
    "AlavancagemStrategy",
    "AlavancagemSRStrategy",
    "PriceActionStrategy",
    "AiGodModeStrategy",
    "LogicaPrecoStrategy",
    "FerreiraStrategy",
    "FerreiraPriceActionStrategy",
    "FerreiraSNRAdvancedStrategy",
    "FerreiraMovingAvgStrategy",
    "FerreiraPrimeiroRegistroStrategy",
    "TraderMachadoStrategy",
    
    # V2
    "FerreiraPriceActionV2Strategy",
    "FerreiraSNRAdvancedV2Strategy",
    "FerreiraMovingAvgV2Strategy",
    "FerreiraPrimeiroRegistroV2Strategy",
    "TraderMachadoV2Strategy",
    
    # Funções helper
    "get_strategy",
    "get_v2_strategies",
    "list_strategies",
    "list_v2_strategies",
    
    # Dicionários
    "AVAILABLE_STRATEGIES",
    "V2_STRATEGIES",
    "STRATEGY_NAMES",
]
