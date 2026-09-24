"""Teste do KemmaxGestao.html no navegador (Chromium via Playwright). Pulado se não houver Playwright."""
import glob
import io
import os
import zipfile

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from xml_exemplos import CLIENTE, EMPRESA, FORNECEDOR, _item, cte, nfe  # noqa: E402

HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "KemmaxGestao.html")
ML = "03007331000141"
CHAVE_VENDA = "35260811111111000111550010000000021000000021"


def _zip(tmp_path):
    compra = nfe("35260722222222000122550010000000011000000011", FORNECEDOR, EMPRESA,
                 [_item(1, "5102", 1000.0, 180.0, codigo="FORN-9")], data="2026-07-10")
    venda = nfe(CHAVE_VENDA, EMPRESA, CLIENTE, [_item(1, "5102", 2000.0, 360.0, codigo="P1", q=10)], intermediador=ML)
    devol = nfe("35260833333333000133550010000000031000000031", CLIENTE, EMPRESA,
                [_item(1, "5202", 400.0, 72.0, codigo="P1", q=2)], fin="4", data="2026-08-20", ref=CHAVE_VENDA)
    frete = cte("35260844444444000144570010000000041000000041", EMPRESA, CLIENTE, "0", 100.0, 12.0) \
        .replace("35260811111111000111550010000000011000000011", CHAVE_VENDA)
    caminho = tmp_path / "agosto.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Mercado Livre/compra.xml", compra)
        zf.writestr("Mercado Livre/venda.xml", venda)
        zf.writestr("ERP/venda-copia.xml", venda)
        zf.writestr("Meli/devolucao.xml", devol)
        zf.writestr("Meli/retorno-full.xml",
                    nfe("35260703007331000141550010000000771000000077", "03007331000141", EMPRESA,
                        [_item(1, "6907", 5000.0, 0.0, codigo="POLA405")], data="2026-07-15"))
        zf.writestr("Canceladas/venda-cancelada.xml",
                    nfe("35260811111111000111550010000000991000000099", EMPRESA, CLIENTE, [_item(1, "5102", 999.0, 0.0)]))
        interno = io.BytesIO()
        with zipfile.ZipFile(interno, "w", zipfile.ZIP_DEFLATED) as z2:
            z2.writestr("cte/frete.xml", frete)
        zf.writestr("fretes.zip", interno.getvalue())
    return str(caminho)


def _valor(page, seletor):
    texto = page.inner_text(seletor)
    return float(texto.replace("R$", "").replace("\xa0", "").replace(".", "").replace(",", ".").strip())


def _linha(page, rotulo, coluna):
    return page.evaluate("""([r,c])=>{let t=window._dre;let i=t.linhas.findIndex(l=>l[0]===r);return t.linhas[i][1][t.ms.indexOf(c)]}""",
                         [rotulo, coluna])


