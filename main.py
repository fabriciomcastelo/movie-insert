import flet as ft
import sqlite3
import json
import os
import requests
import threading
import unicodedata
import time
from urllib.parse import quote_plus, urlparse
from datetime import datetime

try:
    import psycopg2
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

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
COR_ATIVO_BORDA = "#38bdf8"

CORES_AVATAR = [
    "#0284c7", "#0d9488", "#16a34a", "#ca8a04", 
    "#dc2626", "#9333ea", "#c026d3", "#4f46e5"
]

MAPA_LOGOS_STREAMING = {
    "CasteloFlix": "castelo.png",
    "Netflix": "netflix.png",
    "Max": "max.png",
    "Amazon Prime Video": "prime.png",
    "Disney Plus": "Disney.png",
    "Apple TV Plus": "apple.png",
    "Globoplay": "globoplay.png",
    "Paramount Plus": "paramount.png",
    "Telecine": "telecine.png",
    "Stremio": "stremio.png"
}

MAPA_GENEROS_TMDB = {
    "acao": 28, "action": 28,
    "aventura": 12, "adventure": 12,
    "animacao": 16, "animation": 16,
    "comedia": 35, "comedy": 35,
    "crime": 80,
    "documentario": 99, "documentary": 99,
    "drama": 18,
    "familia": 10751, "family": 10751,
    "fantasia": 14, "fantasy": 14,
    "historia": 36, "history": 36,
    "terror": 27, "horror": 27,
    "musica": 10402, "musical": 10402,
    "misterio": 9648, "mystery": 9648,
    "romance": 10749,
    "ficcao cientifica": 878, "sci-fi": 878, "scifi": 878,
    "suspense": 53, "thriller": 53,
    "guerra": 10752, "war": 10752,
    "faroeste": 37, "western": 37
}

MAPA_PAISES_TMDB = {
    "brasil": "pt",
    "brasileiro": "pt",
    "brasileiros": "pt",
    "brasileira": "pt",
    "brasileiras": "pt",
    "nacional": "pt",
    
    "italia": "it",
    "italiano": "it",
    "italianos": "it",
    "italiana": "it",
    "italianas": "it",
    
    "coreia": "ko",
    "coreano": "ko",
    "coreanos": "ko",
    "coreana": "ko",
    "kdrama": "ko",
    "k-drama": "ko",
    
    "japao": "ja",
    "japones": "ja",
    "japoneses": "ja",
    "japonesa": "ja",
    "anime": "ja",
    
    "franca": "fr",
    "frances": "fr",
    "franceses": "fr",
    "francesa": "fr",
    
    "espanha": "es",
    "espanhol": "es",
    "espanhois": "es",
    "espanhola": "es",
    
    "alemanha": "de",
    "alemao": "de",
    "alemaes": "de",
    "alema": "de",
    
    "argentina": "es",
    "argentino": "es",
    "argentinos": "es",
    
    "mexico": "es",
    "mexicano": "es",
    "mexicanos": "es",
    
    "inglaterra": "en",
    "britanico": "en",
    "britanicos": "en",
    "reino unido": "en"
}

MAPA_KEYWORDS_CONHECIDAS = {
    "segunda guerra": "1956|849|428|1957|1958",
    "segunda guerra mundial": "1956|849|428|1957|1958",
    "ww2": "1956|849",
    "wwii": "1956|849",
    "primeira guerra": "1957|2149",
    "primeira guerra mundial": "1957|2149",
    "holocausto": "238|1956",
    "nazismo": "238|1956|3618",
    "guerra fria": "1954|2143",
    "vietna": "1955|1959",
    "guerra do vietna": "1955|1959",
    "zumbi": "12377|186565",
    "zumbis": "12377|186565",
    "viagem no tempo": "4379",
    "espaco": "9882|3801",
    "extraterrestre": "9951|14909",
    "alien": "9951",
    "mafia": "10051|10391",
    "inteligencia artificial": "310",
    "ia": "310",
    "cyberpunk": "12190",
    "apocalipse": "4458",
    "pos-apocaliptico": "4458|2853",
    "serial killer": "10714",
    "vampiro": "3133",
    "vampiros": "3133",
    "espionagem": "470|10085",
    "super heroi": "9715",
    "super-heroi": "9715"
}

def criar_borda(espessura, cor):
    bs = ft.BorderSide(espessura, cor)
    return ft.Border(top=bs, right=bs, bottom=bs, left=bs)

def obter_conexao():
    database_url = os.environ.get("DATABASE_URL")
    if database_url and HAS_POSTGRES:
        url = urlparse(database_url)
        conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port,
            connect_timeout=5
        )
        return conn
    else:
        return sqlite3.connect(DB_FILE, timeout=10)

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

def traduzir_para_ingles(texto):
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=pt&tl=en&dt=t&q={quote_plus(texto)}"
        resp = requests.get(url, timeout=2.0)
        if resp.status_code == 200:
            return resp.json()[0][0][0].strip().lower()
    except Exception:
        pass
    return texto.strip().lower()

