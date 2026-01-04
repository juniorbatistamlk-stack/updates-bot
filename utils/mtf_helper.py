"""
================================================================================
🔧 HELPER DE MULTI-TIMEFRAME PARA A IA
================================================================================
Funções simplificadas para integrar análise de S/R e Tendências com a IA

Uso:
    from utils.mtf_helper import get_complete_analysis
    
    result = get_complete_analysis(api, "EURUSD-OTC")
    print(result['prompt'])  # Contexto para a IA
    print(result['signal'])  # CALL, PUT ou NEUTRAL

================================================================================
"""

from typing import Dict, Optional, Any
from datetime import datetime

try:
    from utils.sr_zones_analyzer import (
        sr_analyzer, 
        get_sr_prompt_context,
        MultiTimeframeAnalysis
    )
except ImportError:
    sr_analyzer = None


def get_candles_multi_timeframe(api, pair: str, count_m5: int = 100) -> Dict[str, list]:
    """
    Busca candles de múltiplos timeframes de uma só vez
    
    Args:
        api: Instância da API (IQ Option)
        pair: Par de moedas
        count_m5: Quantidade de candles M5 (outros são proporcionais)
    
    Returns:
        Dict com candles de cada timeframe
    """
    candles_data = {}
    
    # Timeframes em segundos
    timeframes = {
        "M5": (300, count_m5),
        "M15": (900, max(50, count_m5 // 2)),
        "M30": (1800, max(40, count_m5 // 3)),
        "H1": (3600, max(30, count_m5 // 4))
    }
    
    for tf_name, (seconds, count) in timeframes.items():
        try:
            candles = api.get_candles(pair, seconds, count, time=None)
            if candles:
                candles_data[tf_name] = candles
        except Exception as e:
            print(f"⚠️ Erro ao buscar candles {tf_name}: {e}")
            candles_data[tf_name] = []
    
    return candles_data


def get_complete_analysis(api, pair: str, current_price: Optional[float] = None) -> Dict[str, Any]:
    """
    Análise completa de S/R e Tendências para um par
    
    Args:
        api: Instância da API
        pair: Par de moedas (ex: "EURUSD-OTC")
        current_price: Preço atual (se None, busca automaticamente)
    
    Returns:
        Dict com:
            - prompt: Texto para incluir no contexto da IA
            - signal: CALL, PUT ou NEUTRAL baseado na análise
            - confidence: 0-100 confiança no sinal
            - context: Dict completo com todos os dados
            - analysis: Objeto MultiTimeframeAnalysis
    """
    if sr_analyzer is None:
        return {
            'prompt': '[S/R Analyzer não disponível]',
            'signal': 'NEUTRAL',
            'confidence': 0,
            'context': {},
            'analysis': None
        }
    
    try:
        # Buscar candles
        candles_data = get_candles_multi_timeframe(api, pair)
        
        # Obter preço atual se não fornecido
        if current_price is None:
            if candles_data.get("M5"):
                current_price = candles_data["M5"][-1].get('close', 0)
            else:
                current_price = 0
        
        if current_price <= 0:
            return {
                'prompt': '[Preço inválido]',
                'signal': 'NEUTRAL',
                'confidence': 0,
                'context': {},
                'analysis': None
            }
        
        # Executar análise
        analysis = sr_analyzer.analyze(pair, candles_data, current_price)
        context = sr_analyzer.get_ai_context(analysis)
        prompt = get_sr_prompt_context(pair, candles_data, current_price)
        
        # Determinar sinal baseado na análise
        signal, confidence = _determine_signal(context, analysis)
        
        return {
            'prompt': prompt,
            'signal': signal,
            'confidence': confidence,
            'context': context,
            'analysis': analysis
        }
        
    except Exception as e:
        print(f"❌ Erro na análise MTF: {e}")
        return {
            'prompt': f'[Erro na análise: {str(e)}]',
            'signal': 'NEUTRAL',
            'confidence': 0,
            'context': {},
            'analysis': None
        }


def _determine_signal(context: Dict, analysis: MultiTimeframeAnalysis) -> tuple:
    """
    Determina sinal de trading baseado na análise de S/R
    
    Returns:
        (signal, confidence) - ex: ("CALL", 75)
    """
    signal = "NEUTRAL"
    confidence = 50
    
    # Fatores para CALL (compra)
    call_factors = 0
    # Fatores para PUT (venda)
    put_factors = 0
    
    # 1. Viés de tendência
    if context.get('trend_bias') == "BULLISH":
        call_factors += 2
    elif context.get('trend_bias') == "BEARISH":
        put_factors += 2
    
    # 2. Score de Suporte vs Resistência
    sup_score = context.get('support_score', 0)
    res_score = context.get('resistance_score', 0)
    
    if sup_score > res_score * 1.5:
        call_factors += 2  # Suporte forte próximo = favorece alta
    elif res_score > sup_score * 1.5:
        put_factors += 2  # Resistência forte próxima = favorece queda
    
    # 3. Proximidade de zonas importantes
    nearest_sup = context.get('nearest_support')
    nearest_res = context.get('nearest_resistance')
    
    if nearest_sup and nearest_sup.get('distance_pct', 100) < 0.1:
        # Muito próximo do suporte - pode bouncer
        if nearest_sup.get('strength', 0) >= 3:
            call_factors += 3
    
    if nearest_res and nearest_res.get('distance_pct', 100) < 0.1:
        # Muito próximo da resistência - pode rejeitar
        if nearest_res.get('strength', 0) >= 3:
            put_factors += 3
    
    # 4. Confluências
    for conf in context.get('confluences', []):
        if conf.get('score', 0) > 10:
            if conf.get('type') == 'support':
                call_factors += 1
            else:
                put_factors += 1
    
    # 5. Linhas de tendência ativas
    for tl in context.get('active_trendlines', []):
        if tl.get('type') == 'LTA':
            call_factors += 1
        elif tl.get('type') == 'LTB':
            put_factors += 1
    
    # Determinar sinal final
    total = call_factors + put_factors
    if total == 0:
        return "NEUTRAL", 50
    
    if call_factors > put_factors * 1.3:
        signal = "CALL"
        confidence = min(95, 50 + (call_factors - put_factors) * 10)
    elif put_factors > call_factors * 1.3:
        signal = "PUT"
        confidence = min(95, 50 + (put_factors - call_factors) * 10)
    else:
        signal = "NEUTRAL"
        confidence = 50
    
    return signal, int(confidence)


def get_sr_summary(api, pair: str) -> str:
    """
    Retorna um resumo simples de S/R para exibição rápida
    """
    result = get_complete_analysis(api, pair)
    
    if not result['context']:
        return "❓ Análise indisponível"
    
    ctx = result['context']
    
    lines = [
        f"📊 {pair}",
        f"Tendência: {ctx.get('trend_bias', 'N/A')}",
        f"Sup: {ctx.get('support_score', 0):.0f}% | Res: {ctx.get('resistance_score', 0):.0f}%"
    ]
    
    if ctx.get('nearest_support'):
        s = ctx['nearest_support']
        lines.append(f"🟢 Sup: {s['price']} ({s['distance_pct']:.2f}%)")
    
    if ctx.get('nearest_resistance'):
        r = ctx['nearest_resistance']
        lines.append(f"🔴 Res: {r['price']} ({r['distance_pct']:.2f}%)")
    
    lines.append(f"Sinal: {result['signal']} ({result['confidence']}%)")
    
    return "\n".join(lines)


def enhance_ai_prompt(original_prompt: str, api, pair: str) -> str:
    """
    Adiciona contexto de S/R ao prompt original da IA
    
    Uso:
        prompt = "Analise este candle..."
        enhanced = enhance_ai_prompt(prompt, api, "EURUSD")
    """
    result = get_complete_analysis(api, pair)
    
    enhanced = f"""
{original_prompt}

{result['prompt']}

IMPORTANTE: Use as informações de Suporte/Resistência acima para refinar sua análise.
- Se o preço está próximo de um suporte forte, considere CALL
- Se o preço está próximo de uma resistência forte, considere PUT
- Confluências multi-timeframe aumentam a confiabilidade
- Respeite as linhas de tendência (LTA favorece CALL, LTB favorece PUT)

Sinal sugerido pela análise S/R: {result['signal']} (Confiança: {result['confidence']}%)
"""
    
    return enhanced


# Classe para cache de análises
class MTFCache:
    """Cache para evitar análises repetidas"""
    
    def __init__(self, ttl_seconds: int = 60):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, pair: str) -> Optional[Dict]:
        if pair in self.cache:
            data, timestamp = self.cache[pair]
            if (datetime.now() - timestamp).total_seconds() < self.ttl:
                return data
            del self.cache[pair]
        return None
    
    def set(self, pair: str, data: Dict):
        self.cache[pair] = (data, datetime.now())
    
    def clear(self):
        self.cache.clear()


# Cache global
mtf_cache = MTFCache(ttl_seconds=60)


def get_cached_analysis(api, pair: str) -> Dict[str, Any]:
    """
    Versão com cache da análise completa
    """
    cached = mtf_cache.get(pair)
    if cached:
        return cached
    
    result = get_complete_analysis(api, pair)
    mtf_cache.set(pair, result)
    return result


if __name__ == "__main__":
    print("🔧 MTF Helper - Multi-Timeframe Analysis Helper")
    print("\nFunções disponíveis:")
    print("  - get_complete_analysis(api, pair)")
    print("  - get_sr_summary(api, pair)")
    print("  - enhance_ai_prompt(prompt, api, pair)")
    print("  - get_cached_analysis(api, pair)")
