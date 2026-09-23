import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta

from database import SessionLocal, Produto, Fornecedor, ContaPagar, ContaReceber, CompraSimulada
from seed import seed_data
from auth import exigir_login, botao_sair
from fiscal_pages import pagina_importar, pagina_creditos, pagina_apuracao
from resultado_pages import (
    pagina_resumo_mensal, pagina_lucro_produto, pagina_custos_produtos, pagina_marketplaces, pagina_despesas,
)
from calculations import (
    brl, pct, cmv_normal, cmf_kemmax, resultado_marketplace,
    ponto_equilibrio, cobertura_dias, compra_sugerida
)

st.set_page_config(
    page_title="Kemmax Control",
    layout="wide",
    initial_sidebar_state="expanded"
)

exigir_login()
seed_data()
db = SessionLocal()

st.markdown(
    '''
    <style>
    .main-title {font-size: 34px; font-weight: 800; margin-bottom: 0px;}
    .subtitle {font-size: 16px; color: #666; margin-bottom: 20px;}
    .block-card {padding: 16px; border-radius: 14px; border: 1px solid #DDD; background: #FAFAFA;}
    </style>
    ''',
    unsafe_allow_html=True
)

st.sidebar.title("Kemmax Control")
area = st.sidebar.radio("Área", ["Fiscal e Resultados", "Gestão"], horizontal=True)
if area == "Fiscal e Resultados":
    menu = st.sidebar.radio(
        "Menu",
        [
            "Resumo Mensal",
            "Importar XML",
            "Lucro por Produto",
            "Custos dos Produtos",
            "Marketplaces",
            "Despesas Mensais",
            "Créditos (detalhe)",
            "Apuração (período)",
        ]
    )
else:
    menu = st.sidebar.radio(
        "Menu",
        [
            "Dashboard",
            "Financeiro",
            "Fluxo de Caixa",
            "DRE",
            "Capital de Giro",
            "Produtos",
            "Fornecedores",
            "Compras Inteligentes",
            "Precificação",
            "Estoque e FULL",
            "Posso Comprar?"
        ]
    )
botao_sair()

def contas_pagar_df():
    rows = db.query(ContaPagar).order_by(ContaPagar.vencimento).all()
    return pd.DataFrame([{
        "ID": r.id,
        "Vencimento": r.vencimento,
        "Fornecedor": r.fornecedor,
        "Descrição": r.descricao,
        "Categoria": r.categoria,
        "Valor": r.valor,
        "Prioridade": r.prioridade,
        "Status": r.status,
        "Plano": "Pagar" if r.pagar_no_plano else "Renegociar"
    } for r in rows])

def contas_receber_df():
    rows = db.query(ContaReceber).order_by(ContaReceber.data_prevista).all()
    return pd.DataFrame([{
        "ID": r.id,
        "Data": r.data_prevista,
        "Canal": r.canal,
        "Descrição": r.descricao,
        "Bruto": r.valor_bruto,
        "Taxas": r.taxas,
        "REBATE": r.rebate,
        "Devoluções": r.devolucoes,
        "Líquido": r.valor_bruto - r.taxas + r.rebate - r.devolucoes,
        "Status": r.status
    } for r in rows])

def total_pagar(apenas_plano=False):
    q = db.query(ContaPagar).all()
    return sum(r.valor for r in q if r.status != "Pago" and (r.pagar_no_plano or not apenas_plano))

def total_receber():
    q = db.query(ContaReceber).all()
    return sum((r.valor_bruto - r.taxas + r.rebate - r.devolucoes) for r in q if r.status != "Recebido")

