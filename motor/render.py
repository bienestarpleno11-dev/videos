"""Motor de Shorts de Hábitos Fix Hoy.

Lee un guion en guiones/<id>.json, usa los audios ya generados por Edge TTS
en tts/out/<id>/NN.mp3 y arma el MP4 vertical 1080x1920 en shorts/<id>.mp4.

Formato del guion:
{
  "id": "2026-11-24-aguinaldo",
  "voz": "es-AR-TomasNeural",
  "rate": "+8%",
  "serie": "1 de 5",
  "paleta": "verde",
  "escenas": [
    {"pantalla": "¿EL AGUINALDO YA TIENE *DUEÑO*?", "locucion": "...", "pie": "opcional"},
    ...
  ]
}

Las palabras entre *asteriscos* se pintan con el color de acento.
La última escena lleva el cierre "habitosfixhoy" abajo.
"""
import json
import pathlib
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

BASE = pathlib.Path(__file__).resolve().parent.parent
FUENTES = BASE / "motor" / "fuentes"
GUIONES = BASE / "guiones"
TTS_OUT = BASE / "tts" / "out"
SHORTS = BASE / "shorts"
TRABAJO = BASE / "motor" / ".trabajo"

ANCHO, ALTO = 1080, 1920
MARGEN = 96

PALETAS = {
    "verde": {"fondo": (14, 61, 46), "fondo2": (8, 38, 29), "texto": (255, 255, 255), "acento": (245, 208, 32)},
    "oscuro": {"fondo": (18, 18, 20), "fondo2": (8, 8, 10), "texto": (255, 255, 255), "acento": (245, 208, 32)},
    "naranja": {"fondo": (214, 92, 20), "fondo2": (158, 58, 8), "texto": (255, 255, 255), "acento": (255, 236, 150)},
    "bordo": {"fondo": (122, 26, 48), "fondo2": (78, 14, 30), "texto": (255, 255, 255), "acento": (255, 208, 120)},
    "azul": {"fondo": (20, 48, 92), "fondo2": (10, 28, 58), "texto": (255, 255, 255), "acento": (120, 214, 255)},
}
ORDEN_PALETAS = ["verde", "oscuro", "naranja", "bordo", "azul"]

MARCA = "Hábitos Fix Hoy"
CIERRE = "habitosfixhoy"


def fuente(nombre, tam):
    return ImageFont.truetype(str(FUENTES / nombre), tam)


ABRE, CIERRA = "\u0001", "\u0002"


def envolver(draw, palabras, fnt, ancho_max):
    """Agrupa (palabra, resaltada) en renglones que entren en ancho_max."""
    renglones, actual = [], []
    for palabra, res in palabras:
        prueba = actual + [(palabra, res)]
        texto = " ".join(p for p, _ in prueba)
        if draw.textlength(texto, font=fnt) <= ancho_max or not actual:
            actual = prueba
        else:
            renglones.append(actual)
            actual = [(palabra, res)]
    if actual:
        renglones.append(actual)
    return renglones


def palabras_con_marca(texto):
    """'¿Tiene *dueño*?' -> [('¿Tiene', False), ('dueño?', True)]

    La puntuación pegada a una palabra resaltada viaja con ella, así no
    queda un signo suelto separado del resto.
    """
    marcado = re.sub(r"\*([^*]+)\*", ABRE + r"\1" + CIERRA, texto)
    salida, dentro = [], False
    for token in marcado.split():
        resaltada = dentro or ABRE in token
        marcas = [c for c in token if c in (ABRE, CIERRA)]
        if marcas:
            dentro = marcas[-1] == ABRE
        salida.append((token.replace(ABRE, "").replace(CIERRA, ""), resaltada))
    return salida


def fondo_degradado(col_a, col_b):
    base = Image.new("RGB", (1, ALTO))
    px = base.load()
    for y in range(ALTO):
        t = y / (ALTO - 1)
        px[0, y] = tuple(int(col_a[i] + (col_b[i] - col_a[i]) * t) for i in range(3))
    return base.resize((ANCHO, ALTO))


