import io
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from fiscal_apuracao import (
    cnpjs_candidatos, apagar_dados_fiscais, apurar, dre_lucro_real, exportar_excel, importar_documentos, lancamentos_df,
    creditos_extras_df, reprocessar, salvar_config, carregar_config,
)
from fiscal_rules import ConfigFiscal, cfop_entrada, classificar
from fiscal_xml import XMLFiscalErro, ler_arquivos, ler_xml
from xml_exemplos import CLIENTE, EMPRESA, FORNECEDOR, _item, cte, nfe

CFG = ConfigFiscal(cnpjs=[EMPRESA])

COMPRA = nfe("35260822222222000122550010000000011000000011", FORNECEDOR, EMPRESA,
             [_item(1, "5102", 1000.0, 180.0, v_ipi=50.0)], total=1050.0)
VENDA = nfe("35260811111111000111550010000000021000000021", EMPRESA, CLIENTE,
            [_item(1, "5102", 2000.0, 360.0)], total=2000.0)
DEVOLUCAO = nfe("35260833333333000133550010000000031000000031", CLIENTE, EMPRESA,
                [_item(1, "5202", 500.0, 90.0)], fin="4", total=500.0)
FRETE_VENDA = cte("35260844444444000144570010000000041000000041", EMPRESA, CLIENTE, "0", 100.0, 12.0)
FRETE_COMPRA = cte("35260844444444000144570010000000051000000051", FORNECEDOR, EMPRESA, "3", 100.0, 12.0)
FRETE_TERCEIRO = cte("35260844444444000144570010000000061000000061", FORNECEDOR, EMPRESA, "0", 100.0, 12.0)


def _um(xml):
    (lanc,) = classificar(ler_xml(xml), CFG)
    return lanc


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine)()
    yield sessao
    sessao.close()


def test_leitura_nfe():
    doc = ler_xml(COMPRA)
    assert doc["tipo_documento"] == "NF-e"
    assert doc["chave"] == "35260822222222000122550010000000011000000011"
    assert doc["emitente_doc"] == FORNECEDOR
    assert doc["data_emissao"].isoformat() == "2026-08-10"
    item = doc["itens"][0]
    assert (item["cfop"], item["v_prod"], item["v_icms"], item["v_ipi"]) == ("5102", 1000.0, 180.0, 50.0)


def test_leitura_cte_tomador():
    doc = ler_xml(FRETE_VENDA)
    assert doc["tipo_documento"] == "CT-e"
    assert doc["tomador_doc"] == EMPRESA
    assert doc["valor_total"] == 100.0 and doc["v_icms"] == 12.0
    assert ler_xml(FRETE_COMPRA)["tomador_doc"] == EMPRESA


def test_xml_invalido():
    with pytest.raises(XMLFiscalErro):
        ler_xml("<nada/>")


def test_cfop_entrada():
    assert cfop_entrada("5102") == "1102"
    assert cfop_entrada("6403") == "2403"
    assert cfop_entrada("1202") == "1202"


def test_credito_compra_revenda():
    lanc = _um(COMPRA)
    assert lanc["direcao"] == "Entrada" and lanc["cfop"] == "1102"
    assert lanc["natureza"] == "Compra para revenda"
    assert lanc["icms_credito"] == pytest.approx(180.0)
    # base = mercadoria + IPI - ICMS (Lei 14.592/2023)
    assert lanc["base_pis_cofins"] == pytest.approx(870.0)
    assert lanc["pis_credito"] == pytest.approx(14.355)
    assert lanc["cofins_credito"] == pytest.approx(66.12)
    assert lanc["custo"] == pytest.approx(1050.0 - 180.0 - 14.355 - 66.12)


def test_credito_sem_exclusao_icms():
    cfg = ConfigFiscal(cnpjs=[EMPRESA], excluir_icms_base_credito=False)
    (lanc,) = classificar(ler_xml(COMPRA), cfg)
    assert lanc["base_pis_cofins"] == pytest.approx(1050.0)


def test_compra_com_st_sem_credito_icms():
    xml = nfe("35260822222222000122550010000000071000000071", FORNECEDOR, EMPRESA,
              [_item(1, "5403", 1000.0, 180.0, v_st=120.0)])
    lanc = _um(xml)
    assert lanc["cfop"] == "1403"
    assert lanc["icms_credito"] == 0.0
    assert lanc["pis_credito"] > 0


def test_fornecedor_monofasico_sem_credito_pis_cofins():
    xml = nfe("35260822222222000122550010000000081000000081", FORNECEDOR, EMPRESA,
              [_item(1, "5102", 1000.0, 180.0, cst_pis="04")])
    lanc = _um(xml)
    assert lanc["pis_credito"] == 0.0 and lanc["cofins_credito"] == 0.0
    assert "monofásico" in lanc["observacao"]


