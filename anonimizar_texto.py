"""
CP5 - FIAP Bank | Anonimizacao para exportacao externa (LGPD)

anonimizar_texto(texto) substitui PII por marcadores:
    [NOME]  nome de pessoa (cliente, atendente, gerente ou terceiro)
    [CPF]   CPF formatado ou nao
    [RG]    RG formatado ou nao
    [CONTA] numero de conta e/ou agencia bancaria
    [EMAIL] endereco de e-mail

A funcao trata dois problemas complementares:

1. Identificadores estruturados (CPF, RG, conta/agencia, e-mail): regex.
   O spaCy nao foi treinado para isso, entao sao reconhecidos por formato
   e, quando o formato e ambiguo (ex.: 9 digitos soltos), pela palavra-chave
   que vem antes ("RG", "conta", "agencia"...).

2. Nomes de pessoa: NER do spaCy (entidades PER), filtrado para descartar
   falsos positivos comuns (verbos no inicio da frase marcados como PER,
   siglas como CPF/Pix), e complementado por gatilhos de contexto
   ("meu nome e", "gerente", "Att,", "Assinado,") que recuperam nomes que o
   NER rotula como LOC/ORG ou deixa passar.

Tudo roda localmente: nenhum texto sai da maquina.
"""

from __future__ import annotations

import os
import re
import unicodedata
from functools import lru_cache

# ---------------------------------------------------------------------------
# Marcadores
# ---------------------------------------------------------------------------
M_NOME, M_CPF, M_RG, M_CONTA, M_EMAIL = "[NOME]", "[CPF]", "[RG]", "[CONTA]", "[EMAIL]"
_MARCADORES = {M_NOME, M_CPF, M_RG, M_CONTA, M_EMAIL}

# ---------------------------------------------------------------------------
# 1) Identificadores estruturados
# ---------------------------------------------------------------------------
_FLAGS = re.IGNORECASE | re.UNICODE

# E-mail
RE_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+", _FLAGS)

# Conectores que podem aparecer entre a palavra-chave e o numero:
# "CPF 123...", "CPF: 123", "meu CPF e 123", "RG no 123", "conta numero 123"
_CONECTOR = (
    r"(?:\s*(?::|-|=|#|n[º°o]\.?|num\.?|n[uú]mero|nr\.?|[eé]|eh|de|do|da|sob\s+o)(?![\w]))*?\s*"
)
# Para conta/agencia nao aceitamos "de/do/da" ("conta de 1500 reais" nao e PII)
_CONECTOR_CONTA = r"(?:\s*(?::|-|=|#|n[º°o]\.?|num\.?|n[uú]mero|nr\.?|[eé]|eh)(?![\w]))*?\s*"
# Sequencia numerica "de documento": digitos com . - / espacos internos
_NUM_DOC = r"\d[\d.\-/ ]{2,16}[\dxX]"

RE_CPF_CHAVE = re.compile(
    r"(?P<chave>\bc\.?\s?p\.?\s?f\b\.?)" + _CONECTOR + r"(?P<num>" + _NUM_DOC + r")", _FLAGS
)
RE_RG_CHAVE = re.compile(
    r"(?P<chave>\br\.?\s?g\b\.?|\bregistro\s+geral\b|\bcarteira\s+de\s+identidade\b|\bidentidade\b)"
    + _CONECTOR + r"(?P<num>" + _NUM_DOC + r")",
    _FLAGS,
)
RE_CONTA_CHAVE = re.compile(
    r"(?P<chave>\bconta(?:\s+(?:corrente|poupan[cç]a|salario|salário|digital|pagamento))?\b"
    r"|\bc/c\b|\bcc\b|\bag[eê]ncia\b|\bag\b\.?|\bag\.)"
    + _CONECTOR_CONTA + r"(?P<num>\d[\d.\-/]{2,16}[\dxX])(?![\d])",
    _FLAGS,
)

# Formatos sem palavra-chave
RE_CPF_FORMATO = re.compile(r"(?<![\d.\-])\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d\-])")
RE_CPF_11 = re.compile(r"(?<![\d.\-/])\d{11}(?![\d\-/])")  # 11 digitos soltos
RE_RG_FORMATO = re.compile(r"(?<![\d.\-])\d{1,2}\.\d{3}\.\d{3}-?[\dxX](?![\d\-])")
# conta com digito verificador: 12345-6 / 1234567-X (1 digito apos o hifen)
RE_CONTA_FORMATO = re.compile(r"(?<![\d.\-/])\d{4,12}-[\dxX](?![\d\-])")


def _mascarar_chave(regex: re.Pattern, marcador: str, texto: str) -> str:
    """Troca so o numero, preservando a palavra-chave ("CPF [CPF]")."""

    def _sub(m: re.Match) -> str:
        ini, fim = m.span("num")
        num = m.group("num").rstrip(" .-/")
        fim = m.start("num") + len(num)
        base = m.string
        return base[m.start():ini] + marcador + base[fim:m.end()]

    return regex.sub(_sub, texto)