def init_db():
    conn = None
    try:
        conn = obter_conexao()
        c = conn.cursor()
        is_pg = bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES)
        
        if not is_pg:
            c.execute("PRAGMA journal_mode=WAL;")

        if is_pg:
            c.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE,
                    cor_avatar TEXT DEFAULT '#03434d',
                    pin TEXT DEFAULT ''
                )
            """)
            try:
                c.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS pin TEXT DEFAULT ''")
            except Exception:
                pass
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
        else:
            c.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE COLLATE NOCASE,
                    cor_avatar TEXT DEFAULT '#03434d',
                    pin TEXT DEFAULT ''
                )
            """)
            try:
                c.execute("ALTER TABLE usuarios ADD COLUMN pin TEXT DEFAULT ''")
            except Exception:
                pass
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

    page.splash = ft.Container(
        content=ft.Column(
            controls=[
                ft.Image(src="logo.png", width=180, fit="contain"),
                ft.Container(height=12),
                ft.ProgressRing(width=28, height=28, stroke_width=2.5, color=COR_ATIVO_BORDA)
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=4
        ),
        alignment=ft.Alignment(0, 0),
        bgcolor=COR_FUNDO
    )
    page.update()

    init_db()

    sessao_usuario = {"id": None, "username": "", "cor": COR_PETROLEO}
    ids_salvos_usuario = set()
    titulos_salvos_usuario = set()
    botoes_add_home = {}

    timer_busca = {"timer": None}
    versao_busca_atual = {"epoch": 0}
    primeira_acao_sugestao = {"callback": None}
    tela_ativa_atual = {"indice": 0}

    contexto_busca = {
        "tipo": None,
        "id": None,
        "nome": "",
        "itens_cache": [],
        "offset": 0
    }

    def eh_mobile():
        largura = page.width if page.width else 1000
        return largura < 720

    def abrir_dialogo(modal):
        modal.open = True
        if modal not in page.overlay:
            page.overlay.append(modal)
        page.update()

    def fechar_dialogo(modal):
        modal.open = False
        page.update()

    def recarregar_ids_salvos():
        ids_salvos_usuario.clear()
        titulos_salvos_usuario.clear()
        uid = sessao_usuario["id"]
        if uid:
            conn = None
            try:
                conn = obter_conexao()
                c = conn.cursor()
                query = "SELECT id, titulo FROM filmes WHERE usuario_id = %s" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "SELECT id, titulo FROM filmes WHERE usuario_id = ?"
                c.execute(query, (uid,))
                for row in c.fetchall():
                    ids_salvos_usuario.add(str(row[0]))
                    if row[1]:
                        titulos_salvos_usuario.add(normalizar_texto(row[1]))
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()

    def marcar_botao_home_como_salvo(chave_id):
        if chave_id in botoes_add_home and botoes_add_home[chave_id]:
            btn = botoes_add_home[chave_id]
            btn.icon = ft.Icons.CHECK
            btn.icon_color = "#10b981"
            btn.bgcolor = "#064e3b"
            btn.disabled = True
            btn.tooltip = "Já está na sua biblioteca"
            btn.update()

    estado_biblioteca = {
        "aba": "Para Assistir",
        "modo": "alfabetico",
        "filtro_tipo": "todos"
    }

    paginacao = {
        "pagina_atual": 1,
        "carregando": False,
        "fim": False,
        "filtro_home": "todos",
        "ids_carregados": set(),
        "modo_busca_ativo": False
    }

    progresso = ft.ProgressBar(color=COR_PETROLEO, bgcolor="transparent", visible=False)
    grade_populares = ft.Row(wrap=True, spacing=10, run_spacing=12, alignment=ft.MainAxisAlignment.CENTER)
    coluna_biblioteca_itens = ft.Column(spacing=18, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    spinner_carregamento = ft.ProgressRing(width=28, height=28, stroke_width=2.5, color=COR_PETROLEO, visible=False)

    txt_contador_bib = ft.Text("BIBLIOTECA", color="white", weight="bold", size=11)

    def atualizar_contador_biblioteca():
        uid = sessao_usuario["id"]
        total = 0
        if uid:
            conn = None
            try:
                conn = obter_conexao()
                c = conn.cursor()
                query = "SELECT COUNT(*) FROM filmes WHERE usuario_id = %s" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "SELECT COUNT(*) FROM filmes WHERE usuario_id = ?"
                c.execute(query, (uid,))
                row = c.fetchone()
                total = row[0] if row else 0
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()
        txt_contador_bib.value = f"BIBLIOTECA ({total})"
        txt_contador_bib.update()

    coluna_sugestoes = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
    container_sugestoes = ft.Container(
        content=coluna_sugestoes,
        bgcolor="#111827",
        border_radius=8,
        border=criar_borda(1.2, COR_PETROLEO),
        padding=6,
        visible=False,
        width=320,
        height=260,
        top=160,
        left=20,
        shadow=ft.BoxShadow(blur_radius=15, color="#000000")
    )
    page.overlay.append(container_sugestoes)

    def ocultar_sugestoes():
        if container_sugestoes.visible:
            container_sugestoes.visible = False
            container_sugestoes.update()

    campo_busca = ft.TextField(
        hint_text="Buscar filmes, atores, temas, gêneros, países...",
        hint_style=ft.TextStyle(size=12, color="#64748b"),
        text_size=12,
        bgcolor="#0d1419",
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        expand=True,
        height=38,
        content_padding=ft.Padding(12, 0, 8, 0)
    )

    def alternar_castelo_flix(fid):
        uid = sessao_usuario["id"]
        if not uid or not fid:
            return False

        novo_estado = False
        conn = None
        try:
            conn = obter_conexao()
            c = conn.cursor()
            is_pg = bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES)
            q_sel = "SELECT streaming FROM filmes WHERE id = %s AND usuario_id = %s" if is_pg else "SELECT streaming FROM filmes WHERE id = ? AND usuario_id = ?"
            c.execute(q_sel, (fid, uid))
            row = c.fetchone()
            if row is not None:
                st_atual = row[0] or ""
                partes = [p.strip() for p in st_atual.split(",") if p.strip() and p.strip() != "Sem streaming no BR"]
                
                if "CasteloFlix" in partes:
                    partes.remove("CasteloFlix")
                    novo_estado = False
                else:
                    partes.insert(0, "CasteloFlix")
                    novo_estado = True

                nova_str = ", ".join(partes) if partes else "Sem streaming no BR"
                q_upd = "UPDATE filmes SET streaming = %s WHERE id = %s AND usuario_id = %s" if is_pg else "UPDATE filmes SET streaming = ? WHERE id = ? AND usuario_id = ?"
                c.execute(q_upd, (nova_str, fid, uid))
                conn.commit()
        except Exception as ex:
            print(f"Erro ao alternar CasteloFlix: {ex}")
        finally:
            if conn:
                conn.close()

        if tela_ativa_atual["indice"] == 1:
            carregar_biblioteca()
        return novo_estado

    def carregar_biblioteca():
        coluna_biblioteca_itens.controls.clear()
        todos_itens = []
        uid = sessao_usuario["id"]

        if uid:
            conn = None
            try:
                conn = obter_conexao()
                c = conn.cursor()
                is_pg = bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES)
                
                if is_pg:
                    query = """
                        SELECT id, titulo, ano, poster_url, nota_usuario, categoria, streaming, generos, imdb, tipo 
                        FROM filmes 
                        WHERE usuario_id = %s 
                        ORDER BY ctid DESC
                    """
                    c.execute(query, (uid,))
                else:
                    query = """
                        SELECT id, titulo, ano, poster_url, nota_usuario, categoria, streaming, generos, imdb, tipo 
                        FROM filmes 
                        WHERE usuario_id = ? 
                        ORDER BY rowid DESC
                    """
                    c.execute(query, (uid,))
                todos_itens = c.fetchall()
            except Exception as e:
                print(f"Erro ao carregar biblioteca: {e}")
            finally:
                if conn:
                    conn.close()

        total_para_assistir = sum(1 for it in todos_itens if it[5] == "Para Assistir")
        total_assistidos = sum(1 for it in todos_itens if it[5] == "Assistidos")

        aba_atual = estado_biblioteca["aba"]
        modo_atual = estado_biblioteca["modo"]
        tipo_atual = estado_biblioteca["filtro_tipo"]

        itens_aba = [it for it in todos_itens if it[5] == aba_atual]

        if tipo_atual == "movie":
            itens_filtrados = [it for it in itens_aba if (it[9] or "movie") == "movie"]
        elif tipo_atual == "tv":
            itens_filtrados = [it for it in itens_aba if it[9] == "tv"]
        else:
            itens_filtrados = itens_aba

        btn_print = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.PRINT, size=15, color="white"), ft.Text("Imprimir", color="white", size=12, weight="bold")], spacing=4),
            bgcolor=COR_CHUMBO,
            height=34,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=18), padding=ft.Padding(14, 0, 14, 0)),
            on_click=lambda e: imprimir_lista()
        )

        is_para_assistir_ativo = (aba_atual == "Para Assistir")
        
        btn_aba_para_assistir = ft.Button(
            content=ft.Text(f"⏳ Para Assistir ({total_para_assistir})", color="white" if is_para_assistir_ativo else "#94a3b8", weight="bold", size=14),
            bgcolor=COR_PETROLEO if is_para_assistir_ativo else "#141d24",
            height=46,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=14),
                side=ft.BorderSide(2.2, COR_ATIVO_BORDA) if is_para_assistir_ativo else ft.BorderSide(1.2, COR_BORDA),
                padding=ft.Padding(20, 0, 20, 0)
            ),
            on_click=lambda e: mudar_aba_biblioteca("Para Assistir")
        )

        btn_aba_assistidos = ft.Button(
            content=ft.Text(f"✓ Assistidos ({total_assistidos})", color="white" if not is_para_assistir_ativo else "#94a3b8", weight="bold", size=14),
            bgcolor=COR_PETROLEO if not is_para_assistir_ativo else "#141d24",
            height=46,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=14),
                side=ft.BorderSide(2.2, COR_ATIVO_BORDA) if not is_para_assistir_ativo else ft.BorderSide(1.2, COR_BORDA),
                padding=ft.Padding(20, 0, 20, 0)
            ),
            on_click=lambda e: mudar_aba_biblioteca("Assistidos")
        )

        linha_abas_biblioteca = ft.Row(
            spacing=16, 
            alignment=ft.MainAxisAlignment.CENTER, 
            controls=[btn_aba_para_assistir, btn_aba_assistidos]
        )

        def criar_botao_tipo(rotulo, valor_tipo):
            ativo = (tipo_atual == valor_tipo)
            return ft.Button(
                content=ft.Text(rotulo, color="white" if ativo else "#94a3b8", size=11, weight="bold"),
                bgcolor=COR_PETROLEO if ativo else COR_CARD,
                height=32,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=16), side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if ativo else ft.BorderSide(1, COR_BORDA), padding=ft.Padding(12, 0, 12, 0)),
                on_click=lambda e, t=valor_tipo: mudar_filtro_tipo_bib(t)
            )

        barra_tipo = ft.Row(
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Tipo:", size=11, color="#cbd5e1", weight="bold"),
                criar_botao_tipo("Todos", "todos"),
                criar_botao_tipo("🎬 Filmes", "movie"),
                criar_botao_tipo("📺 Séries", "tv"),
            ]
        )

        def criar_botao_filtro(rotulo, modo_alvo):
            ativo = (modo_atual == modo_alvo)
            return ft.Button(
                content=ft.Text(rotulo, color="white" if ativo else "#94a3b8", size=11, weight="bold"),
                bgcolor=COR_PETROLEO if ativo else COR_CARD,
                height=32,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), side=ft.BorderSide(2, COR_ATIVO_BORDA) if ativo else ft.BorderSide(1, COR_BORDA), padding=ft.Padding(14, 0, 14, 0)),
                on_click=lambda e, m=modo_alvo: mudar_modo_filtro(m)
            )

        controles_filtros = [
            ft.Text("Organizar:", size=11, color="#cbd5e1", weight="bold"),
            criar_botao_filtro("A-Z", "alfabetico"),
            criar_botao_filtro("Gênero", "genero"),
        ]

        if aba_atual == "Para Assistir":
            controles_filtros.append(criar_botao_filtro("Nota IMDb", "nota"))
        else:
            controles_filtros.append(criar_botao_filtro("Nota Pessoal", "nota_pessoal"))

        barra_filtros = ft.Row(
            spacing=6, 
            alignment=ft.MainAxisAlignment.CENTER, 
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controles_filtros
        )

        topo_biblioteca = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(f"Biblioteca ({len(todos_itens)})", size=22, weight="bold", color=COR_TEXTO_CLARO), 
                    btn_print
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=4),
                linha_abas_biblioteca,
                ft.Container(height=4),
                barra_tipo,
                barra_filtros
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            width=1050
        )

        coluna_biblioteca_itens.controls.append(topo_biblioteca)

        if not itens_filtrados:
            coluna_biblioteca_itens.controls.append(
                ft.Container(content=ft.Text("Nenhum título encontrado com os filtros selecionados.", color="#94a3b8", size=14), padding=ft.Padding(10, 30, 10, 20))
            )
            coluna_biblioteca_itens.update()
            return

        grade_categorias_mestre = ft.Row(
            wrap=True,
            spacing=28,
            run_spacing=24,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.START,
            width=1100
        )

        mobile_ativo = eh_mobile()
        largura_unitaria_card = 160 if mobile_ativo else 162
        espaco_entre_cards = 10
        max_colunas_por_bloco = 2 if mobile_ativo else 5

        def renderizar_secao(titulo_secao, icone_fallback, cor, lista):
            if not lista:
                return

            qtd_itens = len(lista)
            cols_efetivas = min(qtd_itens, max_colunas_por_bloco)
            largura_bloco = max(180, (cols_efetivas * largura_unitaria_card) + ((cols_efetivas - 1) * espaco_entre_cards) + 8)

            grade_cards = ft.Row(
                wrap=True,
                spacing=espaco_entre_cards,
                run_spacing=12,
                alignment=ft.MainAxisAlignment.START,
                controls=[
                    criar_card_filme(mid, tp, tit, ano, p_url, categoria=cat, nota=nota, streaming_txt=st_txt)
                    for mid, tit, ano, p_url, nota, cat, tp, st_txt in lista
                ]
            )

            cabecalho_itens = [
                ft.Text(icone_fallback, size=15),
                ft.Text(titulo_secao, size=15, weight="bold", color=cor),
                ft.Container(
                    content=ft.Text(f"{qtd_itens}", size=11, color="white", weight="bold"),
                    bgcolor=COR_CARD,
                    border=criar_borda(1, COR_BORDA),
                    padding=ft.Padding(6, 2, 6, 2),
                    border_radius=8
                )
            ]

            bloco = ft.Container(
                content=ft.Column([
                    ft.Row(
                        cabecalho_itens,
                        spacing=7,
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER
                    ),
                    grade_cards
                ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.START),
                width=largura_bloco
            )
            grade_categorias_mestre.controls.append(bloco)

        if modo_atual == "alfabetico":
            mapa_alfabetico = {}
            itens_ordenados = sorted(itens_filtrados, key=lambda x: normalizar_texto(x[1]))
            for row in itens_ordenados:
                mid, tit, ano, p_url, nota, cat, st_txt, tp = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[9]
                letra = normalizar_texto(tit)[:1].upper() if tit else "#"
                if not letra.isalpha():
                    letra = "#"
                mapa_alfabetico.setdefault(letra, []).append((mid, tit, ano, p_url, nota, cat, tp or "movie", st_txt or ""))

            letras_ordenadas = sorted([k for k in mapa_alfabetico.keys() if k != "#"])
            if "#" in mapa_alfabetico:
                letras_ordenadas.append("#")

            for letra in letras_ordenadas:
                renderizar_secao(f"Letra {letra}", "🔤", COR_TEXTO_CLARO, mapa_alfabetico[letra])

        elif modo_atual == "genero":
            mapa_generos = {}
            for row in itens_filtrados:
                mid, tit, ano, p_url, nota, cat, st_txt, gens, tp = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[9]
                
                # Limpa "Outros" ou vazios substituindo por "Sem Classificação"
                lista_bruta = [g.strip() for g in gens.split(",") if g.strip() and g.strip() != "Outros"] if gens else []
                lista_g = lista_bruta if lista_bruta else ["Sem Classificação"]

                for g in lista_g:
                    mapa_generos.setdefault(g, []).append((mid, tit, ano, p_url, nota, cat, tp or "movie", st_txt or ""))

            chaves_ordenadas = sorted([k for k in mapa_generos.keys() if k != "Sem Classificação"])
            if "Sem Classificação" in mapa_generos:
                chaves_ordenadas.append("Sem Classificação")

            for g_nome in chaves_ordenadas:
                cor_g = "#94a3b8" if g_nome == "Sem Classificação" else "#fbbf24"
                ico_g = "📁" if g_nome == "Sem Classificação" else "🏷️"
                renderizar_secao(g_nome, ico_g, cor_g, mapa_generos[g_nome])

        elif modo_atual == "nota":
            def pegar_imdb_float(it):
                val = it[8]
                try:
                    return float(str(val).replace(",", ".")) if (val and val != "N/A") else 0.0
                except Exception:
                    return 0.0

            itens_ordenados_imdb = sorted(itens_filtrados, key=pegar_imdb_float, reverse=True)
            lista_cards = [(row[0], row[1], row[2], row[3], row[4], row[5], row[9] or "movie", row[6] or "") for row in itens_ordenados_imdb]
            renderizar_secao("Ordenado por IMDb", "⭐", COR_TEXTO_CLARO, lista_cards)

        elif modo_atual == "nota_pessoal":
            def pegar_nota_pessoal_float(it):
                val = it[4]
                try:
                    return float(str(val).replace(",", ".")) if (val and val != "N/A") else 0.0
                except Exception:
                    return 0.0

            itens_ordenados_pessoal = sorted(itens_filtrados, key=pegar_nota_pessoal_float, reverse=True)
            lista_cards = [(row[0], row[1], row[2], row[3], row[4], row[5], row[9] or "movie", row[6] or "") for row in itens_ordenados_pessoal]
            renderizar_secao("Sua Nota Pessoal", "★", COR_TEXTO_CLARO, lista_cards)

        coluna_biblioteca_itens.controls.append(grade_categorias_mestre)
        coluna_biblioteca_itens.update()

    def mudar_aba_biblioteca(nova_aba):
        estado_biblioteca["aba"] = nova_aba
        if nova_aba == "Para Assistir" and estado_biblioteca["modo"] == "nota_pessoal":
            estado_biblioteca["modo"] = "nota"
        elif nova_aba == "Assistidos" and estado_biblioteca["modo"] == "nota":
            estado_biblioteca["modo"] = "nota_pessoal"
        carregar_biblioteca()

    def mudar_modo_filtro(novo_modo):
        estado_biblioteca["modo"] = novo_modo
        carregar_biblioteca()

    def mudar_filtro_tipo_bib(novo_tipo):
        estado_biblioteca["filtro_tipo"] = novo_tipo
        carregar_biblioteca()

    def imprimir_lista():
        uid = sessao_usuario["id"]
        filmes = []
        if uid:
            conn = None
            try:
                conn = obter_conexao()
                c = conn.cursor()
                query = "SELECT titulo, ano, imdb, rotten, streaming, diretor, tipo FROM filmes WHERE categoria = 'Para Assistir' AND usuario_id = %s ORDER BY titulo ASC" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "SELECT titulo, ano, imdb, rotten, streaming, diretor, tipo FROM filmes WHERE categoria = 'Para Assistir' AND usuario_id = ? ORDER BY titulo ASC"
                c.execute(query, (uid,))
                filmes = c.fetchall()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()

        if not filmes:
            return

        linhas = "".join([f"<tr><td>{i}</td><td><b>{t}</b> ({a})</td><td>{'Série' if tp == 'tv' else 'Filme'}</td><td>⭐ {im}</td><td>🍅 {rt}</td><td>{st}</td><td>{dr}</td></tr>" for i, (t, a, im, rt, st, dr, tp) in enumerate(filmes, 1)])
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Para Assistir</title>
        <style>body{{font-family:sans-serif;margin:20px;}}table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid #ccc;padding:8px;text-align:left;}}th{{background:#f1f5f9;}}</style>
        </head><body><h2>🎬 Lista Para Assistir ({len(filmes)})</h2><table><thead><tr><th>#</th><th>Título</th><th>Tipo</th><th>IMDb</th><th>RT</th><th>Streaming</th><th>Direção/Criação</th></tr></thead><tbody>{linhas}</tbody></table><script>window.onload=function(){{window.print();}}</script></body></html>"""
        arq = os.path.abspath("lista_para_assistir.html")
        with open(arq, "w", encoding="utf-8") as f:
            f.write(html)
        page.launch_url(f"file://{arq}")

    def remover_filme_direto(fid):
        uid = sessao_usuario["id"]
        if uid:
            conn = None
            try:
                conn = obter_conexao()
                c = conn.cursor()
                query = "DELETE FROM filmes WHERE id = %s AND usuario_id = %s" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "DELETE FROM filmes WHERE id = ? AND usuario_id = ?"
                c.execute(query, (fid, uid))
                conn.commit()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()
            recarregar_ids_salvos()
            atualizar_contador_biblioteca()
            carregar_biblioteca()

    def abrir_modal_avaliacao(fid, nota_atual=None):
        nota_selecionada = {"valor": str(int(float(nota_atual))) if (nota_atual and nota_atual != "N/A") else "10"}

        botoes_n = []
        linha_1_5 = ft.Row(spacing=6, alignment=ft.MainAxisAlignment.CENTER)
        linha_6_10 = ft.Row(spacing=6, alignment=ft.MainAxisAlignment.CENTER)

        def selecionar_v(val_s):
            nota_selecionada["valor"] = str(val_s)
            for b in botoes_n:
                is_ativo = (b.data == str(val_s))
                b.bgcolor = COR_PETROLEO if is_ativo else "#1f2937"
                b.content.color = "white" if is_ativo else "#94a3b8"
            modal.update()

        for n in range(1, 11):
            s_val = str(n)
            is_padrao = (s_val == nota_selecionada["valor"])
            btn = ft.Container(
                content=ft.Text(s_val, size=13, weight="bold", color="white" if is_padrao else "#94a3b8", text_align=ft.TextAlign.CENTER),
                alignment=ft.Alignment(0, 0),
                width=38,
                height=38,
                shape=ft.BoxShape.CIRCLE,
                bgcolor=COR_PETROLEO if is_padrao else "#1f2937",
                data=s_val,
                on_click=lambda e, val=s_val: selecionar_v(val)
            )
            botoes_n.append(btn)
            if n <= 5:
                linha_1_5.controls.append(btn)
            else:
                linha_6_10.controls.append(btn)

        def salvar_nota(e):
            uid = sessao_usuario["id"]
            if fid and uid:
                conn = None
                try:
                    conn = obter_conexao()
                    c = conn.cursor()
                    query = "UPDATE filmes SET categoria = 'Assistidos', nota_usuario = %s WHERE id = %s AND usuario_id = %s" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "UPDATE filmes SET categoria = 'Assistidos', nota_usuario = ? WHERE id = ? AND usuario_id = ?"
                    c.execute(query, (nota_selecionada["valor"], fid, uid))
                    conn.commit()
                except Exception as ex:
                    print(f"Erro ao salvar nota: {ex}")
                finally:
                    if conn:
                        conn.close()
                fechar_dialogo(modal)
                carregar_biblioteca()

        modal = ft.AlertDialog(
            modal=False,
            title=ft.Text("Qual nota você dá ao título?", size=16, weight="bold"),
            content=ft.Column([
                ft.Text("Selecione a nota:", size=13, color="#94a3b8"),
                linha_1_5,
                linha_6_10,
            ], tight=True, spacing=10),
            actions=[
                ft.Button(content=ft.Text("Cancelar", color="#94a3b8"), on_click=lambda e: fechar_dialogo(modal)),
                ft.Button(content=ft.Text("Confirmar", color="white"), bgcolor=COR_PETROLEO, on_click=salvar_nota)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )

        abrir_dialogo(modal)

    def pedir_confirmacao_remocao(fid, titulo):
        def confirmar_remocao(e):
            uid = sessao_usuario["id"]
            if fid and uid:
                conn = None
                try:
                    conn = obter_conexao()
                    c = conn.cursor()
                    query = "DELETE FROM filmes WHERE id = %s AND usuario_id = %s" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "DELETE FROM filmes WHERE id = ? AND usuario_id = ?"
                    c.execute(query, (fid, uid))
                    conn.commit()
                except Exception:
                    pass
                finally:
                    if conn:
                        conn.close()
                recarregar_ids_salvos()
                atualizar_contador_biblioteca()

            fechar_dialogo(modal_exclusao)
            carregar_biblioteca()

        modal_exclusao = ft.AlertDialog(
            modal=False,
            title=ft.Text("Confirmar Exclusão", size=16, weight="bold", color="#ef4444"),
            content=ft.Text(f"Deseja remover '{titulo}' da lista de Assistidos?", size=14, color="#cbd5e1"),
            actions=[
                ft.Button(content=ft.Text("Cancelar", color="#94a3b8"), on_click=lambda e: fechar_dialogo(modal_exclusao)),
                ft.Button(content=ft.Text("Sim, remover", color="white"), bgcolor=COR_VERMELHO_PLAY, on_click=confirmar_remocao)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        abrir_dialogo(modal_exclusao)

    def abrir_detalhes(mid, mtype, titulo_prev, ano_prev, poster_prev, tela_atual="home"):
        ocultar_sugestoes()
        progresso.visible = True
        page.update()

        str_mid = str(mid)
        if "_" in str_mid:
            partes = str_mid.split("_")
            tipo_detectado = partes[0]
            raw_mid = partes[1]
        else:
            tipo_detectado = mtype
            raw_mid = str_mid

        mtype_seguro = "tv" if tipo_detectado in ["tv", "series"] else "movie"
        chave_tmdb_calc = f"{mtype_seguro}_{raw_mid}"

        c = carregar_config()
        tmdb_key = c.get("tmdb_key", "").strip()
        omdb_key = c.get("omdb_key", "").strip()
        uid = sessao_usuario["id"]

        titulo = titulo_prev
        ano = str(ano_prev)
        poster_url = poster_prev if poster_prev else "https://via.placeholder.com/180x260?text=Sem+Poster"
        sinopse = "Sinopse não disponível em português."
        diretor = "N/A"
        elenco = "Não informado"
        generos_txt = "Sem Classificação"
        streamings = "Sem streaming no BR"
        imdb_nota = "N/A"
        rt_nota = "N/A"
        meta_nota = "N/A"
        trailer_url = None
        tem_digital = (mtype_seguro == "tv")
        titulo_orig = ""
        temporadas_detalhes = []
        esta_no_castelo = False

        if uid:
            conn = None
            try:
                conn = obter_conexao()
                c_db = conn.cursor()
                query = "SELECT sinopse, diretor, elenco, generos, streaming, imdb, rotten, metascore, trailer_url, poster_url FROM filmes WHERE id = %s AND usuario_id = %s" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "SELECT sinopse, diretor, elenco, generos, streaming, imdb, rotten, metascore, trailer_url, poster_url FROM filmes WHERE id = ? AND usuario_id = ?"
                c_db.execute(query, (chave_tmdb_calc, uid))
                row_db = c_db.fetchone()
                if row_db:
                    if row_db[0] and row_db[0] != "Adicionado diretamente da tela inicial.":
                        sinopse = row_db[0]
                    if row_db[1] and row_db[1] != "N/A":
                        diretor = row_db[1]
                    if row_db[2] and row_db[2] != "N/A":
                        elenco = row_db[2]
                    if row_db[3] and row_db[3] not in ["Outros", "Sem Classificação"]:
                        generos_txt = row_db[3]
                    if row_db[4]:
                        streamings = row_db[4]
                        esta_no_castelo = ("casteloflix" in streamings.lower())
                    if row_db[5] and row_db[5] != "N/A":
                        imdb_nota = row_db[5]
                    if row_db[6] and row_db[6] != "N/A":
                        rt_nota = row_db[6]
                    if row_db[7] and row_db[7] != "N/A":
                        meta_nota = row_db[7]
                    if row_db[8]:
                        trailer_url = row_db[8]
                    if row_db[9]:
                        poster_url = row_db[9]
            except Exception as e_sql:
                print(f"Erro ao buscar do cache: {e_sql}")
            finally:
                if conn:
                    conn.close()

        if tmdb_key:
            try:
                url_tmdb = f"https://api.themoviedb.org/3/{mtype_seguro}/{raw_mid}?api_key={tmdb_key}&language=pt-BR&append_to_response=credits,watch/providers,external_ids,videos,release_dates"
                res = requests.get(url_tmdb, timeout=4.0).json()

                if mtype_seguro == "movie":
                    for cr in res.get("credits", {}).get("crew", []):
                        if cr.get("job") == "Director":
                            diretor = cr.get("name")
                            break
                    info_criacao = f"Direção: {diretor}"
                else:
                    criadores = [cr.get("name") for cr in res.get("created_by", [])]
                    temporadas_raw = res.get("seasons", [])
                    for temp in temporadas_raw:
                        t_nome = temp.get("name")
                        t_nota = temp.get("vote_average", 0)
                        t_num = temp.get("season_number")
                        if t_num > 0 and t_nome:
                            nota_str = f"⭐ {t_nota:.1f}" if t_nota and t_nota > 0 else "⭐ Sem nota"
                            temporadas_detalhes.append(f"{t_nome}: {nota_str}")

                    temporadas_qtd = res.get("number_of_seasons", 1)
                    info_criacao = f"Criador(es): {', '.join(criadores) if criadores else 'Não informado'} • {temporadas_qtd} Temporada(s)"
                    diretor = info_criacao

                credits_data = res.get("credits", {})
                elenco_list = [a.get("name") for a in credits_data.get("cast", [])[:4]]
                if elenco_list:
                    elenco = ", ".join(elenco_list)

                titulo = res.get("title") or res.get("name") or titulo_prev
                titulo_orig = res.get("original_title") or res.get("original_name") or ""
                ano = str((res.get("release_date") or res.get("first_air_date")) or "")[:4] or str(ano_prev)
                if res.get("overview"):
                    sinopse = res.get("overview")

                lista_generos = [g.get("name") for g in res.get("genres", []) if g.get("name")]
                if lista_generos:
                    generos_txt = ", ".join(lista_generos)

                br_providers = res.get("watch/providers", {}).get("results", {}).get("BR", {}).get("flatrate", [])
                stream_nomes = [p.get("provider_name") for p in br_providers]

                p_path = res.get("poster_path")
                if p_path:
                    poster_url = f"https://image.tmdb.org/t/p/w400{p_path}"

                imdb_id = res.get("imdb_id") or res.get("external_ids", {}).get("imdb_id")
                
                tmdb_vote = res.get("vote_average")
                if tmdb_vote and tmdb_vote > 0:
                    imdb_nota = f"{tmdb_vote:.1f}"

                if omdb_key:
                    try:
                        res_omdb = None
                        if imdb_id:
                            res_omdb = requests.get(f"https://www.omdbapi.com/?i={imdb_id}&apikey={omdb_key}", timeout=2.0).json()
                        elif titulo:
                            tipo_omdb = "series" if mtype_seguro == "tv" else "movie"
                            res_omdb = requests.get(f"https://www.omdbapi.com/?t={quote_plus(titulo)}&type={tipo_omdb}&apikey={omdb_key}", timeout=2.0).json()

                        if res_omdb and res_omdb.get("Response") == "True":
                            if res_omdb.get("imdbRating") and res_omdb.get("imdbRating") != "N/A":
                                imdb_nota = res_omdb.get("imdbRating")
                            m_raw = res_omdb.get("Metascore", "N/A")
                            if m_raw and m_raw != "N/A":
                                meta_nota = m_raw
                            for val in res_omdb.get("Ratings", []):
                                if val.get("Source") == "Rotten Tomatoes":
                                    rt_nota = val.get("Value")
                                    break
                    except Exception:
                        pass

                for v in res.get("videos", {}).get("results", []):
                    if v.get("site") == "YouTube":
                        trailer_url = f"https://www.youtube.com/watch?v={v.get('key')}"
                        if v.get("type") in ["Trailer", "Teaser"]:
                            break

                hoje = datetime.now().strftime("%Y-%m-%d")
                if not tem_digital:
                    for pais in res.get("release_dates", {}).get("results", []):
                        for r_item in pais.get("release_dates", []):
                            if r_item.get("type") in [4, 5]:
                                r_data = (r_item.get("release_date") or "")[:10]
                                if r_data and r_data <= hoje:
                                    tem_digital = True
                                    break
                        if tem_digital:
                            break
                    if not tem_digital and br_providers:
                        tem_digital = True

                if tem_digital and "Stremio" not in stream_nomes:
                    stream_nomes.append("Stremio")

                if esta_no_castelo and "CasteloFlix" not in stream_nomes:
                    stream_nomes.insert(0, "CasteloFlix")

                if stream_nomes:
                    streamings = ", ".join(stream_nomes)
            except Exception as ex:
                print(f"Erro TMDB: {ex}")

        progresso.visible = False

        dt_img = ft.Image(src=poster_url, width=180, height=260, border_radius=10, fit="cover")
        tag_tipo = "Série" if mtype_seguro == "tv" else "Filme"

        modal_det = ft.AlertDialog(modal=False, bgcolor="transparent", content_padding=0)

        def acao_fechar_x(e):
            modal_det.open = False
            page.update()

        btn_fechar_estilizado = ft.IconButton(
            icon=ft.Icons.CLOSE_ROUNDED,
            icon_color="white",
            icon_size=20,
            bgcolor=COR_VERMELHO_PLAY,
            width=34,
            height=34,
            tooltip="Fechar",
            on_click=acao_fechar_x
        )

        logos_row_controls = []
        st_lower = streamings.lower()
        for nome_st, arq_st in MAPA_LOGOS_STREAMING.items():
            termo_busca_st = nome_st.lower().replace(" plus", "").replace("+", "")
            if termo_busca_st in st_lower and os.path.exists(os.path.join(DIR_ASSETS, arq_st)):
                logos_row_controls.append(
                    ft.Container(
                        content=ft.Image(src=arq_st, width=26, height=26, border_radius=6, fit="cover"),
                        tooltip=nome_st
                    )
                )

        txt_streamings_modal = ft.Text(f"📺 {streamings}", size=12, color="#10b981", weight="bold", text_align=ft.TextAlign.CENTER)

        ja_esta = (chave_tmdb_calc in ids_salvos_usuario) or (normalizar_texto(titulo) in titulos_salvos_usuario)

        icone_castelo_btn = ft.Image(src="castelo.png", width=18, height=18, border_radius=4) if os.path.exists(os.path.join(DIR_ASSETS, "castelo.png")) else ft.Icon(ft.Icons.CASTLE, size=16, color="white")
        txt_castelo_btn = ft.Text("Disponível no CasteloFlix ✓" if esta_no_castelo else "Adicionar ao CasteloFlix", size=11, weight="bold", color="white")
        
        btn_castelo_modal = ft.Container(
            visible=ja_esta,
            bgcolor=COR_PETROLEO if esta_no_castelo else "#1e293b",
            border=criar_borda(1.5, COR_ATIVO_BORDA if esta_no_castelo else "#334155"),
            border_radius=8,
            padding=ft.Padding(12, 6, 12, 6),
            content=ft.Row([icone_castelo_btn, txt_castelo_btn], spacing=6, tight=True, alignment=ft.MainAxisAlignment.CENTER)
        )

        def clicar_toggle_castelo_modal(e):
            ativo_agora = alternar_castelo_flix(chave_tmdb_calc)
            btn_castelo_modal.bgcolor = COR_PETROLEO if ativo_agora else "#1e293b"
            btn_castelo_modal.border = criar_borda(1.5, COR_ATIVO_BORDA if ativo_agora else "#334155")
            txt_castelo_btn.value = "Disponível no CasteloFlix ✓" if ativo_agora else "Adicionar ao CasteloFlix"
            
            partes_st = [p.strip() for p in txt_streamings_modal.value.replace("📺 ", "").split(",") if p.strip() and p.strip() != "Sem streaming no BR"]
            if ativo_agora and "CasteloFlix" not in partes_st:
                partes_st.insert(0, "CasteloFlix")
            elif not ativo_agora and "CasteloFlix" in partes_st:
                partes_st.remove("CasteloFlix")
            txt_streamings_modal.value = f"📺 {', '.join(partes_st) if partes_st else 'Sem streaming no BR'}"
            
            modal_det.update()

        btn_castelo_modal.on_click = clicar_toggle_castelo_modal

        info_col = [
            ft.Row([btn_fechar_estilizado], alignment=ft.MainAxisAlignment.END),
            ft.Container(content=dt_img, alignment=ft.Alignment(0, 0)),
            ft.Container(height=4),
            ft.Row([
                ft.Container(content=ft.Text(f"⭐ {imdb_nota}", color="black", size=11, weight="bold"), bgcolor="#f59e0b", padding=ft.Padding(5, 2, 5, 2), border_radius=5),
                ft.Container(content=ft.Text(f"🍅 {rt_nota}", color="white", size=11, weight="bold"), bgcolor=COR_VERMELHO_PLAY, padding=ft.Padding(5, 2, 5, 2), border_radius=5),
                ft.Container(content=ft.Text(f"Ⓜ {meta_nota}", color="white", size=11, weight="bold"), bgcolor="#54a72a" if meta_nota != "N/A" and int(meta_nota) >= 61 else "#334155", padding=ft.Padding(5, 2, 5, 2), border_radius=5),
            ], spacing=6, wrap=True, alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(
                content=ft.Text("🎬 Stremio: HD/4K Disponível" if tem_digital else "⏳ Stremio: Apenas Cinema / CAM", size=11, weight="bold", color="#a7f3d0" if tem_digital else "#fde68a"),
                bgcolor="#065f46" if tem_digital else "#78350f",
                padding=ft.Padding(6, 4, 6, 4),
                border_radius=6,
                alignment=ft.Alignment(0, 0)
            ),
            ft.Row(logos_row_controls, spacing=8, alignment=ft.MainAxisAlignment.CENTER) if logos_row_controls else ft.Container(),
            txt_streamings_modal,
            btn_castelo_modal,
            ft.Container(height=4),
            ft.Text(f"{titulo} ({ano}) • {tag_tipo}", size=18, weight="bold", color="white", text_align=ft.TextAlign.CENTER),
            ft.Text(f"Original: {titulo_orig}", size=12, italic=True, color="#94a3b8", text_align=ft.TextAlign.CENTER, visible=bool(titulo_orig and normalizar_texto(titulo_orig) != normalizar_texto(titulo))),
            ft.Text(f"Direção: {diretor}\nElenco: {elenco}\nGêneros: {generos_txt}", size=11, color="#94a3b8", text_align=ft.TextAlign.CENTER),
        ]

        fallback_trailer = f"https://www.youtube.com/results?search_query={quote_plus('trailer oficial ' + titulo + ' ' + str(ano))}"
        btn_tr = ft.Button(content=ft.Text("▶ Trailer", color="white", size=12, weight="bold"), bgcolor=COR_VERMELHO_PLAY, url=trailer_url if trailer_url else fallback_trailer)
        
        btn_slv = ft.Button(content=ft.Text("✓ Na Biblioteca" if ja_esta else "+ Adicionar à Biblioteca", color="white", size=12), bgcolor="#334155" if ja_esta else COR_PETROLEO, disabled=ja_esta)
        btn_ir = ft.Button(content=ft.Text("📁 Ir para Biblioteca", color="white", size=12), bgcolor="#10b981", visible=(ja_esta and tela_atual != "biblioteca"))

        def acao_salvar_modal(e):
            if uid:
                conn = None
                try:
                    conn = obter_conexao()
                    c = conn.cursor()
                    query = "SELECT categoria FROM filmes WHERE id = %s AND usuario_id = %s" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "SELECT categoria FROM filmes WHERE id = ? AND usuario_id = ?"
                    c.execute(query, (chave_tmdb_calc, uid))
                    if not c.fetchone():
                        insert_query = """
                            INSERT INTO filmes (id, titulo, ano, diretor, elenco, sinopse, imdb, rotten, metascore, streaming, poster_url, categoria, nota_usuario, trailer_url, generos, usuario_id, tipo)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Para Assistir', %s, %s, %s, %s, %s)
                        """ if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else """
                            INSERT INTO filmes (id, titulo, ano, diretor, elenco, sinopse, imdb, rotten, metascore, streaming, poster_url, categoria, nota_usuario, trailer_url, generos, usuario_id, tipo)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Para Assistir', ?, ?, ?, ?, ?)
                        """
                        c.execute(insert_query, (
                            chave_tmdb_calc, titulo, ano, diretor, elenco, sinopse,
                            imdb_nota, rt_nota, meta_nota, streamings, poster_url,
                            None, trailer_url, generos_txt, uid, mtype_seguro
                        ))
                        conn.commit()
                        ids_salvos_usuario.add(chave_tmdb_calc)
                        titulos_salvos_usuario.add(normalizar_texto(titulo))
                except Exception as ex_db:
                    print(f"Erro ao salvar: {ex_db}")
                finally:
                    if conn:
                        conn.close()

            btn_slv.content = ft.Text("✓ Na Biblioteca", color="white", size=12)
            btn_slv.bgcolor = "#334155"
            btn_slv.disabled = True
            btn_ir.visible = True
            btn_castelo_modal.visible = True

            marcar_botao_home_como_salvo(chave_tmdb_calc)
            atualizar_contador_biblioteca()
            modal_det.update()

        btn_slv.on_click = acao_salvar_modal
        btn_ir.on_click = lambda e: (fechar_dialogo(modal_det), alternar_tela(1))

        elementos_modal = [
            ft.Column(info_col, spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([btn_tr, btn_slv], spacing=8, alignment=ft.MainAxisAlignment.CENTER, wrap=True) if tela_atual != "biblioteca" else ft.Row([btn_tr], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(content=btn_ir, alignment=ft.Alignment(0, 0)),
        ]

        if temporadas_detalhes:
            elementos_modal.append(ft.Text("Temporadas & Notas", size=13, weight="bold", color="#94a3b8"))
            lista_t_view = ft.Row(
                controls=[ft.Container(content=ft.Text(t_txt, size=11, color="#cbd5e1", weight="bold"), bgcolor="#1e293b", padding=ft.Padding(8, 4, 8, 4), border_radius=6) for t_txt in temporadas_detalhes],
                wrap=True,
                spacing=6,
                run_spacing=6,
                alignment=ft.MainAxisAlignment.CENTER
            )
            elementos_modal.append(lista_t_view)

        elementos_modal.extend([
            ft.Text("Sinopse", size=13, weight="bold", color="#94a3b8"),
            ft.Text(sinopse, size=12, color="#cbd5e1", text_align=ft.TextAlign.JUSTIFY),
        ])

        conteudo = ft.Container(
            width=480,
            bgcolor=COR_CARD,
            padding=18,
            border_radius=14,
            border=criar_borda(1.5, COR_PETROLEO),
            content=ft.Column(elementos_modal, spacing=10, scroll=ft.ScrollMode.AUTO, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        )

        modal_det.content = conteudo
        abrir_dialogo(modal_det)

    def adicionar_rapido_poster(e, mid, mtype, titulo, ano, poster_url, chave_id, btn_adicionar):
        uid = sessao_usuario["id"]
        if not uid or chave_id in ids_salvos_usuario:
            return

        ids_salvos_usuario.add(chave_id)
        if titulo:
            titulos_salvos_usuario.add(normalizar_texto(titulo))

        btn_adicionar.icon = ft.Icons.CHECK
        btn_adicionar.icon_color = "#10b981"
        btn_adicionar.bgcolor = "#064e3b"
        btn_adicionar.disabled = True
        btn_adicionar.tooltip = "Já está na sua biblioteca"
        btn_adicionar.update()

        def _processar_e_salvar():
            str_mid = str(mid)
            raw_mid = str_mid.split("_")[1] if "_" in str_mid else str_mid
            mtype_seguro = "tv" if mtype in ["tv", "series"] else "movie"
            c_cfg = carregar_config()
            tmdb_key = c_cfg.get("tmdb_key", "").strip()

            diretor_val = "N/A"
            elenco_val = "Não informado"
            sinopse_val = "Sinopse não disponível em português."
            imdb_val = "N/A"
            generos_val = "Sem Classificação"
            streamings_val = "Sem streaming no BR"
            trailer_val = None

            if tmdb_key:
                try:
                    url_tmdb = f"https://api.themoviedb.org/3/{mtype_seguro}/{raw_mid}?api_key={tmdb_key}&language=pt-BR&append_to_response=credits,watch/providers,videos,release_dates"
                    res = requests.get(url_tmdb, timeout=4.0).json()

                    lista_g = [g.get("name") for g in res.get("genres", []) if g.get("name")]
                    if lista_g:
                        generos_val = ", ".join(lista_g)

                    if mtype_seguro == "movie":
                        for cr in res.get("credits", {}).get("crew", []):
                            if cr.get("job") == "Director":
                                diretor_val = cr.get("name")
                                break
                    else:
                        criadores = [cr.get("name") for cr in res.get("created_by", [])]
                        if criadores:
                            diretor_val = ", ".join(criadores)

                    elenco_list = [a.get("name") for a in res.get("credits", {}).get("cast", [])[:4]]
                    if elenco_list:
                        elenco_val = ", ".join(elenco_list)

                    if res.get("overview"):
                        sinopse_val = res.get("overview")
                    tmdb_vote = res.get("vote_average")
                    if tmdb_vote and tmdb_vote > 0:
                        imdb_val = f"{tmdb_vote:.1f}"

                    for v in res.get("videos", {}).get("results", []):
                        if v.get("site") == "YouTube":
                            trailer_val = f"https://www.youtube.com/watch?v={v.get('key')}"
                            if v.get("type") in ["Trailer", "Teaser"]:
                                break

                    br_providers = res.get("watch/providers", {}).get("results", {}).get("BR", {}).get("flatrate", [])
                    stream_nomes = [p.get("provider_name") for p in br_providers]

                    tem_digital = (mtype_seguro == "tv")
                    hoje = datetime.now().strftime("%Y-%m-%d")
                    if not tem_digital:
                        for pais in res.get("release_dates", {}).get("results", []):
                            for r_item in pais.get("release_dates", []):
                                if r_item.get("type") in [4, 5]:
                                    r_data = (r_item.get("release_date") or "")[:10]
                                    if r_data and r_data <= hoje:
                                        tem_digital = True
                                        break
                            if tem_digital:
                                break
                        if not tem_digital and br_providers:
                            tem_digital = True

                    if tem_digital and "Stremio" not in stream_nomes:
                        stream_nomes.append("Stremio")

                    if stream_nomes:
                        streamings_val = ", ".join(stream_nomes)
                except Exception as ex_api:
                    print(f"Erro busca detalhes add rapido: {ex_api}")

            conn = None
            try:
                conn = obter_conexao()
                c = conn.cursor()
                is_pg = bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES)
                query_sel = "SELECT id FROM filmes WHERE id = %s AND usuario_id = %s" if is_pg else "SELECT id FROM filmes WHERE id = ? AND usuario_id = ?"
                c.execute(query_sel, (chave_id, uid))
                if not c.fetchone():
                    query_ins = """
                        INSERT INTO filmes (id, titulo, ano, diretor, elenco, sinopse, imdb, rotten, metascore, streaming, poster_url, categoria, nota_usuario, trailer_url, generos, usuario_id, tipo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'N/A', 'N/A', %s, %s, 'Para Assistir', NULL, %s, %s, %s, %s)
                    """ if is_pg else """
                        INSERT INTO filmes (id, titulo, ano, diretor, elenco, sinopse, imdb, rotten, metascore, streaming, poster_url, categoria, nota_usuario, trailer_url, generos, usuario_id, tipo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'N/A', 'N/A', ?, ?, 'Para Assistir', NULL, ?, ?, ?, ?)
                    """
                    c.execute(query_ins, (
                        chave_id, titulo, str(ano), diretor_val, elenco_val, sinopse_val,
                        imdb_val, streamings_val, poster_url, trailer_val, generos_val, uid, mtype_seguro
                    ))
                    conn.commit()
                    atualizar_contador_biblioteca()
            except Exception as ex:
                print(f"Erro add rapido db: {ex}")
            finally:
                if conn:
                    conn.close()

        threading.Thread(target=_processar_e_salvar, daemon=True).start()

    def criar_card_filme(mid, mtype, titulo, ano, poster_url, categoria=None, nota=None, streaming_txt=""):
        mtype_seguro = "tv" if mtype in ["tv", "series"] else "movie"
        chave_id = mid if isinstance(mid, str) and ("_" in mid or mid.startswith("tt")) else f"{mtype_seguro}_{mid}"
        mobile = eh_mobile()
        
        largura_card = 160 if mobile else 162
        altura_img = 225 if mobile else 216

        st_lower = (streaming_txt or "").lower()
        no_castelo = ("casteloflix" in st_lower)

        # Mini-faixa permanente com logos dos streamings abaixo do título (Opção A)
        faixa_logos_streaming = None
        if categoria is not None:
            icones_plataformas = []
            for nome_st, arq_st in MAPA_LOGOS_STREAMING.items():
                termo_busca_st = nome_st.lower().replace(" plus", "").replace("+", "")
                if termo_busca_st in st_lower and os.path.exists(os.path.join(DIR_ASSETS, arq_st)):
                    icones_plataformas.append(
                        ft.Container(
                            content=ft.Image(src=arq_st, width=18, height=18, border_radius=4, fit="cover"),
                            tooltip=nome_st
                        )
                    )
            
            if icones_plataformas:
                faixa_logos_streaming = ft.Row(
                    controls=icones_plataformas,
                    spacing=4,
                    alignment=ft.MainAxisAlignment.CENTER,
                    wrap=True,
                    height=22
                )
            else:
                faixa_logos_streaming = ft.Container(
                    content=ft.Text("Sem streaming", size=9, color="#64748b", italic=True),
                    height=22,
                    alignment=ft.Alignment(0, 0)
                )

        acoes = []
        if categoria == "Para Assistir":
            acoes.append(
                ft.Button(
                    content=ft.Text("✓ Visto", color="white", size=10),
                    bgcolor="#10b981",
                    height=28,
                    style=ft.ButtonStyle(padding=ft.Padding(8, 0, 8, 0)),
                    on_click=lambda e, cid=chave_id: abrir_modal_avaliacao(cid)
                )
            )
            
            tem_img_castelo = os.path.exists(os.path.join(DIR_ASSETS, "castelo.png"))
            conteudo_castelo = ft.Image(
                src="castelo.png",
                width=16,
                height=16,
                border_radius=4,
                opacity=1.0 if no_castelo else 0.35
            ) if tem_img_castelo else ft.Icon(ft.Icons.CASTLE, size=14, color="#38bdf8" if no_castelo else "#64748b")

            btn_castelo_card = ft.Container(
                content=conteudo_castelo,
                width=26,
                height=26,
                border_radius=6,
                alignment=ft.Alignment(0, 0),
                bgcolor="#064e3b" if no_castelo else "#1e293b",
                border=criar_borda(1.2, COR_ATIVO_BORDA if no_castelo else "transparent"),
                tooltip="Remover do CasteloFlix" if no_castelo else "Marcar no CasteloFlix",
                on_click=lambda e, cid=chave_id: alternar_castelo_flix(cid)
            )
            acoes.append(btn_castelo_card)

            acoes.append(
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_color="red400",
                    icon_size=15,
                    width=26,
                    height=26,
                    style=ft.ButtonStyle(padding=0),
                    tooltip="Remover",
                    on_click=lambda e, cid=chave_id: remover_filme_direto(cid)
                )
            )
        elif categoria == "Assistidos":
            bg_nota, cor_texto, borda_nota = obter_estilo_nota(nota)
            acoes.append(
                ft.Container(
                    content=ft.Text(f"★ {nota}" if nota else "★ Avaliar", color=cor_texto, size=11, weight="bold"),
                    bgcolor=bg_nota,
                    border=borda_nota,
                    padding=ft.Padding(6, 3, 6, 3),
                    border_radius=5,
                    on_click=lambda e, cid=chave_id, n=nota: abrir_modal_avaliacao(cid, n)
                )
            )
            acoes.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color="red400",
                    icon_size=16,
                    tooltip="Excluir",
                    on_click=lambda e, cid=chave_id, t=titulo: pedir_confirmacao_remocao(cid, t)
                )
            )

        badge_tipo = None
        if mtype_seguro == "tv":
            badge_tipo = ft.Container(
                content=ft.Text("SÉRIE", size=9, weight="bold", color="white"),
                bgcolor="#4338ca",
                padding=ft.Padding(4, 2, 4, 2),
                border_radius=4,
                top=6,
                right=6
            )

        btn_add_rapido = None
        if not categoria:
            ja_esta_salvo = (chave_id in ids_salvos_usuario) or (normalizar_texto(titulo) in titulos_salvos_usuario)
            btn_add_rapido = ft.IconButton(
                icon=ft.Icons.CHECK if ja_esta_salvo else ft.Icons.ADD,
                icon_color="#10b981" if ja_esta_salvo else "white",
                bgcolor="#064e3b" if ja_esta_salvo else "#0d1419cc",
                tooltip="Já está na sua biblioteca" if ja_esta_salvo else "Adicionar à Biblioteca",
                disabled=ja_esta_salvo,
                bottom=6,
                right=6,
                width=32 if mobile else 28,
                height=32 if mobile else 28,
                style=ft.ButtonStyle(padding=0)
            )
            btn_add_rapido.on_click = lambda e, m=mid, mt=mtype_seguro, t=titulo, a=ano, p=poster_url, c=chave_id, b=btn_add_rapido: adicionar_rapido_poster(e, m, mt, t, a, p, c, b)
            botoes_add_home[chave_id] = btn_add_rapido

        stack_itens = [
            ft.Image(
                src=poster_url if poster_url else "https://via.placeholder.com/152x216?text=Sem+Poster",
                width=largura_card - 10,
                height=altura_img,
                border_radius=6,
                fit="cover"
            )
        ]
        if badge_tipo:
            stack_itens.append(badge_tipo)
        if btn_add_rapido:
            stack_itens.append(btn_add_rapido)

        elementos_coluna_card = [
            ft.Stack(stack_itens),
            ft.Text(
                f"{titulo}\n({ano})",
                size=11,
                weight="bold",
                max_lines=2,
                overflow="ellipsis",
                width=largura_card - 10,
                text_align=ft.TextAlign.CENTER,
                color=COR_TEXTO_CLARO
            )
        ]

        if faixa_logos_streaming:
            elementos_coluna_card.append(faixa_logos_streaming)

        if acoes:
            elementos_coluna_card.append(
                ft.Row(acoes, spacing=3, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=largura_card - 10)
            )

        card_corpo = ft.Container(
            width=largura_card,
            bgcolor=COR_CARD,
            padding=5,
            border_radius=8,
            border=criar_borda(1.2, COR_BORDA),
            content=ft.Column(elementos_coluna_card, spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            on_click=lambda e, m=chave_id, mt=mtype_seguro, t=titulo, a=ano, p=poster_url: abrir_detalhes(m, mt, t, a, p, tela_atual="home" if categoria is None else "biblioteca")
        )
        return card_corpo

    def carregar_mais_busca():
        if paginacao["carregando"] or paginacao["fim"]:
            return

        paginacao["carregando"] = True
        spinner_carregamento.visible = True
        spinner_carregamento.update()

        f_tipo = paginacao["filtro_home"]
        todos_itens = contexto_busca.get("itens_cache", [])
        
        if f_tipo == "movie":
            filtrados = [i for i in todos_itens if i.get("media_type") == "movie"]
        elif f_tipo == "tv":
            filtrados = [i for i in todos_itens if i.get("media_type") == "tv"]
        else:
            filtrados = todos_itens

        offset = contexto_busca.get("offset", 0)
        proxima_fatia = filtrados[offset : offset + 16]

        if not proxima_fatia:
            paginacao["fim"] = True
            btn_carregar_mais.visible = False
            paginacao["carregando"] = False
            spinner_carregamento.visible = False
            page.update()
            return

        novos_cards = [
            criar_card_filme(
                it.get("id"),
                it.get("media_type", "movie"),
                it.get("title") or it.get("name") or "Sem título",
                str((it.get("release_date") or it.get("first_air_date")) or "")[:4],
                f"https://image.tmdb.org/t/p/w185{it.get('poster_path')}"
            )
            for it in proxima_fatia
        ]

        contexto_busca["offset"] = offset + len(proxima_fatia)
        grade_populares.controls.extend(novos_cards)

        paginacao["fim"] = (contexto_busca["offset"] >= len(filtrados))
        btn_carregar_mais.visible = not paginacao["fim"]
        paginacao["carregando"] = False
        spinner_carregamento.visible = False
        page.update()

    def acao_carregar_mais(e):
        if paginacao["modo_busca_ativo"]:
            carregar_mais_busca()
        else:
            carregar_populares(incrementar=True)

    btn_carregar_mais = ft.Button(
        content=ft.Text("Carregar Mais Títulos", size=12, weight="bold", color=COR_TEXTO_CLARO),
        bgcolor=COR_CARD,
        height=38,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), side=ft.BorderSide(1, COR_BORDA)),
        on_click=acao_carregar_mais
    )

    def renderizar_itens_busca_contexto():
        f_tipo = paginacao["filtro_home"]
        todos_itens = contexto_busca.get("itens_cache", [])
        
        if f_tipo == "movie":
            filtrados = [i for i in todos_itens if i.get("media_type") == "movie"]
        elif f_tipo == "tv":
            filtrados = [i for i in todos_itens if i.get("media_type") == "tv"]
        else:
            filtrados = todos_itens

        grade_populares.controls.clear()
        botoes_add_home.clear()
        contexto_busca["offset"] = 0
        paginacao["fim"] = False

        if not filtrados:
            rotulo = "séries" if f_tipo == "tv" else ("filmes" if f_tipo == "movie" else "obras")
            grade_populares.controls.append(
                ft.Container(
                    content=ft.Text(f"Nenhuma {rotulo} encontrada com o termo '{contexto_busca.get('nome')}'.", size=14, color="#94a3b8", text_align=ft.TextAlign.CENTER),
                    padding=40
                )
            )
            btn_carregar_mais.visible = False
            page.update()
            return

        primeira_fatia = filtrados[:16]
        contexto_busca["offset"] = len(primeira_fatia)

        cards = [
            criar_card_filme(
                it.get("id"),
                it.get("media_type", "movie"),
                it.get("title") or it.get("name") or "Sem título",
                str((it.get("release_date") or it.get("first_air_date")) or "")[:4],
                f"https://image.tmdb.org/t/p/w185{it.get('poster_path')}"
            )
            for it in primeira_fatia
        ]

        grade_populares.controls.extend(cards)
        paginacao["fim"] = (len(filtrados) <= 16)
        btn_carregar_mais.visible = not paginacao["fim"]
        page.update()

    def carregar_populares(incrementar=False):
        c = carregar_config()
        tmdb_key = c.get("tmdb_key", "").strip()

        if not tmdb_key:
            grade_populares.controls.clear()
            grade_populares.controls.append(
                ft.Container(content=ft.Text("⚠️ Chave do TMDb ausente. Adicione TMDB_KEY no Render ou config.json.", color="#f87171", size=13, text_align=ft.TextAlign.CENTER), padding=20)
            )
            grade_populares.update()
            return

        if paginacao["carregando"] or paginacao["fim"] or paginacao["modo_busca_ativo"]:
            return

        paginacao["carregando"] = True
        if incrementar:
            paginacao["pagina_atual"] += 1

        spinner_carregamento.visible = True
        btn_carregar_mais.visible = False
        spinner_carregamento.update()
        btn_carregar_mais.update()

        def _fetch():
            try:
                p = paginacao["pagina_atual"]
                f_home = paginacao["filtro_home"]

                if f_home == "movie":
                    url = f"https://api.themoviedb.org/3/trending/movie/week?api_key={tmdb_key}&language=pt-BR&page={p}"
                elif f_home == "tv":
                    url = f"https://api.themoviedb.org/3/trending/tv/week?api_key={tmdb_key}&language=pt-BR&page={p}"
                else:
                    url = f"https://api.themoviedb.org/3/trending/all/week?api_key={tmdb_key}&language=pt-BR&page={p}"

                resp = requests.get(url, timeout=4.0)

                if resp.status_code == 200:
                    dados = resp.json()
                    itens = dados.get("results", [])
                    total_pages = dados.get("total_pages", 1000)

                    if not itens or p >= total_pages:
                        paginacao["fim"] = True

                    novos = []
                    for it in itens:
                        mid = it.get("id")
                        if f_home == "tv":
                            media_t = "tv"
                        elif f_home == "movie":
                            media_t = "movie"
                        else:
                            media_t = it.get("media_type") or ("tv" if "name" in it else "movie")

                        if not it.get("poster_path"):
                            continue

                        chave_unicidade = f"{media_t}_{mid}"
                        if chave_unicidade in paginacao["ids_carregados"]:
                            continue
                        paginacao["ids_carregados"].add(chave_unicidade)

                        tit = it.get("title") or it.get("name") or "Sem título"
                        ano = str((it.get("release_date") or it.get("first_air_date")) or "")[:4]
                        p_path = it.get("poster_path")
                        p_url = f"https://image.tmdb.org/t/p/w185{p_path}" if p_path else None
                        novos.append(criar_card_filme(mid, media_t, tit, ano, p_url))

                    grade_populares.controls.extend(novos)
            except Exception as e:
                print(f"Erro ao buscar populares: {e}")
            finally:
                paginacao["carregando"] = False
                spinner_carregamento.visible = False
                btn_carregar_mais.visible = not paginacao["fim"]
                page.update()

        threading.Thread(target=_fetch, daemon=True).start()

    def alternar_filtro_home(novo_filtro):
        paginacao["carregando"] = False
        paginacao["filtro_home"] = novo_filtro
        atualizar_botoes_filtro_home()

        if paginacao["modo_busca_ativo"] and contexto_busca.get("tipo"):
            renderizar_itens_busca_contexto()
            return

        paginacao["pagina_atual"] = 1
        paginacao["fim"] = False
        paginacao["ids_carregados"].clear()
        botoes_add_home.clear()
        grade_populares.controls.clear()
        txt_titulo_home.value = "Em Alta (TMDb Trends)"
        page.update()
        carregar_populares()

    def atualizar_botoes_filtro_home():
        atual = paginacao["filtro_home"]
        
        btn_home_todos.bgcolor = COR_PETROLEO if atual == "todos" else COR_CARD
        btn_home_todos.content.color = "white" if atual == "todos" else "#94a3b8"
        btn_home_todos.style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=20),
            side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if atual == "todos" else ft.BorderSide(1, COR_BORDA)
        )

        btn_home_filmes.bgcolor = COR_PETROLEO if atual == "movie" else COR_CARD
        btn_home_filmes.content.color = "white" if atual == "movie" else "#94a3b8"
        btn_home_filmes.style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=20),
            side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if paginacao["filtro_home"] == "movie" else ft.BorderSide(1, COR_BORDA)
        )

        btn_home_series.bgcolor = COR_PETROLEO if atual == "tv" else COR_CARD
        btn_home_series.content.color = "white" if atual == "tv" else "#94a3b8"
        btn_home_series.style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=20),
            side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if paginacao["filtro_home"] == "tv" else ft.BorderSide(1, COR_BORDA)
        )
        linha_controles_unificados.update()

    btn_home_todos = ft.Button(
        content=ft.Text("Todos", size=11, weight="bold", color="white"),
        bgcolor=COR_PETROLEO,
        height=32,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=20), side=ft.BorderSide(1.8, COR_ATIVO_BORDA)),
        on_click=lambda e: alternar_filtro_home("todos")
    )
    btn_home_filmes = ft.Button(
        content=ft.Text("🎬 Filmes", size=11, weight="bold", color="#94a3b8"),
        bgcolor=COR_CARD,
        height=32,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=20), side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if paginacao["filtro_home"] == "movie" else ft.BorderSide(1, COR_BORDA)),
        on_click=lambda e: alternar_filtro_home("movie")
    )
    btn_home_series = ft.Button(
        content=ft.Text("📺 Séries", size=11, weight="bold", color="#94a3b8"),
        bgcolor=COR_CARD,
        height=32,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=20), side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if paginacao["filtro_home"] == "tv" else ft.BorderSide(1, COR_BORDA)),
        on_click=lambda e: alternar_filtro_home("tv")
    )

    btn_tab_bib = ft.Container(
        content=txt_contador_bib,
        bgcolor=COR_CARD,
        border=criar_borda(1.2, COR_BORDA),
        border_radius=10,
        padding=ft.Padding(12, 8, 12, 8),
        on_click=lambda e: alternar_tela(1)
    )

    linha_controles_unificados = ft.Row(
        controls=[btn_home_todos, btn_home_filmes, btn_home_series, btn_tab_bib],
        spacing=8,
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        wrap=True
    )

    # -------------------------------------------------------------
    # FUNÇÕES DE BUSCA E AUTOCOMPLETE
    # -------------------------------------------------------------
    def exibir_filmografia_pessoa(person_id, nome_pessoa):
        ocultar_sugestoes()
        campo_busca.value = nome_pessoa
        paginacao["modo_busca_ativo"] = True
        paginacao["fim"] = False
        btn_carregar_mais.visible = False
        grade_populares.controls.clear()
        botoes_add_home.clear()
        
        contexto_busca["tipo"] = "person"
        contexto_busca["id"] = person_id
        contexto_busca["nome"] = nome_pessoa
        contexto_busca["itens_cache"] = []
        contexto_busca["offset"] = 0
        
        txt_titulo_home.value = nome_pessoa
        alternar_tela(0)
        progresso.visible = True
        page.update()

        c = carregar_config()
        tmdb_key = c.get("tmdb_key", "").strip()

        def _fetch():
            try:
                url = f"https://api.themoviedb.org/3/person/{person_id}/combined_credits?api_key={tmdb_key}&language=pt-BR"
                res = requests.get(url, timeout=4.5).json()
                
                cast_puro = res.get("cast", [])
                crew_puro = res.get("crew", [])
                
                itens_filtrados = []
                vistos = set()

                for item in cast_puro:
                    mid = item.get("id")
                    if not mid or not item.get("poster_path"):
                        continue
                    
                    personagem = (item.get("character") or "").lower().strip()
                    generos = item.get("genre_ids", [])
                    
                    if 99 in generos or "self" in personagem or "himself" in personagem or "herself" in personagem:
                        continue
                        
                    mtype = "tv" if (item.get("media_type") == "tv" or "name" in item or "first_air_date" in item) else "movie"
                    item["media_type"] = mtype
                    
                    chave = f"{mtype}_{mid}"
                    if chave not in vistos:
                        vistos.add(chave)
                        itens_filtrados.append(item)

                for item in crew_puro:
                    mid = item.get("id")
                    if not mid or not item.get("poster_path"):
                        continue
                        
                    job = (item.get("job") or "").lower().strip()
                    generos = item.get("genre_ids", [])
                    
                    if job in ["director", "creator", "writer"]:
                        if 99 in generos:
                            continue
                            
                        mtype = "tv" if (item.get("media_type") == "tv" or "name" in item or "first_air_date" in item) else "movie"
                        item["media_type"] = mtype
                        
                        chave = f"{mtype}_{mid}"
                        if chave not in vistos:
                            vistos.add(chave)
                            itens_filtrados.append(item)

                contexto_busca["itens_cache"] = sorted(
                    itens_filtrados,
                    key=lambda x: (x.get("vote_count", 0), x.get("popularity", 0)),
                    reverse=True
                )
            except Exception as ex:
                print(f"Erro filmografia filtrada: {ex}")
            finally:
                progresso.visible = False
                renderizar_itens_busca_contexto()

        threading.Thread(target=_fetch, daemon=True).start()

    def processar_itens_busca(lista_bruta, vistos, itens_saida, mtype_padrao=None, min_votos=0):
        for item in lista_bruta:
            if not item.get("poster_path"):
                continue
            if min_votos and item.get("vote_count", 0) < min_votos:
                continue

            mtype = mtype_padrao or item.get("media_type")
            if mtype not in ["movie", "tv"]:
                mtype = "tv" if ("name" in item or "first_air_date" in item) else "movie"
            item["media_type"] = mtype

            chave = f"{mtype}_{item.get('id')}"
            if chave not in vistos:
                vistos.add(chave)
                itens_saida.append(item)

    def executar_pesquisa_tema_ou_termo(termo_busca):
        ocultar_sugestoes()
        termo_limpo = termo_busca.strip()
        if not termo_limpo:
            return

        campo_busca.value = termo_limpo
        paginacao["modo_busca_ativo"] = True
        paginacao["fim"] = False
        btn_carregar_mais.visible = False
        grade_populares.controls.clear()
        botoes_add_home.clear()
        
        contexto_busca["tipo"] = "tema"
        contexto_busca["id"] = termo_limpo
        contexto_busca["nome"] = termo_limpo
        contexto_busca["itens_cache"] = []
        contexto_busca["offset"] = 0
        
        txt_titulo_home.value = termo_limpo.title()
        alternar_tela(0)
        progresso.visible = True
        page.update()

        c = carregar_config()
        tmdb_key = c.get("tmdb_key", "").strip()

        def _fetch():
            try:
                norm = normalizar_texto(termo_limpo)
                itens_totais = []
                vistos = set()

                genero_id = MAPA_GENEROS_TMDB.get(norm)
                if genero_id:
                    for pg in [1, 2, 3]:
                        try:
                            url_m = f"https://api.themoviedb.org/3/discover/movie?api_key={tmdb_key}&language=pt-BR&sort_by=vote_count.desc&with_genres={genero_id}&vote_count.gte=30&page={pg}"
                            res_m = requests.get(url_m, timeout=3.5).json().get("results", [])
                            processar_itens_busca(res_m, vistos, itens_totais, mtype_padrao="movie")
                        except Exception:
                            pass
                    for pg in [1, 2]:
                        try:
                            url_t = f"https://api.themoviedb.org/3/discover/tv?api_key={tmdb_key}&language=pt-BR&sort_by=vote_count.desc&with_genres={genero_id}&vote_count.gte=10&page={pg}"
                            res_t = requests.get(url_t, timeout=3.5).json().get("results", [])
                            processar_itens_busca(res_t, vistos, itens_totais, mtype_padrao="tv")
                        except Exception:
                            pass

                lang_code = MAPA_PAISES_TMDB.get(norm)
                if not lang_code:
                    for k_pais, cod in MAPA_PAISES_TMDB.items():
                        if k_pais in norm:
                            lang_code = cod
                            break

                if lang_code:
                    param_extra = "&with_origin_country=BR" if lang_code == "pt" and norm in ["brasil", "brasileiro", "brasileiros", "brasileira", "nacional"] else ""
                    for pg in [1, 2, 3]:
                        try:
                            url_m = f"https://api.themoviedb.org/3/discover/movie?api_key={tmdb_key}&language=pt-BR&sort_by=vote_count.desc&with_original_language={lang_code}{param_extra}&page={pg}"
                            res_m = requests.get(url_m, timeout=3.5).json().get("results", [])
                            processar_itens_busca(res_m, vistos, itens_totais, mtype_padrao="movie")
                        except Exception:
                            pass
                    for pg in [1, 2]:
                        try:
                            url_t = f"https://api.themoviedb.org/3/discover/tv?api_key={tmdb_key}&language=pt-BR&sort_by=vote_count.desc&with_original_language={lang_code}{param_extra}&page={pg}"
                            res_t = requests.get(url_t, timeout=3.5).json().get("results", [])
                            processar_itens_busca(res_t, vistos, itens_totais, mtype_padrao="tv")
                        except Exception:
                            pass

                kw_ids_str = ""
                if not genero_id and not lang_code:
                    for termo_k, ids_v in MAPA_KEYWORDS_CONHECIDAS.items():
                        if termo_k in norm:
                            kw_ids_str = ids_v
                            break

                if kw_ids_str:
                    for pg in [1, 2, 3]:
                        try:
                            url_m = f"https://api.themoviedb.org/3/discover/movie?api_key={tmdb_key}&language=pt-BR&sort_by=vote_count.desc&with_keywords={kw_ids_str}&vote_count.gte=30&page={pg}"
                            res_m = requests.get(url_m, timeout=3.5).json().get("results", [])
                            processar_itens_busca(res_m, vistos, itens_totais, mtype_padrao="movie")
                        except Exception:
                            pass
                    for pg in [1, 2]:
                        try:
                            url_t = f"https://api.themoviedb.org/3/discover/tv?api_key={tmdb_key}&language=pt-BR&sort_by=vote_count.desc&with_keywords={kw_ids_str}&vote_count.gte=10&page={pg}"
                            res_t = requests.get(url_t, timeout=3.5).json().get("results", [])
                            processar_itens_busca(res_t, vistos, itens_totais, mtype_padrao="tv")
                        except Exception:
                            pass

                if not genero_id and not lang_code:
                    for pg in [1, 2]:
                        try:
                            url_multi_pt = f"https://api.themoviedb.org/3/search/multi?api_key={tmdb_key}&query={quote_plus(termo_limpo)}&language=pt-BR&include_adult=false&page={pg}"
                            res_multi_pt = requests.get(url_multi_pt, timeout=3.0).json().get("results", [])
                            processar_itens_busca(res_multi_pt, vistos, itens_totais, min_votos=5)
                        except Exception:
                            pass
                    
                    for pg in [1, 2]:
                        try:
                            url_multi_orig = f"https://api.themoviedb.org/3/search/multi?api_key={tmdb_key}&query={quote_plus(termo_limpo)}&include_adult=false&page={pg}"
                            res_multi_orig = requests.get(url_multi_orig, timeout=3.0).json().get("results", [])
                            processar_itens_busca(res_multi_orig, vistos, itens_totais, min_votos=5)
                        except Exception:
                            pass

                contexto_busca["itens_cache"] = sorted(itens_totais, key=lambda x: x.get("vote_count", 0), reverse=True)
            except Exception as ex:
                print(f"Erro pesquisa tema/nacionalidade: {ex}")
            finally:
                progresso.visible = False
                renderizar_itens_busca_contexto()

        threading.Thread(target=_fetch, daemon=True).start()

    def selecionar_sugestao_filme(mid, mtype, tit, ano, p_url):
        ocultar_sugestoes()
        campo_busca.value = tit
        campo_busca.update()
        abrir_detalhes(mid, mtype, tit, ano, p_url, tela_atual="home")

    def buscar_sugestoes_api(termo, epoch_disparo):
        if epoch_disparo != versao_busca_atual["epoch"]:
            return

        c = carregar_config()
        tmdb_key = c.get("tmdb_key", "").strip()
        termo_limpo = termo.strip()
        if not tmdb_key or len(termo_limpo) < 2:
            primeira_acao_sugestao["callback"] = None
            ocultar_sugestoes()
            return

        try:
            url_multi = "https://api.themoviedb.org/3/search/multi"
            params_multi = {"api_key": tmdb_key, "query": termo_limpo, "language": "pt-BR", "include_adult": "false"}
            resp_multi = requests.get(url_multi, params=params_multi, timeout=3.0)
            
            if epoch_disparo != versao_busca_atual["epoch"]:
                return

            itens_multi = resp_multi.json().get("results", []) if resp_multi.status_code == 200 else []

            coluna_sugestoes.controls.clear()
            primeira_acao_sugestao["callback"] = None

            pessoas = [i for i in itens_multi if i.get("media_type") == "person"][:2]
            for p in pessoas:
                pid = p.get("id")
                pnome = p.get("name") or "Artista"
                dept = p.get("known_for_department") or "Atuação"
                dept_traduzido = "Direção" if dept == "Directing" else "Ator/Atriz"
                pic = p.get("profile_path")
                pic_url = f"https://image.tmdb.org/t/p/w185{pic}" if pic else None

                if primeira_acao_sugestao["callback"] is None:
                    primeira_acao_sugestao["callback"] = lambda id_p=pid, nome_p=pnome: exibir_filmografia_pessoa(id_p, nome_p)

                linha_p = ft.Container(
                    padding=6,
                    border_radius=6,
                    bgcolor="#1e293b",
                    on_click=lambda e, person_id=pid, name=pnome: exibir_filmografia_pessoa(person_id, name),
                    content=ft.Row([
                        ft.Image(src=pic_url if pic_url else "https://via.placeholder.com/32x46?text=👤", width=32, height=46, border_radius=4, fit="cover"),
                        ft.Column([
                            ft.Text(pnome, size=12, weight="bold", color="white", max_lines=1, overflow="ellipsis"),
                            ft.Text(f"👤 {dept_traduzido} • Filmografia", size=10, color="#38bdf8")
                        ], spacing=2, expand=True)
                    ], spacing=8)
                )
                coluna_sugestoes.controls.append(linha_p)

            obras = [i for i in itens_multi if i.get("media_type") in ["movie", "tv"] and i.get("poster_path")][:4]
            for item in obras:
                mtype = item.get("media_type", "movie")
                mid = item.get("id")
                tit = item.get("title") or item.get("name") or "Sem título"
                ano = str((item.get("release_date") or item.get("first_air_date")) or "")[:4]
                p_path = item.get("poster_path")
                p_url = f"https://image.tmdb.org/t/p/w185{p_path}" if p_path else None

                if primeira_acao_sugestao["callback"] is None:
                    primeira_acao_sugestao["callback"] = lambda m=mid, mt=mtype, t=tit, a=ano, p=p_url: selecionar_sugestao_filme(m, mt, t, a, p)

                linha_item = ft.Container(
                    padding=6,
                    border_radius=6,
                    bgcolor=COR_CARD,
                    on_click=lambda e, m=mid, mt=mtype, t=tit, a=ano, p=p_url: selecionar_sugestao_filme(m, mt, t, a, p),
                    content=ft.Row([
                        ft.Image(src=p_url if p_url else "https://via.placeholder.com/40x60?text=-", width=32, height=46, border_radius=4, fit="cover"),
                        ft.Column([
                            ft.Text(tit, size=12, weight="bold", color="white", max_lines=1, overflow="ellipsis"),
                            ft.Text(f"{ano} • {'Série' if mtype == 'tv' else 'Filme'}", size=10, color="#94a3b8")
                        ], spacing=2, expand=True)
                    ], spacing=8)
                )
                coluna_sugestoes.controls.append(linha_item)

            linha_tema_universal = ft.Container(
                padding=8,
                border_radius=6,
                bgcolor="#164e63",
                on_click=lambda e, t=termo_limpo: executar_pesquisa_tema_ou_termo(t),
                content=ft.Row([
                    ft.Icon(ft.Icons.SEARCH, size=18, color="#38bdf8"),
                    ft.Column([
                        ft.Text(f'Ver catálogo sobre "{termo_limpo}"', size=12, weight="bold", color="white", max_lines=1, overflow="ellipsis"),
                        ft.Text("🏷️ Gênero, nacionalidade ou tema", size=10, color="#7dd3fc")
                    ], spacing=2, expand=True)
                ], spacing=8)
            )
            coluna_sugestoes.controls.append(linha_tema_universal)

            if primeira_acao_sugestao["callback"] is None:
                primeira_acao_sugestao["callback"] = lambda t=termo_limpo: executar_pesquisa_tema_ou_termo(t)

            if len(coluna_sugestoes.controls) > 0 and epoch_disparo == versao_busca_atual["epoch"]:
                largura_atual = page.width if page.width else 1000
                container_sugestoes.visible = True
                if largura_atual < 720:
                    container_sugestoes.width = min(int(largura_atual * 0.90), 380)
                    container_sugestoes.left = max(10, int((largura_atual - container_sugestoes.width) / 2))
                    container_sugestoes.top = 165
                else:
                    container_sugestoes.width = 320
                    container_sugestoes.left = max(0, int((largura_atual / 2) - 160))
                    container_sugestoes.top = 165
            else:
                ocultar_sugestoes()

            container_sugestoes.update()
        except Exception as ex:
            print(f"Erro busca expandida: {ex}")

    def disparar_busca_manual(e=None):
        if primeira_acao_sugestao["callback"]:
            cb = primeira_acao_sugestao["callback"]
            ocultar_sugestoes()
            cb()
        else:
            termo = campo_busca.value
            if termo and len(termo.strip()) >= 2:
                executar_pesquisa_tema_ou_termo(termo)

    def ao_digitar_busca(e):
        termo = campo_busca.value
        versao_busca_atual["epoch"] += 1
        epoch_deste_disparo = versao_busca_atual["epoch"]

        if timer_busca["timer"]:
            timer_busca["timer"].cancel()

        if not termo or len(termo.strip()) < 2:
            primeira_acao_sugestao["callback"] = None
            ocultar_sugestoes()
            return

        t = threading.Timer(0.3, buscar_sugestoes_api, args=[termo, epoch_deste_disparo])
        timer_busca["timer"] = t
        t.start()

    campo_busca.suffix = ft.IconButton(
        icon=ft.Icons.SEARCH,
        icon_color="#64748b",
        icon_size=18,
        tooltip="Buscar primeira sugestão",
        on_click=disparar_busca_manual
    )
    campo_busca.on_change = ao_digitar_busca
    campo_busca.on_submit = disparar_busca_manual

    def clicar_no_logo(e):
        campo_busca.value = ""
        paginacao["modo_busca_ativo"] = False
        contexto_busca["tipo"] = None
        contexto_busca["id"] = None
        contexto_busca["nome"] = ""
        contexto_busca["itens_cache"] = []
        contexto_busca["offset"] = 0
        
        txt_titulo_home.value = "Em Alta (TMDb Trends)"
        btn_carregar_mais.visible = True
        alternar_tela(0)
        alternar_filtro_home("todos")

    img_logo = ft.Image(src="logo.png", height=65, fit="contain")
    btn_logo_interativo = ft.Container(content=img_logo, padding=2, tooltip="Voltar ao Início", on_click=clicar_no_logo)

    lbl_user_tag = ft.Text("", size=12, color="#64748b", weight="bold")

    def acao_trocar_perfil(e):
        sessao_usuario["id"] = None
        sessao_usuario["username"] = ""
        ids_salvos_usuario.clear()
        titulos_salvos_usuario.clear()
        botoes_add_home.clear()
        
        campo_busca.value = ""
        paginacao["pagina_atual"] = 1
        paginacao["carregando"] = False
        paginacao["fim"] = False
        paginacao["filtro_home"] = "todos"
        paginacao["modo_busca_ativo"] = False
        paginacao["ids_carregados"].clear()
        
        contexto_busca["tipo"] = None
        contexto_busca["id"] = None
        contexto_busca["nome"] = ""
        contexto_busca["itens_cache"] = []
        contexto_busca["offset"] = 0
        
        grade_populares.controls.clear()
        layout_mestre.visible = False
        carregar_perfis_tela()
        tela_perfis.visible = True
        page.update()

    btn_trocar_perfil = ft.IconButton(
        icon=ft.Icons.SWITCH_ACCOUNT_ROUNDED,
        icon_color=COR_TEXTO_CLARO,
        icon_size=20,
        tooltip="Trocar Perfil",
        on_click=acao_trocar_perfil
    )

    bloco_usuario_topo = ft.Row(
        controls=[lbl_user_tag, btn_trocar_perfil],
        spacing=4,
        alignment=ft.MainAxisAlignment.END,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )

    container_input_busca = ft.Container(
        content=ft.Row(controls=[campo_busca], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        width=320
    )

    coluna_conteudo_cabecalho = ft.Column(
        controls=[
            progresso,
            bloco_usuario_topo,
            ft.Row([btn_logo_interativo], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([container_input_busca], alignment=ft.MainAxisAlignment.CENTER),
            linha_controles_unificados
        ],
        spacing=6,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    cabecalho_fixo = ft.Container(
        bgcolor=COR_FUNDO,
        padding=ft.Padding(12, 4, 12, 8),
        border=ft.Border(bottom=ft.BorderSide(1, COR_BORDA)),
        content=coluna_conteudo_cabecalho
    )

    def ajustar_layout_responsivo(e=None):
        mobile = eh_mobile()
        largura_janela = page.width if page.width else 1000
        na_biblioteca = (tela_ativa_atual["indice"] == 1)

        if mobile:
            img_logo.height = 80 if na_biblioteca else 60
            container_input_busca.width = min(int(largura_janela * 0.92), 380)
            titulo_trends.width = None
            grade_populares.spacing = 8
            grade_populares.run_spacing = 10
        else:
            img_logo.height = 92 if na_biblioteca else 68
            container_input_busca.width = 340
            titulo_trends.width = 1100
            grade_populares.spacing = 12
            grade_populares.run_spacing = 14
        page.update()

    page.on_resized = ajustar_layout_responsivo

    txt_titulo_home = ft.Text("Em Alta (TMDb Trends)", size=15, weight="bold", color=COR_TEXTO_CLARO)

    titulo_trends = ft.Container(
        content=ft.Row([txt_titulo_home], alignment=ft.MainAxisAlignment.START),
        width=1100,
        padding=ft.Padding(0, 8, 0, 0)
    )

    bloco_carregamento_fim = ft.Column(
        controls=[spinner_carregamento, btn_carregar_mais],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=8
    )

    view_inicio = ft.Container(
        expand=True,
        padding=ft.Padding(8, 0, 8, 10),
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[
                titulo_trends,
                grade_populares,
                ft.Container(content=bloco_carregamento_fim, alignment=ft.Alignment(0, 0), padding=ft.Padding(0, 15, 0, 40))
            ]
        )
    )

    view_biblioteca = ft.Container(
        expand=True,
        visible=False,
        padding=ft.Padding(8, 10, 8, 10),
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[coluna_biblioteca_itens]
        )
    )

    def alternar_tela(indice):
        ocultar_sugestoes()
        tela_ativa_atual["indice"] = indice

        if indice == 0:
            view_inicio.visible = True
            view_biblioteca.visible = False
            linha_controles_unificados.visible = True
            container_input_busca.visible = True
            btn_tab_bib.border = criar_borda(1.2, COR_BORDA)
        elif indice == 1:
            carregar_biblioteca()
            view_inicio.visible = False
            view_biblioteca.visible = True
            linha_controles_unificados.visible = False
            container_input_busca.visible = False
            btn_tab_bib.border = criar_borda(2, COR_ATIVO_BORDA)

        ajustar_layout_responsivo()
        page.update()

    layout_mestre = ft.Column(
        expand=True,
        spacing=0,
        visible=False,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            cabecalho_fixo,
            view_inicio,
            view_biblioteca
        ]
    )

    linha_cards_perfis = ft.Row(
        wrap=True,
        spacing=24,
        run_spacing=24,
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )

    def entrar_com_perfil(uid, nome, cor):
        sessao_usuario["id"] = int(uid)
        sessao_usuario["username"] = str(nome)
        sessao_usuario["cor"] = cor
        lbl_user_tag.value = f"👤 {nome}"
        
        recarregar_ids_salvos()
        tela_perfis.visible = False
        layout_mestre.visible = True
        ajustar_layout_responsivo()
        atualizar_contador_biblioteca()

        paginacao["pagina_atual"] = 1
        paginacao["carregando"] = False
        paginacao["fim"] = False
        paginacao["filtro_home"] = "todos"
        paginacao["modo_busca_ativo"] = False
        paginacao["ids_carregados"].clear()
        botoes_add_home.clear()
        
        contexto_busca["tipo"] = None
        contexto_busca["id"] = None
        contexto_busca["nome"] = ""
        contexto_busca["itens_cache"] = []
        contexto_busca["offset"] = 0
        
        grade_populares.controls.clear()
        page.update()
        carregar_populares()

    txt_novo_perfil_nome = ft.TextField(
        label="Nome do Perfil",
        label_style=ft.TextStyle(color="#94a3b8"),
        bgcolor=COR_FUNDO,
        dense=True,
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        width=280,
        autofocus=True
    )
    txt_novo_perfil_pin = ft.TextField(
        label="Senha/PIN (Opcional)",
        label_style=ft.TextStyle(color="#94a3b8"),
        hint_text="Ex: 1234 (Deixe vazio para sem senha)",
        hint_style=ft.TextStyle(size=11, color="#64748b"),
        password=True,
        can_reveal_password=True,
        bgcolor=COR_FUNDO,
        dense=True,
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        width=280
    )
    txt_novo_perfil_erro = ft.Text("", size=12, color="#ef4444")

    modal_novo_perfil = ft.AlertDialog(modal=False, actions_alignment=ft.MainAxisAlignment.END)

    def fechar_modal_novo_perfil(e=None):
        modal_novo_perfil.open = False
        page.update()

    def acao_salvar_novo_perfil(e):
        nome = txt_novo_perfil_nome.value.strip() if txt_novo_perfil_nome.value else ""
        pin = txt_novo_perfil_pin.value.strip() if txt_novo_perfil_pin.value else ""
        if len(nome) < 2:
            txt_novo_perfil_erro.value = "Digite pelo menos 2 caracteres."
            modal_novo_perfil.update()
            return

        conn = None
        try:
            conn = obter_conexao()
            c = conn.cursor()
            query_sel = "SELECT id FROM usuarios WHERE username = %s" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "SELECT id FROM usuarios WHERE username = ?"
            c.execute(query_sel, (nome,))
            if c.fetchone():
                txt_novo_perfil_erro.value = "Este perfil já existe."
                modal_novo_perfil.update()
                return

            c.execute("SELECT COUNT(*) FROM usuarios")
            qtd = c.fetchone()[0]
            cor_escolhida = CORES_AVATAR[qtd % len(CORES_AVATAR)]

            query_ins = "INSERT INTO usuarios (username, cor_avatar, pin) VALUES (%s, %s, %s)" if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES) else "INSERT INTO usuarios (username, cor_avatar, pin) VALUES (?, ?, ?)"
            c.execute(query_ins, (nome, cor_escolhida, pin))
            
            if bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES):
                c.execute("SELECT id FROM usuarios WHERE username = %s", (nome,))
                novo_id = c.fetchone()[0]
            else:
                novo_id = c.lastrowid
                
            conn.commit()

            fechar_modal_novo_perfil()
            entrar_com_perfil(novo_id, nome, cor_escolhida)
        except Exception as err:
            txt_novo_perfil_erro.value = f"Erro: {err}"
            modal_novo_perfil.update()
        finally:
            if conn:
                conn.close()

    txt_novo_perfil_nome.on_submit = acao_salvar_novo_perfil
    txt_novo_perfil_pin.on_submit = acao_salvar_novo_perfil

    modal_novo_perfil.title = ft.Text("Adicionar Novo Perfil", size=16, weight="bold", color="white")
    modal_novo_perfil.content = ft.Column([
        ft.Text("Defina o nome e a senha do perfil:", size=13, color="#94a3b8"),
        txt_novo_perfil_erro,
        txt_novo_perfil_nome,
        txt_novo_perfil_pin
    ], tight=True, spacing=10)
    modal_novo_perfil.actions = [
        ft.Button(content=ft.Text("Cancelar", color="#94a3b8"), on_click=fechar_modal_novo_perfil),
        ft.Button(content=ft.Text("Salvar Perfil", color="white"), bgcolor=COR_PETROLEO, on_click=acao_salvar_novo_perfil)
    ]

    def abrir_modal_novo_perfil(e=None):
        txt_novo_perfil_nome.value = ""
        txt_novo_perfil_pin.value = ""
        txt_novo_perfil_erro.value = ""
        abrir_dialogo(modal_novo_perfil)

    txt_acesso_pin = ft.TextField(
        label="Digite a Senha/PIN",
        password=True,
        can_reveal_password=True,
        bgcolor=COR_FUNDO,
        dense=True,
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        width=260,
        autofocus=True
    )
    txt_acesso_erro = ft.Text("", size=12, color="#ef4444")
    dados_perfil_pendente = {"id": None, "nome": "", "cor": "", "pin_correto": ""}

    modal_solicitar_pin = ft.AlertDialog(modal=False, actions_alignment=ft.MainAxisAlignment.END)

    def fechar_modal_pin(e=None):
        modal_solicitar_pin.open = False
        page.update()

    def verificar_pin_e_entrar(e=None):
        if txt_acesso_pin.value.strip() == dados_perfil_pendente["pin_correto"]:
            fechar_modal_pin()
            entrar_com_perfil(dados_perfil_pendente["id"], dados_perfil_pendente["nome"], dados_perfil_pendente["cor"])
        else:
            txt_acesso_erro.value = "Senha incorreta. Tente novamente."
            modal_solicitar_pin.update()

    txt_acesso_pin.on_submit = verificar_pin_e_entrar
    modal_solicitar_pin.title = ft.Text("Perfil Protegido", size=16, weight="bold", color="white")
    modal_solicitar_pin.content = ft.Column([
        txt_acesso_erro,
        txt_acesso_pin
    ], tight=True, spacing=10)
    modal_solicitar_pin.actions = [
        ft.Button(content=ft.Text("Cancelar", color="#94a3b8"), on_click=fechar_modal_pin),
        ft.Button(content=ft.Text("Entrar", color="white"), bgcolor=COR_PETROLEO, on_click=verificar_pin_e_entrar)
    ]

    def tentar_entrar_perfil(uid, nome, cor, pin):
        if pin and pin.strip():
            dados_perfil_pendente["id"] = uid
            dados_perfil_pendente["nome"] = nome
            dados_perfil_pendente["cor"] = cor
            dados_perfil_pendente["pin_correto"] = pin.strip()
            txt_acesso_pin.value = ""
            txt_acesso_erro.value = ""
            abrir_dialogo(modal_solicitar_pin)
        else:
            entrar_com_perfil(uid, nome, cor)

    perfil_a_excluir = {"id": None, "nome": "", "pin": ""}
    modal_confirmar_exclusao_perfil = ft.AlertDialog(modal=False, actions_alignment=ft.MainAxisAlignment.END)
    txt_exclusao_pin = ft.TextField(
        label="Senha do Perfil",
        password=True,
        can_reveal_password=True,
        bgcolor=COR_FUNDO,
        dense=True,
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        width=260
    )
    txt_exclusao_erro = ft.Text("", size=12, color="#ef4444")
    txt_aviso_exclusao = ft.Text("", size=13, color="#cbd5e1")

    def fechar_modal_exclusao_perfil(e=None):
        modal_confirmar_exclusao_perfil.open = False
        page.update()

    def confirmar_exclusao_perfil_banco(e=None):
        pid = perfil_a_excluir["id"]
        pin_esperado = perfil_a_excluir["pin"]
        
        if pin_esperado and pin_esperado.strip():
            if txt_exclusao_pin.value.strip() != pin_esperado.strip():
                txt_exclusao_erro.value = "Senha incorreta. Não foi possível excluir."
                modal_confirmar_exclusao_perfil.update()
                return

        if pid:
            conn = None
            try:
                conn = obter_conexao()
                c = conn.cursor()
                is_pg = bool(os.environ.get("DATABASE_URL") and HAS_POSTGRES)
                q_del_filmes = "DELETE FROM filmes WHERE usuario_id = %s" if is_pg else "DELETE FROM filmes WHERE usuario_id = ?"
                q_del_user = "DELETE FROM usuarios WHERE id = %s" if is_pg else "DELETE FROM usuarios WHERE id = ?"
                c.execute(q_del_filmes, (pid,))
                c.execute(q_del_user, (pid,))
                conn.commit()
            except Exception as ex:
                print(f"Erro ao excluir perfil: {ex}")
            finally:
                if conn:
                    conn.close()
            fechar_modal_exclusao_perfil()
            carregar_perfis_tela()
            page.update()

    txt_exclusao_pin.on_submit = confirmar_exclusao_perfil_banco

    modal_confirmar_exclusao_perfil.title = ft.Text("Excluir Perfil", size=16, weight="bold", color="#ef4444")
    modal_confirmar_exclusao_perfil.actions = [
        ft.Button(content=ft.Text("Cancelar", color="#94a3b8"), on_click=fechar_modal_exclusao_perfil),
        ft.Button(content=ft.Text("Sim, Excluir", color="white"), bgcolor=COR_VERMELHO_PLAY, on_click=confirmar_exclusao_perfil_banco)
    ]

    def pedir_exclusao_perfil(e, uid, nome, pin):
        perfil_a_excluir["id"] = uid
        perfil_a_excluir["nome"] = nome
        perfil_a_excluir["pin"] = pin
        txt_exclusao_pin.value = ""
        txt_exclusao_erro.value = ""
        
        tem_pin = bool(pin and pin.strip())
        txt_aviso_exclusao.value = f"Tem certeza de que deseja excluir '{nome}' e sua biblioteca?"
        
        elementos_conteudo = [txt_aviso_exclusao]
        if tem_pin:
            elementos_conteudo.extend([
                ft.Text("Este perfil é protegido. Digite a senha para confirmar:", size=12, color="#94a3b8"),
                txt_exclusao_erro,
                txt_exclusao_pin
            ])
            
        modal_confirmar_exclusao_perfil.content = ft.Column(elementos_conteudo, tight=True, spacing=10)
        abrir_dialogo(modal_confirmar_exclusao_perfil)

    def criar_card_avatar(uid, nome, cor, pin):
        iniciais = (nome[:2] if len(nome) >= 2 else nome).upper()
        
        btn_del_perfil = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
            icon_color="#ffffffb3",
            icon_size=15,
            width=26,
            height=26,
            top=4,
            right=4,
            bgcolor="#00000040",
            tooltip=f"Excluir perfil {nome}",
            on_click=lambda e, u=uid, n=nome, p=pin: pedir_exclusao_perfil(e, u, n, p)
        )

        badge_lock = None
        if pin and pin.strip():
            badge_lock = ft.Icon(ft.Icons.LOCK, size=14, color="#cbd5e1")

        box_avatar_clicavel = ft.Container(
            content=ft.Text(iniciais, size=28, weight="bold", color="white"),
            alignment=ft.Alignment(0, 0),
            width=110,
            height=110,
            border_radius=12,
            bgcolor=cor,
            border=criar_borda(2, "transparent"),
            on_click=lambda e, u=uid, n=nome, c=cor, p=pin: tentar_entrar_perfil(u, n, c, p)
        )

        stack_avatar = ft.Stack([
            box_avatar_clicavel,
            btn_del_perfil
        ])

        linha_nome = [ft.Text(nome, size=14, weight="bold", color="#94a3b8", text_align=ft.TextAlign.CENTER)]
        if badge_lock:
            linha_nome.append(badge_lock)

        return ft.Column([
            stack_avatar,
            ft.Row(linha_nome, spacing=4, alignment=ft.MainAxisAlignment.CENTER, width=110)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8)

    def criar_card_adicionar():
        box_add = ft.Container(
            content=ft.Icon(ft.Icons.ADD_ROUNDED, size=46, color="#64748b"),
            alignment=ft.Alignment(0, 0),
            width=110,
            height=110,
            border_radius=12,
            bgcolor="#0d1419",
            border=criar_borda(1.5, "#334155"),
            on_click=abrir_modal_novo_perfil
        )
        return ft.Column([
            box_add,
            ft.Text("Adicionar Perfil", size=13, color="#64748b", text_align=ft.TextAlign.CENTER, width=110)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8)

    def carregar_perfis_tela():
        linha_cards_perfis.controls.clear()
        perfis = []
        conn = None
        try:
            conn = obter_conexao()
            c = conn.cursor()
            c.execute("SELECT id, username, cor_avatar, pin FROM usuarios ORDER BY id ASC")
            perfis = c.fetchall()
        except Exception as e:
            print(f"Erro ao buscar perfis: {e}")
        finally:
            if conn:
                conn.close()

        for row in perfis:
            pid = row[0]
            pnome = row[1]
            pcor = row[2] if row[2] else COR_PETROLEO
            ppin = row[3] if len(row) > 3 and row[3] else ""
            linha_cards_perfis.controls.append(criar_card_avatar(pid, pnome, pcor, ppin))

        linha_cards_perfis.controls.append(criar_card_adicionar())

    tela_perfis = ft.Container(
        expand=True,
        alignment=ft.Alignment(0, 0),
        padding=ft.Padding(20, 40, 20, 40),
        content=ft.Column([
            ft.Image(src="logo.png", height=75, fit="contain"),
            ft.Container(height=10),
            ft.Text("Quem está usando?", size=26, weight="bold", color="white", text_align=ft.TextAlign.CENTER),
            ft.Container(height=15),
            linha_cards_perfis
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=12),
        visible=True
    )

    page.overlay.append(modal_novo_perfil)
    page.overlay.append(modal_solicitar_pin)
    page.overlay.append(modal_confirmar_exclusao_perfil)
    page.add(tela_perfis, layout_mestre)
    carregar_perfis_tela()
    ajustar_layout_responsivo()

    page.splash = None
    page.update()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 8550))
    ft.run(
        main,
        view=ft.AppView.WEB_BROWSER,
        host="0.0.0.0",
        port=porta,
        assets_dir=DIR_ASSETS
    )
