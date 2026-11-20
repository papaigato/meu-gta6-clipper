"""Coisas que todos os passos do clipper usam: pastas, tempo e chamadas de programas."""
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

CASA = Path(os.environ.get("CLIPPER_GTA6_HOME", Path.home() / "clipper-gta6"))
TRABALHO = CASA / "trabalho"   # áudio, transcrição e trechos de cada live

def obter_pasta_cortes():
    r"""Detecta automaticamente o Google Drive de 4TB (unidade G:\ ou Meu Drive) ou usa CLIPPER_CORTES_DIR."""
    if "CLIPPER_CORTES_DIR" in os.environ:
        p = Path(os.environ["CLIPPER_CORTES_DIR"])
        p.mkdir(parents=True, exist_ok=True)
        return p
    # Busca por unidades do Google Drive no Windows
    for letra in ("G", "H", "I", "D", "E", "F"):
        for sub in ("Meu Drive", "My Drive"):
            raiz = Path(f"{letra}:/{sub}")
            if raiz.exists():
                pasta_drive = raiz / "GTA6_Cortes"
                try:
                    pasta_drive.mkdir(parents=True, exist_ok=True)
                    return pasta_drive
                except OSError:
                    pass
    return CASA / "cortes"

CORTES = obter_pasta_cortes()
MODELOS = CASA / "modelos"     # o detector de rosto (baixado no setup)
YUNET = MODELOS / "face_detection_yunet_2023mar.onnx"
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")
BLOCO_MIN = 12  # a IA lê a transcrição 12 minutos por vez


def slug(texto, limite=60):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t[:limite].strip("-") or "live"


def hms(seg):
    seg = max(0, int(round(seg)))
    return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"


def segundos(valor):
    """Aceita 3723, '3723', '1:02:03' ou '62:03'."""
    if isinstance(valor, (int, float)):
        return float(valor)
    partes = [float(p) for p in str(valor).strip().split(":")]
    total = 0.0
    for p in partes:
        total = total * 60 + p
    return total


def rodar(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def tem(programa):
    return shutil.which(programa) is not None


def ffmpeg_embutido():
    """Sem ffmpeg no computador, usa o ffmpeg que vem no pacote static-ffmpeg (baixado no instalar)."""
    if tem("ffmpeg") and tem("ffprobe"):
        return True
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths(weak=True)
    except Exception:
        return False
    return tem("ffmpeg") and tem("ffprobe")


def buscar_cookies():
    """Busca cookies do YouTube no Google Drive, no Colab ou configurados por variável."""
    candidatos = [
        os.environ.get("CLIPPER_COOKIES"),
        Path("/content/drive/MyDrive/cookies.txt"),
        Path("/content/drive/MyDrive/GTA6_Cortes/cookies.txt"),
        Path("/content/cookies.txt"),
        Path.home() / "cookies.txt",
    ]
    for c in candidatos:
        if c and Path(c).is_file():
            return Path(c)
    return None


def ytdlp():
    """yt-dlp do ambiente do clipper (sempre atualizado pelo setup) ou o do sistema."""
    local = Path(sys.executable).parent / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp")
    cmd = [str(local)] if local.exists() else [sys.executable, "-m", "yt_dlp"]
    ff_dir = Path(sys.executable).parent
    if (ff_dir / "ffmpeg.exe").exists() or (ff_dir / "ffmpeg").exists():
        cmd += ["--ffmpeg-location", str(ff_dir)]
    # o YouTube está passando a exigir um JavaScript pra liberar os formatos: o instalar põe o Deno no ambiente
    deno = Path(sys.executable).parent / ("deno.exe" if os.name == "nt" else "deno")
    if deno.exists():
        cmd += ["--js-runtimes", f"deno:{deno}"]
    elif tem("deno") or tem("node"):
        cmd += ["--js-runtimes", "deno" if tem("deno") else "node"]
    
    # Cookies para evitar bloqueio de bot em nuvem (Colab)
    cookies = buscar_cookies()
    if cookies:
        cmd += ["--cookies", str(cookies)]
    return cmd


TRANCADA = ("confirm your age", "inappropriate for some users", "members-only", "join this channel",
            "subscriber", "private video", "requires authentication", "sign in to confirm")


def motivo_trancada(erro):
    """Se o yt-dlp recusou porque a live pede login (idade, membros, inscritos, privada), diz isso em português."""
    t = (erro or "").lower()
    if not any(k in t for k in TRANCADA):
        return None
    if "age" in t or "inappropriate" in t:
        return "essa live é trancada por idade (o YouTube pede login pra ver)"
    if "member" in t or "join this channel" in t or "subscriber" in t:
        return "essa live é só pra membros/inscritos do canal"
    return "essa live pede login (privada ou restrita)"


def ler_json(caminho, padrao=None):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def gravar_json(caminho, dados):
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def pasta_da_live(nome):
    """Aceita o nome da pasta, um pedaço dele ou o link original."""
    if (TRABALHO / nome).is_dir():
        return TRABALHO / nome
    for p in sorted(TRABALHO.glob("*")):
        info = ler_json(p / "info.json", {})
        if nome in (info.get("url"), info.get("webpage_url")) or nome.lower() in p.name:
            return p
    sys.exit(f"Não achei a live '{nome}' em {TRABALHO}. Rode antes: clip.py preparar LINK")
