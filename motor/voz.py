"""Genera la voz argentina de cada escena de un guion con Edge TTS.

Lee guiones/<id>.json y escribe, por cada escena:
  tts/out/<id>/NN.mp3    el audio
  tts/out/<id>/NN.json   los tiempos de cada palabra, para los subtítulos

Si el audio de una escena ya existe, no lo vuelve a generar.
"""
import asyncio
import json
import pathlib
import sys

import edge_tts

BASE = pathlib.Path(__file__).resolve().parent.parent
GUIONES = BASE / "guiones"
TTS_OUT = BASE / "tts" / "out"

VOZ_POR_DEFECTO = "es-AR-TomasNeural"


async def decir(texto, voz, rate, mp3, tiempos_json):
    """Guarda el MP3 y, aparte, cuándo arranca y termina cada palabra."""
    ultimo_error = None
    for intento in range(3):
        try:
            audio = bytearray()
            palabras = []
            comunicar = edge_tts.Communicate(texto, voz, rate=rate)
            async for parte in comunicar.stream():
                if parte["type"] == "audio":
                    audio.extend(parte["data"])
                elif parte["type"] == "WordBoundary":
                    # Edge TTS informa en unidades de 100 nanosegundos.
                    inicio = parte["offset"] / 10_000_000
                    largo = parte["duration"] / 10_000_000
                    palabras.append({
                        "texto": parte["text"],
                        "inicio": round(inicio, 3),
                        "fin": round(inicio + largo, 3),
                    })
            if not audio:
                raise RuntimeError("Edge TTS no devolvió audio")
            mp3.write_bytes(bytes(audio))
            tiempos_json.write_text(
                json.dumps({"palabras": palabras}, ensure_ascii=False),
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
