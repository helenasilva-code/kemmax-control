import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Banco dos testes fora da pasta do projeto
os.environ["KEMMAX_DB"] = os.path.join(tempfile.mkdtemp(), "teste.db")