def test_html_completo(tmp_path):
    chromium = glob.glob("/opt/pw-browsers/chromium*/chrome-linux*/chrome")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium[0] if chromium else None)
        page = browser.new_page()
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.goto("file://" + HTML)
        page.wait_for_function("window.document.querySelector('#month').options.length>0")

        page.click("text=Importações")
        page.set_input_files("#files", _zip(tmp_path))
        page.click("#registerImport")
        page.wait_for_selector("text=Importação concluída.")
        resultado = page.inner_text("#importResult")
        assert "5 novos" in resultado and "1 repetidos" in resultado and "1 cancelamentos" in resultado
        assert EMPRESA in resultado  # CNPJ definido automaticamente

        page.click("text=Canais e Tarifas")
        page.fill("#chName", "Mercado Livre")
        page.fill("#chPct", "12")
        page.fill("#chFixed", "1")
        page.click("#addChannel")

        page.click("text=Produtos e Custos")
        page.fill("#sku", "P1")
        page.fill("#purchase", "50")
        page.fill("#outside", "10")
        page.click("#addProd")
        assert "CMV Financeiro R$ 60,00" in page.inner_text("#prodMsg").replace("\xa0", " ")

        page.click("text=Financeiro / Extrato")
        page.fill("#expMonth", "2026-08")
        page.fill("#expVal", "100")
        page.click("#addExp")

        page.select_option("#month", "2026-08")
        page.click("text=Dashboard")
        assert _valor(page, "#kFat") == pytest.approx(2000)
        assert _valor(page, "#kFrete") == pytest.approx(78.75)
        assert _valor(page, "#kCred") == pytest.approx(21.25)
        cred = page.inner_text("#dashCred")
        assert "CT-e (fretes)" in cred and "Devoluções de venda" in cred

        page.click("text=CT-e e Créditos")
        assert _valor(page, "#cteIcms") == pytest.approx(12)
        assert _valor(page, "#ctePis") == pytest.approx(1.65)
        assert _valor(page, "#cteCof") == pytest.approx(7.6)
        assert "Ago/26" in page.inner_text("#cteMes")
        page.click("text=Dashboard")

        page.click("text=Rentabilidade por Produto")
        assert _valor(page, "#rRes") == pytest.approx(590.64 - 78.75, abs=0.01)
        assert _valor(page, "#rFin") == pytest.approx(590.64 - 78.75 - 80, abs=0.01)
        assert "Mercado Livre" in page.inner_text("#rentChannel")

        page.click("text=DRE Mensal")
        assert _linha(page, "= Receita líquida", "2026-08") == pytest.approx(1190.64, abs=0.01)
        assert _linha(page, "(−) CMV DRE", "2026-08") == pytest.approx(-400)
        assert _linha(page, "= Margem de contribuição", "2026-08") == pytest.approx(511.89, abs=0.01)
        lair = 511.89 - 100
        assert _linha(page, "= Resultado antes IRPJ/CSLL", "2026-08") == pytest.approx(lair, abs=0.01)
        assert _linha(page, "= Lucro líquido (DRE)", "2026-08") == pytest.approx(lair * 0.76, abs=0.01)

        page.click("text=CT-e e Créditos")
        page.select_option("#cteBaseRegra", "sem_icms")
        assert _valor(page, "#ctePis") == pytest.approx(88 * 0.0165, abs=0.01)
        page.select_option("#cteBaseRegra", "integral")
        assert _valor(page, "#ctePis") == pytest.approx(1.65)

        page.click("text=Apuração Impostos")
        assert "ICMS — Débitos (vendas)" in page.inner_text("#apBody")
        apur = page.evaluate("window._apur.linhas.filter(l=>l[0].startsWith('ICMS — A recolher'))[0][1]")
        assert apur[6] == pytest.approx(0) and apur[7] == pytest.approx(360 - 72 - 12 - 180)

        page.click("text=NF de Venda")
        page.click("#vdAbas >> text=Vendas para SP")
        assert page.inner_text("#vdN") == "1" and _valor(page, "#vdV") == pytest.approx(2000)
        page.click("#vdAbas >> text=Vendas para outros estados")
        assert page.inner_text("#vdN") == "0"
        page.click("#vdAbas >> text=Todas")
        assert page.inner_text("#vdN") == "1"
        assert _valor(page, "#vdV") == pytest.approx(2000)
        assert _valor(page, "#vdD") == pytest.approx(400)
        assert "Devolução" in page.inner_text("#vdBody")
        page.click("#vdBody tr.nf >> nth=0")
        assert "P1 — Produto 1" in page.inner_text("#vdBody")
        page.select_option("#vdTipo", "Venda")
        assert "Devolução" not in page.inner_text("#vdBody")
        page.fill("#vdBusca", "nao-existe")
        assert "Nenhuma NF de venda" in page.inner_text("#vdBody")
        page.fill("#vdBusca", "")

        page.click("text=NF de Compra")
        page.select_option("#month", "2026-07")
        assert _valor(page, "#cpC") == pytest.approx(180 + 820 * 0.0925)
        assert _valor(page, "#cpIcms") == pytest.approx(180)
        assert _valor(page, "#cpPis") == pytest.approx(820 * 0.0165)
        assert _valor(page, "#cpCof") == pytest.approx(820 * 0.076)
        assert _valor(page, "#cpBase") == pytest.approx(820)
        mes = page.inner_text("#cpMes")
        assert "Jul/26" in mes and "Total no ano" in mes
        jul = page.evaluate("window._cpMes.find(r=>r.m==='2026-07')")
        assert jul["docs"] == 1 and jul["vc"] == pytest.approx(1000) and jul["oDocs"] == 1 and jul["oVc"] == pytest.approx(5000)
        assert "Retorno de depósito / armazém (FULL)" in page.inner_text("#cpNat")
        page.click("#cpBody tr.nf >> nth=0")
        assert "FORN-9" in page.inner_text("#cpBody")
        assert "Total (1 notas)" in page.inner_text("#cpBody")
        page.select_option("#cpTipo", "outras")
        assert "Retorno de depósito" in page.inner_text("#cpBody") and "FORN-9" not in page.inner_text("#cpBody")
        page.select_option("#cpTipo", "")
        assert "Total (2 notas)" in page.inner_text("#cpBody")

        # recarregar: dados persistem no IndexedDB
        page.reload()
        page.wait_for_function("window.document.querySelector('#month').options.length>0")
        page.select_option("#month", "2026-08")
        assert _valor(page, "#kFat") == pytest.approx(2000)
        assert erros == []
        browser.close()


