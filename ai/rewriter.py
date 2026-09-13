import asyncio
from time import perf_counter
import re
import unicodedata
from difflib import SequenceMatcher

import requests

from diagnostics.audit import registrar_erro, registrar_etapa


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
TEMPO_LIMITE = 90

MAXIMO_LINHAS = 1
MAXIMO_CARACTERES = 130
MAXIMO_TENTATIVAS = 3
LIMITE_SEMELHANCA = 0.78


TERMOS_DE_PRODUTO = {
    "robo", "robô", "aspirador", "air fryer", "fritadeira", "panela",
    "panelas", "frigideira", "caçarola", "caçarola", "cooktop",
    "furadeira", "parafusadeira", "ferramenta", "maleta",
    "relogio", "relógio", "smartwatch", "fone", "headset", "caixa de som",
    "televisao", "televisão", "tv", "monitor", "notebook", "computador",
    "celular", "smartphone", "iphone", "tablet", "camera", "câmera",
    "tupperware", "pote", "potes", "garrafa", "copo", "caneca", "kit",
    "camiseta", "camisa", "tenis", "tênis", "sapato", "sandalia", "sandália",
    "mochila", "bolsa", "ssd", "hd", "memoria", "memória", "teclado",
    "mouse", "cadeira", "ventilador", "ar condicionado", "microondas",
    "micro-ondas", "geladeira", "lavadora", "secadora", "fogao", "fogão",
}


PALAVRAS_IGNORADAS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do",
    "das", "dos", "e", "em", "no", "na", "nos", "nas", "para", "por",
    "com", "sem", "que", "se", "esse", "essa", "este", "esta", "isso",
    "mais", "muito", "bem", "já", "ja", "sua", "seu",
}


# Palavras que indicam que o modelo entendeu o produto errado.
# Ex.: "jogo de panelas" não é jogo de videogame/tabuleiro.
REGRAS_DE_INCOMPATIBILIDADE = (
    (
        ("panela", "panelas", "frigideira", "caçarola", "cozinha", "cooktop"),
        ("aprender", "jogar", "partida", "fase", "nível", "nivel", "jogador", "game"),
        "A IA tratou utensílios de cozinha como jogo ou brincadeira.",
    ),
    (
        ("furadeira", "parafusadeira", "ferramenta"),
        ("varrer", "aspirar", "limpeza automática", "limpeza automatica"),
        "A IA atribuiu função de limpeza a uma ferramenta.",
    ),
    (
        ("pote", "potes", "tupperware", "recipiente"),
        ("aspirar", "varrer", "robô", "robo"),
        "A IA confundiu recipientes com aparelho de limpeza.",
    ),
)


def remover_links(texto: str) -> str:
    return re.sub(r"https?://\S+", "", texto or "", flags=re.IGNORECASE).strip()


def extrair_primeira_linha(texto: str) -> str:
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if linha:
            return linha
    return ""


def extrair_titulo_produto(texto: str) -> str:
    """Retorna a primeira linha útil depois da chamada, que normalmente é o título."""
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]
    for linha in linhas[1:]:
        if re.search(r"https?://", linha, re.IGNORECASE):
            continue
        if re.search(r"\b(?:cupom|código|codigo|pix|frete|cashback)\b", linha, re.IGNORECASE):
            continue
        if re.fullmatch(r"(?:R\$\s*)?\d{1,3}(?:\.\d{3})*(?:,\d{2})?(?:\s+à\s+vista)?", linha, re.IGNORECASE):
            continue
        return linha
    return ""


def extrair_contexto_produto(texto: str) -> str:
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]
    contexto_limpo: list[str] = []

    for linha in linhas[1:8]:
        if re.search(r"https?://", linha, re.IGNORECASE):
            continue
        if re.search(r"\b(?:cupom|código|codigo|pix|frete|cashback)\b", linha, re.IGNORECASE):
            continue
        if re.search(r"R\$\s*\d|\bpor\s+\d[\d.,]*|\b\d+[.,]\d{2}\s+à\s+vista", linha, re.IGNORECASE):
            continue
        if linha:
            contexto_limpo.append(linha)

    return "\n".join(contexto_limpo[:3]).strip()


def normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip())


