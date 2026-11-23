"""Motor de Shorts de Hábitos Fix Hoy.

Lee guiones/<id>.json, usa los audios y los tiempos de palabra que dejó
motor/voz.py en tts/out/<id>/ y arma el MP4 vertical 1080x1920 en
shorts/<id>.mp4.

Gramática visual, la de los Shorts que funcionan:
  - fondo con profundidad y deriva lenta, nunca un color plano
  - entrada del titular con desplazamiento y fundido
  - golpe de zoom al empezar cada escena, movimiento continuo
  - subtítulos karaoke palabra por palabra, sincronizados con la voz
  - barra de progreso que avanza, para que se vea cuánto falta
  - zonas seguras: nada importante en el 18% de arriba ni el 25% de abajo

Formato del guion: ver motor/README.md
"""
import json
import math
import pathlib
import random
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = pathlib.Path(__file__).resolve().parent.parent
FUENTES = BASE / "motor" / "fuentes"
GUIONES = BASE / "guiones"
TTS_OUT = BASE / "tts" / "out"
SHORTS = BASE / "shorts"
TRABAJO = BASE / "motor" / ".trabajo"

ANCHO, ALTO = 1080, 1920
FPS = 30
MARGEN = 92

# Zonas seguras de la interfaz de Shorts
TOPE_SEGURO = int(ALTO * 0.18)
PISO_SEGURO = int(ALTO * 0.75)

ABRE, CIERRA = "\u0001", "\u0002"

PALETAS = {
    "verde":   {"base": (10, 38, 30),  "luz": (24, 120, 86),  "acento": (245, 208, 32)},
    "oscuro":  {"base": (14, 14, 17),  "luz": (62, 62, 78),   "acento": (245, 208, 32)},
    "naranja": {"base": (92, 32, 8),   "luz": (222, 104, 24), "acento": (255, 232, 140)},
    "bordo":   {"base": (58, 10, 24),  "luz": (150, 32, 60),  "acento": (255, 206, 120)},
    "azul":    {"base": (10, 24, 50),  "luz": (28, 72, 150),  "acento": (120, 214, 255)},
}
ORDEN_PALETAS = ["verde", "oscuro", "naranja", "bordo", "azul"]

BLANCO = (255, 255, 255)
MARCA = "Hábitos Fix Hoy"
CIERRE_MARCA = "habitosfixhoy"

PALABRAS_POR_BLOQUE = 3


def fuente(nombre, tam):
    return ImageFont.truetype(str(FUENTES / nombre), tam)


