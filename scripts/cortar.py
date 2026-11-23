"""Passos 3 e 4: junta as notas que a IA deu, fica com os melhores e monta os cortes verticais.

Cada corte: câmera do streamer em cima, jogo embaixo, título de gancho, legenda palavra por palavra
e um .txt com a legenda do post e as hashtags.
"""
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from comum import (CORTES, YUNET, YUNET_URL, gravar_json, hms, ler_json, pasta_temp_live, rodar, segundos, tem_nvenc, ytdlp)  # noqa: F401

FONTES = Path(__file__).resolve().parent.parent / "fontes"
L, A = 1080, 1920          # vídeo vertical
CAM_H = 590                # faixa da câmera em cima (30.7% da altura, estilo TikTok Grota Clips)
JOGO_H = A - CAM_H         # faixa do jogo embaixo (69.3% da altura, 1330px)


# ================================================================ escolher
CHAVES = {"inicio": ("inicio", "início", "start", "comeco", "começo", "de"),
          "fim": ("fim", "end", "final", "ate", "até"),
          "nota": ("nota", "score", "pontos", "pontuacao", "pontuação"),
          "titulo": ("titulo", "título", "title", "gancho", "hook"),
          "post": ("post", "legenda", "caption", "descricao", "descrição")}


def ler_tolerante(arq):
    """A IA às vezes escreve o JSON com ```json, vírgula sobrando ou comentário. Aceita tudo isso."""
    t = Path(arq).read_text(encoding="utf-8", errors="ignore").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t)
    for tentativa in (t, None):
        if tentativa is None:
            ini = [i for i in (t.find("["), t.find("{")) if i >= 0]
            fim = max(t.rfind("]"), t.rfind("}"))
            if not ini or fim < 0:
                return None
            tentativa = re.sub(r"//[^\n]*", "", t[min(ini):fim + 1])
            tentativa = re.sub(r",\s*([\]}])", r"\1", tentativa)
        try:
            d = json.loads(tentativa)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict):
            d = d.get("momentos") or d.get("cortes") or d.get("moments") or [d]
        return d if isinstance(d, list) else None
    return None


def _campo(m, nome):
    for k in CHAVES[nome]:
        if k in m and m[k] not in (None, ""):
            return m[k]
    return None


def _titulo_auto(pasta, s, e):
    trans = ler_json(pasta / "transcricao.json", {}).get("segmentos", [])
    falas = [t for a, b, t in trans if s <= a <= e and len(t.split()) >= 3]
    if not falas:
        return "OLHA O QUE ACONTECEU NA LIVE"
    t = max(falas, key=lambda x: (x.count("!") + len(re.findall(r"[A-ZÁÉÍÓÚÃÕÇ]{3,}", x)), len(x)))
    t = re.sub(r"\s+", " ", t).strip(" .,…").upper()
    return (t[:42].rsplit(" ", 1)[0] + "…") if len(t) > 45 else t


def momentos_automaticos(pasta):
    """Sem a IA ter escrito nada: usa os trechos mais quentes (pico de grito/chat) como cortes."""
    cand = ler_json(pasta / "candidatos.json", [])
    nome = ler_json(pasta / "info.json", {}).get("uploader") or ""
    out = []
    for c in cand:
        s, e = max(0, c["pico"] - 15), c["pico"] + 30
        out.append({"inicio": s, "fim": e, "nota": c["calor"], "titulo": _titulo_auto(pasta, s, e),
                    "post": f"Olha isso na live {('do ' + nome) if nome else ''} 😳 #gta6 #gtavi #gta #cortes #streamer",
                    "_auto": True})
    return out


