import flet as ft
import sqlite3
import json
import os
import requests
import threading
import unicodedata
import hashlib
import time
from urllib.parse import quote_plus
from datetime import datetime

CONFIG_FILE = "config.json"
DB_FILE = "filmes.db"

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
DIR_ASSETS = os.path.join(DIR_BASE, "assets")

COR_PETROLEO = "#03434d"
COR_PETROLEO_HOVER = "#055663"
COR_CHUMBO = "#48585e"
COR_TEXTO_CLARO = "#e5ecf0"
COR_VERMELHO_PLAY = "#9e0f0f"
COR_FUNDO = "#070b0e"
COR_CARD = "#0d1419"
COR_BORDA = "#17232b"

def criar_borda(espessura, cor):
    bs = ft.BorderSide(espessura, cor)
    return ft.Border(top=bs, right=bs, bottom=bs, left=bs)

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

# -------------------------------------------------------------
# SEGURANÇA E BASE DE DADOS
# -------------------------------------------------------------
def gerar_hash_senha(senha: str) -> str:
    salt = os.urandom(16).hex()
    hash_obj = hashlib.pbkdf2_hmac(
        'sha256', 
        senha.encode('utf-8'), 
        bytes.fromhex(salt), 
        100000
    )
    return f"{salt}:{hash_obj.hex()}"

def verificar_senha(senha_fornecida: str, hash_armazenado: str) -> bool:
    try:
        salt, hash_real = hash_armazenado.split(":")
        hash_teste = hashlib.pbkdf2_hmac(
            'sha256', 
            senha_fornecida.encode('utf-8'), 
            bytes.fromhex(salt), 
            100000
        )
        return hash_teste.hex() == hash_real
    except Exception:
        return False