def test_html_reducao_base_e_difal(tmp_path):
    compra = nfe("35260822222222000122550010000000091000000091", FORNECEDOR, EMPRESA,
                 [_item(1, "5102", 10000.0, 880.0, codigo="MAQ-F", q=5, p_red=26.67, p_icms=12, ncm="84411090")],
                 data="2026-08-02")
    venda = nfe("35260811111111000111550010000000081000000081", EMPRESA, CLIENTE,
                [_item(1, "6108", 3000.0, 264.0, codigo="EXA4", q=1, p_red=26.67, p_icms=12, ncm="84401090",
                       difal=(246.0, 60.0, 20.5, 12.0))], uf_dest="BA", intermediador=ML)
    caminho = tmp_path / "reducao.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("compra.xml", compra)
        zf.writestr("venda.xml", venda)
    chromium = glob.glob("/opt/pw-browsers/chromium*/chrome-linux*/chrome")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium[0] if chromium else None)
        page = browser.new_page()
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.goto("file://" + HTML)
        page.wait_for_function("window.document.querySelector('#month').options.length>0")
        page.click("text=Importações")
        page.set_input_files("#files", str(caminho))
        page.click("#registerImport")
        page.wait_for_selector("text=Importação concluída.")
        # documentos lidos por versão anterior (sem NCM) são atualizados ao reimportar, sem duplicar
        page.evaluate("Object.values(db.docs).forEach(d=>{delete d.v;d.it&&d.it.forEach(i=>delete i.ncm)})")
        page.click("#registerImport")
        page.wait_for_function("document.querySelector('#importResult').innerText.includes('atualizados')")
        assert "2 atualizados" in page.inner_text("#importResult")
        assert page.evaluate("Object.keys(db.docs).length") == 2
        page.select_option("#month", "2026-08")

        page.click("text=NF de Venda")
        page.click("#vdAbas >> text=Vendas para SP")
        assert page.inner_text("#vdN") == "0"
        page.click("#vdAbas >> text=Vendas para outros estados")
        assert page.inner_text("#vdN") == "1" and "BA" in page.inner_text("#vdBody")
        page.click("#vdAbas >> text=Todas")
        uf = page.inner_text("#vdUf").replace("\xa0", " ")
        assert "BA" in uf and "R$ 246,00" in uf and "R$ 60,00" in uf and "R$ 306,00" in uf
        page.click("#vdBody tr.nf >> nth=0")
        detalhe = page.inner_text("#vdBody")
        assert "NCM 8440.10.90 (redução Conv. 52/91)" in detalhe
        assert "redução da base 26,67%" in detalhe and "carga efetiva 8,8%" in detalhe
        assert "interna 20,5% − interestadual 12%" in detalhe

        page.click("text=NF de Compra")
        assert _valor(page, "#cpIcms") == pytest.approx(880)
        assert _valor(page, "#cpBase") == pytest.approx(10000 - 880)

        page.click("text=Auditoria")
        audit = page.inner_text("#auditText")
        assert "Itens com redução da base de ICMS (CST 20/70): 2" in audit and "8,8%" in audit
        assert "Conferência dos NCMs com redução de base" in audit
        linhas = [l for l in audit.splitlines() if "8440.10.90" in l or "8441.10.90" in l]
        venda_l = [l for l in linhas if l.startswith("Venda")][0]
        compra_l = [l for l in linhas if l.startswith("Compra")][0]
        assert "SP→BA" in venda_l and "5,14%" in venda_l and "Destacado acima" in venda_l
        assert "R$ 109,80" in venda_l.replace("\xa0", " ")
        assert "SP→SP" in compra_l and "OK" in compra_l

        page.click("text=Produtos e Custos")
        page.fill("#purchase", "100")
        page.fill("#icmspct", "12")
        page.fill("#icmsred", "26.67")
        assert page.input_value("#icmscarga").startswith("8,79")
        page.click("#calcCred")
        assert float(page.input_value("#icmscred")) == pytest.approx(8.80, abs=0.01)
        assert float(page.input_value("#piscred")) == pytest.approx((100 - 8.7996) * 0.0165, abs=0.01)
        assert erros == []
        browser.close()