def dibujar_escena(escena, paleta, serie, es_ultima, destino):
    col = PALETAS[paleta]
    img = fondo_degradado(col["fondo"], col["fondo2"])
    draw = ImageDraw.Draw(img)

    # Barra de progreso fina arriba
    draw.rounded_rectangle([MARGEN, 70, ANCHO - MARGEN, 78], radius=4,
                           fill=(255, 255, 255, 60))

    # Marca
    f_marca = fuente("FiraSans-SemiBold.ttf", 38)
    draw.text((ANCHO / 2, 130), MARCA, font=f_marca, fill=col["texto"], anchor="mm")

    # Badge de serie
    if serie:
        f_serie = fuente("FiraSans-Black.ttf", 34)
        ancho_t = draw.textlength(serie, font=f_serie)
        x0 = (ANCHO - ancho_t) / 2 - 34
        x1 = (ANCHO + ancho_t) / 2 + 34
        draw.rounded_rectangle([x0, 180, x1, 248], radius=34, fill=col["texto"])
        draw.text((ANCHO / 2, 214), serie, font=f_serie, fill=col["fondo"], anchor="mm")

    # Texto principal: busca el tamaño más grande que entre
    texto = escena.get("pantalla", "")
    palabras = palabras_con_marca(texto)
    ancho_max = ANCHO - 2 * MARGEN
    alto_max = 980

    for tam in range(132, 51, -4):
        fnt = fuente("Anton-Regular.ttf", tam)
        renglones = envolver(draw, palabras, fnt, ancho_max)
        interlinea = int(tam * 1.18)
        if len(renglones) * interlinea <= alto_max:
            break

    alto_bloque = len(renglones) * interlinea
    y = (ALTO - alto_bloque) / 2 - 40

    for renglon in renglones:
        texto_r = " ".join(p for p, _ in renglon)
        x = (ANCHO - draw.textlength(texto_r, font=fnt)) / 2
        for palabra, res in renglon:
            color = col["acento"] if res else col["texto"]
            draw.text((x, y), palabra, font=fnt, fill=color)
            x += draw.textlength(palabra + " ", font=fnt)
        y += interlinea

    # Pie opcional
    pie = escena.get("pie")
    if pie:
        f_pie = fuente("FiraSans-SemiBold.ttf", 46)
        draw.text((ANCHO / 2, y + 60), pie, font=f_pie, fill=col["acento"], anchor="mm")

    # Cierre de marca en la última escena
    if es_ultima:
        f_cierre = fuente("FiraSans-Black.ttf", 50)
        draw.text((ANCHO / 2, ALTO - 150), CIERRE, font=f_cierre,
                  fill=col["texto"], anchor="mm")

    img.save(destino, "PNG")


def duracion(archivo):
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(archivo)],
        capture_output=True, text=True, check=True)
    return float(salida.stdout.strip())


def clip(png, mp3, salida, segundos):
    """Imagen + audio -> clip con un zoom lento."""
    cuadros = max(int(segundos * 30), 1)
    zoom = f"zoompan=z='min(zoom+0.0006,1.10)':d={cuadros}:s={ANCHO}x{ALTO}:fps=30"
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(png)]
    if mp3:
        cmd += ["-i", str(mp3), "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-vf", zoom, "-t", f"{segundos:.3f}", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-r", "30", str(salida)]
    subprocess.run(cmd, check=True, capture_output=True)


def main(ruta_guion):
    guion = json.loads(pathlib.Path(ruta_guion).read_text(encoding="utf-8"))
    rid = guion["id"]
    escenas = guion["escenas"]
    serie = guion.get("serie", "")
    paleta_fija = guion.get("paleta")

    audios = TTS_OUT / rid
    TRABAJO.mkdir(parents=True, exist_ok=True)
    SHORTS.mkdir(parents=True, exist_ok=True)

    partes = []
    for i, escena in enumerate(escenas):
        paleta = escena.get("paleta") or paleta_fija or ORDEN_PALETAS[i % len(ORDEN_PALETAS)]
        png = TRABAJO / f"{rid}-{i:02d}.png"
        dibujar_escena(escena, paleta, serie, i == len(escenas) - 1, png)

        mp3 = audios / f"{i:02d}.mp3"
        if mp3.exists():
            segundos = duracion(mp3) + 0.45
        else:
            mp3 = None
            segundos = float(escena.get("segundos", 4))
            print(f"  aviso: sin audio para la escena {i}, uso {segundos}s")

        parte = TRABAJO / f"{rid}-{i:02d}.mp4"
        clip(png, mp3, parte, segundos)
        partes.append(parte)
        print(f"  escena {i}: {segundos:.2f}s  [{paleta}]")

    lista = TRABAJO / f"{rid}-lista.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in partes), encoding="utf-8")

    final = SHORTS / f"{rid}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(final)],
        check=True, capture_output=True)

    total = duracion(final)
    print(f"Listo: {final}  ({total:.1f}s)")
    return final


if __name__ == "__main__":
    if len(sys.argv) > 1:
        objetivos = [pathlib.Path(sys.argv[1])]
    else:
        objetivos = sorted(GUIONES.glob("*.json"))
    for guion in objetivos:
        print(f"== {guion.name}")
        main(guion)
