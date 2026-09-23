"""Resultados mês a mês (compras, vendas, CT-e, apuração, DRE) e lucro por produto.

Funções puras sobre DataFrames: lancamentos_df, creditos_extras_df e os cadastros.
"""
import pandas as pd

from cadastros import SEM_MARKETPLACE, COLUNAS_DESPESAS
from fiscal_apuracao import (
    CSLL, IRPJ, IRPJ_ADICIONAL, IRPJ_LIMITE_ADICIONAL_MES, PIS_FINANCEIRO, COFINS_FINANCEIRO,
)
from fiscal_xml import somente_digitos

COMPRAS = ["Compra para revenda", "Compra para industrialização"]
OUTRAS_ENTRADAS = ["Uso e consumo", "Ativo imobilizado", "Bonificação / brinde", "Transferência", "Outras operações"]
FRETES = ["Frete sobre vendas", "Frete sobre compras", "Frete de transferência", "Frete - outros"]
NOMES_MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def meses_do_ano(ano, ate=None):
    """['2026-01', ...] até o mês de `ate` (date) quando for o mesmo ano."""
    ultimo = ate.month if ate is not None and ate.year == ano else 12
    return [f"{ano}-{m:02d}" for m in range(1, ultimo + 1)]


def rotulo_mes(mes):
    ano, m = mes.split("-")
    return f"{NOMES_MES[int(m) - 1]}/{ano[2:]}"


def _com_mes(df, coluna="data"):
    df = df.copy()
    df["mes"] = pd.to_datetime(df[coluna]).dt.strftime("%Y-%m") if not df.empty else pd.Series(dtype=str)
    return df


# ---------------------------------------------------------------- vendas por item

def vendas_itens(lanc, produtos, marketplaces):
    """Itens de venda e devolução de venda com marketplace, custos e lucro.

    produtos: produtos_custos_df; marketplaces: marketplaces_df.
    """
    colunas = ["mes", "data", "chave", "codigo", "descricao", "marketplace", "quantidade", "receita",
               "impostos", "comissao", "frete_marketplace", "embalagem", "cmv_dre", "cmv_financeiro",
               "lucro_dre", "lucro_financeiro", "custo_cadastrado"]
    if lanc.empty:
        return pd.DataFrame(columns=colunas)
    df = _com_mes(lanc[lanc["natureza"].isin(["Venda", "Devolução de venda"])])
    if df.empty:
        return pd.DataFrame(columns=colunas)

    # Marketplace: CNPJ do intermediador; a devolução herda o da venda original
    por_cnpj = {somente_digitos(c): n for n, c in zip(marketplaces["nome"], marketplaces["cnpj_intermediador"]) if c}
    intermed_venda = dict(zip(lanc["chave"], lanc["intermediador"].fillna("")))
    cnpj = df["intermediador"].fillna("")
    cnpj = cnpj.where(cnpj != "", df["chave_ref"].fillna("").map(intermed_venda).fillna(""))
    df["marketplace"] = cnpj.map(lambda c: por_cnpj.get(somente_digitos(c), SEM_MARKETPLACE if not c else f"Outro ({c})"))

    taxas = marketplaces.set_index("nome")
    venda = df["natureza"] == "Venda"
    sinal = venda.map({True: 1.0, False: -1.0})
    df["quantidade"] = df["quantidade"].fillna(0) * sinal
    df["impostos"] = (df["icms_debito"] + df["difal"] + df["pis_debito"] + df["cofins_debito"]
                      - df["icms_credito"] - df["pis_credito"] - df["cofins_credito"])
    pct = df["marketplace"].map(taxas["comissao_pct"]).fillna(0)
    fixa = df["marketplace"].map(taxas["taxa_fixa"]).fillna(0)
    frete = df["marketplace"].map(taxas["frete_medio"]).fillna(0)
    # Na devolução o marketplace estorna a comissão; frete e embalagem já foram gastos
    df["comissao"] = df["receita"] * pct + df["quantidade"] * fixa
    df["frete_marketplace"] = (df["quantidade"] * frete).where(venda, 0.0)

    chave_sku = produtos["sku"].astype(str).str.strip().str.upper()
    custos = produtos.assign(chave_sku=chave_sku).drop_duplicates("chave_sku").set_index("chave_sku")
    sku = df["codigo"].fillna("").astype(str).str.strip().str.upper()
    cmv_dre = sku.map(custos["cmv_normal"]).fillna(0)
    cmv_fin = sku.map(custos["cmf_kemmax"]).fillna(0)
    embalagem = sku.map(custos["embalagem_unit"]).fillna(0)
    df["custo_cadastrado"] = cmv_dre > 0
    df["embalagem"] = (df["quantidade"] * embalagem).where(venda, 0.0)
    df["cmv_dre"] = df["quantidade"] * cmv_dre
    df["cmv_financeiro"] = df["quantidade"] * cmv_fin.where(cmv_fin > 0, cmv_dre)
    df["lucro_dre"] = (df["receita"] - df["impostos"] - df["comissao"] - df["frete_marketplace"]
                       - df["embalagem"] - df["cmv_dre"])
    df["lucro_financeiro"] = df["lucro_dre"] - (df["cmv_financeiro"] - df["cmv_dre"])
    return df[colunas]