def escolher(pasta, manter=3, minimo=20, maximo=60, auto=False):
    dur_live = float(ler_json(pasta / "info.json", {}).get("duration") or 10 ** 7)
    brutos, ruins = [], []
    for arq in sorted((pasta / "momentos").glob("*.json")):
        dados = ler_tolerante(arq)
        if dados is None:
            ruins.append(f"{arq.name}: não é um JSON que dá pra ler")
            continue
        brutos += [(arq.stem, m) for m in dados]
    if auto or not brutos:
        if not auto:
            print("A IA não escreveu nenhum momento ainda: usando os trechos mais quentes da live (modo automático).")
        brutos = [("automatico", m) for m in momentos_automaticos(pasta)]
    todos = []
    for origem, m in brutos:
        try:
            s, e = segundos(_campo(m, "inicio")), segundos(_campo(m, "fim"))
        except (TypeError, ValueError, AttributeError):
            ruins.append(f"{origem}: tempo que não entendi em {str(m)[:70]}")
            continue
        if e < s:
            s, e = e, s
        s, e = max(0.0, s), min(dur_live, e)
        if e - s < minimo:
            e = min(dur_live, s + minimo)
        if e - s > maximo:
            e = s + maximo
        try:
            nota = float(str(_campo(m, "nota") or 70).split("/")[0])
        except ValueError:
            nota = 70.0
        titulo = str(_campo(m, "titulo") or "").strip() or _titulo_auto(pasta, s, e)
        post = str(_campo(m, "post") or "").strip()
        if "#gta6" not in post.lower():
            post = (post + " #gta6 #gtavi #gta #cortes").strip()
        todos.append({**m, "titulo": titulo, "post": post, "nota": nota, "_s": s, "_e": e, "_bloco": origem})
    if ruins:
        print("ATENÇÃO, pulei:", *ruins, sep="\n  ")
    todos.sort(key=lambda m: -m["nota"])
    escolhidos = []
    for m in todos:
        if any(m["_s"] < o["_e"] and o["_s"] < m["_e"] for o in escolhidos):
            continue  # sobrepõe um corte melhor
        escolhidos.append(m)
        if len(escolhidos) >= manter:
            break
    escolhidos.sort(key=lambda m: m["_s"])
    gravar_json(pasta / "escolhidos.json", {"possiveis": len(todos), "cortes": escolhidos})
    print(f"\nAchei {len(todos)} momentos possíveis e fiquei com os {len(escolhidos)} melhores:")
    for i, m in enumerate(escolhidos, 1):
        print(f"  {i}. [{hms(m['_s'])}–{hms(m['_e'])}] nota {m['nota']:.0f}  {m.get('titulo', '')}")
    return escolhidos


