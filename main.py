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
# BANCO DE DADOS
# -------------------------------------------------------------
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
    filme_avaliando = {"id": None, "nota": "10"}
    filme_para_remover = {"id": None, "titulo": ""}
    
    botoes_add_home = {}
    ids_salvos_usuario = set()
    titulos_salvos_usuario = set()

    def safe_update():
        try:
            page.update()
        except Exception:
            pass

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
        safe_update()

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
        "ids_carregados": set()
    }

    progresso = ft.ProgressBar(color=COR_PETROLEO, bgcolor="transparent", visible=False)

    def abrir_dialogo(modal):
        modal.open = True
        if modal not in page.overlay:
            page.overlay.append(modal)
        safe_update()

    def fechar_dialogo(modal):
        modal.open = False
        safe_update()

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
        safe_update()

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

    # -------------------------------------------------------------
    # JANELA DE DETALHES
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
        safe_update()

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
        safe_update()

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
                safe_update()

        threading.Thread(target=_fetch, daemon=True).start()

    # -------------------------------------------------------------
    # ADICIONAR RÁPIDO DIRETO NO PÔSTER (+)
    # -------------------------------------------------------------
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
        safe_update()

    # -------------------------------------------------------------
    # CARTÕES DOS FILMES E SÉRIES
    # -------------------------------------------------------------
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
        if mtype == "tv":
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
            btn_add_rapido.on_click = lambda e, m=mid, mt=mtype, t=titulo, a=ano, p=poster_url, c=chave_id, b=btn_add_rapido: adicionar_rapido_poster(e, m, mt, t, a, p, c, b)
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
            on_click=lambda e: abrir_detalhes(mid, mtype, titulo, ano, poster_url, tela_atual="home" if categoria is None else "biblioteca")
        )
        return card_corpo

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
        on_click=lambda e: carregar_populares(incrementar=True)
    )

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
            safe_update()
            return

        if paginacao["carregando"] or paginacao["fim"]:
            return

        paginacao["carregando"] = True
        if incrementar:
            paginacao["pagina_atual"] += 1

        spinner_carregamento.visible = True
        btn_carregar_mais.visible = False
        safe_update()

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
                        media_t = it.get("media_type") or ("tv" if f_home == "tv" else "movie")
                        if media_t not in ["movie", "tv"]:
                            continue

                        chave_unicidade = f"{media_t}_{mid}"
                        if chave_unicidade in paginacao["ids_carregados"]:
                            continue
                        paginacao["ids_carregados"].add(chave_unicidade)

                        tit = it.get("title") or it.get("name") or "Sem título"
                        ano = str((it.get("release_date") or it.get("first_air_date")) or "")[:4]
                        p_path = it.get("poster_path")
                        p_url = f"https://image.tmdb.org/t/p/w300{p_path}" if p_path else None
                        novos.append(criar_card_filme(mid, media_t, tit, ano, p_url))

                    grade_populares.controls.extend(novos)
            except Exception as e:
                print(f"Erro ao buscar populares: {e}")
            finally:
                paginacao["carregando"] = False
                spinner_carregamento.visible = False
                btn_carregar_mais.visible = not paginacao["fim"]
                safe_update()

        threading.Thread(target=_fetch, daemon=True).start()

    def alternar_filtro_home(novo_filtro):
        if paginacao["filtro_home"] == novo_filtro and len(grade_populares.controls) > 0:
            return
        paginacao["carregando"] = False
        paginacao["filtro_home"] = novo_filtro
        paginacao["pagina_atual"] = 1
        paginacao["fim"] = False
        paginacao["ids_carregados"].clear()
        botoes_add_home.clear()
        grade_populares.controls.clear()
        atualizar_botoes_filtro_home()
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
        safe_update()

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
            side=ft.BorderSide(1, COR_BORDA)
        ),
        on_click=lambda e: alternar_filtro_home("movie")
    )
    btn_home_series = ft.Button(
        content=ft.Text("📺 Séries", size=11, weight="bold", color="#94a3b8"),
        bgcolor=COR_CARD,
        height=32,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=20),
            side=ft.BorderSide(1, COR_BORDA)
        ),
        on_click=lambda e: alternar_filtro_home("tv")
    )

    linha_seletor_home = ft.Row(
        controls=[btn_home_todos, btn_home_filmes, btn_home_series],
        spacing=8,
        alignment=ft.MainAxisAlignment.CENTER
    )

    def ao_rolar_inicio(e: ft.OnScrollEvent):
        ocultar_sugestoes()
        distancia_do_fim = e.max_scroll_extent - e.pixels
        percentual = (e.pixels / e.max_scroll_extent) if e.max_scroll_extent > 0 else 0

        if (distancia_do_fim <= 1200 or percentual >= 0.75) and e.max_scroll_extent > 0:
            if not paginacao["carregando"] and not paginacao["fim"]:
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

    # -------------------------------------------------------------
    # BIBLIOTECA
    # -------------------------------------------------------------
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
                linha_abas_biblioteca
