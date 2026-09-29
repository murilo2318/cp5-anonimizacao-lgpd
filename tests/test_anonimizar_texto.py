"""Casos fora do CSV publico, para checar se a funcao generaliza.
Rodar com:  python -m pytest -q
"""
import pytest

from anonimizar_texto import anonimizar_texto as anon


@pytest.mark.parametrize("entrada, esperado", [
    ("Meu CPF é 321.654.987-10.", "Meu CPF é [CPF]."),
    ("cpf: 32165498710", "cpf: [CPF]"),
    ("RG nº 12.345.678-X", "RG nº [RG]"),
    ("identidade 501987654", "identidade [RG]"),
    ("ag. 0452 cc 00123-4", "ag. [CONTA] cc [CONTA]"),
    ("conta corrente nº 12.345-6", "conta corrente nº [CONTA]"),
    ("email: MARIA.SOUZA@Yahoo.com.br", "email: [EMAIL]"),
])
def test_identificadores_estruturados(entrada, esperado):
    assert anon(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    "Meu cartão final 1234 e o CEP 09010-160 estão corretos.",
    "Paguei R$ 1.234,56 no dia 12/05/2024.",
    "Paguei a conta de 1500 reais.",
    "Fui cobrado duas vezes na fatura.",
    "Achei ótimo o novo aplicativo.",
    "Tive problema com o Pix e com o Nubank.",
    "Sou Cliente Premium há anos.",
    "O gerente Regional não ajudou.",
])
def test_nao_mascara_texto_comum(entrada):
    assert anon(entrada) == entrada


@pytest.mark.parametrize("entrada, esperado", [
    ("Olá, sou a Mariana Lopes, cliente há 10 anos.", "Olá, sou a [NOME], cliente há 10 anos."),
    ("Quero falar com o Sr. Roberto Almeida.", "Quero falar com o Sr. [NOME]."),
    ("Falei com o atendente marcos na terça.", "Falei com o atendente [NOME] na terça."),
    ("Quero cancelar. att. fernanda", "Quero cancelar. att. [NOME]"),
    ("Atenciosamente, Luciana Martins", "Atenciosamente, [NOME]"),
])
def test_nomes(entrada, esperado):
    assert anon(entrada) == esperado


def test_entrada_vazia_e_none():
    assert anon("") == ""
    assert anon(None) == ""
