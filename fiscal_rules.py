"""Regras de crédito e débito de ICMS, PIS e COFINS para empresa do Lucro Real
(PIS/COFINS não cumulativos - Leis 10.637/2002 e 10.833/2003).

Transforma um documento lido por fiscal_xml em lançamentos (um por item de NF-e
ou um por CT-e) com os valores de débito, crédito e custo já calculados.

As regras são uma parametrização padrão para empresa comercial. Casos
específicos (monofásicos, ativo imobilizado/CIAP, benefícios estaduais) devem
ser validados com a contabilidade.
"""
from dataclasses import dataclass, field

from fiscal_xml import somente_digitos


@dataclass
class ConfigFiscal:
    cnpjs: list = field(default_factory=list)
    aliq_pis: float = 0.0165
    aliq_cofins: float = 0.076
    # STF Tema 69: ICMS destacado não compõe a base do PIS/COFINS sobre vendas
    excluir_icms_base_debito: bool = True
    # Lei 14.592/2023: ICMS destacado sai da base do crédito na aquisição (a partir de 05/2023)
    excluir_icms_base_credito: bool = True
    # IPI não recuperável integra o custo de aquisição (IN RFB 2.121/2022)
    incluir_ipi_credito: bool = True
    # ICMS-ST pago na aquisição: tema controverso, desligado por padrão
    incluir_st_credito: bool = False

    def e_empresa(self, documento):
        doc = somente_digitos(documento)
        return bool(doc) and doc in {somente_digitos(c) for c in self.cnpjs}


# Natureza da operação pelos 3 últimos dígitos do CFOP.
# (natureza, credita/debita ICMS, credita/debita PIS-COFINS)
CFOP_ENTRADA = {
    **{s: ("Compra para industrialização", True, True) for s in ("101", "111", "116", "120", "122", "124", "125", "126", "401")},
    **{s: ("Compra para revenda", True, True) for s in ("102", "113", "117", "118", "121")},
    # Compra com ST (substituído): ICMS próprio não se credita, PIS/COFINS sim
    "403": ("Compra para revenda", False, True),
    **{s: ("Devolução de venda", True, True) for s in ("201", "202", "410", "411")},
    **{s: ("Ativo imobilizado", False, False) for s in ("406", "551")},
    **{s: ("Uso e consumo", False, False) for s in ("407", "556")},
    "910": ("Bonificação / brinde", True, False),
    **{s: ("Transferência", True, False) for s in ("151", "152", "153")},
}

CFOP_SAIDA = {
    **{s: ("Venda", True, True) for s in (
        "101", "102", "103", "104", "105", "106", "107", "108", "109", "110",
        "113", "114", "115", "116", "117", "118", "119", "120", "122", "123",
        "401", "402", "403")},
    # Substituído tributário: sem débito de ICMS próprio
    "405": ("Venda", False, True),
    **{s: ("Devolução de compra", True, True) for s in ("201", "202", "410", "411")},
    "551": ("Venda de ativo", True, False),
    "910": ("Bonificação / brinde", True, False),
    **{s: ("Transferência", True, False) for s in ("151", "152", "153")},
}

# CST de PIS/COFINS na saída que não geram débito (alíquota zero, monofásico,
# suspensão, isenção, não incidência, outras operações)
CST_SEM_DEBITO = {"04", "05", "06", "07", "08", "09", "49"}
# CST do fornecedor indicando produto monofásico/alíquota zero: revenda não gera crédito
CST_FORNECEDOR_SEM_CREDITO = {"04", "05", "06", "07", "08", "09"}


def cfop_entrada(cfop):
    """Converte o CFOP de saída do fornecedor (5/6/7xxx) no CFOP de entrada (1/2/3xxx)."""
    cfop = somente_digitos(cfop)
    if len(cfop) == 4 and cfop[0] in "567":
        return str(int(cfop[0]) - 4) + cfop[1:]
    return cfop