def _anonimizar_estruturados(texto: str) -> str:
    texto = RE_EMAIL.sub(M_EMAIL, texto)
    # Palavra-chave primeiro: resolve ambiguidade (RG com 9 digitos x conta)
    texto = _mascarar_chave(RE_CPF_CHAVE, M_CPF, texto)
    texto = _mascarar_chave(RE_RG_CHAVE, M_RG, texto)
    texto = _mascarar_chave(RE_CONTA_CHAVE, M_CONTA, texto)
    # Depois formatos inequivocos que ficaram sem palavra-chave
    texto = RE_CPF_FORMATO.sub(M_CPF, texto)
    texto = RE_RG_FORMATO.sub(M_RG, texto)
    texto = RE_CPF_11.sub(M_CPF, texto)
    texto = RE_CONTA_FORMATO.sub(M_CONTA, texto)
    return texto


# ---------------------------------------------------------------------------
# 2) Nomes de pessoa
# ---------------------------------------------------------------------------
_PARTICULAS = {"da", "de", "do", "das", "dos", "d'", "di", "van", "von", "del"}

# Siglas/termos que o NER as vezes marca como PER e nunca sao nome de pessoa
_NUNCA_NOME = {
    "cpf", "rg", "pix", "ted", "doc", "cnpj", "fiap", "bank", "app", "sac",
    "att", "atenciosamente", "assinado", "obrigado", "obrigada", "ola", "olá",
    "oi", "bom", "boa", "prezado", "prezada", "cartao", "cartão", "conta",
    "agencia", "agência", "cliente", "gerente", "atendente", "visa",
    "mastercard", "elo", "boleto", "fatura", "extrato", "nome", "email", "e-mail",
}

# Gatilhos em que o que vem depois e uma assinatura: aceita nome minusculo
RE_GATILHO_ASSINATURA = re.compile(
    r"\b(?:assinado|att|atenciosamente|atte|abs|abra[cç]os|cordialmente|grato|grata)\b\s*[,.:\-]?\s*",
    _FLAGS,
)
# Gatilhos de apresentacao / papel: o proximo token tende a ser nome
RE_GATILHO_PESSOA = re.compile(
    r"\b(?:meu\s+nome\s+(?:completo\s+)?(?:e|é|eh)|me\s+chamo|nome\s+completo\s*:?"
    r"|sou\s+(?:o|a)(?:\s+(?:cliente|correntista|titular))?|sou"
    r"|(?:o|a)\s+(?:cliente|correntista|titular)"
    r"|cliente|correntista|titular|gerente|atendente|analista|consultora?|operadora?"
    r"|funcion[aá]ri[oa]|colaboradora?|supervisora?|sr\.?|sra\.?|srta\.?|senhora?|dr\.?|dra\.?"
    r"|reclama[cç][aã]o\s+(?:de|do|da)|em\s+nome\s+(?:de|do|da)|falei\s+com(?:\s+(?:o|a))?"
    r"|com\s+(?:o|a)|pel[oa])\s*[,:]?\s+",
    _FLAGS,
)

# Primeiros nomes brasileiros frequentes. Usado so em contexto de gatilho,
# para aceitar nome escrito em minusculo que o spaCy rotula como substantivo
# (ex.: "o atendente marcos"). Nao e lista dos exemplos do CSV.
_PRENOMES = set("""
ana maria joao joão jose josé antonio antônio francisco carlos paulo pedro lucas luiz luis luís marcos
gabriel rafael daniel marcelo bruno eduardo felipe raimundo rodrigo manoel mateus matheus andre andré
fernando fabio fábio leonardo gustavo guilherme leandro tiago thiago anderson ricardo marcio márcio
jorge sebastiao sebastião alexandre roberto edson diego vitor victor sergio sérgio claudio cláudio
julio júlio renato henrique igor caio vinicius vinícius murilo nicolas otavio otávio arthur artur
heitor davi enzo miguel samuel benjamin theo leticia letícia juliana adriana marcia márcia fernanda
patricia patrícia aline sandra camila amanda bruna jessica jéssica leticia julia júlia luciana
vanessa mariana gabriela vera beatriz larissa renata simone carla cristina daniela raquel tatiana
debora débora priscila natalia natália michele alice sofia laura helena valentina isabela isadora
manuela livia lívia rafaela bianca carolina paula elaine regina rosana silvia sílvia viviane yumi
karina kelly monica mônica eliane lucia lúcia fabiana claudia cláudia sabrina tamires thais thaís
""".split())

