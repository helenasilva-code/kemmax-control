"""Telas Streamlit do módulo fiscal: importação de XML, créditos, apuração e DRE."""
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from calculations import brl
from database import CreditoExtra, backup_banco, restaurar_banco
from fiscal_apuracao import (
    carregar_config, salvar_config, importar_documentos, cnpjs_candidatos, apagar_dados_fiscais, reprocessar, excluir_documentos,
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


def _gravar_lote(db, documentos, cfg):
    barra = st.progress(0.0, text="Gravando documentos...")
    resumo = importar_documentos(db, documentos, cfg, progresso=lambda f: barra.progress(f, text="Gravando documentos..."))
    barra.empty()
    st.success(f"{resumo['importados']} documento(s) importado(s). {resumo['duplicados']} já existiam e foram "
               f"ignorados. {resumo['cancelados']} cancelamento(s) aplicado(s).")
    return resumo["erros"]


def _mostrar_erros(erros):
    if erros:
        with st.expander(f"{len(erros)} arquivo(s) não importado(s)", expanded=len(erros) <= 10):
            st.dataframe([{"Arquivo": n, "Motivo": m} for n, m in erros], width="stretch", hide_index=True)


# ---------------------------------------------------------------- Importar XML

def pagina_importar(db):
    _titulo("Leitura de XML fiscal",
            "NF-e de compras e vendas e CT-e de fretes - Lucro Real (PIS/COFINS não cumulativo)")
    cfg = carregar_config(db)
    aba_importar, aba_docs, aba_config, aba_backup = st.tabs(
        ["Importar", "Documentos importados", "Configuração", "Backup"])

    with aba_importar:
        st.caption("Envie o .zip baixado do Google Drive, do portal da SEFAZ ou do contador: pode ter pastas, "
                   "outros .zip dentro, NF-e, CT-e e eventos de cancelamento. Notas repetidas são ignoradas.")
        arquivos = st.file_uploader("XMLs de NF-e/CT-e ou arquivos .zip", type=["xml", "zip"],
                                    accept_multiple_files=True)
        if arquivos and st.button("Ler arquivos", type="primary"):
            with st.spinner("Lendo XMLs..."):
                st.session_state["xml_lidos"] = ler_arquivos([(a.name, a.getvalue()) for a in arquivos])

        if "xml_lidos" in st.session_state:
            documentos, erros_leitura = st.session_state["xml_lidos"]
            tipos = pd.Series([d["tipo_documento"] for d in documentos]).value_counts()
            st.info(f"Lidos: {tipos.get('NF-e', 0)} NF-e, {tipos.get('CT-e', 0)} CT-e, "
                    f"{tipos.get('Evento', 0)} cancelamento(s), {len(erros_leitura)} arquivo(s) com erro.")

            if not cfg.cnpjs:
                candidatos = cnpjs_candidatos(documentos)
                st.warning("Informe qual é o CNPJ da empresa: ele define o que é compra (crédito) e o que é "
                           "venda (débito). Abaixo, os CNPJs que mais aparecem nos XMLs.")
                opcoes = {f"{c} - {nome} ({qtd} documentos)": c for c, nome, qtd in candidatos}
                escolhidos = st.multiselect("CNPJ(s) da empresa (matriz e filiais)", list(opcoes),
                                            default=list(opcoes)[:1])
                if escolhidos and st.button("Confirmar CNPJ e gravar", type="primary"):
                    cfg.cnpjs = [opcoes[e] for e in escolhidos]
                    salvar_config(db, cfg)
                    _mostrar_erros(erros_leitura + _gravar_lote(db, documentos, cfg))
                    del st.session_state["xml_lidos"]
            elif st.button("Gravar no sistema", type="primary"):
                _mostrar_erros(erros_leitura + _gravar_lote(db, documentos, cfg))
                del st.session_state["xml_lidos"]

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


    with aba_backup:
        st.caption("Todos os dados ficam num único arquivo de banco (kemmax_control.db) no seu computador. "
                   "Baixe uma cópia com frequência e guarde num local seguro.")
        st.download_button("Baixar backup do banco", backup_banco(),
                           file_name=f"kemmax_backup_{date.today():%Y%m%d}.db", mime="application/octet-stream")
        restaurar = st.file_uploader("Restaurar backup (.db)", type=["db"])
        if restaurar and st.button("Substituir os dados atuais por este backup"):
            try:
                restaurar_banco(restaurar.getvalue())
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success("Backup restaurado.")
                st.rerun()

        st.divider()
        confirmar = st.checkbox("Quero apagar todos os XMLs importados, lançamentos e créditos extras")
        if confirmar and st.button("Apagar dados fiscais"):
            apagar_dados_fiscais(db)
            st.success("Dados fiscais apagados. A configuração (CNPJ e alíquotas) foi mantida.")


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