def test_html_cancelamentos(tmp_path):
    compra = nfe("35260822222222000122550010000075151000075151", FORNECEDOR, EMPRESA,
                 [_item(1, "5102", 1850.0, 0.0, codigo="COFRE")], data="2026-08-05")
    compra2 = nfe("35260822222222000122550010000075161000075161", FORNECEDOR, EMPRESA,
                  [_item(1, "5102", 500.0, 60.0, codigo="X")], data="2026-08-06")
    # nota cujo protocolo já vem como cancelada (cStat 101)
    compra3 = nfe("35260822222222000122550010000075171000075171", FORNECEDOR, EMPRESA,
                  [_item(1, "5102", 700.0, 84.0, codigo="Y")], data="2026-08-07") \
        .replace("</NFe>", "</NFe><protNFe><infProt><chNFe>35260822222222000122550010000075171000075171</chNFe><cStat>101</cStat></infProt></protNFe>")
    # resumo da SEFAZ (distribuição DF-e) informando a nota 7516 como cancelada
    resumo = ('<resNFe xmlns="http://www.portalfiscal.inf.br/nfe"><chNFe>35260822222222000122550010000075161000075161</chNFe>'
              '<cSitNFe>3</cSitNFe></resNFe>')
    caminho = tmp_path / "canc.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("compra.xml", compra)
        zf.writestr("compra2.xml", compra2)
        zf.writestr("compra3.xml", compra3)
        zf.writestr("resumo.xml", resumo)
    chromium = glob.glob("/opt/pw-browsers/chromium*/chrome-linux*/chrome")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium[0] if chromium else None)
        page = browser.new_page()
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.goto("file://" + HTML)
        page.wait_for_function("window.document.querySelector('#month').options.length>0")
        page.evaluate(f"db.config.cnpjs=['{EMPRESA}']")
        page.click("text=Importações")
        page.set_input_files("#files", str(caminho))
        page.click("#registerImport")
        page.wait_for_selector("text=Importação concluída.")
        assert "2 cancelamentos" in page.inner_text("#importResult")
        assert page.evaluate("Object.keys(db.docs).length") == 1
        page.select_option("#month", "2026-08")

        page.click("text=NF de Compra")
        assert _valor(page, "#cpV") == pytest.approx(1850)
        page.click("#cpBody >> text=marcar cancelada")
        assert _valor(page, "#cpV") == pytest.approx(0)

        page.click("text=Auditoria")
        audit = page.inner_text("#auditText")
        assert "Marcada manualmente" in audit and "Protocolo SEFAZ: cancelada (cStat 101)" in audit
        assert "Resumo SEFAZ: cancelada" in audit and "0 cancelamento(s) recebidos sem a nota importada" in audit
        page.click("#auditText >> tr:has-text('Marcada manualmente') >> text=Restaurar")
        page.click("text=NF de Compra")
        assert _valor(page, "#cpV") == pytest.approx(1850)
        assert erros == []
        browser.close()