def test_uso_consumo_sem_credito():
    xml = nfe("35260822222222000122550010000000091000000091", FORNECEDOR, EMPRESA,
              [_item(1, "5556", 300.0, 54.0)])
    lanc = _um(xml)
    assert lanc["natureza"] == "Uso e consumo"
    assert lanc["icms_credito"] == lanc["pis_credito"] == 0.0


def test_debito_venda():
    lanc = _um(VENDA)
    assert lanc["direcao"] == "Saída" and lanc["natureza"] == "Venda"
    assert lanc["receita"] == pytest.approx(2000.0)
    assert lanc["icms_debito"] == pytest.approx(360.0)
    # STF Tema 69: ICMS fora da base
    assert lanc["pis_debito"] == pytest.approx(1640.0 * 0.0165)
    assert lanc["cofins_debito"] == pytest.approx(1640.0 * 0.076)


def test_devolucao_venda_gera_credito():
    lanc = _um(DEVOLUCAO)
    assert lanc["natureza"] == "Devolução de venda"
    assert lanc["icms_credito"] == pytest.approx(90.0)
    assert lanc["base_pis_cofins"] == pytest.approx(410.0)
    assert lanc["receita"] == pytest.approx(-500.0)


def test_cte_frete_venda_e_compra():
    venda = _um(FRETE_VENDA)
    assert venda["natureza"] == "Frete sobre vendas"
    assert venda["icms_credito"] == pytest.approx(12.0)
    assert venda["pis_credito"] == pytest.approx(1.65)
    assert venda["cofins_credito"] == pytest.approx(7.6)
    assert venda["custo"] == 0.0

    compra = _um(FRETE_COMPRA)
    assert compra["natureza"] == "Frete sobre compras"
    assert compra["custo"] == pytest.approx(100.0 - 12.0 - 1.65 - 7.6)


def test_cte_de_terceiro_sem_credito():
    lanc = _um(FRETE_TERCEIRO)
    assert lanc["natureza"] == "Frete não tomado pela empresa"
    assert lanc["icms_credito"] == lanc["pis_credito"] == 0.0


def test_nfe_de_outra_empresa_gera_erro():
    xml = nfe("35260822222222000122550010000000101000000101", FORNECEDOR, CLIENTE, [_item(1, "5102", 10.0, 1.8)])
    with pytest.raises(ValueError):
        classificar(ler_xml(xml), CFG)


def test_ler_arquivos_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("compra.xml", COMPRA)
        zf.writestr("frete.xml", FRETE_VENDA)
        zf.writestr("leia-me.txt", "ignorar")
    docs, erros = ler_arquivos([("lote.zip", buffer.getvalue()), ("ruim.xml", b"<x")])
    assert len(docs) == 2
    assert [nome for nome, _ in erros] == ["ruim.xml"]


def test_importacao_apuracao_e_dre(db):
    salvar_config(db, CFG)
    cfg = carregar_config(db)
    docs, _ = ler_arquivos([(f"{i}.xml", x.encode()) for i, x in enumerate(
        [COMPRA, VENDA, DEVOLUCAO, FRETE_VENDA, FRETE_COMPRA, FRETE_TERCEIRO, VENDA])])
    resumo = importar_documentos(db, docs, cfg)
    assert resumo == {"importados": 6, "duplicados": 1, "cancelados": 0, "erros": []}

    lanc = lancamentos_df(db)
    extras = creditos_extras_df(db)
    res = apurar(lanc, extras, saldo_icms_anterior=10.0)

    assert res["ICMS"]["debitos"] == pytest.approx(360.0)
    assert res["ICMS"]["creditos_documentos"] == pytest.approx(180.0 + 90.0 + 12.0 + 12.0)
    assert res["ICMS"]["a_recolher"] == pytest.approx(360.0 - 294.0 - 10.0)
    pis_creditos = 870 * 0.0165 + 410 * 0.0165 + 1.65 + 1.65
    assert res["PIS"]["creditos_documentos"] == pytest.approx(pis_creditos)

    tabela, ind = dre_lucro_real(lanc, extras, despesas={"ADS": 100.0})
    assert ind["receita_bruta"] == pytest.approx(2000.0)
    receita_liquida = 2000 - 500 - (360 - 90) - (1640 - 410) * (0.0165 + 0.076)
    assert ind["receita_liquida"] == pytest.approx(receita_liquida)
    cmv = (1050 - 180 - 870 * 0.0925) + (100 - 12 - 9.25)
    assert ind["cmv"] == pytest.approx(cmv)
    assert ind["lair"] == pytest.approx(receita_liquida - cmv - (100 - 12 - 9.25) - 100.0)
    assert ind["csll"] == pytest.approx(ind["lair"] * 0.09)
    assert exportar_excel({"DRE": tabela})[:2] == b"PK"

    # Mudar a configuração e reprocessar recalcula os créditos a partir do XML salvo
    assert reprocessar(db, ConfigFiscal(cnpjs=[EMPRESA], excluir_icms_base_credito=False)) == []
    compra = lancamentos_df(db).query("natureza == 'Compra para revenda'").iloc[0]
    assert compra["base_pis_cofins"] == pytest.approx(1050.0)


