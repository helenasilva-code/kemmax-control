PIS = 0.0165
COFINS = 0.076
PIS_COFINS = PIS + COFINS

def brl(valor):
    try:
        valor = float(valor)
        if abs(valor) < 0.005:
            valor = 0.0  # evita "R$ -0,00"
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def pct(valor):
    try:
        return f"{float(valor) * 100:.2f}%".replace(".", ",")
    except Exception:
        return "0,00%"

def cmv_normal(valor_mercadoria, ipi_pct, icms_pct, valor_fora_nf=0, frete_compra=0, outros=0, embalagem=0):
    ipi = valor_mercadoria * ipi_pct
    nf_total = valor_mercadoria + ipi
    credito_icms = valor_mercadoria * icms_pct
    credito_pis_cofins = valor_mercadoria * PIS_COFINS
    custo_caixa = nf_total + valor_fora_nf + frete_compra + outros + embalagem
    cmv = custo_caixa - credito_icms - credito_pis_cofins
    return {
        "ipi": ipi,
        "nf_total": nf_total,
        "credito_icms": credito_icms,
        "credito_pis_cofins": credito_pis_cofins,
        "custo_caixa": custo_caixa,
        "cmv": cmv
    }

def cmf_kemmax(valor_mercadoria, ipi_pct, icms_pct, valor_fora_nf=0, frete_compra=0, outros=0, embalagem=0):
    ipi = valor_mercadoria * ipi_pct
    nf_total = valor_mercadoria + ipi
    credito_icms = valor_mercadoria * icms_pct
    base_pis_cofins = valor_mercadoria - credito_icms
    credito_pis_cofins = base_pis_cofins * PIS_COFINS
    custo_caixa = nf_total + valor_fora_nf + frete_compra + outros + embalagem
    cmf = custo_caixa - credito_icms - credito_pis_cofins
    return {
        "ipi": ipi,
        "nf_total": nf_total,
        "credito_icms": credito_icms,
        "base_pis_cofins": base_pis_cofins,
        "credito_pis_cofins": credito_pis_cofins,
        "custo_caixa": custo_caixa,
        "cmf": cmf
    }

def taxa_shopee(preco):
    if preco <= 79.99:
        return preco * 0.20 + 4
    if preco <= 99.99:
        return preco * 0.14 + 16
    if preco <= 199.99:
        return preco * 0.14 + 20
    return preco * 0.14 + 26

def resultado_marketplace(preco_venda, custo, canal, comissao_ml=0.12, frete=0, embalagem=0, rebate=0, devolucao_pct=0, devolucao_custo=0, imposto_venda_pct=0):
    if canal == "Shopee":
        comissao = taxa_shopee(preco_venda)
    elif canal == "Mercado Livre":
        comissao = preco_venda * comissao_ml
    else:
        comissao = preco_venda * comissao_ml

    credito_comissao_frete = (comissao + frete) * PIS_COFINS
    provisao_devolucao = preco_venda * devolucao_pct + devolucao_custo
    imposto_venda = preco_venda * imposto_venda_pct

    lucro = preco_venda - custo - comissao - frete - embalagem - provisao_devolucao - imposto_venda + rebate + credito_comissao_frete
    margem = lucro / preco_venda if preco_venda else 0

    return {
        "comissao": comissao,
        "credito_comissao_frete": credito_comissao_frete,
        "provisao_devolucao": provisao_devolucao,
        "imposto_venda": imposto_venda,
        "lucro": lucro,
        "margem": margem
    }

def ponto_equilibrio(despesas_fixas, margem_contribuicao):
    return despesas_fixas / margem_contribuicao if margem_contribuicao else 0

def cobertura_dias(estoque_total, venda_media_dia):
    return estoque_total / venda_media_dia if venda_media_dia else 0

def compra_sugerida(estoque_total, venda_media_dia, lead_time_dias, estoque_seguranca_dias):
    estoque_ideal = venda_media_dia * (lead_time_dias + estoque_seguranca_dias)
    qtd_sugerida = max(0, estoque_ideal - estoque_total)
    return estoque_ideal, qtd_sugerida
