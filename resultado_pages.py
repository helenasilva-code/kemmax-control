"""Telas de resultado: Resumo Mensal, Lucro por Produto e cadastros (custos, marketplaces, despesas)."""
from datetime import date

import pandas as pd
import streamlit as st

from cadastros import (
    COLUNAS_DESPESAS, cadastrar_produtos, despesas_df, marketplaces_df, produtos_custos_df,
    salvar_custos, salvar_despesas, salvar_marketplaces, seed_marketplaces,
)
from calculations import brl
from fiscal_apuracao import carregar_config, creditos_extras_df, exportar_excel, lancamentos_df
from fiscal_mensal import (
    VALORES_PRODUTO, lucro_por_produto, meses_do_ano, resumo_completo, rotulo_mes,
)

NOMES_PRODUTO = {
    "codigo": "SKU", "descricao": "Produto", "marketplace": "Marketplace", "mes": "Mês",
    "quantidade": "Qtde", "receita": "Receita", "impostos": "Impostos", "comissao": "Comissão + taxa fixa",
    "frete_marketplace": "Frete", "embalagem": "Embalagem", "cmv_dre": "CMV DRE",
    "cmv_financeiro": "CMV Financeiro", "lucro_dre": "Lucro DRE", "lucro_financeiro": "Lucro Financeiro",
    "margem_dre": "Margem DRE", "margem_financeira": "Margem Financeira", "resultado": "Resultado",
}


def _titulo(texto, subtitulo=""):
    st.markdown(f'<div class="main-title">{texto}</div>', unsafe_allow_html=True)
    if subtitulo:
        st.markdown(f'<div class="subtitle">{subtitulo}</div>', unsafe_allow_html=True)


def _avisar_depois(msg):
    """Mensagem de sucesso que sobrevive ao st.rerun()."""
    st.session_state["_aviso_salvo"] = msg
    st.rerun()


def _mostrar_aviso():
    if "_aviso_salvo" in st.session_state:
        st.success(st.session_state.pop("_aviso_salvo"))


def _vermelho_se_negativo(v):
    return "color: #C62828" if isinstance(v, (int, float)) and v < -0.004 else ""


def _estilo_mensal(df):
    """Valores em R$, quantidades inteiras, totais em negrito e negativos em vermelho."""
    numericas = [c for c in df.columns if c != "Linha"]
    qtde = df["Linha"].str.contains(r"\(qtde\)|Unidades", regex=True)
    estilo = (df.style
              .format(brl, subset=pd.IndexSlice[~qtde, numericas])
              .format("{:,.0f}", subset=pd.IndexSlice[qtde, numericas])
              .map(_vermelho_se_negativo, subset=numericas))
    destaque = df["Linha"].str.startswith("=") | df["Linha"].str.contains("A recolher|total", case=False)
    return estilo.apply(lambda linha: ["font-weight: bold" if destaque[linha.name] else "" for _ in linha], axis=1)


def _tabela_mensal(df):
    st.dataframe(_estilo_mensal(df), width="stretch", hide_index=True, height=min(36 * (len(df) + 1) + 3, 1200),
                 column_config={"Linha": st.column_config.Column("Linha", width="large", pinned=True)})


def _anos_disponiveis(db):
    lanc = lancamentos_df(db)
    anos = set(pd.to_datetime(lanc["data"]).dt.year.dropna().astype(int)) if not lanc.empty else set()
    anos.add(date.today().year)
    return sorted(anos, reverse=True)


def _estilo_produtos(df):
    moeda = [c for c in ["Receita", "Impostos", "Comissão + taxa fixa", "Frete", "Embalagem", "CMV DRE",
                         "CMV Financeiro", "Lucro DRE", "Lucro Financeiro"] if c in df.columns]
    margens = [c for c in ["Margem DRE", "Margem Financeira"] if c in df.columns]
    cores = {"Lucro": "color: #2E7D32; font-weight: bold", "Prejuízo": "color: #C62828; font-weight: bold",
             "Sem custo cadastrado": "color: #EF6C00"}
    return (df.style.format(brl, subset=moeda)
            .format(lambda v: f"{v * 100:.1f}%".replace(".", ","), subset=margens)
            .format("{:,.0f}", subset=["Qtde"])
            .map(_vermelho_se_negativo, subset=moeda + margens)
            .map(lambda v: cores.get(v, ""), subset=["Resultado"] if "Resultado" in df.columns else []))


# ---------------------------------------------------------------- Resumo Mensal