# Tokens que param a extensao de um nome capturado por gatilho
_POS_PARADA = {"VERB", "AUX", "ADV", "DET", "PRON", "CCONJ", "SCONJ", "NUM", "PUNCT", "SYM", "ADP"}


@lru_cache(maxsize=1)
def _carregar_spacy():
    """Carrega o melhor modelo pt disponivel. Retorna None se nao houver."""
    try:
        import spacy
    except Exception:
        return None
    candidatos = [os.environ.get("SPACY_MODEL")] if os.environ.get("SPACY_MODEL") else []
    candidatos += ["pt_core_news_lg", "pt_core_news_md", "pt_core_news_sm"]
    for nome in candidatos:
        try:
            return spacy.load(nome, disable=["lemmatizer"])
        except Exception:
            continue
    # Ultima tentativa: baixar o modelo pequeno
    try:
        from spacy.cli import download

        download("pt_core_news_sm")
        return spacy.load("pt_core_news_sm", disable=["lemmatizer"])
    except Exception:
        return None


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_PRENOMES_SA = {_sem_acento(p) for p in _PRENOMES}


def _e_marcador(tok_text: str) -> bool:
    return tok_text.upper() in {"NOME", "CPF", "RG", "CONTA", "EMAIL", "[", "]"}


def _token_pode_ser_nome(tok, permitir_minusculo: bool) -> bool:
    txt = tok.text
    base = _sem_acento(txt.lower())
    if not txt.isalpha() or base in _NUNCA_NOME or _e_marcador(txt):
        return False
    if txt[0].isupper():
        return tok.pos_ in {"PROPN", "NOUN", "ADJ", "X"} or tok.ent_type_ in {"PER", "LOC", "ORG", "MISC"}
    # minusculo
    if tok.pos_ == "PROPN" or tok.ent_type_ == "PER":
        return True
    if base in _PRENOMES_SA:
        return True
    return permitir_minusculo and tok.pos_ not in _POS_PARADA


def _estender_nome(doc, i: int, permitir_minusculo: bool, max_tokens: int = 6):
    """A partir do token i, devolve (ini_char, fim_char) do nome ou None."""
    if i >= len(doc) or not _token_pode_ser_nome(doc[i], permitir_minusculo):
        return None
    ini = doc[i].idx
    fim = doc[i].idx + len(doc[i].text)
    j = i + 1
    usados = 1
    while j < len(doc) and usados < max_tokens:
        t = doc[j]
        if t.text.lower() in _PARTICULAS and j + 1 < len(doc) and _token_pode_ser_nome(doc[j + 1], permitir_minusculo):
            fim = doc[j + 1].idx + len(doc[j + 1].text)
            j += 2
            usados += 2
            continue
        if _token_pode_ser_nome(t, permitir_minusculo) and (
            t.text[0].isupper() == doc[i].text[0].isupper() or t.pos_ == "PROPN" or t.ent_type_ == "PER"
        ):
            fim = t.idx + len(t.text)
            j += 1
            usados += 1
            continue
        break
    return ini, fim


def _spans_nomes_spacy(texto: str, nlp) -> list[tuple[int, int]]:
    doc = nlp(texto)
    spans: list[tuple[int, int]] = []

    # a) Entidades PER do NER, com filtro de falso positivo
    for ent in doc.ents:
        if ent.label_ != "PER":
            continue
        toks = [t for t in ent if not _e_marcador(t.text)]
        # remove pronomes de tratamento e tokens nao-nome das bordas
        while toks and (toks[0].pos_ not in {"PROPN"} or _sem_acento(toks[0].text.lower().rstrip(".")) in {"sr", "sra", "srta", "dr", "dra"}):
            toks = toks[1:]
        while toks and toks[-1].pos_ != "PROPN":
            toks = toks[:-1]
        if not toks:
            continue  # ex.: "Fui", "Achei", "otimo" marcados como PER
        # Palavra unica no inicio da frase ("Transfiram", "Encaminho") costuma
        # ser verbo capitalizado. So aceita se for prenome conhecido.
        if (
            len(toks) == 1
            and toks[0].is_sent_start
            and _sem_acento(toks[0].text.lower()) not in _PRENOMES_SA
        ):
            continue
        if any(_sem_acento(t.text.lower()) in _NUNCA_NOME for t in toks) and len(toks) == 1:
            continue
        spans.append((toks[0].idx, toks[-1].idx + len(toks[-1].text)))

    # b) Gatilhos de contexto
    for regex, minusc in ((RE_GATILHO_ASSINATURA, True), (RE_GATILHO_PESSOA, False)):
        for m in regex.finditer(texto):
            # primeiro token que comeca no fim do gatilho
            k = next((t.i for t in doc if t.idx >= m.end()), None)
            if k is None:
                continue
            if regex is RE_GATILHO_PESSOA:
                # Depois de um gatilho de papel ("cliente", "gerente", "com o"),
                # o primeiro token so conta como nome se o NER disser PER, se for
                # prenome conhecido, ou se for inicio de nome composto
                # (duas palavras PROPN capitalizadas). Evita "Cliente Premium",
                # "gerente Regional", "com o Itau".
                t0 = doc[k]
                t1 = doc[k + 1] if k + 1 < len(doc) else None
                composto = (
                    t0.text[:1].isupper() and t0.pos_ == "PROPN"
                    and t1 is not None and t1.text[:1].isupper() and t1.pos_ == "PROPN"
                    and t0.ent_type_ not in {"ORG", "LOC"}
                )
                if not (
                    t0.ent_type_ == "PER"
                    or _sem_acento(t0.text.lower()) in _PRENOMES_SA
                    or composto
                ):
                    continue
            span = _estender_nome(doc, k, permitir_minusculo=minusc)
            if span:
                spans.append(span)
    return spans


