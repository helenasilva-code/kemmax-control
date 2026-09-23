"""Importação de XMLs para o banco, apuração de ICMS/PIS/COFINS e DRE fiscal (Lucro Real)."""
import io
from collections import Counter

import pandas as pd

from database import ConfigFiscalDB, DocumentoFiscal, LancamentoFiscal, CreditoExtra, NotaCancelada
from fiscal_rules import ConfigFiscal, classificar
from fiscal_xml import ler_xml

CAMPOS_VALOR = [
    "valor_contabil", "receita", "base_icms", "icms_debito", "icms_credito", "icms_st",
    "ipi", "difal", "base_pis_cofins", "pis_debito", "cofins_debito",
    "pis_credito", "cofins_credito", "custo",
]

CAMPOS_LANCAMENTO = [
    "chave", "tipo_documento", "numero", "data", "direcao", "participante", "intermediador", "chave_ref",
    "n_item", "codigo", "quantidade", "descricao", "cfop", "natureza", "observacao", *CAMPOS_VALOR,
]

# Alíquotas do IRPJ/CSLL no Lucro Real
IRPJ = 0.15
IRPJ_ADICIONAL = 0.10
IRPJ_LIMITE_ADICIONAL_MES = 20000.0
CSLL = 0.09
# PIS/COFINS sobre receitas financeiras (Decreto 8.426/2015)
PIS_FINANCEIRO = 0.0065
COFINS_FINANCEIRO = 0.04


# ---------------------------------------------------------------- configuração

def carregar_config(db):
    row = db.query(ConfigFiscalDB).first()
    if row is None:
        return ConfigFiscal()
    return ConfigFiscal(
        cnpjs=[c.strip() for c in (row.cnpjs or "").split(",") if c.strip()],
        aliq_pis=row.aliq_pis,
        aliq_cofins=row.aliq_cofins,
        excluir_icms_base_debito=row.excluir_icms_base_debito,
        excluir_icms_base_credito=row.excluir_icms_base_credito,
        incluir_ipi_credito=row.incluir_ipi_credito,
        incluir_st_credito=row.incluir_st_credito,
    )


def salvar_config(db, cfg):
    row = db.query(ConfigFiscalDB).first() or ConfigFiscalDB()
    row.cnpjs = ",".join(cfg.cnpjs)
    row.aliq_pis = cfg.aliq_pis
    row.aliq_cofins = cfg.aliq_cofins
    row.excluir_icms_base_debito = cfg.excluir_icms_base_debito
    row.excluir_icms_base_credito = cfg.excluir_icms_base_credito
    row.incluir_ipi_credito = cfg.incluir_ipi_credito
    row.incluir_st_credito = cfg.incluir_st_credito
    db.add(row)
    db.commit()


# ---------------------------------------------------------------- importação

def _gravar_lancamentos(db, documento_id, lancamentos):
    for lanc in lancamentos:
        db.add(LancamentoFiscal(documento_id=documento_id, **{k: lanc[k] for k in CAMPOS_LANCAMENTO}))


def cnpjs_candidatos(documentos):
    """CNPJs que mais aparecem nos XMLs (a empresa está em quase todos).

    Devolve lista de (cnpj, nome, quantidade) ordenada da mais frequente.
    """
    contagem, nomes = Counter(), {}
    for doc in documentos:
        if doc["tipo_documento"] == "NF-e":
            partes = [(doc["emitente_doc"], doc["emitente_nome"]), (doc["destinatario_doc"], doc["destinatario_nome"])]
        elif doc["tipo_documento"] == "CT-e":
            partes = [(doc["tomador_doc"], doc["tomador_nome"])]
        else:
            continue
        for cnpj, nome in {p for p in partes if len(p[0]) == 14}:
            contagem[cnpj] += 1
            nomes.setdefault(cnpj, nome)
    return [(cnpj, nomes[cnpj], qtd) for cnpj, qtd in contagem.most_common()]


