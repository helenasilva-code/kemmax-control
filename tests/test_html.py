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
        assert "4 novos" in resultado and "1 repetidos" in resultado
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

        page.click("text=Financeiro / Despesas")
        page.fill("#expMonth", "2026-08")
        page.fill("#expVal", "100")
        page.click("#addExp")

        page.select_option("#month", "2026-08")
        page.click("text=Dashboard")
        assert _valor(page, "#kFat") == pytest.approx(2000)
        assert _valor(page, "#kFrete") == pytest.approx(78.75)
        assert _valor(page, "#kCred") == pytest.approx(21.25)

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

        page.click("text=Apuração Impostos")
        apur = page.evaluate("window._apur.linhas.filter(l=>l[0].startsWith('ICMS — A recolher'))[0][1]")
        assert apur[6] == pytest.approx(0) and apur[7] == pytest.approx(360 - 72 - 12 - 180)

        page.click("text=Compras Mensais")
        page.select_option("#month", "2026-07")
        assert _valor(page, "#cpC") == pytest.approx(180 + 820 * 0.0925)

        # recarregar: dados persistem no IndexedDB
        page.reload()
        page.wait_for_function("window.document.querySelector('#month').options.length>0")
        page.select_option("#month", "2026-08")
        assert _valor(page, "#kFat") == pytest.approx(2000)
        assert erros == []
        browser.close()