if menu == "Dashboard":
    st.markdown('<div class="main-title">Dashboard Executivo</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Visão rápida da saúde financeira da Kemmax</div>', unsafe_allow_html=True)

    pagar_plano = total_pagar(apenas_plano=True)
    pagar_total = total_pagar(apenas_plano=False)
    receber = total_receber()
    saldo_plano = receber - pagar_plano

    produtos = db.query(Produto).all()
    estoque_caixa = sum((p.estoque_empresa + p.estoque_full) * p.custo_caixa for p in produtos)
    produtos_criticos = 0
    for p in produtos:
        total = p.estoque_empresa + p.estoque_full
        cob = cobertura_dias(total, p.venda_media_dia)
        if p.venda_media_dia > 0 and cob <= p.lead_time_dias:
            produtos_criticos += 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Receber previsto", brl(receber))
    c2.metric("Pagar no plano", brl(pagar_plano))
    c3.metric("Saldo do plano", brl(saldo_plano))
    c4.metric("Estoque a custo caixa", brl(estoque_caixa))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Pagar total", brl(pagar_total))
    c6.metric("A renegociar", brl(pagar_total - pagar_plano))
    c7.metric("Produtos críticos", produtos_criticos)
    c8.metric("Capital necessário", brl(abs(saldo_plano)) if saldo_plano < 0 else brl(0))

    st.subheader("Pagamentos por status do plano")
    dfp = contas_pagar_df()
    if not dfp.empty:
        resumo = dfp.groupby("Plano", as_index=False)["Valor"].sum()
        st.plotly_chart(px.pie(resumo, names="Plano", values="Valor"), use_container_width=True)
    else:
        st.info("Cadastre contas a pagar no menu Financeiro.")