def test_html_lixeira(tmp_path):
    compra = nfe("35260822222222000122550010000080011000080011", FORNECEDOR, EMPRESA,
                 [_item(1, "5102", 1000.0, 120.0, codigo="A")], data="2026-08-05")
    retorno1 = nfe("35260803007331000141550010000080021000080021", "03007331000141", EMPRESA,
                   [_item(1, "6907", 4000.0, 0.0, codigo="B")], data="2026-08-06")
    retorno2 = nfe("35260803007331000141550010000080031000080031", "03007331000141", EMPRESA,
                   [_item(1, "6907", 3000.0, 0.0, codigo="C")], data="2026-08-07")
    caminho = tmp_path / "lix.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, x in enumerate([compra, retorno1, retorno2]):
            zf.writestr(f"{i}.xml", x)
    chromium = glob.glob("/opt/pw-browsers/chromium*/chrome-linux*/chrome")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium[0] if chromium else None)
        page = browser.new_page()
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.goto("file://" + HTML)
        page.wait_for_function("window.document.querySelector('#month').options.length>0")
        page.evaluate(f"db.config.cnpjs=['{EMPRESA}']")

        def importar():
            page.click("text=Importações")
            page.set_input_files("#files", str(caminho))
            page.click("#registerImport")
            page.wait_for_selector("text=Importação concluída.")
            return page.inner_text("#importResult")

        importar()
        page.select_option("#month", "2026-08")
        ndocs = "Object.keys(db.docs).length"

        # excluir uma nota
        page.click("text=NF de Compra")
        page.click("#cpBody >> text=excluir")
        assert page.evaluate(ndocs) == 2 and _valor(page, "#cpV") == pytest.approx(0)
        # reimportar não traz de volta
        assert "1 na Lixeira (ignorados)" in importar()
        assert page.evaluate(ndocs) == 2
        assert "Excluída manualmente" in page.inner_text("#lixBody")
        page.click("#lixBody >> text=Restaurar")
        assert page.evaluate(ndocs) == 3

        # excluir em lote só as outras entradas (retornos do FULL)
        page.click("text=NF de Compra")
        page.select_option("#cpTipo", "outras")
        page.click("#compras >> text=Excluir notas listadas")
        assert page.evaluate(ndocs) == 1
        page.click("text=Importações")
        page.click("#lixRestTodos")
        assert page.evaluate(ndocs) == 3
        # excluir pela natureza no quadro "Por natureza"
        page.click("text=NF de Compra")
        page.click("#cpNat tr:has-text('Retorno de depósito') >> text=excluir todas")
        assert page.evaluate(ndocs) == 1
        page.select_option("#cpTipo", "compras")
        assert _valor(page, "#cpV") == pytest.approx(1000)

        # excluir o mês inteiro e apagar definitivamente
        page.click("text=Importações")
        page.click("#docsBody >> text=excluir mês")
        assert page.evaluate(ndocs) == 0
        page.click("#lixApagarTodos")
        assert page.evaluate("Object.values(db.trash).every(t=>t.apagada&&!t.doc)")
        assert "3 na Lixeira (ignorados)" in importar()
        page.click("#lixLiberar")
        assert "3 novos" in importar()

        page.click("#importsBody >> text=remover do histórico >> nth=0")
        assert page.evaluate("db.imports.length") == 3
        assert erros == []
        browser.close()


OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL<BANKACCTFROM><BANKID>0341<ACCTID>12345-6</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20260801<DTEND>20260831
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260803120000[-03:EST]<TRNAMT>-45.90<FITID>A1<MEMO>TARIFA PACOTE SERVICOS
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260804<TRNAMT>12500.00<FITID>A2<MEMO>PIX RECEBIDO MERCADO PAGO IP
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260805<TRNAMT>-389.77<FITID>A3<MEMO>PAG CONTA ENEL SP
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260806<TRNAMT>-1500.00<FITID>A4<MEMO>PIX ENVIADO JOAO DA SILVA
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260807<TRNAMT>-800.00<FITID>A5<MEMO>DARF SIMPLES
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""

