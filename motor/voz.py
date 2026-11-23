"""Genera la voz argentina de cada escena de un guion con Edge TTS.

Lee guiones/<id>.json y escribe tts/out/<id>/00.mp3, 01.mp3, ...
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


async def decir(texto, voz, rate, destino):
    for intento in range(3):
        try:
            await edge_tts.Communicate(texto, voz, rate=rate).save(str(destino))
            return
        except Exception:
            if intento == 2:
                raise
            await asyncio.sleep(3)


async def procesar(ruta):
    guion = json.loads(ruta.read_text(encoding="utf-8"))
    rid = guion["id"]
    voz = guion.get("voz", VOZ_POR_DEFECTO)
    rate = guion.get("rate", "+0%")
    destino = TTS_OUT / rid
    destino.mkdir(parents=True, exist_ok=True)

    for i, escena in enumerate(guion["escenas"]):
        texto = escena.get("locucion", "").strip()
        archivo = destino / f"{i:02d}.mp3"
        if not texto:
            print(f"  escena {i}: sin locución, se omite")
            continue
        if archivo.exists() and archivo.stat().st_size > 0:
            print(f"  escena {i}: ya existe")
            continue
        await decir(texto, voz, rate, archivo)
        print(f"  escena {i}: {archivo.name} con {voz}")


async def main():
    objetivos = [pathlib.Path(sys.argv[1])] if len(sys.argv) > 1 else sorted(GUIONES.glob("*.json"))
    for ruta in objetivos:
        print(f"== {ruta.name}")
        await procesar(ruta)


asyncio.run(main())