def importar_documentos(db, documentos, cfg, progresso=None):
    """Grava documentos lidos por fiscal_xml.ler_arquivos.

    Ignora chaves já importadas; eventos de cancelamento removem a nota (antes ou
    depois dela ser importada). progresso(fração) é chamado a cada documento.

    Devolve dict com importados, duplicados, cancelados e erros [(arquivo, mensagem)].
    """
    resumo = {"importados": 0, "duplicados": 0, "cancelados": 0, "erros": []}
    existentes = {c for (c,) in db.query(DocumentoFiscal.chave)}
    canceladas = {c for (c,) in db.query(NotaCancelada.chave)}

    # Cancelamentos primeiro, para valer mesmo se a nota vier depois no mesmo lote
    for doc in documentos:
        if doc["tipo_documento"] == "Evento" and doc["chave"] not in canceladas:
            db.add(NotaCancelada(chave=doc["chave"], data_evento=doc["data_emissao"], arquivo=doc.get("arquivo", "")))
            canceladas.add(doc["chave"])
            if doc["chave"] in existentes:
                excluir_documentos(db, [doc["chave"]], commit=False)
                existentes.discard(doc["chave"])
            resumo["cancelados"] += 1

    notas = [d for d in documentos if d["tipo_documento"] != "Evento"]
    for i, doc in enumerate(notas, start=1):
        if progresso:
            progresso(i / len(notas))
        chave = doc["chave"]
        if chave in canceladas:
            continue
        if chave in existentes:
            resumo["duplicados"] += 1
            continue
        try:
            lancamentos = classificar(doc, cfg)
        except ValueError as exc:
            resumo["erros"].append((doc.get("arquivo", chave), str(exc)))
            continue

        registro = DocumentoFiscal(
            chave=chave,
            tipo_documento=doc["tipo_documento"],
            numero=doc["numero"],
            data_emissao=doc["data_emissao"],
            emitente=doc["emitente_nome"],
            destinatario=doc["destinatario_nome"],
            valor_total=doc["valor_total"],
            arquivo=doc.get("arquivo", ""),
            xml=doc.get("xml", ""),
        )
        db.add(registro)
        db.flush()
        _gravar_lancamentos(db, registro.id, lancamentos)
        existentes.add(chave)
        resumo["importados"] += 1
    db.commit()
    return resumo


def reprocessar(db, cfg):
    """Recalcula todos os lançamentos a partir dos XMLs guardados (após mudar a configuração)."""
    erros = []
    db.query(LancamentoFiscal).delete()
    for registro in db.query(DocumentoFiscal).all():
        try:
            _gravar_lancamentos(db, registro.id, classificar(ler_xml(registro.xml), cfg))
        except ValueError as exc:
            erros.append((registro.arquivo or registro.chave, str(exc)))
    db.commit()
    return erros


def excluir_documentos(db, chaves, commit=True):
    for registro in db.query(DocumentoFiscal).filter(DocumentoFiscal.chave.in_(chaves)).all():
        db.query(LancamentoFiscal).filter_by(documento_id=registro.id).delete()
        db.delete(registro)
    if commit:
        db.commit()


def apagar_dados_fiscais(db):
    for modelo in (LancamentoFiscal, DocumentoFiscal, NotaCancelada, CreditoExtra):
        db.query(modelo).delete()
    db.commit()


# ---------------------------------------------------------------- consultas

def lancamentos_df(db, inicio=None, fim=None):
    q = db.query(LancamentoFiscal)
    if inicio:
        q = q.filter(LancamentoFiscal.data >= inicio)
    if fim:
        q = q.filter(LancamentoFiscal.data <= fim)
    rows = q.order_by(LancamentoFiscal.data, LancamentoFiscal.numero, LancamentoFiscal.n_item).all()
    return pd.DataFrame([{k: getattr(r, k) for k in CAMPOS_LANCAMENTO} for r in rows], columns=CAMPOS_LANCAMENTO)


def documentos_df(db):
    rows = db.query(DocumentoFiscal).order_by(DocumentoFiscal.data_emissao).all()
    return pd.DataFrame([{
        "Tipo": r.tipo_documento,
        "Número": r.numero,
        "Emissão": r.data_emissao,
        "Emitente": r.emitente,
        "Destinatário": r.destinatario,
        "Valor": r.valor_total,
        "Chave": r.chave,
        "Arquivo": r.arquivo,
    } for r in rows])


