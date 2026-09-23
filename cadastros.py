"""Cadastros usados nos resultados: custos dos produtos, marketplaces e despesas mensais."""
import pandas as pd

from database import Produto, Marketplace, DespesaMensal
from fiscal_xml import somente_digitos

SEM_MARKETPLACE = "Venda direta / outros"

# Valores iniciais: confira as taxas atuais de cada marketplace e ajuste na tela
MARKETPLACES_PADRAO = [
    ("Mercado Livre", "03007331000141", 0.12, 0.0, 0.0),
    ("Shopee", "35635824000112", 0.20, 4.0, 0.0),
    ("Amazon", "15436940000103", 0.0, 0.0, 0.0),
    ("Magalu", "47960950000121", 0.0, 0.0, 0.0),
    (SEM_MARKETPLACE, "", 0.0, 0.0, 0.0),
]

COLUNAS_DESPESAS = {
    "ads": "ADS / Publicidade",
    "pessoal": "Pessoal e pró-labore",
    "despesas_fixas": "Despesas fixas",
    "servicos": "Serviços",
    "outras": "Outras despesas",
    "receitas_financeiras": "Receitas financeiras",
    "despesas_financeiras": "Despesas financeiras",
}


# ---------------------------------------------------------------- custos dos produtos

def calcular_custo(valor_nf, ipi_pct, icms_pct, valor_por_fora, frete_unit, cfg):
    """Custo unitário de um produto.

    CMV DRE: o que está na nota (mercadoria + IPI + frete) menos os créditos de
    ICMS e PIS/COFINS. CMV Financeiro: CMV DRE + o que é pago por fora da nota.
    """
    ipi = valor_nf * ipi_pct
    icms = valor_nf * icms_pct
    base_pc = valor_nf + frete_unit
    if cfg.incluir_ipi_credito:
        base_pc += ipi
    if cfg.excluir_icms_base_credito:
        base_pc -= icms
    pis_cofins = max(base_pc, 0.0) * (cfg.aliq_pis + cfg.aliq_cofins)
    cmv_dre = valor_nf + ipi + frete_unit - icms - pis_cofins
    return {
        "credito_icms": icms,
        "credito_pis_cofins": pis_cofins,
        "cmv_dre": cmv_dre,
        "cmv_financeiro": cmv_dre + valor_por_fora,
        "custo_caixa": valor_nf + ipi + frete_unit + valor_por_fora,
    }


def produtos_custos_df(db):
    colunas = ["sku", "nome", "valor_nf", "ipi_pct", "icms_pct", "valor_por_fora", "frete_unit",
               "embalagem_unit", "cmv_normal", "cmf_kemmax", "custo_caixa"]
    rows = db.query(Produto).order_by(Produto.sku).all()
    return pd.DataFrame([{c: getattr(p, c) for c in colunas} for p in rows], columns=colunas)


def salvar_custos(db, df, cfg):
    """Grava a tabela editada. Se o valor da NF foi informado, os CMVs são calculados;
    senão ficam os valores digitados em CMV DRE / CMV Financeiro. Produtos que saíram
    da tabela são excluídos. Devolve quantos foram excluídos."""
    numericas = ["valor_nf", "ipi_pct", "icms_pct", "valor_por_fora", "frete_unit", "embalagem_unit",
                 "cmv_normal", "cmf_kemmax"]
    df = df.copy()
    df[numericas] = df[numericas].fillna(0)
    df[["sku", "nome"]] = df[["sku", "nome"]].fillna("")
    skus = set()
    for linha in df.to_dict("records"):
        sku = str(linha["sku"]).strip()
        if not sku or sku in skus:
            continue
        skus.add(sku)
        p = db.query(Produto).filter_by(sku=sku).first() or Produto(sku=sku)
        p.nome = str(linha["nome"]).strip() or sku
        for campo in ("valor_nf", "ipi_pct", "icms_pct", "valor_por_fora", "frete_unit", "embalagem_unit"):
            setattr(p, campo, float(linha[campo] or 0))
        if p.valor_nf > 0:
            custo = calcular_custo(p.valor_nf, p.ipi_pct, p.icms_pct, p.valor_por_fora, p.frete_unit, cfg)
            p.cmv_normal = custo["cmv_dre"]
            p.cmf_kemmax = custo["cmv_financeiro"]
            p.custo_caixa = custo["custo_caixa"]
        else:
            p.cmv_normal = float(linha["cmv_normal"] or 0)
            p.cmf_kemmax = float(linha["cmf_kemmax"] or 0) or p.cmv_normal + p.valor_por_fora
        db.add(p)
    removidos = 0
    if skus:
        removidos = db.query(Produto).filter(Produto.sku.notin_(skus)).delete(synchronize_session=False)
    db.commit()
    return removidos


