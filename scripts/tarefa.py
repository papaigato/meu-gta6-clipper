"""Trabalho pesado em segundo plano.

O Claude Code corta qualquer comando que demore mais que alguns minutos. Escutar uma live de 4 horas demora mais que
isso: antes o comando morria, a IA rodava de novo e tudo recomeçava do zero (o "loop" que o pessoal viu).

Agora o trabalho roda sozinho em segundo plano, guarda o progresso no disco, e cada chamada só ACOMPANHA por até
ESPERA segundos. Rodar o mesmo comando de novo nunca recomeça nada: só mostra o progresso.
"""
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

ESPERA = int(os.environ.get("CLIPPER_ESPERA", "100"))  # abaixo dos 2 min que o Claude Code dá por padrão
CLIP = Path(__file__).resolve().parent / "clip.py"


def _vivo(pid, proc=None):
    if proc is not None:
        return proc.poll() is None
    if pid <= 0:
        return False
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _arquivos(pasta, nome):
    return {k: pasta / f".{nome}.{k}" for k in ("feito", "erro", "pid", "log")}


def limpar(pasta, nome):
    for a in _arquivos(pasta, nome).values():
        a.unlink(missing_ok=True)


def acompanhar(pasta, nome, argv, espera=ESPERA):
    """Garante que o trabalho `nome` está rodando (ou já terminou) e acompanha. Devolve 'pronto', 'rodando' ou 'erro'."""
    a = _arquivos(pasta, nome)
    if a["feito"].exists():
        return "pronto"
    pid = int(a["pid"].read_text() or 0) if a["pid"].exists() else 0
    proc = None
    if not _vivo(pid):
        a["erro"].unlink(missing_ok=True)
        log = open(a["log"], "a", encoding="utf-8")
        kw = {"start_new_session": True}
        if os.name == "nt":  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
            kw = {"creationflags": 0x00000008 | 0x00000200 | 0x08000000}
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", OPENCV_LOG_LEVEL="ERROR")
        try:
            from comum import cuda_ld_library_path
            nv_libs = cuda_ld_library_path()
            if nv_libs:
                atual_ld = env.get("LD_LIBRARY_PATH", "")
                env["LD_LIBRARY_PATH"] = f"{nv_libs}:{atual_ld}" if atual_ld else nv_libs
        except Exception:
            pass
        proc = subprocess.Popen([sys.executable, str(CLIP), "_trabalho", nome, *argv], stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, **kw)
        pid = proc.pid
        a["pid"].write_text(str(pid))
        print("      (roda em segundo plano: continua mesmo se este comando for interrompido)", flush=True)
        lido = a["log"].stat().st_size
    else:
        print("      já estava rodando, acompanhando…", flush=True)
        linhas = a["log"].read_text(encoding="utf-8", errors="ignore").splitlines()
        for l in linhas[-3:]:
            print(l, flush=True)
        lido = a["log"].stat().st_size
    t0 = time.time()
    while True:
        time.sleep(2)
        with open(a["log"], encoding="utf-8", errors="ignore") as f:
            f.seek(lido)
            novo = f.read()
            lido = f.tell()
        if novo:
            print(novo, end="", flush=True)
        if a["feito"].exists():
            return "pronto"
        if a["erro"].exists() or not _vivo(pid, proc):
            if a["feito"].exists():
                return "pronto"
            return "erro"
        if time.time() - t0 > espera:
            return "rodando"


def executar(pasta, nome, funcao):
    """Lado do trabalho em segundo plano: roda e marca feito/erro."""
    a = _arquivos(pasta, nome)
    try:
        funcao()
        a["feito"].write_text("ok")
    except SystemExit as e:
        a["erro"].write_text(str(e.code))
        print(e.code if isinstance(e.code, str) else "", flush=True)
    except BaseException:
        a["erro"].write_text(traceback.format_exc())
        traceback.print_exc()
    finally:
        a["pid"].unlink(missing_ok=True)


def explicar_erro(pasta, nome):
    """Mostra o fim do log e limpa o erro pra próxima tentativa recomeçar do ponto em que parou."""
    a = _arquivos(pasta, nome)
    msg = a["erro"].read_text(encoding="utf-8", errors="ignore") if a["erro"].exists() else ""
    if "NÃO DÁ PRA BAIXAR" not in msg:
        linhas = a["log"].read_text(encoding="utf-8", errors="ignore").splitlines() if a["log"].exists() else []
        print("\n".join(linhas[-15:]))
    a["erro"].unlink(missing_ok=True)
    a["pid"].unlink(missing_ok=True)
    return msg