CSV_BANCO = """Extrato conta corrente - Banco X
Agência;Conta
1234;99999-0

Data;Histórico;Documento;Débito (R$);Crédito (R$);Saldo (R$)
31/07/2026;SALDO ANTERIOR;;;;10.000,00
10/08/2026;"PAGTO FACEBK *ADS; CAMPANHA";111;1.234,56;;8.765,44
11/08/2026;RENDIMENTO APLIC AUTOMATICA;;;12,34;8.777,78
12/08/2026;PIX ENVIADO JOAO DA SILVA;222;1.500,00;;7.277,78
"""


def test_html_extrato(tmp_path):
    (tmp_path / "itau.ofx").write_text(OFX, encoding="latin-1")
    (tmp_path / "bancox.csv").write_text(CSV_BANCO, encoding="latin-1")
    chromium = glob.glob("/opt/pw-browsers/chromium*/chrome-linux*/chrome")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium[0] if chromium else None)
        page = browser.new_page()
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("dialog", lambda d: d.accept(d.default_value) if d.type == "prompt" else d.accept())
        page.goto("file://" + HTML)
        page.wait_for_function("window.document.querySelector('#month').options.length>0")
        page.click("text=Financeiro / Extrato")
        page.set_input_files("#bkFiles", [str(tmp_path / "itau.ofx"), str(tmp_path / "bancox.csv")])
        page.click("#bkImport")
        page.wait_for_function("document.querySelector('#bkResult').innerText.includes('bancox.csv')")
        res = page.inner_text("#bkResult")
        assert "itau.ofx: 5 lançamentos lidos" in res and "bancox.csv: 3 lançamentos lidos" in res
        page.select_option("#month", "2026-08")

        cat = page.evaluate("Object.fromEntries(Object.values(db.bank).map(t=>[t.desc,t.cat]))")
        assert cat["TARIFA PACOTE SERVICOS"] == "Despesas financeiras"
        assert cat["PIX RECEBIDO MERCADO PAGO IP"] == "Recebimento de vendas / marketplace"
        assert cat["PAG CONTA ENEL SP"] == "Despesas fixas"
        assert cat["DARF SIMPLES"] == "Impostos (apurados nas notas)"
        assert cat["PAGTO FACEBK *ADS; CAMPANHA"] == "ADS / Publicidade"
        assert cat["RENDIMENTO APLIC AUTOMATICA"] == "Receitas financeiras"
        assert cat["PIX ENVIADO JOAO DA SILVA"] == ""
        assert page.evaluate("Object.values(db.bank).find(t=>t.desc.startsWith('PAGTO FACEBK')).valor") == pytest.approx(-1234.56)
        assert page.inner_text("#fSem") == "2"
        assert _valor(page, "#fEnt") == pytest.approx(12512.34)

        # reimportar não duplica
        page.click("#bkImport")
        page.wait_for_function("document.querySelector('#bkResult').innerText.includes('0 novos')")
        assert page.evaluate("Object.keys(db.bank).length") == 8

        # classificar à mão e criar regra: o outro PIX igual é classificado junto
        page.select_option("#fFiltro", "__sem")
        page.select_option("#fBody tr >> nth=0 >> select", "Pessoal e pró-labore")
        page.select_option("#fFiltro", "")
        linha = page.locator("#fBody tr", has_text="2026-08-06")
        linha.locator("text=criar regra").click()
        assert page.inner_text("#fSem") == "0"

        # DRE recebe as despesas do extrato (e não os recebimentos, impostos...)
        page.click("text=DRE Mensal")
        def linha_dre(r):
            return page.evaluate("""([r])=>{let t=window._dre;let i=t.linhas.findIndex(l=>l[0]===r);return t.linhas[i][1][t.ms.indexOf('2026-08')]}""", [r])
        assert linha_dre("(−) Despesas financeiras") == pytest.approx(-45.90)
        assert linha_dre("(−) Despesas fixas") == pytest.approx(-389.77)
        assert linha_dre("(−) ADS / Publicidade") == pytest.approx(-1234.56)
        assert linha_dre("(−) Pessoal e pró-labore") == pytest.approx(-3000)
        assert linha_dre("(+) Receitas financeiras") == pytest.approx(12.34)
        assert linha_dre("Receita bruta de vendas") == pytest.approx(0)
        assert erros == []
        browser.close()


