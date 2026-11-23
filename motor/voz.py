"""Genera la voz argentina de cada escena de un guion con Edge TTS.

Lee guiones/<id>.json y escribe, por cada escena:
  tts/out/<id>/NN.mp3    el audio
  tts/out/<id>/NN.json   los tiempos de cada palabra, para los subtítulos

Si el audio de una escena ya existe, no lo vuelve a generar.
"""
import asyncio
import json
import pathlib
import subprocess
import sys

import edge_tts

BASE = pathlib.Path(__file__).resolve().parent.parent
GUIONES = BASE / "guiones"
TTS_OUT = BASE / "tts" / "out"

VOZ_POR_DEFECTO = "es-AR-TomasNeural"


def duracion_mp3(archivo):
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(archivo)],
        capture_output=True, text=True, check=True)
    return float(salida.stdout.strip())


def repartir(texto, desde, hasta):
    """Reparte las palabras de un tramo según el largo de cada una.

    Edge TTS informa los límites de cada frase, no de cada palabra, así
    que dentro de cada frase se estima. El error queda en centésimas,
    que para bloques de tres palabras no se nota.
    """
    palabras = texto.split()
    total = hasta - desde
    if not palabras or total <= 0:
        return []
    pesos = [len(p) + 1.4 for p in palabras]
    suma = sum(pesos)
    salida, t = [], desde
    for palabra, peso in zip(palabras, pesos):
        largo = total * peso / suma
        salida.append({"texto": palabra,
                       "inicio": round(t, 3),
                       "fin": round(t + largo * 0.93, 3)})
        t += largo
    return salida


def a_palabras(tramos, texto, total):
    """De los tramos que informó Edge TTS a una lista de palabras."""
    if not tramos:
        arranque = min(0.12, total * 0.04)
        return repartir(texto, arranque, max(total - 0.18, arranque + 0.1))
    palabras = []
    for i, tramo in enumerate(tramos):
        # El final informado a veces se queda corto: estiramos hasta el
        # arranque del tramo siguiente, o hasta el final del audio.
        siguiente = tramos[i + 1]["inicio"] if i + 1 < len(tramos) else total
        fin = max(tramo["fin"], min(siguiente, tramo["fin"] + 0.35))
        palabras.extend(repartir(tramo["texto"], tramo["inicio"], fin))
    return palabras


async def decir(texto, voz, rate, mp3, tiempos_json):
    """Guarda el MP3 y, aparte, cuándo arranca y termina cada palabra."""
    ultimo_error = None
    for intento in range(3):
        try:
            audio = bytearray()
            tramos = []
            tipos = set()
            comunicar = edge_tts.Communicate(texto, voz, rate=rate)
            async for parte in comunicar.stream():
                tipo = parte.get("type", "")
                tipos.add(tipo)
                if tipo == "audio":
                    audio.extend(parte["data"])
                elif "Boundary" in tipo and parte.get("text"):
                    # Edge TTS informa en unidades de 100 nanosegundos.
                    inicio = parte["offset"] / 10_000_000
                    largo = parte.get("duration", 0) / 10_000_000
                    tramos.append({
                        "texto": parte["text"],
                        "inicio": round(inicio, 3),
                        "fin": round(inicio + largo, 3),
                    })
            if not audio:
                raise RuntimeError("Edge TTS no devolvió audio")
            mp3.write_bytes(bytes(audio))

            total = duracion_mp3(mp3)
            palabras = a_palabras(tramos, texto, total)
            origen = f"{len(tramos)} tramos de Edge TTS" if tramos else "estimado"
            if not tramos:
                print(f"    sin tramos de Edge TTS (tipos: {sorted(tipos)})")

            tiempos_json.write_text(
                json.dumps({"origen": origen, "palabras": palabras},
                           ensure_ascii=False),
                encoding="utf-8")
            return
        except Exception as error:
            ultimo_error = error
            await asyncio.sleep(3)
    raise ultimo_error


async def procesar(ruta):
    guion = json.loads(ruta.read_text(encoding="utf-8"))
    rid = guion["id"]
    voz = guion.get("voz", VOZ_POR_DEFECTO)
    rate = guion.get("rate", "+0%")
    destino = TTS_OUT / rid
    destino.mkdir(parents=True, exist_ok=True)

    for i, escena in enumerate(guion["escenas"]):
        texto = escena.get("locucion", "").strip()
        mp3 = destino / f"{i:02d}.mp3"
        tiempos = destino / f"{i:02d}.json"
        if not texto:
            print(f"  escena {i}: sin locución, se omite")
            continue
        if mp3.exists() and mp3.stat().st_size > 0 and tiempos.exists():
            print(f"  escena {i}: ya existe")
            continue
        await decir(texto, voz, rate, mp3, tiempos)
        datos = json.loads(tiempos.read_text(encoding="utf-8"))
        print(f"  escena {i}: {mp3.name}, {len(datos['palabras'])} palabras marcadas")


async def main():
    objetivos = [pathlib.Path(sys.argv[1])] if len(sys.argv) > 1 else sorted(GUIONES.glob("*.json"))
    for ruta in objetivos:
        print(f"== {ruta.name}")
        await procesar(ruta)


asyncio.run(main())