def _lancamento_base(doc, direcao):
    return {
        "chave": doc["chave"],
        "tipo_documento": doc["tipo_documento"],
        "numero": doc.get("numero", ""),
        "data": doc.get("data_emissao"),
        "direcao": direcao,
        "participante": "",
        "intermediador": doc.get("intermediador_doc", ""),
        "chave_ref": doc.get("chave_ref", ""),
        "n_item": 0,
        "codigo": "",
        "quantidade": 0.0,
        "descricao": "",
        "cfop": "",
        "natureza": "",
        "valor_contabil": 0.0,
        "receita": 0.0,
        "base_icms": 0.0,
        "icms_debito": 0.0,
        "icms_credito": 0.0,
        "icms_st": 0.0,
        "ipi": 0.0,
        "difal": 0.0,
        "base_pis_cofins": 0.0,
        "pis_debito": 0.0,
        "cofins_debito": 0.0,
        "pis_credito": 0.0,
        "cofins_credito": 0.0,
        "custo": 0.0,
        "observacao": "",
    }


def _base_credito_item(item, cfg):
    base = item["v_prod"] - item["v_desc"] + item["v_frete"] + item["v_seg"] + item["v_outro"]
    if cfg.incluir_ipi_credito:
        base += item["v_ipi"]
    if cfg.incluir_st_credito:
        base += item["v_icms_st"]
    if cfg.excluir_icms_base_credito:
        base -= item["v_icms"]
    return max(base, 0.0)


def _classificar_item_nfe(doc, item, direcao, cfop, participante, cfg):
    lanc = _lancamento_base(doc, direcao)
    sufixo = cfop[1:]
    tabela = CFOP_SAIDA if direcao == "Saída" else CFOP_ENTRADA
    natureza, usa_icms, usa_pc = tabela.get(sufixo, ("Outras operações", False, False))

    valor_mercadoria = item["v_prod"] - item["v_desc"] + item["v_frete"] + item["v_seg"] + item["v_outro"]
    valor_contabil = valor_mercadoria + item["v_ipi"] + item["v_icms_st"]
    obs = []

    lanc.update({
        "participante": participante,
        "n_item": item["n_item"],
        "codigo": item["codigo"],
        "quantidade": item["quantidade"],
        "descricao": item["descricao"],
        "cfop": cfop,
        "natureza": natureza,
        "valor_contabil": valor_contabil,
        "base_icms": item["vbc_icms"],
        "icms_st": item["v_icms_st"],
        "ipi": item["v_ipi"],
        "difal": item["v_difal"] if direcao == "Saída" else 0.0,
    })

    if natureza == "Outras operações":
        obs.append("CFOP sem crédito/débito automático - revisar")

    if direcao == "Saída":
        if usa_icms:
            lanc["icms_debito"] = item["v_icms"]
        if natureza == "Venda":
            lanc["receita"] = valor_mercadoria
            if usa_pc and item["cst_pis"] not in CST_SEM_DEBITO:
                base = valor_mercadoria - (item["v_icms"] if cfg.excluir_icms_base_debito else 0.0)
                base = max(base, 0.0)
                lanc["base_pis_cofins"] = base
                lanc["pis_debito"] = base * cfg.aliq_pis
                lanc["cofins_debito"] = base * cfg.aliq_cofins
            elif item["cst_pis"] in CST_SEM_DEBITO:
                obs.append(f"CST PIS {item['cst_pis']} sem débito")
        elif natureza == "Devolução de compra" and usa_pc:
            # Estorna o crédito tomado na compra
            base = _base_credito_item(item, cfg)
            lanc["base_pis_cofins"] = -base
            lanc["pis_credito"] = -base * cfg.aliq_pis
            lanc["cofins_credito"] = -base * cfg.aliq_cofins
            lanc["custo"] = -(valor_contabil - lanc["icms_debito"] - base * (cfg.aliq_pis + cfg.aliq_cofins))
    else:
        credito_icms = 0.0
        if usa_icms:
            credito_icms = item["v_icms"] or item["v_cred_sn"]
        lanc["icms_credito"] = credito_icms

        credito_pc_base = 0.0
        if usa_pc:
            if natureza == "Devolução de venda":
                # Anula o débito da venda: mesma base usada na saída
                credito_pc_base = valor_mercadoria - (item["v_icms"] if cfg.excluir_icms_base_debito else 0.0)
                lanc["receita"] = -valor_mercadoria
            elif cfop.startswith("3"):
                # Importação: crédito = PIS/COFINS-Importação pagos (informados na NF-e de entrada)
                lanc["pis_credito"] = item["v_pis"]
                lanc["cofins_credito"] = item["v_cofins"]
                obs.append("Importação: crédito pelo PIS/COFINS-Importação da NF")
            elif item["cst_pis"] in CST_FORNECEDOR_SEM_CREDITO:
                obs.append(f"Fornecedor CST PIS {item['cst_pis']} (monofásico/alíquota zero) - sem crédito")
            else:
                credito_pc_base = _base_credito_item(item, cfg)

        if credito_pc_base:
            credito_pc_base = max(credito_pc_base, 0.0)
            lanc["base_pis_cofins"] = credito_pc_base
            lanc["pis_credito"] = credito_pc_base * cfg.aliq_pis
            lanc["cofins_credito"] = credito_pc_base * cfg.aliq_cofins

        if natureza in ("Compra para revenda", "Compra para industrialização"):
            lanc["custo"] = valor_contabil - credito_icms - lanc["pis_credito"] - lanc["cofins_credito"]
        elif natureza == "Ativo imobilizado":
            obs.append("Crédito via CIAP (ICMS 1/48) e depreciação (PIS/COFINS) - lançar em Créditos Extras")

    lanc["observacao"] = "; ".join(obs)
    return lanc