def _xlsx_contas(caminho, pago_aluguel=False):
    import datetime
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Relatório de contas a pagar"])
    ws.append([])
    ws.append(["Data vencimento", "Nome do contato", "Histórico", "Categoria", "Nº documento", "Valor",
               "Situação", "Data pagamento", "Valor pago"])
    ws.append([datetime.date(2026, 8, 5), "Imobiliária Centro", "Aluguel agosto", "Aluguel", "AL-08", 3200.0,
               "Pago" if pago_aluguel else "Em aberto", datetime.date(2026, 8, 5) if pago_aluguel else None,
               3200.0 if pago_aluguel else None])
    ws.append([datetime.date(2026, 8, 10), "Excentrix Máquinas", "NF 5521 parcela 1/3", "Fornecedores", "5521-1",
               12000.0, "Pago", datetime.date(2026, 8, 11), 12000.0])
    ws.append([datetime.date(2099, 1, 10), "Excentrix Máquinas", "NF 5521 parcela 3/3", "Fornecedores", "5521-3",
               12000.0, "Em aberto", None, None])
    ws.append([datetime.date(2026, 8, 20), "Contabilidade Silva", "Honorários", "Serviços contábeis", "CT-08",
               950.0, "Cancelado", None, None])
    wb.save(caminho)


def test_html_contas_a_pagar(tmp_path):
    _xlsx_contas(tmp_path / "contas.xlsx")
    ofx = OFX.replace("<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260807<TRNAMT>-800.00<FITID>A5<MEMO>DARF SIMPLES",
                      "<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260812<TRNAMT>-12000.00<FITID>A6<MEMO>PIX ENVIADO EXCENTRIX")
    (tmp_path / "banco.ofx").write_text(ofx, encoding="latin-1")
    chromium = glob.glob("/opt/pw-browsers/chromium*/chrome-linux*/chrome")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium[0] if chromium else None)
        page = browser.new_page()
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("dialog", lambda d: d.accept(d.default_value) if d.type == "prompt" else d.accept())
        page.goto("file://" + HTML)
        page.wait_for_function("window.document.querySelector('#month').options.length>0")
        page.click("text=Financeiro / Extrato")
        page.set_input_files("#bkFiles", str(tmp_path / "banco.ofx"))
        page.click("#bkImport")
        page.wait_for_function("document.querySelector('#bkResult').innerText.includes('banco.ofx')")

        page.click("text=Contas a Pagar")
        page.set_input_files("#apFiles", str(tmp_path / "contas.xlsx"))
        page.click("#apImport")
        page.wait_for_function("document.querySelector('#apResult').innerText.includes('contas.xlsx')")
        res = page.inner_text("#apResult")
        assert "4 contas lidas" in res and "4 novas" in res, res
        page.select_option("#month", "2026-08")
        assert _valor(page, "#apAberto") == pytest.approx(15200)
        assert _valor(page, "#apVenc") == pytest.approx(3200)   # aluguel vencido em 05/08/2026
        assert _valor(page, "#apPagas") == pytest.approx(12000)
        assert "Aluguel" in page.inner_text("#apProj") or "Vencidas" in page.inner_text("#apProj")

        # conta paga encontrada no extrato
        page.select_option("#apSit", "pago")
        assert "Sim" in page.inner_text("#cpgBody")
        # regra padrão classifica aluguel como despesa fixa
        cats = page.evaluate("Object.fromEntries(Object.values(db.ap).map(a=>[a.desc,a.cat]))")
        assert cats["Aluguel agosto"] == "Despesas fixas"

        # reimportar com o aluguel pago atualiza, não duplica
        _xlsx_contas(tmp_path / "contas.xlsx", pago_aluguel=True)
        page.set_input_files("#apFiles", str(tmp_path / "contas.xlsx"))
        page.click("#apImport")
        page.wait_for_function("document.querySelector('#apResult').innerText.includes('atualizadas')")
        assert "0 novas" in page.inner_text("#apResult") and "4 atualizadas" in page.inner_text("#apResult")
        assert _valor(page, "#apAberto") == pytest.approx(12000)

        # fonte da DRE: contas a pagar (competência) x extrato
        page.click("text=DRE Mensal")
        fixas = "(()=>{let t=window._dre;let i=t.linhas.findIndex(l=>l[0]==='(−) Despesas fixas');return t.linhas[i][1][t.ms.indexOf('2026-08')]})()"
        assert page.evaluate(fixas) == pytest.approx(-389.77)          # ENEL do extrato
        page.click("text=Contas a Pagar")
        page.select_option("#fonteDre", "ap")
        page.click("text=DRE Mensal")
        assert page.evaluate(fixas) == pytest.approx(-3200)            # aluguel do contas a pagar
        assert erros == []
        browser.close()