def suavizar(t):
    """Easing de salida: arranca rápido y frena."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def palabras_con_marca(texto):
    """'¿Tiene *dueño*?' -> [('¿Tiene', False), ('dueño?', True)]"""
    marcado = re.sub(r"\*([^*]+)\*", ABRE + r"\1" + CIERRA, texto)
    salida, dentro = [], False
    for token in marcado.split():
        resaltada = dentro or ABRE in token
        marcas = [c for c in token if c in (ABRE, CIERRA)]
        if marcas:
            dentro = marcas[-1] == ABRE
        salida.append((token.replace(ABRE, "").replace(CIERRA, ""), resaltada))
    return salida


def envolver(draw, palabras, fnt, ancho_max):
    renglones, actual = [], []
    for palabra, res in palabras:
        prueba = actual + [(palabra, res)]
        if draw.textlength(" ".join(p for p, _ in prueba), font=fnt) <= ancho_max or not actual:
            actual = prueba
        else:
            renglones.append(actual)
            actual = [(palabra, res)]
    if actual:
        renglones.append(actual)
    return renglones


# ---------------------------------------------------------------- fondo

def traer_archivo(origen, sufijo):
    """Baja una URL a la carpeta de trabajo, o resuelve una ruta del repo."""
    if not origen:
        return None
    try:
        if origen.startswith(("http://", "https://")):
            import hashlib
            import urllib.request
            cache = TRABAJO / "fondos"
            cache.mkdir(parents=True, exist_ok=True)
            nombre = hashlib.sha1(origen.encode("utf-8")).hexdigest()[:16]
            destino = cache / f"{nombre}{sufijo}"
            if not destino.exists() or destino.stat().st_size == 0:
                pedido = urllib.request.Request(
                    origen, headers={"User-Agent": "habitosfixhoy-motor/1.0"})
                with urllib.request.urlopen(pedido, timeout=90) as r:
                    destino.write_bytes(r.read())
            return destino
        ruta = BASE / origen
        return ruta if ruta.exists() else None
    except Exception as error:
        print(f"  aviso: no pude traer {origen}: {error}")
        return None


def traer_imagen(origen):
    """Devuelve la imagen de un `fondo`: ruta del repo o URL. None si falla."""
    ruta = traer_archivo(origen, ".img")
    if ruta is None:
        return None
    try:
        return Image.open(ruta).convert("RGB")
    except Exception as error:
        print(f"  aviso: no pude abrir el fondo {origen}: {error}")
        return None


def recortar_vertical(img, w, h):
    """Recorta al centro para llenar w x h sin deformar."""
    escala = max(w / img.width, h / img.height)
    nuevo = (max(int(img.width * escala), w), max(int(img.height * escala), h))
    img = img.resize(nuevo, Image.LANCZOS)
    x = (img.width - w) // 2
    y = (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def fondo_foto(imagen, paleta, w, h):
    """Foto oscurecida y teñida, para que el texto blanco se lea siempre."""
    col = PALETAS[paleta]
    base = recortar_vertical(imagen, w, h)
    oscuro = Image.new("RGB", (w, h), (0, 0, 0))
    base = Image.blend(base, oscuro, 0.52)
    tinte = Image.new("RGB", (w, h), col["base"])
    base = Image.blend(base, tinte, 0.30)

    # Degradado inferior, para apoyar los subtítulos
    sombra = Image.new("L", (1, h))
    px = sombra.load()
    for y in range(h):
        t = y / (h - 1)
        px[0, y] = int(150 * max(0.0, (t - 0.45) / 0.55) ** 1.4)
    sombra = sombra.resize((w, h))
    base = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), base, sombra)
    return base


def fondo_escena(paleta, semilla, origen_foto=None):
    """Fondo de la escena: una foto tratada, o uno generado con profundidad.

    Se dibuja más grande que el cuadro para poder moverlo sin bordes.
    """
    col = PALETAS[paleta]
    rnd = random.Random(semilla)
    sobra = 1.14
    w, h = int(ANCHO * sobra), int(ALTO * sobra)

    foto = traer_imagen(origen_foto)
    if foto is not None:
        return fondo_foto(foto, paleta, w, h)

    # Degradado vertical de base
    tira = Image.new("RGB", (1, h))
    px = tira.load()
    for y in range(h):
        t = y / (h - 1)
        px[0, y] = tuple(int(col["base"][i] * (1 - t * 0.45)) for i in range(3))
    img = tira.resize((w, h))

    # Manchas de luz, difuminadas fuerte
    capa = Image.new("RGB", (w // 4, h // 4), (0, 0, 0))
    dib = ImageDraw.Draw(capa)
    for _ in range(3):
        r = rnd.randint(h // 16, h // 7)
        cx = rnd.randint(0, w // 4)
        cy = rnd.randint(0, h // 4)
        intensidad = rnd.uniform(0.55, 1.0)
        color = tuple(int(c * intensidad) for c in col["luz"])
        dib.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    capa = capa.filter(ImageFilter.GaussianBlur(radius=h // 28)).resize((w, h))
    img = Image.blend(img, Image.blend(img, capa, 0.85), 0.55)

    # Grano
    grano = Image.effect_noise((w, h), 14).convert("L").point(lambda v: v // 7)
    img = Image.composite(Image.new("RGB", (w, h), (255, 255, 255)), img,
                          grano.point(lambda v: min(v, 26)))

    # Viñeta
    vineta = Image.new("L", (w // 6, h // 6), 0)
    ImageDraw.Draw(vineta).ellipse(
        [-w // 24, -h // 24, w // 6 + w // 24, h // 6 + h // 24], fill=255)
    vineta = vineta.filter(ImageFilter.GaussianBlur(h // 60)).resize((w, h))
    img = Image.composite(img, Image.new("RGB", (w, h), (0, 0, 0)), vineta)
    return img


# --------------------------------------------------------------- capas

def capa_titular(escena, paleta, draw_ref):
    """Devuelve una capa RGBA con el titular ya compuesto, y su alto."""
    col = PALETAS[paleta]
    palabras = palabras_con_marca(escena.get("pantalla", ""))
    ancho_max = ANCHO - 2 * MARGEN
    alto_max = 620

    for tam in range(126, 51, -4):
        fnt = fuente("Anton-Regular.ttf", tam)
        renglones = envolver(draw_ref, palabras, fnt, ancho_max)
        interlinea = int(tam * 1.14)
        if len(renglones) * interlinea <= alto_max:
            break

    alto = len(renglones) * interlinea + 20
    capa = Image.new("RGBA", (ANCHO, alto), (0, 0, 0, 0))
    dib = ImageDraw.Draw(capa)
    y = 0
    for renglon in renglones:
        texto_r = " ".join(p for p, _ in renglon)
        x = (ANCHO - dib.textlength(texto_r, font=fnt)) / 2
        for palabra, res in renglon:
            color = col["acento"] if res else BLANCO
            dib.text((x + 4, y + 5), palabra, font=fnt, fill=(0, 0, 0, 120))
            dib.text((x, y), palabra, font=fnt, fill=color + (255,))
            x += dib.textlength(palabra + " ", font=fnt)
        y += interlinea
    return capa, alto


def capa_fija(paleta, serie, es_ultima):
    """Marca, badge de serie y cierre: lo que no cambia dentro de la escena."""
    col = PALETAS[paleta]
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    dib = ImageDraw.Draw(capa)

    f_marca = fuente("FiraSans-SemiBold.ttf", 36)
    dib.text((ANCHO / 2, 128), MARCA, font=f_marca, fill=BLANCO + (225,), anchor="mm")

    if serie:
        f_serie = fuente("FiraSans-Black.ttf", 32)
        ancho_t = dib.textlength(serie, font=f_serie)
        x0, x1 = (ANCHO - ancho_t) / 2 - 30, (ANCHO + ancho_t) / 2 + 30
        dib.rounded_rectangle([x0, 172, x1, 232], radius=30, fill=col["acento"] + (255,))
        dib.text((ANCHO / 2, 202), serie, font=f_serie, fill=(0, 0, 0, 255), anchor="mm")

    if es_ultima:
        f_cierre = fuente("FiraSans-Black.ttf", 46)
        dib.text((ANCHO / 2, ALTO - 190), CIERRE_MARCA, font=f_cierre,
                 fill=BLANCO + (240,), anchor="mm")
    return capa


def bloques_de_subtitulo(palabras):
    """Agrupa las palabras habladas en bloques cortos y legibles."""
    bloques, actual = [], []
    for p in palabras:
        actual.append(p)
        corta_por_puntuacion = p["texto"].strip().endswith((".", ",", "?", "!", ":", ";"))
        if len(actual) >= PALABRAS_POR_BLOQUE or corta_por_puntuacion:
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return [{
        "palabras": b,
        "inicio": b[0]["inicio"],
        "fin": b[-1]["fin"],
    } for b in bloques]


def dibujar_subtitulo(dib, bloque, t, paleta):
    """Karaoke: el bloque entero en blanco, la palabra que suena en acento."""
    col = PALETAS[paleta]
    fnt = fuente("FiraSans-Black.ttf", 62)
    palabras = bloque["palabras"]
    textos = [p["texto"].strip() for p in palabras]
    ancho_total = dib.textlength(" ".join(textos), font=fnt)

    # Si no entra, achicamos
    tam = 62
    while ancho_total > ANCHO - 2 * MARGEN and tam > 34:
        tam -= 3
        fnt = fuente("FiraSans-Black.ttf", tam)
        ancho_total = dib.textlength(" ".join(textos), font=fnt)

    y = 1305
    x = (ANCHO - ancho_total) / 2

    # Fondo translúcido para que se lea sobre cualquier imagen
    dib.rounded_rectangle(
        [x - 34, y - 52, x + ancho_total + 34, y + 52], radius=26,
        fill=(0, 0, 0, 125))

    for p, texto in zip(palabras, textos):
        activa = p["inicio"] <= t <= p["fin"] + 0.06
        color = col["acento"] if activa else BLANCO
        dib.text((x + 3, y + 4), texto, font=fnt, fill=(0, 0, 0, 150), anchor="lm")
        dib.text((x, y), texto, font=fnt, fill=color, anchor="lm")
        x += dib.textlength(texto + " ", font=fnt)


# -------------------------------------------------------------- armado

def duracion(archivo):
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(archivo)],
        capture_output=True, text=True, check=True)
    return float(salida.stdout.strip())


def musica_por_defecto():
    """Primer MP3 que haya en motor/musica/, si es que hay alguno."""
    carpeta = BASE / "motor" / "musica"
    if not carpeta.exists():
        return None
    pistas = sorted(carpeta.glob("*.mp3"))
    return str(pistas[0].relative_to(BASE)) if pistas else None


def capa_tratamiento(paleta):
    """Oscurecido, tinte y degradado inferior, sobre metraje real.

    Va debajo del texto y encima del video, para que el blanco se lea
    sobre cualquier imagen sin tapar lo que se ve.
    """
    col = PALETAS[paleta]
    capa = Image.new("RGBA", (ANCHO, ALTO), col["base"] + (108,))
    oscuro = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 70))
    capa.alpha_composite(oscuro)

    # Degradado inferior para apoyar los subtítulos
    alto_grad = ALTO - 900
    grad = Image.new("RGBA", (1, alto_grad))
    px = grad.load()
    for y in range(alto_grad):
        px[0, y] = (0, 0, 0, int(165 * (y / (alto_grad - 1)) ** 1.5))
    capa.alpha_composite(grad.resize((ANCHO, alto_grad)), (0, 900))

    # Viñeta
    vineta = Image.new("L", (ANCHO // 6, ALTO // 6), 110)
    ImageDraw.Draw(vineta).ellipse(
        [ANCHO // 60, ALTO // 60, ANCHO // 6 - ANCHO // 60, ALTO // 6 - ALTO // 60],
        fill=0)
    vineta = vineta.filter(ImageFilter.GaussianBlur(ALTO // 120)).resize((ANCHO, ALTO))
    negro = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    negro.putalpha(vineta)
    capa.alpha_composite(negro)
    return capa


def entrada_de_fondo(escena, paleta, semilla, segundos):
    """Arma los argumentos de ffmpeg para el fondo de la escena.

    Devuelve (argumentos de entrada, filtro, hay_metraje_real).
    """
    cuadros = max(int(segundos * FPS), 1)

    clip = traer_archivo(escena.get("video"), ".mp4")
    if clip is not None:
        # Metraje real: se repite si es más corto que la escena y se
        # recorta al vertical sin deformar.
        entrada = ["-stream_loop", "-1", "-i", str(clip)]
        filtro = (f"scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,"
                  f"crop={ANCHO}:{ALTO},fps={FPS},"
                  f"eq=saturation=1.08:contrast=1.04")
        return entrada, filtro, True

    foto = escena.get("fondo")
    if foto and traer_imagen(foto) is not None:
        ruta = traer_archivo(foto, ".img")
        entrada = ["-loop", "1", "-i", str(ruta)]
        filtro = (f"scale={ANCHO * 2}:{ALTO * 2}:force_original_aspect_ratio=increase,"
                  f"crop={ANCHO * 2}:{ALTO * 2},"
                  f"zoompan=z='min(zoom+0.0007,1.14)':d={cuadros}:"
                  f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                  f"s={ANCHO}x{ALTO}:fps={FPS}")
        return entrada, filtro, True

    # Sin material: fondo generado con profundidad
    generado = fondo_escena(paleta, semilla)
    ruta = TRABAJO / f"generado-{semilla}.png"
    generado.save(ruta, "PNG")
    entrada = ["-loop", "1", "-i", str(ruta)]
    filtro = (f"zoompan=z='min(zoom+0.0005,1.10)':d={cuadros}:"
              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
              f"s={ANCHO}x{ALTO}:fps={FPS}")
    return entrada, filtro, False


def render_escena(escena, paleta, serie, es_ultima, segundos, palabras_voz,
                  salida, avance_desde, avance_hasta, semilla):
    """Compone la escena: fondo por ffmpeg, texto y subtítulos por encima."""
    medidor = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    titular, alto_titular = capa_titular(escena, paleta, medidor)
    fija = capa_fija(paleta, serie, es_ultima)
    bloques = bloques_de_subtitulo(palabras_voz) if palabras_voz else []

    col = PALETAS[paleta]
    total = max(int(segundos * FPS), 1)
    y_titular = TOPE_SEGURO + (PISO_SEGURO - TOPE_SEGURO - alto_titular) // 2 - 60

    entrada, filtro_fondo, metraje = entrada_de_fondo(escena, paleta, semilla, segundos)
    tratamiento = capa_tratamiento(paleta) if metraje else None

    cmd = (["ffmpeg", "-y"] + entrada +
           ["-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-",
            "-filter_complex",
            f"[0:v]{filtro_fondo}[bg];[bg][1:v]overlay=format=auto[v]",
            "-map", "[v]", "-an", "-t", f"{segundos:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", str(salida)])
    proceso = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    try:
        for n in range(total):
            t = n / FPS
            avance = n / max(total - 1, 1)

            cuadro = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
            if tratamiento is not None:
                cuadro.alpha_composite(tratamiento)

            # Titular: sube y aparece
            prog = suavizar(t / 0.38)
            if prog > 0:
                capa = titular if prog >= 1 else titular.copy()
                if prog < 1:
                    alfa = capa.getchannel("A").point(lambda v: int(v * prog))
                    capa.putalpha(alfa)
                cuadro.alpha_composite(capa, (0, int(y_titular + 46 * (1 - prog))))

            cuadro.alpha_composite(fija)
            dib = ImageDraw.Draw(cuadro, "RGBA")

            # Subtítulo karaoke
            for bloque in bloques:
                if bloque["inicio"] - 0.08 <= t <= bloque["fin"] + 0.18:
                    dibujar_subtitulo(dib, bloque, t, paleta)
                    break

            # Barra de progreso de todo el video
            pos = avance_desde + (avance_hasta - avance_desde) * avance
            dib.rounded_rectangle([MARGEN, 74, ANCHO - MARGEN, 82], radius=4,
                                  fill=(255, 255, 255, 55))
            if pos > 0:
                dib.rounded_rectangle(
                    [MARGEN, 74, MARGEN + (ANCHO - 2 * MARGEN) * pos, 82],
                    radius=4, fill=col["acento"] + (255,))

            proceso.stdin.write(cuadro.tobytes())
    finally:
        proceso.stdin.close()
        error = proceso.stderr.read().decode("utf-8", "ignore")
        proceso.wait()
    if proceso.returncode != 0:
        raise RuntimeError(f"ffmpeg falló en la escena:\n{error[-1500:]}")


def main(ruta_guion):
    guion = json.loads(pathlib.Path(ruta_guion).read_text(encoding="utf-8"))
    rid = guion["id"]
    escenas = guion["escenas"]
    serie = guion.get("serie", "")
    paleta_fija = guion.get("paleta")

    audios = TTS_OUT / rid
    TRABAJO.mkdir(parents=True, exist_ok=True)
    SHORTS.mkdir(parents=True, exist_ok=True)

    # Duración de cada escena, para repartir la barra de progreso
    duraciones = []
    for i, escena in enumerate(escenas):
        mp3 = audios / f"{i:02d}.mp3"
        if mp3.exists():
            duraciones.append(duracion(mp3) + 0.5)
        else:
            duraciones.append(float(escena.get("segundos", 4)))
    total_video = sum(duraciones)

    partes, acumulado = [], 0.0
    for i, escena in enumerate(escenas):
        paleta = escena.get("paleta") or paleta_fija or ORDEN_PALETAS[i % len(ORDEN_PALETAS)]
        mp3 = audios / f"{i:02d}.mp3"
        tiempos = audios / f"{i:02d}.json"
        palabras_voz = []
        if tiempos.exists():
            palabras_voz = json.loads(tiempos.read_text(encoding="utf-8")).get("palabras", [])

        muda = TRABAJO / f"{rid}-{i:02d}-muda.mp4"
        render_escena(escena, paleta, serie, i == len(escenas) - 1,
                      duraciones[i], palabras_voz, muda,
                      acumulado / total_video,
                      (acumulado + duraciones[i]) / total_video,
                      semilla=f"{rid}-{i}")

        parte = TRABAJO / f"{rid}-{i:02d}.mp4"
        if mp3.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(muda), "-i", str(mp3),
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(parte)],
                check=True, capture_output=True)
        else:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(muda), "-f", "lavfi",
                 "-i", "anullsrc=r=48000:cl=stereo", "-c:v", "copy",
                 "-c:a", "aac", "-shortest", str(parte)],
                check=True, capture_output=True)

        partes.append(parte)
        acumulado += duraciones[i]
        print(f"  escena {i}: {duraciones[i]:.2f}s  [{paleta}]  "
              f"{len(palabras_voz)} palabras")

    lista = TRABAJO / f"{rid}-lista.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in partes), encoding="utf-8")

    final = SHORTS / f"{rid}.mp4"
    musica = traer_archivo(guion.get("musica") or musica_por_defecto(), ".mp3")

    if musica is not None:
        # La música va muy por debajo de la voz, con entrada y salida suaves.
        volumen = float(guion.get("volumen_musica", 0.08))
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
             "-stream_loop", "-1", "-i", str(musica),
             "-filter_complex",
             f"[1:a]volume={volumen},afade=t=in:st=0:d=1.2,"
             f"afade=t=out:st={max(total_video - 1.4, 0.1):.2f}:d=1.4[mus];"
             f"[0:a][mus]amix=inputs=2:duration=first:dropout_transition=0,"
             f"alimiter=limit=0.95[a]",
             "-map", "0:v", "-map", "[a]",
             "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)],
            check=True, capture_output=True)
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
             "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)],
            check=True, capture_output=True)

    print(f"Listo: {final}  ({duracion(final):.1f}s)")
    return final


if __name__ == "__main__":
    objetivos = [pathlib.Path(sys.argv[1])] if len(sys.argv) > 1 else sorted(GUIONES.glob("*.json"))
    for guion in objetivos:
        print(f"== {guion.name}")
        main(guion)