VALORES_PRODUTO = ["quantidade", "receita", "impostos", "comissao", "frete_marketplace", "embalagem",
                   "cmv_dre", "cmv_financeiro", "lucro_dre", "lucro_financeiro"]


def lucro_por_produto(itens, por=("codigo",)):
    por = list(por)
    if itens.empty:
        return pd.DataFrame(columns=[*por, "descricao", *VALORES_PRODUTO, "margem_dre", "margem_financeira",
                                     "resultado", "custo_cadastrado"])
    agrupado = itens.groupby(por, as_index=False).agg(
        descricao=("descricao", "first"), custo_cadastrado=("custo_cadastrado", "all"),
        **{c: (c, "sum") for c in VALORES_PRODUTO})
    receita = agrupado["receita"].where(agrupado["receita"] != 0)
    agrupado["margem_dre"] = (agrupado["lucro_dre"] / receita).fillna(0)
    agrupado["margem_financeira"] = (agrupado["lucro_financeiro"] / receita).fillna(0)
    agrupado["resultado"] = agrupado["lucro_financeiro"].map(lambda v: "Lucro" if v >= 0 else "Prejuízo")
    agrupado.loc[~agrupado["custo_cadastrado"], "resultado"] = "Sem custo cadastrado"
    return agrupado.sort_values("lucro_financeiro")


# ---------------------------------------------------------------- tabelas mensais

class _Tabela:
    """Monta uma tabela Linha x Meses + Total."""

    def __init__(self, meses):
        self.meses = meses
        self.linhas = []

    def add(self, rotulo, valores, total="soma"):
        valores = [float(valores.get(m, 0.0)) for m in self.meses] if isinstance(valores, (dict, pd.Series)) else list(valores)
        if total == "soma":
            tot = sum(valores)
        elif total == "primeiro":
            tot = valores[0] if valores else 0.0
        else:
            tot = valores[-1] if valores else 0.0
        self.linhas.append([rotulo, *valores, tot])

    def df(self):
        return pd.DataFrame(self.linhas, columns=["Linha", *[rotulo_mes(m) for m in self.meses], "Total"])


def _soma_mes(df, coluna, filtro=None):
    if df.empty:
        return {}
    if filtro is not None:
        df = df[filtro(df)]
    return df.groupby("mes")[coluna].sum().to_dict()


def _conta_mes(df, filtro):
    if df.empty:
        return {}
    df = df[filtro(df)]
    return df.groupby("mes")["chave"].nunique().to_dict()


def _natureza(*nomes):
    return lambda d: d["natureza"].isin(nomes)


def tabela_compras(lanc, meses):
    t = _Tabela(meses)
    compras = _natureza(*COMPRAS)
    t.add("Notas de compra (qtde)", _conta_mes(lanc, compras))
    t.add("Valor das compras (total das NF)", _soma_mes(lanc, "valor_contabil", compras))
    t.add("IPI", _soma_mes(lanc, "ipi", compras))
    t.add("ICMS-ST", _soma_mes(lanc, "icms_st", compras))
    t.add("Crédito ICMS", _soma_mes(lanc, "icms_credito", compras))
    t.add("Crédito PIS", _soma_mes(lanc, "pis_credito", compras))
    t.add("Crédito COFINS", _soma_mes(lanc, "cofins_credito", compras))
    t.add("Custo líquido das compras (CMV DRE)", _soma_mes(lanc, "custo", compras))
    t.add("Devoluções de compra", _soma_mes(lanc, "valor_contabil", _natureza("Devolução de compra")))
    t.add("Uso e consumo / ativo / outras entradas", _soma_mes(
        lanc, "valor_contabil", lambda d: d["natureza"].isin(OUTRAS_ENTRADAS) & (d["direcao"] == "Entrada")))
    return t.df()


