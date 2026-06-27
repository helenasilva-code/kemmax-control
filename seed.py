from database import SessionLocal, Produto, Fornecedor
from datetime import date

def seed_data():
    db = SessionLocal()

    fornecedores = [
        ("Excentrix", "Máquinas", "Encadernadoras e equipamentos"),
        ("MBSET", "Fornecedor", "Fornecedor estratégico"),
        ("Lassane", "Fornecedor", "Espirais, canteadeiras e suprimentos"),
        ("Spiralteck", "Fornecedor", "Wire-O"),
        ("Maroger", "Fornecedor", "Máquinas"),
        ("Prolam", "Fornecedor", "Polaseal"),
        ("JOJO", "Fornecedor", "Comparação de Wire-O"),
    ]

    for nome, categoria, obs in fornecedores:
        if not db.query(Fornecedor).filter_by(nome=nome).first():
            db.add(Fornecedor(nome=nome, categoria=categoria, observacao=obs))

    produtos = [
        ("POLA405", "Polaseal A4 125 micras", "Polaseal", "Prolam", 31.59, 31.95, 41.20, 56.50, 52.90, 1000, 0, 49, 20, 15),
        ("EXA4", "Encadernadora A4 Excentrix", "Máquinas", "Excentrix", 329.07, 329.07, 397.40, 498.00, 498.00, 0, 0, 0.3, 20, 15),
        ("EXCONJU", "Encadernadora 2x1 Excentrix", "Máquinas", "Excentrix", 919.91, 919.91, 1111.50, 1538.00, 1538.00, 0, 8, 0.2, 20, 15),
        ("KITCAPA", "Kit Capas A4", "Capas", "Fornecedor Capas", 16.77, 16.77, 22.31, 33.49, 33.49, 1000, 0, 20, 15, 15),
        ("CX36WIREOBRA58A5", "Wire-O A5 5/8 Branco 36 un", "Wire-O A5", "Spiralteck", 24.95, 25.31, 30.83, 0, 74.90, 0, 0, 5, 20, 15),
        ("CX50WIREOBRA58A4", "Wire-O A4 5/8 Branco 50 un", "Wire-O A4", "Spiralteck", 0, 0, 45.50, 0, 74.90, 0, 0, 3, 20, 15),
        ("CX50WIREOBRA34A4", "Wire-O A4 3/4 Branco 50 un", "Wire-O A4", "Spiralteck", 0, 0, 54.26, 0, 89.90, 0, 0, 3, 20, 15),
        ("CX50WIREOBRA78A4", "Wire-O A4 7/8 Branco 50 un", "Wire-O A4", "Spiralteck", 0, 0, 67.62, 0, 109.90, 0, 0, 2, 20, 15),
        ("CX50WIREOBRA1A4", "Wire-O A4 1 polegada Branco 50 un", "Wire-O A4", "Spiralteck", 0, 0, 81.05, 0, 129.90, 0, 0, 1, 20, 15),
        ("PCT100ESP14MMPRE", "Espiral Preto 14mm c/100", "Espiral ST", "Lassane", 14.60, 14.60, 15.11, 0, 0, 0, 0, 0, 15, 10),
    ]

    for sku, nome, categoria, fornecedor, cmv, cmf, caixa, ml, shopee, emp, full, venda_dia, lead, seg in produtos:
        if not db.query(Produto).filter_by(sku=sku).first():
            db.add(Produto(
                sku=sku, nome=nome, categoria=categoria, fornecedor_padrao=fornecedor,
                cmv_normal=cmv, cmf_kemmax=cmf, custo_caixa=caixa,
                preco_ml=ml, preco_shopee=shopee,
                estoque_empresa=emp, estoque_full=full, venda_media_dia=venda_dia,
                lead_time_dias=lead, estoque_seguranca_dias=seg
            ))

    db.commit()
    db.close()