def creditos_extras_df(db, inicio=None, fim=None):
    q = db.query(CreditoExtra)
    if inicio:
        q = q.filter(CreditoExtra.data >= inicio)
    if fim:
        q = q.filter(CreditoExtra.data <= fim)
    colunas = ["id", "data", "categoria", "descricao", "base_pis_cofins", "pis_credito", "cofins_credito", "icms_credito"]
    return pd.DataFrame([{k: getattr(r, k) for k in colunas} for r in q.order_by(CreditoExtra.data).all()], columns=colunas)


# ---------------------------------------------------------------- apuração

def _soma(df, coluna):
    return float(df[coluna].sum()) if not df.empty else 0.0


def apurar(lanc, extras, saldo_icms_anterior=0.0, saldo_pis_anterior=0.0, saldo_cofins_anterior=0.0):
    """Apuração de ICMS, PIS e COFINS do período.

    saldo_*_anterior = saldo credor vindo do período anterior (valor positivo).
    """
    resultado = {}
    tributos = {
        "ICMS": ("icms_debito", "icms_credito", saldo_icms_anterior),
        "PIS": ("pis_debito", "pis_credito", saldo_pis_anterior),
        "COFINS": ("cofins_debito", "cofins_credito", saldo_cofins_anterior),
    }
    for nome, (col_deb, col_cred, saldo_anterior) in tributos.items():
        debitos = _soma(lanc, col_deb)
        creditos_xml = _soma(lanc, col_cred)
        creditos_extras = _soma(extras, col_cred)
        saldo = debitos - creditos_xml - creditos_extras - saldo_anterior
        resultado[nome] = {
            "debitos": debitos,
            "creditos_documentos": creditos_xml,
            "creditos_extras": creditos_extras,
            "saldo_credor_anterior": saldo_anterior,
            "a_recolher": max(saldo, 0.0),
            "saldo_credor_transportar": max(-saldo, 0.0),
        }
    return resultado


def apuracao_df(resultado):
    linhas = [
        ("Débitos (saídas)", "debitos"),
        ("(-) Créditos dos XMLs (NF-e / CT-e)", "creditos_documentos"),
        ("(-) Créditos extras", "creditos_extras"),
        ("(-) Saldo credor anterior", "saldo_credor_anterior"),
        ("= Imposto a recolher", "a_recolher"),
        ("= Saldo credor a transportar", "saldo_credor_transportar"),
    ]
    return pd.DataFrame([
        {"Linha": rotulo, **{t: resultado[t][chave] for t in ("ICMS", "PIS", "COFINS")}}
        for rotulo, chave in linhas
    ])


def resumo_por_natureza(lanc):
    if lanc.empty:
        return pd.DataFrame(columns=["direcao", "natureza", "documentos", *CAMPOS_VALOR])
    agrupado = lanc.groupby(["direcao", "natureza"], as_index=False).agg(
        documentos=("chave", "nunique"), **{c: (c, "sum") for c in CAMPOS_VALOR}
    )
    return agrupado.sort_values(["direcao", "natureza"])


def resumo_mensal(lanc, extras):
    """Créditos e débitos por mês (para gráfico e conferência)."""
    colunas = ["icms_debito", "icms_credito", "pis_debito", "pis_credito", "cofins_debito", "cofins_credito"]
    partes = []
    if not lanc.empty:
        df = lanc.copy()
        df["mes"] = pd.to_datetime(df["data"]).dt.to_period("M").astype(str)
        partes.append(df.groupby("mes")[colunas].sum())
    if not extras.empty:
        df = extras.copy()
        df["mes"] = pd.to_datetime(df["data"]).dt.to_period("M").astype(str)
        for c in ("icms_debito", "pis_debito", "cofins_debito"):
            df[c] = 0.0
        partes.append(df.groupby("mes")[colunas].sum())
    if not partes:
        return pd.DataFrame(columns=["mes", *colunas])
    return pd.concat(partes).groupby(level=0).sum().reset_index()


# ---------------------------------------------------------------- exportação

def exportar_excel(planilhas):
    """planilhas: dict {nome_aba: DataFrame}. Devolve bytes do .xlsx."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nome, df in planilhas.items():
            df.to_excel(writer, sheet_name=nome[:31], index=False)
    return buffer.getvalue()
