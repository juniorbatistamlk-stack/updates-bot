# strategies/definitions.py

"""
DEFINIÇÕES DE LÓGICA ESTRATÉGICA PARA A INTELIGÊNCIA ARTIFICIAL
Este arquivo centraliza as regras de operação de todas as estratégias.
A IA usa estas definições para validar sinais com precisão cirúrgica.
"""

STRATEGY_DEFINITIONS = {
    # === ESTRATÉGIAS ANTIGAS (1-7) ===
    
    "Ferreira Trader Sniper": """
    ESTRATÉGIA: Ferreira Trader Sniper (V1)
    TIPO: Pullback e Reversão em Bandas de Bollinger
    
    REGRAS DE ENTRADA:
    1. TENDÊNCIA (Pullback):
       - Preço acima da EMA 100 = Tendência de ALTA.
       - Preço abaixo da EMA 100 = Tendência de BAIXA.
       - GATILHO CALL: Vela toca na EMA 20 e fecha acima dela (Pullback). RSI < 70.
       - GATILHO PUT: Vela toca na EMA 20 e fecha abaixo dela (Pullback). RSI > 30.
    
    2. REVERSÃO (Sniper):
       - GATILHO PUT: Vela toca na Banda Superior, deixa pavio superior (> 50% do corpo) e RSI >= 70.
       - GATILHO CALL: Vela toca na Banda Inferior, deixa pavio inferior (> 50% do corpo) e RSI <= 30.
    
    CRITÉRIOS DE RECUSA DA IA:
    - Contra tendência forte sem padrão de exaustão claro.
    - Vela sem pavio (força contínua) tocando na banda (perigo de rompimento).
    """,

    "Price Action Reversal Master 1.0": """
    ESTRATÉGIA: Price Action Reversal Master
    TIPO: Reversão em Suporte e Resistência (S/R)
    
    REGRAS DE ENTRADA:
    1. ZONAS: Identificar Topos e Fundos recentes.
    2. FILTRO MACRO: Só comprar se preço > SMA 50. Só vender se preço < SMA 50.
    3. GATILHOS (PADRÕES DE VELA):
       - MARTELO (Call): Pavio inferior 2x corpo, em Suporte.
       - SHOOTING STAR (Put): Pavio superior 2x corpo, em Resistência.
       - ENGOLFO DE ALTA (Call): Vela verde engole vermelha anterior, em Suporte.
       - ENGOLFO DE BAIXA (Put): Vela vermelha engole verde anterior, em Resistência.
    
    CRITÉRIOS DE RECUSA DA IA:
    - Padrão formado "no meio do nada" (longe de S/R).
    - Martelo/Star com pouco pavio ou corpo muito grande (indecisão).
    """,

    "Lógica do Preço (Travamentos)": """
    ESTRATÉGIA: Lógica do Preço (Travamentos)
    TIPO: Travamento em Zonas de Comando
    
    REGRAS DE ENTRADA:
    1. ZONAS DE COMANDO: Velas onde Abertura = Mínima (Comando Alta) ou Abertura = Máxima (Comando Baixa).
    2. TRAVAMENTO: O corpo da vela atual fecha EXATAMENTE na linha de abertura do comando (tolerância mínima).
    3. GATILHO CALL: Vela vermelha trava em Suporte de Comando.
    4. GATILHO PUT: Vela verde trava em Resistência de Comando.
    
    CRITÉRIOS DE RECUSA DA IA:
    - Vela de travamento muito pequena (Doji).
    - Rompimento da zona (fechou um pouco além).
    - Travamento longe da zona (gap visível).
    """,

    "Ana Tavares Retraction System": """
    ESTRATÉGIA: Ana Tavares (Retração M5)
    TIPO: Retração em M5 no "Efeito Elástico"
    
    REGRAS DE ENTRADA:
    1. TEMPO: Pico deve ocorrer nos primeiros 2m30s (50% da vela M5).
    2. EXPLOSÃO: Vela deve esticar rápido (Pico de volatilidade).
    3. ZONA: Toque na SMA 20 ou Zona S/R.
    4. GATILHO: A vela estica, toca na zona e deve retrair.
       - CALL: Tendência Alta + Toque na SMA 20.
       - PUT: Tendência Baixa + Toque na SMA 20.
    
    CRITÉRIOS DE RECUSA DA IA:
    - Movimento lento (vela "trator").
    - Vela nasceu muito perto da zona (sem espaço para esticar).
    - Tempo esgotado (> 2m30s).
    """,

    "Trader Conservador": """
    ESTRATÉGIA: Trader Conservador (Canais/Fimathe)
    TIPO: Breakout (Rompimento) a favor da macro
    
    REGRAS DE ENTRADA:
    1. ESTRUTURA: Canal de Referência + Zona Neutra.
    2. TENDÊNCIA: SMA 200 define direção.
    3. GATILHO CALL: Rompimento do topo do canal de referência + Tendência BULLISH + Vela Verde fechada fora.
    4. GATILHO PUT: Rompimento do fundo do canal de referência + Tendência BEARISH + Vela Vermelha fechada fora.
    
    CRITÉRIOS DE RECUSA DA IA:
    - Rompimento com vela de dúvida (pavio contra).
    - Mercado lateral (preço "flat" na SMA 200).
    - Rompimento fraco (apenas pavio ou corpo ínfimo).
    """,

    "Alavancagem Agressiva (Fluxo + Reversão)": """
    ESTRATÉGIA: Alavancagem Agressiva
    TIPO: Híbrido (Fluxo e Reversão)
    
    REGRAS DE ENTRADA:
    1. MODO FLUXO (Três Soldados / Marubozu):
       - 3 velas fortes na mesma direção (Corpo > 60%).
       - Marubozu (Corpo > 75%) rompendo nível.
       - AÇÃO: Entrar a favor do movimento.
    2. MODO REVERSÃO:
       - Só opera reversão se houver confirmação (Vela de força contra a zona S/R).
       - NUNCA operar toque cego.
    
    CRITÉRIOS DE RECUSA DA IA:
    - Sequência de velas diminuindo de tamanho (perda de força).
    - Marubozu exausto (muito grande, > 3x média).
    - Zonas de "briga" (muitos pavios para ambos os lados).
    """,

    "Alavancagem S/R Sniper (+5 Padrões)": """
    ESTRATÉGIA: Alavancagem SR Sniper
    TIPO: Padrões de Candle em S/R
    
    REGRAS DE ENTRADA:
    1. LOCALIZAÇÃO: Preço próximo a Suporte ou Resistência mapeado.
    2. CONFIRMAÇÃO: Obrigatório padrão de candle:
       - Martelo/Shooting Star.
       - Engolfo.
       - Marubozu (Força saindo da zona).
    3. FILTRO: A favor das médias EMA 20/50.
    
    CRITÉRIOS DE RECUSA DA IA:
    - Padrão contra a tendência das médias.
    - Vela de sinal com pavio de rejeição contra a operação.
    """,

    # === NOVAS ESTRATÉGIAS (8-12) ===

    "Price Action Dinâmico (Ferreira)": """
    ESTRATÉGIA: Price Action Dinâmico (Ferreira)
    TIPO: Leitura de vela a vela (Fluxo, Pavio, Simetria)
    
    REGRAS DE ENTRADA:
    1. SETUP A (Fluxo de Continuidade):
       - Rompimento de defesa anterior.
       - CALL: Vela verde rompe máxima da anterior verde + Pavio sup pequeno.
       - PUT: Vela vermelha rompe mínima da anterior vermelha + Pavio inf pequeno.
    2. SETUP B (Entrega Futura):
       - Preenchimento de pavio.
       - CALL: Vela anterior deixou pavio inferior grande + Atual verde rompendo 50% dele.
       - PUT: Vela anterior deixou pavio superior grande + Atual vermelha rompendo 50% dele.
    3. SETUP C (Simetria):
       - Reversão em níveis exatos.
       - Preço fecha ou abre exatamente em topo/fundo anterior (tolerância 2 pips).
       - Confirmação: Corpo menor que anterior (fraqueza).
    
    CRITÉRIOS DE RECUSA DA IA:
    - Rejeição na zona oposta.
    - MACD contra o movimento.
    - Corpo da vela diminuindo + Pavio de rejeição aumentando.
    """,

    "SNR Advanced (Ferreira)": """
    ESTRATÉGIA: Ferreira SNR Advanced
    TIPO: Rompimento Falso e Exaustão
    
    REGRAS DE ENTRADA:
    1. ANTI-BOX: Ignorar primeiro toque. Esperar manipulação.
    2. GATILHO 1: Rompimento Falso (Preço rompe e volta para dentro da zona).
    3. GATILHO 2: Exaustão (Vela grande bate na zona e perde força/pavio).
    4. GATILHO 3: Engolfo na zona (Vela reverte engolfando anterior na cara do S/R).
    
    CRITÉRIOS DE RECUSA DA IA:
    - Rompimento real (vela fecha longe da zona após romper).
    - Vela de força nascendo perto da zona e rompendo direto (sem exaustão).
    """,

    "Médias Móveis (Ferreira)": """
    ESTRATÉGIA: Ferreira Médias Móveis
    TIPO: Cruzamento EMA 5 x SMA 20 + Pullback
    
    REGRAS DE ENTRADA:
    1. CRUZAMENTO: EMA 5 (Rápida) cruza SMA 20 (Lenta).
    2. IMPULSÃO: Vela do cruzamento deve ser forte (corpo expressivo).
    3. PULLBACK:
       - Aguardar preço retornar e tocar/aproximar da EMA 5.
       - Entrar a favor da nova tendência.
    
    CRITÉRIOS DE RECUSA DA IA:
    - Médias "enroladas" (Lateralização).
    - Preço travado em S/R logo após o cruzamento (sem alvo).
    - Vela de cruzamento cheia de pavios (indecisão).
    """,

    "Primeiro Registro V2 (Ferreira)": """
    ESTRATÉGIA: Primeiro Registro V2 (1R Defense)
    TIPO: Defesa de Taxa Institucional
    
    REGRAS DE ENTRADA:
    1. MARCAÇÃO 1R (Primeiro Registro):
       - Identificar reversão (troca de cor) ou Comando.
       - Marcar o pavio da primeira vela do movimento (1R).
    2. ROMPIMENTO: Preço deve sair da zona.
    3. TESTE (Retração):
       - Preço volta para testar a linha do 1R.
       - GATILHO: Toca na linha e RETRAI (Defesa).
       - CALL: Toca no 1R de alta e fecha ACIMA.
       - PUT: Toca no 1R de baixa e fecha ABAIXO.
    
    CRITÉRIOS DE RECUSA DA IA:
    - Vela de teste rompe a linha com o corpo (invasão de lote).
    - Tendência macro contra a defesa.
    """,

    "Trader Machado (Lógica Preço)": """
    ESTRATÉGIA: Trader Machado (Lógica do Preço)
    TIPO: Price Action Puro (Lotes, Simetria, Vácuo)
    
    REGRAS DE ENTRADA:
    1. NOVA ALTA/BAIXA (Continuidade):
       - Vela rompe pavio da anterior (gera interesse/vácuo).
       - Sem travamento à esquerda.
       - AÇÃO: Seguir fluxo (Call/Put).
    2. REVERSÃO POR SIMETRIA (Trava):
       - Corpo fecha alinhado com pavio/corpo anterior (Simetria).
       - Perda de volume.
       - AÇÃO: Reversão.
    3. DEFESA DE LOTE:
       - Preço retorna à primeira vela de um lote anterior.
       - Respeita a zona (não rompe).
    
    CRITÉRIOS DE RECUSA DA IA:
    - Vela sem pavio na direção do movimento (fim de ciclo).
    - Travamento falso (rompeu um pouco ou não chegou).
    - Mercado errático (muitos pavios sem direção).
    """,

    # === ESTRATÉGIA META (13) ===
    
    "AI God Mode (12-in-1)": """
    ESTRATÉGIA: AI GOD MODE (O MELHOR TRADER DO MUNDO)
    TIPO: ARBITRAGEM INTELIGENTE MULTI-ESTRATÉGIA
    
    SUA MISSÃO:
    Você é o Gestor Supremo de Risco e Oportunidade.
    Você recebe relatórios de 12 Traders especialistas (Sub-Estratégias).
    Sua função não é apenas "validar", é ESCOLHER E DECIDIR.
    
    REGRAS DE ARBITRAGEM:
    1. CONVERGÊNCIA: Se múltiplos traders sugerem CALL, a probabilidade é altíssima. APROVE.
    2. DIVERGÊNCIA: Se um sugere CALL e outro PUT, analise quem tem a lógica mais forte para o contexto atual (ex: se mercado lateral, ignore traders de tendência).
    3. QUALIDADE: Se apenas um trader sugeriu entrada, mas a explicação é técnica e perfeita (ex: Snipe em S/R), APROVE.
    4. FILTRO DE RUÍDO: Se os sinais são fracos ou contraditórios, VETE todos.
    
    MINDSET:
    - Você busca a "Entrada Perfeita".
    - Se houver dúvida, proteja o capital.
    - Se houver certeza, ataque com confiança.
    """
}
