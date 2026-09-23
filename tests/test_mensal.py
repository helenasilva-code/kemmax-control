import os
import sqlite3
import subprocess
import sys
import tempfile

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cadastros import (
    SEM_MARKETPLACE, calcular_custo, despesas_df, marketplaces_df, produtos_custos_df, salvar_custos,
    salvar_despesas, salvar_marketplaces, seed_marketplaces, cadastrar_produtos,
)
from database import Base, Produto
from fiscal_apuracao import creditos_extras_df, importar_documentos, lancamentos_df
from fiscal_mensal import lucro_por_produto, meses_do_ano, resumo_completo, vendas_itens
from fiscal_rules import ConfigFiscal
from fiscal_xml import ler_arquivos, ler_xml
from xml_exemplos import CLIENTE, EMPRESA, FORNECEDOR, _item, nfe

CFG = ConfigFiscal(cnpjs=[EMPRESA])
ML = "03007331000141"
MESES = ["2026-07", "2026-08"]

COMPRA_JUL = nfe("35260722222222000122550010000000011000000011", FORNECEDOR, EMPRESA,
                 [_item(1, "5102", 1000.0, 180.0, codigo="FORN-9")], data="2026-07-10")
VENDA_AGO = nfe("35260811111111000111550010000000021000000021", EMPRESA, CLIENTE,
                [_item(1, "5102", 2000.0, 360.0, codigo="P1", q=10)], intermediador=ML)
DEVOL_AGO = nfe("35260833333333000133550010000000031000000031", CLIENTE, EMPRESA,
                [_item(1, "5202", 400.0, 72.0, codigo="P1", q=2)], fin="4", data="2026-08-20",
                ref="35260811111111000111550010000000021000000021")


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine)()
    seed_marketplaces(sessao)
    mkts = marketplaces_df(sessao)
    mkts.loc[mkts["nome"] == "Mercado Livre", ["comissao_pct", "taxa_fixa", "frete_medio"]] = [0.12, 1.0, 2.0]
    salvar_marketplaces(sessao, mkts)
    sessao.add(Produto(sku="P1", nome="Produto 1", cmv_normal=50.0, cmf_kemmax=60.0, embalagem_unit=1.0))
    sessao.commit()
    salvar_despesas(sessao, pd.DataFrame([{"mes": "2026-08", "ads": 100.0, "pessoal": 0, "despesas_fixas": 0,
                                           "servicos": 0, "outras": 0, "receitas_financeiras": 0,
                                           "despesas_financeiras": 0}]))
    docs, erros = ler_arquivos([(f"{i}.xml", x.encode()) for i, x in enumerate([COMPRA_JUL, VENDA_AGO, DEVOL_AGO])])
    assert erros == []
    importar_documentos(sessao, docs, CFG)
    yield sessao
    sessao.close()


def _resumo(db, **kw):
    return resumo_completo(lancamentos_df(db), creditos_extras_df(db), produtos_custos_df(db), marketplaces_df(db),
                           despesas_df(db, MESES), MESES, **kw)


def _linha(tabela, rotulo, coluna):
    return float(tabela.loc[tabela["Linha"] == rotulo, coluna].iloc[0])


def test_leitura_intermediador_e_referencia():
    venda = ler_xml(VENDA_AGO)
    assert venda["intermediador_doc"] == ML
    devol = ler_xml(DEVOL_AGO)
    assert devol["chave_ref"] == venda["chave"]
    assert devol["itens"][0]["quantidade"] == 2


def test_lucro_por_produto(db):
    itens = _resumo(db)["itens"]
    venda = itens[itens["quantidade"] > 0].iloc[0]
    assert venda["marketplace"] == "Mercado Livre"
    assert venda["impostos"] == pytest.approx(360 + 1640 * 0.0925)
    assert venda["comissao"] == pytest.approx(2000 * 0.12 + 10 * 1.0)
    assert venda["lucro_dre"] == pytest.approx(2000 - 511.7 - 250 - 20 - 10 - 500)
    assert venda["lucro_financeiro"] == pytest.approx(708.3 - 100)

    devol = itens[itens["quantidade"] < 0].iloc[0]
    assert devol["marketplace"] == "Mercado Livre"  # herdado da venda original
    assert devol["comissao"] == pytest.approx(-400 * 0.12 - 2 * 1.0)

    produto = lucro_por_produto(itens).iloc[0]
    assert produto["quantidade"] == 8
    assert produto["lucro_dre"] == pytest.approx(560.64)
    assert produto["lucro_financeiro"] == pytest.approx(560.64 - 80)
    assert produto["resultado"] == "Lucro"


def test_produto_sem_custo_e_sem_marketplace():
    lanc = pd.DataFrame([{
        "chave": "x", "tipo_documento": "NF-e", "data": pd.Timestamp("2026-08-01").date(), "natureza": "Venda",
        "intermediador": "", "chave_ref": "", "codigo": "NOVO", "descricao": "Novo", "quantidade": 1.0,
        "receita": 100.0, "icms_debito": 0.0, "difal": 0.0, "pis_debito": 0.0, "cofins_debito": 0.0,
        "icms_credito": 0.0, "pis_credito": 0.0, "cofins_credito": 0.0}])
    mkts = pd.DataFrame([{"nome": SEM_MARKETPLACE, "cnpj_intermediador": "", "comissao_pct": 0.0,
                          "taxa_fixa": 0.0, "frete_medio": 0.0}])
    prods = pd.DataFrame(columns=["sku", "nome", "cmv_normal", "cmf_kemmax", "embalagem_unit"])
    itens = vendas_itens(lanc, prods, mkts)
    assert itens.iloc[0]["marketplace"] == SEM_MARKETPLACE
    assert lucro_por_produto(itens).iloc[0]["resultado"] == "Sem custo cadastrado"


