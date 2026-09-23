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
2. Envie os XMLs (NF-e de compra e venda, CT-e) soltos ou em `.zip`. Chaves repetidas são ignoradas.
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
- fiscal_xml.py, fiscal_rules.py, fiscal_apuracao.py, fiscal_pages.py
- requirements.txt
- README.md