def _spans_nomes_sem_spacy(texto: str) -> list[tuple[int, int]]:
    """Fallback se o spaCy nao estiver instalado: so gatilhos + maiusculas."""
    spans = []
    nome_cap = r"[A-ZÀ-Ý][a-zà-ÿ]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý][a-zà-ÿ]+){0,5}"
    nome_min = r"[a-zà-ÿ]+(?:\s+[a-zà-ÿ]+){0,4}"
    for m in RE_GATILHO_PESSOA.finditer(texto):
        n = re.match(nome_cap, texto[m.end():])
        if n and _sem_acento(n.group(0).split()[0].lower()) not in _NUNCA_NOME:
            spans.append((m.end(), m.end() + n.end()))
    for m in RE_GATILHO_ASSINATURA.finditer(texto):
        n = re.match(nome_cap + "|" + nome_min, texto[m.end():])
        if n:
            spans.append((m.end(), m.end() + n.end()))
    return spans


def _unir(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    spans = sorted(s for s in spans if s[1] > s[0])
    out: list[list[int]] = []
    for a, b in spans:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [tuple(x) for x in out]


def _anonimizar_nomes(texto: str) -> str:
    nlp = _carregar_spacy()
    spans = _spans_nomes_spacy(texto, nlp) if nlp is not None else _spans_nomes_sem_spacy(texto)
    spans = _unir(spans)
    if not spans:
        return texto

    # Outras ocorrencias do mesmo nome (ex.: "Carlos Ferreira ... o Carlos")
    partes = set()
    for a, b in spans:
        for p in re.findall(r"[^\W\d_]+", texto[a:b]):
            if len(p) >= 3 and p.lower() not in _PARTICULAS and p[0].isupper():
                partes.add(p)
    extras = []
    for p in partes:
        for m in re.finditer(r"(?<![\w\[])" + re.escape(p) + r"(?![\w\]])", texto):
            extras.append(m.span())
    spans = _unir(spans + extras)

    saida, pos = [], 0
    for a, b in spans:
        saida.append(texto[pos:a])
        saida.append(M_NOME)
        pos = b
    saida.append(texto[pos:])
    # "[NOME] [NOME]" vira um marcador so
    return re.sub(r"\[NOME\](?:\s+\[NOME\])+", M_NOME, "".join(saida))


# ---------------------------------------------------------------------------
# API publica (assinatura fixa exigida pelo enunciado)
# ---------------------------------------------------------------------------
def anonimizar_texto(texto: str) -> str:
    """
    Recebe o texto original de uma manifestacao e retorna o texto com toda
    a informacao de identificacao pessoal (PII) substituida por um marcador
    do tipo [NOME], [CPF], [RG], [CONTA] ou [EMAIL].

    Parametros
    ----------
    texto : str
        Texto original, possivelmente contendo PII.

    Retorno
    -------
    str
        Texto anonimizado, pronto para exportacao externa.
    """
    if texto is None:
        return ""
    if not isinstance(texto, str):
        texto = str(texto)
    if not texto.strip():
        return texto
    # Ordem importa: estruturados antes dos nomes, para o NER nao confundir
    # "CPF 22233344455" com uma entidade e para os numeros ja estarem fora.
    texto = _anonimizar_estruturados(texto)
    texto = _anonimizar_nomes(texto)
    return texto


if __name__ == "__main__":
    exemplos = [
        "Meu nome e Carlos Eduardo Ferreira e identifiquei uma transacao.",
        "Segue print do erro. Att, gustavo lima araujo, CPF 22233344455.",
        "Trabalho na agencia 1123, conta 998877-2, e gostaria de revisar.",
        "Meu contrato esta em nome de Beatriz Cristina Monteiro, RG 12345678, conta 33445-5.",
        "Falei com a atendente Júlia e o gerente marcos, meu e-mail é x.y@banco.com.br.",
    ]
    for e in exemplos:
        print(e, "\n  ->", anonimizar_texto(e))