def tabela_vendas(itens, meses):
    t = _Tabela(meses)
    vendas = itens[itens["quantidade"] > 0] if not itens.empty else itens
    devol = itens[itens["quantidade"] < 0] if not itens.empty else itens
    for nome in sorted(vendas["marketplace"].unique()) if not vendas.empty else []:
        t.add(f"Vendas {nome}", _soma_mes(vendas, "receita", lambda d, n=nome: d["marketplace"] == n))
    t.add("Receita bruta total", _soma_mes(vendas, "receita"))
    t.add("Devoluções de vendas", _soma_mes(devol, "receita"))
    t.add("Unidades vendidas", _soma_mes(vendas, "quantidade"))
    t.add("Unidades devolvidas", _soma_mes(devol, "quantidade"))
    t.add("Comissões e taxas marketplaces", _soma_mes(itens, "comissao"))
    t.add("Lucro dos produtos (CMV DRE)", _soma_mes(itens, "lucro_dre"))
    t.add("Lucro dos produtos (CMV Financeiro)", _soma_mes(itens, "lucro_financeiro"))
    return t.df()


def tabela_cte(lanc, meses):
    t = _Tabela(meses)
    cte = lambda d: d["tipo_documento"] == "CT-e"  # noqa: E731
    t.add("CT-e (qtde)", _conta_mes(lanc, cte))
    for natureza in FRETES + ["Frete não tomado pela empresa"]:
        t.add(natureza, _soma_mes(lanc, "valor_contabil", _natureza(natureza)))
    t.add("Crédito ICMS CT-e", _soma_mes(lanc, "icms_credito", cte))
    t.add("Crédito PIS CT-e", _soma_mes(lanc, "pis_credito", cte))
    t.add("Crédito COFINS CT-e", _soma_mes(lanc, "cofins_credito", cte))
    total = pd.Series(_soma_mes(lanc, "icms_credito", cte), dtype=float).add(
        pd.Series(_soma_mes(lanc, "pis_credito", cte), dtype=float), fill_value=0).add(
        pd.Series(_soma_mes(lanc, "cofins_credito", cte), dtype=float), fill_value=0)
    t.add("Total de créditos CT-e", total.to_dict())
    return t.df()


def tabela_apuracao(lanc, extras, meses, saldos_iniciais=None):
    """Apuração mensal com o saldo credor passando para o mês seguinte."""
    saldos_iniciais = saldos_iniciais or {}
    t = _Tabela(meses)
    cte = lambda d: d["tipo_documento"] == "CT-e"  # noqa: E731
    nfe = lambda d: d["tipo_documento"] != "CT-e"  # noqa: E731
    resumo = {}
    for tributo, sufixo in (("ICMS", "icms"), ("PIS", "pis"), ("COFINS", "cofins")):
        debitos = _soma_mes(lanc, f"{sufixo}_debito")
        cred_nfe = _soma_mes(lanc, f"{sufixo}_credito", nfe)
        cred_cte = _soma_mes(lanc, f"{sufixo}_credito", cte)
        cred_extra = _soma_mes(extras, f"{sufixo}_credito")
        saldo = float(saldos_iniciais.get(tributo, 0.0))
        anteriores, recolher, transportar = [], [], []
        for mes in meses:
            anteriores.append(saldo)
            resultado = debitos.get(mes, 0) - cred_nfe.get(mes, 0) - cred_cte.get(mes, 0) - cred_extra.get(mes, 0) - saldo
            recolher.append(max(resultado, 0.0))
            saldo = max(-resultado, 0.0)
            transportar.append(saldo)
        t.add(f"{tributo} - Débitos (vendas)", debitos)
        t.add(f"{tributo} - (-) Créditos NF-e", cred_nfe)
        t.add(f"{tributo} - (-) Créditos CT-e", cred_cte)
        t.add(f"{tributo} - (-) Créditos extras", cred_extra)
        t.add(f"{tributo} - (-) Saldo credor anterior", anteriores, total="primeiro")
        t.add(f"{tributo} - A recolher", recolher)
        t.add(f"{tributo} - Saldo credor p/ próximo mês", transportar, total="ultimo")
        resumo[tributo] = dict(zip(meses, recolher))
    return t.df(), resumo


