from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Boolean
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

Base.metadata.create_all(bind=engine)
