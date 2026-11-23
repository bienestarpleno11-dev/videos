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


def repartir(texto, total):
    """Reparto estimado: cada palabra ocupa según su largo.

    Se usa sólo si Edge TTS no informa los tiempos reales. Deja un
    pequeño silencio al principio y al final, como hace la voz.
    """
    palabras = texto.split()
    if not palabras or total <= 0:
        return []
    pesos = [len(p) + 1.4 for p in palabras]
    suma = sum(pesos)
    arranque = min(0.12, total * 0.04)
    util = max(total - arranque - min(0.25, total * 0.06), 0.1)
    salida, t = [], arranque
    for palabra, peso in zip(palabras, pesos):
        largo = util * peso / suma
        salida.append({"texto": palabra,
                       "inicio": round(t, 3),
                       "fin": round(t + largo * 0.92, 3)})
        t += largo
    return salida


async def decir(texto, voz, rate, mp3, tiempos_json):
    """Guarda el MP3 y, aparte, cuándo arranca y termina cada palabra."""
    ultimo_error = None
    for intento in range(3):
        try:
            audio = bytearray()
            palabras = []
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
                    palabras.append({
                        "texto": parte["text"],
                        "inicio": round(inicio, 3),
                        "fin": round(inicio + largo, 3),
                    })
            if not audio:
                raise RuntimeError("Edge TTS no devolvió audio")
            mp3.write_bytes(bytes(audio))

            origen = "edge-tts"
            if not palabras:
                origen = "estimado"
                palabras = repartir(texto, duracion_mp3(mp3))
                print(f"    sin tiempos de Edge TTS (tipos: {sorted(tipos)}), "
                      f"se estiman por largo de palabra")

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