def pagina_resumo_mensal(db):
    _titulo("Resumo Mensal", "Compras, vendas, CT-e, créditos, apuração e DRE mês a mês a partir dos XMLs")
    seed_marketplaces(db)

    c1, c2 = st.columns([1, 2])
    ano = c1.selectbox("Ano", _anos_disponiveis(db))
    cmv_modo = c2.radio("CMV da DRE", ["Custo cadastrado x produtos vendidos", "Compras líquidas do mês"],
                        horizontal=True, help="O custo cadastrado usa a tela Custos dos Produtos. "
                        "Compras líquidas usa o total das NF-e de compra do mês, menos os créditos.")
    with st.expander(f"Saldo credor de impostos em 31/12/{ano - 1}"):
        s1, s2, s3 = st.columns(3)
        saldos = {"ICMS": s1.number_input("ICMS", min_value=0.0, step=100.0, key="saldo_icms"),
                  "PIS": s2.number_input("PIS", min_value=0.0, step=100.0, key="saldo_pis"),
                  "COFINS": s3.number_input("COFINS", min_value=0.0, step=100.0, key="saldo_cofins")}

    meses = meses_do_ano(ano, date.today())
    lanc = lancamentos_df(db, date(ano, 1, 1), date(ano, 12, 31))
    if lanc.empty:
        st.info(f"Nenhum XML de {ano} importado. Use o menu **Importar XML** para enviar os .zip de cada mês.")
        return
    extras = creditos_extras_df(db, date(ano, 1, 1), date(ano, 12, 31))
    r = resumo_completo(lanc, extras, produtos_custos_df(db), marketplaces_df(db), despesas_df(db, meses),
                        meses, saldos, cmv_modo.startswith("Custo"))

    ind = r["indicadores"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Receita bruta no ano", brl(ind["receita_bruta"]))
    k2.metric("Lucro líquido (DRE)", brl(ind["lucro_liquido"]))
    k3.metric("Resultado financeiro (caixa)", brl(ind["resultado_caixa"]))
    k4.metric("ICMS + PIS + COFINS a recolher", brl(ind["impostos_recolher"]))

    itens = r["itens"]
    sem_custo = itens[~itens["custo_cadastrado"].astype(bool)] if not itens.empty else itens
    if not sem_custo.empty:
        st.warning(f"{sem_custo['codigo'].nunique()} produto(s) vendido(s) sem custo cadastrado "
                   f"({brl(sem_custo['receita'].sum())} de receita): o CMV deles está zerado. "
                   "Cadastre em **Custos dos Produtos**.")

    abas = st.tabs(["DRE", "Compras", "Vendas", "CT-e / Fretes", "Créditos e Apuração"])
    for aba, chave in zip(abas, ["dre", "compras", "vendas", "cte", "apuracao"]):
        with aba:
            _tabela_mensal(r[chave])

    st.download_button(
        "Baixar tudo em Excel",
        exportar_excel({"DRE": r["dre"], "Compras": r["compras"], "Vendas": r["vendas"], "CT-e": r["cte"],
                        "Apuração": r["apuracao"],
                        "Lucro por produto": lucro_por_produto(itens, ("codigo", "marketplace")).rename(columns=NOMES_PRODUTO),
                        "Itens vendidos": itens.rename(columns=NOMES_PRODUTO)}),
        file_name=f"kemmax_resumo_{ano}.xlsx", type="primary",
    )
    st.caption("IRPJ/CSLL estimados mês a mês (adicional de 10% acima de R$ 20 mil/mês), sem ajustes do LALUR. "
               "Estimativa gerencial: confirme com a contabilidade.")


# ---------------------------------------------------------------- Lucro por Produto

def pagina_lucro_produto(db):
    _titulo("Lucro por Produto", "Cada venda: receita - impostos - comissão e taxa fixa - frete - embalagem - CMV")
    seed_marketplaces(db)
    ano = st.selectbox("Ano", _anos_disponiveis(db), key="lp_ano")
    meses = meses_do_ano(ano, date.today())
    lanc = lancamentos_df(db, date(ano, 1, 1), date(ano, 12, 31))
    r = resumo_completo(lanc, creditos_extras_df(db, date(ano, 1, 1), date(ano, 12, 31)), produtos_custos_df(db),
                        marketplaces_df(db), despesas_df(db, meses), meses)
    itens = r["itens"]
    if itens.empty:
        st.info("Nenhuma venda importada neste ano. Importe os XMLs das NF-e de venda.")
        return

    c1, c2, c3 = st.columns(3)
    opcoes_mes = ["Ano todo"] + [rotulo_mes(m) for m in meses]
    escolha_mes = c1.selectbox("Mês", opcoes_mes)
    mkts = c2.multiselect("Marketplaces", sorted(itens["marketplace"].unique()))
    visao = c3.radio("Agrupar por", ["Produto", "Produto e marketplace", "Produto e mês"], horizontal=False)

    filtrado = itens
    if escolha_mes != "Ano todo":
        filtrado = filtrado[filtrado["mes"] == meses[opcoes_mes.index(escolha_mes) - 1]]
    if mkts:
        filtrado = filtrado[filtrado["marketplace"].isin(mkts)]
    por = {"Produto": ["codigo"], "Produto e marketplace": ["codigo", "marketplace"],
           "Produto e mês": ["codigo", "mes"]}[visao]
    tabela = lucro_por_produto(filtrado, por)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Receita", brl(filtrado["receita"].sum()))
    k2.metric("Lucro DRE", brl(filtrado["lucro_dre"].sum()))
    k3.metric("Lucro Financeiro", brl(filtrado["lucro_financeiro"].sum()))
    k4.metric("Produtos com prejuízo", int((tabela["resultado"] == "Prejuízo").sum()))

    if "mes" in tabela.columns:
        tabela["mes"] = tabela["mes"].map(rotulo_mes)
    colunas = [*por, "descricao", *VALORES_PRODUTO, "margem_dre", "margem_financeira", "resultado"]
    exibir = tabela[colunas].rename(columns=NOMES_PRODUTO)
    st.dataframe(_estilo_produtos(exibir), width="stretch", hide_index=True)
    st.caption("Lucro DRE usa o CMV DRE (só a nota). Lucro Financeiro desconta também o que foi pago por fora. "
               "Comissão, taxa fixa e frete vêm da tela Marketplaces; custo e embalagem, de Custos dos Produtos.")

    sem_custo = tabela[tabela["resultado"] == "Sem custo cadastrado"]
    if not sem_custo.empty:
        st.warning(f"{sem_custo['codigo'].nunique()} produto(s) sem custo cadastrado: o lucro deles está superestimado.")
        if st.button("Cadastrar esses produtos em Custos dos Produtos"):
            nomes = itens.drop_duplicates("codigo").set_index("codigo")["descricao"]
            novos = cadastrar_produtos(db, [(c, nomes.get(c, c)) for c in sem_custo["codigo"].unique()])
            st.success(f"{novos} produto(s) criado(s). Preencha os custos em Custos dos Produtos.")

    st.download_button("Baixar em Excel", exportar_excel({"Lucro por produto": exibir}),
                       file_name=f"lucro_por_produto_{ano}.xlsx")


# ---------------------------------------------------------------- Custos dos Produtos

def pagina_custos_produtos(db):
    _titulo("Custos dos Produtos", "CMV DRE (só a nota fiscal) e CMV Financeiro (nota + valor pago por fora)")
    _mostrar_aviso()
    cfg = carregar_config(db)
    st.markdown(
        "- Preencha **Valor na NF** (unitário, sem IPI), **IPI %**, **ICMS %**, **Pago por fora** e **Frete** "
        "que o sistema calcula os dois custos, já descontando os créditos de ICMS e PIS/COFINS.\n"
        "- Se não quiser detalhar, deixe *Valor na NF* em 0 e digite o **CMV DRE** e o **CMV Financeiro** direto.\n"
        "- **Embalagem** é o custo por unidade vendida, usado no Lucro por Produto."
    )
    df = produtos_custos_df(db)
    df["ipi_pct"] = df["ipi_pct"] * 100
    df["icms_pct"] = df["icms_pct"] * 100
    moeda = st.column_config.NumberColumn
    editado = st.data_editor(
        df, num_rows="dynamic", width="stretch", hide_index=True, key="editor_custos",
        column_config={
            "sku": st.column_config.TextColumn("SKU", required=True),
            "nome": st.column_config.TextColumn("Produto"),
            "valor_nf": moeda("Valor na NF (un.)", format="R$ %.2f", min_value=0.0),
            "ipi_pct": moeda("IPI %", format="%.2f", min_value=0.0),
            "icms_pct": moeda("ICMS %", format="%.2f", min_value=0.0),
            "valor_por_fora": moeda("Pago por fora (un.)", format="R$ %.2f", min_value=0.0),
            "frete_unit": moeda("Frete compra (un.)", format="R$ %.2f", min_value=0.0),
            "embalagem_unit": moeda("Embalagem (un.)", format="R$ %.2f", min_value=0.0),
            "cmv_normal": moeda("CMV DRE", format="R$ %.2f", min_value=0.0),
            "cmf_kemmax": moeda("CMV Financeiro", format="R$ %.2f", min_value=0.0),
            "custo_caixa": moeda("Desembolso total (un.)", format="R$ %.2f", disabled=True),
        },
    )
    if st.button("Salvar custos", type="primary"):
        editado = editado.copy()
        editado["ipi_pct"] = editado["ipi_pct"].fillna(0) / 100
        editado["icms_pct"] = editado["icms_pct"].fillna(0) / 100
        removidos = salvar_custos(db, editado, cfg)
        _avisar_depois("Custos salvos e recalculados." + (f" {removidos} produto(s) removido(s)." if removidos else ""))

    with st.expander("Consultar últimas compras (NF-e) para preencher os custos"):
        lanc = lancamentos_df(db)
        compras = lanc[lanc["natureza"].isin(["Compra para revenda", "Compra para industrialização"])] if not lanc.empty else lanc
        if compras.empty:
            st.info("Importe XMLs de compra para ver os valores pagos.")
        else:
            compras = compras.sort_values("data", ascending=False).head(500).copy()
            mercadoria = compras["valor_contabil"] - compras["ipi"] - compras["icms_st"]
            qtd = compras["quantidade"].where(compras["quantidade"] > 0)
            compras["valor_unit"] = mercadoria / qtd
            compras["ipi_pct"] = (compras["ipi"] / mercadoria.where(mercadoria > 0)).fillna(0) * 100
            compras["icms_pct"] = (compras["icms_credito"] / mercadoria.where(mercadoria > 0)).fillna(0) * 100
            busca = st.text_input("Buscar produto ou fornecedor")
            if busca:
                alvo = compras["descricao"].str.contains(busca, case=False, na=False) | \
                    compras["participante"].str.contains(busca, case=False, na=False)
                compras = compras[alvo]
            st.dataframe(
                compras[["data", "participante", "codigo", "descricao", "quantidade", "valor_unit", "ipi_pct", "icms_pct"]]
                .rename(columns={"data": "Data", "participante": "Fornecedor", "codigo": "Cód. fornecedor",
                                 "descricao": "Produto", "quantidade": "Qtde", "valor_unit": "Valor unit. NF",
                                 "ipi_pct": "IPI %", "icms_pct": "ICMS %"})
                .style.format({"Valor unit. NF": brl, "IPI %": "{:.2f}", "ICMS %": "{:.2f}", "Qtde": "{:,.0f}"}),
                width="stretch", hide_index=True)


# ---------------------------------------------------------------- Marketplaces

def pagina_marketplaces(db):
    _titulo("Marketplaces", "Comissão, taxa fixa e frete de cada canal - usados no Lucro por Produto e na DRE")
    _mostrar_aviso()
    seed_marketplaces(db)
    st.markdown(
        "- O marketplace de cada venda é identificado pelo **CNPJ do intermediador** que vai na NF-e.\n"
        "- **Comissão %** incide sobre o valor da venda; **Taxa fixa** e **Frete médio** são por unidade vendida.\n"
        "- Vendas sem intermediador caem em *Venda direta / outros*. Confira as taxas atuais de cada canal."
    )
    df = marketplaces_df(db)
    df["comissao_pct"] = df["comissao_pct"] * 100
    editado = st.data_editor(
        df, num_rows="dynamic", width="stretch", hide_index=True, key="editor_marketplaces",
        column_config={
            "nome": st.column_config.TextColumn("Marketplace", required=True),
            "cnpj_intermediador": st.column_config.TextColumn("CNPJ do intermediador"),
            "comissao_pct": st.column_config.NumberColumn("Comissão %", format="%.2f", min_value=0.0),
            "taxa_fixa": st.column_config.NumberColumn("Taxa fixa (un.)", format="R$ %.2f", min_value=0.0),
            "frete_medio": st.column_config.NumberColumn("Frete médio (un.)", format="R$ %.2f", min_value=0.0),
        },
    )
    if st.button("Salvar marketplaces", type="primary"):
        editado = editado.copy()
        editado["comissao_pct"] = editado["comissao_pct"].fillna(0) / 100
        salvar_marketplaces(db, editado)
        _avisar_depois("Marketplaces salvos.")


# ---------------------------------------------------------------- Despesas Mensais

def pagina_despesas(db):
    _titulo("Despesas Mensais", "Valores que não vêm dos XMLs, para fechar a DRE de cada mês")
    _mostrar_aviso()
    ano = st.selectbox("Ano", _anos_disponiveis(db), key="desp_ano")
    meses = meses_do_ano(ano)
    df = despesas_df(db, meses)
    df.insert(1, "Mês", df["mes"].map(rotulo_mes))
    editado = st.data_editor(
        df, width="stretch", hide_index=True, key=f"editor_despesas_{ano}",
        column_config={
            "mes": None,
            "Mês": st.column_config.TextColumn("Mês", disabled=True),
            **{c: st.column_config.NumberColumn(nome, format="R$ %.2f", min_value=0.0)
               for c, nome in COLUNAS_DESPESAS.items()},
        },
    )
    if st.button("Salvar despesas", type="primary"):
        salvar_despesas(db, editado.drop(columns=["Mês"]))
        st.success("Despesas salvas.")
