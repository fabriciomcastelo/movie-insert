import flet as ft
import sqlite3
import json
import os
import requests
import threading
import unicodedata
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
COR_ATIVO_BORDA = "#38bdf8"

CORES_AVATAR = [
    "#0284c7", "#0d9488", "#16a34a", "#ca8a04", 
    "#dc2626", "#9333ea", "#c026d3", "#4f46e5"
]

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
    "vampiros": "3133"
}

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
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE COLLATE NOCASE,
                cor_avatar TEXT DEFAULT '#03434d'
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
        try:
            c.execute("ALTER TABLE usuarios ADD COLUMN cor_avatar TEXT DEFAULT '#03434d'")
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

    sessao_usuario = {"id": None, "username": "", "cor": COR_PETROLEO}
    item_ativo = {"data": None}
    timer_busca = {"timer": None}
    versao_busca_atual = {"epoch": 0}
    filme_avaliando = {"id": None, "nota": "10"}
    filme_para_remover = {"id": None, "titulo": ""}
    
    botoes_add_home = {}
    ids_salvos_usuario = set()
    titulos_salvos_usuario = set()

    contexto_busca = {
        "tipo": None,
        "id": None,
        "nome": "",
        "itens_cache": [],
        "offset": 0
    }

    def recarregar_ids_salvos():
        ids_salvos_usuario.clear()
        titulos_salvos_usuario.clear()
        uid = sessao_usuario["id"]
        if uid:
            conn = None
            try:
                conn = sqlite3.connect(DB_FILE, timeout=5)
                c = conn.cursor()
                c.execute("SELECT id, titulo FROM filmes WHERE usuario_id = ?", (uid,))
                for row in c.fetchall():
                    ids_salvos_usuario.add(str(row[0]))
                    if row[1]:
                        titulos_salvos_usuario.add(normalizar_texto(row[1]))
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()

    def marcar_botao_home_como_salvo(chave_tmdb, chave_imdb=None):
        chaves = [chave_tmdb]
        if chave_imdb:
            chaves.append(chave_imdb)
        for k in chaves:
            if k in botoes_add_home and botoes_add_home[k]:
                btn = botoes_add_home[k]
                btn.icon = ft.Icons.CHECK
                btn.icon_color = "#10b981"
                btn.bgcolor = "#064e3b"
                btn.disabled = True
                btn.tooltip = "Já está na sua biblioteca"
        page.update()

    estado_biblioteca = {
        "aba": "Para Assistir",
        "modo": "streaming",
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
                conn = sqlite3.connect(DB_FILE, timeout=5)
                c = conn.cursor()
                c.execute("DELETE FROM filmes WHERE id = ? AND usuario_id = ?", (fid, uid))
                conn.commit()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()
            
            recarregar_ids_salvos()
            
            if fid in botoes_add_home and botoes_add_home[fid]:
                btn = botoes_add_home[fid]
                btn.icon = ft.Icons.ADD
                btn.icon_color = "white"
                btn.bgcolor = "#0d1419cc"
                btn.disabled = False
                btn.tooltip = "Adicionar à Biblioteca"

            fechar_dialogo(modal_confirmacao)
            atualizar_contador_biblioteca()
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
                conn = sqlite3.connect(DB_FILE, timeout=5)
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
    btn_salvar = ft.Button(content=ft.Text("+ Adicionar à Biblioteca", color="white", size=12), bgcolor=COR_PETROLEO, disabled=True)
    btn_ir_lista = ft.Button(content=ft.Text("📁 Ir para Biblioteca", color="white", size=12), bgcolor="#10b981", visible=False)

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

        fid = it["id"]
        chave_tmdb_orig = it.get("tmdb_orig_key")
        tipo_salvar = it.get("tipo", "movie")
        
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            c = conn.cursor()
            c.execute("SELECT categoria FROM filmes WHERE id = ? AND usuario_id = ?", (fid, uid))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO filmes (id, titulo, ano, diretor, elenco, sinopse, imdb, rotten, metascore, streaming, poster_url, categoria, nota_usuario, trailer_url, generos, usuario_id, tipo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Para Assistir', ?, ?, ?, ?, ?)
                """, (
                    fid, it["titulo"], it["ano"], it["diretor"], it["elenco"],
                    it["sinopse"], it["imdb"], it["rotten"], it.get("metascore", "N/A"),
                    it["streaming"], it["poster_url"], it.get("nota_usuario"),
                    it.get("trailer_url"), it.get("generos", ""), uid, tipo_salvar
                ))
                conn.commit()
                ids_salvos_usuario.add(fid)
                if it.get("titulo"):
                    titulos_salvos_usuario.add(normalizar_texto(it["titulo"]))
        except Exception as ex:
            print(f"Erro ao salvar: {ex}")
        finally:
            if conn:
                conn.close()

        it["categoria_existente"] = "Para Assistir"
        btn_salvar.content = ft.Text("✓ Na Biblioteca", color="white", size=12)
        btn_salvar.bgcolor = "#334155"
        btn_salvar.disabled = True
        btn_ir_lista.visible = True

        marcar_botao_home_como_salvo(chave_tmdb_orig, fid)
        atualizar_contador_biblioteca()
        page.update()

    btn_salvar.on_click = salvar_filme_ativo

    def abrir_detalhes(mid, mtype, titulo_prev, ano_prev, poster_prev, tela_atual="home"):
        ocultar_sugestoes()

        mtype_seguro = "tv" if mtype in ["tv", "series"] else "movie"
        chave_tmdb_calc = f"{mtype_seguro}_{mid}"

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
        
        if tela_atual == "biblioteca":
            btn_salvar.visible = False
            btn_ir_lista.visible = False
        else:
            ja_esta = (chave_tmdb_calc in ids_salvos_usuario) or (normalizar_texto(titulo_prev) in titulos_salvos_usuario)
            btn_salvar.visible = True
            btn_salvar.disabled = ja_esta
            btn_salvar.content = ft.Text("✓ Na Biblioteca" if ja_esta else "+ Adicionar à Biblioteca", color="white", size=12)
            btn_salvar.bgcolor = "#334155" if ja_esta else COR_PETROLEO
            btn_ir_lista.visible = ja_esta

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
                res = requests.get(url_tmdb, timeout=3.5).json()

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

                credits_data = res.get("credits", {})
                elenco_list = [a.get("name") for a in credits_data.get("cast", [])[:4]]
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
                        res_omdb = requests.get(f"https://www.omdbapi.com/?i={imdb_id}&apikey={omdb_key}", timeout=2.0).json()
                        if res_omdb.get("Response") == "True":
                            imdb_nota = res_omdb.get("imdbRating", "N/A")
                            m_raw = res_omdb.get("Metascore", "N/A")
                            if m_raw and m_raw != "N/A":
                                meta_nota = m_raw

                            for val in res_omdb.get("Ratings", []):
                                if val.get("Source") == "Rotten Tomatoes":
                                    rt_nota = val.get("Value")
                                    break
                    except Exception:
                        pass

                trailer_url = None
                for v in res.get("videos", {}).get("results", []):
                    if v.get("site") == "YouTube":
                        trailer_url = f"https://www.youtube.com/watch?v={v.get('key')}"
                        if v.get("type") in ["Trailer", "Teaser"]:
                            break

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

                streamings = ", ".join(stream_nomes) if stream_nomes else "Sem streaming no BR"

                chave_id = imdb_id or chave_tmdb_calc
                
                if chave_tmdb_calc in botoes_add_home:
                    botoes_add_home[chave_id] = botoes_add_home[chave_tmdb_calc]

                nota_usr = None
                cat_exist = None

                if uid:
                    conn = None
                    try:
                        conn = sqlite3.connect(DB_FILE, timeout=5)
                        cur = conn.cursor()
                        cur.execute("SELECT nota_usuario, categoria FROM filmes WHERE (id = ? OR id = ?) AND usuario_id = ?", (chave_id, chave_tmdb_calc, uid))
                        row = cur.fetchone()
                        if row:
                            nota_usr = row[0]
                            cat_exist = row[1]
                    except Exception:
                        pass
                    finally:
                        if conn:
                            conn.close()

                item_ativo["data"] = {
                    "id": chave_id, "tmdb_orig_key": chave_tmdb_calc, "titulo": titulo, "ano": ano, 
                    "diretor": diretor, "elenco": elenco, "sinopse": sinopse, "imdb": imdb_nota, 
                    "rotten": rt_nota, "metascore": meta_nota, "streaming": streamings, 
                    "poster_url": poster_url, "nota_usuario": nota_usr, "trailer_url": trailer_url, 
                    "categoria_existente": cat_exist, "generos": generos_txt, "tipo": mtype_seguro
                }

                dt_img.src = poster_url
                tag_tipo = "Série" if mtype_seguro == "tv" else "Filme"
                dt_titulo.value = f"{titulo} ({ano}) • {tag_tipo}"
                
                if titulo_orig and normalizar_texto(titulo_orig) != normalizar_texto(titulo):
                    dt_titulo_original.value = f"Original: {titulo_orig}"
                    dt_titulo_original.visible = True
                else:
                    dt_titulo_original.visible = False

                dt_meta.value = f"{info_criacao}\nElenco: {elenco}\nGêneros: {generos_txt}"
                dt_imdb.content.value = f"⭐ {imdb_nota}"
                dt_rt.content.value = f"🍅 {rt_nota}"
                
                if meta_nota != "N/A":
                    try:
                        val_m = int(meta_nota)
                        if val_m >= 61:
                            bg_meta = "#54a72a"
                            cor_meta_txt = "white"
                        elif val_m >= 40:
                            bg_meta = "#ffcc33"
                            cor_meta_txt = "black"
                        else:
                            bg_meta = "#dc2626"
                            cor_meta_txt = "white"
                    except Exception:
                        bg_meta = "#334155"
                        cor_meta_txt = "white"
                    dt_metascore.content.value = f"Ⓜ {meta_nota}"
                    dt_metascore.bgcolor = bg_meta
                    dt_metascore.content.color = cor_meta_txt
                else:
                    dt_metascore.content.value = "Ⓜ --"
                    dt_metascore.bgcolor = "#334155"
                    dt_metascore.content.color = "white"

                dt_user.content.value = f"★ {nota_usr}" if nota_usr else "★ --"
                dt_stream.value = f"📺 {streamings}"
                dt_sinopse.value = sinopse

                btn_trailer.url = trailer_url if trailer_url else fallback_trailer

                if tem_digital:
                    txt_stremio.value = "🎬 Stremio: HD/4K Disponível"
                    txt_stremio.color = "#a7f3d0"
                    dt_stremio_status.bgcolor = "#065f46"
                else:
                    txt_stremio.value = "⏳ Stremio: Apenas Cinema / CAM"
                    txt_stremio.color = "#fde68a"
                    dt_stremio_status.bgcolor = "#78350f"

                if tela_atual == "biblioteca":
                    btn_salvar.visible = False
                    btn_ir_lista.visible = False
                elif cat_exist or (chave_id in ids_salvos_usuario) or (chave_tmdb_calc in ids_salvos_usuario):
                    btn_salvar.content = ft.Text("✓ Na Biblioteca", color="white", size=12)
                    btn_salvar.bgcolor = "#334155"
                    btn_salvar.disabled = True
                    btn_salvar.visible = True
                    btn_ir_lista.visible = True
                    marcar_botao_home_como_salvo(chave_tmdb_calc, chave_id)
                else:
                    btn_salvar.content = ft.Text("+ Adicionar à Biblioteca", color="white", size=12)
                    btn_salvar.bgcolor = COR_PETROLEO
                    btn_salvar.disabled = False
                    btn_salvar.visible = True
                    btn_ir_lista.visible = False

            except Exception as ex:
                print(f"Erro ao obter detalhes: {ex}")
            finally:
                progresso.visible = False
                conteudo_modal.update()
                page.update()

        threading.Thread(target=_fetch, daemon=True).start()

    def adicionar_rapido_poster(e, mid, mtype, titulo, ano, poster_url, chave_id, btn_adicionar):
        uid = sessao_usuario["id"]
        if not uid or chave_id in ids_salvos_usuario:
            return

        mtype_seguro = "tv" if mtype in ["tv", "series"] else "movie"

        conn = None
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            c = conn.cursor()
            c.execute("SELECT id FROM filmes WHERE id = ? AND usuario_id = ?", (chave_id, uid))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO filmes (id, titulo, ano, diretor, elenco, sinopse, imdb, rotten, metascore, streaming, poster_url, categoria, nota_usuario, trailer_url, generos, usuario_id, tipo)
                    VALUES (?, ?, ?, 'N/A', 'N/A', 'Adicionado diretamente da tela inicial.', 'N/A', 'N/A', 'N/A', 'Consultando...', ?, 'Para Assistir', NULL, NULL, 'Outros', ?, ?)
                """, (chave_id, titulo, str(ano), poster_url, uid, mtype_seguro))
                conn.commit()
                ids_salvos_usuario.add(chave_id)
                if titulo:
                    titulos_salvos_usuario.add(normalizar_texto(titulo))
                atualizar_contador_biblioteca()
        except Exception as ex:
            print(f"Erro add rapido: {ex}")
        finally:
            if conn:
                conn.close()

        btn_adicionar.icon = ft.Icons.CHECK
        btn_adicionar.icon_color = "#10b981"
        btn_adicionar.bgcolor = "#064e3b"
        btn_adicionar.disabled = True
        btn_adicionar.tooltip = "Já está na sua biblioteca"
        page.update()

    def criar_card_filme(mid, mtype, titulo, ano, poster_url, categoria=None, nota=None):
        mtype_seguro = "tv" if mtype in ["tv", "series"] else "movie"
        chave_id = mid if isinstance(mid, str) and ("_" in mid or mid.startswith("tt")) else f"{mtype_seguro}_{mid}"
        
        acoes = []
        if categoria == "Para Assistir":
            acoes.append(
                ft.Button(
                    content=ft.Text("✓ Visto", color="white", size=10),
                    bgcolor="#10b981",
                    height=28,
                    on_click=lambda e: abrir_modal_avaliacao(chave_id)
                )
            )
            acoes.append(
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_color="red400",
                    icon_size=16,
                    tooltip="Remover",
                    on_click=lambda e: remover_filme_direto(chave_id)
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
                    ink=True,
                    on_click=lambda e: abrir_modal_avaliacao(chave_id, nota)
                )
            )
            acoes.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color="red400",
                    icon_size=16,
                    tooltip="Excluir",
                    on_click=lambda e: pedir_confirmacao_remocao(chave_id, titulo)
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
                width=28,
                height=28,
                style=ft.ButtonStyle(padding=0)
            )
            btn_add_rapido.on_click = lambda e, m=mid, mt=mtype_seguro, t=titulo, a=ano, p=poster_url, c=chave_id, b=btn_add_rapido: adicionar_rapido_poster(e, m, mt, t, a, p, c, b)
            botoes_add_home[chave_id] = btn_add_rapido

        stack_itens = [
            ft.Image(
                src=poster_url if poster_url else "https://via.placeholder.com/152x216?text=Sem+Poster",
                width=152,
                height=216,
                border_radius=6,
                fit="cover"
            )
        ]
        if badge_tipo:
            stack_itens.append(badge_tipo)
        if btn_add_rapido:
            stack_itens.append(btn_add_rapido)

        imagem_com_badge = ft.Stack(stack_itens)

        card_corpo = ft.Container(
            width=162,
            bgcolor=COR_CARD,
            padding=5,
            border_radius=8,
            ink=True,
            border=criar_borda(1.2, COR_BORDA),
            content=ft.Column([
                imagem_com_badge,
                ft.Text(
                    f"{titulo}\n({ano})",
                    size=11,
                    weight="bold",
                    max_lines=2,
                    overflow="ellipsis",
                    width=152,
                    text_align=ft.TextAlign.CENTER,
                    color=COR_TEXTO_CLARO
                ),
                ft.Row(acoes, spacing=3, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=152) if acoes else ft.Container()
            ], spacing=3, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            on_click=lambda e: abrir_detalhes(mid, mtype_seguro, titulo, ano, poster_url, tela_atual="home" if categoria is None else "biblioteca")
        )
        return card_corpo

    # -------------------------------------------------------------
    # CARREGAMENTO INCREMENTAL OTIMIZADO
    # -------------------------------------------------------------
    def carregar_mais_busca():
        if paginacao["carregando"] or paginacao["fim"]:
            return

        paginacao["carregando"] = True
        spinner_carregamento.visible = True
        page.update()

        f_tipo = paginacao["filtro_home"]
        todos_itens = contexto_busca.get("itens_cache", [])
        
        # Filtro estrito: se f_tipo for 'tv', exige media_type == 'tv'
        if f_tipo == "movie":
            filtrados = [i for i in todos_itens if i.get("media_type") == "movie"]
        elif f_tipo == "tv":
            filtrados = [i for i in todos_itens if i.get("media_type") == "tv"]
        else:
            filtrados = todos_itens

        offset = contexto_busca.get("offset", 0)
        proxima_fatia = filtrados[offset : offset + 20]

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

        if contexto_busca["offset"] >= len(filtrados):
            paginacao["fim"] = True
            btn_carregar_mais.visible = False
        else:
            btn_carregar_mais.visible = True

        paginacao["carregando"] = False
        spinner_carregamento.visible = False
        page.update()

    def acao_carregar_mais(e):
        if paginacao["modo_busca_ativo"]:
            carregar_mais_busca()
        else:
            carregar_populares(incrementar=True)

    grade_populares = ft.Row(wrap=True, spacing=12, run_spacing=14, alignment=ft.MainAxisAlignment.CENTER)
    coluna_biblioteca_itens = ft.Column(spacing=18, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    spinner_carregamento = ft.ProgressRing(width=28, height=28, stroke_width=2.5, color=COR_PETROLEO, visible=False)

    btn_carregar_mais = ft.Button(
        content=ft.Text("Carregar Mais Títulos", size=12, weight="bold", color=COR_TEXTO_CLARO),
        bgcolor=COR_CARD,
        height=36,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            side=ft.BorderSide(1, COR_BORDA)
        ),
        on_click=acao_carregar_mais
    )

    # -------------------------------------------------------------
    # RENDERIZAÇÃO ESTÁVEL DA PESQUISA COM FILTRO RÍGIDO DE TIPO
    # -------------------------------------------------------------
    def renderizar_itens_busca_contexto():
        f_tipo = paginacao["filtro_home"]
        todos_itens = contexto_busca.get("itens_cache", [])
        
        # Filtro estrito: se f_tipo for 'tv', exige media_type == 'tv'
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
                    content=ft.Text(
                        f"Nenhuma {rotulo} encontrada com o termo '{contexto_busca.get('nome')}'.",
                        size=14,
                        color="#94a3b8",
                        text_align=ft.TextAlign.CENTER
                    ),
                    padding=40
                )
            )
            btn_carregar_mais.visible = False
            page.update()
            return

        primeira_fatia = filtrados[:20]
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

        if len(filtrados) > 20:
            paginacao["fim"] = False
            btn_carregar_mais.visible = True
        else:
            paginacao["fim"] = True
            btn_carregar_mais.visible = False

        page.update()

    # -------------------------------------------------------------
    # POPULARES E ROLAGEM INFINITA
    # -------------------------------------------------------------
    def carregar_populares(incrementar=False):
        c = carregar_config()
        tmdb_key = c.get("tmdb_key", "").strip()

        if not tmdb_key:
            grade_populares.controls.clear()
            grade_populares.controls.append(
                ft.Container(
                    content=ft.Text("⚠️ Chave do TMDb ausente. Adicione TMDB_KEY no Render.", color="#f87171", size=13, text_align=ft.TextAlign.CENTER),
                    padding=20
                )
            )
            page.update()
            return

        if paginacao["carregando"] or paginacao["fim"] or paginacao["modo_busca_ativo"]:
            return

        paginacao["carregando"] = True
        if incrementar:
            paginacao["pagina_atual"] += 1

        spinner_carregamento.visible = True
        btn_carregar_mais.visible = False
        page.update()

        def _fetch():
            try:
                p = paginacao["pagina_atual"]
                f_home = paginacao["filtro_home"]

                # Separação rígida de endpoints para nunca misturar filmes e séries no modo trending
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
                        
                        # Atribuição estrita do media_type baseada na aba ativa
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

        # Se houver busca de pessoa ou tema em andamento, filtra estritamente a busca em memória
        if paginacao["modo_busca_ativo"] and contexto_busca.get("tipo"):
            renderizar_itens_busca_contexto()
            return

        paginacao["pagina_atual"] = 1
        paginacao["fim"] = False
        paginacao["ids_carregados"].clear()
        botoes_add_home.clear()
        grade_populares.controls.clear()
        txt_titulo_home.value = "Em Alta (TMDb Trends)"
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
            side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if atual == "movie" else ft.BorderSide(1, COR_BORDA)
        )

        btn_home_series.bgcolor = COR_PETROLEO if atual == "tv" else COR_CARD
        btn_home_series.content.color = "white" if atual == "tv" else "#94a3b8"
        btn_home_series.style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=20),
            side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if atual == "tv" else ft.BorderSide(1, COR_BORDA)
        )
        page.update()

    btn_home_todos = ft.Button(
        content=ft.Text("Todos", size=11, weight="bold", color="white"),
        bgcolor=COR_PETROLEO,
        height=32,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=20),
            side=ft.BorderSide(1.8, COR_ATIVO_BORDA)
        ),
        on_click=lambda e: alternar_filtro_home("todos")
    )
    btn_home_filmes = ft.Button(
        content=ft.Text("🎬 Filmes", size=11, weight="bold", color="#94a3b8"),
        bgcolor=COR_CARD,
        height=32,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=20),
            side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if paginacao["filtro_home"] == "movie" else ft.BorderSide(1, COR_BORDA)
        ),
        on_click=lambda e: alternar_filtro_home("movie")
    )
    btn_home_series = ft.Button(
        content=ft.Text("📺 Séries", size=11, weight="bold", color="#94a3b8"),
        bgcolor=COR_CARD,
        height=32,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=20),
            side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if paginacao["filtro_home"] == "tv" else ft.BorderSide(1, COR_BORDA)
        ),
        on_click=lambda e: alternar_filtro_home("tv")
    )

    txt_contador_bib = ft.Text("BIBLIOTECA", color="white", weight="bold", size=11)

    def atualizar_contador_biblioteca():
        uid = sessao_usuario["id"]
        total = 0
        if uid:
            conn = None
            try:
                conn = sqlite3.connect(DB_FILE, timeout=5)
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM filmes WHERE usuario_id = ?", (uid,))
                row = c.fetchone()
                total = row[0] if row else 0
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()
        txt_contador_bib.value = f"BIBLIOTECA ({total})"
        page.update()

    btn_tab_bib = ft.Container(
        content=txt_contador_bib,
        bgcolor=COR_CARD,
        border=criar_borda(1.2, COR_BORDA),
        border_radius=10,
        padding=ft.Padding(12, 8, 12, 8),
        ink=True,
        on_click=lambda e: alternar_tela(1)
    )

    linha_controles_unificados = ft.Row(
        controls=[btn_home_todos, btn_home_filmes, btn_home_series, btn_tab_bib],
        spacing=8,
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        wrap=True
    )

    def ao_rolar_inicio(e: ft.OnScrollEvent):
        ocultar_sugestoes()
        if paginacao["carregando"] or paginacao["fim"]:
            return

        distancia_do_fim = e.max_scroll_extent - e.pixels
        percentual = (e.pixels / e.max_scroll_extent) if e.max_scroll_extent > 0 else 0

        if (distancia_do_fim <= 1000 or percentual >= 0.80) and e.max_scroll_extent > 0:
            if paginacao["modo_busca_ativo"]:
                carregar_mais_busca()
            else:
                carregar_populares(incrementar=True)

    def remover_filme_direto(fid):
        uid = sessao_usuario["id"]
        if uid:
            conn = None
            try:
                conn = sqlite3.connect(DB_FILE, timeout=5)
                c = conn.cursor()
                c.execute("DELETE FROM filmes WHERE id = ? AND usuario_id = ?", (fid, uid))
                conn.commit()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()
            
            recarregar_ids_salvos()
            
            if fid in botoes_add_home and botoes_add_home[fid]:
                btn = botoes_add_home[fid]
                btn.icon = ft.Icons.ADD
                btn.icon_color = "white"
                btn.bgcolor = "#0d1419cc"
                btn.disabled = False
                btn.tooltip = "Adicionar à Biblioteca"
            
            atualizar_contador_biblioteca()
            carregar_biblioteca()

    def imprimir_lista():
        uid = sessao_usuario["id"]
        filmes = []
        if uid:
            conn = None
            try:
                conn = sqlite3.connect(DB_FILE, timeout=5)
                c = conn.cursor()
                c.execute("SELECT titulo, ano, imdb, rotten, streaming, diretor, tipo FROM filmes WHERE categoria = 'Para Assistir' AND usuario_id = ? ORDER BY titulo ASC", (uid,))
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

    def carregar_biblioteca():
        coluna_biblioteca_itens.controls.clear()
        todos_itens = []
        uid = sessao_usuario["id"]

        if uid:
            conn = None
            try:
                conn = sqlite3.connect(DB_FILE, timeout=5)
                c = conn.cursor()
                c.execute("""
                    SELECT id, titulo, ano, poster_url, nota_usuario, categoria, streaming, generos, imdb, tipo 
                    FROM filmes 
                    WHERE usuario_id = ? 
                    ORDER BY rowid DESC
                """, (uid,))
                todos_itens = c.fetchall()
            except Exception:
                pass
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
            content=ft.Text("🖨️ Imprimir", color="white", size=11, weight="bold"),
            bgcolor=COR_CHUMBO,
            on_click=lambda e: imprimir_lista()
        )

        is_para_assistir_ativo = (aba_atual == "Para Assistir")
        btn_aba_para_assistir = ft.Button(
            content=ft.Text(f"⏳ Para Assistir ({total_para_assistir})", color="white" if is_para_assistir_ativo else "#94a3b8", weight="bold"),
            bgcolor=COR_PETROLEO if is_para_assistir_ativo else "#141d24",
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                side=ft.BorderSide(2, COR_ATIVO_BORDA) if is_para_assistir_ativo else ft.BorderSide(1, COR_BORDA)
            ),
            on_click=lambda e: mudar_aba_biblioteca("Para Assistir")
        )

        btn_aba_assistidos = ft.Button(
            content=ft.Text(f"✓ Assistidos ({total_assistidos})", color="white" if not is_para_assistir_ativo else "#94a3b8", weight="bold"),
            bgcolor=COR_PETROLEO if not is_para_assistir_ativo else "#141d24",
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                side=ft.BorderSide(2, COR_ATIVO_BORDA) if not is_para_assistir_ativo else ft.BorderSide(1, COR_BORDA)
            ),
            on_click=lambda e: mudar_aba_biblioteca("Assistidos")
        )

        linha_abas_biblioteca = ft.Row(
            spacing=10,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[btn_aba_para_assistir, btn_aba_assistidos]
        )

        def criar_botao_tipo(rotulo, valor_tipo):
            ativo = (tipo_atual == valor_tipo)
            return ft.Button(
                content=ft.Text(rotulo, color="white" if ativo else "#94a3b8", size=11, weight="bold"),
                bgcolor=COR_PETROLEO if ativo else COR_CARD,
                height=32,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=20),
                    side=ft.BorderSide(1.8, COR_ATIVO_BORDA) if ativo else ft.BorderSide(1, COR_BORDA)
                ),
                on_click=lambda e, t=valor_tipo: mudar_filtro_tipo_bib(t)
            )

        barra_tipo = ft.Row(
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
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
                bgcolor="#055663" if ativo else COR_CARD,
                height=32,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    side=ft.BorderSide(2, "#38bdf8") if ativo else ft.BorderSide(1, COR_BORDA)
                ),
                on_click=lambda e, m=modo_alvo: mudar_modo_filtro(m)
            )

        controles_filtros = [
            ft.Text("Organizar:", size=11, color="#cbd5e1", weight="bold"),
            criar_botao_filtro("Streaming", "streaming"),
            criar_botao_filtro("A-Z", "alfabetico"),
            criar_botao_filtro("Gênero", "genero"),
        ]

        if aba_atual == "Para Assistir":
            controles_filtros.append(criar_botao_filtro("Nota IMDb", "nota"))
        else:
            controles_filtros.append(criar_botao_filtro("Nota Pessoal", "nota_pessoal"))

        barra_filtros = ft.Row(
            spacing=8,
            wrap=True,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=controles_filtros
        )

        topo_biblioteca = ft.Container(
            content=ft.Column([
                ft.Row(
                    [
                        ft.Text(f"Biblioteca ({len(todos_itens)})", size=20, weight="bold", color=COR_TEXTO_CLARO),
                        btn_print
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                linha_abas_biblioteca,
                barra_tipo,
                barra_filtros
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            width=1000
        )

        coluna_biblioteca_itens.controls.append(topo_biblioteca)

        if not itens_filtrados:
            coluna_biblioteca_itens.controls.append(
                ft.Container(
                    content=ft.Text(
                        "Nenhum título encontrado com os filtros selecionados.",
                        color="#94a3b8",
                        size=14
                    ),
                    padding=ft.Padding(10, 30, 10, 20)
                )
            )
            page.update()
            return

        def renderizar_secao(titulo_secao, icone, cor, lista):
            if not lista:
                return
            grade_cards = ft.Row(
                wrap=True,
                spacing=12,
                run_spacing=14,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    criar_card_filme(mid, tp, tit, ano, p_url, categoria=cat, nota=nota)
                    for mid, tit, ano, p_url, nota, cat, tp in lista
                ]
            )
            bloco = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(f"{icone} {titulo_secao}", size=15, weight="bold", color=cor),
                        ft.Container(
                            content=ft.Text(f"{len(lista)}", size=11, color="white", weight="bold"),
                            bgcolor=COR_CARD,
                            border=criar_borda(1, COR_BORDA),
                            padding=ft.Padding(5, 2, 5, 2),
                            border_radius=8
                        )
                    ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                    grade_cards
                ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                width=1000
            )
            coluna_biblioteca_itens.controls.append(bloco)

        def renderizar_grade_lado_a_lado(lista, texto_info=None):
            if not lista:
                return
            grade = ft.Row(
                wrap=True,
                spacing=12,
                run_spacing=14,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    criar_card_filme(mid, tp, tit, ano, p_url, categoria=cat, nota=nota)
                    for mid, tit, ano, p_url, nota, cat, tp in lista
                ]
            )
            elementos = []
            if texto_info:
                elementos.append(
                    ft.Row([
                        ft.Text(texto_info, size=15, weight="bold", color=COR_TEXTO_CLARO),
                        ft.Container(
                            content=ft.Text(f"{len(lista)}", size=11, color="white", weight="bold"),
                            bgcolor=COR_CARD,
                            border=criar_borda(1, COR_BORDA),
                            padding=ft.Padding(5, 2, 5, 2),
                            border_radius=8
                        )
                    ], spacing=6, alignment=ft.MainAxisAlignment.CENTER)
                )
            elementos.append(grade)
            bloco = ft.Container(
                content=ft.Column(elementos, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                width=1000
            )
            coluna_biblioteca_itens.controls.append(bloco)

        if modo_atual == "streaming":
            ordem_secoes = list(STREAMINGS_PADRAO) + ["Stremio", "Sem streaming no BR"]
            mapa = {s: [] for s in ordem_secoes}

            for row in itens_filtrados:
                mid, tit, ano, p_url, nota, cat, streaming_txt, tp = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[9]
                st_str = streaming_txt or ""
                alocado_oficial = False

                for st_nome in STREAMINGS_PADRAO:
                    termo = st_nome.lower().replace(" plus", "").replace("+", "")
                    if termo in st_str.lower():
                        mapa[st_nome].append((mid, tit, ano, p_url, nota, cat, tp or "movie"))
                        alocado_oficial = True

                if not alocado_oficial:
                    if "stremio" in st_str.lower():
                        mapa["Stremio"].append((mid, tit, ano, p_url, nota, cat, tp or "movie"))
                    else:
                        mapa["Sem streaming no BR"].append((mid, tit, ano, p_url, nota, cat, tp or "movie"))

            for servico in ordem_secoes:
                cor = "#a78bfa" if servico == "Stremio" else ("#94a3b8" if servico == "Sem streaming no BR" else COR_TEXTO_CLARO)
                ico = "🎬" if servico == "Stremio" else ("❌" if servico == "Sem streaming no BR" else "📺")
                renderizar_secao(servico, ico, cor, mapa[servico])

        elif modo_atual == "alfabetico":
            mapa_alfabetico = {}
            itens_ordenados = sorted(itens_filtrados, key=lambda x: normalizar_texto(x[1]))
            for row in itens_ordenados:
                mid, tit, ano, p_url, nota, cat, tp = row[0], row[1], row[2], row[3], row[4], row[5], row[9]
                letra = normalizar_texto(tit)[:1].upper() if tit else "#"
                if not letra.isalpha():
                    letra = "#"
                mapa_alfabetico.setdefault(letra, []).append((mid, tit, ano, p_url, nota, cat, tp or "movie"))

            letras_ordenadas = sorted([k for k in mapa_alfabetico.keys() if k != "#"])
            if "#" in mapa_alfabetico:
                letras_ordenadas.append("#")

            for letra in letras_ordenadas:
                renderizar_secao(f"Letra {letra}", "🔤", COR_TEXTO_CLARO, mapa_alfabetico[letra])

        elif modo_atual == "genero":
            mapa_generos = {}
            for row in itens_filtrados:
                mid, tit, ano, p_url, nota, cat, gens, tp = row[0], row[1], row[2], row[3], row[4], row[5], row[7], row[9]
                lista_g = [g.strip() for g in gens.split(",")] if gens else ["Outros"]
                for g in lista_g:
                    mapa_generos.setdefault(g, []).append((mid, tit, ano, p_url, nota, cat, tp or "movie"))

            for g_nome in sorted(mapa_generos.keys()):
                renderizar_secao(g_nome, "🏷️", "#fbbf24", mapa_generos[g_nome])

        elif modo_atual == "nota":
            def pegar_imdb_float(it):
                val = it[8]
                try:
                    return float(str(val).replace(",", ".")) if (val and val != "N/A") else 0.0
                except Exception:
                    return 0.0

            itens_ordenados_imdb = sorted(itens_filtrados, key=pegar_imdb_float, reverse=True)
            lista_cards = [
                (row[0], row[1], row[2], row[3], row[4], row[5], row[9] or "movie")
                for row in itens_ordenados_imdb
            ]
            renderizar_grade_lado_a_lado(
                lista_cards,
                texto_info="⭐ Ordenado por Nota do IMDb (Maior para Menor)"
            )

        elif modo_atual == "nota_pessoal":
            def pegar_nota_pessoal_float(it):
                val = it[4]
                try:
                    return float(str(val).replace(",", ".")) if (val and val != "N/A") else 0.0
                except Exception:
                    return 0.0

            itens_ordenados_pessoal = sorted(itens_filtrados, key=pegar_nota_pessoal_float, reverse=True)
            lista_cards = [
                (row[0], row[1], row[2], row[3], row[4], row[5], row[9] or "movie")
                for row in itens_ordenados_pessoal
            ]
            renderizar_grade_lado_a_lado(
                lista_cards,
                texto_info="★ Ordenado por Sua Nota Pessoal (10 a 1)"
            )

        page.update()

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
            page.update()

    # FILTRAGEM INTELIGENTE DE ARTISTA (COM CLASSIFICAÇÃO RÍGIDA DE TV/MOVIE)
    def exibir_filmografia_pessoa(person_id, nome_pessoa):
        ocultar_sugestoes()
        campo_busca.value = nome_pessoa
        paginacao["modo_busca_ativo"] = True
        paginacao["fim"] = False
        btn_carregar_mais.visible = False
        grade_populares.controls.clear()
        
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
                        
                    # Detecção rígida: se tem 'name' ou 'first_air_date', é TV
                    if item.get("media_type") == "tv" or "name" in item or "first_air_date" in item:
                        mtype = "tv"
                    else:
                        mtype = "movie"
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
                            
                        if item.get("media_type") == "tv" or "name" in item or "first_air_date" in item:
                            mtype = "tv"
                        else:
                            mtype = "movie"
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
                kw_ids_str = ""

                for termo_k, ids_v in MAPA_KEYWORDS_CONHECIDAS.items():
                    if termo_k in norm:
                        kw_ids_str = ids_v
                        break

                if not kw_ids_str:
                    tr = traduzir_para_ingles(termo_limpo)
                    kw_encontrados = set()
                    for q in [tr, norm]:
                        try:
                            kw_url = f"https://api.themoviedb.org/3/search/keyword?api_key={tmdb_key}&query={quote_plus(q)}&page=1"
                            r = requests.get(kw_url, timeout=2.0)
                            if r.status_code == 200:
                                for k in r.json().get("results", [])[:3]:
                                    kw_encontrados.add(str(k.get("id")))
                        except Exception:
                            pass
                    if kw_encontrados:
                        kw_ids_str = "|".join(list(kw_encontrados)[:5])

                itens_totais = []
                vistos = set()

                if kw_ids_str:
                    for pg in [1, 2, 3]:
                        try:
                            url_m = f"https://api.themoviedb.org/3/discover/movie?api_key={tmdb_key}&language=pt-BR&sort_by=vote_count.desc&with_keywords={kw_ids_str}&vote_count.gte=30&page={pg}"
                            res_m = requests.get(url_m, timeout=3.5).json().get("results", [])
                            for item in res_m:
                                if not item.get("poster_path"):
                                    continue
                                item["media_type"] = "movie"
                                chave = f"movie_{item.get('id')}"
                                if chave not in vistos:
                                    vistos.add(chave)
                                    itens_totais.append(item)
                        except Exception:
                            pass

                    for pg in [1, 2]:
                        try:
                            url_t = f"https://api.themoviedb.org/3/discover/tv?api_key={tmdb_key}&language=pt-BR&sort_by=vote_count.desc&with_keywords={kw_ids_str}&vote_count.gte=10&page={pg}"
                            res_t = requests.get(url_t, timeout=3.5).json().get("results", [])
                            for item in res_t:
                                if not item.get("poster_path"):
                                    continue
                                item["media_type"] = "tv"
                                chave = f"tv_{item.get('id')}"
                                if chave not in vistos:
                                    vistos.add(chave)
                                    itens_totais.append(item)
                        except Exception:
                            pass

                for pg in [1, 2]:
                    try:
                        url_multi = f"https://api.themoviedb.org/3/search/multi?api_key={tmdb_key}&query={quote_plus(termo_limpo)}&language=pt-BR&include_adult=false&page={pg}"
                        res_multi = requests.get(url_multi, timeout=3.0).json().get("results", [])
                        for item in res_multi:
                            mtype = item.get("media_type")
                            if mtype not in ["movie", "tv"]:
                                mtype = "tv" if "name" in item else "movie"
                            item["media_type"] = mtype

                            if item.get("poster_path") and item.get("vote_count", 0) >= 20:
                                chave = f"{mtype}_{item.get('id')}"
                                if chave not in vistos:
                                    vistos.add(chave)
                                    itens_totais.append(item)
                    except Exception:
                        pass

                contexto_busca["itens_cache"] = sorted(itens_totais, key=lambda x: x.get("vote_count", 0), reverse=True)
            except Exception as ex:
                print(f"Erro pesquisa tema: {ex}")
            finally:
                progresso.visible = False
                renderizar_itens_busca_contexto()

        threading.Thread(target=_fetch, daemon=True).start()

    def selecionar_sugestao_filme(mid, mtype, tit, ano, p_url):
        ocultar_sugestoes()
        campo_busca.value = tit
        page.update()
        abrir_detalhes(mid, mtype, tit, ano, p_url, tela_atual="home")

    def buscar_sugestoes_api(termo, epoch_disparo):
        if epoch_disparo != versao_busca_atual["epoch"]:
            return

        c = carregar_config()
        tmdb_key = c.get("tmdb_key", "").strip()
        termo_limpo = termo.strip()
        if not tmdb_key or len(termo_limpo) < 2:
            ocultar_sugestoes()
            return

        try:
            url_multi = "https://api.themoviedb.org/3/search/multi"
            params_multi = {
                "api_key": tmdb_key,
                "query": termo_limpo,
                "language": "pt-BR",
                "include_adult": "false"
            }
            resp_multi = requests.get(url_multi, params=params_multi, timeout=3.0)
            
            if epoch_disparo != versao_busca_atual["epoch"]:
                return

            itens_multi = resp_multi.json().get("results", []) if resp_multi.status_code == 200 else []

            coluna_sugestoes.controls.clear()

            linha_tema_universal = ft.Container(
                padding=8,
                border_radius=6,
                ink=True,
                bgcolor="#164e63",
                on_click=lambda e, t=termo_limpo: executar_pesquisa_tema_ou_termo(t),
                content=ft.Row([
                    ft.Icon(ft.Icons.SEARCH, size=18, color="#38bdf8"),
                    ft.Column([
                        ft.Text(f'Ver catálogo sobre "{termo_limpo}"', size=12, weight="bold", color="white", max_lines=1, overflow="ellipsis"),
                        ft.Text("🏷️ Assunto, contexto ou tema", size=10, color="#7dd3fc")
                    ], spacing=2, expand=True)
                ], spacing=8)
            )
            coluna_sugestoes.controls.append(linha_tema_universal)

            pessoas = [i for i in itens_multi if i.get("media_type") == "person"][:2]
            for p in pessoas:
                pid = p.get("id")
                pnome = p.get("name") or "Artista"
                dept = p.get("known_for_department") or "Atuação"
                dept_traduzido = "Direção" if dept == "Directing" else "Ator/Atriz"
                pic = p.get("profile_path")
                pic_url = f"https://image.tmdb.org/t/p/w185{pic}" if pic else None

                linha_p = ft.Container(
                    padding=6,
                    border_radius=6,
                    ink=True,
                    bgcolor="#1e293b",
                    on_click=lambda e, person_id=pid, name=pnome: exibir_filmografia_pessoa(person_id, name),
                    content=ft.Row([
                        ft.Image(
                            src=pic_url if pic_url else "https://via.placeholder.com/32x46?text=👤",
                            width=32,
                            height=46,
                            border_radius=4,
                            fit="cover"
                        ),
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

                linha_item = ft.Container(
                    padding=6,
                    border_radius=6,
                    ink=True,
                    bgcolor=COR_CARD,
                    on_click=lambda e, m=mid, mt=mtype, t=tit, a=ano, p=p_url: selecionar_sugestao_filme(m, mt, t, a, p),
                    content=ft.Row([
                        ft.Image(
                            src=p_url if p_url else "https://via.placeholder.com/40x60?text=-",
                            width=32,
                            height=46,
                            border_radius=4,
                            fit="cover"
                        ),
                        ft.Column([
                            ft.Text(tit, size=12, weight="bold", color="white", max_lines=1, overflow="ellipsis"),
                            ft.Text(f"{ano} • {'Série' if mtype == 'tv' else 'Filme'}", size=10, color="#94a3b8")
                        ], spacing=2, expand=True)
                    ], spacing=8)
                )
                coluna_sugestoes.controls.append(linha_item)

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

            page.update()
        except Exception as ex:
            print(f"Erro busca expandida: {ex}")

    def disparar_busca_manual(e=None):
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
            ocultar_sugestoes()
            return

        t = threading.Timer(0.3, buscar_sugestoes_api, args=[termo, epoch_deste_disparo])
        timer_busca["timer"] = t
        t.start()

    campo_busca = ft.TextField(
        hint_text="Buscar filmes, atores, temas...",
        hint_style=ft.TextStyle(size=12, color="#64748b"),
        text_size=12,
        bgcolor="#0d1419",
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        expand=True,
        height=38,
        content_padding=ft.Padding(12, 0, 8, 0),
        suffix=ft.IconButton(
            icon=ft.Icons.SEARCH,
            icon_color="#64748b",
            icon_size=18,
            tooltip="Buscar filme, pessoa ou tema",
            on_click=disparar_busca_manual
        ),
        on_change=ao_digitar_busca,
        on_submit=disparar_busca_manual
    )

    def clicar_no_logo(e):
        btn_logo_interativo.scale = 0.94
        page.update()
        time.sleep(0.06)
        btn_logo_interativo.scale = 1.0
        
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

    btn_logo_interativo = ft.Container(
        content=img_logo,
        ink=True,
        padding=2,
        scale=1.0,
        animate_scale=ft.Animation(100, ft.AnimationCurve.EASE_OUT),
        tooltip="Voltar ao Início (Todos)",
        on_click=clicar_no_logo
    )

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
        content=ft.Row(
            controls=[campo_busca],
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
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
        largura_janela = page.width if page.width else 1000
        if largura_janela < 720:
            img_logo.height = 60
            container_input_busca.width = min(int(largura_janela * 0.92), 380)
            titulo_trends.width = None
        else:
            img_logo.height = 68
            container_input_busca.width = 340
            titulo_trends.width = 1100
        page.update()

    page.on_resized = ajustar_layout_responsivo

    txt_titulo_home = ft.Text("Em Alta (TMDb Trends)", size=15, weight="bold", color=COR_TEXTO_CLARO)

    titulo_trends = ft.Container(
        content=ft.Row([txt_titulo_home], alignment=ft.MainAxisAlignment.START),
        width=1100,
        padding=ft.Padding(0, 8, 0, 0)
    )

    bloco_carregamento_fim = ft.Column(
        controls=[
            spinner_carregamento,
            btn_carregar_mais
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=8
    )

    view_inicio = ft.Container(
        expand=True,
        padding=ft.Padding(8, 0, 8, 10),
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            on_scroll=ao_rolar_inicio,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[
                titulo_trends,
                grade_populares,
                ft.Container(
                    content=bloco_carregamento_fim,
                    alignment=ft.Alignment(0, 0),
                    padding=ft.Padding(0, 15, 0, 40)
                )
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
        fechar_dialogo(modal_detalhes)
        ocultar_sugestoes()

        if indice == 0:
            view_inicio.visible = True
            view_biblioteca.visible = False
            linha_controles_unificados.visible = True
            btn_tab_bib.border = criar_borda(1.2, COR_BORDA)
        elif indice == 1:
            carregar_biblioteca()
            view_inicio.visible = False
            view_biblioteca.visible = True
            linha_controles_unificados.visible = False
            btn_tab_bib.border = criar_borda(2, COR_ATIVO_BORDA)

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
        page.update()

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
        
        botoes_add_home.clear()
        grade_populares.controls.clear()

        carregar_populares()

    txt_novo_perfil_nome = ft.TextField(
        label="Nome do Perfil",
        label_style=ft.TextStyle(color="#94a3b8"),
        bgcolor=COR_FUNDO,
        dense=True,
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        width=280
    )
    txt_novo_perfil_erro = ft.Text("", size=12, color="#ef4444")

    def salvar_novo_perfil(e):
        nome = txt_novo_perfil_nome.value.strip() if txt_novo_perfil_nome.value else ""
        if len(nome) < 2:
            txt_novo_perfil_erro.value = "Digite pelo menos 2 caracteres."
            page.update()
            return

        conn = None
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            c = conn.cursor()
            c.execute("SELECT id FROM usuarios WHERE username = ?", (nome,))
            if c.fetchone():
                txt_novo_perfil_erro.value = "Este perfil já existe."
                page.update()
                return

            c.execute("SELECT COUNT(*) FROM usuarios")
            qtd = c.fetchone()[0]
            cor_escolhida = CORES_AVATAR[qtd % len(CORES_AVATAR)]

            c.execute("INSERT INTO usuarios (username, cor_avatar) VALUES (?, ?)", (nome, cor_escolhida))
            novo_id = c.lastrowid
            conn.commit()

            fechar_dialogo(modal_novo_perfil)
            txt_novo_perfil_nome.value = ""
            txt_novo_perfil_erro.value = ""

            entrar_com_perfil(novo_id, nome, cor_escolhida)
        except Exception as err:
            txt_novo_perfil_erro.value = f"Erro: {err}"
            page.update()
        finally:
            if conn:
                conn.close()

    modal_novo_perfil = ft.AlertDialog(
        modal=False,
        title=ft.Text("Adicionar Novo Perfil", size=16, weight="bold", color="white"),
        content=ft.Column([
            ft.Text("Como deseja chamar este perfil?", size=13, color="#94a3b8"),
            txt_novo_perfil_erro,
            txt_novo_perfil_nome
        ], tight=True, spacing=10),
        actions=[
            ft.Button(content=ft.Text("Cancelar", color="#94a3b8"), on_click=lambda e: fechar_dialogo(modal_novo_perfil)),
            ft.Button(content=ft.Text("Salvar Perfil", color="white"), bgcolor=COR_PETROLEO, on_click=salvar_novo_perfil)
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )

    def abrir_modal_novo_perfil(e=None):
        txt_novo_perfil_nome.value = ""
        txt_novo_perfil_erro.value = ""
        abrir_dialogo(modal_novo_perfil)

    def criar_card_avatar(uid, nome, cor):
        iniciais = (nome[:2] if len(nome) >= 2 else nome).upper()
        
        avatar_box = ft.Container(
            content=ft.Text(iniciais, size=32, weight="bold", color="white"),
            alignment=ft.Alignment(0, 0),
            width=110,
            height=110,
            border_radius=12,
            bgcolor=cor,
            border=criar_borda(2, "transparent"),
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT)
        )

        def on_hover_card(e):
            avatar_box.border = criar_borda(2, "white" if e.data == "true" else "transparent")
            card_item.scale = 1.05 if e.data == "true" else 1.0
            page.update()

        card_item = ft.Container(
            content=ft.Column([
                avatar_box,
                ft.Text(nome, size=14, weight="bold", color="#94a3b8", text_align=ft.TextAlign.CENTER, width=110)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            ink=True,
            border_radius=12,
            padding=4,
            scale=1.0,
            animate_scale=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
            on_hover=on_hover_card,
            on_click=lambda e, u=uid, n=nome, c=cor: entrar_com_perfil(u, n, c)
        )
        return card_item

    def criar_card_adicionar():
        box_add = ft.Container(
            content=ft.Icon(ft.Icons.ADD_ROUNDED, size=48, color="#64748b"),
            alignment=ft.Alignment(0, 0),
            width=110,
            height=110,
            border_radius=12,
            bgcolor="#0d1419",
            border=criar_borda(1.5, "#334155")
        )

        def on_hover_add(e):
            box_add.border = criar_borda(1.5, "white" if e.data == "true" else "#334155")
            box_add.content.color = "white" if e.data == "true" else "#64748b"
            card_add.scale = 1.05 if e.data == "true" else 1.0
            page.update()

        card_add = ft.Container(
            content=ft.Column([
                box_add,
                ft.Text("Adicionar Perfil", size=13, color="#64748b", text_align=ft.TextAlign.CENTER, width=110)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            ink=True,
            border_radius=12,
            padding=4,
            scale=1.0,
            animate_scale=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
            on_hover=on_hover_add,
            on_click=abrir_modal_novo_perfil
        )
        return card_add

    def carregar_perfis_tela():
        linha_cards_perfis.controls.clear()
        perfis = []
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            c = conn.cursor()
            c.execute("SELECT id, username, cor_avatar FROM usuarios ORDER BY id ASC")
            perfis = c.fetchall()
        except Exception as e:
            print(f"Erro ao buscar perfis: {e}")
        finally:
            if conn:
                conn.close()

        if not perfis:
            abrir_modal_novo_perfil()

        for pid, pnome, pcor in perfis:
            cor_final = pcor if pcor else COR_PETROLEO
            linha_cards_perfis.controls.append(criar_card_avatar(pid, pnome, cor_final))

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

    page.add(tela_perfis, layout_mestre)
    carregar_perfis_tela()
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