# ================================================================ câmera do streamer
def dimensoes_video(video):
    """Lê largura e altura reais do vídeo rapidamente via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=s=x:p=0", str(video)],
            capture_output=True, text=True, timeout=15
        )
        partes = r.stdout.strip().splitlines()[0].split("x")
        w, h = int(partes[0]), int(partes[1])
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return 1920, 1080


def duracao_video(video, padrao=45.0):
    """Lê duração do vídeo com fallback seguro (nunca quebra em float(''))."""
    for cmd in (
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(video)],
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            txt = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
            if txt and txt.upper() != "N/A":
                val = float(txt)
                if val > 0.5:
                    return val
        except Exception:
            pass
    return float(padrao)


def achar_camera(video):
    """Procura o rosto em 24 quadros do trecho, agrupa por posição e devolve a caixa (x, y, l, a) da webcam."""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video))
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if W <= 0 or H <= 0:
        cap.release()
        W, H = dimensoes_video(video)
        return W, H, None
    if not YUNET.exists():
        YUNET.parent.mkdir(parents=True, exist_ok=True)
        try:
            import urllib.request
            urllib.request.urlretrieve(YUNET_URL, str(YUNET))
        except Exception:
            pass
    if not YUNET.exists():
        cap.release()
        return W, H, None
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    esc = 1280 / W
    h_esc = max(1, int(H * esc))
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (1280, h_esc), 0.6)
    amostras = 24
    caixas, lidos = [], 0
    for k in range(amostras):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (k + 0.5) / amostras))
        ok, q = cap.read()
        if not ok:
            continue
        lidos += 1
        _, rostos = det.detect(cv2.resize(q, (1280, h_esc)))
        for r in rostos if rostos is not None else []:
            if r[14] >= 0.7 and r[3] / esc > H * 0.035:
                caixas.append([v / esc for v in r[:4]] + [k])
    cap.release()
    if len(caixas) < 3 or lidos == 0:
        return W, H, None
    c = np.array(caixas)
    centros = c[:, :2] + c[:, 2:4] / 2
    raio = W * 0.08
    melhor, melhor_nota = None, -1.0
    for i in range(len(c)):
        viz = np.linalg.norm(centros - centros[i], axis=1) < raio
        quadros = len(set(c[viz, 4].astype(int)))
        borda = max(abs(centros[i, 0] - W / 2) / (W / 2), abs(centros[i, 1] - H / 2) / (H / 2))
        nota = quadros + 0.5 * borda
        if nota > melhor_nota:
            melhor_nota, melhor = nota, viz
    grupo = c[melhor]
    if len(set(grupo[:, 4].astype(int))) < max(3, int(lidos * 0.3)):
        return W, H, None
    fh_med = float(np.median(grupo[:, 3]))
    if fh_med > H * 0.30:  # rosto muito grande (>30% da tela) = podcast / live só de câmera
        return W, H, None
    x1 = float(np.percentile(grupo[:, 0], 10))
    y1 = float(np.percentile(grupo[:, 1], 10))
    x2 = float(np.percentile(grupo[:, 0] + grupo[:, 2], 90))
    y2 = float(np.percentile(grupo[:, 1] + grupo[:, 3], 90))
    fcx, fcy = (x1 + x2) / 2, (y1 + y2) / 2
    fw_eff = max(float(np.median(grupo[:, 2])), x2 - x1)
    fh_eff = max(fh_med, y2 - y1)
    return W, H, [fcx - fw_eff / 2, fcy - fh_eff / 2, fw_eff, fh_eff]


def obter_camera_live(pasta, trecho, estilo):
    """Detecta a câmera uma única vez por live (salva em camera.json) e aplica fallback calibrado no modo split."""
    W, H = dimensoes_video(trecho)
    if estilo == "blur":
        print("      estilo: fundo desfocado (blur) com jogo centralizado", flush=True)
        return W, H, None
    cache_cam = pasta / "camera.json"
    cam = ler_json(cache_cam)
    if cam and cam.get("W") == W and cam.get("H") == H and cam.get("rosto") is not None:
        return W, H, cam["rosto"]
    print("      procurando a câmera do streamer (1x por live)…", flush=True)
    W_det, H_det, rosto = achar_camera(trecho)
    W, H = (W_det or W), (H_det or H)
    if rosto is None and estilo == "split":
        # Fallback calibrado (canto superior esquerdo - padrão Paulinho o LOKO) em vez de cair para blur
        rosto = [0.05 * W, 0.05 * H, 0.08 * W, 0.08 * H]
        print("      usando posição calibrada padrão da webcam (canto superior esquerdo)", flush=True)
    elif rosto is not None:
        print("      câmera do streamer achada e salva em cache: câmera em cima, jogo embaixo", flush=True)
    else:
        print("      sem caixinha de câmera: imagem inteira no meio com fundo desfocado", flush=True)
    if rosto is not None:
        gravar_json(cache_cam, {"W": W, "H": H, "rosto": rosto})
    return W, H, rosto


def _par(v):
    return int(v) // 2 * 2


def filtro(W, H, rosto):
    estilo = os.environ.get("CLIPPER_ESTILO", "split").lower()
    if rosto is None or estilo == "blur":
        # Sem câmera ou estilo blur: jogo no meio, fundo desfocado
        return ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:3[bg];"
                "[0:v]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p,ass=legenda.ass:fontsdir=fontes[v]")
    fx, fy, fw, fh = rosto
    fcx, fcy = fx + fw / 2, fy + fh / 2

    # Centraliza o recorte no rosto detectado (em vez de canto fixo) para não cortar metade da cabeça
    zoom = float(os.environ.get("CLIPPER_CAM_ZOOM", "4.8"))
    cw = _par(min(max(fw * zoom, fh * 2.8 * L / CAM_H, 0.22 * W), 0.48 * W))
    ch = _par(cw * CAM_H / L)
    cx = _par(fcx - cw / 2)
    cy = _par(fcy - 0.38 * ch)

    cx = _par(min(max(cx, 0), W - cw))
    cy = _par(min(max(cy, 0), H - ch))

    gw = int(min(W, H * L / JOGO_H)) // 2 * 2
    gx = int((W - gw) / 2) // 2 * 2

    return (f"[0:v]crop={cw}:{ch}:{cx}:{cy},scale={L}:{CAM_H}:flags=lanczos,unsharp=5:5:0.7:5:5:0.0,setsar=1[cam];"
            f"[0:v]crop={gw}:{H}:{gx}:0,scale={L}:{JOGO_H}:flags=lanczos,setsar=1[jogo];"
            f"[cam][jogo]vstack=inputs=2,format=yuv420p,ass=legenda.ass:fontsdir=fontes[v]")


# ================================================================ legenda
def _ass_tempo(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _limpo(txt):
    return txt.replace("{", "(").replace("}", ")").replace("\\", "/").strip()


def audio_16k(arquivo):
    """O ffmpeg lê o áudio (não depende do leitor do faster-whisper, que quebra entre versões)."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arquivo), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768


