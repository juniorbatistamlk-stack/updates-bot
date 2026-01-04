"""
================================================================================
📊 ANALISADOR DE SUPORTE, RESISTÊNCIA E LINHAS DE TENDÊNCIA
================================================================================
Módulo para detectar zonas de S/R e linhas de tendência em múltiplos timeframes
para auxiliar a IA nas decisões de trading.

Timeframes analisados: M5, M15, M30, H1
Técnicas: Pivots, Fractais, Regressão Linear, Confluência Multi-TF

Autor: Dark Black Bot
================================================================================
"""

import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


class ZoneType(Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


class TrendType(Enum):
    LTA = "LTA"  # Linha de Tendência de Alta
    LTB = "LTB"  # Linha de Tendência de Baixa


@dataclass
class SRZone:
    """Representa uma zona de Suporte ou Resistência"""
    price: float
    zone_type: ZoneType
    timeframe: str
    strength: int  # 1-5 (quantidade de toques)
    first_touch: datetime
    last_touch: datetime
    zone_width: float  # Largura da zona em preço
    broken: bool = False
    
    @property
    def zone_high(self) -> float:
        return self.price + self.zone_width / 2
    
    @property
    def zone_low(self) -> float:
        return self.price - self.zone_width / 2
    
    def is_price_in_zone(self, price: float) -> bool:
        return self.zone_low <= price <= self.zone_high


@dataclass
class TrendLine:
    """Representa uma Linha de Tendência (LTA ou LTB)"""
    trend_type: TrendType
    timeframe: str
    start_price: float
    end_price: float
    start_time: datetime
    end_time: datetime
    slope: float  # Inclinação
    strength: int  # Quantidade de toques
    valid: bool = True
    
    def get_price_at_time(self, target_time: datetime) -> float:
        """Calcula o preço da linha de tendência em um momento específico"""
        if self.end_time == self.start_time:
            return self.start_price
        
        time_ratio = (target_time - self.start_time).total_seconds() / \
                     (self.end_time - self.start_time).total_seconds()
        return self.start_price + (self.end_price - self.start_price) * time_ratio


@dataclass
class MultiTimeframeAnalysis:
    """Análise completa de múltiplos timeframes"""
    pair: str
    timestamp: datetime
    current_price: float
    
    # Zonas por timeframe
    zones_m5: List[SRZone] = field(default_factory=list)
    zones_m15: List[SRZone] = field(default_factory=list)
    zones_m30: List[SRZone] = field(default_factory=list)
    zones_h1: List[SRZone] = field(default_factory=list)
    
    # Linhas de tendência por timeframe
    trendlines_m5: List[TrendLine] = field(default_factory=list)
    trendlines_m15: List[TrendLine] = field(default_factory=list)
    trendlines_m30: List[TrendLine] = field(default_factory=list)
    trendlines_h1: List[TrendLine] = field(default_factory=list)
    
    # Confluências detectadas
    confluence_zones: List[Dict] = field(default_factory=list)
    
    # Scores
    support_score: float = 0.0
    resistance_score: float = 0.0
    trend_bias: str = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL


class SRZonesAnalyzer:
    """
    Analisador de Suporte, Resistência e Linhas de Tendência
    """
    
    # Pesos por timeframe (maior timeframe = maior peso)
    TIMEFRAME_WEIGHTS = {
        "M5": 1.0,
        "M15": 1.5,
        "M30": 2.0,
        "H1": 3.0
    }
    
    # Configurações de detecção
    PIVOT_LOOKBACK = {
        "M5": 5,
        "M15": 5,
        "M30": 4,
        "H1": 3
    }
    
    # Tolerância para zona (em % do preço)
    ZONE_TOLERANCE = {
        "M5": 0.0005,   # 0.05%
        "M15": 0.0008,  # 0.08%
        "M30": 0.0012,  # 0.12%
        "H1": 0.0020    # 0.20%
    }
    
    def __init__(self):
        self.cache = {}
        
    def analyze(self, pair: str, candles_data: Dict[str, List[Dict]], 
                current_price: float) -> MultiTimeframeAnalysis:
        """
        Análise completa de S/R e Linhas de Tendência
        
        Args:
            pair: Par de moedas (ex: "EURUSD")
            candles_data: Dict com candles por timeframe
                         {"M5": [...], "M15": [...], "M30": [...], "H1": [...]}
            current_price: Preço atual
            
        Returns:
            MultiTimeframeAnalysis com todas as zonas e linhas detectadas
        """
        analysis = MultiTimeframeAnalysis(
            pair=pair,
            timestamp=datetime.now(),
            current_price=current_price
        )
        
        # Analisar cada timeframe
        for tf, candles in candles_data.items():
            if not candles or len(candles) < 20:
                continue
                
            # Detectar zonas de S/R
            zones = self._detect_sr_zones(candles, tf, current_price)
            
            # Detectar linhas de tendência
            trendlines = self._detect_trendlines(candles, tf)
            
            # Atribuir às propriedades corretas
            if tf == "M5":
                analysis.zones_m5 = zones
                analysis.trendlines_m5 = trendlines
            elif tf == "M15":
                analysis.zones_m15 = zones
                analysis.trendlines_m15 = trendlines
            elif tf == "M30":
                analysis.zones_m30 = zones
                analysis.trendlines_m30 = trendlines
            elif tf == "H1":
                analysis.zones_h1 = zones
                analysis.trendlines_h1 = trendlines
        
        # Detectar confluências entre timeframes
        analysis.confluence_zones = self._detect_confluences(analysis, current_price)
        
        # Calcular scores
        analysis.support_score, analysis.resistance_score = \
            self._calculate_scores(analysis, current_price)
        
        # Determinar viés de tendência
        analysis.trend_bias = self._determine_trend_bias(analysis)
        
        return analysis
    
    def _detect_sr_zones(self, candles: List[Dict], timeframe: str, 
                         current_price: float) -> List[SRZone]:
        """Detecta zonas de Suporte e Resistência usando pivots e fractais"""
        zones = []
        lookback = self.PIVOT_LOOKBACK.get(timeframe, 5)
        tolerance = self.ZONE_TOLERANCE.get(timeframe, 0.001)
        
        # Extrair dados
        highs = np.array([c.get('max', c.get('high', 0)) for c in candles])
        lows = np.array([c.get('min', c.get('low', 0)) for c in candles])
        
        if len(highs) < lookback * 2 + 1:
            return zones
        
        # Detectar Pivot Highs (Resistências potenciais)
        pivot_highs = []
        for i in range(lookback, len(highs) - lookback):
            is_pivot = True
            for j in range(1, lookback + 1):
                if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                    is_pivot = False
                    break
            if is_pivot:
                pivot_highs.append({
                    'price': highs[i],
                    'index': i,
                    'time': candles[i].get('from', datetime.now())
                })
        
        # Detectar Pivot Lows (Suportes potenciais)
        pivot_lows = []
        for i in range(lookback, len(lows) - lookback):
            is_pivot = True
            for j in range(1, lookback + 1):
                if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                    is_pivot = False
                    break
            if is_pivot:
                pivot_lows.append({
                    'price': lows[i],
                    'index': i,
                    'time': candles[i].get('from', datetime.now())
                })
        
        # Agrupar pivots próximos em zonas (Resistências)
        resistance_zones = self._cluster_pivots(pivot_highs, tolerance, current_price)
        for zone_data in resistance_zones:
            zone = SRZone(
                price=zone_data['price'],
                zone_type=ZoneType.RESISTANCE,
                timeframe=timeframe,
                strength=zone_data['touches'],
                first_touch=zone_data['first_touch'],
                last_touch=zone_data['last_touch'],
                zone_width=zone_data['width'],
                broken=zone_data['price'] < current_price
            )
            zones.append(zone)
        
        # Agrupar pivots próximos em zonas (Suportes)
        support_zones = self._cluster_pivots(pivot_lows, tolerance, current_price)
        for zone_data in support_zones:
            zone = SRZone(
                price=zone_data['price'],
                zone_type=ZoneType.SUPPORT,
                timeframe=timeframe,
                strength=zone_data['touches'],
                first_touch=zone_data['first_touch'],
                last_touch=zone_data['last_touch'],
                zone_width=zone_data['width'],
                broken=zone_data['price'] > current_price
            )
            zones.append(zone)
        
        # Ordenar por força
        zones.sort(key=lambda z: z.strength, reverse=True)
        
        return zones[:10]  # Top 10 zonas
    
    def _cluster_pivots(self, pivots: List[Dict], tolerance: float, 
                        current_price: float) -> List[Dict]:
        """Agrupa pivots próximos em zonas"""
        if not pivots:
            return []
        
        # Ordenar por preço
        pivots_sorted = sorted(pivots, key=lambda p: p['price'])
        clusters = []
        current_cluster = [pivots_sorted[0]]
        
        for pivot in pivots_sorted[1:]:
            # Se está dentro da tolerância, adiciona ao cluster atual
            if abs(pivot['price'] - current_cluster[-1]['price']) / current_price <= tolerance:
                current_cluster.append(pivot)
            else:
                # Finaliza cluster atual e inicia novo
                if current_cluster:
                    clusters.append(current_cluster)
                current_cluster = [pivot]
        
        if current_cluster:
            clusters.append(current_cluster)
        
        # Converter clusters em zonas
        zones = []
        for cluster in clusters:
            if len(cluster) >= 2:  # Mínimo 2 toques para ser válido
                prices = [p['price'] for p in cluster]
                times = [p['time'] for p in cluster]
                
                # Converter times para datetime se necessário
                parsed_times = []
                for t in times:
                    if isinstance(t, datetime):
                        parsed_times.append(t)
                    elif isinstance(t, (int, float)):
                        parsed_times.append(datetime.fromtimestamp(t))
                    else:
                        parsed_times.append(datetime.now())
                
                zones.append({
                    'price': np.mean(prices),
                    'touches': len(cluster),
                    'first_touch': min(parsed_times) if parsed_times else datetime.now(),
                    'last_touch': max(parsed_times) if parsed_times else datetime.now(),
                    'width': max(prices) - min(prices) if len(prices) > 1 else current_price * tolerance
                })
        
        return zones
    
    def _detect_trendlines(self, candles: List[Dict], timeframe: str) -> List[TrendLine]:
        """Detecta Linhas de Tendência de Alta (LTA) e Baixa (LTB)"""
        trendlines = []
        
        if len(candles) < 20:
            return trendlines
        
        # Extrair dados
        highs = np.array([c.get('max', c.get('high', 0)) for c in candles])
        lows = np.array([c.get('min', c.get('low', 0)) for c in candles])
        
        # Detectar LTA (conectando mínimos ascendentes)
        lta = self._find_best_trendline(candles, lows, TrendType.LTA, timeframe)
        if lta:
            trendlines.append(lta)
        
        # Detectar LTB (conectando máximos descendentes)
        ltb = self._find_best_trendline(candles, highs, TrendType.LTB, timeframe)
        if ltb:
            trendlines.append(ltb)
        
        return trendlines
    
    def _find_best_trendline(self, candles: List[Dict], prices: np.ndarray, 
                             trend_type: TrendType, timeframe: str) -> Optional[TrendLine]:
        """Encontra a melhor linha de tendência usando regressão e validação"""
        n = len(prices)
        if n < 10:
            return None
        
        best_line = None
        best_touches = 0
        
        # Tentar diferentes combinações de pontos
        lookback = min(50, n)
        
        for i in range(lookback - 5):
            for j in range(i + 5, lookback):
                # Calcular linha entre ponto i e j
                p1, p2 = prices[n - lookback + i], prices[n - lookback + j]
                
                # Verificar direção correta
                if trend_type == TrendType.LTA and p2 <= p1:
                    continue  # LTA deve ser ascendente
                if trend_type == TrendType.LTB and p2 >= p1:
                    continue  # LTB deve ser descendente
                
                # Calcular inclinação
                slope = (p2 - p1) / (j - i)
                
                # Contar toques na linha
                touches = 0
                tolerance = abs(p2 - p1) * 0.02  # 2% de tolerância
                
                for k in range(i, j + 1):
                    expected = p1 + slope * (k - i)
                    actual = prices[n - lookback + k]
                    
                    if trend_type == TrendType.LTA:
                        # Para LTA, preço deve estar acima ou tocando a linha
                        if abs(actual - expected) <= tolerance or actual >= expected:
                            if abs(actual - expected) <= tolerance:
                                touches += 1
                    else:
                        # Para LTB, preço deve estar abaixo ou tocando a linha
                        if abs(actual - expected) <= tolerance or actual <= expected:
                            if abs(actual - expected) <= tolerance:
                                touches += 1
                
                # Validar se a linha ainda é válida
                valid = True
                for k in range(j + 1, lookback):
                    expected = p1 + slope * (k - i)
                    actual = prices[n - lookback + k]
                    
                    if trend_type == TrendType.LTA and actual < expected - tolerance * 2:
                        valid = False
                        break
                    if trend_type == TrendType.LTB and actual > expected + tolerance * 2:
                        valid = False
                        break
                
                # Atualizar melhor linha
                if touches > best_touches and touches >= 3:
                    time1 = candles[n - lookback + i].get('from', datetime.now())
                    time2 = candles[n - lookback + j].get('from', datetime.now())
                    
                    # Converter para datetime
                    if isinstance(time1, (int, float)):
                        time1 = datetime.fromtimestamp(time1)
                    if isinstance(time2, (int, float)):
                        time2 = datetime.fromtimestamp(time2)
                    
                    best_line = TrendLine(
                        trend_type=trend_type,
                        timeframe=timeframe,
                        start_price=p1,
                        end_price=p2,
                        start_time=time1,
                        end_time=time2,
                        slope=slope,
                        strength=touches,
                        valid=valid
                    )
                    best_touches = touches
        
        return best_line
    
    def _detect_confluences(self, analysis: MultiTimeframeAnalysis, 
                           current_price: float) -> List[Dict]:
        """Detecta confluências entre diferentes timeframes"""
        confluences = []
        
        # Coletar todas as zonas
        all_zones = []
        for zones, tf in [
            (analysis.zones_m5, "M5"),
            (analysis.zones_m15, "M15"),
            (analysis.zones_m30, "M30"),
            (analysis.zones_h1, "H1")
        ]:
            for zone in zones:
                all_zones.append(zone)
        
        # Agrupar zonas próximas de diferentes timeframes
        tolerance = current_price * 0.002  # 0.2%
        processed = set()
        
        for i, zone1 in enumerate(all_zones):
            if i in processed:
                continue
            
            confluence_group = [zone1]
            timeframes = {zone1.timeframe}
            
            for j, zone2 in enumerate(all_zones):
                if i == j or j in processed:
                    continue
                
                # Verificar se estão próximas
                if abs(zone1.price - zone2.price) <= tolerance:
                    if zone2.timeframe not in timeframes:
                        confluence_group.append(zone2)
                        timeframes.add(zone2.timeframe)
                        processed.add(j)
            
            # Se temos confluência de múltiplos timeframes
            if len(timeframes) >= 2:
                # Calcular score da confluência
                score = sum(
                    self.TIMEFRAME_WEIGHTS.get(z.timeframe, 1) * z.strength 
                    for z in confluence_group
                )
                
                avg_price = np.mean([z.price for z in confluence_group])
                
                confluences.append({
                    'price': avg_price,
                    'type': confluence_group[0].zone_type.value,
                    'timeframes': list(timeframes),
                    'total_touches': sum(z.strength for z in confluence_group),
                    'score': score,
                    'distance_pct': abs(avg_price - current_price) / current_price * 100
                })
            
            processed.add(i)
        
        # Ordenar por score
        confluences.sort(key=lambda c: c['score'], reverse=True)
        
        return confluences[:5]  # Top 5 confluências
    
    def _calculate_scores(self, analysis: MultiTimeframeAnalysis, 
                         current_price: float) -> Tuple[float, float]:
        """Calcula scores de suporte e resistência baseado na proximidade e força"""
        support_score = 0.0
        resistance_score = 0.0
        
        # Proximidade máxima para considerar (1%)
        max_distance = current_price * 0.01
        
        all_zones = (
            analysis.zones_m5 + analysis.zones_m15 + 
            analysis.zones_m30 + analysis.zones_h1
        )
        
        for zone in all_zones:
            distance = abs(zone.price - current_price)
            
            if distance > max_distance:
                continue
            
            # Score baseado na proximidade e força
            proximity_factor = 1 - (distance / max_distance)
            weight = self.TIMEFRAME_WEIGHTS.get(zone.timeframe, 1)
            zone_score = proximity_factor * zone.strength * weight
            
            if zone.zone_type == ZoneType.SUPPORT and zone.price < current_price:
                support_score += zone_score
            elif zone.zone_type == ZoneType.RESISTANCE and zone.price > current_price:
                resistance_score += zone_score
        
        # Normalizar para 0-100
        max_possible = 5 * 3 * 4  # max strength * max weight * 4 timeframes
        support_score = min(100, (support_score / max_possible) * 100)
        resistance_score = min(100, (resistance_score / max_possible) * 100)
        
        return round(support_score, 2), round(resistance_score, 2)
    
    def _determine_trend_bias(self, analysis: MultiTimeframeAnalysis) -> str:
        """Determina o viés de tendência baseado nas linhas de tendência"""
        bullish_count = 0
        bearish_count = 0
        
        all_trendlines = (
            analysis.trendlines_m5 + analysis.trendlines_m15 + 
            analysis.trendlines_m30 + analysis.trendlines_h1
        )
        
        for tl in all_trendlines:
            if not tl.valid:
                continue
            
            weight = self.TIMEFRAME_WEIGHTS.get(tl.timeframe, 1)
            
            if tl.trend_type == TrendType.LTA:
                bullish_count += weight * tl.strength
            else:
                bearish_count += weight * tl.strength
        
        if bullish_count > bearish_count * 1.2:
            return "BULLISH"
        elif bearish_count > bullish_count * 1.2:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def get_ai_context(self, analysis: MultiTimeframeAnalysis) -> Dict:
        """
        Retorna contexto formatado para a IA usar na análise
        """
        context = {
            'pair': analysis.pair,
            'current_price': analysis.current_price,
            'trend_bias': analysis.trend_bias,
            'support_score': analysis.support_score,
            'resistance_score': analysis.resistance_score,
            'nearest_support': None,
            'nearest_resistance': None,
            'confluences': [],
            'active_trendlines': [],
            'recommendation': ""
        }
        
        # Encontrar suporte e resistência mais próximos
        all_zones = (
            analysis.zones_m5 + analysis.zones_m15 + 
            analysis.zones_m30 + analysis.zones_h1
        )
        
        supports = [z for z in all_zones if z.zone_type == ZoneType.SUPPORT 
                   and z.price < analysis.current_price and not z.broken]
        resistances = [z for z in all_zones if z.zone_type == ZoneType.RESISTANCE 
                      and z.price > analysis.current_price and not z.broken]
        
        if supports:
            nearest_sup = max(supports, key=lambda z: z.price)
            context['nearest_support'] = {
                'price': round(nearest_sup.price, 5),
                'timeframe': nearest_sup.timeframe,
                'strength': nearest_sup.strength,
                'distance_pct': round(abs(nearest_sup.price - analysis.current_price) 
                                     / analysis.current_price * 100, 3)
            }
        
        if resistances:
            nearest_res = min(resistances, key=lambda z: z.price)
            context['nearest_resistance'] = {
                'price': round(nearest_res.price, 5),
                'timeframe': nearest_res.timeframe,
                'strength': nearest_res.strength,
                'distance_pct': round(abs(nearest_res.price - analysis.current_price) 
                                     / analysis.current_price * 100, 3)
            }
        
        # Confluências
        for conf in analysis.confluence_zones[:3]:
            context['confluences'].append({
                'price': round(conf['price'], 5),
                'type': conf['type'],
                'timeframes': conf['timeframes'],
                'score': round(conf['score'], 2)
            })
        
        # Linhas de tendência ativas
        all_trendlines = (
            analysis.trendlines_m5 + analysis.trendlines_m15 + 
            analysis.trendlines_m30 + analysis.trendlines_h1
        )
        
        for tl in all_trendlines:
            if tl.valid:
                context['active_trendlines'].append({
                    'type': tl.trend_type.value,
                    'timeframe': tl.timeframe,
                    'strength': tl.strength,
                    'slope': 'ascending' if tl.slope > 0 else 'descending'
                })
        
        # Gerar recomendação
        context['recommendation'] = self._generate_recommendation(context)
        
        return context
    
    def _generate_recommendation(self, context: Dict) -> str:
        """Gera recomendação baseada na análise"""
        recommendations = []
        
        # Análise de tendência
        if context['trend_bias'] == "BULLISH":
            recommendations.append("📈 Tendência de ALTA detectada")
        elif context['trend_bias'] == "BEARISH":
            recommendations.append("📉 Tendência de BAIXA detectada")
        else:
            recommendations.append("↔️ Mercado LATERAL")
        
        # Análise de S/R
        if context['support_score'] > 70:
            recommendations.append("🟢 Suporte FORTE próximo - Favorece CALL")
        elif context['resistance_score'] > 70:
            recommendations.append("🔴 Resistência FORTE próxima - Favorece PUT")
        
        # Confluências
        if context['confluences']:
            best_conf = context['confluences'][0]
            if best_conf['type'] == 'support':
                recommendations.append(f"⭐ Confluência de SUPORTE em {best_conf['price']} "
                                      f"({', '.join(best_conf['timeframes'])})")
            else:
                recommendations.append(f"⭐ Confluência de RESISTÊNCIA em {best_conf['price']} "
                                      f"({', '.join(best_conf['timeframes'])})")
        
        # Posição relativa
        if context['nearest_support'] and context['nearest_resistance']:
            sup_dist = context['nearest_support']['distance_pct']
            res_dist = context['nearest_resistance']['distance_pct']
            
            if sup_dist < res_dist * 0.5:
                recommendations.append("⚠️ Preço MUITO PRÓXIMO do suporte - Aguardar confirmação")
            elif res_dist < sup_dist * 0.5:
                recommendations.append("⚠️ Preço MUITO PRÓXIMO da resistência - Aguardar confirmação")
        
        return " | ".join(recommendations)
    
    def format_for_display(self, analysis: MultiTimeframeAnalysis) -> str:
        """Formata a análise para exibição no console"""
        lines = [
            "",
            "═" * 60,
            "📊 ANÁLISE DE SUPORTE, RESISTÊNCIA E TENDÊNCIA",
            "═" * 60,
            f"Par: {analysis.pair} | Preço: {analysis.current_price}",
            f"Viés: {analysis.trend_bias}",
            f"Score Suporte: {analysis.support_score} | Score Resistência: {analysis.resistance_score}",
            "",
            "─" * 60,
            "🎯 ZONAS DE S/R POR TIMEFRAME:",
            "─" * 60,
        ]
        
        for tf, zones in [
            ("M5", analysis.zones_m5),
            ("M15", analysis.zones_m15),
            ("M30", analysis.zones_m30),
            ("H1", analysis.zones_h1)
        ]:
            if zones:
                lines.append(f"\n  [{tf}]")
                for z in zones[:3]:
                    status = "✅" if not z.broken else "❌"
                    lines.append(f"    {status} {z.zone_type.value.upper()}: {z.price:.5f} "
                               f"(Força: {z.strength})")
        
        lines.append("")
        lines.append("─" * 60)
        lines.append("📐 LINHAS DE TENDÊNCIA:")
        lines.append("─" * 60)
        
        all_trendlines = (
            analysis.trendlines_m5 + analysis.trendlines_m15 + 
            analysis.trendlines_m30 + analysis.trendlines_h1
        )
        
        for tl in all_trendlines:
            status = "✅" if tl.valid else "❌"
            emoji = "📈" if tl.trend_type == TrendType.LTA else "📉"
            lines.append(f"  {status} {emoji} {tl.trend_type.value} [{tl.timeframe}] "
                        f"- Toques: {tl.strength}")
        
        if analysis.confluence_zones:
            lines.append("")
            lines.append("─" * 60)
            lines.append("⭐ CONFLUÊNCIAS MULTI-TIMEFRAME:")
            lines.append("─" * 60)
            
            for conf in analysis.confluence_zones:
                lines.append(f"  • {conf['type'].upper()} @ {conf['price']:.5f}")
                lines.append(f"    Timeframes: {', '.join(conf['timeframes'])}")
                lines.append(f"    Score: {conf['score']:.1f} | Distância: {conf['distance_pct']:.2f}%")
        
        lines.append("")
        lines.append("═" * 60)
        
        return "\n".join(lines)


# Instância global para uso fácil
sr_analyzer = SRZonesAnalyzer()


def analyze_sr_zones(pair: str, candles_data: Dict[str, List[Dict]], 
                     current_price: float) -> Dict:
    """
    Função helper para análise rápida
    
    Exemplo de uso:
        candles_data = {
            "M5": api.get_candles(pair, 300, 100),
            "M15": api.get_candles(pair, 900, 50),
            "M30": api.get_candles(pair, 1800, 40),
            "H1": api.get_candles(pair, 3600, 30)
        }
        result = analyze_sr_zones("EURUSD", candles_data, current_price)
    """
    analysis = sr_analyzer.analyze(pair, candles_data, current_price)
    return sr_analyzer.get_ai_context(analysis)


# Exemplo de integração com a IA
def get_sr_prompt_context(pair: str, candles_data: Dict[str, List[Dict]], 
                          current_price: float) -> str:
    """
    Retorna contexto formatado para incluir no prompt da IA
    """
    context = analyze_sr_zones(pair, candles_data, current_price)
    
    prompt_parts = [
        f"\n=== ANÁLISE DE SUPORTE/RESISTÊNCIA ({pair}) ===",
        f"Preço Atual: {context['current_price']}",
        f"Viés de Tendência: {context['trend_bias']}",
        f"Score Suporte: {context['support_score']}/100",
        f"Score Resistência: {context['resistance_score']}/100",
    ]
    
    if context['nearest_support']:
        s = context['nearest_support']
        prompt_parts.append(f"Suporte Mais Próximo: {s['price']} ({s['timeframe']}, "
                           f"força {s['strength']}, distância {s['distance_pct']}%)")
    
    if context['nearest_resistance']:
        r = context['nearest_resistance']
        prompt_parts.append(f"Resistência Mais Próxima: {r['price']} ({r['timeframe']}, "
                           f"força {r['strength']}, distância {r['distance_pct']}%)")
    
    if context['confluences']:
        prompt_parts.append("\nConfluências Importantes:")
        for c in context['confluences']:
            prompt_parts.append(f"  - {c['type'].upper()} @ {c['price']} "
                              f"[{', '.join(c['timeframes'])}] score={c['score']}")
    
    if context['active_trendlines']:
        prompt_parts.append("\nLinhas de Tendência Ativas:")
        for tl in context['active_trendlines']:
            prompt_parts.append(f"  - {tl['type']} ({tl['timeframe']}) - "
                              f"força {tl['strength']}")
    
    prompt_parts.append(f"\nRecomendação: {context['recommendation']}")
    prompt_parts.append("=" * 50)
    
    return "\n".join(prompt_parts)


if __name__ == "__main__":
    # Teste básico
    print("📊 Módulo de Análise de S/R e Linhas de Tendência")
    print("Use: from utils.sr_zones_analyzer import analyze_sr_zones, get_sr_prompt_context")