def normalizar_comparacao(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def palavras_relevantes(texto: str) -> set[str]:
    return {
        palavra
        for palavra in normalizar_comparacao(texto).split()
        if len(palavra) >= 3 and palavra not in PALAVRAS_IGNORADAS
    }


def calcular_semelhanca(original: str, resposta: str) -> float:
    original_n = normalizar_comparacao(original)
    resposta_n = normalizar_comparacao(resposta)
    if not original_n or not resposta_n:
        return 1.0

    seq = SequenceMatcher(None, original_n, resposta_n).ratio()
    p_original = palavras_relevantes(original)
    p_resposta = palavras_relevantes(resposta)
    sobreposicao = (
        len(p_original & p_resposta) / max(1, len(p_original))
        if p_original and p_resposta else 0.0
    )
    return max(seq, sobreposicao)


def limpar_resposta(texto: str) -> str:
    texto = remover_links(texto).strip().strip('"\'“”')
    prefixos = (
        "texto reformulado:", "mensagem reformulada:", "chamada:",
        "gancho:", "resposta:", "resultado:", "texto final:", "nova chamada:",
    )
    minusculo = texto.lower()
    for prefixo in prefixos:
        if minusculo.startswith(prefixo):
            texto = texto[len(prefixo):].strip()
            break

    linhas = [normalizar(l) for l in texto.splitlines() if normalizar(l)]
    texto = " ".join(linhas[:MAXIMO_LINHAS]).strip()
    if len(texto) > MAXIMO_CARACTERES:
        texto = texto[:MAXIMO_CARACTERES].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return texto.upper()


def termo_presente(termo: str, texto: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(termo)}(?!\w)", texto, flags=re.IGNORECASE) is not None


def inventou_outro_produto(texto_original: str, resposta: str) -> tuple[bool, str]:
    original = (texto_original or "").lower()
    resposta_m = (resposta or "").lower()
    for termo in TERMOS_DE_PRODUTO:
        if termo_presente(termo, resposta_m) and not termo_presente(termo, original):
            return True, termo
    return False, ""


def contexto_incompativel(texto_original: str, resposta: str) -> tuple[bool, str]:
    original = normalizar_comparacao(texto_original)
    resposta_n = normalizar_comparacao(resposta)
    for termos_contexto, termos_proibidos, motivo in REGRAS_DE_INCOMPATIBILIDADE:
        if any(normalizar_comparacao(t) in original for t in termos_contexto):
            if any(normalizar_comparacao(t) in resposta_n for t in termos_proibidos):
                return True, motivo
    return False, ""


def validar_resposta(texto_original: str, chamada_original: str, resposta: str) -> tuple[bool, str]:
    if not resposta:
        return False, "A IA retornou texto vazio."
    if len(resposta) > MAXIMO_CARACTERES:
        return False, "A resposta ficou longa demais."
    if len([l for l in resposta.splitlines() if l.strip()]) > MAXIMO_LINHAS:
        return False, "A resposta passou do limite de linhas."

    if re.search(
        r"https?://|r\$\s*\d|\b\d+\s*%|\bcupom\b|\bfrete\s+gr[aá]tis\b|"
        r"\b(?:por|de)\s+\d[\d.,]*\b|\b\d+\s*x\b|\bpix\b|\bà\s+vista\b",
        resposta,
        re.IGNORECASE,
    ):
        return False, "A IA incluiu informação comercial proibida."

    inventou, termo = inventou_outro_produto(texto_original, resposta)
    if inventou:
        return False, f'A IA inventou ou trocou o produto por "{termo}".'

    incompatível, motivo = contexto_incompativel(texto_original, resposta)
    if incompatível:
        return False, motivo

    semelhanca = calcular_semelhanca(chamada_original, resposta)
    if semelhanca >= LIMITE_SEMELHANCA:
        return False, f"A nova chamada ficou parecida demais com a original ({semelhanca:.0%})."

    return True, ""


def montar_prompt(chamada_original: str, titulo_produto: str, contexto_produto: str, tentativa: int) -> str:
    angulos = {
        1: "Destaque uma situação de uso real e coerente com o produto.",
        2: "Crie desejo pela praticidade ou pelo resultado que o produto realmente oferece.",
        3: "Use curiosidade leve, mas deixe evidente que você entendeu o produto.",
    }
    orientacao = angulos.get(tentativa, angulos[1])

    aviso_especial = ""
    titulo_n = normalizar_comparacao(titulo_produto)
    if "jogo de panela" in titulo_n or "jogo panelas" in titulo_n:
        aviso_especial = (
            "ATENÇÃO: neste anúncio, a palavra JOGO significa CONJUNTO DE PANELAS. "
            "Não use aprender, jogar, partida, fase, nível ou qualquer referência a games."
        )

    return f"""
VOCÊ REESCREVE SOMENTE A PRIMEIRA CHAMADA DE UMA PROMOÇÃO PARA WHATSAPP.

PRODUTO EXATO:
{titulo_produto or contexto_produto or "PRODUTO NÃO IDENTIFICADO"}

CONTEXTO ADICIONAL:
{contexto_produto or "SEM CONTEXTO ADICIONAL"}

CHAMADA ORIGINAL:
{chamada_original}

{aviso_especial}

OBJETIVO:
Criar uma chamada nova, mais envolvente e coerente com o PRODUTO EXATO.
Ela não deve ser uma simples troca de sinônimos da frase original.

ÂNGULO DESTA TENTATIVA:
{orientacao}

REGRAS OBRIGATÓRIAS:
- Escreva somente UMA frase curta.
- A frase precisa fazer sentido para o produto exato acima.
- Preserve o assunto geral, mas pode abandonar um trocadilho ruim ou ambíguo.
- Não copie a estrutura da chamada original.
- Não reescreva a descrição do produto.
- Não invente material, função, benefício ou característica.
- Não mencione preço, desconto, cupom, frete, estoque, urgência, loja, link ou pagamento.
- Não use “aproveite”, “corre”, “não perca” ou frases genéricas.
- Use no máximo {MAXIMO_CARACTERES} caracteres.
- Retorne somente a frase final, sem aspas e sem explicações.

NOVA CHAMADA:
""".strip()


def consultar_ollama(prompt: str, tentativa: int) -> str:
    temperaturas = {1: 0.40, 2: 0.52, 3: 0.62}
    resposta = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperaturas.get(tentativa, 0.48),
                "top_p": 0.82,
                "num_predict": 55,
                "repeat_penalty": 1.20,
            },
        },
        timeout=TEMPO_LIMITE,
    )
    resposta.raise_for_status()
    return limpar_resposta(resposta.json().get("response", ""))