def init_db():
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=20)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE COLLATE NOCASE,
                password_hash TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS filmes (
                id TEXT,
                titulo TEXT,
                ano TEXT,
                diretor TEXT,
                elenco TEXT,
                sinopse TEXT,
                imdb TEXT,
                rotten TEXT,
                metascore TEXT,
                streaming TEXT,
                poster_url TEXT,
                categoria TEXT,
                nota_usuario TEXT,
                trailer_url TEXT,
                generos TEXT,
                usuario_id INTEGER,
                tipo TEXT DEFAULT 'movie',
                PRIMARY KEY (id, usuario_id)
            )
        """)
        try:
            c.execute("ALTER TABLE filmes ADD COLUMN metascore TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE filmes ADD COLUMN generos TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE filmes ADD COLUMN usuario_id INTEGER DEFAULT 1")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE filmes ADD COLUMN tipo TEXT DEFAULT 'movie'")
        except Exception:
            pass
        conn.commit()
    except Exception as e:
        print(f"Erro init_db: {e}")
    finally:
        if conn:
            conn.close()

def normalizar_texto(texto):
    if not texto:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).lower().strip()

def obter_estilo_nota(nota_str):
    try:
        val = int(float(nota_str))
    except Exception:
        val = 0

    if 1 <= val <= 5:
        return "#dc2626", "white", None
    elif 6 <= val <= 8:
        return COR_PETROLEO, "white", None
    elif val == 9:
        return "#16a34a", "white", None
    elif val >= 10:
        return "#000000", "#f8fafc", criar_borda(1, "#475569")
    return "#1e1b4b", "#a78bfa", None

def main(page: ft.Page):
    page.title = "Movie Insert"
    page.favicon = "favicon.png"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = COR_FUNDO
    page.padding = 0
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.scroll = None

    init_db()

    sessao_usuario = {
        "id": None,
        "username": ""
    }

    item_ativo = {"data": None}
    timer_busca = {"timer": None}
    filme_avaliando = {"id": None, "nota": "10"}
    filme_para_remover = {"id": None, "titulo": ""}
    
    estado_biblioteca = {
        "aba": "Para Assistir",
        "modo": "streaming",
        "filtro_tipo": "todos"  # "todos", "movie", "tv"
    }

    paginacao = {
        "pagina_atual": 1,
        "carregando": False,
        "fim": False,
        "filtro_home": "todos",  # "todos", "movie", "tv"
        "ids_carregados": set()
    }

    progresso = ft.ProgressBar(color=COR_PETROLEO, bgcolor="transparent", visible=False)

    def abrir_dialogo(modal):
        modal.open = True
        if modal not in page.overlay:
            page.overlay.append(modal)
        page.update()

    def fechar_dialogo(modal):
        modal.open = False
        page.update()

    txt_confirmacao_msg = ft.Text("", size=14, color="#cbd5e1")

    def executar_remocao(e):
        fid = filme_para_remover["id"]
        uid = sessao_usuario["id"]
        if fid and uid:
            conn = None
            try:
                conn = sqlite3.connect(DB_FILE, timeout=15)
                c = conn.cursor()
                c.execute("DELETE FROM filmes WHERE id = ? AND usuario_id = ?", (fid, uid))
                conn.commit()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()
            fechar_dialogo(modal_confirmacao)
            carregar_biblioteca()

    modal_confirmacao = ft.AlertDialog(
        modal=False,
        title=ft.Text("Confirmar Exclusão", size=16, weight="bold", color="#ef4444"),
        content=txt_confirmacao_msg,
        actions=[
            ft.Button(content=ft.Text("Cancelar", color="#94a3b8"), on_click=lambda e: fechar_dialogo(modal_confirmacao)),
            ft.Button(content=ft.Text("Sim, remover", color="white"), bgcolor=COR_VERMELHO_PLAY, on_click=executar_remocao)
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )

    def pedir_confirmacao_remocao(fid, titulo):
        filme_para_remover["id"] = fid
        filme_para_remover["titulo"] = titulo
        txt_confirmacao_msg.value = f"Deseja remover '{titulo}' da lista de Assistidos?"
        abrir_dialogo(modal_confirmacao)

    # -------------------------------------------------------------
    # SELETOR DE AVALIAÇÃO
    # -------------------------------------------------------------
    botoes_notas = []
    linha_notas_1_5 = ft.Row(spacing=6, alignment=ft.MainAxisAlignment.CENTER)
    linha_notas_6_10 = ft.Row(spacing=6, alignment=ft.MainAxisAlignment.CENTER)

    def selecionar_nota_valor(valor):
        filme_avaliando["nota"] = str(valor)
        for btn in botoes_notas:
            is_ativo = (btn.data == str(valor))
            btn.bgcolor = COR_PETROLEO if is_ativo else "#1f2937"
            btn.content.color = "white" if is_ativo else "#94a3b8"
        page.update()

    for n in range(1, 11):
        s_val = str(n)
        is_padrao = (n == 10)
        btn_n = ft.Container(
            content=ft.Text(s_val, size=13, weight="bold", color="white" if is_padrao else "#94a3b8", text_align=ft.TextAlign.CENTER),
            alignment=ft.Alignment(0, 0),
            width=40,
            height=40,
            shape=ft.BoxShape.CIRCLE,
            bgcolor=COR_PETROLEO if is_padrao else "#1f2937",
            ink=True,
            data=s_val,
            on_click=lambda e, v=s_val: selecionar_nota_valor(v)
        )
        botoes_notas.append(btn_n)
        if n <= 5:
            linha_notas_1_5.controls.append(btn_n)
        else:
            linha_notas_6_10.controls.append(btn_n)

    def confirmar_avaliacao(e):
        fid = filme_avaliando["id"]
        nota = filme_avaliando.get("nota", "10")
        uid = sessao_usuario["id"]
        if fid and uid:
            conn = None
            try:
                conn = sqlite3.connect(DB_FILE, timeout=15)
                c = conn.cursor()
                c.execute("UPDATE filmes SET categoria = 'Assistidos', nota_usuario = ? WHERE id = ? AND usuario_id = ?", (nota, fid, uid))
                conn.commit()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()
            fechar_dialogo(modal_avaliacao)
            carregar_biblioteca()

    modal_avaliacao = ft.AlertDialog(
        modal=False,
        title=ft.Text("Qual nota você dá ao título?", size=16, weight="bold"),
        content=ft.Column([
            ft.Text("Selecione a nota:", size=13, color="#94a3b8"),
            linha_notas_1_5,
            linha_notas_6_10,
        ], tight=True, spacing=10),
        actions=[
            ft.Button(content=ft.Text("Cancelar", color="#94a3b8"), on_click=lambda e: fechar_dialogo(modal_avaliacao)),
            ft.Button(content=ft.Text("Confirmar", color="white"), bgcolor=COR_PETROLEO, on_click=confirmar_avaliacao)
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )

    def abrir_modal_avaliacao(fid, nota_atual=None):
        filme_avaliando["id"] = fid
        try:
            nota_inicial = str(int(float(nota_atual))) if (nota_atual and nota_atual != "N/A") else "10"
        except Exception:
            nota_inicial = "10"
        selecionar_nota_valor(nota_inicial)
        abrir_dialogo(modal_avaliacao)

    # -------------------------------------------------------------
    # JANELA DE DETALHES COM SUPORTE A SÉRIE E METASCORE
    # -------------------------------------------------------------
    dt_img = ft.Image(
        src="https://via.placeholder.com/130x195?text=Sem+Poster",
        width=135,
        height=200,
        border_radius=8,
        fit="cover"
    )
    dt_titulo = ft.Text("", size=17, weight="bold", color="white")
    dt_titulo_original = ft.Text("", size=12, italic=True, color="#94a3b8", visible=False)
    dt_meta = ft.Text("", size=11, color="#94a3b8")
    dt_stream = ft.Text("", size=12, color="#10b981", weight="bold")
    dt_sinopse = ft.Text("", size=12, color="#cbd5e1")

    txt_stremio = ft.Text("🔍 Verificando lançamento...", size=11, weight="bold", color="#93c5fd")
    dt_stremio_status = ft.Container(
        content=txt_stremio,
        bgcolor="#1e293b",
        padding=ft.Padding(6, 4, 6, 4),
        border_radius=6
    )

    dt_imdb = ft.Container(content=ft.Text("⭐ --", color="black", size=11, weight="bold"), bgcolor="#f59e0b", padding=ft.Padding(5, 2, 5, 2), border_radius=5)
    dt_rt = ft.Container(content=ft.Text("🍅 --", color="white", size=11, weight="bold"), bgcolor=COR_VERMELHO_PLAY, padding=ft.Padding(5, 2, 5, 2), border_radius=5)
    dt_metascore = ft.Container(content=ft.Text("Ⓜ --", color="white", size=11, weight="bold"), bgcolor="#334155", padding=ft.Padding(5, 2, 5, 2), border_radius=5)
    dt_user = ft.Container(content=ft.Text("★ --", color="white", size=11, weight="bold"), bgcolor=COR_PETROLEO, padding=ft.Padding(5, 2, 5, 2), border_radius=5)

    btn_trailer = ft.Button(
        content=ft.Text("▶ Trailer", color="white", size=12, weight="bold"),
        bgcolor=COR_VERMELHO_PLAY,
        url="https://youtube.com"
    )
    btn_salvar = ft.Button(content=ft.Text("+ Adicionar à Lista", color="white", size=12), bgcolor=COR_PETROLEO, disabled=True)
    btn_ir_lista = ft.Button(content=ft.Text("📁 Ir para Minha Lista", color="white", size=12), bgcolor="#10b981", visible=False)

    def fechar_detalhes(e=None):
        fechar_dialogo(modal_detalhes)

    def acao_ir_para_lista(e):
        fechar_dialogo(modal_detalhes)
        alternar_tela(1)

    btn_ir_lista.on_click = acao_ir_para_lista

    btn_fechar = ft.Button(
        content=ft.Text("✕ Fechar", color="white", weight="bold", size=12),
        bgcolor=COR_PETROLEO,
        on_click=fechar_detalhes
    )

    coluna_info_topo = ft.Column([
        dt_titulo,
        dt_titulo_original,
        dt_meta,
        ft.Row([dt_imdb, dt_rt, dt_metascore, dt_user], spacing=6, wrap=True),
        dt_stremio_status,
        dt_stream,
    ], spacing=3, width=310)

    conteudo_modal = ft.Container(
        width=480,
        bgcolor=COR_CARD,
        padding=14,
        border_radius=12,
        border=criar_borda(1.5, COR_PETROLEO),
        content=ft.Column([
            ft.Row([btn_fechar], alignment=ft.MainAxisAlignment.END),
            ft.Row(
                [dt_img, coluna_info_topo],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.START,
                wrap=True,
                spacing=10
            ),
            ft.Row([btn_trailer, btn_salvar], spacing=8, wrap=True),
            btn_ir_lista,
            ft.Text("Sinopse", size=13, weight="bold", color="#94a3b8"),
            dt_sinopse,
        ], spacing=8, scroll=ft.ScrollMode.AUTO, tight=True)
    )

    modal_detalhes = ft.AlertDialog(
        content=conteudo_modal,
        modal=False,
        bgcolor="transparent",
        content_padding=0
    )

    def salvar_filme_ativo(e):
        it = item_ativo["data"]
        uid = sessao_usuario["id"]
        if not it or not uid:
            return

        tipo_salvar = it.get("tipo", "movie")
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE, timeout=15)
            c = conn.cursor()
            c.execute("SELECT categoria FROM filmes WHERE id = ? AND usuario_id = ?", (it["id"], uid))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO filmes (id, titulo, ano, diretor, elenco, sinopse, imdb, rotten, metascore, streaming, poster_url, categoria, nota_usuario, trailer_url, generos, usuario_id, tipo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Para Assistir', ?, ?, ?, ?, ?)
                """, (
                    it["id"], it["titulo"], it["ano"], it["diretor"], it["elenco"],
                    it["sinopse"], it["imdb"], it["rotten"], it.get("metascore", "N/A"),
                    it["streaming"], it["poster_url"], it.get("nota_usuario"),
                    it.get("trailer_url"), it.get("generos", ""), uid, tipo_salvar
                ))
                conn.commit()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        it["categoria_existente"] = "Para Assistir"
        btn_salvar.content = ft.Text("✓ Na sua Lista", color="white", size=12)
        btn_salvar.bgcolor = "#334155"
        btn_salvar.disabled = True
        btn_ir_lista.visible = True
        page.update()

    btn_salvar.on_click = salvar_filme_ativo

    def abrir_detalhes(mid, mtype, titulo_prev, ano_prev, poster_prev):
        if container_sugestoes.visible:
            container_sugestoes.visible = False

        mtype_seguro = "tv" if mtype in ["tv", "series"] else "movie"

        dt_img.src = poster_prev if poster_prev else "https://via.placeholder.com/130x195?text=Sem+Poster"
        dt_titulo.value = f"{titulo_prev} ({ano_prev})"
        dt_titulo_original.visible = False
        dt_meta.value = "Obtendo dados..."
        dt_stream.value = "Consultando disponibilidade..."
        dt_sinopse.value = "Carregando sinopse..."
        txt_stremio.value = "🔍 Checando qualidade..."
        txt_stremio.color = "#93c5fd"
        dt_stremio_status.bgcolor = "#1e293b"
        dt_imdb.content.value = "⭐ .."
        dt_rt.content.value = "🍅 .."
        dt_metascore.content.value = "Ⓜ .."
        dt_metascore.bgcolor = "#334155"
        dt_metascore.content.color = "white"
        dt_user.content.value = "★ .."
        btn_salvar.disabled = True
        btn_ir_lista.visible = False

        fallback_trailer = f"https://www.youtube.com/results?search_query={quote_plus('trailer oficial ' + titulo_prev + ' ' + ano_prev)}"
        btn_trailer.url = fallback_trailer

        abrir_dialogo(modal_detalhes)
        progresso.visible = True
        page.update()

        c = carregar_config()
        tmdb_key = c.get("tmdb_key", "").strip()
        omdb_key = c.get("omdb_key", "").strip()
        uid = sessao_usuario["id"]

        def _fetch():
            try:
                url_tmdb = f"https://api.themoviedb.org/3/{mtype_seguro}/{mid}?api_key={tmdb_key}&language=pt-BR&append_to_response=credits,watch/providers,external_ids,videos,release_dates"
                res = requests.get(url_tmdb, timeout=4.5).json()

                if mtype_seguro == "movie":
                    diretor = "N/A"
                    for cr in res.get("credits", {}).get("crew", []):
                        if cr.get("job") == "Director":
                            diretor = cr.get("name")
                            break
                    info_criacao = f"Direção: {diretor}"
                else:
                    criadores = [cr.get("name") for cr in res.get("created_by", [])]
                    temporadas = res.get("number_of_seasons", 1)
                    info_criacao = f"Criador(es): {', '.join(criadores) if criadores else 'Não informado'} • {temporadas} Temporada(s)"
                    diretor = info_criacao

                elenco_list = [a.get("name") for a in res.get("credits", {}).get("cast", [])[:4]]
                elenco = ", ".join(elenco_list) if elenco_list else "Não informado"

                titulo = res.get("title") or res.get("name") or titulo_prev
                titulo_orig = res.get("original_title") or res.get("original_name") or ""
                ano = str((res.get("release_date") or res.get("first_air_date")) or "")[:4] or ano_prev
                sinopse = res.get("overview") or "Sinopse não disponível em português."

                lista_generos = [g.get("name") for g in res.get("genres", []) if g.get("name")]
                generos_txt = ", ".join(lista_generos) if lista_generos else "Outros"

                br_providers = res.get("watch/providers", {}).get("results", {}).get("BR", {}).get("flatrate", [])
                stream_nomes = [p.get("provider_name") for p in br_providers]

                poster_path = res.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w300{poster_path}" if poster_path else poster_prev

                imdb_id = res.get("imdb_id") or res.get("external_ids", {}).get("imdb_id")
                imdb_nota, rt_nota, meta_nota = "N/A", "N/A", "N/A"

                if omdb_key and imdb_id:
                    try:
                        res_omdb = requests.get(f"https://www.omdbapi.com/?i={imdb_id}&apikey={omdb_key}", timeout=2.5).json()
                        if res_omdb.get("Response") == "True":
                            imdb_nota = res_omdb.get("imdbRating", "N/A")
                            m_raw = res_omdb.get("Metascore", "N/A")
                            if m_raw and m_raw != "N/A":
                                meta_nota = m_raw

                            for val in res_omdb.get("Ratings", []):
                                if val.get("Source") == "Rotten Tomatoes":
                                    rt_nota = val.get("Value")
                                    break
                    except Excepti
