from streamlit.testing.v1 import AppTest


def _app():
    from auth import exigir_login
    import streamlit as st
    exigir_login()
    st.write("conteudo protegido")


def test_sem_senha_abre_direto(monkeypatch):
    monkeypatch.delenv("KEMMAX_SENHA", raising=False)
    at = AppTest.from_function(_app).run()
    assert at.markdown[-1].value == "conteudo protegido"


def test_com_senha_exige_login(monkeypatch):
    monkeypatch.setenv("KEMMAX_SENHA", "segredo")
    at = AppTest.from_function(_app).run()
    assert not any(m.value == "conteudo protegido" for m in at.markdown)

    at.text_input[0].input("errada")
    at.button[0].click().run()
    assert at.error[0].value == "Senha incorreta."

    at.text_input[0].input("segredo")
    at.button[0].click().run()
    assert at.markdown[-1].value == "conteudo protegido"
