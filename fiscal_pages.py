"""Telas Streamlit do módulo fiscal: importação de XML, créditos, apuração e DRE."""
from datetime import date

import plotly.express as px
import streamlit as st

from calculations import brl
from database import CreditoExtra
from fiscal_apuracao import (
    carregar_config, salvar_config, importar_documentos, reprocessar, excluir_documentos,
    lancamentos_df, documentos_df, creditos_extras_df, apurar, apuracao_df,
    resumo_por_natureza, resumo_mensal, dre_lucro_real, exportar_excel,
)
from fiscal_rules import ConfigFiscal
from fiscal_xml import ler_arquivos, somente_digitos

COLUNAS_LANCAMENTO = {
    "data": "Data", "tipo_documento": "Doc", "numero": "Número", "direcao": "Direção",
    "participante": "Participante", "descricao": "Descrição", "cfop": "CFOP", "natureza": "Natureza",
    "valor_contabil": "Valor contábil", "icms_debito": "ICMS débito", "icms_credito": "ICMS crédito",
    "base_pis_cofins": "Base PIS/COFINS", "pis_debito": "PIS débito", "cofins_debito": "COFINS débito",
    "pis_credito": "PIS crédito", "cofins_credito": "COFINS crédito", "icms_st": "ICMS-ST", "ipi": "IPI",
    "difal": "DIFAL", "custo": "Custo líquido", "observacao": "Observação", "chave": "Chave",
}

CATEGORIAS_EXTRAS = [
    "Armazenagem (ex.: FULL Mercado Livre)",
    "Energia elétrica",
    "Aluguel de prédio / máquinas (PJ)",
    "Arrendamento mercantil",
    "Depreciação / amortização",
    "Insumos e serviços",
    "Frete sem CT-e",
    "CIAP (ICMS 1/48 do ativo)",
    "Outros",
]


def _titulo(texto, subtitulo=""):
    st.markdown(f'<div class="main-title">{texto}</div>', unsafe_allow_html=True)
    if subtitulo:
        st.markdown(f'<div class="subtitle">{subtitulo}</div>', unsafe_allow_html=True)


def _periodo(prefixo):
    hoje = date.today()
    inicio_padrao = hoje.replace(day=1)
    c1, c2 = st.columns(2)
    inicio = c1.date_input("Início do período", inicio_padrao, key=f"{prefixo}_inicio", format="DD/MM/YYYY")
    fim = c2.date_input("Fim do período", hoje, key=f"{prefixo}_fim", format="DD/MM/YYYY")
    return inicio, fim


def _formatar(df):
    moeda = [c for c in df.columns if df[c].dtype.kind == "f"]
    return df.style.format({c: brl for c in moeda})


def _exibir_lancamentos(df):
    st.dataframe(_formatar(df[list(COLUNAS_LANCAMENTO)].rename(columns=COLUNAS_LANCAMENTO)),
                 width="stretch", hide_index=True)


def _aviso_config(cfg):
    if not cfg.cnpjs:
        st.warning("Cadastre o CNPJ da empresa na aba **Configuração** antes de importar: "
                   "é ele que define se o XML é entrada (crédito) ou saída (débito).")
        return False
    return True


# ---------------------------------------------------------------- Importar XML