def _irpj_csll(lair):
    base = max(lair, 0.0)
    csll = base * CSLL
    irpj = base * IRPJ + max(base - IRPJ_LIMITE_ADICIONAL_MES, 0.0) * IRPJ_ADICIONAL
    return irpj, csll


def tabela_dre(lanc, extras, itens, despesas, meses, cmv_pelo_cadastro=True):
    """DRE mês a mês. despesas: despesas_df (colunas mes + COLUNAS_DESPESAS)."""
    vendas_nat = _natureza("Venda")
    devol_nat = _natureza("Devolução de venda")
    desp = despesas.set_index("mes") if not despesas.empty else pd.DataFrame(columns=list(COLUNAS_DESPESAS))

    def v(d, mes):
        return float(d.get(mes, 0.0))

    receita = _soma_mes(lanc, "receita", vendas_nat)
    devolucao = _soma_mes(lanc, "receita", devol_nat)
    icms = pd.Series(_soma_mes(lanc, "icms_debito", vendas_nat), dtype=float).sub(
        pd.Series(_soma_mes(lanc, "icms_credito", devol_nat), dtype=float), fill_value=0).to_dict()
    difal = _soma_mes(lanc, "difal", vendas_nat)
    pis = pd.Series(_soma_mes(lanc, "pis_debito", vendas_nat), dtype=float).sub(
        pd.Series(_soma_mes(lanc, "pis_credito", devol_nat), dtype=float), fill_value=0).to_dict()
    cofins = pd.Series(_soma_mes(lanc, "cofins_debito", vendas_nat), dtype=float).sub(
        pd.Series(_soma_mes(lanc, "cofins_credito", devol_nat), dtype=float), fill_value=0).to_dict()
    cmv_cadastro = _soma_mes(itens, "cmv_dre")
    cmv_fin = _soma_mes(itens, "cmv_financeiro")
    compras_liq = _soma_mes(lanc, "custo", lambda d: d["natureza"].isin(COMPRAS + ["Frete sobre compras", "Devolução de compra"]))
    comissao = _soma_mes(itens, "comissao")
    frete_mkt = _soma_mes(itens, "frete_marketplace")
    embalagem = _soma_mes(itens, "embalagem")
    fv = _natureza("Frete sobre vendas")
    frete_bruto, frete_creditos = _soma_mes(lanc, "valor_contabil", fv), [
        _soma_mes(lanc, c, fv) for c in ("icms_credito", "pis_credito", "cofins_credito")]
    frete_cte = {m: v(frete_bruto, m) - sum(v(c, m) for c in frete_creditos) for m in meses}
    creditos_extras = [_soma_mes(extras, c) for c in ("pis_credito", "cofins_credito", "icms_credito")]
    extras_total = {m: sum(v(c, m) for c in creditos_extras) for m in meses}

    linhas = {}
    for mes in meses:
        d = {c: float(desp.at[mes, c]) if mes in desp.index else 0.0 for c in COLUNAS_DESPESAS}
        rl = v(receita, mes) + v(devolucao, mes) - v(icms, mes) - v(difal, mes) - v(pis, mes) - v(cofins, mes)
        cmv = v(cmv_cadastro, mes) if cmv_pelo_cadastro else v(compras_liq, mes)
        lb = rl - cmv
        despesas_venda = v(comissao, mes) + v(frete_mkt, mes) + frete_cte[mes] + v(embalagem, mes)
        despesas_adm = d["ads"] + d["pessoal"] + d["despesas_fixas"] + d["servicos"] + d["outras"]
        operacional = lb - despesas_venda - despesas_adm + extras_total[mes]
        pc_fin = d["receitas_financeiras"] * (PIS_FINANCEIRO + COFINS_FINANCEIRO)
        lair = operacional + d["receitas_financeiras"] - pc_fin - d["despesas_financeiras"]
        irpj, csll = _irpj_csll(lair)
        liquido = lair - irpj - csll
        por_fora = v(cmv_fin, mes) - v(cmv_cadastro, mes)
        linhas[mes] = [
            ("Receita bruta de vendas", v(receita, mes)),
            ("(-) Devoluções de vendas", v(devolucao, mes)),
            ("(-) ICMS", -v(icms, mes)),
            ("(-) DIFAL / FCP", -v(difal, mes)),
            ("(-) PIS", -v(pis, mes)),
            ("(-) COFINS", -v(cofins, mes)),
            ("= Receita líquida", rl),
            ("(-) CMV DRE" + (" (custo cadastrado x vendas)" if cmv_pelo_cadastro else " (compras líquidas)"), -cmv),
            ("= Lucro bruto", lb),
            ("(-) Comissões e taxas marketplaces", -v(comissao, mes)),
            ("(-) Frete marketplaces (frete médio)", -v(frete_mkt, mes)),
            ("(-) Fretes CT-e sobre vendas (líquido de créditos)", -frete_cte[mes]),
            ("(-) Embalagens", -v(embalagem, mes)),
            *[(f"(-) {COLUNAS_DESPESAS[c]}", -d[c]) for c in ("ads", "pessoal", "despesas_fixas", "servicos", "outras")],
            ("(+) Créditos extras (energia, aluguel, armazenagem...)", extras_total[mes]),
            ("= Resultado operacional", operacional),
            ("(+) Receitas financeiras", d["receitas_financeiras"]),
            ("(-) PIS/COFINS sobre receitas financeiras", -pc_fin),
            ("(-) Despesas financeiras", -d["despesas_financeiras"]),
            ("= Lucro antes do IR e CSLL (LAIR)", lair),
            ("(-) CSLL 9%", -csll),
            ("(-) IRPJ 15% + adicional 10%", -irpj),
            ("= Lucro líquido (DRE)", liquido),
            ("(-) Pagamentos por fora da NF (CMV Financeiro - CMV DRE)", -por_fora),
            ("= Resultado financeiro (caixa)", liquido - por_fora),
        ]

    t = _Tabela(meses)
    rotulos = [r for r, _ in linhas[meses[0]]] if meses else []
    for i, rotulo in enumerate(rotulos):
        t.add(rotulo, [linhas[m][i][1] for m in meses])
    return t.df()