def classificar_nfe(doc, cfg):
    emitente_e_empresa = cfg.e_empresa(doc["emitente_doc"])
    destinatario_e_empresa = cfg.e_empresa(doc["destinatario_doc"])

    if emitente_e_empresa:
        direcao = "Saída" if doc["tp_nf"] == "1" else "Entrada"
        participante = doc["destinatario_nome"]
        converter = False
    elif destinatario_e_empresa and doc["tp_nf"] == "1":
        direcao = "Entrada"
        participante = doc["emitente_nome"]
        converter = True
    elif destinatario_e_empresa:
        raise ValueError("NF-e de entrada emitida por terceiro: a escrituração é do emitente.")
    else:
        raise ValueError("CNPJ da empresa não é emitente nem destinatário da NF-e.")

    lancamentos = []
    for item in doc["itens"]:
        cfop = cfop_entrada(item["cfop"]) if converter else somente_digitos(item["cfop"])
        lancamentos.append(_classificar_item_nfe(doc, item, direcao, cfop, participante, cfg))
    return lancamentos


def classificar_cte(doc, cfg):
    lanc = _lancamento_base(doc, "Entrada")
    lanc.update({
        "participante": doc["emitente_nome"],
        "descricao": f"Frete {doc['remetente_nome']} → {doc['destinatario_nome']}",
        "cfop": somente_digitos(doc.get("cfop", "")),
        "valor_contabil": doc["valor_total"],
        "base_icms": doc["vbc_icms"],
    })

    if not cfg.e_empresa(doc["tomador_doc"]):
        lanc["natureza"] = "Frete não tomado pela empresa"
        lanc["valor_contabil"] = 0.0
        lanc["observacao"] = f"Tomador: {doc['tomador_nome'] or doc['tomador_doc']} - sem crédito"
        return [lanc]

    remetente = cfg.e_empresa(doc["remetente_doc"])
    destinatario = cfg.e_empresa(doc["destinatario_doc"])
    obs = []
    if remetente and destinatario:
        natureza, credita_pc = "Frete de transferência", False
        obs.append("Frete entre estabelecimentos: sem crédito de PIS/COFINS")
    elif remetente:
        # Lei 10.833/2003, art. 3º, IX: frete na operação de venda
        natureza, credita_pc = "Frete sobre vendas", True
    elif destinatario:
        # Integra o custo de aquisição
        natureza, credita_pc = "Frete sobre compras", True
    else:
        natureza, credita_pc = "Frete - outros", False
        obs.append("Empresa é tomadora mas não é remetente nem destinatária - revisar")

    lanc["natureza"] = natureza
    lanc["icms_credito"] = doc["v_icms"]
    if doc["transportador_simples"]:
        obs.append("Transportadora do Simples: sem ICMS destacado")

    if credita_pc:
        base = doc["valor_total"]
        lanc["base_pis_cofins"] = base
        lanc["pis_credito"] = base * cfg.aliq_pis
        lanc["cofins_credito"] = base * cfg.aliq_cofins

    liquido = doc["valor_total"] - lanc["icms_credito"] - lanc["pis_credito"] - lanc["cofins_credito"]
    if natureza == "Frete sobre compras":
        lanc["custo"] = liquido
    lanc["observacao"] = "; ".join(obs)
    return [lanc]


def classificar(doc, cfg):
    if doc["tipo_documento"] == "CT-e":
        return classificar_cte(doc, cfg)
    return classificar_nfe(doc, cfg)