def pagina_importar(db):
    _titulo("Leitura de XML fiscal",
            "NF-e de compras e vendas e CT-e de fretes - Lucro Real (PIS/COFINS não cumulativo)")
    cfg = carregar_config(db)
    aba_importar, aba_docs, aba_config = st.tabs(["Importar", "Documentos importados", "Configuração"])

    with aba_importar:
        if _aviso_config(cfg):
            arquivos = st.file_uploader("Selecione XMLs de NF-e/CT-e ou arquivos .zip",
                                        type=["xml", "zip"], accept_multiple_files=True)
            if arquivos and st.button("Ler e gravar XMLs", type="primary"):
                documentos, erros_leitura = ler_arquivos([(a.name, a.getvalue()) for a in arquivos])
                importados, duplicados, erros = importar_documentos(db, documentos, cfg)
                st.success(f"{importados} documento(s) importado(s). {duplicados} já existiam e foram ignorados.")
                for nome, msg in erros_leitura + erros:
                    st.error(f"{nome}: {msg}")

        st.markdown("""
**Como o sistema lê cada documento**

| Documento | Situação | ICMS | PIS/COFINS |
|---|---|---|---|
| NF-e de fornecedor (CFOP 1102/2102, 1101, 1403) | Compra para revenda / industrialização | Crédito do ICMS destacado (exceto compra com ST) | Crédito 1,65% + 7,6% sobre mercadoria + frete + IPI − ICMS |
| NF-e emitida pela empresa (5102/6102/6108...) | Venda | Débito do ICMS destacado + DIFAL | Débito sobre venda − ICMS (Tema 69) |
| Devolução de venda (1202/2202) | Anula a venda | Crédito | Crédito (estorno do débito) |
| Devolução de compra (5202/6202) | Anula a compra | Débito | Estorno do crédito |
| CT-e com a empresa tomadora e remetente | Frete sobre vendas | Crédito | Crédito (art. 3º, IX, Lei 10.833) |
| CT-e com a empresa tomadora e destinatária | Frete sobre compras (custo) | Crédito | Crédito |
| Uso e consumo, ativo, bonificação, remessas | Sem crédito automático | Ver observação | Ver observação |
""")

    with aba_docs:
        docs = documentos_df(db)
        if docs.empty:
            st.info("Nenhum documento importado.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Documentos", len(docs))
            c2.metric("NF-e", int((docs["Tipo"] == "NF-e").sum()))
            c3.metric("CT-e", int((docs["Tipo"] == "CT-e").sum()))
            st.dataframe(_formatar(docs), width="stretch", hide_index=True)
            excluir = st.multiselect("Excluir documentos (chave)", docs["Chave"].tolist())
            if excluir and st.button("Excluir selecionados"):
                excluir_documentos(db, excluir)
                st.success("Documentos excluídos.")
                st.rerun()

    with aba_config:
        with st.form("form_config_fiscal"):
            cnpjs = st.text_area("CNPJ(s) da empresa (um por linha, inclua as filiais)", "\n".join(cfg.cnpjs))
            c1, c2 = st.columns(2)
            aliq_pis = c1.number_input("Alíquota PIS", value=cfg.aliq_pis, step=0.0001, format="%.4f")
            aliq_cofins = c2.number_input("Alíquota COFINS", value=cfg.aliq_cofins, step=0.0001, format="%.4f")
            excluir_deb = st.checkbox("Excluir ICMS da base do PIS/COFINS nas vendas (STF Tema 69)",
                                      value=cfg.excluir_icms_base_debito)
            excluir_cred = st.checkbox("Excluir ICMS da base do crédito de PIS/COFINS nas compras (Lei 14.592/2023)",
                                       value=cfg.excluir_icms_base_credito)
            incluir_ipi = st.checkbox("Incluir IPI não recuperável na base do crédito", value=cfg.incluir_ipi_credito)
            incluir_st = st.checkbox("Incluir ICMS-ST na base do crédito (tema controverso)",
                                     value=cfg.incluir_st_credito)
            salvar = st.form_submit_button("Salvar configuração e recalcular documentos")
        if salvar:
            novo = ConfigFiscal(
                cnpjs=[somente_digitos(c) for c in cnpjs.replace(",", "\n").splitlines() if somente_digitos(c)],
                aliq_pis=aliq_pis, aliq_cofins=aliq_cofins,
                excluir_icms_base_debito=excluir_deb, excluir_icms_base_credito=excluir_cred,
                incluir_ipi_credito=incluir_ipi, incluir_st_credito=incluir_st,
            )
            salvar_config(db, novo)
            erros = reprocessar(db, novo)
            st.success("Configuração salva e documentos recalculados.")
            for nome, msg in erros:
                st.error(f"{nome}: {msg}")


# ---------------------------------------------------------------- Créditos