def _reformular_sincrono(texto_original: str, loja: str, preco: str, cupom: str) -> str:
    chamada_original = extrair_primeira_linha(texto_original)
    if not chamada_original:
        return ""

    titulo_produto = extrair_titulo_produto(texto_original)
    contexto_produto = extrair_contexto_produto(texto_original)
    ultimo_motivo = ""

    for tentativa in range(1, MAXIMO_TENTATIVAS + 1):
        prompt = montar_prompt(chamada_original, titulo_produto, contexto_produto, tentativa)
        reformulado = consultar_ollama(prompt, tentativa)
        valido, motivo = validar_resposta(texto_original, chamada_original, reformulado)
        if valido:
            return reformulado
        ultimo_motivo = motivo
        print(f"\n⚠ IA: tentativa {tentativa} descartada: {motivo}")

    raise ValueError(
        "Nenhuma reformulação segura e coerente foi gerada. "
        f"Último motivo: {ultimo_motivo}"
    )


async def reformular_promocao(
    texto_original: str,
    loja: str,
    preco: str,
    cupom: str,
    audit_id: str = "",
) -> str:
    inicio = perf_counter()

    if audit_id:
        registrar_etapa(
            audit_id,
            "IA_OLLAMA",
            codigo="CONSULTA_INICIADA",
            modelo=OLLAMA_MODEL,
            maximo_tentativas=MAXIMO_TENTATIVAS,
        )

    try:
        resultado = await asyncio.to_thread(
            _reformular_sincrono,
            texto_original,
            loja,
            preco,
            cupom,
        )
        if audit_id:
            registrar_etapa(
                audit_id,
                "IA_OLLAMA",
                status="OK" if resultado else "ALERTA",
                codigo="TEXTO_GERADO" if resultado else "TEXTO_NAO_GERADO",
                texto_reformulado=resultado,
                duracao_ms=(perf_counter() - inicio) * 1000,
            )
        return resultado

    except requests.exceptions.ConnectionError as erro:
        print("\n⚠ IA local indisponível: o Ollama não está respondendo.")
        codigo = "OLLAMA_INDISPONIVEL"
    except requests.exceptions.Timeout as erro:
        print("\n⚠ A IA local ultrapassou o tempo limite.")
        codigo = "OLLAMA_TIMEOUT"
    except requests.exceptions.HTTPError as erro:
        print("\n⚠ Erro de comunicação com o Ollama:", erro)
        codigo = "OLLAMA_ERRO_HTTP"
    except Exception as erro:
        print("\n⚠ A reformulação foi descartada:", erro)
        codigo = "IA_REFORMULACAO_DESCARTADA"

    if audit_id:
        registrar_erro(
            audit_id,
            "IA_OLLAMA",
            erro,
            codigo=codigo,
            duracao_ms=(perf_counter() - inicio) * 1000,
        )
    return ""
