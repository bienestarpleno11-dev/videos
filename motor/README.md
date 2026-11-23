# Motor de Shorts — Hábitos Fix Hoy

Convierte un guion en JSON en un Short vertical terminado, con voz argentina.
Corre solo en GitHub Actions: no hay que instalar ni ejecutar nada a mano.

## Cómo se usa

1. Se sube un archivo a `guiones/<fecha>-<tema>.json`.
2. GitHub Actions genera la voz con Edge TTS, arma el video y lo commitea en
   `shorts/<id>.mp4`.
3. El MP4 también queda como artefacto descargable de la corrida.

También se puede disparar a mano desde la pestaña Actions, con
*Armar Short* → *Run workflow*, indicando un guion o dejándolo vacío para todos.

## Formato del guion

```json
{
  "id": "2026-11-24-aguinaldo",
  "voz": "es-AR-TomasNeural",
  "rate": "+8%",
  "serie": "1 de 5",
  "escenas": [
    {
      "pantalla": "¿EL AGUINALDO YA TIENE *DUEÑO*?",
      "locucion": "¿El aguinaldo ya tiene dueño antes de que lo cobres?",
      "paleta": "verde"
    }
  ]
}
```

- `pantalla`: el texto grande. Lo que va entre `*asteriscos*` se pinta en amarillo.
- `locucion`: lo que se escucha. Define cuánto dura la escena y alimenta
  los subtítulos karaoke, que se sincronizan palabra por palabra.
- `video`: URL o ruta de un clip MP4 vertical de fondo. Es lo que mejor
  queda: metraje real en movimiento. Si el clip dura menos que la escena,
  se repite.
- `fondo`: una imagen, por si no hay clip. Lleva un zoom lento.
- Si no hay ni `video` ni `fondo`, se genera un fondo con profundidad a
  partir de la paleta. El orden de preferencia es video, imagen, generado.

Sobre el metraje real se aplica solo un oscurecido, un tinte de la paleta,
un degradado abajo y una viñeta, para que el texto blanco se lea siempre.
- `paleta`: `verde`, `oscuro`, `naranja`, `bordo` o `azul`. Si no se indica, van rotando.
- `serie`: el cartelito de arriba, por ejemplo `1 de 5`. Opcional.

La última escena lleva `habitosfixhoy` abajo, siempre.

## Música

Si hay un MP3 en `motor/musica/`, se mezcla solo bajo la voz, con entrada
y salida suaves. Se usa el primero por orden alfabético. Con `musica` en
el guion se puede indicar otro, y con `volumen_musica` subirlo o bajarlo
(por defecto 0.08, bien atrás).

## Voces argentinas

- `es-AR-TomasNeural` — masculina
- `es-AR-ElenaNeural` — femenina

`rate` acelera o frena la locución: `+8%` va bien para Shorts.

## Archivos

- `motor/voz.py` — genera los MP3 de cada escena.
- `motor/render.py` — dibuja las escenas y las arma con ffmpeg.
- `motor/fuentes/` — las tipografías, versionadas para que el render sea igual siempre.
- `.github/workflows/short.yml` — el que dispara todo.

## Costo

Cero. Edge TTS es gratis y GitHub Actions corre dentro del plan gratuito.
