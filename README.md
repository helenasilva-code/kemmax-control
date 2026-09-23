# Kemmax Control Profissional

Sistema web inicial para gestão da Kemmax.

## Módulos principais

- Dashboard Executivo
- Financeiro
- Fluxo de Caixa
- DRE Gerencial
- Capital de Giro
- Produtos
- Fornecedores
- Compras Inteligentes
- CMV Normal
- CMF Kemmax
- Precificação Mercado Livre e Shopee
- Plano de pagamentos
- Simulador "Posso Comprar?"
- Fiscal e Resultados (Lucro Real): XML de NF-e/CT-e, resumo mensal, créditos, apuração, DRE mensal e lucro por produto

## Fiscal e Resultados (Lucro Real)

Área **Fiscal e Resultados** no menu lateral:

| Tela | Para que serve |
|---|---|
| **Resumo Mensal** | Jan → mês atual: DRE, compras, vendas por marketplace, CT-e/fretes, créditos e apuração de ICMS/PIS/COFINS (saldo credor passa de um mês para o outro). Botão para baixar tudo em Excel. |
| **Importar XML** | Envie os `.zip` de cada mês (NF-e de compra e venda, CT-e, cancelamentos). Na primeira vez o sistema sugere o CNPJ da empresa. Aba Backup. |
| **Lucro por Produto** | Por SKU (e por marketplace ou mês): receita − impostos − comissão − taxa fixa − frete − embalagem − CMV. Mostra Lucro DRE e Lucro Financeiro e marca **Lucro / Prejuízo**. |
| **Custos dos Produtos** | Valor na NF, IPI %, ICMS %, valor **pago por fora**, frete e embalagem por unidade → calcula **CMV DRE** (só a nota, líquido de créditos) e **CMV Financeiro** (CMV DRE + por fora). Consulta das últimas compras para preencher. |
| **Marketplaces** | Comissão %, taxa fixa por unidade e frete médio de cada canal. A venda é ligada ao marketplace pelo CNPJ do intermediador da NF-e. |
| **Despesas Mensais** | ADS, pessoal, despesas fixas, serviços, outras e resultado financeiro de cada mês, para fechar a DRE. |
| **Créditos (detalhe)** / **Apuração (período)** | Conferência nota a nota e créditos extras (armazenagem FULL, energia, aluguel, CIAP). |

### Como o sistema calcula

1. Identifica entrada/saída pelo CNPJ, converte o CFOP do fornecedor (5102 → 1102) e calcula por item:
   - **Compras para revenda/industrialização**: crédito do ICMS destacado (não credita em compra com ST,
     CFOP 1403) e crédito de PIS 1,65% / COFINS 7,6% sobre mercadoria + frete + IPI − ICMS (Lei 14.592/2023).
     Fornecedor com CST PIS 04–09 (monofásico/alíquota zero) não gera crédito.
   - **Vendas**: débito do ICMS destacado, DIFAL/FCP e PIS/COFINS sobre a venda sem o ICMS (STF Tema 69).
   - **Devoluções** de venda (crédito, herda o marketplace da venda original) e de compra (estorno do crédito).
   - **CT-e** em que a empresa é tomadora: frete sobre vendas (art. 3º, IX, Lei 10.833) e frete sobre compras
     geram crédito de ICMS e PIS/COFINS.
   - Uso e consumo, ativo imobilizado, bonificações e remessas ficam sem crédito automático, com observação.
2. **DRE mensal**: receita − devoluções − ICMS/DIFAL/PIS/COFINS = receita líquida; − CMV DRE (quantidade vendida ×
   custo cadastrado, ou compras líquidas do mês); − comissões, fretes, embalagens e despesas do mês; IRPJ 15% +
   adicional 10% (acima de R$ 20 mil/mês) e CSLL 9% → lucro líquido; − pagamentos por fora → resultado de caixa.

As opções de base de cálculo (Tema 69, Lei 14.592, IPI, ICMS-ST) ficam em *Importar XML → Configuração*; ao
salvar, todos os XMLs são recalculados. Os valores são uma estimativa gerencial: valide com a contabilidade.

### Testes

```
pip install pytest
python -m pytest tests
```

## Versão sem instalação: KemmaxGestao.html

Arquivo único que abre no Chrome ou Edge (dois cliques), sem Python. Lê os ZIPs de NF-e/CT-e no próprio
navegador e guarda tudo neste computador (IndexedDB): Dashboard, Importações, Produtos e Custos por vigência,
Rentabilidade por Produto, Canais e Tarifas, CT-e e Créditos, Compras Mensais, Apuração ICMS/PIS/COFINS,
DRE Mensal, Despesas, Auditoria/fechamento e Backup (baixe o backup .json com frequência).
Usa as mesmas regras fiscais da versão Python. Teste automatizado: `tests/test_html.py` (Playwright).

## Usar no seu computador (sistema fechado - recomendado para os XMLs)

Os XMLs e o banco de dados ficam só no seu computador; nada vai para o GitHub nem para a internet.

1. Instale o Python 3.11 ou mais novo em https://www.python.org/downloads/
   (no Windows, marque **"Add python.exe to PATH"** na instalação).
2. No GitHub, clique em **Code → Download ZIP** e descompacte numa pasta (ex.: `Documentos\KemmaxControl`).
3. Dê dois cliques em **`iniciar_windows.bat`** (Windows) ou rode `./iniciar_mac_linux.sh` (Mac/Linux).
   Na primeira vez ele instala o que precisa (alguns minutos); depois abre direto no navegador em
   http://localhost:8501. O sistema só aceita acesso deste computador.
4. Menu **Importar XML** → envie os `.zip` (pode enviar todos os meses de uma vez) → **Ler arquivos** →
   confirme o CNPJ da empresa sugerido → **Gravar**.
5. Preencha **Marketplaces**, **Custos dos Produtos** e **Despesas Mensais**.
6. Veja **Resumo Mensal** e **Lucro por Produto**.

Os dados ficam no arquivo `kemmax_control.db`, na pasta do sistema. Em **Importar XML → Backup**
dá para baixar uma cópia, restaurar ou apagar os dados fiscais. Ao atualizar o sistema para uma versão nova,
copie o `kemmax_control.db` para a pasta nova.

### Senha de acesso

Para exigir senha, crie o arquivo `.streamlit/secrets.toml` com:

```
KEMMAX_SENHA = "sua-senha"
```

(ou defina a variável de ambiente `KEMMAX_SENHA`). No Streamlit Cloud, cadastre em *Settings → Secrets*.
**Não publique o sistema na web sem senha**: os XMLs têm dados de clientes e fornecedores. Além disso,
no Streamlit Cloud o banco é apagado quando o app reinicia - use o Backup.

## Como publicar na web

1. Suba estes arquivos para o GitHub.
2. Entre em https://streamlit.io/cloud
3. Clique em New app.
4. Selecione o repositório.
5. Em Main file path, coloque: app.py
6. Clique em Deploy.

## Arquivos necessários

- app.py
- database.py
- calculations.py
- seed.py
- fiscal_xml.py, fiscal_rules.py, fiscal_apuracao.py, fiscal_mensal.py, cadastros.py
- fiscal_pages.py, resultado_pages.py, auth.py
- iniciar_windows.bat, iniciar_mac_linux.sh, .streamlit/config.toml
- requirements.txt
- README.md
