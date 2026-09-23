"""XMLs mínimos de NF-e e CT-e usados nos testes (CNPJ da empresa: 11111111000111)."""

EMPRESA = "11111111000111"
FORNECEDOR = "22222222000122"
CLIENTE = "33333333000133"
TRANSPORTADORA = "44444444000144"


def _item(n, cfop, v_prod, icms, v_ipi=0.0, cst_pis="01", v_st=0.0, v_frete=0.0, codigo=None, q=10):
    ipi = (f"<IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>{v_prod}</vBC><pIPI>5</pIPI>"
           f"<vIPI>{v_ipi:.2f}</vIPI></IPITrib></IPI>") if v_ipi else ""
    frete = f"<vFrete>{v_frete:.2f}</vFrete>" if v_frete else ""
    return f"""
    <det nItem="{n}">
      <prod><cProd>{codigo or f"P{n}"}</cProd><xProd>Produto {n}</xProd><NCM>48201000</NCM><CFOP>{cfop}</CFOP>
        <qCom>{q}</qCom><vProd>{v_prod:.2f}</vProd>{frete}</prod>
      <imposto>
        <ICMS><ICMS00><orig>0</orig><CST>00</CST><vBC>{v_prod:.2f}</vBC><pICMS>18</pICMS>
          <vICMS>{icms:.2f}</vICMS><vICMSST>{v_st:.2f}</vICMSST></ICMS00></ICMS>
        {ipi}
        <PIS><PISAliq><CST>{cst_pis}</CST><vBC>{v_prod}</vBC><pPIS>1.65</pPIS><vPIS>0</vPIS></PISAliq></PIS>
        <COFINS><COFINSAliq><CST>{cst_pis}</CST><vBC>{v_prod}</vBC><pCOFINS>7.6</pCOFINS><vCOFINS>0</vCOFINS></COFINSAliq></COFINS>
      </imposto>
    </det>"""


def nfe(chave, emit, dest, itens, tp_nf="1", data="2026-08-10", fin="1", total=0.0, intermediador="", ref=""):
    intermed = f"<infIntermed><CNPJ>{intermediador}</CNPJ><idCadIntTran>loja</idCadIntTran></infIntermed>" if intermediador else ""
    nfref = f"<NFref><refNFe>{ref}</refNFe></NFref>" if ref else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe{chave}" versao="4.00">
    <ide><cUF>35</cUF><natOp>Venda</natOp><mod>55</mod><serie>1</serie><nNF>{chave[-6:]}</nNF>
      <dhEmi>{data}T10:00:00-03:00</dhEmi><tpNF>{tp_nf}</tpNF><finNFe>{fin}</finNFe>{nfref}</ide>
    <emit><CNPJ>{emit}</CNPJ><xNome>Emitente {emit[:4]}</xNome><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>
    <dest><CNPJ>{dest}</CNPJ><xNome>Destinatario {dest[:4]}</xNome><enderDest><UF>SP</UF></enderDest></dest>
    {''.join(itens)}
    <total><ICMSTot><vNF>{total:.2f}</vNF></ICMSTot></total>
    {intermed}
  </infNFe></NFe>
</nfeProc>"""


def cte(chave, rem, dest, toma, valor, icms, data="2026-08-12"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00">
  <CTe><infCte Id="CTe{chave}" versao="4.00">
    <ide><cUF>35</cUF><CFOP>5353</CFOP><natOp>Prestacao de servico</natOp><mod>57</mod><serie>1</serie>
      <nCT>{chave[-6:]}</nCT><dhEmi>{data}T08:00:00-03:00</dhEmi><toma3><toma>{toma}</toma></toma3></ide>
    <emit><CNPJ>{TRANSPORTADORA}</CNPJ><xNome>Transportadora</xNome><enderEmit><UF>SP</UF></enderEmit></emit>
    <rem><CNPJ>{rem}</CNPJ><xNome>Remetente {rem[:4]}</xNome></rem>
    <dest><CNPJ>{dest}</CNPJ><xNome>Destinatario {dest[:4]}</xNome></dest>
    <vPrest><vTPrest>{valor:.2f}</vTPrest><vRec>{valor:.2f}</vRec></vPrest>
    <imp><ICMS><ICMS00><CST>00</CST><vBC>{valor:.2f}</vBC><pICMS>12</pICMS><vICMS>{icms:.2f}</vICMS></ICMS00></ICMS></imp>
    <infCTeNorm><infDoc><infNFe><chave>35260811111111000111550010000000011000000011</chave></infNFe></infDoc></infCTeNorm>
  </infCte></CTe>
</cteProc>"""