def pagina_creditos(db):
    _titulo("Créditos de ICMS, PIS e COFINS", "Créditos lidos dos XMLs e créditos extras do período")
    inicio, fim = _periodo("cred")
    lanc = lancamentos_df(db, inicio, fim)
    extras = creditos_extras_df(db, inicio, fim)

    entradas = lanc[(lanc["icms_credito"] != 0) | (lanc["pis_credito"] != 0) | (lanc["cofins_credito"] != 0)]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Crédito ICMS", brl(entradas["icms_credito"].sum() + extras["icms_credito"].sum()))
    c2.metric("Crédito PIS", brl(entradas["pis_credito"].sum() + extras["pis_credito"].sum()))
    c3.metric("Crédito COFINS", brl(entradas["cofins_credito"].sum() + extras["cofins_credito"].sum()))
    c4.metric("Total de créditos", brl(
        entradas[["icms_credito", "pis_credito", "cofins_credito"]].sum().sum()
        + extras[["icms_credito", "pis_credito", "cofins_credito"]].sum().sum()))

    aba_nat, aba_itens, aba_extras = st.tabs(["Por natureza", "Documentos com crédito", "Créditos extras"])

    with aba_nat:
        resumo = resumo_por_natureza(entradas)
        resumo = resumo[["direcao", "natureza", "documentos", "valor_contabil", "base_pis_cofins",
                         "icms_credito", "pis_credito", "cofins_credito"]]
        st.dataframe(_formatar(resumo.rename(columns=COLUNAS_LANCAMENTO | {
            "direcao": "Direção", "documentos": "Documentos"})), width="stretch", hide_index=True)
        if not resumo.empty:
            grafico = resumo.melt(id_vars="natureza", value_vars=["icms_credito", "pis_credito", "cofins_credito"],
                                  var_name="Tributo", value_name="Crédito")
            grafico["Tributo"] = grafico["Tributo"].map({"icms_credito": "ICMS", "pis_credito": "PIS",
                                                         "cofins_credito": "COFINS"})
            st.plotly_chart(px.bar(grafico, x="natureza", y="Crédito", color="Tributo", barmode="group",
                                   labels={"natureza": "Natureza"}), width="stretch")

    with aba_itens:
        if entradas.empty:
            st.info("Nenhum crédito no período.")
        else:
            _exibir_lancamentos(entradas)
        sem_credito = lanc[(lanc["direcao"] == "Entrada") & (lanc["observacao"] != "")]
        if not sem_credito.empty:
            st.subheader("Entradas para revisar")
            _exibir_lancamentos(sem_credito)

    with aba_extras:
        st.caption("Créditos que não vêm de NF-e/CT-e: armazenagem do FULL, energia, aluguel, depreciação, CIAP...")
        with st.form("form_credito_extra", clear_on_submit=True):
            c1, c2 = st.columns(2)
            data_ = c1.date_input("Data", fim, format="DD/MM/YYYY")
            categoria = c2.selectbox("Categoria", CATEGORIAS_EXTRAS)
            descricao = st.text_input("Descrição")
            c3, c4 = st.columns(2)
            base = c3.number_input("Base de cálculo PIS/COFINS", min_value=0.0, step=100.0)
            icms = c4.number_input("Crédito de ICMS (ex.: parcela CIAP)", min_value=0.0, step=10.0)
            if st.form_submit_button("Adicionar crédito"):
                cfg = carregar_config(db)
                db.add(CreditoExtra(data=data_, categoria=categoria, descricao=descricao, base_pis_cofins=base,
                                    pis_credito=base * cfg.aliq_pis, cofins_credito=base * cfg.aliq_cofins,
                                    icms_credito=icms))
                db.commit()
                st.success("Crédito adicionado.")
                st.rerun()
        if not extras.empty:
            st.dataframe(_formatar(extras), width="stretch", hide_index=True)
            remover = st.multiselect("Remover créditos (id)", extras["id"].tolist())
            if remover and st.button("Remover selecionados"):
                db.query(CreditoExtra).filter(CreditoExtra.id.in_(remover)).delete(synchronize_session=False)
                db.commit()
                st.rerun()


# ---------------------------------------------------------------- Apuração

def pagina_apuracao(db):
    _titulo("Apuração ICMS / PIS / COFINS", "Débitos das saídas menos créditos das entradas - Lucro Real")
    inicio, fim = _periodo("apur")
    c1, c2, c3 = st.columns(3)
    saldo_icms = c1.number_input("Saldo credor ICMS anterior", min_value=0.0, step=100.0)
    saldo_pis = c2.number_input("Saldo credor PIS anterior", min_value=0.0, step=100.0)
    saldo_cofins = c3.number_input("Saldo credor COFINS anterior", min_value=0.0, step=100.0)

    lanc = lancamentos_df(db, inicio, fim)
    extras = creditos_extras_df(db, inicio, fim)
    resultado = apurar(lanc, extras, saldo_icms, saldo_pis, saldo_cofins)

    cols = st.columns(3)
    for col, tributo in zip(cols, ("ICMS", "PIS", "COFINS")):
        r = resultado[tributo]
        if r["a_recolher"] > 0:
            col.metric(f"{tributo} a recolher", brl(r["a_recolher"]))
        else:
            col.metric(f"{tributo} saldo credor", brl(r["saldo_credor_transportar"]))

    tabela = apuracao_df(resultado)
    st.dataframe(_formatar(tabela), width="stretch", hide_index=True)

    mensal = resumo_mensal(lanc, extras)
    if not mensal.empty:
        st.subheader("Débitos x créditos por mês")
        grafico = mensal.melt(id_vars="mes", var_name="Conta", value_name="Valor")
        st.plotly_chart(px.bar(grafico, x="mes", y="Valor", color="Conta", barmode="group",
                               labels={"mes": "Mês"}), width="stretch")

    natureza = resumo_por_natureza(lanc)
    st.subheader("Resumo por natureza da operação")
    st.dataframe(_formatar(natureza), width="stretch", hide_index=True)

    st.download_button(
        "Baixar apuração em Excel",
        exportar_excel({"Apuração": tabela, "Por natureza": natureza, "Mensal": mensal,
                        "Lançamentos": lanc, "Créditos extras": extras}),
        file_name=f"apuracao_{inicio:%Y%m%d}_{fim:%Y%m%d}.xlsx",
    )

    with st.expander("Ver todos os lançamentos do período"):
        if not lanc.empty:
            _exibir_lancamentos(lanc)


