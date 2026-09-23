from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import date

engine = create_engine("sqlite:///kemmax_control.db", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Produto(Base):
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True)
    nome = Column(String)
    categoria = Column(String)
    fornecedor_padrao = Column(String)
    cmv_normal = Column(Float, default=0)
    cmf_kemmax = Column(Float, default=0)
    custo_caixa = Column(Float, default=0)
    preco_ml = Column(Float, default=0)
    preco_shopee = Column(Float, default=0)
    estoque_empresa = Column(Float, default=0)
    estoque_full = Column(Float, default=0)
    venda_media_dia = Column(Float, default=0)
    lead_time_dias = Column(Float, default=20)
    estoque_seguranca_dias = Column(Float, default=15)

class Fornecedor(Base):
    __tablename__ = "fornecedores"
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True)
    categoria = Column(String)
    observacao = Column(String)

class ContaPagar(Base):
    __tablename__ = "contas_pagar"
    id = Column(Integer, primary_key=True)
    vencimento = Column(Date)
    fornecedor = Column(String)
    descricao = Column(String)
    categoria = Column(String)
    valor = Column(Float, default=0)
    prioridade = Column(String, default="Média")
    status = Column(String, default="Previsto")
    pagar_no_plano = Column(Boolean, default=True)

class ContaReceber(Base):
    __tablename__ = "contas_receber"
    id = Column(Integer, primary_key=True)
    data_prevista = Column(Date)
    canal = Column(String)
    descricao = Column(String)
    valor_bruto = Column(Float, default=0)
    taxas = Column(Float, default=0)
    rebate = Column(Float, default=0)
    devolucoes = Column(Float, default=0)
    status = Column(String, default="Previsto")

class CompraSimulada(Base):
    __tablename__ = "compras_simuladas"
    id = Column(Integer, primary_key=True)
    data = Column(Date, default=date.today)
    produto_sku = Column(String)
    fornecedor = Column(String)
    valor_mercadoria = Column(Float, default=0)
    ipi_pct = Column(Float, default=0)
    icms_pct = Column(Float, default=0)
    valor_fora_nf = Column(Float, default=0)
    frete_compra = Column(Float, default=0)
    embalagem = Column(Float, default=0)
    cmv_normal = Column(Float, default=0)
    cmf_kemmax = Column(Float, default=0)
    custo_caixa = Column(Float, default=0)

class ConfigFiscalDB(Base):
    __tablename__ = "config_fiscal"
    id = Column(Integer, primary_key=True)
    cnpjs = Column(String, default="")
    aliq_pis = Column(Float, default=0.0165)
    aliq_cofins = Column(Float, default=0.076)
    excluir_icms_base_debito = Column(Boolean, default=True)
    excluir_icms_base_credito = Column(Boolean, default=True)
    incluir_ipi_credito = Column(Boolean, default=True)
    incluir_st_credito = Column(Boolean, default=False)

class DocumentoFiscal(Base):
    __tablename__ = "documentos_fiscais"
    id = Column(Integer, primary_key=True)
    chave = Column(String, unique=True, index=True)
    tipo_documento = Column(String)
    numero = Column(String)
    data_emissao = Column(Date)
    emitente = Column(String)
    destinatario = Column(String)
    valor_total = Column(Float, default=0)
    arquivo = Column(String)
    xml = Column(Text)

class LancamentoFiscal(Base):
    __tablename__ = "lancamentos_fiscais"
    id = Column(Integer, primary_key=True)
    documento_id = Column(Integer, ForeignKey("documentos_fiscais.id", ondelete="CASCADE"), index=True)
    chave = Column(String, index=True)
    tipo_documento = Column(String)
    numero = Column(String)
    data = Column(Date, index=True)
    direcao = Column(String)
    participante = Column(String)
    n_item = Column(Integer)
    descricao = Column(String)
    cfop = Column(String)
    natureza = Column(String)
    valor_contabil = Column(Float, default=0)
    receita = Column(Float, default=0)
    base_icms = Column(Float, default=0)
    icms_debito = Column(Float, default=0)
    icms_credito = Column(Float, default=0)
    icms_st = Column(Float, default=0)
    ipi = Column(Float, default=0)
    difal = Column(Float, default=0)
    base_pis_cofins = Column(Float, default=0)
    pis_debito = Column(Float, default=0)
    cofins_debito = Column(Float, default=0)
    pis_credito = Column(Float, default=0)
    cofins_credito = Column(Float, default=0)
    custo = Column(Float, default=0)
    observacao = Column(String)

class CreditoExtra(Base):
    """Créditos fora dos XMLs: energia, aluguel, armazenagem (FULL), depreciação, CIAP..."""
    __tablename__ = "creditos_extras"
    id = Column(Integer, primary_key=True)
    data = Column(Date)
    categoria = Column(String)
    descricao = Column(String)
    base_pis_cofins = Column(Float, default=0)
    pis_credito = Column(Float, default=0)
    cofins_credito = Column(Float, default=0)
    icms_credito = Column(Float, default=0)

Base.metadata.create_all(bind=engine)
