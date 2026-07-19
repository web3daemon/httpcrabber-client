<div align="center">

# 🦀 httpcrabber

**Interceptor de tráfico a nivel de red para hacer ingeniería inversa de APIs web.**
Invisible para las protecciones JavaScript de la página, porque nunca entra en ella.

[English](README.md) · [Русский](README.ru.md) · **Español** · [中文](README.zh.md)

[![Python 3.11+](assets/badge-python.svg)](https://www.python.org/)
[![Licencia GPL-3.0](assets/badge-license.svg)](LICENSE)
[![Plataforma Windows](assets/badge-platform.svg)](#requisitos)
[![Basado en mitmproxy](assets/badge-mitmproxy.svg)](https://mitmproxy.org/)

</div>

---

```
┌────────────────────────────── ● SESSION LIVE ───────────────────────────────┐
│                                                                             │
│    Session  TARGET RECON                                                    │
│   Upstream  socks5://user:****@1.2.3.4:1080                                 │
│  mitmproxy  127.0.0.1:8080                                                  │
│        Log  LOGS/target_recon                                               │
│                                                                             │
│   ⠸  LIVE INTERCEPT                                                         │
│   14:22:07  GET    200  https://cdn.target.com/static/js/main.a3f1c8.c…     │
│   14:22:07  POST   403  https://api.target.com/v2/auth/challenge            │
│   14:22:08  GET    304  https://target.com/assets/app.css                   │
│   14:22:08  POST   200  https://api.target.com/v2/graphql                   │
│   14:22:09  WS     →    wss://realtime.target.com/socket                    │
│   14:22:09  WS     ←    wss://realtime.target.com/socket                    │
│   14:22:10  GET    500  https://api.target.com/v2/telemetry/collect         │
│   14:22:11  ERR    ···  https://blocked.tracker.io/beacon                   │
│   14:22:12  DELETE 204  https://api.target.com/v2/session                   │
│                                                                             │
│   REQ 1478 RESP 1443 WS 12 JS 38 ERR 2        ▂▆█▄▂▁ ▁▄  03:41              │
│                                                                             │
│        Close Chrome or press Ctrl+C to finish and save the session.         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

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
| 💚 **CLI hacker animada** | Lluvia matrix, banner con glitch, máquina de escribir, líneas `[ OK ]`, spinners |
| 📡 **Feed de intercepción en vivo** | Peticiones en tiempo real, métodos y códigos de estado coloreados, sparkline de tráfico |
| 🧅 **Cualquier proxy upstream** | `socks5` / `http` / `https`, con o sin autenticación, en todas las notaciones habituales |
| 🗂 **Una carpeta por sesión** | Volcado de red y scripts juntos: archiva o comparte una sesión como una unidad |
| 📜 **Captura completa de JavaScript** | Bundles externos y bloques `<script>` en línea, completos y deduplicados |
| 🌐 **Chrome se inicia solo** | Lanzado a través del proxy con un perfil dedicado |
| 🔐 **Configuración automática de CA** | El certificado se comprueba e instala en el primer arranque |
| ⏹ **Cierre seguro** | Termina al cerrar Chrome *o* con `Ctrl+C`: el volcado se guarda igualmente |
| 🌍 **Interfaz bilingüe** | Ruso e inglés, elegido al inicio |

## Requisitos

- **Python 3.11+**
- **Google Chrome**
- **Windows** — la instalación del certificado usa `certutil` y Chrome se localiza mediante
  rutas de Windows. Linux y macOS aún no están soportados (se aceptan contribuciones).

## Instalación

```bash
git clone https://github.com/web3daemon/httpcrabber-client.git
cd httpcrabber-client

python -m venv .venv
.venv\Scripts\Activate.ps1        # PowerShell
# source .venv/bin/activate       # bash

pip install -r requirements.txt
```

## Inicio rápido

```bash
python httpcrabber.py
```

La herramienta pide tres cosas y se encarga del resto:

1. **Idioma** — ruso o inglés
2. **Proxy upstream** — pégalo en cualquier formato, o pulsa <kbd>Enter</kbd> para conexión directa
3. **Nombre de sesión** — por ejemplo `TARGET RECON`

Después instala el certificado CA si hace falta (confirma el diálogo de Windows una vez),
arranca Chrome a través del proxy y vuelca todo en la carpeta de sesión. Navega con
normalidad: cada petición, respuesta, trama WebSocket y script queda capturado.

Sin animación:

```bash
python httpcrabber.py --no-anim
```

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

Esquemas: `http`, `https`, `socks5`, `socks5h`, `socks4`.
La contraseña se enmascara en la interfaz.

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

```
  Chrome ──▶ mitmproxy ──▶ puente pproxy ──▶ tu proxy upstream ──▶ objetivo
             (captura)      (adaptador de esquemas)
```

mitmproxy solo soporta de forma nativa proxies upstream `http`/`https`. Para que **SOCKS5**
funcione de forma transparente, httpcrabber levanta un puente local
[pproxy](https://github.com/qwj/python-proxy) que habla HTTP con mitmproxy y cualquier
esquema con tu proxy. Ambos saltos van por loopback, así que la sobrecarga es insignificante.

## ⚠️ Seguridad

**El tráfico capturado contiene credenciales activas.** Los volcados de sesión incluyen de
forma habitual cabeceras `Cookie`, `Set-Cookie`, `Authorization`, claves de API y tokens de
todos los sitios que visitaste durante la sesión.

- `LOGS/` y `*.jsonl` están excluidos en [`.gitignore`](.gitignore) — **que siga así**.
- Nunca subas, publiques ni compartas un volcado de sesión sin revisarlo antes.
- Trata una carpeta de sesión como si fuera la exportación de tu gestor de contraseñas.
  Porque en la práctica lo es.

## Uso responsable

Esta es una herramienta para investigación de seguridad, depuración de APIs y trabajos de
interoperabilidad sobre sistemas que te pertenecen o que tienes autorización para probar.
Eres responsable de cumplir la legislación aplicable, los términos de servicio de los sitios
a los que accedes y la privacidad de los datos de terceros que encuentres. No la uses para
acceder a sistemas sin permiso.

## Licencia

[GNU General Public License v3.0](LICENSE) — texto completo en el archivo de licencia.