# ---------------------------------------------------------------- DRE

def pagina_dre_fiscal(db):
    _titulo("DRE Lucro Real", "Montada a partir das NF-e e CT-e importados, com IRPJ e CSLL")
    inicio, fim = _periodo("dre")
    meses = max(1, (fim.year - inicio.year) * 12 + fim.month - inicio.month + 1)
    lanc = lancamentos_df(db, inicio, fim)
    extras = creditos_extras_df(db, inicio, fim)

    with st.expander("Estoques e despesas do período", expanded=True):
        c1, c2 = st.columns(2)
        estoque_inicial = c1.number_input("Estoque inicial (custo líquido)", min_value=0.0, step=1000.0)
        estoque_final = c2.number_input("Estoque final (custo líquido)", min_value=0.0, step=1000.0)
        c3, c4, c5 = st.columns(3)
        comissoes = c3.number_input("Comissões / tarifas marketplace", min_value=0.0, step=100.0)
        ads = c4.number_input("ADS / Publicidade", min_value=0.0, step=100.0)
        embalagens = c5.number_input("Embalagens", min_value=0.0, step=100.0)
        c6, c7, c8 = st.columns(3)
        pessoal = c6.number_input("Pessoal e pró-labore", min_value=0.0, step=100.0)
        fixas = c7.number_input("Outras despesas fixas", min_value=0.0, step=100.0)
        servicos = c8.number_input("Serviços operacionais", min_value=0.0, step=100.0)
        c9, c10 = st.columns(2)
        rec_fin = c9.number_input("Receitas financeiras", min_value=0.0, step=100.0)
        desp_fin = c10.number_input("Despesas financeiras (juros, tarifas)", min_value=0.0, step=100.0)

    with st.expander("Ajustes do LALUR"):
        c1, c2, c3 = st.columns(3)
        adicoes = c1.number_input("Adições", min_value=0.0, step=100.0)
        exclusoes = c2.number_input("Exclusões", min_value=0.0, step=100.0)
        prejuizo = c3.number_input("Prejuízo fiscal a compensar", min_value=0.0, step=100.0)

    despesas = {
        "Comissões / tarifas marketplace": comissoes, "ADS / Publicidade": ads, "Embalagens": embalagens,
        "Pessoal e pró-labore": pessoal, "Outras despesas fixas": fixas, "Serviços operacionais": servicos,
    }
    tabela, ind = dre_lucro_real(lanc, extras, meses, estoque_inicial, estoque_final, despesas,
                                 rec_fin, desp_fin, adicoes, exclusoes, prejuizo)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Receita bruta", brl(ind["receita_bruta"]))
    k2.metric("Receita líquida", brl(ind["receita_liquida"]))
    k3.metric("Lucro bruto", brl(ind["lucro_bruto"]))
    k4.metric("Lucro líquido", brl(ind["lucro_liquido"]))

    exibicao = tabela.copy()
    exibicao["% Receita líquida"] = exibicao["% Receita líquida"].map(lambda v: f"{v * 100:.2f}%".replace(".", ","))
    exibicao["Valor"] = exibicao["Valor"].map(brl)
    st.dataframe(exibicao, width="stretch", hide_index=True)
    st.caption(f"Período de {meses} mês(es): adicional de IRPJ sobre o que exceder {brl(20000 * meses)}. "
               "Estimativa gerencial - confirme com a contabilidade antes de recolher.")

    st.download_button("Baixar DRE em Excel", exportar_excel({"DRE": tabela}),
                       file_name=f"dre_{inicio:%Y%m%d}_{fim:%Y%m%d}.xlsx")
