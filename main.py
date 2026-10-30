import flet as ft
import sqlite3
import json
import os
import requests
import threading
import unicodedata
from urllib.parse import quote_plus
from datetime import datetime

CONFIG_FILE = "config.json"
DB_FILE = "filmes.db"

STREAMINGS_PADRAO = [
    "Netflix",
    "Max",
    "Amazon Prime Video",
    "Disney Plus",
    "Apple TV Plus",
    "Globoplay",
    "Paramount Plus",
    "Telecine"
]

http_session = requests.Session()

def carregar_config():
    cfg = {"omdb_key": "", "tmdb_key": ""}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    if not cfg.get("tmdb_key"):
        cfg["tmdb_key"] = os.environ.get("TMDB_KEY", "")
    if not cfg.get("omdb_key"):
        cfg["omdb_key"] = os.environ.get("OMDB_KEY", "")
    return cfg

def init_db():
    try:
        with sqlite3.connect(DB_FILE, timeout=10) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS filmes (
                    id TEXT PRIMARY KEY,
                    titulo TEXT,
                    ano TEXT,
                    diretor TEXT,
                    elenco TEXT,
                    sinopse TEXT,
                    imdb TEXT,
                    rotten TEXT,
                    streaming TEXT,
                    poster_url TEXT,
                    categoria TEXT,
                    nota_usuario TEXT,
                    trailer_url TEXT
                )
            """)
            conn.commit()
    except Exception:
        pass

def obter_estilo_nota(nota_str):
    try:
        val = int(float(nota_str))
    except Exception:
        val = 0

    if 1 <= val <= 5:
        return "#dc2626", "white", None
    elif 6 <= val <= 8:
        return "#2563eb", "white", None
    elif val == 9:
        return "#16a34a", "white", None
    elif val >= 10:
        return "#000000", "#f8fafc", ft.Border(
            ft.BorderSide(1, "#475569"),
            ft.BorderSide(1, "#475569"),
            ft.BorderSide(1, "#475569"),
            ft.BorderSide(1, "#475569")
        )
    return "#1e1b4b", "#a78bfa", None

def main(page: ft.Page):
    page.title = "Movie Insert"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0b0c0f"
    page.padding = ft.Padding(12, 10, 12, 0)
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.scroll = None

    init_db()
    item_ativo = {"data": None}
    timer_busca = {"timer": None}
    filme_avaliando = {"id": None, "nota": "10"}
    filme_para_remover = {"id": None, "titulo": ""}

    paginacao = {
        "pagina_atual": 0,
        "carregando": False,
        "fim": False
    }

    progresso = ft.ProgressBar(color="#3b82f6", bgcolor="transparent", visible=False)

    def fechar_busca_se_aberta(e=None):
        if container_sugestoes.visible:
            container_sugestoes.visible = False
            page.update()

    def abrir_dialogo(modal):
        modal.open = True
        if modal not in page.overlay:
            page.overlay.append(modal)
        page.update()

    