def test_irpj_adicional():
    import pandas as pd
    from fiscal_apuracao import CAMPOS_LANCAMENTO
    vazio = pd.DataFrame(columns=CAMPOS_LANCAMENTO)
    extras = pd.DataFrame(columns=["pis_credito", "cofins_credito", "icms_credito"])
    _, ind = dre_lucro_real(vazio, extras, meses=1, receitas_financeiras=100000.0)
    base = 100000 * (1 - 0.0465)
    assert ind["irpj"] == pytest.approx(base * 0.15 + (base - 20000) * 0.10)


def evento_cancelamento(chave):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00"><evento><infEvento Id="ID110111{chave}01">
  <chNFe>{chave}</chNFe><dhEvento>2026-08-11T09:00:00-03:00</dhEvento><tpEvento>110111</tpEvento>
</infEvento></evento></procEventoNFe>"""


def test_cancelamento_antes_e_depois(db):
    chave_venda = ler_xml(VENDA)["chave"]
    chave_compra = ler_xml(COMPRA)["chave"]
    docs, erros = ler_arquivos([("venda.xml", VENDA.encode()), ("canc.xml", evento_cancelamento(chave_venda).encode())])
    assert erros == []
    resumo = importar_documentos(db, docs, CFG)
    assert resumo["importados"] == 0 and resumo["cancelados"] == 1

    # Nota já importada e cancelada depois
    importar_documentos(db, ler_arquivos([("compra.xml", COMPRA.encode())])[0], CFG)
    assert len(lancamentos_df(db)) == 1
    resumo = importar_documentos(db, ler_arquivos([("c.xml", evento_cancelamento(chave_compra).encode())])[0], CFG)
    assert resumo["cancelados"] == 1
    assert lancamentos_df(db).empty

    # Reimportar a nota cancelada não traz ela de volta
    assert importar_documentos(db, ler_arquivos([("compra.xml", COMPRA.encode())])[0], CFG)["importados"] == 0


def test_outros_eventos_sao_ignorados():
    carta = evento_cancelamento("3526" + "0" * 40).replace("110111", "110110")
    docs, erros = ler_arquivos([("cce.xml", carta.encode())])
    assert docs == [] and erros == []


def test_xml_iso_8859_1_e_bom(db):
    latin = COMPRA.replace('encoding="UTF-8"', 'encoding="ISO-8859-1"').replace("Produto 1", "Encadernação")
    docs, erros = ler_arquivos([("latin.xml", latin.encode("latin-1")),
                                ("bom.xml", b"\xef\xbb\xbf" + VENDA.encode())])
    assert erros == []
    assert docs[0]["itens"][0]["descricao"] == "Encadernação"
    importar_documentos(db, docs, CFG)
    assert reprocessar(db, CFG) == []
    assert "Encadernação" in lancamentos_df(db)["descricao"].tolist()


def test_cnpjs_candidatos():
    docs, _ = ler_arquivos([(f"{i}.xml", x.encode()) for i, x in enumerate([COMPRA, VENDA, DEVOLUCAO, FRETE_VENDA])])
    assert cnpjs_candidatos(docs)[0][0] == EMPRESA


def test_apagar_dados_fiscais(db):
    importar_documentos(db, ler_arquivos([("compra.xml", COMPRA.encode())])[0], CFG)
    apagar_dados_fiscais(db)
    assert lancamentos_df(db).empty


def test_backup_e_restauracao():
    import database
    from database import SessionLocal, backup_banco, restaurar_banco
    from seed import seed_data
    seed_data()
    sessao = SessionLocal()
    importar_documentos(sessao, ler_arquivos([("compra.xml", COMPRA.encode())])[0], CFG)
    copia = backup_banco()
    apagar_dados_fiscais(sessao)
    assert lancamentos_df(sessao).empty
    sessao.close()

    restaurar_banco(copia)
    sessao = SessionLocal()
    assert len(lancamentos_df(sessao)) == 1
    sessao.close()
    with pytest.raises(ValueError):
        restaurar_banco(b"nao e banco")
    assert database.DB_PATH.endswith("teste.db")
