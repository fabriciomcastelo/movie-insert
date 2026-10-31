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
# SEGURANÇA E BANCO DE DADOS
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
                streaming TEXT,
                poster_url TEXT,
                categoria TEXT,
                nota_usuario TEXT,
                trailer_url TEXT,
                generos TEXT,
                usuario_id INTEGER,
                PRIMARY KEY (id, usuario_id)
            )
        """)
        try:
            c.execute("ALTER TABLE filmes ADD COLUMN generos TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE filmes ADD COLUMN usuario_id INTEGER DEFAULT 1")
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
        "modo": "streaming"
    }

    paginacao = {
        "pagina_atual": 1,
        "carregando": False,
        "fim": False,
        "modo_api": "trending",
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
    # SELETOR DE NOTAS
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
        title=ft.Text("Qual nota você dá ao filme?", size=16, weight="bold"),
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
        ft.Row([dt_imdb, dt_rt, dt_user], spacing=6, wrap=True),
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

        conn = None
        try:
            conn = sqlite3.connect(DB_FILE, timeout=15)
            c = conn.cursor()
            c.execute("SELECT categoria FROM filmes WHERE id = ? AND usuario_id = ?", (it["id"], uid))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO filmes (id, titulo, ano, diretor, elenco, sinopse, imdb, rotten, streaming, poster_url, categoria, nota_usuario, trailer_url, generos, usuario_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Para Assistir', ?, ?, ?, ?)
                """, (
                    it["id"], it["titulo"], it["ano"], it["diretor"], it["elenco"],
                    it["sinopse"], it["imdb"], it["rotten"], it["streaming"],
                    it["poster_url"], it.get("nota_usuario"), it.get("trailer_url"),
                    it.get("generos", ""), uid
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
                url_tmdb = f"https://api.themoviedb.org/3/{mtype}/{mid}?api_key={tmdb_key}&language=pt-BR&append_to_response=credits,watch/providers,external_ids,videos,release_dates"
                res = requests.get(url_tmdb, timeout=4.0).json()

                diretor = "N/A"
                credits_data = res.get("credits", {})
                if mtype == "movie":
                    for cr in credits_data.get("crew", []):
                        if cr.get("job") == "Director":
                            diretor = cr.get("name")
                            break
                else:
                    criadores = [cr.get("name") for cr in res.get("created_by", [])]
                    diretor = ", ".join(criadores) if criadores else "Não informado"

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
                imdb_nota, rt_nota = "N/A", "N/A"

                if omdb_key and imdb_id:
                    try:
                        res_omdb = requests.get(f"https://www.omdbapi.com/?i={imdb_id}&apikey={omdb_key}", timeout=2.0).json()
                        if res_omdb.get("Response") == "True":
                            imdb_nota = res_omdb.get("imdbRating", "N/A")
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

                tem_digital = False
                hoje = datetime.now().strftime("%Y-%m-%d")
                if mtype == "tv":
                    tem_digital = True
                else:
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

                chave_id = imdb_id or f"{mtype}_{mid}"
                nota_usr = None
                cat_exist = None

                if uid:
                    conn = None
                    try:
                        conn = sqlite3.connect(DB_FILE, timeout=15)
                        cur = conn.cursor()
                        cur.execute("SELECT nota_usuario, categoria FROM filmes WHERE id = ? AND usuario_id = ?", (chave_id, uid))
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
                    "id": chave_id, "titulo": titulo, "ano": ano, "diretor": diretor,
                    "elenco": elenco, "sinopse": sinopse, "imdb": imdb_nota, "rotten": rt_nota,
                    "streaming": streamings, "poster_url": poster_url,
                    "nota_usuario": nota_usr, "trailer_url": trailer_url, "categoria_existente": cat_exist,
                    "generos": generos_txt
                }

                dt_img.src = poster_url
                dt_titulo.value = f"{titulo} ({ano})"
                
                if titulo_orig and normalizar_texto(titulo_orig) != normalizar_texto(titulo):
                    dt_titulo_original.value = f"Original: {titulo_orig}"
                    dt_titulo_original.visible = True
                else:
                    dt_titulo_original.visible = False

                dt_meta.value = f"Direção: {diretor}\nElenco: {elenco}\nGêneros: {generos_txt}"
                dt_imdb.content.value = f"⭐ {imdb_nota}"
                dt_rt.content.value = f"🍅 {rt_nota}"
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

                if cat_exist:
                    btn_salvar.content = ft.Text("✓ Na sua Lista", color="white", size=12)
                    btn_salvar.bgcolor = "#334155"
                    btn_salvar.disabled = True
                    btn_ir_lista.visible = True
                else:
                    btn_salvar.content = ft.Text("+ Adicionar à Lista", color="white", size=12)
                    btn_salvar.bgcolor = COR_PETROLEO
                    btn_salvar.disabled = False
                    btn_ir_lista.visible = False

            except Exception:
                pass
            finally:
                progresso.visible = False
                conteudo_modal.update()
                page.update()

        threading.Thread(target=_fetch, daemon=True).start()

    # -------------------------------------------------------------
    # CARTÕES DOS FILMES
    # -------------------------------------------------------------
    def criar_card_filme(mid, mtype, titulo, ano, poster_url, categoria=None, nota=None):
        acoes = []
        if categoria == "Para Assistir":
            acoes.append(
                ft.Button(
                    content=ft.Text("✓ Visto", color="white", size=10),
                    bgcolor="#10b981",
                    height=28,
                    on_click=lambda e: abrir_modal_avaliacao(mid)
                )
            )
            acoes.append(
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_color="red400",
                    icon_size=16,
                    tooltip="Remover",
                    on_click=lambda e: remover_filme_direto(mid)
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
                    on_click=lambda e: abrir_modal_avaliacao(mid, nota)
                )
            )
            acoes.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color="red400",
                    icon_size=16,
                    tooltip="Excluir",
                    on_click=lambda e: pedir_confirmacao_remocao(mid, titulo)
                )
            )

        card_corpo = ft.Container(
            width=162,
            bgcolor=COR_CARD,
            padding=5,
            border_radius=8,
            ink=True,
            border=criar_borda(1.2, COR_BORDA),
            content=ft.Column([
                ft.Image(
                    src=poster_url if poster_url else "https://via.placeholder.com/152x216?text=Sem+Poster",
                    width=152,
                    height=216,
                    border_radius=6,
                    fit="cover"
                ),
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
            on_click=lambda e: abrir_detalhes(mid, mtype, titulo, ano, poster_url)
        )
        return card_corpo

    grade_populares = ft.Row(wrap=True, spacing=12, run_spacing=14, alignment=ft.MainAxisAlignment.CENTER)
    coluna_biblioteca_itens = ft.Column(spacing=16, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    spinner_carregamento = ft.ProgressRing(width=30, height=30, stroke_width=3, color=COR_PETROLEO, visible=False)

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

        if paginacao["carregando"] or paginacao["fim"]:
            return

        paginacao["carregando"] = True
        if incrementar:
            paginacao["pagina_atual"] += 1

        spinner_carregamento.visible = True
        page.update()

        def _fetch():
            try:
                p = paginacao["pagina_atual"]
                modo = paginacao["modo_api"]

                if modo == "trending":
                    url = f"https://api.themoviedb.org/3/trending/movie/week?api_key={tmdb_key}&language=pt-BR&page={p}"
                else:
                    url = f"https://api.themoviedb.org/3/movie/popular?api_key={tmdb_key}&language=pt-BR&page={p}"

                resp = requests.get(url, timeout=6.0)

                if resp.status_code == 200:
                    dados = resp.json()
                    itens = dados.get("results", [])
                    total_p = dados.get("total_pages", 1000)

                    if (not itens or p >= min(total_p, 20)) and modo == "trending":
                        paginacao["modo_api"] = "popular"
                        paginacao["pagina_atual"] = 1
                        url_pop = f"https://api.themoviedb.org/3/movie/popular?api_key={tmdb_key}&language=pt-BR&page=1"
                        resp_pop = requests.get(url_pop, timeout=6.0)
                        if resp_pop.status_code == 200:
                            dados = resp_pop.json()
                            itens = dados.get("results", [])

                    novos = []
                    for it in itens:
                        mid = it.get("id")
                        if mid in paginacao["ids_carregados"]:
                            continue
                        paginacao["ids_carregados"].add(mid)

                        tit = it.get("title") or it.get("name")
                        ano = str((it.get("release_date") or it.get("first_air_date")) or "")[:4]
                        p_path = it.get("poster_path")
                        p_url = f"https://image.tmdb.org/t/p/w300{p_path}" if p_path else None
                        novos.append(criar_card_filme(mid, "movie", tit, ano, p_url))

                    grade_populares.controls.extend(novos)
            except Exception as e:
                print(f"Erro ao buscar filmes: {e}")
            finally:
                paginacao["carregando"] = False
                spinner_carregamento.visible = False
                page.update()

        threading.Thread(target=_fetch, daemon=True).start()

    def ao_rolar_inicio(e: ft.OnScrollEvent):
        if container_sugestoes.visible:
            container_sugestoes.visible = False
            page.update()

        if e.max_scroll_extent > 0 and (e.pixels + 1000) >= e.max_scroll_extent:
            if not paginacao["carregando"] and not paginacao["fim"]:
                carregar_populares(incrementar=True)

    def remover_filme_direto(fid):
        uid = sessao_usuario["id"]
        if uid:
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
            carregar_biblioteca()

    def imprimir_lista():
        uid = sessao_usuario["id"]
        filmes = []
        if uid:
            conn = None
            try:
                conn = sqlite3.connect(DB_FILE, timeout=15)
                c = conn.cursor()
                c.execute("SELECT titulo, ano, imdb, rotten, streaming, diretor FROM filmes WHERE categoria = 'Para Assistir' AND usuario_id = ? ORDER BY titulo ASC", (uid,))
                filmes = c.fetchall()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()

        if not filmes:
            return

        linhas = "".join([f"<tr><td>{i}</td><td><b>{t}</b> ({a})</td><td>⭐ {im}</td><td>🍅 {rt}</td><td>{st}</td><td>{dr}</td></tr>" for i, (t, a, im, rt, st, dr) in enumerate(filmes, 1)])
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Para Assistir</title>
        <style>body{{font-family:sans-serif;margin:20px;}}table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid #ccc;padding:8px;text-align:left;}}th{{background:#f1f5f9;}}</style>
        </head><body><h2>🎬 Lista Para Assistir ({len(filmes)})</h2><table><thead><tr><th>#</th><th>Título</th><th>IMDb</th><th>RT</th><th>Streaming</th><th>Diretor</th></tr></thead><tbody>{linhas}</tbody></table><script>window.onload=function(){{window.print();}}</script></body></html>"""
        arq = os.path.abspath("lista_para_assistir.html")
        with open(arq, "w", encoding="utf-8") as f:
            f.write(html)
        page.launch_url(f"file://{arq}")

    # -------------------------------------------------------------
    # BIBLIOTECA (FILTRADA POR USUÁRIO)
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

    def carregar_biblioteca():
        coluna_biblioteca_itens.controls.clear()
        todos_itens = []
        uid = sessao_usuario["id"]

        if uid:
            conn = None
            try:
                conn = sqlite3.connect(DB_FILE, timeout=15)
                c = conn.cursor()
                c.execute("""
                    SELECT id, titulo, ano, poster_url, nota_usuario, categoria, streaming, generos, imdb 
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

        itens_filtrados = [it for it in todos_itens if it[5] == aba_atual]

        btn_print = ft.Button(
            content=ft.Text("🖨️ Imprimir", color="white", size=11, weight="bold"),
            bgcolor=COR_CHUMBO,
            on_click=lambda e: imprimir_lista()
        )

        btn_aba_para_assistir = ft.Button(
            content=ft.Text(f"⏳ Para Assistir ({total_para_assistir})", color=COR_TEXTO_CLARO if aba_atual == "Para Assistir" else "#94a3b8", weight="bold"),
            bgcolor=COR_PETROLEO if aba_atual == "Para Assistir" else COR_CHUMBO,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            on_click=lambda e: mudar_aba_biblioteca("Para Assistir")
        )

        btn_aba_assistidos = ft.Button(
            content=ft.Text(f"✓ Assistidos ({total_assistidos})", color=COR_TEXTO_CLARO if aba_atual == "Assistidos" else "#94a3b8", weight="bold"),
            bgcolor=COR_PETROLEO if aba_atual == "Assistidos" else COR_CHUMBO,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            on_click=lambda e: mudar_aba_biblioteca("Assistidos")
        )

        linha_abas_biblioteca = ft.Row(
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[btn_aba_para_assistir, btn_aba_assistidos]
        )

        def criar_botao_filtro(rotulo, modo_alvo):
            ativo = (modo_atual == modo_alvo)
            return ft.Button(
                content=ft.Text(rotulo, color=COR_TEXTO_CLARO if ativo else "#94a3b8", size=11, weight="bold"),
                bgcolor=COR_PETROLEO if ativo else COR_CARD,
                height=32,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    side=ft.BorderSide(1, COR_PETROLEO if ativo else COR_BORDA)
                ),
                on_click=lambda e, m=modo_alvo: mudar_modo_filtro(m)
            )

        controles_filtros = [
            ft.Text("Organizar:", size=11, color="#94a3b8", weight="bold"),
            criar_botao_filtro("Streaming", "streaming"),
            criar_botao_filtro("A-Z", "alfabetico"),
            criar_botao_filtro("Gênero", "genero"),
        ]

        if aba_atual == "Para Assistir":
            controles_filtros.append(criar_botao_filtro("Nota IMDb", "nota"))
        else:
            controles_filtros.append(criar_botao_filtro("Nota Pessoal", "nota_pessoal"))

        barra_filtros = ft.Row(
            spacing=6,
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
                barra_filtros
            ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            width=1000
        )

        coluna_biblioteca_itens.controls.append(topo_biblioteca)

        if not itens_filtrados:
            coluna_biblioteca_itens.controls.append(
                ft.Container(
                    content=ft.Text(
                        f"Nenhum filme na lista de {aba_atual}.",
                        color="#94a3b8",
                        size=14
                    ),
                    padding=ft.Padding(10, 25, 10, 20)
                )
            )
            page.update()
            return

        def renderizar_secao(titulo_secao, icone, cor, lista):
            if not lista:
                return
            linha_cards = ft.Row(
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                alignment=ft.MainAxisAlignment.START,
                controls=[
                    criar_card_filme(mid, "movie", tit, ano, p_url, categoria=cat, nota=nota)
                    for mid, tit, ano, p_url, nota, cat in lista
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
                    ], spacing=6),
                    linha_cards
                ], spacing=6),
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
                    criar_card_filme(mid, "movie", tit, ano, p_url, categoria=cat, nota=nota)
                    for mid, tit, ano, p_url, nota, cat in lista
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
                content=ft.Column(elementos, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                width=1000
            )
            coluna_biblioteca_itens.controls.append(bloco)

        # ---------------- MODO 1: STREAMING ----------------
        if modo_atual == "streaming":
            ordem_secoes = list(STREAMINGS_PADRAO) + ["Stremio", "Sem streaming no BR"]
            mapa = {s: [] for s in ordem_secoes}

            for row in itens_filtrados:
                mid, tit, ano, p_url, nota, cat, streaming_txt = row[0], row[1], row[2], row[3], row[4], row[5], row[6]
                st_str = streaming_txt or ""
                alocado_oficial = False

                for st_nome in STREAMINGS_PADRAO:
                    termo = st_nome.lower().replace(" plus", "").replace("+", "")
                    if termo in st_str.lower():
                        mapa[st_nome].append((mid, tit, ano, p_url, nota, cat))
                        alocado_oficial = True

                if not alocado_oficial:
                    if "stremio" in st_str.lower():
                        mapa["Stremio"].append((mid, tit, ano, p_url, nota, cat))
                    else:
                        mapa["Sem streaming no BR"].append((mid, tit, ano, p_url, nota, cat))

            for servico in ordem_secoes:
                cor = "#a78bfa" if servico == "Stremio" else ("#94a3b8" if servico == "Sem streaming no BR" else COR_TEXTO_CLARO)
                ico = "🎬" if servico == "Stremio" else ("❌" if servico == "Sem streaming no BR" else "📺")
                renderizar_secao(servico, ico, cor, mapa[servico])

        # ---------------- MODO 2: ORDEM ALFABÉTICA (A-Z) ----------------
        elif modo_atual == "alfabetico":
            mapa_alfabetico = {}
            itens_ordenados = sorted(itens_filtrados, key=lambda x: normalizar_texto(x[1]))
            for row in itens_ordenados:
                mid, tit, ano, p_url, nota, cat = row[0], row[1], row[2], row[3], row[4], row[5]
                letra = normalizar_texto(tit)[:1].upper() if tit else "#"
                if not letra.isalpha():
                    letra = "#"
                mapa_alfabetico.setdefault(letra, []).append((mid, tit, ano, p_url, nota, cat))

            letras_ordenadas = sorted([k for k in mapa_alfabetico.keys() if k != "#"])
            if "#" in mapa_alfabetico:
                letras_ordenadas.append("#")

            for letra in letras_ordenadas:
                renderizar_secao(f"Letra {letra}", "🔤", COR_TEXTO_CLARO, mapa_alfabetico[letra])

        # ---------------- MODO 3: GÊNEROS ----------------
        elif modo_atual == "genero":
            mapa_generos = {}
            for row in itens_filtrados:
                mid, tit, ano, p_url, nota, cat, gens = row[0], row[1], row[2], row[3], row[4], row[5], row[7]
                lista_g = [g.strip() for g in gens.split(",")] if gens else ["Outros"]
                for g in lista_g:
                    mapa_generos.setdefault(g, []).append((mid, tit, ano, p_url, nota, cat))

            for g_nome in sorted(mapa_generos.keys()):
                renderizar_secao(g_nome, "🏷️", "#fbbf24", mapa_generos[g_nome])

        # ---------------- MODO 4: NOTA DO IMDB (LADO A LADO) ----------------
        elif modo_atual == "nota":
            def pegar_imdb_float(it):
                val = it[8]
                try:
                    return float(str(val).replace(",", ".")) if (val and val != "N/A") else 0.0
                except Exception:
                    return 0.0

            itens_ordenados_imdb = sorted(itens_filtrados, key=pegar_imdb_float, reverse=True)
            lista_cards = [
                (row[0], row[1], row[2], row[3], row[4], row[5])
                for row in itens_ordenados_imdb
            ]
            renderizar_grade_lado_a_lado(
                lista_cards,
                texto_info="⭐ Ordenado por Nota do IMDb (Maior para Menor)"
            )

        # ---------------- MODO 5: NOTA PESSOAL (LADO A LADO) ----------------
        elif modo_atual == "nota_pessoal":
            def pegar_nota_pessoal_float(it):
                val = it[4]
                try:
                    return float(str(val).replace(",", ".")) if (val and val != "N/A") else 0.0
                except Exception:
                    return 0.0

            itens_ordenados_pessoal = sorted(itens_filtrados, key=pegar_nota_pessoal_float, reverse=True)
            lista_cards = [
                (row[0], row[1], row[2], row[3], row[4], row[5])
                for row in itens_ordenados_pessoal
            ]
            renderizar_grade_lado_a_lado(
                lista_cards,
                texto_info="★ Ordenado por Sua Nota Pessoal (10 a 1)"
            )

        page.update()

    # -------------------------------------------------------------
    # SUGESTÕES NO OVERLAY (FLUTUA SEM EMPURRAR O CABEÇALHO)
    # -------------------------------------------------------------
    coluna_sugestoes = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)

    container_sugestoes = ft.Container(
        content=coluna_sugestoes,
        bgcolor="#111827",
        border_radius=8,
        border=criar_borda(1.2, COR_PETROLEO),
        padding=6,
        visible=False,
        width=290,
        height=260,
        top=138, # Posicionado exatamente abaixo da linha da barra de busca
        shadow=ft.BoxShadow(blur_radius=15, color="#000000")
    )
    page.overlay.append(container_sugestoes)

    def selecionar_sugestao(mid, mtype, tit, ano, p_url):
        container_sugestoes.visible = False
        campo_busca.value = ""
        page.update()
        abrir_detalhes(mid, mtype, tit, ano, p_url)

    def buscar_sugestoes_api(termo):
        c = carregar_config()
        tmdb_key = c.get("tmdb_key", "").strip()
        termo_limpo = termo.strip()
        if not tmdb_key or len(termo_limpo) < 2:
            container_sugestoes.visible = False
            page.update()
            return

        try:
            url = "https://api.themoviedb.org/3/search/multi"
            params = {
                "api_key": tmdb_key,
                "query": termo_limpo,
                "language": "pt-BR",
                "include_adult": "false"
            }
            resp = requests.get(url, params=params, timeout=3.5)
            if resp.status_code != 200:
                return

            itens = resp.json().get("results", [])
            validos = [i for i in itens if i.get("media_type") in ["movie", "tv"]]

            coluna_sugestoes.controls.clear()
            for item in validos[:6]:
                mtype = item.get("media_type", "movie")
                mid = item.get("id")
                tit = item.get("title") or item.get("name") or "Sem título"
                ano = str((item.get("release_date") or item.get("first_air_date")) or "")[:4]
                p_path = item.get("poster_path")
                p_url = f"https://image.tmdb.org/t/p/w200{p_path}" if p_path else None

                linha_item = ft.Container(
                    padding=6,
                    border_radius=6,
                    ink=True,
                    bgcolor=COR_CARD,
                    on_click=lambda e, m=mid, mt=mtype, t=tit, a=ano, p=p_url: selecionar_sugestao(m, mt, t, a, p),
                    content=ft.Row([
                        ft.Image(
                            src=p_url if p_url else "https://via.placeholder.com/40x60?text=-",
                            width=35,
                            height=50,
                            border_radius=4,
                            fit="cover"
                        ),
                        ft.Column([
                            ft.Text(tit, size=13, weight="bold", color="white", max_lines=1, overflow="ellipsis"),
                            ft.Text(f"{ano} • {'Filme' if mtype == 'movie' else 'Série'}", size=11, color="#94a3b8")
                        ], spacing=2, expand=True)
                    ], spacing=10)
                )
                coluna_sugestoes.controls.append(linha_item)

            container_sugestoes.visible = len(coluna_sugestoes.controls) > 0
            page.update()
        except Exception:
            pass

    def disparar_busca_manual(e=None):
        termo = campo_busca.value
        if termo and len(termo.strip()) >= 2:
            buscar_sugestoes_api(termo)

    def ao_digitar_busca(e):
        termo = campo_busca.value
        if timer_busca["timer"]:
            timer_busca["timer"].cancel()

        if not termo or len(termo.strip()) < 2:
            container_sugestoes.visible = False
            page.update()
            return

        t = threading.Timer(0.2, buscar_sugestoes_api, args=[termo])
        timer_busca["timer"] = t
        t.start()

    def fechar_busca_ao_perder_foco(e):
        def _ocultar():
            if container_sugestoes.visible:
                container_sugestoes.visible = False
                page.update()
        threading.Timer(0.25, _ocultar).start()

    # Dimensões atualizadas: 45px altura e 224px largura
    campo_busca = ft.TextField(
        hint_text="Buscar filmes ou séries...",
        hint_style=ft.TextStyle(size=12, color="#64748b"),
        text_size=12,
        bgcolor="#0d1419",
        border_radius=10,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        width=224,
        height=45,
        content_padding=ft.Padding(12, 0, 8, 0),
        on_change=ao_digitar_busca,
        on_submit=disparar_busca_manual,
        on_blur=fechar_busca_ao_perder_foco
    )

    btn_lupa = ft.IconButton(
        icon=ft.Icons.SEARCH,
        icon_color="#64748b",
        icon_size=20,
        tooltip="Buscar filme",
        on_click=disparar_busca_manual
    )

    # -------------------------------------------------------------
    # LOGO INTERATIVO (PARTE SUPERIOR CENTRALIZADA)
    # -------------------------------------------------------------
    def clicar_no_logo(e):
        btn_logo_interativo.scale = 0.94
        page.update()
        time.sleep(0.08)
        btn_logo_interativo.scale = 1.0
        alternar_tela(0)

    btn_logo_interativo = ft.Container(
        content=ft.Image(src="logo.png", height=65, fit="contain"),
        ink=True,
        border_radius=8,
        padding=4,
        scale=1.0,
        animate_scale=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
        tooltip="Voltar ao Início",
        on_click=clicar_no_logo
    )

    btn_tab_bib = ft.Container(
        content=ft.Image(src="biblioteca.png", height=45, fit="contain"),
        ink=True,
        border_radius=10,
        border=criar_borda(2, "transparent"),
        padding=2,
        on_click=lambda e: alternar_tela(1)
    )

    # Informações de usuário no canto superior direito
    lbl_user_tag = ft.Text("", size=12, color="#64748b", weight="bold")

    def acao_logout(e):
        try:
            page.run_javascript("document.cookie = 'user_id=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';")
            page.run_javascript("document.cookie = 'username=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';")
            page.run_javascript("document.cookie = 'manter_conectado=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';")
            page.client_storage.clear()
        except Exception:
            pass
        
        sessao_usuario["id"] = None
        sessao_usuario["username"] = ""
        txt_auth_user.value = ""
        txt_auth_pass.value = ""
        txt_auth_pass_confirm.value = ""
        txt_auth_erro.value = ""
        
        paginacao["pagina_atual"] = 1
        paginacao["carregando"] = False
        paginacao["fim"] = False
        paginacao["modo_api"] = "trending"
        paginacao["ids_carregados"].clear()
        grade_populares.controls.clear()
        
        definir_modo_auth("login")
        layout_mestre.visible = False
        card_auth.visible = True
        page.update()

    btn_logout = ft.IconButton(
        icon=ft.Icons.LOGOUT,
        icon_color=COR_VERMELHO_PLAY,
        icon_size=18,
        tooltip="Sair da conta",
        on_click=acao_logout
    )

    bloco_usuario_topo = ft.Row(
        controls=[lbl_user_tag, btn_logout],
        spacing=4,
        alignment=ft.MainAxisAlignment.END,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )

    linha_busca_input = ft.Row(
        controls=[campo_busca, btn_lupa],
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )

    # Linha Inferior Centralizada: Botão Biblioteca + Caixa de Pesquisa
    linha_inferior_menu = ft.Row(
        controls=[
            btn_tab_bib,
            linha_busca_input
        ],
        spacing=16,
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )

    # Cabeçalho com logo no topo centralizado e os controles abaixo
    cabecalho_fixo = ft.Container(
        bgcolor=COR_FUNDO,
        padding=ft.Padding(20, 6, 20, 12),
        border=ft.Border(bottom=ft.BorderSide(1, COR_BORDA)),
        content=ft.Column([
            progresso,
            bloco_usuario_topo,
            ft.Row([btn_logo_interativo], alignment=ft.MainAxisAlignment.CENTER),
            linha_inferior_menu
        ], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    )

    # -------------------------------------------------------------
    # ADAPTAÇÃO DINÂMICA
    # -------------------------------------------------------------
    def ajustar_layout_responsivo(e=None):
        largura_janela = page.width if page.width else 1000
        if largura_janela < 720:
            campo_busca.width = max(180, int(largura_janela - 150))
            container_sugestoes.width = max(200, int(largura_janela - 100))
            btn_logo_interativo.content.height = 50
            btn_tab_bib.content.height = 40
            titulo_trends.width = None
            container_sugestoes.left = 20
            container_sugestoes.top = 150
        else:
            campo_busca.width = 224
            container_sugestoes.width = 280
            btn_logo_interativo.content.height = 65
            btn_tab_bib.content.height = 45
            titulo_trends.width = 1100
            # Alinha o dropdown flutuante logo abaixo do campo no desktop
            container_sugestoes.left = max(0, int((largura_janela / 2) - 40))
            container_sugestoes.top = 142
        page.update()

    page.on_resized = ajustar_layout_responsivo

    # -------------------------------------------------------------
    # VIEWS ROLÁVEIS INDEPENDENTES
    # -------------------------------------------------------------
    titulo_trends = ft.Container(
        content=ft.Text("Filmes em Alta (TMDb Trends)", size=15, weight="bold", color=COR_TEXTO_CLARO),
        alignment=ft.Alignment(-1, 0),
        width=1100,
        padding=ft.Padding(0, 10, 0, 0)
    )

    view_inicio = ft.Container(
        expand=True,
        padding=ft.Padding(12, 0, 12, 10),
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            on_scroll=ao_rolar_inicio,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[
                titulo_trends,
                grade_populares,
                ft.Container(
                    content=spinner_carregamento,
                    alignment=ft.Alignment(0, 0),
                    padding=ft.Padding(0, 15, 0, 35)
                )
            ]
        )
    )

    view_biblioteca = ft.Container(
        expand=True,
        visible=False,
        padding=ft.Padding(12, 10, 12, 10),
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[coluna_biblioteca_itens]
        )
    )

    def alternar_tela(indice):
        fechar_dialogo(modal_detalhes)
        if container_sugestoes.visible:
            container_sugestoes.visible = False

        if indice == 0:
            view_inicio.visible = True
            view_biblioteca.visible = False
            btn_tab_bib.border = criar_borda(2, "transparent")
            btn_logo_interativo.border = criar_borda(2, COR_PETROLEO)
        elif indice == 1:
            carregar_biblioteca()
            view_inicio.visible = False
            view_biblioteca.visible = True
            btn_tab_bib.border = criar_borda(2, COR_PETROLEO)
            btn_logo_interativo.border = criar_borda(2, "transparent")

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

    # -------------------------------------------------------------
    # TELA DE AUTENTICAÇÃO
    # -------------------------------------------------------------
    logo_login = ft.Image(src="logo.png", height=65, fit="contain")

    txt_auth_titulo = ft.Text("Entrar", size=18, weight="bold", color=COR_TEXTO_CLARO)
    txt_auth_erro = ft.Text("", size=12, color="#ef4444")
    
    txt_auth_user = ft.TextField(
        label="Nome de Usuário",
        label_style=ft.TextStyle(color="#94a3b8"),
        bgcolor=COR_FUNDO,
        dense=True,
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        width=300
    )
    txt_auth_pass = ft.TextField(
        label="Senha",
        label_style=ft.TextStyle(color="#94a3b8"),
        password=True,
        can_reveal_password=True,
        bgcolor=COR_FUNDO,
        dense=True,
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        width=300
    )
    txt_auth_pass_confirm = ft.TextField(
        label="Confirmar Nova Senha",
        label_style=ft.TextStyle(color="#94a3b8"),
        password=True,
        can_reveal_password=True,
        bgcolor=COR_FUNDO,
        dense=True,
        border_radius=8,
        border_color=COR_BORDA,
        focused_border_color=COR_PETROLEO,
        width=300,
        visible=False
    )

    chk_manter_conectado = ft.Checkbox(
        label="Permanecer conectado",
        label_style=ft.TextStyle(size=12, color=COR_TEXTO_CLARO),
        value=True,
        fill_color=COR_PETROLEO,
        check_color="white"
    )
    container_chk_manter = ft.Container(
        content=chk_manter_conectado,
        width=300,
        alignment=ft.Alignment(-1, 0),
        visible=True
    )

    modo_auth = {"modo": "login"}

    def definir_modo_auth(novo_modo):
        modo_auth["modo"] = novo_modo
        txt_auth_erro.value = ""
        txt_auth_pass_confirm.visible = (novo_modo == "recuperar")
        container_chk_manter.visible = (novo_modo == "login")
        
        if novo_modo == "login":
            txt_auth_titulo.value = "Entrar"
            txt_auth_pass.label = "Senha"
            btn_executar_auth.bgcolor = COR_PETROLEO
            btn_executar_auth.content = ft.Text("Entrar", color="white", weight="bold")
            btn_alternar_auth.content = ft.Text("Não tem uma conta? Cadastre-se", color="#94a3b8", size=12)
            btn_recuperar_auth.visible = True
            
        elif novo_modo == "cadastro":
            txt_auth_titulo.value = "Criar Nova Conta"
            txt_auth_pass.label = "Senha"
            btn_executar_auth.bgcolor = COR_PETROLEO
            btn_executar_auth.content = ft.Text("Cadastrar Nova Conta", color="white", weight="bold")
            btn_alternar_auth.content = ft.Text("Já tem uma conta? Entrar", color="#94a3b8", size=12)
            btn_recuperar_auth.visible = False
            
        elif novo_modo == "recuperar":
            txt_auth_titulo.value = "Recuperar / Trocar Senha"
            txt_auth_pass.label = "Nova Senha"
            btn_executar_auth.bgcolor = COR_VERMELHO_PLAY
            btn_executar_auth.content = ft.Text("Salvar Nova Senha", color="white", weight="bold")
            btn_alternar_auth.content = ft.Text("Lembrou da senha? Voltar ao Login", color="#94a3b8", size=12)
            btn_recuperar_auth.visible = False
            
        page.update()

    def iniciar_sessao(uid, username, persistir=True):
        sessao_usuario["id"] = int(uid)
        sessao_usuario["username"] = str(username)
        lbl_user_tag.value = f"👤 {username}"
        
        if persistir:
            try:
                page.run_javascript(f"document.cookie = 'user_id={uid}; max-age=31536000; path=/;';")
                page.run_javascript(f"document.cookie = 'username={username}; max-age=31536000; path=/;';")
                page.run_javascript("document.cookie = 'manter_conectado=true; max-age=31536000; path=/;';")
                page.client_storage.set("user_id", str(uid))
                page.client_storage.set("username", str(username))
                page.client_storage.set("manter_conectado", "true")
            except Exception:
                pass
        else:
            try:
                page.run_javascript("document.cookie = 'user_id=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';")
                page.run_javascript("document.cookie = 'username=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';")
                page.run_javascript("document.cookie = 'manter_conectado=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';")
                page.client_storage.clear()
            except Exception:
                pass

        spinner_autologin.visible = False
        card_auth.visible = False
        layout_mestre.visible = True
        ajustar_layout_responsivo()
        page.update()

        paginacao["pagina_atual"] = 1
        paginacao["carregando"] = False
        paginacao["fim"] = False
        paginacao["modo_api"] = "trending"
        paginacao["ids_carregados"].clear()
        grade_populares.controls.clear()

        carregar_populares()
        threading.Timer(0.6, lambda: carregar_populares(incrementar=True)).start()
        threading.Timer(1.4, lambda: carregar_populares(incrementar=True)).start()

    def processar_auth(e):
        usuario = txt_auth_user.value.strip() if txt_auth_user.value else ""
        senha = txt_auth_pass.value.strip() if txt_auth_pass.value else ""
        senha_confirm = txt_auth_pass_confirm.value.strip() if txt_auth_pass_confirm.value else ""

        if not usuario or not senha:
            txt_auth_erro.value = "Preencha todos os campos obrigatórios."
            page.update()
            return

        if len(usuario) < 3:
            txt_auth_erro.value = "O usuário deve ter pelo menos 3 caracteres."
            page.update()
            return

        if len(senha) < 4:
            txt_auth_erro.value = "A senha deve ter pelo menos 4 caracteres."
            page.update()
            return

        user_auth_id = None
        user_auth_nome = None
        conn = None

        try:
            conn = sqlite3.connect(DB_FILE, timeout=15)
            c = conn.cursor()

            if modo_auth["modo"] == "cadastro":
                c.execute("SELECT id FROM usuarios WHERE username = ?", (usuario,))
                if c.fetchone():
                    txt_auth_erro.value = "Este nome de usuário já está em uso."
                    page.update()
                    return

                p_hash = gerar_hash_senha(senha)
                c.execute("INSERT INTO usuarios (username, password_hash) VALUES (?, ?)", (usuario, p_hash))
                user_auth_id = c.lastrowid
                user_auth_nome = usuario
                conn.commit()

            elif modo_auth["modo"] == "login":
                c.execute("SELECT id, password_hash FROM usuarios WHERE username = ?", (usuario,))
                user_row = c.fetchone()
                if not user_row or not verificar_senha(senha, user_row[1]):
                    txt_auth_erro.value = "Usuário ou senha inválidos."
                    page.update()
                    return

                user_auth_id = user_row[0]
                user_auth_nome = usuario

            elif modo_auth["modo"] == "recuperar":
                if senha != senha_confirm:
                    txt_auth_erro.value = "As senhas digitadas não coincidem."
                    page.update()
                    return

                c.execute("SELECT id FROM usuarios WHERE username = ?", (usuario,))
                user_row = c.fetchone()
                if not user_row:
                    txt_auth_erro.value = "Usuário não encontrado."
                    page.update()
                    return

                novo_hash = gerar_hash_senha(senha)
                c.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (novo_hash, user_row[0]))
                conn.commit()
                user_auth_id = user_row[0]
                user_auth_nome = usuario

        except Exception as err:
            txt_auth_erro.value = f"Erro no banco: {err}"
            page.update()
            return
        finally:
            if conn:
                conn.close()

        if user_auth_id and user_auth_nome:
            deve_manter = chk_manter_conectado.value if modo_auth["modo"] == "login" else True
            iniciar_sessao(user_auth_id, user_auth_nome, persistir=deve_manter)

    btn_executar_auth = ft.Button(
        content=ft.Text("Entrar", color="white", weight="bold"),
        bgcolor=COR_PETROLEO,
        width=300,
        height=40,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        on_click=processar_auth
    )

    btn_alternar_auth = ft.Button(
        content=ft.Text("Não tem uma conta? Cadastre-se", color="#94a3b8", size=12),
        bgcolor="transparent",
        on_click=lambda e: definir_modo_auth("cadastro" if modo_auth["modo"] == "login" else "login")
    )

    btn_recuperar_auth = ft.Button(
        content=ft.Text("Esqueceu a senha?", color="#64748b", size=11),
        bgcolor="transparent",
        on_click=lambda e: definir_modo_auth("recuperar")
    )

    card_interno_auth = ft.Container(
        width=360,
        bgcolor=COR_CARD,
        padding=24,
        border_radius=12,
        border=criar_borda(1.5, COR_BORDA),
        content=ft.Column([
            logo_login,
            ft.Container(height=4),
            txt_auth_titulo,
            txt_auth_erro,
            txt_auth_user,
            txt_auth_pass,
            txt_auth_pass_confirm,
            container_chk_manter,
            ft.Container(height=4),
            btn_executar_auth,
            btn_alternar_auth,
            btn_recuperar_auth
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8)
    )

    card_auth = ft.Container(
        alignment=ft.Alignment(0, 0),
        padding=ft.Padding(0, 60, 0, 0),
        content=card_interno_auth,
        visible=False
    )

    spinner_autologin = ft.Container(
        alignment=ft.Alignment(0, 0),
        padding=ft.Padding(0, 150, 0, 0),
        content=ft.ProgressRing(width=36, height=36, stroke_width=3, color=COR_PETROLEO),
        visible=True
    )

    page.add(spinner_autologin, card_auth, layout_mestre)
    page.update()

    # -------------------------------------------------------------
    # RECUPERAÇÃO DE SESSÃO
    # -------------------------------------------------------------
    def verificar_sessao_salva():
        time.sleep(0.3)
        saved_uid = None
        saved_user = None
        saved_manter = None

        try:
            saved_uid = page.client_storage.get("user_id")
            saved_user = page.client_storage.get("username")
            saved_manter = page.client_storage.get("manter_conectado")
        except Exception:
            pass

        if not saved_uid or str(saved_manter).lower() != "true":
            try:
                cookies = page.cookies
                if cookies:
                    saved_uid = cookies.get("user_id")
                    saved_user = cookies.get("username")
                    saved_manter = cookies.get("manter_conectado")
            except Exception:
                pass

        if saved_uid and saved_user and (str(saved_manter).lower() == "true"):
            iniciar_sessao(saved_uid, saved_user, persistir=True)
        else:
            spinner_autologin.visible = False
            definir_modo_auth("login")
            card_auth.visible = True
            layout_mestre.visible = False
            ajustar_layout_responsivo()
            page.update()

    threading.Thread(target=verificar_sessao_salva, daemon=True).start()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 8550))
    ft.run(
        main,
        view=ft.AppView.WEB_BROWSER,
        host="0.0.0.0",
        port=porta,
        assets_dir=DIR_ASSETS
    )
