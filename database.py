from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import date
import os

# Caminho do banco: por padrão na pasta do app; KEMMAX_DB permite apontar para outra pasta
DB_PATH = os.environ.get("KEMMAX_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kemmax_control.db"))

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
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
    # Composição do custo unitário (tela Custos dos Produtos).
    # cmv_normal = CMV DRE (só a NF, líquido de créditos); cmf_kemmax = CMV Financeiro (NF + por fora)
    valor_nf = Column(Float, default=0)
    ipi_pct = Column(Float, default=0)
    icms_pct = Column(Float, default=0)
    valor_por_fora = Column(Float, default=0)
    frete_unit = Column(Float, default=0)
    embalagem_unit = Column(Float, default=0)

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
    intermediador = Column(String, default="")
    chave_ref = Column(String, default="")
    n_item = Column(Integer)
    codigo = Column(String, default="", index=True)
    quantidade = Column(Float, default=0)
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

class NotaCancelada(Base):
    """Chaves com evento de cancelamento: não entram na apuração nem se forem importadas depois."""
    __tablename__ = "notas_canceladas"
    id = Column(Integer, primary_key=True)
    chave = Column(String, unique=True, index=True)
    data_evento = Column(Date)
    arquivo = Column(String)

class Marketplace(Base):
    __tablename__ = "marketplaces"
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True)
    cnpj_intermediador = Column(String, default="")
    comissao_pct = Column(Float, default=0)
    taxa_fixa = Column(Float, default=0)          # por unidade vendida
    frete_medio = Column(Float, default=0)        # por unidade vendida (frete pago ao marketplace)

class DespesaMensal(Base):
    __tablename__ = "despesas_mensais"
    id = Column(Integer, primary_key=True)
    mes = Column(String, unique=True)             # AAAA-MM
    ads = Column(Float, default=0)
    pessoal = Column(Float, default=0)
    despesas_fixas = Column(Float, default=0)
    servicos = Column(Float, default=0)
    outras = Column(Float, default=0)
    receitas_financeiras = Column(Float, default=0)
    despesas_financeiras = Column(Float, default=0)

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

def migrar():
    """Cria tabelas e acrescenta colunas novas em bancos de versões anteriores."""
    from sqlalchemy import inspect, text
    Base.metadata.create_all(bind=engine)
    inspetor = inspect(engine)
    with engine.begin() as conn:
        for tabela in Base.metadata.sorted_tables:
            existentes = {c["name"] for c in inspetor.get_columns(tabela.name)}
            for coluna in tabela.columns:
                if coluna.name in existentes:
                    continue
                ddl = f"ALTER TABLE {tabela.name} ADD COLUMN {coluna.name} {coluna.type.compile(engine.dialect)}"
                padrao = coluna.default.arg if coluna.default is not None else None
                if isinstance(padrao, (bool, int, float)):
                    ddl += f" DEFAULT {int(padrao) if isinstance(padrao, bool) else padrao}"
                elif isinstance(padrao, str):
                    ddl += f" DEFAULT '{padrao}'"
                conn.execute(text(ddl))

migrar()


def backup_banco():
    """Cópia consistente do banco SQLite em bytes."""
    import sqlite3
    import tempfile
    with tempfile.TemporaryDirectory() as pasta:
        destino_path = os.path.join(pasta, "backup.db")
        origem = sqlite3.connect(DB_PATH)
        destino = sqlite3.connect(destino_path)
        with destino:
            origem.backup(destino)
        origem.close()
        destino.close()
        with open(destino_path, "rb") as f:
            return f.read()


def restaurar_banco(conteudo):
    """Substitui o banco atual por um backup gerado por backup_banco()."""
    import sqlite3
    import tempfile
    if not conteudo.startswith(b"SQLite format 3\x00"):
        raise ValueError("Arquivo não é um banco SQLite.")
    with tempfile.TemporaryDirectory() as pasta:
        origem_path = os.path.join(pasta, "restaurar.db")
        with open(origem_path, "wb") as f:
            f.write(conteudo)
        origem = sqlite3.connect(origem_path)
        tabelas = {r[0] for r in origem.execute("select name from sqlite_master where type='table'")}
        if "produtos" not in tabelas:
            origem.close()
            raise ValueError("Backup não é do Kemmax Control.")
        engine.dispose()
        destino = sqlite3.connect(DB_PATH)
        with destino:
            origem.backup(destino)
        origem.close()
        destino.close()
    # Backups antigos podem não ter as tabelas/colunas novas
    migrar()