def test_apuracao_com_saldo_credor_transportado(db):
    ap = _resumo(db)["apuracao"]
    assert _linha(ap, "ICMS - A recolher", "Jul/26") == 0
    assert _linha(ap, "ICMS - Saldo credor p/ próximo mês", "Jul/26") == pytest.approx(180)
    assert _linha(ap, "ICMS - (-) Saldo credor anterior", "Ago/26") == pytest.approx(180)
    assert _linha(ap, "ICMS - A recolher", "Ago/26") == pytest.approx(360 - 72 - 180)
    ap = _resumo(db, saldos_iniciais={"ICMS": 50})["apuracao"]
    assert _linha(ap, "ICMS - Saldo credor p/ próximo mês", "Jul/26") == pytest.approx(230)


def test_dre_mensal(db):
    dre = _resumo(db)["dre"]
    assert _linha(dre, "Receita bruta de vendas", "Ago/26") == pytest.approx(2000)
    assert _linha(dre, "= Receita líquida", "Ago/26") == pytest.approx(1600 - 288 - 1312 * 0.0925)
    assert _linha(dre, "(-) CMV DRE (custo cadastrado x vendas)", "Ago/26") == pytest.approx(-400)
    lair = 1190.64 - 400 - 200 - 20 - 10 - 100
    assert _linha(dre, "= Lucro antes do IR e CSLL (LAIR)", "Ago/26") == pytest.approx(lair)
    liquido = lair * (1 - 0.09 - 0.15)
    assert _linha(dre, "= Lucro líquido (DRE)", "Ago/26") == pytest.approx(liquido)
    assert _linha(dre, "= Resultado financeiro (caixa)", "Ago/26") == pytest.approx(liquido - 80)
    assert _linha(dre, "Receita bruta de vendas", "Total") == pytest.approx(2000)

    dre = _resumo(db, cmv_pelo_cadastro=False)["dre"]
    custo_compra = 1000 - 180 - 820 * 0.0925
    assert _linha(dre, "(-) CMV DRE (compras líquidas)", "Jul/26") == pytest.approx(-custo_compra)


def test_tabelas_compras_vendas_cte(db):
    r = _resumo(db)
    assert _linha(r["compras"], "Notas de compra (qtde)", "Jul/26") == 1
    assert _linha(r["compras"], "Crédito ICMS", "Jul/26") == pytest.approx(180)
    assert _linha(r["vendas"], "Vendas Mercado Livre", "Ago/26") == pytest.approx(2000)
    assert _linha(r["vendas"], "Unidades vendidas", "Ago/26") == 10
    assert _linha(r["cte"], "CT-e (qtde)", "Total") == 0


def test_calcular_custo():
    c = calcular_custo(100.0, 0.10, 0.18, 20.0, 5.0, CFG)
    assert c["credito_pis_cofins"] == pytest.approx(97 * 0.0925)
    assert c["cmv_dre"] == pytest.approx(115 - 18 - 97 * 0.0925)
    assert c["cmv_financeiro"] == pytest.approx(c["cmv_dre"] + 20)
    assert c["custo_caixa"] == pytest.approx(135)


def test_salvar_custos_calcula_e_remove(db):
    df = produtos_custos_df(db)
    novo = {"sku": "P2", "nome": None, "valor_nf": 100.0, "ipi_pct": 0.10, "icms_pct": 0.18,
            "valor_por_fora": 20.0, "frete_unit": 5.0, "embalagem_unit": None, "cmv_normal": None,
            "cmf_kemmax": None, "custo_caixa": None}
    vazio = {k: None for k in novo}
    df = pd.concat([df, pd.DataFrame([novo, vazio])], ignore_index=True)
    assert salvar_custos(db, df, CFG) == 0
    p2 = db.query(Produto).filter_by(sku="P2").one()
    assert p2.nome == "P2"
    assert p2.cmf_kemmax == pytest.approx(calcular_custo(100, 0.1, 0.18, 20, 5, CFG)["cmv_financeiro"])
    assert db.query(Produto).filter_by(sku="0").first() is None

    assert salvar_custos(db, df[df["sku"] == "P2"], CFG) == 1
    assert [p.sku for p in db.query(Produto)] == ["P2"]
    assert cadastrar_produtos(db, [("P2", "x"), ("p3 ", "Três")]) == 1


def test_meses_do_ano():
    from datetime import date
    assert meses_do_ano(2026, date(2026, 3, 5)) == ["2026-01", "2026-02", "2026-03"]
    assert len(meses_do_ano(2025, date(2026, 3, 5))) == 12


def test_migracao_de_banco_antigo():
    caminho = os.path.join(tempfile.mkdtemp(), "antigo.db")
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE lancamentos_fiscais (id INTEGER PRIMARY KEY, chave VARCHAR, descricao VARCHAR)")
    con.execute("INSERT INTO lancamentos_fiscais (chave, descricao) VALUES ('c', 'antigo')")
    con.execute("CREATE TABLE produtos (id INTEGER PRIMARY KEY, sku VARCHAR, cmv_normal FLOAT)")
    con.commit()
    con.close()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run([sys.executable, "-c", "import database"], cwd=raiz, check=True,
                   env={**os.environ, "KEMMAX_DB": caminho})
    con = sqlite3.connect(caminho)
    colunas = {r[1] for r in con.execute("PRAGMA table_info(lancamentos_fiscais)")}
    assert {"codigo", "quantidade", "intermediador", "chave_ref"} <= colunas
    assert con.execute("SELECT quantidade, descricao FROM lancamentos_fiscais").fetchone() == (0.0, "antigo")
    assert "valor_por_fora" in {r[1] for r in con.execute("PRAGMA table_info(produtos)")}
    con.close()
