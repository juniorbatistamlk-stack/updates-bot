"""
================================================================================
📈 ANALISADOR DE MOVIMENTAÇÃO DO GRÁFICO - MICRO E MACRO
================================================================================
Analisa a movimentação do preço em duas escalas:
- MICRO: Últimos 5-15 candles (momentum imediato)
- MACRO: Últimos 30-100 candles (tendência geral)

Detecta:
- Velocidade do preço (quão rápido está se movendo)
- Aceleração (o movimento está aumentando ou diminuindo?)
- Divergência Micro/Macro (sinais de reversão)
- Força do movimento (momentum)
- Padrões de impulso, correção e consolidação

Autor: Dark Black Bot
================================================================================
"""

import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class MovementType(Enum):
    """Tipo de movimento detectado"""
    IMPULSO_ALTA = "impulso_alta"      # Movimento forte de alta
    IMPULSO_BAIXA = "impulso_baixa"    # Movimento forte de baixa
    CORRECAO_ALTA = "correcao_alta"    # Correção dentro de tendência de alta
    CORRECAO_BAIXA = "correcao_baixa"  # Correção dentro de tendência de baixa
    CONSOLIDACAO = "consolidacao"       # Mercado lateralizado
    ACELERANDO = "acelerando"          # Movimento ganhando força
    DESACELERANDO = "desacelerando"    # Movimento perdendo força
    REVERSAO = "reversao"              # Possível reversão


class TrendDirection(Enum):
    """Direção da tendência"""
    ALTA = "alta"
    BAIXA = "baixa"
    LATERAL = "lateral"


@dataclass
class MicroAnalysis:
    """Análise da movimentação MICRO (curto prazo)"""
    direction: TrendDirection
    velocity: float          # Velocidade do preço (pips/candle)
    acceleration: float      # Aceleração (mudança na velocidade)
    momentum: float          # Força do movimento (0-100)
    volatility: float        # Volatilidade recente
    candles_analyzed: int
    consecutive_direction: int  # Candles consecutivos na mesma direção
    last_candle_strength: float  # Força do último candle (0-100)
    movement_type: MovementType
    
    # Padrões detectados
    is_doji: bool = False
    is_engulfing: bool = False
    is_pin_bar: bool = False
    has_long_wick: bool = False


@dataclass  
class MacroAnalysis:
    """Análise da movimentação MACRO (longo prazo)"""
    direction: TrendDirection
    trend_strength: float     # Força da tendência (0-100)
    avg_velocity: float       # Velocidade média
    trend_age: int           # Há quantos candles a tendência começou
    higher_highs: int        # Quantidade de topos mais altos
    lower_lows: int          # Quantidade de fundos mais baixos
    trend_line_slope: float  # Inclinação da linha de tendência
    retracements: int        # Quantidade de correções
    movement_type: MovementType
    
    # Médias móveis
    price_vs_ma20: str       # "above", "below", "crossing"
    price_vs_ma50: str
    ma_alignment: str        # "bullish", "bearish", "mixed"


@dataclass
class MovementAnalysis:
    """Análise completa de movimentação Micro + Macro"""
    pair: str
    timestamp: datetime
    current_price: float
    
    # Análises
    micro: MicroAnalysis
    macro: MacroAnalysis
    
    # Divergência
    has_divergence: bool = False
    divergence_type: str = ""  # "bullish", "bearish"
    divergence_strength: float = 0.0
    
    # Scores finais
    bullish_score: float = 0.0  # 0-100 - probabilidade de alta
    bearish_score: float = 0.0  # 0-100 - probabilidade de baixa
    
    # Recomendação
    signal_bias: str = "NEUTRAL"  # CALL, PUT, NEUTRAL
    confidence: float = 50.0
    reasoning: str = ""