_WHISPER_CACHE = {}


def _obter_whisper(modelo):
    """Carrega o WhisperModel uma única vez e reutiliza em todos os cortes."""
    from faster_whisper import WhisperModel
    dispositivo = os.environ.get("CLIPPER_DEVICE", "auto")
    computacao = os.environ.get("CLIPPER_COMPUTE_TYPE", "auto")
    chave = (modelo, dispositivo, computacao)
    if chave not in _WHISPER_CACHE:
        try:
            _WHISPER_CACHE[chave] = WhisperModel(modelo, device=dispositivo, compute_type=computacao)
        except Exception:
            _WHISPER_CACHE[chave] = WhisperModel(modelo, device="cpu", compute_type="int8")
    return _WHISPER_CACHE[chave]


def palavras_do_trecho(video, idioma, modelo="small"):
    from faster_whisper import WhisperModel
    audio = audio_16k(video)
    m = _obter_whisper(modelo)
    try:
        segs, _ = m.transcribe(audio, language=idioma, word_timestamps=True, vad_filter=True,
                               beam_size=1, condition_on_previous_text=False)
        return [(w.start, w.end, w.word.strip()) for s in segs for w in (s.words or []) if w.word.strip()]
    except Exception:
        chave_cpu = (modelo, "cpu", "int8")
        if chave_cpu not in _WHISPER_CACHE:
            _WHISPER_CACHE[chave_cpu] = WhisperModel(modelo, device="cpu", compute_type="int8")
        # Atualiza cache padrão para não falhar de novo no próximo corte
        dispositivo = os.environ.get("CLIPPER_DEVICE", "auto")
        computacao = os.environ.get("CLIPPER_COMPUTE_TYPE", "auto")
        _WHISPER_CACHE[(modelo, dispositivo, computacao)] = _WHISPER_CACHE[chave_cpu]
        segs, _ = _WHISPER_CACHE[chave_cpu].transcribe(audio, language=idioma, word_timestamps=True, vad_filter=True,
                                                       beam_size=1, condition_on_previous_text=False)
        return [(w.start, w.end, w.word.strip()) for s in segs for w in (s.words or []) if w.word.strip()]


def quebrar_titulo_banner(titulo, max_carac=24):
    palavras = titulo.split()
    linhas, atual = [], []
    tam = 0
    for p in palavras:
        if tam + len(p) + (1 if atual else 0) > max_carac and atual:
            linhas.append(" ".join(atual))
            atual = [p]
            tam = len(p)
        else:
            atual.append(p)
            tam += len(p) + (1 if len(atual) > 1 else 0)
    if atual:
        linhas.append(" ".join(atual))
    return r"\N".join(linhas)


