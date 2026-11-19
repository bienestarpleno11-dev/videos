"""Genera voces gratis con Edge TTS (voces neurales de Microsoft).

Lee cada pedido en tts/requests/<id>.json:
  {"id": "2026-11-19-short", "voice": "es-AR-TomasNeural", "rate": "+8%",
   "texts": ["texto escena 0", "texto escena 1", ...]}
y escribe tts/out/<id>/00.mp3, 01.mp3, ... y tts/out/<id>/done.txt.
Si algo falla, escribe tts/out/<id>/error.txt con el error.
"""
import asyncio, json, pathlib, traceback
import edge_tts

BASE = pathlib.Path(__file__).parent
REQ, OUT = BASE / "requests", BASE / "out"


async def procesar(pedido: pathlib.Path):
    data = json.loads(pedido.read_text(encoding="utf-8"))
    rid = data.get("id") or pedido.stem
    destino = OUT / rid
    if (destino / "done.txt").exists():
        return
    destino.mkdir(parents=True, exist_ok=True)
    voz = data.get("voice", "es-AR-TomasNeural")
    rate = data.get("rate", "+0%")
    try:
        for i, texto in enumerate(data["texts"]):
            archivo = destino / f"{i:02d}.mp3"
            for intento in range(3):
                try:
                    await edge_tts.Communicate(texto, voz, rate=rate).save(str(archivo))
                    break
                except Exception:
                    if intento == 2:
                        raise
                    await asyncio.sleep(3)
        (destino / "done.txt").write_text(f"{len(data['texts'])} archivos con {voz}\n")
        (destino / "error.txt").unlink(missing_ok=True)
    except Exception:
        (destino / "error.txt").write_text(traceback.format_exc())


async def main():
    for pedido in sorted(REQ.glob("*.json")):
        await procesar(pedido)


asyncio.run(main())