class PriceMovementAnalyzer:
    """
    Analisador de Movimentação de Preço - Micro e Macro
    """
    
    # Configurações
    MICRO_CANDLES = 10    # Candles para análise micro
    MACRO_CANDLES = 50    # Candles para análise macro
    
    def __init__(self):
        self.cache = {}
    
    def analyze(self, pair: str, candles: List[Dict], 
                current_price: Optional[float] = None) -> MovementAnalysis:
        """
        Análise completa de movimentação Micro e Macro
        
        Args:
            pair: Par de moedas
            candles: Lista de candles (mínimo 50 recomendado)
            current_price: Preço atual (se None, usa último close)
        
        Returns:
            MovementAnalysis com análise completa
        """
        if not candles or len(candles) < 20:
            return self._empty_analysis(pair, current_price or 0)
        
        # Extrair dados
        opens = np.array([c.get('open', 0) for c in candles])
        highs = np.array([c.get('max', c.get('high', 0)) for c in candles])
        lows = np.array([c.get('min', c.get('low', 0)) for c in candles])
        closes = np.array([c.get('close', 0) for c in candles])
        
        if current_price is None:
            current_price = closes[-1]
        
        # Análise MICRO (últimos N candles)
        micro = self._analyze_micro(opens, highs, lows, closes)
        
        # Análise MACRO (todos os candles disponíveis)
        macro = self._analyze_macro(opens, highs, lows, closes)
        
        # Detectar divergência
        has_div, div_type, div_strength = self._detect_divergence(micro, macro)
        
        # Calcular scores
        bullish, bearish = self._calculate_scores(micro, macro, has_div, div_type)
        
        # Determinar sinal
        signal, confidence, reasoning = self._determine_signal(
            micro, macro, bullish, bearish, has_div, div_type
        )
        
        return MovementAnalysis(
            pair=pair,
            timestamp=datetime.now(),
            current_price=current_price,
            micro=micro,
            macro=macro,
            has_divergence=has_div,
            divergence_type=div_type,
            divergence_strength=div_strength,
            bullish_score=bullish,
            bearish_score=bearish,
            signal_bias=signal,
            confidence=confidence,
            reasoning=reasoning
        )
    
    def _analyze_micro(self, opens: np.ndarray, highs: np.ndarray, 
                       lows: np.ndarray, closes: np.ndarray) -> MicroAnalysis:
        """Análise MICRO - Momentum imediato"""
        n = min(self.MICRO_CANDLES, len(closes))
        
        # Pegar últimos N candles
        o, h, lows, c = opens[-n:], highs[-n:], lows[-n:], closes[-n:]
        
        # 1. Velocidade do preço (variação média por candle)
        price_changes = np.diff(c)
        velocity = np.mean(price_changes) if len(price_changes) > 0 else 0
        
        # 2. Aceleração (mudança na velocidade)
        if len(price_changes) >= 2:
            first_half = np.mean(price_changes[:len(price_changes)//2])
            second_half = np.mean(price_changes[len(price_changes)//2:])
            acceleration = second_half - first_half
        else:
            acceleration = 0
        
        # 3. Momentum (força do movimento)
        total_move = c[-1] - c[0] if len(c) > 1 else 0
        total_range = np.sum(h - lows)
        momentum = abs(total_move) / max(total_range, 0.0001) * 100
        momentum = min(100, momentum)
        
        # 4. Volatilidade
        volatility = np.std(price_changes) if len(price_changes) > 0 else 0
        
        # 5. Direção
        if velocity > 0.00001:
            direction = TrendDirection.ALTA
        elif velocity < -0.00001:
            direction = TrendDirection.BAIXA
        else:
            direction = TrendDirection.LATERAL
        
        # 6. Candles consecutivos na mesma direção
        consecutive = 1
        for i in range(len(c) - 2, -1, -1):
            if (c[i+1] > c[i] and direction == TrendDirection.ALTA) or \
               (c[i+1] < c[i] and direction == TrendDirection.BAIXA):
                consecutive += 1
            else:
                break
        
        # 7. Força do último candle
        last_body = abs(c[-1] - o[-1])
        last_range = h[-1] - lows[-1]
        last_strength = (last_body / max(last_range, 0.0001)) * 100 if last_range > 0 else 0
        
        # 8. Detectar padrões no último candle
        is_doji = last_body < last_range * 0.1
        
        # Pin bar (pavio longo)
        upper_wick = h[-1] - max(o[-1], c[-1])
        lower_wick = min(o[-1], c[-1]) - lows[-1]
        is_pin_bar = (upper_wick > last_body * 2) or (lower_wick > last_body * 2)
        has_long_wick = upper_wick > last_range * 0.4 or lower_wick > last_range * 0.4
        
        # Engulfing (último candle engolfa o anterior)
        is_engulfing = False
        if len(c) >= 2:
            prev_body = abs(c[-2] - o[-2])
            is_engulfing = last_body > prev_body * 1.5 and \
                          ((c[-1] > o[-1] and c[-2] < o[-2]) or \
                           (c[-1] < o[-1] and c[-2] > o[-2]))
        
        # 9. Tipo de movimento
        movement_type = self._classify_micro_movement(
            velocity, acceleration, momentum, consecutive, is_doji
        )
        
        return MicroAnalysis(
            direction=direction,
            velocity=velocity,
            acceleration=acceleration,
            momentum=momentum,
            volatility=volatility,
            candles_analyzed=n,
            consecutive_direction=consecutive,
            last_candle_strength=last_strength,
            movement_type=movement_type,
            is_doji=is_doji,
            is_engulfing=is_engulfing,
            is_pin_bar=is_pin_bar,
            has_long_wick=has_long_wick
        )
    
    def _analyze_macro(self, opens: np.ndarray, highs: np.ndarray,
                       lows: np.ndarray, closes: np.ndarray) -> MacroAnalysis:
        """Análise MACRO - Tendência geral"""
        n = min(self.MACRO_CANDLES, len(closes))
        
        _, h, lows, c = opens[-n:], highs[-n:], lows[-n:], closes[-n:]
        
        # 1. Calcular médias móveis
        ma20 = np.mean(c[-20:]) if len(c) >= 20 else np.mean(c)
        ma50 = np.mean(c[-50:]) if len(c) >= 50 else np.mean(c)
        
        current = c[-1]
        
        # Posição do preço vs MAs
        price_vs_ma20 = "above" if current > ma20 else "below" if current < ma20 else "at"
        price_vs_ma50 = "above" if current > ma50 else "below" if current < ma50 else "at"
        
        # Alinhamento das MAs
        if ma20 > ma50 and current > ma20:
            ma_alignment = "bullish"
        elif ma20 < ma50 and current < ma20:
            ma_alignment = "bearish"
        else:
            ma_alignment = "mixed"
        
        # 2. Direção da tendência
        first_third = np.mean(c[:n//3])
        last_third = np.mean(c[-n//3:])
        
        trend_change = (last_third - first_third) / first_third * 100
        
        if trend_change > 0.1:
            direction = TrendDirection.ALTA
        elif trend_change < -0.1:
            direction = TrendDirection.BAIXA
        else:
            direction = TrendDirection.LATERAL
        
        # 3. Força da tendência
        # Usando ADX simplificado
        price_changes = np.abs(np.diff(c))
        directional_move = abs(c[-1] - c[0])
        total_move = np.sum(price_changes)
        trend_strength = (directional_move / max(total_move, 0.0001)) * 100
        trend_strength = min(100, trend_strength)
        
        # 4. Velocidade média
        avg_velocity = np.mean(np.diff(c))
        
        # 5. Contar Higher Highs e Lower Lows
        higher_highs = 0
        lower_lows = 0
        
        for i in range(5, len(h)):
            if h[i] > np.max(h[max(0, i-5):i]):
                higher_highs += 1
            if lows[i] < np.min(lows[max(0, i-5):i]):
                lower_lows += 1
        
        # 6. Idade da tendência (desde última reversão)
        trend_age = self._calculate_trend_age(c, direction)
        
        # 7. Inclinação da linha de tendência (regressão linear)
        x = np.arange(len(c))
        slope, _ = np.polyfit(x, c, 1) if len(c) > 1 else (0, 0)
        
        # 8. Contar retracements (correções)
        retracements = self._count_retracements(c, direction)
        
        # 9. Tipo de movimento
        movement_type = self._classify_macro_movement(
            direction, trend_strength, higher_highs, lower_lows, retracements
        )
        
        return MacroAnalysis(
            direction=direction,
            trend_strength=trend_strength,
            avg_velocity=avg_velocity,
            trend_age=trend_age,
            higher_highs=higher_highs,
            lower_lows=lower_lows,
            trend_line_slope=slope,
            retracements=retracements,
            movement_type=movement_type,
            price_vs_ma20=price_vs_ma20,
            price_vs_ma50=price_vs_ma50,
            ma_alignment=ma_alignment
        )
    
    def _classify_micro_movement(self, velocity: float, acceleration: float,
                                  momentum: float, consecutive: int, 
                                  is_doji: bool) -> MovementType:
        """Classifica o tipo de movimento micro"""
        if is_doji:
            return MovementType.CONSOLIDACAO
        
        if acceleration > 0 and momentum > 50:
            return MovementType.ACELERANDO
        elif acceleration < 0 and momentum < 30:
            return MovementType.DESACELERANDO
        
        if consecutive >= 4 and momentum > 60:
            if velocity > 0:
                return MovementType.IMPULSO_ALTA
            else:
                return MovementType.IMPULSO_BAIXA
        
        if momentum < 20:
            return MovementType.CONSOLIDACAO
        
        if velocity > 0:
            return MovementType.CORRECAO_BAIXA if acceleration < 0 else MovementType.IMPULSO_ALTA
        else:
            return MovementType.CORRECAO_ALTA if acceleration > 0 else MovementType.IMPULSO_BAIXA
    
    def _classify_macro_movement(self, direction: TrendDirection, 
                                  trend_strength: float, higher_highs: int,
                                  lower_lows: int, retracements: int) -> MovementType:
        """Classifica o tipo de movimento macro"""
        if trend_strength < 20:
            return MovementType.CONSOLIDACAO
        
        if direction == TrendDirection.ALTA:
            if higher_highs > lower_lows * 2 and trend_strength > 50:
                return MovementType.IMPULSO_ALTA
            elif retracements > 3:
                return MovementType.CORRECAO_BAIXA
            else:
                return MovementType.IMPULSO_ALTA
        
        elif direction == TrendDirection.BAIXA:
            if lower_lows > higher_highs * 2 and trend_strength > 50:
                return MovementType.IMPULSO_BAIXA
            elif retracements > 3:
                return MovementType.CORRECAO_ALTA
            else:
                return MovementType.IMPULSO_BAIXA
        
        return MovementType.CONSOLIDACAO
    
    def _calculate_trend_age(self, closes: np.ndarray, 
                             direction: TrendDirection) -> int:
        """Calcula há quantos candles a tendência começou"""
        if len(closes) < 3:
            return 0
        
        age = 0
        for i in range(len(closes) - 2, -1, -1):
            if direction == TrendDirection.ALTA:
                if closes[i+1] >= closes[i]:
                    age += 1
                else:
                    break
            elif direction == TrendDirection.BAIXA:
                if closes[i+1] <= closes[i]:
                    age += 1
                else:
                    break
            else:
                break
        
        return age
    
    def _count_retracements(self, closes: np.ndarray, 
                            direction: TrendDirection) -> int:
        """Conta quantas correções ocorreram"""
        if len(closes) < 5:
            return 0
        
        retracements = 0
        in_retracement = False
        
        for i in range(1, len(closes)):
            if direction == TrendDirection.ALTA:
                if closes[i] < closes[i-1]:
                    if not in_retracement:
                        retracements += 1
                        in_retracement = True
                else:
                    in_retracement = False
            elif direction == TrendDirection.BAIXA:
                if closes[i] > closes[i-1]:
                    if not in_retracement:
                        retracements += 1
                        in_retracement = True
                else:
                    in_retracement = False
        
        return retracements
    
    def _detect_divergence(self, micro: MicroAnalysis, 
                           macro: MacroAnalysis) -> Tuple[bool, str, float]:
        """
        Detecta divergência entre Micro e Macro
        
        Returns:
            (has_divergence, divergence_type, strength)
        """
        # Divergência de alta (bullish): Macro descendo, Micro subindo
        if macro.direction == TrendDirection.BAIXA and \
           micro.direction == TrendDirection.ALTA and \
           micro.momentum > 40:
            strength = micro.momentum * 0.7 + (100 - macro.trend_strength) * 0.3
            return True, "bullish", strength
        
        # Divergência de baixa (bearish): Macro subindo, Micro descendo
        if macro.direction == TrendDirection.ALTA and \
           micro.direction == TrendDirection.BAIXA and \
           micro.momentum > 40:
            strength = micro.momentum * 0.7 + (100 - macro.trend_strength) * 0.3
            return True, "bearish", strength
        
        # Divergência de momentum (movimento enfraquecendo)
        if macro.movement_type in [MovementType.IMPULSO_ALTA, MovementType.IMPULSO_BAIXA]:
            if micro.movement_type == MovementType.DESACELERANDO:
                div_type = "bearish" if macro.direction == TrendDirection.ALTA else "bullish"
                return True, div_type, 50.0
        
        return False, "", 0.0
    
    def _calculate_scores(self, micro: MicroAnalysis, macro: MacroAnalysis,
                          has_div: bool, div_type: str) -> Tuple[float, float]:
        """Calcula scores bullish e bearish"""
        bullish = 50.0
        bearish = 50.0
        
        # Contribuição MICRO (40% do peso)
        if micro.direction == TrendDirection.ALTA:
            bullish += micro.momentum * 0.4
        elif micro.direction == TrendDirection.BAIXA:
            bearish += micro.momentum * 0.4
        
        # Bônus por candles consecutivos
        if micro.consecutive_direction >= 3:
            if micro.direction == TrendDirection.ALTA:
                bullish += 10
            else:
                bearish += 10
        
        # Bônus por padrões de reversão
        if micro.is_pin_bar or micro.is_engulfing:
            if micro.direction == TrendDirection.ALTA:
                bullish += 15
            else:
                bearish += 15
        
        # Contribuição MACRO (40% do peso)
        if macro.direction == TrendDirection.ALTA:
            bullish += macro.trend_strength * 0.4
        elif macro.direction == TrendDirection.BAIXA:
            bearish += macro.trend_strength * 0.4
        
        # Alinhamento de MAs
        if macro.ma_alignment == "bullish":
            bullish += 15
        elif macro.ma_alignment == "bearish":
            bearish += 15
        
        # Divergência (20% do peso)
        if has_div:
            if div_type == "bullish":
                bullish += 20
                bearish -= 10
            elif div_type == "bearish":
                bearish += 20
                bullish -= 10
        
        # Normalizar para 0-100
        total = bullish + bearish
        if total > 0:
            bullish = (bullish / total) * 100
            bearish = (bearish / total) * 100
        
        return round(bullish, 2), round(bearish, 2)
    
    def _determine_signal(self, micro: MicroAnalysis, macro: MacroAnalysis,
                          bullish: float, bearish: float, 
                          has_div: bool, div_type: str) -> Tuple[str, float, str]:
        """Determina o sinal final"""
        reasons = []
        
        # Determinar direção
        if bullish > bearish + 15:
            signal = "CALL"
            confidence = min(95, bullish)
        elif bearish > bullish + 15:
            signal = "PUT"
            confidence = min(95, bearish)
        else:
            signal = "NEUTRAL"
            confidence = 50
        
        # Construir reasoning
        # Micro
        if micro.movement_type == MovementType.IMPULSO_ALTA:
            reasons.append("📈 Micro: Impulso de ALTA")
        elif micro.movement_type == MovementType.IMPULSO_BAIXA:
            reasons.append("📉 Micro: Impulso de BAIXA")
        elif micro.movement_type == MovementType.ACELERANDO:
            dir_emoji = "📈" if micro.direction == TrendDirection.ALTA else "📉"
            reasons.append(f"{dir_emoji} Micro: ACELERANDO")
        elif micro.movement_type == MovementType.DESACELERANDO:
            reasons.append("⚠️ Micro: Desacelerando")
        elif micro.movement_type == MovementType.CONSOLIDACAO:
            reasons.append("↔️ Micro: Consolidação")
        
        # Macro
        if macro.direction == TrendDirection.ALTA:
            reasons.append(f"📊 Macro: Tendência ALTA ({macro.trend_strength:.0f}%)")
        elif macro.direction == TrendDirection.BAIXA:
            reasons.append(f"📊 Macro: Tendência BAIXA ({macro.trend_strength:.0f}%)")
        else:
            reasons.append("📊 Macro: Lateral")
        
        # Alinhamento
        if macro.ma_alignment == "bullish":
            reasons.append("✅ MAs alinhadas p/ ALTA")
        elif macro.ma_alignment == "bearish":
            reasons.append("✅ MAs alinhadas p/ BAIXA")
        
        # Divergência
        if has_div:
            if div_type == "bullish":
                reasons.append("⭐ DIVERGÊNCIA BULLISH detectada!")
            else:
                reasons.append("⭐ DIVERGÊNCIA BEARISH detectada!")
        
        # Confluência Micro + Macro
        if micro.direction == macro.direction and micro.direction != TrendDirection.LATERAL:
            dir_name = "ALTA" if micro.direction == TrendDirection.ALTA else "BAIXA"
            reasons.append(f"🔥 CONFLUÊNCIA Micro+Macro: {dir_name}")
            confidence = min(95, confidence + 10)
        
        # Padrões
        if micro.is_engulfing:
            reasons.append("🕯️ Padrão ENGULFING")
        if micro.is_pin_bar:
            reasons.append("🕯️ Padrão PIN BAR")
        
        return signal, round(confidence, 1), " | ".join(reasons)
    
    def _empty_analysis(self, pair: str, price: float) -> MovementAnalysis:
        """Retorna análise vazia quando não há dados suficientes"""
        empty_micro = MicroAnalysis(
            direction=TrendDirection.LATERAL,
            velocity=0, acceleration=0, momentum=0, volatility=0,
            candles_analyzed=0, consecutive_direction=0, last_candle_strength=0,
            movement_type=MovementType.CONSOLIDACAO
        )
        empty_macro = MacroAnalysis(
            direction=TrendDirection.LATERAL,
            trend_strength=0, avg_velocity=0, trend_age=0,
            higher_highs=0, lower_lows=0, trend_line_slope=0, retracements=0,
            movement_type=MovementType.CONSOLIDACAO,
            price_vs_ma20="at", price_vs_ma50="at", ma_alignment="mixed"
        )
        return MovementAnalysis(
            pair=pair, timestamp=datetime.now(), current_price=price,
            micro=empty_micro, macro=empty_macro,
            signal_bias="NEUTRAL", confidence=50,
            reasoning="Dados insuficientes"
        )
    
    def get_ai_context(self, analysis: MovementAnalysis) -> str:
        """
        Retorna contexto formatado para incluir no prompt da IA
        """
        lines = [
            "",
            "=== ANÁLISE DE MOVIMENTAÇÃO (MICRO/MACRO) ===",
            f"Par: {analysis.pair} | Preço: {analysis.current_price}",
            "",
            "📊 MICRO (últimos {0} candles):".format(analysis.micro.candles_analyzed),
            f"   Direção: {analysis.micro.direction.value.upper()}",
            f"   Momentum: {analysis.micro.momentum:.1f}%",
            f"   Velocidade: {'↑' if analysis.micro.velocity > 0 else '↓'} {abs(analysis.micro.velocity):.6f}/candle",
            f"   Aceleração: {'📈 Aumentando' if analysis.micro.acceleration > 0 else '📉 Diminuindo'}",
            f"   Candles consecutivos: {analysis.micro.consecutive_direction}",
            f"   Movimento: {analysis.micro.movement_type.value.upper()}",
        ]
        
        # Padrões micro
        patterns = []
        if analysis.micro.is_doji:
            patterns.append("Doji")
        if analysis.micro.is_engulfing:
            patterns.append("Engulfing")
        if analysis.micro.is_pin_bar:
            patterns.append("Pin Bar")
        if patterns:
            lines.append(f"   Padrões: {', '.join(patterns)}")
        
        lines.extend([
            "",
            "📈 MACRO (tendência geral):",
            f"   Direção: {analysis.macro.direction.value.upper()}",
            f"   Força: {analysis.macro.trend_strength:.1f}%",
            f"   Idade: {analysis.macro.trend_age} candles",
            f"   Higher Highs: {analysis.macro.higher_highs} | Lower Lows: {analysis.macro.lower_lows}",
            f"   Preço vs MA20: {analysis.macro.price_vs_ma20.upper()}",
            f"   Preço vs MA50: {analysis.macro.price_vs_ma50.upper()}",
            f"   Alinhamento MAs: {analysis.macro.ma_alignment.upper()}",
            f"   Movimento: {analysis.macro.movement_type.value.upper()}",
        ])
        
        # Divergência
        if analysis.has_divergence:
            lines.extend([
                "",
                f"⚠️ DIVERGÊNCIA DETECTADA: {analysis.divergence_type.upper()}",
                f"   Força: {analysis.divergence_strength:.1f}%",
            ])
        
        # Scores e recomendação
        lines.extend([
            "",
            "📊 SCORES:",
            f"   Bullish: {analysis.bullish_score:.1f}%",
            f"   Bearish: {analysis.bearish_score:.1f}%",
            "",
            f"💡 Sinal: {analysis.signal_bias} ({analysis.confidence}%)",
            f"   {analysis.reasoning}",
            "=" * 50,
        ])
        
        return "\n".join(lines)
    
    def format_for_display(self, analysis: MovementAnalysis) -> str:
        """Formata para exibição no console"""
        return self.get_ai_context(analysis)


# Instância global
movement_analyzer = PriceMovementAnalyzer()


def analyze_movement(pair: str, candles: List[Dict], 
                     current_price: Optional[float] = None) -> Dict:
    """
    Função helper para análise rápida
    
    Returns:
        Dict com signal, confidence, micro, macro e contexto
    """
    analysis = movement_analyzer.analyze(pair, candles, current_price)
    
    return {
        'signal': analysis.signal_bias,
        'confidence': analysis.confidence,
        'bullish_score': analysis.bullish_score,
        'bearish_score': analysis.bearish_score,
        'micro': {
            'direction': analysis.micro.direction.value,
            'momentum': analysis.micro.momentum,
            'movement': analysis.micro.movement_type.value,
            'consecutive': analysis.micro.consecutive_direction,
            'patterns': {
                'doji': analysis.micro.is_doji,
                'engulfing': analysis.micro.is_engulfing,
                'pin_bar': analysis.micro.is_pin_bar
            }
        },
        'macro': {
            'direction': analysis.macro.direction.value,
            'strength': analysis.macro.trend_strength,
            'ma_alignment': analysis.macro.ma_alignment,
            'movement': analysis.macro.movement_type.value
        },
        'divergence': {
            'detected': analysis.has_divergence,
            'type': analysis.divergence_type,
            'strength': analysis.divergence_strength
        },
        'reasoning': analysis.reasoning,
        'context': movement_analyzer.get_ai_context(analysis)
    }


def get_movement_prompt_context(pair: str, candles: List[Dict]) -> str:
    """Retorna contexto formatado para o prompt da IA"""
    analysis = movement_analyzer.analyze(pair, candles)
    return movement_analyzer.get_ai_context(analysis)


if __name__ == "__main__":
    print("📈 Módulo de Análise de Movimentação MICRO/MACRO")
    print("Use: from utils.price_movement_analyzer import analyze_movement")