def escrever_ass(caminho, titulo, palavras, dur, com_camera):
    y_titulo = 670 if com_camera else 520
    y_leg = 1620
    titulo_formatado = quebrar_titulo_banner(_limpo(titulo).upper())
    dur_gancho = min(3.8, dur)
    linhas = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {L}", f"PlayResY: {A}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        "Style: Gancho,Montserrat ExtraBold,50,&H00FFFFFF,&H00FFFFFF,&H000808D0,&H000808D0,-1,0,0,0,100,100,0,0,3,22,0,5,50,50,0,1",
        "Style: Leg,Montserrat ExtraBold,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,8,2,2,40,40,180,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 1,0:00:00.00,{_ass_tempo(dur_gancho)},Gancho,,0,0,0,,{{\\fad(120,300)\\pos(540,{y_titulo})}}{titulo_formatado}",
    ]
    grupos = [palavras[i:i + 3] for i in range(0, len(palavras), 3)]
    for g, grupo in enumerate(grupos):
        prox = grupos[g + 1][0][0] if g + 1 < len(grupos) else dur
        for k, (s, e, _) in enumerate(grupo):
            fim = grupo[k + 1][0] if k + 1 < len(grupo) else (prox if prox - e < 0.6 else e + 0.25)
            fim = max(s + 0.12, fim)
            txt = " ".join(("{\\c&H0020FFFF&}" if j == k else "{\\c&HFFFFFF&}") + _limpo(w).upper()
                           for j, (_, _, w) in enumerate(grupo))
            linhas.append(f"Dialogue: 0,{_ass_tempo(s)},{_ass_tempo(fim)},Leg,,0,0,0,,{{\\pos(540,{y_leg})}}{txt}")
    Path(caminho).write_text("\n".join(linhas) + "\n", encoding="utf-8")


# ================================================================ baixar só o pedaço
def formato_download():
    max_h = os.environ.get("CLIPPER_MAX_RES", "1440")
    return f"bv*[height<={max_h}]+ba/b[height<={max_h}]/best"


def tem_video(arq):
    """Checagem ultra-rápida (~0.05s) de integridade do vídeo via cabeçalho ffprobe."""
    p = Path(arq)
    if not p.exists() or p.stat().st_size < 50_000:
        return False
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_type", "-of", "csv=p=0", str(p)],
            capture_output=True, text=True, timeout=15
        )
        return "video" in r.stdout.lower()
    except Exception:
        return p.stat().st_size > 100_000


_UA_CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def baixar_trecho(pasta, url, s, e, destino, silencioso=False):
    """Baixa só os segundos do corte em cópia direta de stream (sem re-encode na CPU!).
    1º jeito: yt-dlp --download-sections com mux MKV (aceita VP9+Opus/AV1/H264 em segundos).
    2º jeito: ffmpeg com User-Agent Chrome pulando direto pro minuto certo."""
    max_h = os.environ.get("CLIPPER_MAX_RES", "1440")
    if not silencioso:
        print(f"      baixando pedaço em {max_h}p60 (stream copy turbo)…", flush=True)
    fmt = formato_download()
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        rodar(ytdlp() + ["-f", fmt, "--no-playlist", "--no-warnings", "-q", "--download-sections",
                         f"*{s:.2f}-{e:.2f}", "--merge-output-format", "mkv",
                         "-o", str(destino), url], timeout=900)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    if destino.exists() and tem_video(destino):
        return destino
    for ext in ("mkv", "webm", "mp4", "part"):
        for cand in (destino.with_suffix(f".{ext}"), destino.parent / f"{destino.name}.{ext}"):
            if cand != destino and cand.exists() and tem_video(cand):
                cand.replace(destino)
                return destino
    destino.unlink(missing_ok=True)
    if not silencioso:
        print("      tentando de outro jeito (pulando direto pro minuto do corte)…", flush=True)
    r = subprocess.run(ytdlp() + ["-f", fmt, "-g", "--no-playlist", "--no-warnings", url],
                       capture_output=True, text=True)
    links = [l for l in r.stdout.split() if l.startswith("http")]
    if links:
        entrada = []
        for l in links[:2]:
            entrada += ["-user_agent", _UA_CHROME, "-ss", f"{s:.2f}", "-i", l]
        mapa = ["-map", "0:v:0", "-map", f"{len(links[:2]) - 1}:a:0?"]
        try:
            rodar(["ffmpeg", "-y", "-loglevel", "error", *entrada, "-t", f"{e - s:.2f}", *mapa,
                   "-c", "copy", str(destino)], timeout=900)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    if destino.exists() and tem_video(destino):
        return destino
    destino.unlink(missing_ok=True)
    raise SystemExit("NÃO CONSEGUI BAIXAR esse pedaço do vídeo. Rode 'instalar' (atualiza o baixador) e depois "
                     "'fazer' de novo: os cortes que já ficaram prontos não são refeitos.")


