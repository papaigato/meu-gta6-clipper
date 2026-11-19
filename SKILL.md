---
name: gta6-viral-clipper
description: Clipper viral universal de GTA 6 para Antigravity e Claude Code. Transforma lives do YouTube, Twitch e Kick em múltiplos Reels, TikToks e Shorts verticais 9:16 com webcam no topo, gameplay embaixo, legendas dinâmicas, ganchos nos primeiros 3 segundos e copys com hashtags prontas para postagem.
---

# GTA 6 Viral Clipper (Universal: Antigravity & Claude Code)

Esta skill une o poder do **Clipper do GTA 6** (detecção de gritos, chat acelerado e webcam inteligente) com as melhores técnicas de retenção do **VibeClipper** (legendas dinâmicas e ganchos) e a lógica de esteira automatizada do **SupoClip**.

---

## ⚡ Regras Rápidas de Execução

Depois de instalado o motor local:
- **No Windows (PowerShell):**
  `& "$HOME\clipper-gta6\clip.cmd" <comando>`
- **No Mac / Linux:**
  `~/clipper-gta6/clip <comando>`

> **Aviso de Segundo Plano:** Quando o comando responder `AINDA TRABALHANDO [XX%]`, não é erro! O processamento de vídeo e escuta do áudio está rodando em segundo plano. Basta rodar o mesmo comando novamente após alguns instantes.

---

## 🛠️ Comandos Disponíveis

| Objetivo | Comando |
| :--- | :--- |
| **Instalar / Atualizar motor** | `clip instalar` |
| **Achar lives grandes de GTA 6 hoje** | `clip buscar --quantas 7` |
| **1. Baixar áudio e achar picos** | `clip preparar <LINK_DA_LIVE>` |
| **2. Ficar com os melhores momentos** | `clip escolher <NOME_DA_LIVE> --manter 3` |
| **3. Renderizar os cortes 9:16** | `clip fazer <NOME_DA_LIVE>` |
| **Modo 100% Automático** | `clip automatico <LINK_DA_LIVE> --quantos 3` |
| **Ver status das tarefas** | `clip status` |

---

## 🎯 Fluxo Passo a Passo: Criando 3 a 7 Cortes Virais por Dia

### Passo 1: Preparação da Live
Quando o usuário colar um link de live finalizada:
1. O agente executa:
   ```powershell
   & "$HOME\clipper-gta6\clip.cmd" preparar <LINK>
   ```
2. O script baixa apenas o áudio e gera o arquivo `candidatos.txt` com as marcas de intensidade:
   - `[ALTO +12dB]`: streamer gritou, tomou susto ou reagiu alto.
   - `[CHAT 3.1x]`: o chat acelerou subitamente (aconteceu algo impactante no jogo).

### Passo 2: Seleção e Curadoria da IA
A IA lê o arquivo de candidatos e pontua os momentos de 0 a 100 com base em:
1. **Regra dos 3 primeiros segundos (Hook)**:
   - "A polícia do GTA 6 é muito apelona..."
   - "O que acontece se você fizer isso em Vice City?"
   - "Olha essa física inacreditável!"
2. **Sentido completo**: o trecho tem início, meio e fim (sem depender de contexto anterior).
3. **Duração**: entre 25 e 55 segundos.

A IA grava a seleção em `momentos/candidatos.json`:
```json
[
  {
    "inicio": "00:45:12",
    "fim": "00:45:55",
    "nota": 92,
    "tipo": "fuga de 5 estrelas",
    "titulo": "A IA DA POLÍCIA NO GTA 6 TÁ INSANA!",
    "porque": "perseguição com viaturas capotando e streamer surtando com a física",
    "post": "Você acha que conseguiria despistar a polícia no GTA 6 assim? 😱 Comenta aí! 👇 #gta6 #gtavi #gta #cortes #reelsgames"
  }
]
```

### Passo 3: Escolha do Estilo Visual (REGRA MANDATÓRIA)
Antes de renderizar os cortes (`clip fazer`), a IA **DEVE perguntar ao usuário** qual dos dois estilos ele deseja:
1. **Fundo Desfocado (Cinematic Blur - Estilo do Vídeo 8)**:
   - Jogo 16:9 inteiro no centro da tela sem cortes.
   - Fundo 9:16 preenchido com o próprio vídeo borrado.
   - Legendas centralizadas e limpas (ideal quando o foco é o jogo/gameplay).
   - *Como ativar no sistema:* `$env:CLIPPER_ESTILO = "blur"`.
2. **Split-Screen (Webcam no Topo + Gameplay Embaixo)**:
   - Rosto do streamer detectado por IA e posicionado em cima.
   - Gameplay preenchendo a metade inferior.
   - *Como ativar no sistema:* `$env:CLIPPER_ESTILO = "split"`.

### Passo 4: Montagem e Renderização dos Vídeos
Execute:
```powershell
& "$HOME\clipper-gta6\clip.cmd" escolher <NOME> --manter 3
& "$HOME\clipper-gta6\clip.cmd" fazer <NOME>
```
O script corta exatamente os trechos selecionados, utiliza visão computacional (YuNet) para encontrar a câmera do streamer, posiciona a webcam na metade superior, o gameplay na inferior, e gera a legenda embutida com fonte `Montserrat-ExtraBold`.

### Passo 4: Entrega ao Usuário e Armazenamento na Nuvem (Google Drive 4TB)
Ao finalizar, os cortes são salvos diretamente na nuvem:
- Se o **Google Drive para computador** estiver instalado (letra `G:\`), os vídeos vão automaticamente para:
  `G:\Meu Drive\GTA6_Cortes\<NOME>\`
- Caso contrário, ficam em `C:\Users\<usuario>\clipper-gta6\cortes\<NOME>\`.
*(Você também pode definir uma pasta personalizada setando a variável de ambiente `$env:CLIPPER_CORTES_DIR` ou `$env:CLIPPER_GTA6_HOME`).*

Arquivos gerados:
- `corte_01.mp4`: Vídeo 1080x1920 pronto para Reels / TikTok / Shorts salvo na nuvem.
- `corte_01.txt`: Texto da legenda da postagem com ganchos, CTA e hashtags.
