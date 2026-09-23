"""Leitura de XML de NF-e (modelo 55/65) e CT-e (modelo 57).

Funções puras: recebem bytes/str de XML e devolvem dicionários simples,
sem depender de banco de dados ou Streamlit.
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date


class XMLFiscalErro(Exception):
    pass


def _local(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find(el, *path):
    """Busca por caminho ignorando namespaces. Ex.: _find(ide, "dhEmi")."""
    atual = el
    for nome in path:
        if atual is None:
            return None
        atual = next((c for c in atual if _local(c.tag) == nome), None)
    return atual


def _find_any(el, nome):
    """Primeiro descendente com a tag informada (qualquer profundidade)."""
    if el is None:
        return None
    for c in el.iter():
        if _local(c.tag) == nome:
            return c
    return None


def _text(el, *path, default=""):
    alvo = _find(el, *path) if path else el
    if alvo is None or alvo.text is None:
        return default
    return alvo.text.strip()


def _num(el, *path):
    valor = _text(el, *path, default="")
    try:
        return float(valor) if valor else 0.0
    except ValueError:
        return 0.0


def _data(valor):
    """Converte dhEmi (2024-05-10T14:30:00-03:00) ou dEmi (2024-05-10) em date."""
    try:
        return date.fromisoformat((valor or "").strip()[:10])
    except ValueError:
        return None


def _doc(el):
    """CNPJ ou CPF de um grupo emit/dest/rem/toma."""
    if el is None:
        return ""
    return _text(el, "CNPJ") or _text(el, "CPF")


def somente_digitos(valor):
    return re.sub(r"\D", "", valor or "")


# ---------------------------------------------------------------- NF-e

def _imposto_icms(imposto):
    icms_grupo = _find(imposto, "ICMS")
    if icms_grupo is None or len(icms_grupo) == 0:
        return {"cst_icms": "", "vbc_icms": 0.0, "p_icms": 0.0, "v_icms": 0.0,
                "v_icms_st": 0.0, "v_cred_sn": 0.0}
    g = icms_grupo[0]
    cst = _text(g, "CST") or _text(g, "CSOSN")
    return {
        "cst_icms": cst,
        "vbc_icms": _num(g, "vBC"),
        "p_icms": _num(g, "pICMS"),
        "v_icms": _num(g, "vICMS"),
        "v_icms_st": _num(g, "vICMSST"),
        # Fornecedor do Simples Nacional informa o crédito permitido (CSOSN 101/201/900)
        "v_cred_sn": _num(g, "vCredICMSSN"),
    }


def _imposto_contrib(imposto, nome):
    grupo = _find(imposto, nome)
    if grupo is None or len(grupo) == 0:
        return "", 0.0
    g = grupo[0]
    return _text(g, "CST"), _num(g, "v" + nome)


def _imposto_ipi(imposto):
    ipi = _find(imposto, "IPI")
    if ipi is None:
        return 0.0
    trib = _find(ipi, "IPITrib")
    return _num(trib, "vIPI") if trib is not None else 0.0


def ler_nfe(root):
    inf = _find_any(root, "infNFe")
    if inf is None:
        raise XMLFiscalErro("XML não contém infNFe.")

    chave = somente_digitos(inf.get("Id", ""))
    prot = _find_any(root, "infProt")
    if not chave and prot is not None:
        chave = _text(prot, "chNFe")

    ide = _find(inf, "ide")
    emit = _find(inf, "emit")
    dest = _find(inf, "dest")
    total = _find(inf, "total", "ICMSTot")
    # Venda por marketplace: CNPJ do intermediador (obrigatório desde 2021)
    intermed = _find(inf, "infIntermed")
    # Devolução: chave da NF-e original
    refs = [_text(r) for r in ide.iter() if _local(r.tag) == "refNFe"] if ide is not None else []

    itens = []
    for det in (c for c in inf if _local(c.tag) == "det"):
        prod = _find(det, "prod")
        imposto = _find(det, "imposto")
        icms = _imposto_icms(imposto)
        cst_pis, v_pis = _imposto_contrib(imposto, "PIS")
        cst_cofins, v_cofins = _imposto_contrib(imposto, "COFINS")
        difal = _find(imposto, "ICMSUFDest")
        itens.append({
            "n_item": int(det.get("nItem", len(itens) + 1)),
            "codigo": _text(prod, "cProd"),
            "descricao": _text(prod, "xProd"),
            "ncm": _text(prod, "NCM"),
            "cfop": _text(prod, "CFOP"),
            "quantidade": _num(prod, "qCom"),
            "v_prod": _num(prod, "vProd"),
            "v_desc": _num(prod, "vDesc"),
            "v_frete": _num(prod, "vFrete"),
            "v_seg": _num(prod, "vSeg"),
            "v_outro": _num(prod, "vOutro"),
            "v_ipi": _imposto_ipi(imposto),
            "cst_pis": cst_pis,
            "v_pis": v_pis,
            "cst_cofins": cst_cofins,
            "v_cofins": v_cofins,
            "v_difal": _num(difal, "vICMSUFDest") + _num(difal, "vFCPUFDest") if difal is not None else 0.0,
            **icms,
        })

    return {
        "modelo": _text(ide, "mod") or "55",
        "tipo_documento": "NF-e",
        "chave": chave,
        "numero": _text(ide, "nNF"),
        "serie": _text(ide, "serie"),
        "data_emissao": _data(_text(ide, "dhEmi") or _text(ide, "dEmi")),
        "natureza": _text(ide, "natOp"),
        "tp_nf": _text(ide, "tpNF"),          # 0 = entrada, 1 = saída
        "fin_nfe": _text(ide, "finNFe"),      # 4 = devolução
        "emitente_doc": _doc(emit),
        "emitente_nome": _text(emit, "xNome"),
        "emitente_uf": _text(emit, "enderEmit", "UF"),
        "emitente_crt": _text(emit, "CRT"),   # 1/2 = Simples Nacional
        "destinatario_doc": _doc(dest),
        "destinatario_nome": _text(dest, "xNome"),
        "destinatario_uf": _text(dest, "enderDest", "UF"),
        "valor_total": _num(total, "vNF"),
        "intermediador_doc": _text(intermed, "CNPJ") if intermed is not None else "",
        "chave_ref": refs[0] if refs else "",
        "itens": itens,
    }


# ---------------------------------------------------------------- CT-e

_TOMA3 = {"0": "rem", "1": "exped", "2": "receb", "3": "dest"}


def ler_cte(root):
    inf = _find_any(root, "infCte")
    if inf is None:
        raise XMLFiscalErro("XML não contém infCte.")

    chave = somente_digitos(inf.get("Id", ""))
    ide = _find(inf, "ide")
    emit = _find(inf, "emit")
    partes = {nome: _find(inf, nome) for nome in ("rem", "exped", "receb", "dest")}

    toma3 = _find(ide, "toma3")
    if toma3 is None:
        toma3 = _find(ide, "toma03")
    toma4 = _find(ide, "toma4")
    if toma4 is not None:
        tomador_doc = _doc(toma4)
        tomador_nome = _text(toma4, "xNome")
    else:
        codigo = _text(toma3, "toma") if toma3 is not None else _text(ide, "toma")
        parte = partes.get(_TOMA3.get(codigo, "rem"))
        tomador_doc = _doc(parte)
        tomador_nome = _text(parte, "xNome")

    vprest = _find(inf, "vPrest")
    imp = _find(inf, "imp")
    icms_grupo = _find(imp, "ICMS")
    g = icms_grupo[0] if icms_grupo is not None and len(icms_grupo) else None
    cst = (_text(g, "CST") or _text(g, "CSOSN")) if g is not None else ""
    # ICMS90 "outra UF" e ICMSOutraUF usam vICMSOutraUF
    v_icms = _num(g, "vICMS") + _num(g, "vICMSOutraUF") if g is not None else 0.0
    vbc = _num(g, "vBC") + _num(g, "vBCOutraUF") if g is not None else 0.0
    simples = g is not None and _local(g.tag) == "ICMSSN"

    chaves_nfe = []
    for inf_doc in (c for c in inf.iter() if _local(c.tag) == "infNFe"):
        chave_nfe = _text(inf_doc, "chave")
        if chave_nfe:
            chaves_nfe.append(chave_nfe)

    valor = _num(vprest, "vTPrest")
    return {
        "modelo": _text(ide, "mod") or "57",
        "tipo_documento": "CT-e",
        "chave": chave,
        "numero": _text(ide, "nCT"),
        "serie": _text(ide, "serie"),
        "data_emissao": _data(_text(ide, "dhEmi")),
        "natureza": _text(ide, "natOp"),
        "cfop": _text(ide, "CFOP"),
        "emitente_doc": _doc(emit),
        "emitente_nome": _text(emit, "xNome"),
        "emitente_uf": _text(emit, "enderEmit", "UF"),
        "remetente_doc": _doc(partes["rem"]),
        "remetente_nome": _text(partes["rem"], "xNome"),
        "destinatario_doc": _doc(partes["dest"]),
        "destinatario_nome": _text(partes["dest"], "xNome"),
        "tomador_doc": tomador_doc,
        "tomador_nome": tomador_nome,
        "valor_total": valor,
        "vbc_icms": vbc,
        "v_icms": v_icms,
        "cst_icms": cst,
        "transportador_simples": simples,
        "chaves_nfe": chaves_nfe,
    }


# ---------------------------------------------------------------- entrada

# Cancelamento de NF-e/CT-e e cancelamento por substituição (NFC-e)
EVENTOS_CANCELAMENTO = {"110111", "110112"}


def ler_evento(root):
    inf = _find_any(root, "infEvento")
    chave = _text(inf, "chNFe") or _text(inf, "chCTe")
    tp_evento = _text(inf, "tpEvento")
    return {
        "tipo_documento": "Evento",
        "chave": chave,
        "tp_evento": tp_evento,
        "cancelamento": tp_evento in EVENTOS_CANCELAMENTO,
        "data_emissao": _data(_text(inf, "dhEvento")),
    }


def _decodificar(conteudo):
    """bytes -> str respeitando o encoding declarado (há XMLs em ISO-8859-1)."""
    if isinstance(conteudo, str):
        return conteudo
    conteudo = conteudo.lstrip(b"\xef\xbb\xbf")
    declaracao = re.match(rb'<\?xml[^>]*encoding=["\']([\w\-]+)["\']', conteudo)
    encoding = declaracao.group(1).decode() if declaracao else "utf-8"
    try:
        return conteudo.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return conteudo.decode("latin-1")


def ler_xml(conteudo):
    """Identifica o tipo do XML e devolve o documento lido."""
    texto = _decodificar(conteudo).lstrip("\ufeff")
    # Sem a declaração o ElementTree aceita str independente do encoding original
    texto = re.sub(r"^\s*<\?xml[^>]*\?>", "", texto)
    try:
        root = ET.fromstring(texto)
    except ET.ParseError as exc:
        raise XMLFiscalErro(f"XML inválido: {exc}") from exc

    # O CT-e também contém tags infNFe (NF-e transportadas), por isso vem primeiro
    if _find_any(root, "infCte") is not None:
        return ler_cte(root)
    if _find_any(root, "infNFe") is not None:
        return ler_nfe(root)
    if _find_any(root, "infEvento") is not None:
        return ler_evento(root)
    if _local(root.tag) in ("resNFe", "resEvento"):
        raise XMLFiscalErro("Resumo de NF-e: baixe o XML completo da nota.")
    raise XMLFiscalErro("XML não é NF-e, CT-e nem evento.")


def ler_arquivos(arquivos):
    """Recebe lista de (nome, bytes). Aceita .xml e .zip (inclusive com pastas e zips dentro).

    Devolve (documentos, erros) onde erros é lista de (nome, mensagem).
    Eventos de cancelamento vêm em documentos com tipo_documento == "Evento".
    """
    documentos, erros = [], []
    for nome, conteudo in arquivos:
        if nome.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
                    internos = [(f"{nome}/{n}", zf.read(n)) for n in zf.namelist()
                                if n.lower().endswith((".xml", ".zip")) and not n.startswith("__MACOSX/")]
            except zipfile.BadZipFile:
                erros.append((nome, "ZIP inválido."))
                continue
            docs, errs = ler_arquivos(internos)
            documentos.extend(docs)
            erros.extend(errs)
            continue
        try:
            doc = ler_xml(conteudo)
        except XMLFiscalErro as exc:
            erros.append((nome, str(exc)))
            continue
        if doc["tipo_documento"] == "Evento" and not doc["cancelamento"]:
            continue  # carta de correção, ciência da operação etc. não alteram valores
        doc["arquivo"] = nome
        doc["xml"] = _decodificar(conteudo)
        documentos.append(doc)
    return documentos, erros
