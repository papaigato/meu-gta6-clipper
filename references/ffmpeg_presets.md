# Presets e Comandos FFmpeg para Cortes de GTA 6

Estes comandos realizam a conversão sem a necessidade de abrir editores pesados manualmente.

---

## 1. Corte Rápido Sem Perda (Sem re-renderizar, instantâneo)
Útil para isolar um trecho da live antes de editar:
```powershell
ffmpeg -ss 00:15:30 -to 00:16:15 -i "live_original.mp4" -c copy "trecho_bruto.mp4"
```

---

## 2. Converter Horizontal (16:9) em Vertical (9:16) com Fundo Borrado (Blur)
O padrão mais usado para Reels de games quando não há webcam separada:
- Fundo: tela esticada e desfocada em 1080x1920.
- Frente: gameplay centralizado na proporção original.

```powershell
ffmpeg -ss 00:10:00 -to 00:10:45 -i "live.mp4" `
  -filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];[0:v]scale=1080:608[fg];[bg][fg]overlay=0:(H-h)/2" `
  -c:v libx264 -preset fast -crf 20 -c:a aac -b:a 192k "reel_blur.mp4"
```

---

## 3. Split Screen (Webcam no Topo + Gameplay Embaixo)
Se a live tiver a webcam do streamer no canto superior esquerdo (exemplo: webcam de 480x270 na coordenada 50,50 do vídeo original de 1920x1080):

```powershell
ffmpeg -ss 00:05:00 -to 00:05:40 -i "live.mp4" `
  -filter_complex "[0:v]crop=480:270:50:50,scale=1080:608[cam];[0:v]crop=1080:1080:420:0,scale=1080:1080[game];[cam][game]vstack=inputs=2[outv]" `
  -map "[outv]" -map 0:a -c:v libx264 -preset fast -crf 20 -c:a aac -b:a 192k "reel_split.mp4"
```

---

## 4. Embutir Legenda (.srt ou .ass) Diretamente no Vídeo
Para que as legendas apareçam nativamente no vídeo:
```powershell
ffmpeg -i "reel_pronto.mp4" -vf "subtitles=legenda.srt:force_style='Fontname=Arial Black,Fontsize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=2'" -c:a copy "reel_com_legenda.mp4"
```

---

## 5. Download de Trecho Específico com yt-dlp (Sem baixar a live inteira de 4 horas)
Baixar apenas do minuto 14:00 até o minuto 15:30 de uma live do YouTube:
```powershell
yt-dlp --download-sections "*14:00-15:30" -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]" "LINK_DO_YOUTUBE" -o "gta6_trecho.mp4"
```
