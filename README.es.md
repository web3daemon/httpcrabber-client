<div align="center">

<img src="assets/logo.svg" alt="httpcrabber" width="880">

### Interceptor de tráfico a nivel de red para hacer ingeniería inversa de APIs web

Invisible para las protecciones JavaScript de la página, porque nunca entra en ella.

[![CI](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml/badge.svg)](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml)
[![Versión v1.1.0](assets/badge-version.svg)](https://github.com/web3daemon/httpcrabber-client/releases/latest)
[![Python 3.11+](assets/badge-python.svg)](https://www.python.org/)
[![Plataformas Windows · macOS · Linux](assets/badge-platform.svg)](#requisitos)
[![Licencia GPL-3.0](assets/badge-license.svg)](LICENSE)
[![Basado en mitmproxy](assets/badge-mitmproxy.svg)](https://mitmproxy.org/)

[English](README.md) · [Русский](README.ru.md) · **Español** · [中文](README.zh.md)

<br>

<img src="assets/demo.svg" alt="Demo de httpcrabber: arranque, intercepción en vivo, resumen" width="100%">

[**Características**](#características) · [**Instalación**](#instalación) · [**Inicio rápido**](#inicio-rápido) · [**Línea de comandos**](#línea-de-comandos) · [**Qué se guarda**](#qué-se-guarda) · [**Cómo funciona**](#cómo-funciona) · [**Seguridad**](#-seguridad)

</div>

## ⚡ En marcha en 30 segundos

```bash
pip install git+https://github.com/web3daemon/httpcrabber-client.git
httpcrabber
```

Responde tres preguntas, navega con normalidad y cierra Chrome: cada petición, respuesta, trama WebSocket y script de la sesión queda en `LOGS/<nombre>/`.

## Por qué

Las DevTools del navegador se pueden detectar. El JavaScript antibot (Kasada, Cloudflare,
Vercel BotID) comprueba de forma rutinaria si hay un depurador conectado, si el panel de
desarrollador está abierto o si la pila de red ha sido manipulada desde dentro de la página.

**httpcrabber opera por debajo de todo eso.** Es un proxy HTTPS basado en
[mitmproxy](https://mitmproxy.org/): el tráfico se captura en el cable, no en la página.
Desde el punto de vista del JavaScript, ahí no hay nada.

## Características

| | |
|---|---|
| 💚 **CLI hacker animada** | Lluvia matrix, banner con glitch en degradado, máquina de escribir, insignias de estado a color, spinners en esperas reales |
| 📡 **Feed de intercepción en vivo** | Peticiones en tiempo real, métodos y códigos de estado coloreados, contadores, sparkline de tráfico |
| 📊 **Analítica de sesión** | Hosts principales, desglose por método y estado, duración y tamaño del volcado al terminar |
| 🧅 **Cualquier proxy upstream** | `socks5` / `socks5h` / `socks4` / `http` / `https`, con o sin autenticación, en todas las notaciones habituales |
| 🗂 **Una carpeta por sesión** | Volcado de red y scripts juntos: archiva o comparte una sesión como una unidad |
| 📜 **Captura completa de JavaScript** | Bundles externos y bloques `<script>` en línea, completos y deduplicados por SHA-256 |
| 🌐 **Chrome se inicia solo** | A través del proxy con un perfil dedicado, o usa tu propio navegador con `--no-browser` |
| 🔐 **Configuración automática de CA** | El certificado se comprueba e instala en el primer arranque, en Windows, macOS y Linux |
| ⌨️ **Automatizable** | Cada pregunta tiene su flag; pásalos todos y no se pregunta nada |
| ⏹ **Cierre seguro** | Termina al cerrar Chrome *o* con `Ctrl+C`: el volcado se guarda y los procesos hijos se limpian igualmente |
| 🌍 **Interfaz bilingüe** | Ruso e inglés, elegido al inicio o con `--lang` |

## Requisitos

- **Python 3.11+**
- **Google Chrome** o **Chromium** (opcional con `--no-browser`)

| SO | Detección del navegador | Instalación del certificado CA |
|---|---|---|
| **Windows** | Program Files, LocalAppData | `certutil -user` en el almacén Root del usuario: Windows muestra un diálogo de confirmación |
| **macOS** | `/Applications`, `~/Applications` | `security add-trusted-cert` en el llavero de inicio de sesión: macOS pide tu contraseña una vez |
| **Linux** | `google-chrome`, `chromium` en el `PATH` | Base NSS `~/.pki/nssdb` mediante `certutil` de **libnss3-tools** (`sudo apt install libnss3-tools`): es la que lee Chrome. Firefox tiene su propio almacén; instálalo desde http://mitm.it |

Define `HTTPCRABBER_BROWSER=/ruta/a/chrome` para forzar el navegador en cualquier SO.

## Instalación

```bash
pip install git+https://github.com/web3daemon/httpcrabber-client.git
httpcrabber --version
```

O desde un clon, para desarrollo:

```bash
git clone https://github.com/web3daemon/httpcrabber-client.git
cd httpcrabber-client
python -m venv .venv && source .venv/bin/activate     # .venv\Scripts\Activate.ps1 en Windows
pip install -e ".[dev]"
```

¿Sin instalar nada? `python run.py` funciona directamente desde el clon.

## Inicio rápido

```bash
httpcrabber
```

La herramienta pide tres cosas y se encarga del resto:

1. **Idioma** — ruso o inglés
2. **Proxy upstream** — pégalo en cualquier formato, o pulsa <kbd>Enter</kbd> para conexión directa
3. **Nombre de sesión** — por ejemplo `TARGET RECON`

<p align="center">
  <img src="assets/screen-start.svg" alt="Arranque de httpcrabber: banner, resumen de sesión, estados" width="100%">
</p>

Muestra un resumen de la sesión, instala el certificado CA si hace falta, arranca Chrome a
través del proxy y vuelca todo en la carpeta de sesión. Navega con normalidad: cada
petición, respuesta, trama WebSocket y script queda capturado. Cierra Chrome (o pulsa
<kbd>Ctrl+C</kbd>) para terminar; obtendrás un panel de analítica y la ruta de la carpeta.

<p align="center">
  <img src="assets/screen-summary.svg" alt="Resumen de sesión de httpcrabber" width="100%">
</p>

## Línea de comandos

Cada pregunta tiene su flag. Pásalos todos y httpcrabber no pregunta nada: ideal para scripts.

```bash
httpcrabber --lang en --session "target recon" --proxy socks5://user:pass@1.2.3.4:1080
httpcrabber -l en -s quick --direct --no-browser          # tu propio navegador / dispositivo
httpcrabber --no-anim                                      # salida sin animaciones
```

| Flag | Significado |
|---|---|
| `-l, --lang {ru,en}` | Idioma de la interfaz |
| `-s, --session NAME` | Nombre de sesión → `LOGS/<name>/` |
| `-p, --proxy PROXY` | Proxy upstream en cualquier [formato](#formatos-de-proxy) |
| `--direct` | Sin proxy upstream |
| `--port PORT` | Puerto de escucha de mitmproxy (por defecto `8080`; si está ocupado, el siguiente libre) |
| `-o, --output DIR` | Dónde guardar las sesiones (por defecto `./LOGS`) |
| `--no-browser` | No lanzar Chrome: apunta cualquier navegador o dispositivo a `127.0.0.1:<port>` |
| `--no-anim` | Desactivar animaciones |
| `-V, --version` | Mostrar versión |

## Formatos de proxy

Se aceptan todas las notaciones habituales. Entrada vacía y <kbd>Enter</kbd> para conexión directa.

```
host:port
host:port:user:pass
user:pass@host:port
socks5://user:pass@host:port
http://host:port
https://user:pass@host:port
```

Esquemas: `http`, `https`, `socks5`, `socks5h`, `socks4`. La contraseña se enmascara en la interfaz.

## Qué se guarda

Cada sesión es una carpeta autocontenida:

```
LOGS/
└── target_recon/
    ├── target_recon.jsonl                     # volcado de red
    └── js/
        ├── index.json                         # manifiesto: url, archivo, sha256, tamaño, hits
        ├── cdn.target.com/
        │   └── main.a3f1c8d4.js               # scripts externos
        └── target.com/
            └── inline/inline_0001.e5f6a7b8.js # bloques <script> en línea
```

Si ya existe una sesión con ese nombre, se añade `_2`, `_3` … **Nunca se sobrescribe nada.**

### Volcado de red

Un objeto JSON por línea, con un campo `event`:
`request` · `response` · `ws_open` · `ws_msg` · `ws_close` · `error`.
Cada registro se vuelca a disco de inmediato: un fallo o un cierre forzado no pierde nada.

### JavaScript capturado

- **Los scripts se guardan completos.** Los cuerpos dentro del `.jsonl` se truncan a 200 KB,
  pero los archivos en `js/` son el código fuente íntegro: un bundle minificado de 5 MB se
  guarda entero.
- **Los duplicados se colapsan por SHA-256.** Un bundle pedido cien veces se almacena una
  vez, con `hits: 100` en el manifiesto.
- **Los scripts en línea se extraen** del HTML. Las etiquetas con `src=` se omiten (llegan
  como su propia petición), igual que `application/ld+json` y `text/template`: no son código.
- Los nombres de archivo llevan un hash corto del contenido, así distintas compilaciones del
  mismo `app.js` nunca se sobrescriben.

## Cómo funciona

```mermaid
flowchart LR
    B["🌐 Chrome"] -->|HTTPS| M["🦀 mitmproxy<br/><sub>captura</sub>"]
    M --> P["🔌 puente pproxy<br/><sub>adaptador de esquemas</sub>"]
    P -->|"socks5 · http"| U["🧅 tu proxy upstream"]
    U --> T["🎯 objetivo"]
    M -.-> F[("📁 LOGS/sesión<br/><sub>JSONL + JS</sub>")]

    classDef hop fill:#0b0f0c,stroke:#39ff14,color:#d6ded6,stroke-width:1.5px
    classDef core fill:#0b0f0c,stroke:#ff2fd0,color:#ffffff,stroke-width:2px
    classDef store fill:#0b0f0c,stroke:#00e5ff,color:#d6ded6,stroke-width:1.5px
    class B,P,U,T hop
    class M core
    class F store
```

mitmproxy solo soporta de forma nativa proxies upstream `http`/`https`. Para que **SOCKS5**
funcione de forma transparente, httpcrabber levanta un puente local
[pproxy](https://github.com/qwj/python-proxy) que habla HTTP con mitmproxy y cualquier
esquema con tu proxy. Ambos saltos van por loopback, así que la sobrecarga es insignificante.

```
src/httpcrabber/
  cli.py       argumentos, prompts, main()
  session.py   orquestación: puente → mitmproxy → CA → navegador → bucle en vivo
  capture.py   addon de mitmproxy: volcado JSONL, colector de JS, estadísticas en vivo
  proxy.py     parser del proxy upstream      bridge.py   puente pproxy
  ca.py        instalación de CA por SO       browser.py  detección de Chrome por SO
  ui.py        animaciones, paneles, feed     i18n.py     textos de la interfaz
```

## ⚠️ Seguridad

**El tráfico capturado contiene credenciales activas.** Los volcados de sesión incluyen de
forma habitual cabeceras `Cookie`, `Set-Cookie`, `Authorization`, claves de API y tokens de
todos los sitios que visitaste durante la sesión.

- `LOGS/` y `*.jsonl` están excluidos en [`.gitignore`](.gitignore) — **que siga así**.
- Nunca subas, publiques ni compartas un volcado de sesión sin revisarlo antes.
- Trata una carpeta de sesión como si fuera la exportación de tu gestor de contraseñas.
  Porque en la práctica lo es.
- La herramienta instala una CA raíz generada localmente. [SECURITY.md](SECURITY.md) explica
  cómo eliminarla cuando termines.

## Uso responsable

Esta es una herramienta para investigación de seguridad, depuración de APIs y trabajos de
interoperabilidad sobre sistemas que te pertenecen o que tienes autorización para probar.
Eres responsable de cumplir la legislación aplicable, los términos de servicio de los sitios
a los que accedes y la privacidad de los datos de terceros que encuentres. No la uses para
acceder a sistemas sin permiso.

## Contribuir

Issues y pull requests son bienvenidos: en [CONTRIBUTING.md](CONTRIBUTING.md) están la
configuración, las convenciones y cómo añadir un idioma. Los reportes de seguridad van por
[SECURITY.md](SECURITY.md).

```bash
ruff check src tests run.py && pytest
```

## Licencia

[GNU General Public License v3.0](LICENSE) — texto completo en el archivo de licencia.