elif menu == "Financeiro":
    st.markdown('<div class="main-title">Financeiro</div>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Contas a Pagar", "Contas a Receber"])

    with tab1:
        st.subheader("Cadastrar Conta a Pagar")
        with st.form("form_pagar", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            vencimento = col1.date_input("Vencimento", date.today())
            fornecedor = col2.text_input("Fornecedor")
            categoria = col3.selectbox("Categoria", ["Fornecedor", "Cartão", "Empréstimo", "Plano de Saúde", "Contabilidade", "Pró-labore", "Impostos", "Serviço", "Outro"])
            descricao = st.text_input("Descrição")
            col4, col5, col6 = st.columns(3)
            valor = col4.number_input("Valor", min_value=0.0, step=100.0)
            prioridade = col5.selectbox("Prioridade", ["Crítica", "Alta", "Média", "Baixa"])
            status = col6.selectbox("Status", ["Previsto", "Pago", "Em atraso", "Renegociado"])
            pagar_no_plano = st.checkbox("Entrar no plano priorizado de pagamento", value=True)
            salvar = st.form_submit_button("Salvar Conta")
            if salvar:
                db.add(ContaPagar(vencimento=vencimento, fornecedor=fornecedor, descricao=descricao, categoria=categoria, valor=valor, prioridade=prioridade, status=status, pagar_no_plano=pagar_no_plano))
                db.commit()
                st.success("Conta cadastrada.")

        df = contas_pagar_df()
        st.dataframe(df, use_container_width=True)

    with tab2:
        st.subheader("Cadastrar Conta a Receber")
        with st.form("form_receber", clear_on_submit=True):
            col1, col2 = st.columns(2)
            data_prevista = col1.date_input("Data prevista", date.today())
            canal = col2.selectbox("Canal", ["Mercado Livre", "Shopee", "Amazon", "TikTok", "Venda Direta", "Outro"])
            descricao = st.text_input("Descrição do recebimento")
            col3, col4, col5, col6 = st.columns(4)
            valor_bruto = col3.number_input("Valor bruto", min_value=0.0, step=100.0)
            taxas = col4.number_input("Taxas", min_value=0.0, step=10.0)
            rebate = col5.number_input("REBATE", min_value=0.0, step=10.0)
            devolucoes = col6.number_input("Devoluções", min_value=0.0, step=10.0)
            status = st.selectbox("Status", ["Previsto", "Recebido", "Em atraso", "Cancelado"])
            salvar = st.form_submit_button("Salvar Recebimento")
            if salvar:
                db.add(ContaReceber(data_prevista=data_prevista, canal=canal, descricao=descricao, valor_bruto=valor_bruto, taxas=taxas, rebate=rebate, devolucoes=devolucoes, status=status))
                db.commit()
                st.success("Recebimento cadastrado.")

        df = contas_receber_df()
        st.dataframe(df, use_container_width=True)

elif menu == "Fluxo de Caixa":
    st.markdown('<div class="main-title">Fluxo de Caixa</div>', unsafe_allow_html=True)

    saldo_inicial = st.number_input("Saldo inicial em banco/caixa", value=0.0, step=1000.0)
    usar_plano = st.checkbox("Considerar apenas pagamentos do plano priorizado", value=True)

    pagar = contas_pagar_df()
    receber = contas_receber_df()

    eventos = []
    if not receber.empty:
        for _, r in receber.iterrows():
            if r["Status"] != "Recebido":
                eventos.append({"Data": r["Data"], "Descrição": r["Descrição"], "Tipo": "Entrada", "Entrada": r["Líquido"], "Saída": 0})
    if not pagar.empty:
        for _, r in pagar.iterrows():
            if r["Status"] != "Pago" and ((r["Plano"] == "Pagar") or not usar_plano):
                eventos.append({"Data": r["Vencimento"], "Descrição": r["Descrição"], "Tipo": "Saída", "Entrada": 0, "Saída": r["Valor"]})

    if eventos:
        df = pd.DataFrame(eventos).sort_values("Data")
        saldo = saldo_inicial
        saldos = []
        for _, row in df.iterrows():
            saldo += row["Entrada"] - row["Saída"]
            saldos.append(saldo)
        df["Saldo Projetado"] = saldos

        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo final projetado", brl(df["Saldo Projetado"].iloc[-1]))
        c2.metric("Menor saldo do período", brl(df["Saldo Projetado"].min()))
        c3.metric("Necessidade máxima de caixa", brl(abs(df["Saldo Projetado"].min())) if df["Saldo Projetado"].min() < 0 else brl(0))

        st.plotly_chart(px.line(df, x="Data", y="Saldo Projetado", title="Saldo projetado diário"), use_container_width=True)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Cadastre contas a pagar e a receber.")

elif menu == "DRE":
    st.markdown('<div class="main-title">DRE Gerencial</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    faturamento = col1.number_input("Faturamento bruto", value=180000.0, step=1000.0)
    cancelamentos = col2.number_input("Cancelamentos / Devoluções", value=0.0, step=100.0)
    rebate = col3.number_input("REBATE", value=0.0, step=100.0)

    col4, col5, col6 = st.columns(3)
    cmv_total = col4.number_input("CMV Normal total", value=0.0, step=1000.0)
    cmf_total = col5.number_input("CMF Kemmax total", value=0.0, step=1000.0)
    impostos = col6.number_input("Impostos sobre vendas", value=0.0, step=100.0)

    col7, col8, col9 = st.columns(3)
    comissoes = col7.number_input("Comissões", value=0.0, step=100.0)
    fretes = col8.number_input("Fretes", value=0.0, step=100.0)
    embalagens = col9.number_input("Embalagens", value=0.0, step=100.0)

    col10, col11, col12 = st.columns(3)
    ads = col10.number_input("ADS / Publicidade", value=0.0, step=100.0)
    despesas_fixas = col11.number_input("Despesas fixas", value=40000.0, step=1000.0)
    servicos = col12.number_input("Serviços operacionais", value=11290.09, step=100.0)

    receita_liquida = faturamento - cancelamentos + rebate
    lucro_bruto_cmv = receita_liquida - cmv_total - impostos - comissoes - fretes - embalagens
    lucro_bruto_cmf = receita_liquida - cmf_total - impostos - comissoes - fretes - embalagens
    lucro_operacional_cmv = lucro_bruto_cmv - ads - despesas_fixas - servicos
    lucro_operacional_cmf = lucro_bruto_cmf - ads - despesas_fixas - servicos

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Receita líquida", brl(receita_liquida))
    k2.metric("Lucro bruto CMV", brl(lucro_bruto_cmv), pct(lucro_bruto_cmv / receita_liquida if receita_liquida else 0))
    k3.metric("Lucro bruto CMF", brl(lucro_bruto_cmf), pct(lucro_bruto_cmf / receita_liquida if receita_liquida else 0))
    k4.metric("Diferença CMF x CMV", brl(lucro_bruto_cmf - lucro_bruto_cmv))

    k5, k6 = st.columns(2)
    k5.metric("Lucro operacional CMV", brl(lucro_operacional_cmv))
    k6.metric("Lucro operacional CMF", brl(lucro_operacional_cmf))

    dre = pd.DataFrame([
        {"Linha": "Faturamento bruto", "Valor": faturamento},
        {"Linha": "(-) Cancelamentos / Devoluções", "Valor": -cancelamentos},
        {"Linha": "(+) REBATE", "Valor": rebate},
        {"Linha": "Receita líquida", "Valor": receita_liquida},
        {"Linha": "(-) CMV Normal", "Valor": -cmv_total},
        {"Linha": "(-) CMF Kemmax", "Valor": -cmf_total},
        {"Linha": "(-) Impostos", "Valor": -impostos},
        {"Linha": "(-) Comissões", "Valor": -comissoes},
        {"Linha": "(-) Fretes", "Valor": -fretes},
        {"Linha": "(-) Embalagens", "Valor": -embalagens},
        {"Linha": "Lucro bruto CMV", "Valor": lucro_bruto_cmv},
        {"Linha": "Lucro bruto CMF", "Valor": lucro_bruto_cmf},
        {"Linha": "(-) ADS", "Valor": -ads},
        {"Linha": "(-) Despesas fixas", "Valor": -despesas_fixas},
        {"Linha": "(-) Serviços operacionais", "Valor": -servicos},
        {"Linha": "Lucro operacional CMV", "Valor": lucro_operacional_cmv},
        {"Linha": "Lucro operacional CMF", "Valor": lucro_operacional_cmf},
    ])
    st.dataframe(dre, use_container_width=True)

elif menu == "Resumo Mensal":
    pagina_resumo_mensal(db)

elif menu == "Importar XML":
    pagina_importar(db)

elif menu == "Lucro por Produto":
    pagina_lucro_produto(db)

elif menu == "Custos dos Produtos":
    pagina_custos_produtos(db)

elif menu == "Marketplaces":
    pagina_marketplaces(db)

elif menu == "Despesas Mensais":
    pagina_despesas(db)

elif menu == "Créditos (detalhe)":
    pagina_creditos(db)

elif menu == "Apuração (período)":
    pagina_apuracao(db)

elif menu == "Capital de Giro":
    st.markdown('<div class="main-title">Capital de Giro</div>', unsafe_allow_html=True)

    caixa_atual = st.number_input("Caixa disponível hoje", value=0.0, step=1000.0)
    receber_30 = total_receber()
    pagar_30 = total_pagar(apenas_plano=True)
    capital_giro = caixa_atual + receber_30 - pagar_30

    c1, c2, c3 = st.columns(3)
    c1.metric("Caixa atual", brl(caixa_atual))
    c2.metric("Receber previsto", brl(receber_30))
    c3.metric("Pagar no plano", brl(pagar_30))

    st.metric("Capital de giro líquido projetado", brl(capital_giro))
    if capital_giro < 0:
        st.error("Situação crítica: há necessidade de capital adicional.")
    elif capital_giro < 30000:
        st.warning("Atenção: capital de giro baixo para a operação.")
    else:
        st.success("Capital de giro positivo pelo plano atual.")

elif menu == "Produtos":
    st.markdown('<div class="main-title">Produtos</div>', unsafe_allow_html=True)

    produtos = db.query(Produto).all()
    df = pd.DataFrame([{
        "SKU": p.sku,
        "Produto": p.nome,
        "Categoria": p.categoria,
        "Fornecedor": p.fornecedor_padrao,
        "CMV": p.cmv_normal,
        "CMF": p.cmf_kemmax,
        "Custo Caixa": p.custo_caixa,
        "Preço ML": p.preco_ml,
        "Preço Shopee": p.preco_shopee,
        "Estoque Empresa": p.estoque_empresa,
        "Estoque FULL": p.estoque_full,
        "Venda média/dia": p.venda_media_dia
    } for p in produtos])
    st.dataframe(df, use_container_width=True)

elif menu == "Fornecedores":
    st.markdown('<div class="main-title">Fornecedores</div>', unsafe_allow_html=True)
    fornecedores = db.query(Fornecedor).all()
    df = pd.DataFrame([{"Nome": f.nome, "Categoria": f.categoria, "Observação": f.observacao} for f in fornecedores])
    st.dataframe(df, use_container_width=True)

elif menu == "Compras Inteligentes":
    st.markdown('<div class="main-title">Compras Inteligentes</div>', unsafe_allow_html=True)

    produtos = db.query(Produto).all()
    sku = st.selectbox("Produto", [p.sku for p in produtos])
    produto = db.query(Produto).filter_by(sku=sku).first()

    col1, col2, col3 = st.columns(3)
    fornecedor = col1.text_input("Fornecedor", value=produto.fornecedor_padrao if produto else "")
    valor = col2.number_input("Valor da mercadoria na NF sem IPI", value=21.58, step=0.01)
    ipi = col3.number_input("IPI %", value=0.0325, step=0.001, format="%.4f")

    col4, col5, col6 = st.columns(3)
    icms = col4.number_input("ICMS %", value=0.18, step=0.01, format="%.4f")
    fora = col5.number_input("CMF / Valor fora da NF", value=8.55, step=0.01)
    frete = col6.number_input("Frete de compra", value=0.0, step=0.01)

    col7, col8 = st.columns(2)
    embalagem = col7.number_input("Embalagem", value=0.0, step=0.01)
    outros = col8.number_input("Outros custos", value=0.0, step=0.01)

    normal = cmv_normal(valor, ipi, icms, fora, frete, outros, embalagem)
    kemmax = cmf_kemmax(valor, ipi, icms, fora, frete, outros, embalagem)

    c1, c2, c3 = st.columns(3)
    c1.metric("Custo caixa", brl(normal["custo_caixa"]))
    c2.metric("CMV Normal", brl(normal["cmv"]))
    c3.metric("CMF Kemmax", brl(kemmax["cmf"]))

    st.write("Crédito ICMS:", brl(normal["credito_icms"]))
    st.write("Crédito PIS/COFINS Normal:", brl(normal["credito_pis_cofins"]))
    st.write("Crédito PIS/COFINS CMF:", brl(kemmax["credito_pis_cofins"]))

    if st.button("Salvar simulação de compra"):
        db.add(CompraSimulada(
            produto_sku=sku, fornecedor=fornecedor, valor_mercadoria=valor, ipi_pct=ipi,
            icms_pct=icms, valor_fora_nf=fora, frete_compra=frete, embalagem=embalagem,
            cmv_normal=normal["cmv"], cmf_kemmax=kemmax["cmf"], custo_caixa=normal["custo_caixa"]
        ))
        db.commit()
        st.success("Simulação salva.")

elif menu == "Precificação":
    st.markdown('<div class="main-title">Precificação</div>', unsafe_allow_html=True)

    produtos = db.query(Produto).all()
    sku = st.selectbox("Produto", [p.sku for p in produtos])
    produto = db.query(Produto).filter_by(sku=sku).first()

    col1, col2, col3 = st.columns(3)
    canal = col1.selectbox("Canal", ["Mercado Livre", "Shopee"])
    preco = col2.number_input("Preço de venda", value=float(produto.preco_ml if canal == "Mercado Livre" else produto.preco_shopee), step=0.01)
    custo_tipo = col3.selectbox("Custo usado", ["CMF Kemmax", "CMV Normal", "Custo Caixa"])

    custo = produto.cmf_kemmax if custo_tipo == "CMF Kemmax" else produto.cmv_normal if custo_tipo == "CMV Normal" else produto.custo_caixa

    col4, col5, col6 = st.columns(3)
    comissao_ml = col4.number_input("Comissão ML %", value=0.12, step=0.01, format="%.4f")
    frete = col5.number_input("Frete", value=8.15, step=0.01)
    embalagem = col6.number_input("Embalagem", value=1.30, step=0.01)

    col7, col8, col9 = st.columns(3)
    rebate = col7.number_input("REBATE", value=0.0, step=0.01)
    devolucao_pct = col8.number_input("Devoluções %", value=0.02, step=0.01, format="%.4f")
    devolucao_custo = col9.number_input("Custo unitário devolução", value=3.0, step=0.01)

    resultado = resultado_marketplace(preco, custo, canal, comissao_ml, frete, embalagem, rebate, devolucao_pct, devolucao_custo)

    c1, c2, c3 = st.columns(3)
    c1.metric("Comissão", brl(resultado["comissao"]))
    c2.metric("Lucro unitário", brl(resultado["lucro"]))
    c3.metric("Margem", pct(resultado["margem"]))

    st.write("Crédito PIS/COFINS sobre comissão + frete:", brl(resultado["credito_comissao_frete"]))
    st.write("Provisão de devolução:", brl(resultado["provisao_devolucao"]))

elif menu == "Estoque e FULL":
    st.markdown('<div class="main-title">Estoque e FULL</div>', unsafe_allow_html=True)

    produtos = db.query(Produto).all()
    rows = []
    for p in produtos:
        estoque_total = p.estoque_empresa + p.estoque_full
        cob = cobertura_dias(estoque_total, p.venda_media_dia)
        ideal, sugerida = compra_sugerida(estoque_total, p.venda_media_dia, p.lead_time_dias, p.estoque_seguranca_dias)
        status = "Sem giro"
        if p.venda_media_dia > 0:
            if cob <= p.lead_time_dias:
                status = "Crítico"
            elif cob <= p.lead_time_dias + p.estoque_seguranca_dias:
                status = "Atenção"
            else:
                status = "OK"

        rows.append({
            "SKU": p.sku,
            "Produto": p.nome,
            "Empresa": p.estoque_empresa,
            "FULL": p.estoque_full,
            "Total": estoque_total,
            "Venda média/dia": p.venda_media_dia,
            "Cobertura dias": cob,
            "Lead time": p.lead_time_dias,
            "Estoque ideal": ideal,
            "Compra sugerida": sugerida,
            "Status": status,
            "Valor estoque caixa": estoque_total * p.custo_caixa
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    st.plotly_chart(px.bar(df, x="SKU", y="Cobertura dias", color="Status", title="Cobertura em dias por SKU"), use_container_width=True)

elif menu == "Posso Comprar?":
    st.markdown('<div class="main-title">Simulador: Posso Comprar?</div>', unsafe_allow_html=True)

    produtos = db.query(Produto).all()
    sku = st.selectbox("Produto", [p.sku for p in produtos])
    p = db.query(Produto).filter_by(sku=sku).first()

    col1, col2, col3 = st.columns(3)
    qtd_compra = col1.number_input("Quantidade que pretende comprar", value=1000.0, step=100.0)
    custo_unitario = col2.number_input("CMF unitário", value=float(p.cmf_kemmax or p.custo_caixa or 0), step=0.01)
    preco_venda = col3.number_input("Preço de venda", value=float(p.preco_ml or p.preco_shopee or 0), step=0.01)

    col4, col5, col6 = st.columns(3)
    canal = col4.selectbox("Canal de venda", ["Mercado Livre", "Shopee"])
    caixa_atual = col5.number_input("Caixa disponível hoje", value=0.0, step=1000.0)
    considerar_plano = col6.checkbox("Considerar plano priorizado", value=True)

    investimento = qtd_compra * custo_unitario
    receber = total_receber()
    pagar = total_pagar(apenas_plano=considerar_plano)
    saldo_apos_compra = caixa_atual + receber - pagar - investimento

    estoque_total = p.estoque_empresa + p.estoque_full
    ideal, sugerida = compra_sugerida(estoque_total, p.venda_media_dia, p.lead_time_dias, p.estoque_seguranca_dias)
    res = resultado_marketplace(preco_venda, custo_unitario, canal)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Investimento", brl(investimento))
    c2.metric("Saldo após compra", brl(saldo_apos_compra))
    c3.metric("Compra sugerida", f"{sugerida:.0f} un.")
    c4.metric("Lucro unitário estimado", brl(res["lucro"]))

    if saldo_apos_compra < 0:
        st.error("Não comprar agora: o caixa projetado fica negativo.")
    elif qtd_compra < sugerida:
        st.warning("Compra possível, mas a quantidade pode ser baixa para o giro atual.")
    else:
        st.success("Compra viável dentro dos dados informados.")

db.close()
