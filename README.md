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
- Fiscal (Lucro Real): leitura de XML de NF-e e CT-e, créditos de ICMS/PIS/COFINS, apuração e DRE

## Módulo Fiscal - Lucro Real

Menus **Fiscal: Importar XML**, **Fiscal: Créditos**, **Fiscal: Apuração** e **Fiscal: DRE Lucro Real**.

1. Em *Fiscal: Importar XML → Configuração*, cadastre o(s) CNPJ(s) da empresa.
2. Envie os XMLs (NF-e de compra e venda, CT-e, eventos de cancelamento) soltos ou em `.zip`
   (pode ter pastas e zips dentro, XML em UTF-8 ou ISO-8859-1). Chaves repetidas são ignoradas e notas
   canceladas saem da apuração. Se o CNPJ ainda não foi cadastrado, o sistema sugere o que mais aparece nos XMLs.
3. O sistema identifica entrada/saída pelo CNPJ, converte o CFOP do fornecedor (5102 → 1102)
   e calcula por item:
   - **Compras para revenda/industrialização**: crédito do ICMS destacado (não credita em compra com ST,
     CFOP 1403) e crédito de PIS 1,65% / COFINS 7,6% sobre mercadoria + frete + IPI − ICMS (Lei 14.592/2023).
     Fornecedor com CST PIS 04–09 (monofásico/alíquota zero) não gera crédito.
   - **Vendas**: débito do ICMS destacado, DIFAL/FCP e PIS/COFINS sobre a venda sem o ICMS (STF Tema 69).
   - **Devoluções** de venda (crédito) e de compra (estorno do crédito).
   - **CT-e** em que a empresa é tomadora: frete sobre vendas (art. 3º, IX, Lei 10.833) e frete sobre compras
     (custo de aquisição) geram crédito de ICMS e PIS/COFINS.
   - Uso e consumo, ativo imobilizado, bonificações e remessas ficam sem crédito automático, com observação.
4. Em *Fiscal: Créditos → Créditos extras*, lance créditos que não vêm em XML (armazenagem do FULL, energia,
   aluguel, depreciação, CIAP).
5. *Fiscal: Apuração* mostra débitos − créditos − saldo credor anterior de ICMS, PIS e COFINS e exporta para Excel.
6. *Fiscal: DRE Lucro Real* monta a DRE com receita, deduções, CMV (compras líquidas de créditos ± estoques),
   despesas, resultado financeiro, ajustes do LALUR, CSLL 9% e IRPJ 15% + adicional 10%.

As opções de base de cálculo (Tema 69, Lei 14.592, IPI, ICMS-ST) ficam na configuração; ao salvar,
todos os XMLs são recalculados. Os valores são uma estimativa gerencial: valide com a contabilidade.

### Testes

```
pip install pytest
python -m pytest tests
```

## Usar no seu computador (sistema fechado - recomendado para os XMLs)

Os XMLs e o banco de dados ficam só no seu computador; nada vai para o GitHub nem para a internet.

1. Instale o Python 3.11 ou mais novo em https://www.python.org/downloads/
   (no Windows, marque **"Add python.exe to PATH"** na instalação).
2. No GitHub, clique em **Code → Download ZIP** e descompacte numa pasta (ex.: `Documentos\KemmaxControl`).
3. Dê dois cliques em **`iniciar_windows.bat`** (Windows) ou rode `./iniciar_mac_linux.sh` (Mac/Linux).
   Na primeira vez ele instala o que precisa (alguns minutos); depois abre direto no navegador em
   http://localhost:8501. O sistema só aceita acesso deste computador.
4. Menu **Fiscal: Importar XML** → envie o `.zip` baixado do Google Drive → **Ler arquivos** →
   confirme o CNPJ da empresa sugerido → **Gravar**.
5. Veja **Fiscal: Créditos**, **Fiscal: Apuração** e **Fiscal: DRE Lucro Real**.

Os dados ficam no arquivo `kemmax_control.db`, na pasta do sistema. Em **Fiscal: Importar XML → Backup**
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
- fiscal_xml.py, fiscal_rules.py, fiscal_apuracao.py, fiscal_pages.py, auth.py
- iniciar_windows.bat, iniciar_mac_linux.sh, .streamlit/config.toml
- requirements.txt
- README.md
