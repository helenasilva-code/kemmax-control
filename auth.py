"""Senha de acesso ao sistema.

A senha vem da variável de ambiente KEMMAX_SENHA ou de st.secrets["KEMMAX_SENHA"]
(arquivo .streamlit/secrets.toml, ou Secrets no Streamlit Cloud). Sem senha
configurada o app abre direto - adequado só para uso no próprio computador.
"""
import hmac
import os

import streamlit as st


def _senha_configurada():
    senha = os.environ.get("KEMMAX_SENHA", "")
    if senha:
        return senha
    try:
        return st.secrets.get("KEMMAX_SENHA", "")
    except Exception:
        return ""


def exigir_login():
    senha = _senha_configurada()
    if not senha or st.session_state.get("autenticado"):
        return
    st.markdown("### Kemmax Control")
    with st.form("login"):
        digitada = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar")
    if entrar:
        if hmac.compare_digest(digitada.encode(), senha.encode()):
            st.session_state["autenticado"] = True
            st.rerun()
        st.error("Senha incorreta.")
    st.stop()


def botao_sair():
    if _senha_configurada() and st.sidebar.button("Sair"):
        st.session_state.pop("autenticado", None)
        st.rerun()