def cadastrar_produtos(db, codigos_nomes):
    """Cria produtos (sem custo) para códigos vendidos que ainda não têm cadastro."""
    existentes = {s.strip().upper() for (s,) in db.query(Produto.sku)}
    novos = 0
    for codigo, nome in codigos_nomes:
        if codigo and codigo.strip().upper() not in existentes:
            db.add(Produto(sku=codigo.strip(), nome=nome))
            existentes.add(codigo.strip().upper())
            novos += 1
    db.commit()
    return novos


# ---------------------------------------------------------------- marketplaces

def seed_marketplaces(db):
    if db.query(Marketplace).first():
        return
    for nome, cnpj, pct, fixa, frete in MARKETPLACES_PADRAO:
        db.add(Marketplace(nome=nome, cnpj_intermediador=cnpj, comissao_pct=pct, taxa_fixa=fixa, frete_medio=frete))
    db.commit()


def marketplaces_df(db):
    colunas = ["nome", "cnpj_intermediador", "comissao_pct", "taxa_fixa", "frete_medio"]
    rows = db.query(Marketplace).order_by(Marketplace.id).all()
    return pd.DataFrame([{c: getattr(m, c) for c in colunas} for m in rows], columns=colunas)


def salvar_marketplaces(db, df):
    df = df.fillna({"nome": "", "cnpj_intermediador": "", "comissao_pct": 0, "taxa_fixa": 0, "frete_medio": 0})
    nomes = [str(n).strip() for n in df["nome"] if str(n).strip()]
    db.query(Marketplace).filter(Marketplace.nome.notin_(nomes + [SEM_MARKETPLACE])).delete(synchronize_session=False)
    for linha in df.to_dict("records"):
        nome = str(linha["nome"]).strip()
        if not nome:
            continue
        m = db.query(Marketplace).filter_by(nome=nome).first() or Marketplace(nome=nome)
        m.cnpj_intermediador = somente_digitos(str(linha["cnpj_intermediador"]))
        m.comissao_pct = float(linha["comissao_pct"])
        m.taxa_fixa = float(linha["taxa_fixa"])
        m.frete_medio = float(linha["frete_medio"])
        db.add(m)
    db.commit()


# ---------------------------------------------------------------- despesas mensais

def despesas_df(db, meses):
    registros = {d.mes: d for d in db.query(DespesaMensal).filter(DespesaMensal.mes.in_(meses))}
    return pd.DataFrame([
        {"mes": mes, **{c: float(getattr(registros[mes], c) or 0) if mes in registros else 0.0 for c in COLUNAS_DESPESAS}}
        for mes in meses
    ], columns=["mes", *COLUNAS_DESPESAS])


def salvar_despesas(db, df):
    for linha in df.fillna(0).to_dict("records"):
        d = db.query(DespesaMensal).filter_by(mes=linha["mes"]).first() or DespesaMensal(mes=linha["mes"])
        for c in COLUNAS_DESPESAS:
            setattr(d, c, float(linha[c] or 0))
        db.add(d)
    db.commit()