def _args_encoder():
    """Usa GPU NVIDIA NVENC (5x-10x mais rápido) se disponível; caso contrário libx264 CPU."""
    if tem_nvenc():
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "16", "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"]


# ================================================================ fazer
def fazer(pasta, modelo_legenda="small"):
    info = ler_json(pasta / "info.json", {})
    escolhidos = ler_json(pasta / "escolhidos.json", {}).get("cortes")
    if not escolhidos:
        raise SystemExit("Nenhum corte escolhido ainda. Rode antes: clip.py escolher " + pasta.name)
    idioma = ler_json(pasta / "transcricao.json", {}).get("idioma")
    destino = CORTES / pasta.name
    destino.mkdir(parents=True, exist_ok=True)
    temp_base = pasta_temp_live(pasta)
    usa_nvenc = tem_nvenc()
    enc_args = _args_encoder()
    forcar = os.environ.get("CLIPPER_FORCAR_REFAZER", "0") == "1"
    estilo = os.environ.get("CLIPPER_ESTILO", "auto").lower()
    print(f"      [Turbo] Encoder: {'GPU NVIDIA NVENC (h264_nvenc)' if usa_nvenc else 'CPU (libx264)'} | Temp: {temp_base}", flush=True)

    def _precisa_fazer(idx, item):
        s_, e_ = item["_s"], item["_e"]
        tdir_c = pasta / f"corte_{idx:02d}"
        saida_ = destino / f"corte_{idx:02d}.mp4"
        assin_ = f"{s_:.2f}-{e_:.2f}-{item.get('titulo', '')}"
        if not forcar and saida_.exists():
            feito_arq = tdir_c / "feito.txt"
            if feito_arq.exists() and feito_arq.read_text(encoding="utf-8") == assin_:
                return False
            if not feito_arq.exists() and saida_.stat().st_size > 1_000_000:
                return False
        return True

    def _preparar_trecho(idx, item, silencioso=False):
        s_, e_ = item["_s"], item["_e"]
        tdir_t = temp_base / f"corte_{idx:02d}"
        tdir_t.mkdir(parents=True, exist_ok=True)
        trecho_ = tdir_t / "trecho.mkv"
        de_txt = tdir_t / "de.txt"
        if forcar:
            trecho_.unlink(missing_ok=True)
            de_txt.unlink(missing_ok=True)
        if de_txt.exists() and de_txt.read_text() != f"{s_:.2f}-{e_:.2f}":
            trecho_.unlink(missing_ok=True)
        if trecho_.exists() and not tem_video(trecho_):
            trecho_.unlink(missing_ok=True)
        if not trecho_.exists():
            baixar_trecho(pasta, info["url"], s_, e_, trecho_, silencioso=silencioso)
            de_txt.write_text(f"{s_:.2f}-{e_:.2f}")
        return trecho_

    feitos = []
    # Pré-carrega o próximo download em paralelo enquanto o corte atual legenda e renderiza
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut_prox = None
        prox_idx = None

        def _agendar_proximo(atual_idx):
            nonlocal fut_prox, prox_idx
            fut_prox, prox_idx = None, None
            for j in range(atual_idx + 1, len(escolhidos) + 1):
                if _precisa_fazer(j, escolhidos[j - 1]):
                    prox_idx = j
                    fut_prox = pool.submit(_preparar_trecho, j, escolhidos[j - 1], True)
                    break

        for i, m in enumerate(escolhidos, 1):
            s, e = m["_s"], m["_e"]
            print(f"\n[4/4] Corte {i}/{len(escolhidos)}: {m.get('titulo', '')}  ({hms(s)}–{hms(e)})", flush=True)
            tdir_cache = pasta / f"corte_{i:02d}"
            tdir_cache.mkdir(exist_ok=True)
            tdir_tmp = temp_base / f"corte_{i:02d}"
            tdir_tmp.mkdir(parents=True, exist_ok=True)
            saida = destino / f"corte_{i:02d}.mp4"
            assinatura = f"{s:.2f}-{e:.2f}-{m.get('titulo', '')}"
            if not _precisa_fazer(i, m):
                print("      já estava pronto", flush=True)
                feitos.append(saida)
                continue

            if fut_prox is not None and prox_idx == i:
                print("      usando pré-download paralelo…", flush=True)
                trecho = fut_prox.result()
                fut_prox, prox_idx = None, None
            else:
                trecho = _preparar_trecho(i, m, silencioso=False)

            # Dispara o download do próximo corte em segundo plano imediatamente
            _agendar_proximo(i)

            dur = duracao_video(trecho, padrao=max(10.0, e - s))
            W, H, rosto = obter_camera_live(pasta, trecho, estilo)
            print("      legenda palavra por palavra…", flush=True)
            palavras = palavras_do_trecho(trecho, idioma, modelo_legenda)
            escrever_ass(tdir_tmp / "legenda.ass", m.get("titulo", ""), palavras, dur, rosto is not None)
            (tdir_tmp / "fontes").mkdir(exist_ok=True)
            for fonte in FONTES.glob("*.ttf"):
                dest_f = tdir_tmp / "fontes" / fonte.name
                if not dest_f.exists():
                    shutil.copy(fonte, dest_f)

            saida_render = (tdir_tmp / f"render_{i:02d}.mp4") if temp_base != pasta else saida
            print(f"      renderizando 1080x1920@60fps ({'GPU NVENC' if usa_nvenc else 'CPU'})…", flush=True)
            rodar(["ffmpeg", "-y", "-loglevel", "error", "-i", trecho.name, "-filter_complex",
                   filtro(W, H, rosto), "-map", "[v]", "-map", "0:a?", *enc_args,
                   "-r", "60", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                   str(saida_render.resolve())], cwd=tdir_tmp)

            if saida_render != saida:
                shutil.copy2(saida_render, saida)
            post = (f"{m.get('titulo', '')}\n\n{m.get('post', '').strip()}\n\n"
                    f"Corte da live de {info.get('uploader') or info.get('channel')}: {info.get('webpage_url') or info['url']}\n")
            saida.with_suffix(".txt").write_text(post, encoding="utf-8")
            (tdir_cache / "feito.txt").write_text(assinatura, encoding="utf-8")
            feitos.append(saida)
            print(f"      PRONTO: {saida}", flush=True)

            # Limpa temporários do corte no SSD local (/tmp) para economizar espaço
            if tdir_tmp != tdir_cache:
                shutil.rmtree(tdir_tmp, ignore_errors=True)

    for velho in destino.glob("corte_*.*"):  # escolheu menos cortes que da última vez: tira os que sobraram
        if velho.stem not in {f.stem for f in feitos}:
            velho.unlink(missing_ok=True)
    print(f"\n{len(feitos)} cortes prontos pra postar em {destino}")
    return feitos