def indicadores(dre, apuracao_resumo):
    """Números de destaque (coluna Total) para os cards do painel."""
    total = dict(zip(dre["Linha"], dre["Total"]))
    return {
        "receita_bruta": total.get("Receita bruta de vendas", 0.0),
        "lucro_liquido": total.get("= Lucro líquido (DRE)", 0.0),
        "resultado_caixa": total.get("= Resultado financeiro (caixa)", 0.0),
        "impostos_recolher": sum(sum(v.values()) for v in apuracao_resumo.values()),
    }


def resumo_completo(lanc, extras, produtos, marketplaces, despesas, meses, saldos_iniciais=None,
                    cmv_pelo_cadastro=True):
    """Todas as tabelas mensais de uma vez. lanc/extras como vêm do banco (sem coluna mes)."""
    lanc = _com_mes(lanc)
    extras = _com_mes(extras)
    lanc = lanc[lanc["mes"].isin(meses)] if not lanc.empty else lanc
    extras = extras[extras["mes"].isin(meses)] if not extras.empty else extras
    itens = vendas_itens(lanc, produtos, marketplaces)
    apuracao, a_recolher = tabela_apuracao(lanc, extras, meses, saldos_iniciais)
    dre = tabela_dre(lanc, extras, itens, despesas, meses, cmv_pelo_cadastro)
    return {
        "itens": itens,
        "compras": tabela_compras(lanc, meses),
        "vendas": tabela_vendas(itens, meses),
        "cte": tabela_cte(lanc, meses),
        "apuracao": apuracao,
        "a_recolher": a_recolher,
        "dre": dre,
        "indicadores": indicadores(dre, a_recolher),
    }