def test_html_ids_unicos():
    import re
    ids = re.findall(r'id="([^"]+)"', open(HTML, encoding="utf-8").read())
    assert sorted({i for i in ids if ids.count(i) > 1}) == []


CSV_RECEBER = """Vencimento;Cliente;Histórico;Categoria;Documento;Valor;Situação;Data recebimento
04/08/2026;Mercado Livre;Repasse vendas julho;Marketplace;R-01;12.500,00;Recebido;04/08/2026
15/08/2026;Gráfica Alfa Ltda;NF 1201;Venda direta;1201;2.300,00;Em aberto;
10/01/2099;Gráfica Alfa Ltda;NF 1202;Venda direta;1202;5.000,00;Em aberto;
"""


def test_html_contas_a_receber(tmp_path):
    (tmp_path / "receber.csv").write_text(CSV_RECEBER, encoding="utf-8")
    (tmp_path / "banco.ofx").write_text(OFX, encoding="latin-1")
    _xlsx_contas(tmp_path / "contas.xlsx")
    chromium = glob.glob("/opt/pw-browsers/chromium*/chrome-linux*/chrome")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium[0] if chromium else None)
        page = browser.new_page()
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.goto("file://" + HTML)
        page.wait_for_function("window.document.querySelector('#month').options.length>0")
        page.click("text=Financeiro / Extrato")
        page.set_input_files("#bkFiles", str(tmp_path / "banco.ofx"))
        page.click("#bkImport")
        page.wait_for_function("document.querySelector('#bkResult').innerText.includes('banco.ofx')")
        page.click("text=Contas a Pagar")
        page.set_input_files("#apFiles", str(tmp_path / "contas.xlsx"))
        page.click("#apImport")
        page.wait_for_function("document.querySelector('#apResult').innerText.includes('contas.xlsx')")

        page.click("text=Contas a Receber")
        page.set_input_files("#arFiles", str(tmp_path / "receber.csv"))
        page.click("#arImport")
        page.wait_for_function("document.querySelector('#arResult').innerText.includes('receber.csv')")
        assert "3 contas lidas" in page.inner_text("#arResult")
        page.select_option("#month", "2026-08")
        assert _valor(page, "#arAberto") == pytest.approx(7300)
        assert _valor(page, "#arVenc") == pytest.approx(2300)
        assert _valor(page, "#arRec") == pytest.approx(12500)
        page.select_option("#arSit", "pago")
        assert "Sim" in page.inner_text("#arBody")     # repasse encontrado no extrato

        page.fill("#arSaldoIni", "1000")
        page.dispatch_event("#arSaldoIni", "change")
        fluxo = page.inner_text("#arFluxo").replace("\xa0", " ")
        # vencidas: +2.300 a receber, -3.200 a pagar; jan/2099: +5.000, -12.000
        assert "-R$ 900,00" in fluxo and "R$ 100,00" in fluxo and "-R$ 6.900,00" in fluxo
        assert erros == []
        browser.close()
