"""
interfaz.py
===========

CIRCULAR MUSIC · Powered by Linked Structures
Interfaz gráfica (Tkinter) — rediseño "Dark Premium" inspirado en
Spotify Desktop, con identidad visual propia.

Responsabilidades de este módulo
--------------------------------
* Construir y dibujar toda la ventana.
* Traducir las acciones del usuario en llamadas a los callbacks que
  entrega el backend mediante ``configurar_callbacks``.
* Representar el estado que envía el backend mediante
  ``actualizar_estado``.

Lo que este módulo NO hace
--------------------------
* No implementa la lista doblemente enlazada circular.
* No reproduce audio ni importa pygame.
* No decide el comportamiento circular (siguiente / anterior).

La lista ``estado["canciones"]`` es una "fotografía" del recorrido de
la estructura real (desde la cabeza siguiendo las referencias
``siguiente``). Se usa únicamente para dibujar.

Calidad visual sin dependencias externas
----------------------------------------
* Nitidez real en pantallas con escala (125 %, 150 %, 4K): el programa
  se declara "DPI aware" en Windows y escala todas sus medidas.
* Portadas, esquinas redondeadas y botones circulares se generan como
  imágenes con antialiasing (bordes suaves) usando solo Python estándar.
  Las imágenes grandes se generan por partes para no congelar la ventana.

Contrato público (NO cambia)
----------------------------
    from interfaz import ReproductorUI

    ui = ReproductorUI()
    ui.configurar_callbacks({...})
    ui.actualizar_estado({...})
    ui.mainloop()
"""

from __future__ import annotations

import copy
import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
import unicodedata
import warnings
from collections import deque
from tkinter import filedialog, ttk
from typing import Callable

# ======================================================================
# 1. CONFIGURACIÓN GENERAL
# ======================================================================

COLORES = {
    "fondo": "#08090B",          # fondo de la aplicación (casi negro)
    "panel": "#121317",          # paneles principales
    "elevado": "#1B1D22",        # tarjetas, buscador, botones
    "hover": "#24272D",          # elementos bajo el cursor
    "activo": "#2E3139",         # elementos seleccionados
    "borde": "#2B2E36",
    "borde_suave": "#1E2026",
    "texto": "#F4F5F7",
    "texto_sec": "#A4A9B4",
    "texto_tenue": "#6C717D",
    "acento": "#9B7BFF",         # identidad CIRCULAR MUSIC (violeta)
    "acento_hover": "#B49CFF",
    "acento_suave": "#221C3D",
    "acento_texto": "#B9A5FF",
    "siguiente": "#43D3F0",      # referencias "siguiente"
    "anterior": "#B79CFF",       # referencias "anterior"
    "exito": "#3DDC97",
    "advertencia": "#F5C04A",
    "error": "#FF6B7A",
    "esqueleto": "#1C1E24",
    "esqueleto_brillo": "#2B2E36",
    "pista": "#3F424B",
    "menu": "#22242B",
    "menu_hover": "#31343D",
    "toast": "#F3F4F6",
    "toast_texto": "#0E0F12",
    "tooltip": "#2B2E36",
    "icono_oscuro": "#0D0B16",
}

# Color superior del encabezado de la biblioteca.
COLOR_BIBLIOTECA = "#3B2C78"

# Pares (claro, profundo) para las portadas generadas.
PALETAS_PORTADA = [
    ("#8B7BFF", "#24186A"),
    ("#FF7AB6", "#561844"),
    ("#4FD1C5", "#0D3A4F"),
    ("#FFB25B", "#62202E"),
    ("#7FB2FF", "#192A68"),
    ("#B4F06C", "#1C4A38"),
    ("#E08BFF", "#36145C"),
    ("#5EE0FF", "#113C5A"),
]

FUENTES_TEXTO = ("Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text",
                 "Helvetica Neue", "Ubuntu", "Cantarell", "DejaVu Sans", "Arial")
FUENTES_TITULO = ("Segoe UI Variable Display", "Segoe UI", "Inter", "SF Pro Display",
                  "Helvetica Neue", "Ubuntu", "DejaVu Sans", "Arial")
FUENTES_MONO = ("Cascadia Mono", "Consolas", "JetBrains Mono", "Menlo",
                "DejaVu Sans Mono", "Courier New")

TIPOS_AUDIO = [
    ("Archivos de audio", "*.mp3 *.wav *.ogg"),
    ("MP3", "*.mp3"),
    ("WAV", "*.wav"),
    ("OGG", "*.ogg"),
]

CALLBACKS_CONOCIDOS = (
    "agregar_archivos",
    "eliminar_cancion",
    "seleccionar_cancion",
    "alternar_reproduccion",
    "siguiente",
    "anterior",
    "cambiar_volumen",
    "buscar_posicion",
    "alternar_favorito",
    "alternar_aleatorio",
    "alternar_repeticion",
    "guardar_preferencia",
    "cerrar",
)

ESTADO_INICIAL = {
    "canciones": [],
    "actual_id": None,
    "reproduciendo": False,
    "posicion": 0.0,
    "volumen": 0.75,
    "mensaje": "",
    "favoritos": None,
    "recientes": None,
    "aleatorio": False,
    "repetir_uno": False,
}

VISTAS = {"inicio": "Inicio", "biblioteca": "Biblioteca",
          "estructura": "Estructura", "ajustes": "Ajustes"}

PREFERENCIAS_POR_DEFECTO = {
    "panel_derecho": True,
    "barra_contraida": False,
    "animaciones": True,
    "mostrar_ids": True,
}

INTERVALO_COLA_MS = 40     # revisión de estados enviados desde otros hilos
MAX_RECIENTES = 12

# Factor de escala de pantalla (1.0 = 100 %). Se calcula al crear la ventana.
_ESCALA = 1.0
_FABRICA: "FabricaImagenes | None" = None


def S(valor: float) -> int:
    """Convierte medidas de diseño (a 100 %) en píxeles reales de pantalla."""
    return int(round(valor * _ESCALA))


def activar_alta_resolucion() -> None:
    """En Windows pide nitidez real en pantallas con escala (125 %, 150 %, 4K).

    Sin esto, Windows agranda la ventana como una imagen y todo se ve
    borroso. Debe llamarse ANTES de crear la ventana de Tkinter.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001 - si falla, la app funciona igual
        pass


# ======================================================================
# 2. UTILIDADES (sin estado)
# ======================================================================

def limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def numero_finito(valor) -> float | None:
    """Convierte a float; devuelve None si no es un número finito."""
    if isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if math.isnan(numero) or math.isinf(numero):
        return None
    return numero


def duracion_valida(valor) -> float | None:
    numero = numero_finito(valor)
    return numero if numero is not None and numero > 0 else None


def formatear_tiempo(segundos) -> str:
    """00:00 (o 0:00:00 si supera una hora); '--:--' si es desconocido."""
    numero = numero_finito(segundos)
    if numero is None:
        return "--:--"
    total = int(max(0.0, numero))
    horas, resto = divmod(total, 3600)
    minutos, segs = divmod(resto, 60)
    if horas:
        return f"{horas}:{minutos:02d}:{segs:02d}"
    return f"{minutos:02d}:{segs:02d}"


def formatear_duracion_total(segundos: float) -> str:
    total = int(max(0, segundos))
    horas, resto = divmod(total, 3600)
    minutos, segs = divmod(resto, 60)
    if horas:
        return f"{horas} h {minutos:02d} min"
    return f"{minutos} min {segs:02d} s"


def mezclar_color(color_a: str, color_b: str, proporcion: float) -> str:
    """Interpola dos colores #RRGGBB."""
    proporcion = limitar(proporcion, 0.0, 1.0)
    canales = []
    for i in (1, 3, 5):
        a = int(color_a[i:i + 2], 16)
        b = int(color_b[i:i + 2], 16)
        canales.append(round(a + (b - a) * proporcion))
    return "#{:02x}{:02x}{:02x}".format(*canales)


def truncar_texto(texto: str, fuente: tkfont.Font, ancho_maximo: float) -> str:
    """Recorta con '…' para que el texto quepa en ``ancho_maximo`` píxeles."""
    if ancho_maximo <= 0:
        return ""
    if fuente.measure(texto) <= ancho_maximo:
        return texto
    bajo, alto = 0, len(texto)
    while bajo < alto:
        medio = (bajo + alto + 1) // 2
        if fuente.measure(texto[:medio].rstrip() + "…") <= ancho_maximo:
            bajo = medio
        else:
            alto = medio - 1
    return texto[:bajo].rstrip() + "…"


def normalizar_busqueda(texto: str) -> str:
    """Minúsculas y sin tildes, para buscar 'cancion' y encontrar 'Canción'."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).casefold().strip()


def clasificar_mensaje(texto: str) -> str:
    minusculas = texto.lower()
    if any(p in minusculas for p in ("error", "no se pudo", "falló", "fallo",
                                       "inválid", "invalid", "no encontrado")):
        return "error"
    if any(p in minusculas for p in ("advertencia", "atención", "aviso")):
        return "advertencia"
    return "info"


def normalizar_estado(estado: dict) -> dict:
    """Valida el estado recibido y devuelve una COPIA limpia y coherente.

    No reordena las canciones: el orden es el recorrido real de la lista.
    """
    if not isinstance(estado, dict):
        raise TypeError("El estado debe ser un diccionario.")

    canciones = []
    for elemento in estado.get("canciones") or []:
        if not isinstance(elemento, dict):
            continue
        try:
            id_cancion = int(elemento["id"])
        except (KeyError, TypeError, ValueError):
            continue
        canciones.append({
            "id": id_cancion,
            "titulo": str(elemento.get("titulo") or "Sin título"),
            "artista": str(elemento.get("artista") or "Artista desconocido"),
            "duracion": duracion_valida(elemento.get("duracion")),
            "ruta": str(elemento.get("ruta") or ""),
            "album": str(elemento.get("album") or "Sin álbum"),
        })

    ids = {c["id"] for c in canciones}
    actual_id = estado.get("actual_id")
    try:
        actual_id = int(actual_id) if actual_id is not None else None
    except (TypeError, ValueError):
        actual_id = None
    if actual_id not in ids:
        actual_id = None

    duracion_actual = next((c["duracion"] for c in canciones if c["id"] == actual_id), None)
    posicion = max(0.0, numero_finito(estado.get("posicion")) or 0.0)
    if duracion_actual is not None:
        posicion = min(posicion, duracion_actual)

    volumen = numero_finito(estado.get("volumen"))
    volumen = limitar(volumen, 0.0, 1.0) if volumen is not None else 0.75

    return {
        "canciones": canciones,
        "actual_id": actual_id,
        "reproduciendo": bool(estado.get("reproduciendo")) and actual_id is not None,
        "posicion": posicion,
        "volumen": volumen,
        "mensaje": str(estado.get("mensaje") or ""),
        "favoritos": ([str(r) for r in estado["favoritos"] if isinstance(r, str)]
                      if isinstance(estado.get("favoritos"), (list, tuple, set)) else None),
        "recientes": ([str(r) for r in estado["recientes"] if isinstance(r, str)]
                     if isinstance(estado.get("recientes"), (list, tuple)) else None),
        "aleatorio": bool(estado.get("aleatorio", False)),
        "repetir_uno": bool(estado.get("repetir_uno", False)),
    }


# ----------------------------------------------------------------------
# Preferencias (se guardan en un pequeño archivo JSON)
# ----------------------------------------------------------------------

def ruta_preferencias() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "CircularMusic", "preferencias.json")


def cargar_preferencias() -> dict:
    preferencias = dict(PREFERENCIAS_POR_DEFECTO)
    try:
        with open(ruta_preferencias(), encoding="utf-8") as archivo:
            datos = json.load(archivo)
        for clave, defecto in PREFERENCIAS_POR_DEFECTO.items():
            if isinstance(datos.get(clave), type(defecto)):
                preferencias[clave] = datos[clave]
    except (OSError, ValueError, TypeError, AttributeError):
        pass  # primera ejecución o archivo dañado: valores por defecto
    return preferencias


def guardar_preferencias(preferencias: dict) -> bool:
    ruta = ruta_preferencias()
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(preferencias, archivo, indent=2)
    except OSError:
        return False
    return True


# ======================================================================
# 3. IMÁGENES CON ANTIALIASING (solo Python estándar)
# ======================================================================
#
# Tkinter no suaviza los bordes de las figuras. Para lograr bordes
# limpios se generan pequeñas imágenes calculando, para cada píxel, qué
# fracción queda dentro de la figura (antialiasing analítico).

def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _hex(c) -> str:
    return "#%02x%02x%02x" % (int(c[0] + 0.5), int(c[1] + 0.5), int(c[2] + 0.5))


def _mezcla(a, b, t: float):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _cobertura(distancia_interior: float) -> float:
    """Distancia con signo (positiva dentro de la figura) -> opacidad 0..1."""
    if distancia_interior >= 0.5:
        return 1.0
    if distancia_interior <= -0.5:
        return 0.0
    return distancia_interior + 0.5


def _filas_esquina(radio: int, color: str, fondo: str, orientacion: str):
    """Cuarto de círculo: dentro ``color``, fuera ``fondo``."""
    interior, exterior = _rgb(color), _rgb(fondo)
    cx = radio if orientacion in ("nw", "sw") else 0
    cy = radio if orientacion in ("nw", "ne") else 0
    for y in range(radio):
        dy = y + 0.5 - cy
        fila = [_hex(_mezcla(exterior, interior, _cobertura(radio - math.hypot(x + 0.5 - cx, dy))))
                for x in range(radio)]
        yield "{" + " ".join(fila) + "}"


def _filas_esquina_borde(radio: int, relleno: str, borde: str, grosor: int, fondo: str,
                         orientacion: str):
    """Esquina de un rectángulo con borde: fondo / anillo del borde / relleno."""
    interior, anillo, exterior = _rgb(relleno), _rgb(borde), _rgb(fondo)
    cx = radio if orientacion in ("nw", "sw") else 0
    cy = radio if orientacion in ("nw", "ne") else 0
    for y in range(radio):
        dy = y + 0.5 - cy
        fila = []
        for x in range(radio):
            d = math.hypot(x + 0.5 - cx, dy)
            color = _mezcla(anillo, interior, _cobertura(radio - grosor - d))
            fila.append(_hex(_mezcla(exterior, color, _cobertura(radio - d))))
        yield "{" + " ".join(fila) + "}"


def _figuras_icono(icono: str | None, d: float) -> list:
    """Figuras (triángulos o cajas) de los iconos dentro de botones circulares."""
    if icono == "reproducir":
        vertices = [(0.38 * d, 0.29 * d), (0.38 * d, 0.71 * d), (0.72 * d, 0.50 * d)]
        cx = sum(v[0] for v in vertices) / 3
        cy = sum(v[1] for v in vertices) / 3
        aristas = []
        for i in range(3):
            (px, py), (qx, qy) = vertices[i], vertices[(i + 1) % 3]
            nx, ny = qy - py, -(qx - px)
            largo = math.hypot(nx, ny)
            nx, ny = nx / largo, ny / largo
            if (cx - px) * nx + (cy - py) * ny > 0:   # normal hacia fuera
                nx, ny = -nx, -ny
            aristas.append((px, py, nx, ny))
        return [("triangulo", aristas)]
    if icono == "pausa":
        return [("caja", (0.405 * d, 0.5 * d, 0.06 * d, 0.18 * d)),
                ("caja", (0.595 * d, 0.5 * d, 0.06 * d, 0.18 * d))]
    return []


def _cobertura_icono(px: float, py: float, figuras: list) -> float:
    mejor = 0.0
    for tipo, datos in figuras:
        if tipo == "triangulo":
            distancia = max((px - ax) * nx + (py - ay) * ny for ax, ay, nx, ny in datos)
        else:
            cx, cy, mx, my = datos
            distancia = max(abs(px - cx) - mx, abs(py - cy) - my)
        mejor = max(mejor, _cobertura(-distancia))
    return mejor


def _filas_circulo(diametro: int, color: str, fondo: str, icono: str | None, color_icono: str,
                   fondo_inf: str | None = None):
    """Círculo suavizado, opcionalmente con icono reproducir/pausa.

    ``fondo``/``fondo_inf`` permiten que el borde se funda con un degradado.
    """
    c, ci = _rgb(color), _rgb(color_icono)
    f_sup, f_inf = _rgb(fondo), _rgb(fondo_inf or fondo)
    radio = diametro / 2
    figuras = _figuras_icono(icono, diametro)
    for y in range(diametro):
        py = y + 0.5
        f = _mezcla(f_sup, f_inf, y / max(1, diametro - 1))
        hex_fondo = _hex(f)
        fila = []
        for x in range(diametro):
            px = x + 0.5
            a = _cobertura(radio - math.hypot(px - radio, py - radio))
            if a <= 0.0:
                fila.append(hex_fondo)
                continue
            color_px = c
            if figuras:
                ai = _cobertura_icono(px, py, figuras)
                if ai > 0:
                    color_px = _mezcla(c, ci, ai)
            fila.append(_hex(_mezcla(f, color_px, a)))
        yield "{" + " ".join(fila) + "}"


def _filas_portada(id_cancion: int, tam: int, radio: int, fondo_sup: str,
                   fondo_inf: str, sombra: int):
    """Portada geométrica "orbital" (determinista por ID) con sombra opcional.

    Motivo visual: órbitas concéntricas con nodos, en referencia a la
    lista circular. Se genera fila por fila (generador).
    """
    c1, c2 = (_rgb(c) for c in PALETAS_PORTADA[id_cancion % len(PALETAS_PORTADA)])
    blanco, negro = (255, 255, 255), (0, 0, 0)
    claro = _mezcla(c1, blanco, 0.35)
    centro_hub = _mezcla(c2, negro, 0.45)
    f_sup, f_inf = _rgb(fondo_sup), _rgb(fondo_inf)
    s = float(tam)
    total = tam + 2 * sombra

    cx_orb, cy_orb = 0.64 * s, 0.66 * s
    r0, paso, anillos = 0.15 * s, 0.085 * s, 7
    media_linea = max(0.5, s / 280)
    radio_hub = 0.085 * s
    gx, gy, gr = 0.26 * s, 0.22 * s, 0.78 * s
    nodos = []
    cantidad = 2 + id_cancion % 3
    for j in range(cantidad):
        k = 1 + (id_cancion + 2 * j) % 4
        angulo = math.radians((id_cancion * 47 + j * (360 / cantidad + 17)) % 360)
        rr = r0 + k * paso
        nodos.append((cx_orb + rr * math.cos(angulo), cy_orb + rr * math.sin(angulo),
                      0.034 * s * (1.3 if j == 0 else 1.0), j == 0))

    semi = s / 2 - radio
    centro = sombra + s / 2
    hypot = math.hypot
    for y in range(total):
        py = y + 0.5
        fondo_fila = _mezcla(f_sup, f_inf, y / max(1, total - 1))
        qy = abs(py - centro) - semi
        qy_sombra = abs(py - centro - sombra * 0.25) - semi
        v = py - sombra
        fila = []
        for x in range(total):
            px = x + 0.5
            qx = abs(px - centro) - semi
            sd = hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - radio
            fondo_px = fondo_fila
            if sombra and sd > -1.0:
                sds = hypot(max(qx, 0.0), max(qy_sombra, 0.0)) + min(max(qx, qy_sombra), 0.0) - radio
                if sds < sombra:
                    t = 1.0 - max(0.0, sds) / sombra
                    fondo_px = _mezcla(fondo_fila, negro, 0.6 * t * t)
            a = _cobertura(-sd)
            if a <= 0.0:
                fila.append(_hex(fondo_px))
                continue
            u = px - sombra
            base = _mezcla(c1, c2, (u + v) / (2 * s))
            dg = hypot(u - gx, v - gy)
            if dg < gr:
                g = 1.0 - dg / gr
                base = _mezcla(base, claro, 0.5 * g * g)
            dr = hypot(u - cx_orb, v - cy_orb)
            k = int((dr - r0) / paso + 0.5)
            if 0 <= k < anillos:
                linea = _cobertura(media_linea - abs(dr - (r0 + k * paso)) + 0.35)
                if linea > 0:
                    base = _mezcla(base, blanco, linea * (0.30 - 0.028 * k))
            hub = _cobertura(radio_hub - dr)
            if hub > 0:
                base = _mezcla(base, centro_hub, 0.92 * hub)
                punto = _cobertura(0.026 * s - dr)
                if punto > 0:
                    base = _mezcla(base, claro, punto)
            for nx, ny, rn, principal in nodos:
                dn = hypot(u - nx, v - ny)
                if dn < rn * 3.0:
                    an = _cobertura(rn - dn)
                    if an > 0:
                        base = _mezcla(base, blanco, 0.95 * an)
                    elif principal:
                        halo = _cobertura(media_linea * 1.6 - abs(dn - rn * 2.1))
                        if halo > 0:
                            base = _mezcla(base, blanco, 0.45 * halo)
            base = _mezcla(base, negro, 0.16 * v / s)
            fila.append(_hex(_mezcla(fondo_px, base, a)))
        yield "{" + " ".join(fila) + "}"


class FabricaImagenes:
    """Genera y guarda en caché las imágenes suavizadas.

    * Las pequeñas (esquinas, círculos) se crean al instante.
    * Las portadas se generan por partes con ``after`` para no congelar la
      ventana; mientras tanto se muestra un "skeleton" de carga.
    """

    PRESUPUESTO_S = 0.012   # tiempo máximo de trabajo por turno

    def __init__(self, raiz: tk.Misc):
        self._raiz = raiz
        self._cache: dict = {}
        self._esperando: dict = {}
        self._cola: deque = deque()
        self._trabajo = None
        self._filas: list[str] = []
        self._programado = False

    def hay_trabajo(self) -> bool:
        return self._trabajo is not None or bool(self._cola)

    def _crear(self, ancho: int, alto: int, filas) -> tk.PhotoImage:
        imagen = tk.PhotoImage(master=self._raiz, width=ancho, height=alto)
        imagen.put(" ".join(filas))
        return imagen

    def esquina(self, radio: int, color: str, fondo: str, orientacion: str) -> tk.PhotoImage:
        clave = ("esquina", radio, color, fondo, orientacion)
        if clave not in self._cache:
            self._cache[clave] = self._crear(radio, radio, _filas_esquina(radio, color, fondo, orientacion))
        return self._cache[clave]

    def esquina_borde(self, radio: int, relleno: str, borde: str, grosor: int, fondo: str,
                      orientacion: str) -> tk.PhotoImage:
        clave = ("esquina_borde", radio, relleno, borde, grosor, fondo, orientacion)
        if clave not in self._cache:
            self._cache[clave] = self._crear(
                radio, radio, _filas_esquina_borde(radio, relleno, borde, grosor, fondo, orientacion))
        return self._cache[clave]

    def circulo(self, diametro: int, color: str, fondo: str, icono: str | None = None,
                color_icono: str = "#000000", fondo_inf: str | None = None) -> tk.PhotoImage:
        diametro = max(2, int(diametro))
        clave = ("circulo", diametro, color, fondo, icono, color_icono, fondo_inf)
        if clave not in self._cache:
            self._cache[clave] = self._crear(
                diametro, diametro,
                _filas_circulo(diametro, color, fondo, icono, color_icono, fondo_inf))
        return self._cache[clave]

    def portada(self, id_cancion: int, tam: int, radio: int, fondo_sup: str,
                fondo_inf: str | None = None, sombra: int = 0,
                al_listo: Callable | None = None, prioridad: bool = False) -> tk.PhotoImage | None:
        """Devuelve la portada si ya existe; si no, la encola y devuelve None."""
        fondo_inf = fondo_inf or fondo_sup
        clave = ("portada", id_cancion, int(tam), int(radio), fondo_sup, fondo_inf, int(sombra))
        imagen = self._cache.get(clave)
        if imagen is not None:
            return imagen
        if al_listo is not None:
            self._esperando.setdefault(clave, set()).add(al_listo)
        en_curso = self._trabajo is not None and self._trabajo[0] == clave
        encolado = next((t for t in self._cola if t[0] == clave), None)
        if not en_curso and encolado is None:
            total = int(tam) + 2 * int(sombra)
            trabajo = (clave, _filas_portada(id_cancion, int(tam), int(radio), fondo_sup,
                                             fondo_inf, int(sombra)), total, total)
            if prioridad:
                self._cola.appendleft(trabajo)
            else:
                self._cola.append(trabajo)
        elif encolado is not None and prioridad:
            self._cola.remove(encolado)
            self._cola.appendleft(encolado)
        self._programar()
        return None

    def _programar(self) -> None:
        if not self._programado and self.hay_trabajo():
            self._programado = True
            self._raiz.after(1, self._trabajar)

    def _trabajar(self) -> None:
        self._programado = False
        limite = time.perf_counter() + self.PRESUPUESTO_S
        while time.perf_counter() < limite:
            if self._trabajo is None:
                if not self._cola:
                    return
                self._trabajo = self._cola.popleft()
                self._filas = []
            clave, generador, ancho, alto = self._trabajo
            try:
                self._filas.append(next(generador))
            except StopIteration:
                self._terminar(clave, ancho, alto)
        self._programar()

    def _terminar(self, clave, ancho: int, alto: int) -> None:
        try:
            imagen = self._crear(ancho, alto, self._filas)
        except tk.TclError:
            self._trabajo = None
            return
        self._cache[clave] = imagen
        self._trabajo = None
        self._filas = []
        for funcion in self._esperando.pop(clave, set()):
            try:
                funcion(imagen)
            except tk.TclError:
                pass  # el widget que la pidió ya no existe


def fabrica() -> FabricaImagenes:
    if _FABRICA is None:
        raise RuntimeError("Crea primero la ventana ReproductorUI.")
    return _FABRICA


# ======================================================================
# 4. DIBUJO SOBRE CANVAS E ICONOGRAFÍA
# ======================================================================

def rect_redondeado(lienzo: tk.Canvas, x0, y0, x1, y1, radio, color: str, fondo: str,
                    fondo_inf: str | None = None, tags=()) -> None:
    """Rectángulo redondeado con esquinas suavizadas.

    ``fondo`` es el color detrás de las esquinas superiores y ``fondo_inf``
    el de las inferiores (útil sobre degradados).
    """
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    r = int(min(radio, (x1 - x0) // 2, (y1 - y0) // 2))
    opciones = {"fill": color, "outline": "", "width": 0, "tags": tags}
    if r < 2:
        lienzo.create_rectangle(x0, y0, x1, y1, **opciones)
        return
    lienzo.create_rectangle(x0 + r, y0, x1 - r, y1, **opciones)
    lienzo.create_rectangle(x0, y0 + r, x0 + r, y1 - r, **opciones)
    lienzo.create_rectangle(x1 - r, y0 + r, x1, y1 - r, **opciones)
    fondo_inf = fondo_inf or fondo
    fab = fabrica()
    for orientacion, x, y, detras in (("nw", x0, y0, fondo), ("ne", x1 - r, y0, fondo),
                                      ("se", x1 - r, y1 - r, fondo_inf),
                                      ("sw", x0, y1 - r, fondo_inf)):
        lienzo.create_image(x, y, image=fab.esquina(r, color, detras, orientacion),
                            anchor="nw", tags=tags)


def rect_redondeado_borde(lienzo, x0, y0, x1, y1, radio, relleno, borde, grosor, fondo,
                          tags=(), fondo_inf: str | None = None) -> None:
    """Rectángulo redondeado con borde; las esquinas combinan fondo, borde y relleno."""
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    g = int(max(1, round(grosor)))
    r = int(min(radio, (x1 - x0) // 2, (y1 - y0) // 2))

    def rectangulo(a, b, c, d, color):
        lienzo.create_rectangle(a, b, c, d, fill=color, outline="", width=0, tags=tags)

    if r < g + 2:
        rectangulo(x0, y0, x1, y1, borde)
        rectangulo(x0 + g, y0 + g, x1 - g, y1 - g, relleno)
        return
    rectangulo(x0 + r, y0, x1 - r, y1, borde)
    rectangulo(x0, y0 + r, x1, y1 - r, borde)
    rectangulo(x0 + r, y0 + g, x1 - r, y1 - g, relleno)
    rectangulo(x0 + g, y0 + r, x1 - g, y1 - r, relleno)
    fab = fabrica()
    fondo_inf = fondo_inf or fondo
    for orientacion, x, y, detras in (("nw", x0, y0, fondo), ("ne", x1 - r, y0, fondo),
                                      ("se", x1 - r, y1 - r, fondo_inf),
                                      ("sw", x0, y1 - r, fondo_inf)):
        lienzo.create_image(x, y, anchor="nw", tags=tags,
                            image=fab.esquina_borde(r, relleno, borde, g, detras, orientacion))


def dibujar_circulo(lienzo, cx, cy, diametro, color, fondo, icono=None, color_icono="#000000",
                    tags=(), fondo_inf=None) -> None:
    lienzo.create_image(int(round(cx)), int(round(cy)), anchor="center", tags=tags,
                        image=fabrica().circulo(int(diametro), color, fondo, icono, color_icono,
                                                fondo_inf))


def _trazo(tam: float) -> float:
    return max(1.5, tam / 11)


# Todos los iconos comparten la firma (lienzo, cx, cy, tam, color, relleno, tags)

def icono_reproducir(l, cx, cy, tam, color, relleno=True, tags=()):
    m = tam / 2
    l.create_polygon(cx - m * 0.55, cy - m * 0.8, cx - m * 0.55, cy + m * 0.8, cx + m * 0.85, cy,
                     fill=color, outline=color, tags=tags)


def icono_pausa(l, cx, cy, tam, color, relleno=True, tags=()):
    barra, alto, sep = tam * 0.2, tam * 0.42, tam * 0.12
    l.create_rectangle(cx - sep - barra, cy - alto, cx - sep, cy + alto, fill=color, outline="", tags=tags)
    l.create_rectangle(cx + sep, cy - alto, cx + sep + barra, cy + alto, fill=color, outline="", tags=tags)


def icono_siguiente(l, cx, cy, tam, color, relleno=True, tags=()):
    m = tam / 2
    l.create_polygon(cx - m * 0.75, cy - m * 0.7, cx - m * 0.75, cy + m * 0.7, cx + m * 0.4, cy,
                     fill=color, outline=color, tags=tags)
    l.create_rectangle(cx + m * 0.5, cy - m * 0.7, cx + m * 0.78, cy + m * 0.7, fill=color,
                       outline="", tags=tags)


def icono_anterior(l, cx, cy, tam, color, relleno=True, tags=()):
    m = tam / 2
    l.create_polygon(cx + m * 0.75, cy - m * 0.7, cx + m * 0.75, cy + m * 0.7, cx - m * 0.4, cy,
                     fill=color, outline=color, tags=tags)
    l.create_rectangle(cx - m * 0.78, cy - m * 0.7, cx - m * 0.5, cy + m * 0.7, fill=color,
                       outline="", tags=tags)


def icono_aleatorio(l, cx, cy, tam, color, relleno=False, tags=()):
    """Dos trayectorias cruzadas (modo shuffle), completamente vectorial."""
    m, g = tam / 2, _trazo(tam)
    l.create_line(cx - m*.82, cy - m*.53, cx - m*.28, cy - m*.53,
                  cx + m*.28, cy + m*.55, cx + m*.7, cy + m*.55,
                  smooth=True, fill=color, width=g, capstyle="round", tags=tags)
    l.create_line(cx - m*.82, cy + m*.55, cx - m*.28, cy + m*.55,
                  cx + m*.28, cy - m*.53, cx + m*.7, cy - m*.53,
                  smooth=True, fill=color, width=g, capstyle="round", tags=tags)
    for y in (cy - m*.53, cy + m*.55):
        l.create_line(cx + m*.7, y, cx + m*.45, y - m*.2,
                      fill=color, width=g, tags=tags)


def icono_repetir(l, cx, cy, tam, color, relleno=False, tags=()):
    """Dos flechas formando el ciclo de repetición."""
    m, g = tam / 2, _trazo(tam)
    l.create_line(cx - m*.75, cy - m*.2, cx - m*.75, cy - m*.55,
                  cx + m*.75, cy - m*.55, cx + m*.75, cy - m*.15,
                  fill=color, width=g, capstyle="round", joinstyle="round", tags=tags)
    l.create_line(cx + m*.75, cy + m*.2, cx + m*.75, cy + m*.55,
                  cx - m*.75, cy + m*.55, cx - m*.75, cy + m*.15,
                  fill=color, width=g, capstyle="round", joinstyle="round", tags=tags)
    l.create_line(cx + m*.75, cy - m*.15, cx + m*.53, cy - m*.35, fill=color, width=g, tags=tags)
    l.create_line(cx - m*.75, cy + m*.15, cx - m*.53, cy + m*.35, fill=color, width=g, tags=tags)


def icono_inicio(l, cx, cy, tam, color, relleno=False, tags=()):
    m = tam / 2
    puntos = [cx - m * 0.72, cy + m * 0.85, cx - m * 0.72, cy - m * 0.12, cx, cy - m * 0.85,
              cx + m * 0.72, cy - m * 0.12, cx + m * 0.72, cy + m * 0.85]
    l.create_polygon(puntos, fill=color if relleno else "", outline=color, width=_trazo(tam),
                     joinstyle="round", tags=tags)
    if not relleno:
        l.create_line(cx - m * 0.22, cy + m * 0.85, cx - m * 0.22, cy + m * 0.25, cx + m * 0.22,
                      cy + m * 0.25, cx + m * 0.22, cy + m * 0.85, fill=color, width=_trazo(tam),
                      tags=tags)


def icono_biblioteca(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam) * (1.25 if relleno else 1)
    for x in (cx - m * 0.62, cx - m * 0.18):
        l.create_line(x, cy - m * 0.8, x, cy + m * 0.8, fill=color, width=w, capstyle="round", tags=tags)
    l.create_line(cx + m * 0.2, cy - m * 0.72, cx + m * 0.72, cy + m * 0.8, fill=color, width=w,
                  capstyle="round", tags=tags)


def icono_estructura(l, cx, cy, tam, color, relleno=False, tags=()):
    """Órbita con tres nodos: símbolo de la lista circular."""
    m, w = tam / 2, _trazo(tam) * 0.9
    r = m * 0.62
    l.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=w, tags=tags)
    rr = m * (0.27 if relleno else 0.22)
    for angulo in (90, 210, 330):
        x = cx + r * math.cos(math.radians(angulo))
        y = cy - r * math.sin(math.radians(angulo))
        l.create_oval(x - rr, y - rr, x + rr, y + rr, fill=color, outline=color, tags=tags)


def icono_ajustes(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam)
    for dy, posicion in ((-0.55, -0.3), (0.0, 0.35), (0.55, -0.05)):
        y = cy + dy * m
        l.create_line(cx - m * 0.8, y, cx + m * 0.8, y, fill=color, width=w, capstyle="round", tags=tags)
        x, r = cx + posicion * m, m * 0.2
        l.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=color, tags=tags)


def icono_buscar(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam) * 1.1
    r = m * 0.55
    ox, oy = cx - m * 0.15, cy - m * 0.15
    l.create_oval(ox - r, oy - r, ox + r, oy + r, outline=color, width=w, tags=tags)
    l.create_line(cx + m * 0.28, cy + m * 0.28, cx + m * 0.8, cy + m * 0.8, fill=color, width=w,
                  capstyle="round", tags=tags)


def icono_corazon(l, cx, cy, tam, color, relleno=False, tags=()):
    escala = tam / 34
    puntos = []
    for k in range(48):
        t = 2 * math.pi * k / 48
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        puntos += [cx + x * escala, cy - (y + 2.5) * escala]
    l.create_polygon(puntos, fill=color if relleno else "", outline=color, width=_trazo(tam),
                     joinstyle="round", tags=tags)


def icono_mas(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam) * 1.1
    l.create_line(cx - m * 0.8, cy, cx + m * 0.8, cy, fill=color, width=w, capstyle="round", tags=tags)
    l.create_line(cx, cy - m * 0.8, cx, cy + m * 0.8, fill=color, width=w, capstyle="round", tags=tags)


def icono_cerrar(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam) * 1.1
    l.create_line(cx - m * 0.6, cy - m * 0.6, cx + m * 0.6, cy + m * 0.6, fill=color, width=w,
                  capstyle="round", tags=tags)
    l.create_line(cx - m * 0.6, cy + m * 0.6, cx + m * 0.6, cy - m * 0.6, fill=color, width=w,
                  capstyle="round", tags=tags)


def icono_chevron_izq(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam) * 1.3
    l.create_line(cx + m * 0.3, cy - m * 0.75, cx - m * 0.35, cy, cx + m * 0.3, cy + m * 0.75,
                  fill=color, width=w, capstyle="round", joinstyle="round", tags=tags)


def icono_chevron_der(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam) * 1.3
    l.create_line(cx - m * 0.3, cy - m * 0.75, cx + m * 0.35, cy, cx - m * 0.3, cy + m * 0.75,
                  fill=color, width=w, capstyle="round", joinstyle="round", tags=tags)


def icono_papelera(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam)
    l.create_line(cx - m * 0.85, cy - m * 0.55, cx + m * 0.85, cy - m * 0.55, fill=color, width=w,
                  capstyle="round", tags=tags)
    l.create_line(cx - m * 0.3, cy - m * 0.85, cx + m * 0.3, cy - m * 0.85, fill=color, width=w,
                  capstyle="round", tags=tags)
    l.create_polygon(cx - m * 0.62, cy - m * 0.35, cx + m * 0.62, cy - m * 0.35, cx + m * 0.48,
                     cy + m * 0.9, cx - m * 0.48, cy + m * 0.9, fill="", outline=color, width=w,
                     joinstyle="round", tags=tags)


def icono_panel_lateral(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam)
    l.create_rectangle(cx - m * 0.85, cy - m * 0.72, cx + m * 0.85, cy + m * 0.72, outline=color,
                       width=w, tags=tags)
    l.create_line(cx - m * 0.28, cy - m * 0.72, cx - m * 0.28, cy + m * 0.72, fill=color, width=w,
                  tags=tags)


def icono_ahora_suena(l, cx, cy, tam, color, relleno=False, tags=()):
    m, w = tam / 2, _trazo(tam)
    l.create_rectangle(cx - m * 0.85, cy - m * 0.72, cx + m * 0.85, cy + m * 0.72, outline=color,
                       width=w, tags=tags)
    l.create_rectangle(cx + m * 0.12, cy - m * 0.4, cx + m * 0.55, cy + m * 0.4, fill=color,
                       outline="", tags=tags)


def icono_nota(l, cx, cy, tam, color, relleno=True, tags=()):
    m, w = tam / 2, _trazo(tam) * 1.2
    l.create_oval(cx - m * 0.62, cy + m * 0.22, cx - m * 0.02, cy + m * 0.78, fill=color, outline=color,
                  tags=tags)
    l.create_line(cx - m * 0.06, cy + m * 0.5, cx - m * 0.06, cy - m * 0.82, cx + m * 0.6,
                  cy - m * 0.5, fill=color, width=w, capstyle="round", joinstyle="round", tags=tags)


def icono_volumen(l, cx, cy, tam, color, nivel: float, tags=()):
    m = tam / 2
    l.create_polygon(cx - m, cy - m * 0.35, cx - m * 0.45, cy - m * 0.35, cx + m * 0.05, cy - m * 0.8,
                     cx + m * 0.05, cy + m * 0.8, cx - m * 0.45, cy + m * 0.35, cx - m, cy + m * 0.35,
                     fill=color, outline=color, tags=tags)
    w = _trazo(tam)
    if nivel <= 0:
        l.create_line(cx + m * 0.35, cy - m * 0.35, cx + m, cy + m * 0.35, width=w, fill=color,
                      capstyle="round", tags=tags)
        l.create_line(cx + m * 0.35, cy + m * 0.35, cx + m, cy - m * 0.35, width=w, fill=color,
                      capstyle="round", tags=tags)
        return
    radios = [m * 0.55] + ([m * 0.95] if nivel > 0.5 else [])
    for radio in radios:
        l.create_arc(cx - radio, cy - radio, cx + radio, cy + radio, start=-45, extent=90,
                     style=tk.ARC, outline=color, width=w, tags=tags)


VISTAS_NAVEGACION = (
    ("inicio", "Inicio", icono_inicio),
    ("biblioteca", "Biblioteca", icono_biblioteca),
    ("estructura", "Estructura", icono_estructura),
)

ESTILOS_PASTILLA = {
    # estilo: (fondo, fondo_hover, texto)
    "primario": ("acento", "acento_hover", "icono_oscuro"),
    "claro": ("texto", "#FFFFFF", "toast_texto"),
    "sutil": ("elevado", "hover", "texto"),
    "chip": ("elevado", "hover", "texto"),
    "chip_activo": ("texto", "#FFFFFF", "toast_texto"),
}


def _color(nombre: str) -> str:
    return COLORES.get(nombre, nombre)


def dibujar_pastilla(lienzo, x, cy, texto, fuente, estilo, hover, fondo, alto=None,
                     icono=None, alinear="w", habilitado=True, fondo_inf=None):
    """Botón con forma de pastilla. Devuelve su rectángulo (x0, y0, x1, y1)."""
    alto = alto or S(32)
    ancho_icono = S(16) if icono else 0
    hueco = S(8) if icono else 0
    ancho = fuente.measure(texto) + 2 * S(16) + ancho_icono + hueco
    x0 = x if alinear == "w" else x - ancho if alinear == "e" else x - ancho / 2
    y0 = cy - alto / 2
    x1, y1 = x0 + ancho, y0 + alto
    if estilo == "contorno":
        borde = COLORES["texto"] if hover and habilitado else COLORES["texto_tenue"]
        rect_redondeado_borde(lienzo, x0, y0, x1, y1, alto / 2,
                              mezclar_color(fondo, fondo_inf or fondo, 0.5), borde, max(1, S(1)),
                              fondo, fondo_inf=fondo_inf)
        color_texto = COLORES["texto"] if habilitado else COLORES["texto_tenue"]
    else:
        nombre_fondo, nombre_hover, nombre_texto = ESTILOS_PASTILLA[estilo]
        relleno = _color(nombre_hover if hover and habilitado else nombre_fondo)
        color_texto = _color(nombre_texto)
        if not habilitado:
            relleno, color_texto = COLORES["elevado"], COLORES["texto_tenue"]
        rect_redondeado(lienzo, x0, y0, x1, y1, alto / 2, relleno, fondo, fondo_inf)
    xt = x0 + S(16)
    if icono:
        icono(lienzo, xt + ancho_icono / 2, cy, S(14), color_texto)
        xt += ancho_icono + hueco
    lienzo.create_text(xt, cy, text=texto, anchor="w", font=fuente, fill=color_texto)
    return x0, y0, x1, y1


def dibujar_logo(lienzo, cx, cy, diametro, fondo) -> None:
    dibujar_circulo(lienzo, cx, cy, diametro, COLORES["acento"], fondo)
    icono_estructura(lienzo, cx, cy, diametro * 0.55, COLORES["icono_oscuro"], relleno=True)


# ======================================================================
# 5. WIDGETS BASE
# ======================================================================

class Region:
    """Zona sensible al mouse dentro de un CanvasInteractivo."""

    __slots__ = ("x0", "y0", "x1", "y1", "clave", "al_clic", "al_doble", "al_menu", "tooltip")

    def __init__(self, x0, y0, x1, y1, clave, al_clic, al_doble, al_menu, tooltip):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.clave, self.al_clic, self.al_doble = clave, al_clic, al_doble
        self.al_menu, self.tooltip = al_menu, tooltip


class CanvasInteractivo(tk.Canvas):
    """Canvas que se redibuja completo y gestiona hover, clics y tooltips.

    Las subclases implementan ``dibujar(ancho, alto)`` y registran zonas
    clicables con ``region(...)``. Los elementos con la etiqueta "fijo"
    (por ejemplo widgets incrustados) sobreviven a cada redibujado.
    """

    def __init__(self, padre, app: "ReproductorUI", fondo: str, **opciones):
        opciones.setdefault("highlightthickness", 0)
        opciones.setdefault("bd", 0)
        super().__init__(padre, bg=fondo, **opciones)
        self.app = app
        self.fondo = fondo
        self.hover = None
        self._regiones: list[Region] = []
        self._presionada = None
        self._items_eq: list = []
        self._redibujo_pendiente = False
        app.registrar_lienzo(self)
        self.bind("<Configure>", lambda _e: self.redibujar())
        self.bind("<Motion>", self._al_mover)
        self.bind("<Leave>", self._al_salir)
        self.bind("<ButtonPress-1>", self._al_presionar)
        self.bind("<ButtonRelease-1>", self._al_soltar)
        self.bind("<Double-Button-1>", self._al_doble)
        self.bind("<Button-3>", self._al_menu)
        if sys.platform == "darwin":
            self.bind("<Button-2>", self._al_menu)

    # ---------------- Dibujo ----------------

    def redibujar(self) -> None:
        self.addtag_all("borrar")
        self.dtag("fijo", "borrar")
        self.delete("borrar")
        self._regiones = []
        self._items_eq = []
        ancho, alto = self.winfo_width(), self.winfo_height()
        if ancho > 1 and alto > 1:
            self.dibujar(ancho, alto)

    def redibujar_diferido(self, *_argumentos) -> None:
        """Agrupa varias peticiones de redibujado en una sola."""
        if not self._redibujo_pendiente:
            self._redibujo_pendiente = True
            self.after_idle(self._redibujar_ahora)

    def _redibujar_ahora(self) -> None:
        self._redibujo_pendiente = False
        try:
            if self.winfo_exists():
                self.redibujar()
        except tk.TclError:
            pass

    def dibujar(self, ancho: int, alto: int) -> None:
        """Implementado por las subclases."""

    def color_fondo_en(self, y: float) -> str:
        """Color del fondo a la altura ``y`` (los degradados lo redefinen)."""
        return self.fondo

    def fondos(self, cy: float, alto: float) -> tuple[str, str]:
        """Colores de fondo arriba y abajo de un elemento centrado en ``cy``."""
        return self.color_fondo_en(cy - alto / 2), self.color_fondo_en(cy + alto / 2)

    def region(self, x0, y0, x1, y1, clave, al_clic=None, al_doble=None, al_menu=None,
               tooltip=None) -> None:
        self._regiones.append(Region(x0, y0, x1, y1, clave, al_clic, al_doble, al_menu, tooltip))

    # ---------------- Piezas reutilizables ----------------

    def portada(self, id_cancion, x, y, tam, fondo, radio=None, prioridad=False, sombra=0,
                fondo_inf=None) -> None:
        """Dibuja una portada; mientras se genera muestra un skeleton."""
        radio = S(4) if radio is None else radio
        imagen = self.app.fabrica.portada(id_cancion, tam, radio, fondo, fondo_inf, sombra,
                                          al_listo=self.redibujar_diferido, prioridad=prioridad)
        if imagen is None:
            self.create_rectangle(x, y, x + tam, y + tam, fill=COLORES["esqueleto"], outline="",
                                  tags=("esqueleto",))
        else:
            self.create_image(int(x) - sombra, int(y) - sombra, image=imagen, anchor="nw")

    def boton_icono(self, clave, cx, cy, icono, tam_icono, accion, tooltip=None, diametro=None,
                    activo=False, habilitado=True, relleno=False, fondo=None) -> None:
        """Icono con círculo de hover; ``activo`` lo pinta con el acento."""
        diametro = diametro or S(32)
        hover = self.hover == clave and habilitado
        if hover:
            arriba, abajo = (fondo, fondo) if fondo else self.fondos(cy, diametro)
            dibujar_circulo(self, cx, cy, diametro, COLORES["hover"], arriba, fondo_inf=abajo)
        if not habilitado:
            color = COLORES["texto_tenue"]
        elif activo:
            color = COLORES["acento"]
        else:
            color = COLORES["texto"] if hover else COLORES["texto_sec"]
        icono(self, cx, cy, tam_icono, color, relleno)
        self.region(cx - diametro / 2, cy - diametro / 2, cx + diametro / 2, cy + diametro / 2,
                    clave, accion if habilitado else None, tooltip=tooltip)

    def boton_reproducir(self, clave, cx, cy, diametro, reproduciendo, accion, color, color_hover,
                         fondo=None, habilitado=True, tooltip=None) -> None:
        """Botón circular suavizado con icono reproducir/pausa."""
        hover = self.hover == clave and habilitado
        if not habilitado:
            relleno, color_icono = COLORES["elevado"], COLORES["texto_tenue"]
        else:
            relleno, color_icono = (color_hover if hover else color), COLORES["icono_oscuro"]
        diametro_real = diametro + (S(2) if hover else 0)
        arriba, abajo = (fondo, fondo) if fondo else self.fondos(cy, diametro_real)
        dibujar_circulo(self, cx, cy, diametro_real, relleno, arriba,
                        "pausa" if reproduciendo else "reproducir", color_icono, fondo_inf=abajo)
        self.region(cx - diametro / 2, cy - diametro / 2, cx + diametro / 2, cy + diametro / 2,
                    clave, accion if habilitado else None, tooltip=tooltip)

    def ecualizador(self, x, y_base, color) -> None:
        """Tres barras que se animan mientras suena una canción."""
        for k in range(3):
            bx = x + k * S(4.5)
            item = self.create_rectangle(bx, y_base - S(5), bx + S(3), y_base, fill=color, outline="")
            self._items_eq.append((item, bx, y_base, k))

    def animar_ecualizador(self, fase: float) -> None:
        for item, bx, y_base, k in self._items_eq:
            altura = S(3) + S(10) * (0.5 + 0.5 * math.sin(fase * (1.0 + 0.37 * k) + k * 2.1))
            self.coords(item, bx, y_base - altura, bx + S(3), y_base)

    # ---------------- Eventos ----------------

    def _region_en(self, evento) -> Region | None:
        x, y = self.canvasx(evento.x), self.canvasy(evento.y)
        for region in reversed(self._regiones):
            if region.x0 <= x < region.x1 and region.y0 <= y < region.y1:
                return region
        return None

    def _al_mover(self, evento) -> None:
        region = self._region_en(evento)
        clave = region.clave if region else None
        clicable = region is not None and (region.al_clic or region.al_doble)
        self.configure(cursor="hand2" if clicable else "")
        if clave != self.hover:
            self.hover = clave
            self.al_cambiar_hover()
            self.redibujar()
            if region is not None and region.tooltip:
                self.app.tooltips.programar(self, region)
            else:
                self.app.tooltips.ocultar()

    def al_cambiar_hover(self) -> None:
        """Gancho para animaciones de hover (opcional)."""

    def _al_salir(self, _evento) -> None:
        self.app.tooltips.ocultar()
        if self.hover is not None:
            self.hover = None
            self.al_cambiar_hover()
            self.redibujar()

    def _al_presionar(self, evento) -> None:
        region = self._region_en(evento)
        self._presionada = region.clave if region else None
        self.app.tooltips.ocultar()

    def _al_soltar(self, evento) -> None:
        region = self._region_en(evento)
        presionada, self._presionada = self._presionada, None
        if region is not None and region.clave == presionada and region.al_clic:
            region.al_clic()

    def _al_doble(self, evento) -> None:
        region = self._region_en(evento)
        if region is not None and region.al_doble:
            region.al_doble()

    def _al_menu(self, evento) -> None:
        region = self._region_en(evento)
        if region is not None and region.al_menu:
            region.al_menu(evento.x_root, evento.y_root)


class BarraAuto(ttk.Scrollbar):
    """Barra de desplazamiento que solo aparece cuando hace falta."""

    def set(self, inicio, fin):
        if float(inicio) <= 0.001 and float(fin) >= 0.999:
            self.grid_remove()
        else:
            self.grid()
        super().set(inicio, fin)


class ListaVirtual(CanvasInteractivo):
    """Lista vertical que solo dibuja las filas visibles (rápida con muchos elementos)."""

    def __init__(self, padre, app, fondo, alto_fila: int, margen: int = 0):
        super().__init__(padre, app, fondo, yscrollincrement=S(20))
        self.alto_fila = alto_fila
        self.margen = margen
        self.elementos: list[dict] = []
        self._al_rueda = self.desplazar

    def conectar_barra(self, barra: ttk.Scrollbar) -> None:
        barra.configure(command=self._desde_barra)
        self.configure(yscrollcommand=barra.set)

    def _desde_barra(self, *argumentos) -> None:
        self.yview(*argumentos)
        self.redibujar()

    def desplazar(self, pasos: int) -> None:
        self.yview_scroll(pasos * 3, "units")
        self.redibujar()

    def establecer_elementos(self, elementos: list[dict]) -> None:
        self.elementos = elementos
        self.redibujar()

    def dibujar(self, ancho, alto) -> None:
        if self.app.esperando_backend:
            self.configure(scrollregion=(0, 0, ancho, alto))
            self.dibujar_esqueleto(ancho, alto)
            return
        total = self.margen + len(self.elementos) * self.alto_fila + S(8)
        region_alto = max(total, alto)
        self.configure(scrollregion=(0, 0, ancho, region_alto))
        if self.canvasy(0) > region_alto - alto:
            self.yview_moveto(max(0, region_alto - alto) / region_alto)
        if not self.elementos:
            self.dibujar_vacio(ancho, alto)
            return
        arriba = self.canvasy(0)
        primero = max(0, int((arriba - self.margen) // self.alto_fila))
        ultimo = min(len(self.elementos), int((arriba + alto - self.margen) // self.alto_fila) + 1)
        for indice in range(primero, ultimo):
            self.dibujar_fila(indice, self.elementos[indice],
                              self.margen + indice * self.alto_fila, ancho)

    def dibujar_fila(self, indice, elemento, y0, ancho) -> None:
        """Implementado por las subclases."""

    def dibujar_vacio(self, ancho, alto) -> None:
        """Implementado por las subclases."""

    def dibujar_esqueleto(self, ancho, alto) -> None:
        for i in range(6):
            y = self.margen + i * self.alto_fila + self.alto_fila / 2
            self.create_rectangle(S(12), y - S(20), S(52), y + S(20), fill=COLORES["esqueleto"],
                                  outline="", tags=("esqueleto",))
            self.create_rectangle(S(64), y - S(10), S(64) + ancho * 0.45, y - S(2),
                                  fill=COLORES["esqueleto"], outline="", tags=("esqueleto",))
            self.create_rectangle(S(64), y + S(6), S(64) + ancho * 0.28, y + S(13),
                                  fill=COLORES["esqueleto"], outline="", tags=("esqueleto",))

    def asegurar_visible(self, id_cancion) -> None:
        indice = next((i for i, e in enumerate(self.elementos) if e["id"] == id_cancion), None)
        region = str(self.cget("scrollregion")).split()
        if indice is None or len(region) != 4:
            return
        total = float(region[3])
        alto = self.winfo_height()
        y0 = self.margen + indice * self.alto_fila
        y1 = y0 + self.alto_fila
        arriba = self.canvasy(0)
        if y0 < arriba:
            self.yview_moveto(y0 / total)
        elif y1 > arriba + alto:
            self.yview_moveto((y1 - alto) / total)
        self.redibujar()


class VistaDesplazable(tk.Frame):
    """Contenedor con desplazamiento vertical para frames normales."""

    def __init__(self, padre, fondo: str, al_desplazar: Callable[[float], None] | None = None,
                 mostrar_barra: bool = True):
        super().__init__(padre, bg=fondo)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.lienzo = tk.Canvas(self, bg=fondo, highlightthickness=0, bd=0, yscrollincrement=S(20))
        self.lienzo.grid(row=0, column=0, sticky="nsew")
        self.barra = None
        if mostrar_barra:
            self.barra = BarraAuto(self, orient="vertical", command=self.lienzo.yview,
                                   style="Fina.Vertical.TScrollbar")
            self.barra.grid(row=0, column=1, sticky="ns")
        self.lienzo.configure(yscrollcommand=self._al_cambiar_vista)
        self.contenido = tk.Frame(self.lienzo, bg=fondo)
        self._ventana = self.lienzo.create_window(0, 0, window=self.contenido, anchor="nw")
        self.contenido.bind("<Configure>", self._al_cambiar_contenido)
        self.lienzo.bind("<Configure>",
                         lambda e: self.lienzo.itemconfigure(self._ventana, width=e.width))
        self._al_desplazar = al_desplazar
        self.lienzo._al_rueda = self.desplazar
        self.contenido._al_rueda = self.desplazar

    def _al_cambiar_contenido(self, evento) -> None:
        self.lienzo.configure(scrollregion=(0, 0, evento.width, evento.height))

    def _al_cambiar_vista(self, inicio, fin) -> None:
        if self.barra is not None:
            self.barra.set(inicio, fin)
        if self._al_desplazar:
            self._al_desplazar(float(inicio))

    def desplazar(self, pasos: int) -> None:
        if self.contenido.winfo_height() > self.lienzo.winfo_height():
            self.lienzo.yview_scroll(pasos * 3, "units")

    def en_la_cima(self) -> bool:
        return self.lienzo.yview()[0] <= 0.0


class PanelRedondeado(tk.Frame):
    """Frame con esquinas redondeadas y suavizadas (imágenes en las esquinas)."""

    def __init__(self, padre, color: str, fondo: str, radio: int, **opciones):
        super().__init__(padre, bg=color, **opciones)
        self._radio = radio
        self._color = color
        self._fondo = fondo
        self._colores_esquinas: dict[str, str] = {}
        self._esquinas: dict[str, tk.Label] = {}
        for orientacion in ("nw", "ne", "se", "sw"):
            self._esquinas[orientacion] = tk.Label(self, bd=0, highlightthickness=0, padx=0,
                                                   pady=0, bg=color)
        r = radio
        self._esquinas["nw"].place(x=0, y=0)
        self._esquinas["ne"].place(relx=1.0, x=-r, y=0)
        self._esquinas["se"].place(relx=1.0, rely=1.0, x=-r, y=-r)
        self._esquinas["sw"].place(x=0, rely=1.0, y=-r)
        self.configurar_color_esquinas(color)

    def configurar_color_esquinas(self, color_interior: str, orientaciones=("nw", "ne", "se", "sw")):
        for orientacion in orientaciones:
            if self._colores_esquinas.get(orientacion) == color_interior:
                continue
            self._colores_esquinas[orientacion] = color_interior
            imagen = fabrica().esquina(self._radio, color_interior, self._fondo, orientacion)
            self._esquinas[orientacion].configure(image=imagen)

    def levantar_esquinas(self) -> None:
        for etiqueta in self._esquinas.values():
            etiqueta.lift()


class Deslizador(tk.Canvas):
    """Barra deslizante fina estilo reproductor (progreso y volumen).

    Mientras se arrastra, los valores que llegan del backend se ignoran
    para que la barra no salte bajo el cursor.
    """

    def __init__(self, padre, fondo: str, al_mover=None, al_soltar=None):
        super().__init__(padre, width=S(120), height=S(16), bg=fondo, highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=0)
        self._al_mover = al_mover
        self._al_soltar = al_soltar
        self._valor = 0.0
        self._interactivo = True
        self._hover = False
        self._arrastrando = False
        self.bind("<Enter>", lambda _e: self._cambiar_hover(True))
        self.bind("<Leave>", lambda _e: self._cambiar_hover(False))
        self.bind("<ButtonPress-1>", self._al_presionar)
        self.bind("<B1-Motion>", self._al_arrastrar)
        self.bind("<ButtonRelease-1>", self._al_liberar)
        self.bind("<Configure>", lambda _e: self._dibujar())

    @property
    def arrastrando(self) -> bool:
        return self._arrastrando

    @property
    def valor(self) -> float:
        return self._valor

    def establecer_valor(self, valor: float) -> None:
        if self._arrastrando:
            return
        valor = limitar(float(valor), 0.0, 1.0)
        if abs(valor - self._valor) > 1e-4:
            self._valor = valor
            self._dibujar()

    def configurar_interactivo(self, interactivo: bool) -> None:
        interactivo = bool(interactivo)
        if interactivo != self._interactivo:
            self._interactivo = interactivo
            self._arrastrando = False
            self.configure(cursor="hand2" if interactivo else "arrow")
            self._dibujar()

    def _cambiar_hover(self, hover: bool) -> None:
        self._hover = hover
        self._dibujar()

    def _margen(self) -> int:
        return S(7)

    def _valor_desde_x(self, x: float) -> float:
        util = self.winfo_width() - 2 * self._margen()
        return limitar((x - self._margen()) / util, 0.0, 1.0) if util > 0 else 0.0

    def _al_presionar(self, evento):
        if self._interactivo:
            self._arrastrando = True
            self._actualizar(evento)

    def _al_arrastrar(self, evento):
        if self._arrastrando:
            self._actualizar(evento)

    def _al_liberar(self, _evento):
        if not self._arrastrando:
            return
        self._arrastrando = False
        self._dibujar()
        if self._al_soltar:
            self._al_soltar(self._valor)

    def _actualizar(self, evento) -> None:
        self._valor = self._valor_desde_x(evento.x)
        self._dibujar()
        if self._al_mover:
            self._al_mover(self._valor)

    def _dibujar(self) -> None:
        self.delete("all")
        ancho, alto = self.winfo_width(), self.winfo_height()
        if ancho <= 1:
            return
        y = alto / 2
        x0, x1 = self._margen(), ancho - self._margen()
        grosor = S(4)
        self.create_line(x0, y, x1, y, width=grosor, fill=COLORES["pista"], capstyle="round")
        activo = self._interactivo and (self._hover or self._arrastrando)
        x_valor = x0 + (x1 - x0) * self._valor
        if self._valor > 0:
            self.create_line(x0, y, x_valor, y, width=grosor, capstyle="round",
                             fill=COLORES["acento"] if activo else COLORES["texto"])
        if activo:
            dibujar_circulo(self, x_valor, y, S(12), "#FFFFFF", self["bg"])


class Interruptor(tk.Canvas):
    """Interruptor encendido/apagado para la vista de ajustes."""

    def __init__(self, padre, valor: bool, al_cambiar: Callable[[bool], None], fondo: str):
        super().__init__(padre, width=S(44), height=S(24), bg=fondo, highlightthickness=0, bd=0,
                         cursor="hand2")
        self._valor = valor
        self._al_cambiar = al_cambiar
        self._fondo = fondo
        self._hover = False
        self.bind("<Enter>", lambda _e: self._cambiar_hover(True))
        self.bind("<Leave>", lambda _e: self._cambiar_hover(False))
        self.bind("<ButtonRelease-1>", lambda _e: self.alternar())
        self.bind("<Configure>", lambda _e: self.dibujar())

    def establecer(self, valor: bool) -> None:
        if valor != self._valor:
            self._valor = valor
            self.dibujar()

    def alternar(self) -> None:
        self._valor = not self._valor
        self.dibujar()
        self._al_cambiar(self._valor)

    def _cambiar_hover(self, hover):
        self._hover = hover
        self.dibujar()

    def dibujar(self) -> None:
        self.delete("all")
        ancho, alto = S(44), S(24)
        if self._valor:
            pista = COLORES["acento_hover"] if self._hover else COLORES["acento"]
        else:
            pista = "#565A64" if self._hover else COLORES["pista"]
        rect_redondeado(self, 0, 0, ancho, alto, alto / 2, pista, self._fondo)
        x = ancho - S(12) if self._valor else S(12)
        dibujar_circulo(self, x, alto / 2, S(18), "#FFFFFF", pista)


# ======================================================================
# 6. CAPAS FLOTANTES: tooltips, menú contextual y notificaciones
# ======================================================================

class GestorTooltips:
    """Tooltips dibujados dentro de la ventana (sin ventanas adicionales)."""

    RETARDO_MS = 550

    def __init__(self, app: "ReproductorUI"):
        self.app = app
        self.lienzo = tk.Canvas(app, bg=COLORES["fondo"], highlightthickness=0, bd=0)
        self._id = None

    def programar(self, lienzo: tk.Canvas, region: Region) -> None:
        self.ocultar()
        desplazamiento_x, desplazamiento_y = lienzo.canvasx(0), lienzo.canvasy(0)
        cx = lienzo.winfo_rootx() + (region.x0 + region.x1) / 2 - desplazamiento_x
        y_arriba = lienzo.winfo_rooty() + region.y0 - desplazamiento_y
        y_abajo = lienzo.winfo_rooty() + region.y1 - desplazamiento_y
        texto = region.tooltip
        self._id = self.app.after(self.RETARDO_MS,
                                  lambda: self._mostrar(texto, cx, y_arriba, y_abajo))

    def _mostrar(self, texto, cx, y_arriba, y_abajo) -> None:
        self._id = None
        if callable(texto):
            texto = texto()
        fuente = self.app.fuente(9, negrita=True)
        ancho, alto = fuente.measure(texto) + S(20), S(30)
        lienzo = self.lienzo
        lienzo.configure(width=ancho, height=alto)
        lienzo.delete("all")
        rect_redondeado(lienzo, 0, 0, ancho, alto, S(5), COLORES["tooltip"], COLORES["fondo"])
        lienzo.create_text(ancho / 2, alto / 2, text=texto, fill=COLORES["texto"], font=fuente)
        raiz_x, raiz_y = self.app.winfo_rootx(), self.app.winfo_rooty()
        x = limitar(cx - raiz_x - ancho / 2, S(4), self.app.winfo_width() - ancho - S(4))
        y = y_abajo - raiz_y + S(6)
        if y + alto > self.app.winfo_height() - S(4):
            y = y_arriba - raiz_y - alto - S(6)
        lienzo.place(x=x, y=y)
        lienzo.tk.call("raise", lienzo._w)

    def ocultar(self) -> None:
        if self._id is not None:
            self.app.after_cancel(self._id)
            self._id = None
        self.lienzo.place_forget()


class MenuContextual(tk.Frame):
    """Menú contextual (clic derecho) dibujado dentro de la ventana."""

    def __init__(self, app: "ReproductorUI"):
        super().__init__(app, bg=COLORES["menu"], highlightthickness=1,
                         highlightbackground=COLORES["borde"])
        self.app = app
        self.visible = False

    def mostrar(self, opciones: list, x_root: int, y_root: int) -> None:
        """``opciones``: lista de (texto, accion, peligroso) o None (separador)."""
        for hijo in self.winfo_children():
            hijo.destroy()
        tk.Frame(self, bg=COLORES["menu"], height=S(4)).pack(fill="x")
        for opcion in opciones:
            if opcion is None:
                tk.Frame(self, bg=COLORES["borde"], height=1).pack(fill="x", padx=S(10), pady=S(4))
                continue
            texto, accion, peligroso = opcion
            etiqueta = tk.Label(self, text=texto, anchor="w", bg=COLORES["menu"],
                                fg=COLORES["error"] if peligroso else COLORES["texto"],
                                font=self.app.fuente(10), padx=S(14), pady=S(7), cursor="hand2")
            etiqueta.pack(fill="x", padx=S(4))
            etiqueta.bind("<Enter>", lambda _e, w=etiqueta: w.configure(bg=COLORES["menu_hover"]))
            etiqueta.bind("<Leave>", lambda _e, w=etiqueta: w.configure(bg=COLORES["menu"]))
            etiqueta.bind("<ButtonRelease-1>", lambda _e, a=accion: self._elegir(a))
        tk.Frame(self, bg=COLORES["menu"], height=S(4)).pack(fill="x")
        self.update_idletasks()
        ancho = max(self.winfo_reqwidth(), S(230))
        alto = self.winfo_reqheight()
        x = limitar(x_root - self.app.winfo_rootx(), S(4), self.app.winfo_width() - ancho - S(4))
        y = y_root - self.app.winfo_rooty()
        if y + alto > self.app.winfo_height() - S(4):
            y = y - alto
        self.place(x=x, y=max(S(4), y), width=ancho)
        self.lift()
        self.visible = True

    def _elegir(self, accion) -> None:
        self.ocultar()
        accion()

    def ocultar(self) -> None:
        if self.visible:
            self.place_forget()
            self.visible = False

    def contiene(self, widget) -> bool:
        while widget is not None:
            if widget is self:
                return True
            widget = getattr(widget, "master", None)
        return False


class Notificador:
    """Notificaciones discretas ("toasts") en la parte inferior del panel central."""

    DURACION_MS = 3600

    def __init__(self, app: "ReproductorUI", contenedor: tk.Widget):
        self.app = app
        self.lienzo = tk.Canvas(contenedor, bg=COLORES["panel"], highlightthickness=0, bd=0)
        self._id_ocultar = None
        self._token = 0
        self.visible = False

    def mostrar(self, texto: str, tipo: str = "info") -> None:
        fuente = self.app.fuente(10, negrita=True)
        texto = truncar_texto(texto, fuente, S(520))
        ancho = fuente.measure(texto) + S(58)
        alto = S(42)
        lienzo = self.lienzo
        lienzo.configure(width=ancho, height=alto)
        lienzo.delete("all")
        rect_redondeado(lienzo, 0, 0, ancho, alto, S(8), COLORES["toast"], COLORES["panel"])
        colores = {"info": COLORES["acento"], "exito": COLORES["exito"],
                   "advertencia": COLORES["advertencia"], "error": COLORES["error"]}
        dibujar_circulo(lienzo, S(22), alto / 2, S(10), colores.get(tipo, COLORES["acento"]),
                        COLORES["toast"])
        lienzo.create_text(S(38), alto / 2, text=texto, anchor="w", font=fuente,
                           fill=COLORES["toast_texto"])
        self._token += 1
        token = self._token
        self.visible = True

        def paso(progreso):
            if token == self._token:
                self._colocar(S(16) * (1 - progreso))

        self.app.animar(220, paso)
        if self._id_ocultar is not None:
            self.app.after_cancel(self._id_ocultar)
        self._id_ocultar = self.app.after(self.DURACION_MS, self.ocultar)

    def _colocar(self, desplazamiento: float) -> None:
        self.lienzo.place(relx=0.5, rely=1.0, y=-S(20) + desplazamiento, anchor="s")
        self.lienzo.tk.call("raise", self.lienzo._w)

    def ocultar(self) -> None:
        self._id_ocultar = None
        self._token += 1
        self.visible = False
        self.lienzo.place_forget()

    def levantar(self) -> None:
        if self.visible:
            self.lienzo.tk.call("raise", self.lienzo._w)


# ======================================================================
# 7. COMPONENTES DE LA VENTANA
# ======================================================================

# ----------------------------------------------------------------------
# 7.1 Barra superior: navegación, búsqueda y ajustes
# ----------------------------------------------------------------------

class BarraSuperior(CanvasInteractivo):
    MARCADOR = "Buscar canciones o artistas"

    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["fondo"], height=S(64))
        self.texto = tk.StringVar()
        self.entrada = tk.Entry(self, textvariable=self.texto, bd=0, relief="flat",
                                highlightthickness=0, bg=COLORES["elevado"], fg=COLORES["texto"],
                                insertbackground=COLORES["texto"], font=app.fuente(11),
                                selectbackground=COLORES["acento"],
                                selectforeground=COLORES["icono_oscuro"])
        self._item_entrada = None
        self._marcador_activo = False
        self._enfocada = False
        self.entrada.bind("<FocusIn>", self._al_enfocar)
        self.entrada.bind("<FocusOut>", self._al_desenfocar)
        self.texto.trace_add("write", self._al_escribir)
        self._poner_marcador()

    # ---------------- Búsqueda ----------------

    def consulta(self) -> str:
        return "" if self._marcador_activo else self.texto.get()

    def enfocar(self) -> None:
        self.entrada.focus_set()
        self.entrada.icursor("end")

    def limpiar(self) -> None:
        self._quitar_marcador()
        self.texto.set("")
        if not self._enfocada:
            self._poner_marcador()
        self.redibujar()

    def _poner_marcador(self) -> None:
        if not self.texto.get():
            self._marcador_activo = True
            self.entrada.insert(0, self.MARCADOR)
            self.entrada.configure(fg=COLORES["texto_tenue"])

    def _quitar_marcador(self) -> None:
        if self._marcador_activo:
            self._marcador_activo = False
            self.entrada.delete(0, "end")
            self.entrada.configure(fg=COLORES["texto"])

    def _al_enfocar(self, _evento) -> None:
        self._quitar_marcador()
        self._enfocada = True
        self.redibujar()

    def _al_desenfocar(self, _evento) -> None:
        self._enfocada = False
        self._poner_marcador()
        self.redibujar()

    def _al_escribir(self, *_argumentos) -> None:
        if not self._marcador_activo:
            self.app.establecer_busqueda(self.texto.get())
            self.redibujar()

    # ---------------- Dibujo ----------------

    def dibujar(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        cy = alto // 2
        for i, (clave, icono, habilitado, accion, ayuda) in enumerate((
                ("atras", icono_chevron_izq, app.puede_retroceder(), app.retroceder, "Atrás (Alt+←)"),
                ("adelante", icono_chevron_der, app.puede_avanzar(), app.avanzar,
                 "Adelante (Alt+→)"))):
            cx = S(36) + i * S(42)
            hover = self.hover == clave and habilitado
            dibujar_circulo(self, cx, cy, S(32), C["hover"] if hover else C["elevado"], self.fondo)
            icono(self, cx, cy, S(12), C["texto"] if habilitado else C["texto_tenue"])
            self.region(cx - S(16), cy - S(16), cx + S(16), cy + S(16), clave,
                        accion if habilitado else None, tooltip=ayuda)

        ancho_busqueda = int(limitar(ancho * 0.34, S(260), S(480)))
        inicio_x = ancho / 2 - (S(56) + ancho_busqueda) / 2
        self._dibujar_boton_inicio(inicio_x + S(24), cy)
        self._dibujar_buscador(inicio_x + S(56), cy, ancho_busqueda)

        en_ajustes = app.vista_actual == "ajustes"
        cx = ancho - S(36)
        hover = self.hover == "ajustes"
        dibujar_circulo(self, cx, cy, S(36), C["hover"] if hover or en_ajustes else C["elevado"],
                        self.fondo)
        icono_ajustes(self, cx, cy, S(16), C["texto"] if hover or en_ajustes else C["texto_sec"])
        self.region(cx - S(18), cy - S(18), cx + S(18), cy + S(18), "ajustes",
                    lambda: app.navegar("ajustes"), tooltip="Ajustes (Ctrl+,)")

    def _dibujar_boton_inicio(self, cx, cy) -> None:
        C = COLORES
        en_inicio = self.app.vista_actual == "inicio"
        hover = self.hover == "inicio"
        dibujar_circulo(self, cx, cy, S(48), C["hover"] if hover else C["elevado"], self.fondo)
        color = C["texto"] if en_inicio or hover else C["texto_sec"]
        icono_inicio(self, cx, cy + S(1), S(20), color, relleno=en_inicio)
        self.region(cx - S(24), cy - S(24), cx + S(24), cy + S(24), "inicio",
                    lambda: self.app.navegar("inicio"), tooltip="Inicio (Ctrl+1)")

    def _dibujar_buscador(self, x0, cy, ancho) -> None:
        C = COLORES
        x1, y0, y1 = x0 + ancho, cy - S(24), cy + S(24)
        resaltado = self.hover in ("busqueda", "limpiar") or self._enfocada
        color = C["hover"] if resaltado else C["elevado"]
        if self._enfocada:
            rect_redondeado_borde(self, x0, y0, x1, y1, S(24), color, C["texto"], S(2), self.fondo)
        else:
            rect_redondeado(self, x0, y0, x1, y1, S(24), color, self.fondo)
        icono_buscar(self, x0 + S(26), cy, S(18), C["texto"] if resaltado else C["texto_sec"])
        self.region(x0, y0, x1, y1, "busqueda", self.enfocar)
        tiene_texto = bool(self.consulta())
        ancho_entrada = max(S(20), x1 - x0 - S(50) - (S(46) if tiene_texto else S(22)))
        self.entrada.configure(bg=color)
        if self._item_entrada is None:
            self._item_entrada = self.create_window(x0 + S(50), cy, window=self.entrada, anchor="w",
                                                    width=ancho_entrada, height=S(26), tags=("fijo",))
        else:
            self.coords(self._item_entrada, x0 + S(50), cy)
            self.itemconfigure(self._item_entrada, width=ancho_entrada)
        if tiene_texto:
            self.boton_icono("limpiar", x1 - S(26), cy, icono_cerrar, S(14), self.app.limpiar_busqueda,
                             tooltip="Borrar búsqueda (Esc)", diametro=S(30), fondo=color)


# ----------------------------------------------------------------------
# 7.2 Barra lateral: marca, navegación y "Tu biblioteca"
# ----------------------------------------------------------------------

class CabeceraLateral(CanvasInteractivo):
    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], height=S(312))
        self.contraida = False

    def establecer_contraida(self, contraida: bool) -> None:
        self.contraida = contraida
        self.configure(height=S(268) if contraida else S(312))
        self.redibujar()

    def dibujar(self, ancho, alto) -> None:
        if self.contraida:
            self._dibujar_contraida(ancho)
        else:
            self._dibujar_expandida(ancho)

    def _dibujar_contraida(self, ancho) -> None:
        app, C = self.app, COLORES
        cx = ancho / 2
        self.boton_icono("expandir", cx, S(30), icono_panel_lateral, S(18),
                         app.alternar_barra_lateral, tooltip="Expandir barra lateral (Ctrl+B)",
                         diametro=S(40))
        y = S(84)
        for clave, nombre, icono in VISTAS_NAVEGACION:
            activa = app.vista_actual == clave
            hover = self.hover == ("nav", clave)
            if activa or hover:
                rect_redondeado(self, cx - S(22), y - S(21), cx + S(22), y + S(21), S(8),
                                C["elevado"] if activa else C["hover"], self.fondo)
            icono(self, cx, y, S(20), C["texto"] if activa or hover else C["texto_sec"], activa)
            self.region(cx - S(24), y - S(23), cx + S(24), y + S(23), ("nav", clave),
                        lambda c=clave: app.navegar(c), tooltip=nombre)
            y += S(48)
        self.create_line(S(14), y - S(8), ancho - S(14), y - S(8), fill=C["borde_suave"])
        self.boton_icono("agregar", cx, y + S(22), icono_mas, S(16), app.accion_agregar,
                         tooltip="Agregar canciones (Ctrl+O)", diametro=S(40))

    def _dibujar_expandida(self, ancho) -> None:
        app, C = self.app, COLORES
        y = S(32)
        dibujar_logo(self, S(30), y, S(36), self.fondo)
        self.create_text(S(58), y - S(8), text="CIRCULAR MUSIC", anchor="w",
                         font=app.fuente(12, True, display=True), fill=C["texto"])
        self.create_text(S(58), y + S(10), text="Powered by Linked Structures", anchor="w",
                         font=app.fuente(8), fill=C["texto_sec"])
        self.boton_icono("contraer", ancho - S(24), y, icono_panel_lateral, S(18),
                         app.alternar_barra_lateral, tooltip="Contraer barra lateral (Ctrl+B)")

        y = S(86)
        for clave, nombre, icono in VISTAS_NAVEGACION:
            activa = app.vista_actual == clave
            hover = self.hover == ("nav", clave)
            if activa or hover:
                rect_redondeado(self, S(4), y - S(20), ancho - S(4), y + S(20), S(8),
                                C["elevado"] if activa else C["hover"], self.fondo)
            color = C["texto"] if activa or hover else C["texto_sec"]
            icono(self, S(28), y, S(19), color, activa)
            self.create_text(S(52), y, text=nombre, anchor="w", fill=color,
                             font=app.fuente(11, negrita=True))
            self.region(S(4), y - S(21), ancho - S(4), y + S(21), ("nav", clave),
                        lambda c=clave: app.navegar(c))
            y += S(44)

        self.create_line(S(14), y - S(4), ancho - S(14), y - S(4), fill=C["borde_suave"])
        y += S(28)
        hover = self.hover == "titulo_biblioteca"
        color = C["texto"] if hover else C["texto_sec"]
        icono_biblioteca(self, S(28), y, S(18), color)
        self.create_text(S(52), y, text="Tu biblioteca", anchor="w", fill=color,
                         font=app.fuente(11, negrita=True))
        self.region(S(4), y - S(18), ancho - S(52), y + S(18), "titulo_biblioteca",
                    lambda: app.navegar("biblioteca"), tooltip="Abrir la biblioteca")
        self.boton_icono("agregar", ancho - S(28), y, icono_mas, S(16), app.accion_agregar,
                         tooltip="Agregar canciones (Ctrl+O)")

        y += S(42)
        x = S(10)
        for clave, texto in (("todas", "Todas"), ("favoritas", "Favoritas")):
            activa = (clave == "favoritas") == app.filtro_favoritas
            caja = dibujar_pastilla(self, x, y, texto, app.fuente(9, negrita=True),
                                    "chip_activo" if activa else "chip",
                                    self.hover == ("chip", clave), self.fondo, alto=S(30))
            self.region(*caja, ("chip", clave),
                        lambda c=clave: app.establecer_filtro_favoritas(c == "favoritas"))
            x = caja[2] + S(8)


class ListaLateral(ListaVirtual):
    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], alto_fila=S(60), margen=S(2))
        self.contraida = False

    def dibujar_fila(self, indice, cancion, y0, ancho) -> None:
        app, C = self.app, COLORES
        id_cancion = cancion["id"]
        y1 = y0 + self.alto_fila
        cy = (y0 + y1) / 2
        es_actual = id_cancion == app.estado["actual_id"]
        es_seleccion = id_cancion == app.seleccion_id
        hover = self.hover == ("fila", id_cancion)
        color_fila = C["activo"] if es_seleccion else C["hover"] if hover else None
        fondo_fila = color_fila or self.fondo
        acciones = {"al_clic": lambda: app.seleccionar(id_cancion),
                    "al_doble": lambda: app.activar_cancion(id_cancion),
                    "al_menu": lambda x, y: app.mostrar_menu_cancion(id_cancion, x, y)}

        if self.contraida:
            tam = S(46)
            x = (ancho - tam) / 2
            if color_fila:
                rect_redondeado(self, x - S(5), cy - tam / 2 - S(5), x + tam + S(5),
                                cy + tam / 2 + S(5), S(8), color_fila, self.fondo)
            if es_actual:
                rect_redondeado(self, x - S(3), cy - tam / 2 - S(3), x + tam + S(3),
                                cy + tam / 2 + S(3), S(7), C["acento"], fondo_fila)
                fondo_fila = C["acento"]
            self.portada(id_cancion, x, cy - tam / 2, tam, fondo_fila)
            self.region(0, y0, ancho, y1, ("fila", id_cancion), tooltip=cancion["titulo"],
                        **acciones)
            return

        if color_fila:
            rect_redondeado(self, S(4), y0 + S(2), ancho - S(6), y1 - S(2), S(6), color_fila,
                            self.fondo)
        tam = S(44)
        self.portada(id_cancion, S(12), cy - tam / 2, tam, fondo_fila)
        derecha = S(30) if (es_actual and app.estado["reproduciendo"]) or app.es_favorita(id_cancion) else 0
        ancho_texto = ancho - S(68) - S(14) - derecha
        fuente_titulo = app.fuente(10, negrita=True)
        self.create_text(S(68), cy - S(9), anchor="w", font=fuente_titulo,
                         fill=C["acento_texto"] if es_actual else C["texto"],
                         text=truncar_texto(cancion["titulo"], fuente_titulo, ancho_texto))
        fuente_sub = app.fuente(9)
        posicion = app.indices.get(id_cancion, 0) + 1
        self.create_text(S(68), cy + S(10), anchor="w", font=fuente_sub, fill=C["texto_sec"],
                         text=truncar_texto(f"Nodo {posicion} · {cancion['artista']}", fuente_sub,
                                            ancho_texto))
        if es_actual and app.estado["reproduciendo"]:
            self.ecualizador(ancho - S(30), cy + S(6), C["acento"])
        elif app.es_favorita(id_cancion):
            icono_corazon(self, ancho - S(22), cy, S(13), C["acento"], relleno=True)
        self.region(S(4), y0, ancho - S(6), y1, ("fila", id_cancion), **acciones)

    def dibujar_vacio(self, ancho, alto) -> None:
        if self.contraida:
            return
        app, C = self.app, COLORES
        x0, y0, x1 = S(4), S(8), ancho - S(10)
        y1 = y0 + S(156)
        rect_redondeado(self, x0, y0, x1, y1, S(10), C["elevado"], self.fondo)
        if app.estado["canciones"]:
            titulo = "Aún no tienes favoritas"
            texto = "Toca el corazón de una canción para guardarla aquí."
            boton, accion = "Ver todas", lambda: app.establecer_filtro_favoritas(False)
        else:
            titulo = "Crea tu lista circular"
            texto = "Agrega archivos de audio para formar los primeros nodos."
            boton, accion = "Agregar canciones", app.accion_agregar
        self.create_text(x0 + S(18), y0 + S(30), text=titulo, anchor="w", fill=C["texto"],
                         font=app.fuente(11, negrita=True))
        self.create_text(x0 + S(18), y0 + S(48), text=texto, anchor="nw", fill=C["texto_sec"],
                         font=app.fuente(9), width=x1 - x0 - S(36))
        caja = dibujar_pastilla(self, x0 + S(18), y1 - S(32), boton, app.fuente(9, negrita=True),
                                "claro", self.hover == "vacio", C["elevado"], alto=S(32))
        self.region(*caja, "vacio", accion)


class BarraLateral(PanelRedondeado):
    ANCHO_EXPANDIDA = 300
    ANCHO_CONTRAIDA = 76

    def __init__(self, padre, app):
        super().__init__(padre, COLORES["panel"], COLORES["fondo"], S(10),
                         width=S(self.ANCHO_EXPANDIDA))
        self.app = app
        self.contraida = False
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.cabecera = CabeceraLateral(self, app)
        self.cabecera.grid(row=0, column=0, columnspan=2, sticky="ew", padx=S(6), pady=(S(8), 0))
        self.lista = ListaLateral(self, app)
        self.lista.grid(row=1, column=0, sticky="nsew", padx=(S(6), 0))
        barra = BarraAuto(self, orient="vertical", style="Fina.Vertical.TScrollbar")
        barra.grid(row=1, column=1, sticky="ns", padx=(0, S(2)))
        self.lista.conectar_barra(barra)
        self.pie = tk.Label(self, bg=COLORES["panel"], fg=COLORES["texto_tenue"],
                            font=app.fuente(9), anchor="w")
        self.pie.grid(row=2, column=0, columnspan=2, sticky="ew", padx=S(18), pady=(S(6), S(14)))
        self.after_idle(self.levantar_esquinas)

    def establecer_contraida(self, contraida: bool) -> None:
        if contraida == self.contraida:
            return
        self.contraida = contraida
        inicio = self.winfo_width() if self.winfo_width() > 1 else S(self.ANCHO_EXPANDIDA)
        destino = S(self.ANCHO_CONTRAIDA if contraida else self.ANCHO_EXPANDIDA)
        if contraida:
            self._aplicar_modo(True)

        def paso(progreso):
            self.configure(width=int(inicio + (destino - inicio) * progreso))

        def terminar():
            if not contraida:
                self._aplicar_modo(False)
            self.levantar_esquinas()

        self.app.animar(200, paso, terminar)

    def _aplicar_modo(self, contraida: bool) -> None:
        self.cabecera.establecer_contraida(contraida)
        self.lista.contraida = contraida
        self.lista.redibujar()
        if contraida:
            self.pie.grid_remove()
        else:
            self.pie.grid()

    def refrescar(self, cambios: set) -> None:
        if cambios & {"vista", "filtro", "favoritos", "lista"}:
            self.cabecera.redibujar()
        if cambios & {"lista", "actual", "reproduccion", "seleccion", "favoritos", "filtro",
                      "esperando", "prefs"}:
            self.lista.establecer_elementos(self.app.canciones_lateral())
        if cambios & {"lista", "esperando"}:
            canciones = self.app.estado["canciones"]
            if self.app.esperando_backend:
                self.pie.configure(text="Conectando con el reproductor…")
            elif not canciones:
                self.pie.configure(text="Sin canciones")
            else:
                n = len(canciones)
                self.pie.configure(text=f"{n} canción{'es' if n != 1 else ''} · "
                                        f"{self.app.texto_duracion_total()}")
        if "actual" in cambios and self.app.estado["actual_id"] is not None:
            self.lista.asegurar_visible(self.app.estado["actual_id"])


# ----------------------------------------------------------------------
# 7.3 Visualizador de la lista doblemente enlazada circular
# ----------------------------------------------------------------------

class VisualizadorLista(CanvasInteractivo):
    """Dibuja los nodos y sus referencias siguiente/anterior.

    Representa EXCLUSIVAMENTE el estado recibido del backend. Las
    referencias de cada nodo se leen del recorrido recibido:
        siguiente(i) = recorrido[(i + 1) % n]
        anterior(i)  = recorrido[(i - 1) % n]
    No se crea ninguna estructura de datos propia.
    """

    def __init__(self, padre, app, compacto: bool = False):
        super().__init__(padre, app, COLORES["panel"], height=S(236 if compacto else 300),
                         xscrollincrement=S(40))
        self.compacto = compacto
        self.ancho_nodo = S(168 if compacto else 196)
        self.alto_nodo = S(100 if compacto else 116)
        self.separacion = S(88 if compacto else 104)
        self.margen = S(36)
        self.retiro = S(28)
        self.altura_arco = S(34 if compacto else 40)
        self._ancho_total = 1
        self._ancho_actual, self._sep_actual = self.ancho_nodo, self.separacion
        self._posiciones: dict[int, float] = {}
        self._centrar_pendiente = None
        self._al_rueda_h = self._desplazar
        if not compacto:
            self._al_rueda = self._desplazar

    def _desplazar(self, pasos: int) -> None:
        self.xview_scroll(pasos, "units")

    def centrar_en(self, id_cancion) -> None:
        self._centrar_pendiente = id_cancion
        self.after_idle(self._aplicar_centrado)

    def _aplicar_centrado(self) -> None:
        id_cancion, self._centrar_pendiente = self._centrar_pendiente, None
        x = self._posiciones.get(id_cancion)
        visible = self.winfo_width()
        if x is None or self._ancho_total <= visible:
            return
        centro = x + self._ancho_actual / 2
        self.xview_moveto(max(0.0, (centro - visible / 2) / self._ancho_total))

    # ---------------- Dibujo ----------------

    def dibujar(self, ancho, alto) -> None:
        canciones = self.app.estado["canciones"]
        if self.app.esperando_backend:
            self.configure(scrollregion=(0, 0, ancho, alto))
            self._dibujar_esqueleto(ancho, alto)
            return
        if not canciones:
            self._posiciones = {}
            self.configure(scrollregion=(0, 0, ancho, alto))
            self._dibujar_vacia(ancho, alto)
            return
        n = len(canciones)
        W, H, sep = self.ancho_nodo, self.alto_nodo, self.separacion
        contenido = n * W + (n - 1) * sep
        disponible = ancho - 2 * self.margen
        if contenido > disponible:   # se encogen un poco antes de recurrir al scroll
            factor = max(0.8, disponible / contenido)
            W, sep = int(W * factor), int(sep * factor)
            contenido = n * W + (n - 1) * sep
        self._ancho_actual, self._sep_actual = W, sep
        x_inicio = max(self.margen, (ancho - contenido) / 2)
        self._ancho_total = max(ancho, x_inicio + contenido + self.margen)
        y0 = int((alto - H) / 2)
        y1 = y0 + H
        posiciones = [x_inicio + i * (W + sep) for i in range(n)]
        self._posiciones = {c["id"]: x for c, x in zip(canciones, posiciones)}

        self._dibujar_enlaces_circulares(posiciones[0], posiciones[-1], y0, y1, n == 1)
        for i in range(n - 1):
            self._dibujar_enlaces_consecutivos(posiciones[i] + W, posiciones[i + 1], y0)
        for i, (cancion, x) in enumerate(zip(canciones, posiciones)):
            self._dibujar_nodo(x, y0, i, n, cancion, canciones[i - 1]["id"],
                               canciones[(i + 1) % n]["id"])
        self.configure(scrollregion=(0, 0, self._ancho_total, alto))

    def _dibujar_enlaces_circulares(self, x_cabeza_nodo, x_cola_nodo, y0, y1, un_nodo) -> None:
        """cola.siguiente -> cabeza (arco superior) y cabeza.anterior -> cola (arco inferior).

        Con un solo nodo, cabeza y cola son el mismo nodo: ambos arcos
        salen y entran en él mismo (autorreferencia).
        """
        C, r = COLORES, S(14)
        x_cabeza = x_cabeza_nodo + self.retiro
        x_cola = x_cola_nodo + self._ancho_actual - self.retiro
        y_sup, y_inf = y0 - self.altura_arco, y1 + self.altura_arco
        flecha = {"width": S(2), "dash": (6, 4), "smooth": True, "arrow": tk.LAST,
                  "arrowshape": (S(10), S(12), S(4))}
        self.create_line(x_cola, y0 - 2, x_cola, y_sup + r, x_cola, y_sup, x_cola - r, y_sup,
                         x_cabeza + r, y_sup, x_cabeza, y_sup, x_cabeza, y_sup + r, x_cabeza, y0 - 2,
                         fill=C["siguiente"], **flecha)
        self.create_line(x_cabeza, y1 + 2, x_cabeza, y_inf - r, x_cabeza, y_inf, x_cabeza + r, y_inf,
                         x_cola - r, y_inf, x_cola, y_inf, x_cola, y_inf - r, x_cola, y1 + 2,
                         fill=C["anterior"], **flecha)
        centro = (x_cabeza + x_cola) / 2
        fuente = self.app.fuente(8, negrita=True)
        self.create_text(centro, y_sup - S(11), font=fuente, fill=C["siguiente"],
                         text="siguiente → sí mismo" if un_nodo else "cola.siguiente → cabeza")
        self.create_text(centro, y_inf + S(12), font=fuente, fill=C["anterior"],
                         text="anterior → sí mismo" if un_nodo else "cabeza.anterior → cola")

    def _dibujar_enlaces_consecutivos(self, x_derecha, x_izquierda_siguiente, y0) -> None:
        """nodo[i].siguiente -> nodo[i+1]  y  nodo[i+1].anterior -> nodo[i]."""
        C = COLORES
        y_sig = y0 + self.alto_nodo * 0.38
        y_ant = y0 + self.alto_nodo * 0.62
        centro = (x_derecha + x_izquierda_siguiente) / 2
        fuente = self.app.fuente(8, negrita=True)
        flecha = {"width": S(2), "arrow": tk.LAST, "arrowshape": (S(10), S(12), S(4))}
        self.create_line(x_derecha + 3, y_sig, x_izquierda_siguiente - 3, y_sig,
                         fill=C["siguiente"], **flecha)
        self.create_text(centro, y_sig - S(11), text="siguiente", font=fuente, fill=C["siguiente"])
        self.create_line(x_izquierda_siguiente - 3, y_ant, x_derecha + 3, y_ant,
                         fill=C["anterior"], **flecha)
        self.create_text(centro, y_ant + S(12), text="anterior", font=fuente, fill=C["anterior"])

    def _dibujar_nodo(self, x, y0, indice, total, cancion, anterior_id, siguiente_id) -> None:
        app, C = self.app, COLORES
        W, H = self._ancho_actual, self.alto_nodo
        x, y0 = int(x), int(y0)
        x1, y1 = x + W, y0 + H
        id_cancion = cancion["id"]
        es_actual = id_cancion == app.estado["actual_id"]
        es_seleccion = id_cancion == app.seleccion_id
        hover = self.hover == ("nodo", id_cancion)

        relleno = C["acento_suave"] if es_actual else C["hover"] if hover else C["elevado"]
        if es_actual:
            borde, grosor = C["acento"], S(2)
        elif es_seleccion:
            borde, grosor = C["siguiente"], S(2)
        else:
            borde, grosor = (C["activo"] if hover else C["borde"]), max(1, S(1))
        rect_redondeado_borde(self, x, y0, x1, y1, S(12), relleno, borde, grosor, self.fondo)

        franja = C["acento"] if es_actual else C["activo"]
        alto_franja = S(28)
        r = S(12)
        self.create_rectangle(x + r, y0 + grosor, x1 - r, y0 + alto_franja, fill=franja, outline="")
        self.create_rectangle(x + grosor, y0 + r, x1 - grosor, y0 + alto_franja, fill=franja,
                              outline="")
        for orientacion, xe in (("nw", x), ("ne", x1 - r)):
            self.create_image(xe, y0, anchor="nw", image=fabrica().esquina_borde(
                r, franja, borde, grosor, self.fondo, orientacion))
        color_franja = C["icono_oscuro"] if es_actual else C["texto"]
        f_franja = app.fuente(8, negrita=True)
        texto_franja = f"NODO {indice + 1}"
        if es_actual and (f_franja.measure(texto_franja + "  ·  ACTUAL")
                          + app.fuente(8, mono=True).measure(f"ID {id_cancion}") + S(34)) <= W:
            texto_franja += "  ·  ACTUAL"
        self.create_text(x + S(12), y0 + S(15), anchor="w", font=f_franja, fill=color_franja,
                         text=texto_franja)
        self.create_text(x1 - S(12), y0 + S(15), anchor="e", font=app.fuente(8, mono=True),
                         fill=color_franja if es_actual else C["texto_sec"], text=f"ID {id_cancion}")

        ancho_texto = W - S(24)
        f_titulo, f_artista = app.fuente(10, negrita=True), app.fuente(9)
        y_titulo = y0 + alto_franja + (H - alto_franja) * 0.24
        self.create_text(x + S(12), y_titulo, anchor="w", font=f_titulo, fill=C["texto"],
                         text=truncar_texto(cancion["titulo"], f_titulo, ancho_texto))
        self.create_text(x + S(12), y_titulo + S(18), anchor="w", font=f_artista,
                         fill=C["texto_sec"],
                         text=truncar_texto(cancion["artista"], f_artista, ancho_texto))
        y_pie = y1 - S(15)
        self.create_line(x + S(10), y_pie - S(13), x1 - S(10), y_pie - S(13), fill=C["borde"])
        f_mono = app.fuente(8, mono=True)
        self.create_text(x + S(12), y_pie, anchor="w", font=f_mono, fill=C["anterior"],
                         text=f"← ant: {anterior_id}")
        self.create_text(x1 - S(12), y_pie, anchor="e", font=f_mono, fill=C["siguiente"],
                         text=f"sig: {siguiente_id} →")

        if total == 1:
            self._etiqueta_superior(x + W / 2, y0, "CABEZA · COLA")
        elif indice == 0:
            self._etiqueta_superior(x + W / 2, y0, "CABEZA")
        elif indice == total - 1:
            self._etiqueta_superior(x + W / 2, y0, "COLA")

        self.region(x, y0, x1, y1, ("nodo", id_cancion),
                    al_clic=lambda: app.seleccionar(id_cancion),
                    al_doble=lambda: app.activar_cancion(id_cancion),
                    al_menu=lambda xr, yr: app.mostrar_menu_cancion(id_cancion, xr, yr),
                    tooltip="Doble clic para reproducir")

    def _etiqueta_superior(self, x_centro, y0, texto) -> None:
        fuente = self.app.fuente(8, negrita=True)
        mitad = (fuente.measure(texto) + S(16)) / 2
        rect_redondeado(self, x_centro - mitad, y0 - S(22), x_centro + mitad, y0 - S(5), S(8),
                        COLORES["elevado"], self.fondo)
        self.create_text(x_centro, y0 - S(13.5), text=texto, font=fuente, fill=COLORES["texto_sec"])

    def _dibujar_vacia(self, ancho, alto) -> None:
        C, app = COLORES, self.app
        cx, cy = ancho / 2, alto / 2 - S(12)
        rect_redondeado(self, cx - S(170), cy - S(19), cx - S(70), cy + S(19), S(10), C["elevado"],
                        self.fondo)
        self.create_text(cx - S(120), cy, text="cabeza", font=app.fuente(9, mono=True),
                         fill=C["texto"])
        self.create_line(cx - S(64), cy, cx + S(64), cy, fill=C["texto_tenue"], width=S(2),
                         arrow=tk.LAST, arrowshape=(S(10), S(12), S(4)))
        rect_redondeado_borde(self, cx + S(70), cy - S(19), cx + S(170), cy + S(19), S(10),
                              self.fondo, C["texto_tenue"], max(1, S(1)), self.fondo)
        self.create_text(cx + S(120), cy, text="None", font=app.fuente(9, mono=True),
                         fill=C["texto_sec"])
        self.create_text(cx, cy + S(48), font=app.fuente(9), fill=C["texto_sec"],
                         text="Lista vacía  ·  tamaño = 0  ·  no existen nodos ni enlaces")

    def _dibujar_esqueleto(self, ancho, alto) -> None:
        W, H = self.ancho_nodo, self.alto_nodo
        total = 3 * W + 2 * self.separacion
        x = max(self.margen, (ancho - total) / 2)
        y0 = (alto - H) / 2
        for i in range(3):
            xi = x + i * (W + self.separacion)
            self.create_rectangle(xi, y0, xi + W, y0 + H, fill=COLORES["esqueleto"], outline="",
                                  tags=("esqueleto",))


# ----------------------------------------------------------------------
# 7.4 Vista Inicio
# ----------------------------------------------------------------------

class HeroInicio(CanvasInteractivo):
    """Encabezado con degradado, portada grande, título y acciones principales."""

    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], height=S(392))

    def _color_en(self, y: float, alto: int) -> str:
        return mezclar_color(self.app.color_ambiente(), COLORES["panel"], limitar(y / alto, 0, 1))

    def color_fondo_en(self, y: float) -> str:
        return self._color_en(y, max(1, self.winfo_height()))

    def dibujar(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        superior = app.color_ambiente()
        for y in range(0, alto, 2):
            self.create_line(0, y, ancho, y, width=2, fill=mezclar_color(superior, C["panel"], y / alto))

        pad, tam = S(28), S(200)
        x_portada, y_portada = pad, S(72)
        x_texto = x_portada + tam + S(28)
        ancho_texto = ancho - x_texto - pad
        actual = app.cancion_actual()

        if app.esperando_backend:
            self._dibujar_esqueleto(x_portada, y_portada, tam, x_texto, ancho_texto)
            return

        if actual is None:
            rect_redondeado(self, x_portada, y_portada, x_portada + tam, y_portada + tam, S(8),
                            C["elevado"], self._color_en(y_portada, alto),
                            self._color_en(y_portada + tam, alto))
            icono_nota(self, x_portada + tam / 2, y_portada + tam / 2, S(64), C["texto_tenue"])
            if app.estado["canciones"]:
                antetitulo, titulo = "CIRCULAR MUSIC", "Nada sonando"
                detalle = "Elige una canción de tu lista circular para comenzar."
            else:
                antetitulo, titulo = "CIRCULAR MUSIC", "Tu lista circular está vacía"
                detalle = "Agrega canciones para crear los primeros nodos."
            self._dibujar_textos(x_texto, ancho_texto, antetitulo, titulo, None, detalle)
        else:
            sombra = S(26)
            self.portada(actual["id"], x_portada, y_portada, tam,
                         self._color_en(y_portada - sombra, alto), radio=S(8), prioridad=True,
                         sombra=sombra, fondo_inf=self._color_en(y_portada + tam + sombra, alto))
            posicion = app.indices[actual["id"]] + 1
            n = len(app.estado["canciones"])
            detalle = (f"  •  Nodo {posicion} de {n}  •  ID {actual['id']}  •  "
                       f"{formatear_tiempo(actual['duracion'])}")
            antetitulo = "SONANDO AHORA" if app.estado["reproduciendo"] else "CANCIÓN ACTUAL"
            self._dibujar_textos(x_texto, ancho_texto, antetitulo, actual["titulo"],
                                 actual["artista"], detalle)
        self._dibujar_acciones(pad, S(340), actual)

    def _dibujar_textos(self, x, ancho, antetitulo, titulo, artista, detalle) -> None:
        app, C = self.app, COLORES
        fuente = app.fuente(26, negrita=True, display=True)
        for tamano in (46, 40, 34, 30, 26, 22):
            candidata = app.fuente(tamano, negrita=True, display=True)
            if candidata.measure(titulo) <= ancho:
                fuente = candidata
                break
        y_base = S(272)
        y_titulo = y_base - S(30)
        self.create_text(x, y_titulo, anchor="sw", font=fuente, fill=C["texto"],
                         text=truncar_texto(titulo, fuente, ancho))
        alto_titulo = fuente.metrics("linespace")
        self.create_text(x, y_titulo - alto_titulo + S(2), anchor="sw", text=antetitulo,
                         font=app.fuente(9, negrita=True), fill=C["texto"])
        x_detalle = x
        if artista:
            f_artista = app.fuente(10, negrita=True)
            artista = truncar_texto(artista, f_artista, ancho * 0.5)
            self.create_text(x, y_base, anchor="sw", text=artista, font=f_artista, fill=C["texto"])
            x_detalle += f_artista.measure(artista)
        f_detalle = app.fuente(10)
        self.create_text(x_detalle, y_base, anchor="sw", font=f_detalle, fill=C["texto_sec"],
                         text=truncar_texto(detalle, f_detalle, ancho - (x_detalle - x)))

    def _dibujar_acciones(self, x, cy, actual) -> None:
        app, C = self.app, COLORES
        hay_canciones = bool(app.estado["canciones"])
        reproduciendo = app.estado["reproduciendo"]
        self.boton_reproducir("reproducir", x + S(28), cy, S(56), reproduciendo,
                              app.accion_reproducir_principal, C["acento"], C["acento_hover"],
                              habilitado=hay_canciones,
                              tooltip="Pausar (Espacio)" if reproduciendo else "Reproducir (Espacio)")
        x_siguiente = x + S(84)
        if actual is not None:
            favorita = app.es_favorita(actual["id"])
            self.boton_icono("favorita", x_siguiente + S(16), cy, icono_corazon, S(26),
                             lambda: app.alternar_favorito(actual["id"]),
                             tooltip="Quitar de favoritas" if favorita else "Agregar a favoritas",
                             diametro=S(40), activo=favorita, relleno=favorita)
            self.boton_icono("eliminar", x_siguiente + S(60), cy, icono_papelera, S(22),
                             lambda: app.eliminar_cancion(actual["id"]),
                             tooltip="Eliminar de la lista", diametro=S(40))
            x_siguiente += S(96)
        if hay_canciones:
            arriba, abajo = self.fondos(cy, S(34))
            caja = dibujar_pastilla(self, x_siguiente + S(8), cy, "Ver estructura",
                                    app.fuente(9, negrita=True), "contorno",
                                    self.hover == "estructura", arriba, alto=S(34),
                                    icono=icono_estructura, fondo_inf=abajo)
            self.region(*caja, "estructura", lambda: app.navegar("estructura"))
        else:
            arriba, abajo = self.fondos(cy, S(40))
            caja = dibujar_pastilla(self, x_siguiente + S(8), cy, "Agregar canciones",
                                    app.fuente(10, negrita=True), "primario",
                                    self.hover == "agregar", arriba, alto=S(40), icono=icono_mas,
                                    fondo_inf=abajo)
            self.region(*caja, "agregar", app.accion_agregar)

    def _dibujar_esqueleto(self, x, y, tam, x_texto, ancho_texto) -> None:
        bloques = [(x, y, x + tam, y + tam),
                   (x_texto, S(182), x_texto + ancho_texto * 0.25, S(194)),
                   (x_texto, S(206), x_texto + ancho_texto * 0.7, S(244)),
                   (x_texto, S(256), x_texto + ancho_texto * 0.45, S(270)),
                   (S(28), S(312), S(84), S(368))]
        for x0, y0, x1, y1 in bloques:
            self.create_rectangle(x0, y0, x1, y1, fill=COLORES["esqueleto"], outline="",
                                  tags=("esqueleto",))


class FilaTarjetas(CanvasInteractivo):
    """Fila horizontal de tarjetas con portada (estilo Spotify)."""

    def __init__(self, padre, app, al_cambiar_vista: Callable):
        super().__init__(padre, app, COLORES["panel"], height=S(258))
        self.canciones: list[dict] = []
        self.ancho_tarjeta = S(180)
        self.configure(xscrollincrement=self.ancho_tarjeta, xscrollcommand=lambda *_: al_cambiar_vista())
        self._al_rueda_h = lambda pasos: self.xview_scroll(pasos, "units")
        self._animacion = (None, 1.0)

    def establecer(self, canciones: list[dict]) -> None:
        self.canciones = canciones
        self.redibujar()

    def mover_pagina(self, sentido: int) -> None:
        unidades = max(1, self.winfo_width() // self.ancho_tarjeta - 1)
        self.xview_scroll(sentido * unidades, "units")

    def al_cambiar_hover(self) -> None:
        clave = self.hover
        id_tarjeta = clave[1] if isinstance(clave, tuple) else None
        if id_tarjeta is None or id_tarjeta == self._animacion[0]:
            return
        self._animacion = (id_tarjeta, 0.0)

        def paso(progreso):
            if self._animacion[0] == id_tarjeta:
                self._animacion = (id_tarjeta, progreso)
                self.redibujar()

        self.app.animar(160, paso)

    def dibujar(self, ancho, alto) -> None:
        app = self.app
        if app.esperando_backend:
            for i in range(max(1, ancho // self.ancho_tarjeta)):
                x = S(16) + i * self.ancho_tarjeta
                self.create_rectangle(x + S(12), S(12), x + S(164), S(164), fill=COLORES["esqueleto"],
                                      outline="", tags=("esqueleto",))
                self.create_rectangle(x + S(12), S(180), x + S(130), S(192),
                                      fill=COLORES["esqueleto"], outline="", tags=("esqueleto",))
            return
        total = S(32) + len(self.canciones) * self.ancho_tarjeta
        self.configure(scrollregion=(0, 0, max(total, ancho), alto))
        for i, cancion in enumerate(self.canciones):
            self._dibujar_tarjeta(S(16) + i * self.ancho_tarjeta, cancion)

    def _dibujar_tarjeta(self, x, cancion) -> None:
        app, C = self.app, COLORES
        id_cancion = cancion["id"]
        clave_tarjeta, clave_play = ("tarjeta", id_cancion), ("play", id_cancion)
        hover = self.hover in (clave_tarjeta, clave_play)
        es_actual = id_cancion == app.estado["actual_id"]
        es_seleccion = id_cancion == app.seleccion_id
        x1 = x + self.ancho_tarjeta - S(4)
        if hover or es_seleccion:
            rect_redondeado(self, x, 0, x1, S(250), S(10),
                            C["activo"] if es_seleccion else C["elevado"], self.fondo)
        tam = S(152)
        xp, yp = x + S(12), S(12)
        self.portada(id_cancion, xp, yp, tam, self.fondo)
        ancho_texto = self.ancho_tarjeta - S(28)
        f_titulo, f_sub = app.fuente(10, negrita=True), app.fuente(9)
        self.create_text(xp, S(184), anchor="w", font=f_titulo,
                         fill=C["acento_texto"] if es_actual else C["texto"],
                         text=truncar_texto(cancion["titulo"], f_titulo, ancho_texto))
        self.create_text(xp, S(204), anchor="w", font=f_sub, fill=C["texto_sec"],
                         text=truncar_texto(cancion["artista"], f_sub, ancho_texto))
        posicion = app.indices.get(id_cancion, 0) + 1
        self.create_text(xp, S(224), anchor="w", font=app.fuente(8, mono=True),
                         fill=C["texto_tenue"], text=f"Nodo {posicion} · ID {id_cancion}")
        self.region(x, 0, x1, S(250), clave_tarjeta,
                    al_clic=lambda: app.seleccionar(id_cancion),
                    al_doble=lambda: app.activar_cancion(id_cancion),
                    al_menu=lambda xr, yr: app.mostrar_menu_cancion(id_cancion, xr, yr))

        sonando = es_actual and app.estado["reproduciendo"]
        if hover or sonando:
            progreso = self._animacion[1] if self._animacion[0] == id_cancion else 1.0
            desplazamiento = S(8) * (1 - progreso)
            cx = xp + tam - S(28)
            cy = yp + tam - S(28) + desplazamiento
            accion = app.accion_alternar if es_actual else (lambda: app.activar_cancion(id_cancion))
            color_detras = mezclar_color(PALETAS_PORTADA[id_cancion % len(PALETAS_PORTADA)][1],
                                         "#000000", 0.3)
            self.boton_reproducir(clave_play, cx, cy, S(46), sonando, accion, C["acento"],
                                  C["acento_hover"], fondo=color_detras,
                                  tooltip="Pausar" if sonando else "Reproducir")


class EncabezadoSeccion(CanvasInteractivo):
    """Título de sección con enlace "Mostrar todo" y flechas de desplazamiento."""

    def __init__(self, padre, app, titulo: str, subtitulo: str, al_ver_todo: Callable | None):
        super().__init__(padre, app, COLORES["panel"], height=S(58))
        self.titulo, self.subtitulo = titulo, subtitulo
        self.al_ver_todo = al_ver_todo
        self.fila: FilaTarjetas | None = None

    def dibujar(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        self.create_text(S(28), S(24), anchor="w", text=self.titulo,
                         font=app.fuente(16, negrita=True, display=True), fill=C["texto"])
        self.create_text(S(28), S(46), anchor="w", text=self.subtitulo, font=app.fuente(9),
                         fill=C["texto_sec"])
        x = ancho - S(28)
        if self.fila is not None:
            inicio, fin = self.fila.xview()
            for clave, icono, sentido, habilitado in (("der", icono_chevron_der, 1, fin < 0.999),
                                                      ("izq", icono_chevron_izq, -1, inicio > 0.001)):
                cx = x - S(16)
                hover = self.hover == clave and habilitado
                dibujar_circulo(self, cx, S(28), S(32), C["hover"] if hover else C["elevado"],
                                self.fondo)
                icono(self, cx, S(28), S(12), C["texto"] if habilitado else C["texto_tenue"])
                self.region(cx - S(16), S(12), cx + S(16), S(44), clave,
                            (lambda s=sentido: self.fila.mover_pagina(s)) if habilitado else None)
                x -= S(40)
        if self.al_ver_todo:
            hover = self.hover == "todo"
            fuente = app.fuente(9, negrita=True)
            texto = "Mostrar todo"
            x0 = x - S(8) - fuente.measure(texto)
            self.create_text(x - S(8), S(28), anchor="e", text=texto, font=fuente,
                             fill=C["texto"] if hover else C["texto_sec"])
            if hover:
                self.create_line(x0, S(37), x - S(8), S(37), fill=C["texto"])
            self.region(x0, S(16), x - S(8), S(40), "todo", self.al_ver_todo)


class SeccionTarjetas(tk.Frame):
    def __init__(self, padre, app, titulo, subtitulo, al_ver_todo=None):
        super().__init__(padre, bg=COLORES["panel"])
        self.encabezado = EncabezadoSeccion(self, app, titulo, subtitulo, al_ver_todo)
        self.encabezado.pack(fill="x")
        self.fila = FilaTarjetas(self, app, self.encabezado.redibujar_diferido)
        self.fila.pack(fill="x", padx=S(12))
        self.encabezado.fila = self.fila

    def establecer(self, canciones: list[dict]) -> None:
        self.fila.establecer(canciones)
        self.fila.xview_moveto(0)
        self.encabezado.redibujar()


class EncabezadoEstructura(CanvasInteractivo):
    """Título de la sección de estructura en Inicio."""

    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], height=S(58))

    def dibujar(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        self.create_text(S(28), S(24), anchor="w", text="Estructura en vivo",
                         font=app.fuente(16, negrita=True, display=True), fill=C["texto"])
        self.create_text(S(28), S(46), anchor="w", font=app.fuente(9), fill=C["texto_sec"],
                         text="Así está enlazada tu lista ahora mismo")
        hover = self.hover == "abrir"
        fuente = app.fuente(9, negrita=True)
        texto = "Abrir vista completa"
        x1 = ancho - S(28)
        x0 = x1 - fuente.measure(texto)
        self.create_text(x1, S(28), anchor="e", text=texto, font=fuente,
                         fill=C["texto"] if hover else C["texto_sec"])
        if hover:
            self.create_line(x0, S(37), x1, S(37), fill=C["texto"])
        self.region(x0, S(16), x1, S(40), "abrir", lambda: app.navegar("estructura"))


class VistaInicio(tk.Frame):
    def __init__(self, padre, app):
        super().__init__(padre, bg=COLORES["panel"])
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.desplazable = VistaDesplazable(self, COLORES["panel"], mostrar_barra=False,
                                            al_desplazar=lambda _i: app.actualizar_esquinas_centro())
        self.desplazable.grid(row=0, column=0, sticky="nsew")
        contenido = self.desplazable.contenido
        self.hero = HeroInicio(contenido, app)
        self.hero.pack(fill="x")
        self.circulo = SeccionTarjetas(
            contenido, app, "Siguen en el círculo",
            "Recorrido desde el nodo actual siguiendo las referencias «siguiente»",
            al_ver_todo=lambda: app.navegar("biblioteca"))
        self.circulo.pack(fill="x", pady=(0, S(8)))
        self.recientes = SeccionTarjetas(contenido, app, "Escuchadas recientemente",
                                         "Canciones que sonaron durante esta sesión")
        self.estructura = tk.Frame(contenido, bg=COLORES["panel"])
        self.estructura.pack(fill="x", pady=(0, S(28)))
        EncabezadoEstructura(self.estructura, app).pack(fill="x")
        self.visualizador = VisualizadorLista(self.estructura, app, compacto=True)
        self.visualizador.pack(fill="x", padx=S(12))
        self._recientes_visibles = False
        self._circulo_visible = True

    def en_la_cima(self) -> bool:
        return self.desplazable.en_la_cima()

    def refrescar(self, cambios: set) -> None:
        app = self.app
        if cambios & {"lista", "actual", "reproduccion", "favoritos", "esperando", "callbacks"}:
            self.hero.redibujar()
        if cambios & {"lista", "actual", "reproduccion", "seleccion", "esperando"}:
            mostrar = bool(app.estado["canciones"]) or app.esperando_backend
            if mostrar != self._circulo_visible:
                self._circulo_visible = mostrar
                if mostrar:
                    self.circulo.pack(fill="x", pady=(0, S(8)), after=self.hero)
                else:
                    self.circulo.pack_forget()
            self.circulo.establecer(app.canciones_desde_actual())
        if cambios & {"recientes", "lista", "actual", "reproduccion", "seleccion"}:
            recientes = app.canciones_recientes()
            mostrar = bool(recientes) and not app.esperando_backend
            if mostrar != self._recientes_visibles:
                self._recientes_visibles = mostrar
                if mostrar:
                    self.recientes.pack(fill="x", pady=(0, S(8)), before=self.estructura)
                else:
                    self.recientes.pack_forget()
            if mostrar:
                self.recientes.establecer(recientes)
        if cambios & {"lista", "actual", "seleccion", "esperando"}:
            self.visualizador.redibujar()
        if "actual" in cambios and app.estado["actual_id"] is not None:
            self.visualizador.centrar_en(app.estado["actual_id"])


# ----------------------------------------------------------------------
# 7.5 Vista Biblioteca (lista de canciones con filtros y búsqueda)
# ----------------------------------------------------------------------

class EncabezadoBiblioteca(CanvasInteractivo):
    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], height=S(300))

    def _color_en(self, y, alto) -> str:
        return mezclar_color(COLOR_BIBLIOTECA, COLORES["panel"], limitar(y / alto, 0, 1))

    def color_fondo_en(self, y: float) -> str:
        return self._color_en(y, max(1, self.winfo_height()))

    def dibujar(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        for y in range(0, alto, 2):
            self.create_line(0, y, ancho, y, width=2, fill=self._color_en(y, alto))
        pad, tam, y_tile = S(28), S(168), S(52)
        rect_redondeado(self, pad, y_tile, pad + tam, y_tile + tam, S(8),
                        mezclar_color(C["acento"], "#000000", 0.12), self._color_en(y_tile, alto),
                        self._color_en(y_tile + tam, alto))
        icono_estructura(self, pad + tam / 2, y_tile + tam / 2, S(82), "#FFFFFF", relleno=True)

        consulta = app.consulta_busqueda
        canciones = app.estado["canciones"]
        filtradas = app.canciones_filtradas()
        if consulta:
            antetitulo, titulo = "BÚSQUEDA", f"«{consulta}»"
            detalle = f"{len(filtradas)} de {len(canciones)} canciones coinciden"
        elif app.filtro_favoritas:
            antetitulo, titulo = "COLECCIÓN", "Tus favoritas"
            detalle = f"{len(filtradas)} canción{'es' if len(filtradas) != 1 else ''} marcadas"
        else:
            antetitulo, titulo = "LISTA DOBLEMENTE ENLAZADA CIRCULAR", "Tu biblioteca"
            n = len(canciones)
            detalle = f"{n} canción{'es' if n != 1 else ''}"
            if canciones:
                detalle += f", {app.texto_duracion_total()}  •  cabeza: ID {canciones[0]['id']}"
        x_texto = pad + tam + S(28)
        ancho_texto = ancho - x_texto - pad
        self.create_text(x_texto, S(118), anchor="sw", text=antetitulo,
                         font=app.fuente(9, negrita=True), fill=C["texto"])
        fuente = app.fuente(40, negrita=True, display=True)
        self.create_text(x_texto, S(176), anchor="sw", font=fuente, fill=C["texto"],
                         text=truncar_texto(titulo, fuente, ancho_texto))
        fuente_detalle = app.fuente(10)
        self.create_text(x_texto, S(212), anchor="sw", font=fuente_detalle, fill=C["texto_sec"],
                         text=truncar_texto("CIRCULAR MUSIC  •  " + detalle, fuente_detalle,
                                            ancho_texto))
        self._dibujar_acciones(pad, S(262), alto, ancho, filtradas)

    def _dibujar_acciones(self, x, cy, alto, ancho, filtradas) -> None:
        app, C = self.app, COLORES
        fondo, fondo_inf = self.fondos(cy, S(32))
        reproduciendo = app.estado["reproduciendo"]
        actual_visible = any(c["id"] == app.estado["actual_id"] for c in filtradas)

        def reproducir():
            if actual_visible:
                app.accion_alternar()
            elif filtradas:
                app.activar_cancion(filtradas[0]["id"])

        self.boton_reproducir("reproducir", x + S(26), cy, S(52), reproduciendo and actual_visible,
                              reproducir, C["acento"], C["acento_hover"],
                              habilitado=bool(filtradas), tooltip="Reproducir")
        xc = x + S(72)
        for clave, texto in (("todas", "Todas"), ("favoritas", "Favoritas")):
            activa = (clave == "favoritas") == app.filtro_favoritas
            caja = dibujar_pastilla(self, xc, cy, texto, app.fuente(9, negrita=True),
                                    "chip_activo" if activa else "chip", self.hover == ("chip", clave),
                                    fondo, alto=S(32), fondo_inf=fondo_inf)
            self.region(*caja, ("chip", clave),
                        lambda c=clave: app.establecer_filtro_favoritas(c == "favoritas"))
            xc = caja[2] + S(8)
        caja = dibujar_pastilla(self, xc + S(8), cy, "Agregar canciones", app.fuente(9, negrita=True),
                                "contorno", self.hover == "agregar", fondo, alto=S(32),
                                icono=icono_mas, fondo_inf=fondo_inf)
        self.region(*caja, "agregar", app.accion_agregar, tooltip="Ctrl+O")
        hay_seleccion = app.seleccion_id is not None
        caja = dibujar_pastilla(self, ancho - S(28), cy, "Eliminar seleccionada",
                                app.fuente(9, negrita=True), "sutil", self.hover == "eliminar", fondo,
                                alto=S(32), icono=icono_papelera, alinear="e",
                                habilitado=hay_seleccion, fondo_inf=fondo_inf)
        self.region(*caja, "eliminar", app.eliminar_seleccion if hay_seleccion else None,
                    tooltip="Supr" if hay_seleccion else "Selecciona una canción")


def columnas_tabla(ancho: int, mostrar_ids: bool) -> dict:
    """Posiciones X de las columnas (compartidas por cabecera y filas)."""
    columna_id = ancho - S(200)
    columna_fav = ancho - S(116)
    limite_titulo = (columna_id - S(40)) if mostrar_ids else (columna_fav - S(30))
    return {"indice": S(36), "portada": S(64), "titulo": S(116), "id": columna_id,
            "fav": columna_fav, "duracion": ancho - S(28),
            "ancho_titulo": limite_titulo - S(116)}


class CabeceraTabla(CanvasInteractivo):
    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], height=S(38))

    def dibujar(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        col = columnas_tabla(ancho, app.prefs["mostrar_ids"])
        fuente, color = app.fuente(9), C["texto_sec"]
        y = alto / 2
        self.create_text(col["indice"], y, text="#", font=fuente, fill=color)
        self.create_text(col["portada"], y, text="Título", anchor="w", font=fuente, fill=color)
        if app.prefs["mostrar_ids"]:
            self.create_text(col["id"], y, text="ID", font=fuente, fill=color)
        self.create_text(col["duracion"], y, text="Duración", anchor="e", font=fuente, fill=color)
        self.create_line(S(12), alto - 1, ancho - S(12), alto - 1, fill=C["borde"])


class TablaCanciones(ListaVirtual):
    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], alto_fila=S(58), margen=S(8))

    def dibujar_fila(self, indice, cancion, y0, ancho) -> None:
        app, C = self.app, COLORES
        id_cancion = cancion["id"]
        col = columnas_tabla(ancho, app.prefs["mostrar_ids"])
        y1 = y0 + self.alto_fila
        cy = (y0 + y1) / 2
        es_actual = id_cancion == app.estado["actual_id"]
        es_seleccion = id_cancion == app.seleccion_id
        clave = ("fila", id_cancion)
        hover = self.hover in (clave, ("play", id_cancion), ("fav", id_cancion))
        color_fila = C["activo"] if es_seleccion else C["hover"] if hover else None
        fondo_fila = color_fila or self.fondo
        if color_fila:
            rect_redondeado(self, S(8), y0 + S(2), ancho - S(8), y1 - S(2), S(6), color_fila,
                            self.fondo)
        self.region(S(8), y0, ancho - S(8), y1, clave,
                    al_clic=lambda: app.seleccionar(id_cancion),
                    al_doble=lambda: app.activar_cancion(id_cancion),
                    al_menu=lambda x, y: app.mostrar_menu_cancion(id_cancion, x, y))

        posicion = app.indices.get(id_cancion, 0) + 1
        sonando = es_actual and app.estado["reproduciendo"]
        if hover:
            dibujo = icono_pausa if sonando else icono_reproducir
            dibujo(self, col["indice"], cy, S(14), C["texto"])
            accion = app.accion_alternar if es_actual else (lambda: app.activar_cancion(id_cancion))
            self.region(col["indice"] - S(16), y0, col["indice"] + S(16), y1, ("play", id_cancion),
                        accion, tooltip="Pausar" if sonando else "Reproducir")
        elif sonando:
            self.ecualizador(col["indice"] - S(6), cy + S(7), C["acento"])
        else:
            self.create_text(col["indice"], cy, text=str(posicion), font=app.fuente(10),
                             fill=C["acento_texto"] if es_actual else C["texto_sec"])

        self.portada(id_cancion, col["portada"], cy - S(20), S(40), fondo_fila)
        f_titulo, f_artista = app.fuente(10, negrita=True), app.fuente(9)
        self.create_text(col["titulo"], cy - S(9), anchor="w", font=f_titulo,
                         fill=C["acento_texto"] if es_actual else C["texto"],
                         text=truncar_texto(cancion["titulo"], f_titulo, col["ancho_titulo"]))
        self.create_text(col["titulo"], cy + S(10), anchor="w", font=f_artista,
                         fill=C["texto_sec"],
                         text=truncar_texto(cancion["artista"], f_artista, col["ancho_titulo"]))
        if app.prefs["mostrar_ids"]:
            self.create_text(col["id"], cy, text=str(id_cancion), font=app.fuente(9, mono=True),
                             fill=C["texto_sec"])
        favorita = app.es_favorita(id_cancion)
        if favorita or hover:
            hover_fav = self.hover == ("fav", id_cancion)
            color = C["acento"] if favorita else (C["texto"] if hover_fav else C["texto_sec"])
            icono_corazon(self, col["fav"], cy, S(16), color, relleno=favorita)
            self.region(col["fav"] - S(16), y0 + S(8), col["fav"] + S(16), y1 - S(8),
                        ("fav", id_cancion), lambda: app.alternar_favorito(id_cancion),
                        tooltip="Quitar de favoritas" if favorita else "Agregar a favoritas")
        self.create_text(col["duracion"], cy, anchor="e", text=formatear_tiempo(cancion["duracion"]),
                         font=app.fuente(9, mono=True), fill=C["texto_sec"])

    def dibujar_vacio(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        cx, cy = ancho / 2, min(alto / 2, S(150))
        if not app.estado["canciones"]:
            titulo = "Tu biblioteca está vacía"
            texto = "Agrega canciones para formar los nodos de tu lista circular."
            boton, accion = "Agregar canciones", app.accion_agregar
            icono = icono_nota
        elif app.consulta_busqueda:
            titulo = f"No se encontraron resultados para «{app.consulta_busqueda}»"
            texto = "Revisa la ortografía o prueba con otras palabras."
            boton, accion = "Borrar búsqueda", app.limpiar_busqueda
            icono = icono_buscar
        else:
            titulo = "Aún no tienes favoritas"
            texto = "Toca el corazón de cualquier canción para guardarla aquí."
            boton, accion = "Ver todas", lambda: app.establecer_filtro_favoritas(False)
            icono = icono_corazon
        dibujar_circulo(self, cx, cy - S(48), S(64), C["elevado"], self.fondo)
        icono(self, cx, cy - S(48), S(26), C["texto_sec"])
        f_titulo = app.fuente(15, negrita=True, display=True)
        self.create_text(cx, cy + S(6), font=f_titulo, fill=C["texto"],
                         text=truncar_texto(titulo, f_titulo, ancho - S(60)))
        self.create_text(cx, cy + S(32), text=texto, font=app.fuente(10), fill=C["texto_sec"])
        caja = dibujar_pastilla(self, cx, cy + S(76), boton, app.fuente(10, negrita=True), "claro",
                                self.hover == "vacio", self.fondo, alto=S(40), alinear="center")
        self.region(*caja, "vacio", accion)


class VistaBiblioteca(tk.Frame):
    def __init__(self, padre, app):
        super().__init__(padre, bg=COLORES["panel"])
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.encabezado = EncabezadoBiblioteca(self, app)
        self.encabezado.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.cabecera = CabeceraTabla(self, app)
        self.cabecera.grid(row=1, column=0, sticky="ew", padx=(S(12), 0))
        self.tabla = TablaCanciones(self, app)
        self.tabla.grid(row=2, column=0, sticky="nsew", padx=(S(12), 0), pady=(0, S(8)))
        barra = BarraAuto(self, orient="vertical", style="Fina.Vertical.TScrollbar")
        barra.grid(row=2, column=1, sticky="ns", pady=(0, S(8)))
        self.tabla.conectar_barra(barra)

    def refrescar(self, cambios: set) -> None:
        if cambios & {"lista", "actual", "reproduccion", "seleccion", "favoritos", "filtro",
                      "esperando", "callbacks"}:
            self.encabezado.redibujar()
        if "prefs" in cambios:
            self.cabecera.redibujar()
        if cambios & {"lista", "actual", "reproduccion", "seleccion", "favoritos", "filtro",
                      "esperando", "prefs"}:
            self.tabla.establecer_elementos(self.app.canciones_filtradas())
        if "actual" in cambios and self.app.estado["actual_id"] is not None:
            self.tabla.asegurar_visible(self.app.estado["actual_id"])


# ----------------------------------------------------------------------
# 7.6 Vista Estructura (visualizador grande)
# ----------------------------------------------------------------------

class EncabezadoVistaEstructura(CanvasInteractivo):
    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], height=S(150))

    def dibujar(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        self.create_text(S(28), S(30), anchor="nw", text="Estructura de datos",
                         font=app.fuente(28, negrita=True, display=True), fill=C["texto"])
        f_sub = app.fuente(10)
        self.create_text(S(28), S(80), anchor="nw", font=f_sub, fill=C["texto_sec"],
                         text=truncar_texto("Lista doblemente enlazada circular · cada canción es un "
                                            "nodo con referencias «siguiente» y «anterior»",
                                            f_sub, ancho - S(56)))
        canciones = app.estado["canciones"]
        actual = app.estado["actual_id"]
        if canciones:
            datos = [f"{len(canciones)} nodo{'s' if len(canciones) != 1 else ''}",
                     f"Cabeza · ID {canciones[0]['id']}", f"Cola · ID {canciones[-1]['id']}",
                     f"Actual · {('ID ' + str(actual)) if actual is not None else 'ninguno'}"]
        else:
            datos = ["0 nodos", "Cabeza · None"]
        x = S(28)
        for texto in datos:
            caja = dibujar_pastilla(self, x, S(124), texto, app.fuente(9, negrita=True), "chip",
                                    False, self.fondo, alto=S(30))
            x = caja[2] + S(8)


class ExplicacionEstructura(CanvasInteractivo):
    TARJETAS = (
        ("siguiente", "Referencia «siguiente» →",
         "Cada nodo apunta al próximo. La flecha punteada superior une la cola con la cabeza."),
        ("anterior", "← Referencia «anterior»",
         "Cada nodo apunta al previo. La flecha punteada inferior une la cabeza con la cola."),
        ("acento", "Nodo actual",
         "Se resalta en violeta. Haz doble clic en cualquier nodo para reproducir esa canción."),
    )

    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], height=S(124))

    def dibujar(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        hueco = S(12)
        ancho_tarjeta = (ancho - 2 * S(28) - 2 * hueco) / 3
        for i, (color, titulo, texto) in enumerate(self.TARJETAS):
            x0 = S(28) + i * (ancho_tarjeta + hueco)
            x1 = x0 + ancho_tarjeta
            rect_redondeado(self, x0, S(8), x1, alto - S(16), S(10), C["elevado"], self.fondo)
            self.create_rectangle(x0 + S(16), S(26), x0 + S(40), S(29), fill=C[color], outline="")
            self.create_text(x0 + S(16), S(44), anchor="w", text=titulo,
                             font=app.fuente(10, negrita=True), fill=C["texto"])
            self.create_text(x0 + S(16), S(58), anchor="nw", text=texto, font=app.fuente(9),
                             fill=C["texto_sec"], width=ancho_tarjeta - S(32))


class VistaEstructura(tk.Frame):
    def __init__(self, padre, app):
        super().__init__(padre, bg=COLORES["panel"])
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.encabezado = EncabezadoVistaEstructura(self, app)
        self.encabezado.grid(row=0, column=0, sticky="ew")
        self.visualizador = VisualizadorLista(self, app, compacto=False)
        self.visualizador.grid(row=1, column=0, sticky="nsew", padx=S(12))
        barra = BarraAuto(self, orient="horizontal", command=self.visualizador.xview,
                          style="Fina.Horizontal.TScrollbar")
        barra.grid(row=2, column=0, sticky="ew", padx=S(28))
        self.visualizador.configure(xscrollcommand=barra.set)
        self.explicacion = ExplicacionEstructura(self, app)
        self.explicacion.grid(row=3, column=0, sticky="ew")

    def refrescar(self, cambios: set) -> None:
        if cambios & {"lista", "actual", "esperando"}:
            self.encabezado.redibujar()
        if cambios & {"lista", "actual", "seleccion", "esperando"}:
            self.visualizador.redibujar()
        if "actual" in cambios and self.app.estado["actual_id"] is not None:
            self.visualizador.centrar_en(self.app.estado["actual_id"])


# ----------------------------------------------------------------------
# 7.7 Vista Ajustes (preferencias reales y guardadas)
# ----------------------------------------------------------------------

class VistaAjustes(tk.Frame):
    OPCIONES = (
        ("panel_derecho", "Mostrar el panel «Ahora suena»",
         "Muestra la portada, los nodos vecinos y la cola a la derecha (Ctrl+J)."),
        ("barra_contraida", "Contraer la barra lateral",
         "Deja solo los iconos para ganar espacio (Ctrl+B)."),
        ("animaciones", "Animaciones y microinteracciones",
         "Ecualizador animado, transiciones y efectos al pasar el mouse."),
        ("mostrar_ids", "Mostrar el ID de cada nodo en la biblioteca",
         "Útil para relacionar cada fila con su nodo en la estructura."),
    )
    ATAJOS = (
        ("Espacio", "Reproducir / pausar"), ("Ctrl + → / ←", "Siguiente / anterior"),
        ("↑ / ↓", "Mover la selección"), ("Enter", "Reproducir la selección"),
        ("Supr", "Eliminar la selección"), ("Ctrl + O", "Agregar canciones"),
        ("Ctrl + F", "Buscar"), ("Esc", "Borrar búsqueda / cerrar menú"),
        ("Ctrl + 1 / 2 / 3", "Inicio / Biblioteca / Estructura"), ("Ctrl + ,", "Ajustes"),
        ("Alt + ← / →", "Atrás / adelante"), ("Ctrl + B / J", "Barra lateral / panel derecho"),
    )

    def __init__(self, padre, app):
        super().__init__(padre, bg=COLORES["panel"])
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        desplazable = VistaDesplazable(self, COLORES["panel"])
        desplazable.grid(row=0, column=0, sticky="nsew")
        cuerpo = tk.Frame(desplazable.contenido, bg=COLORES["panel"])
        cuerpo.pack(fill="x", padx=S(32), pady=(S(28), S(32)))
        self.interruptores: dict[str, Interruptor] = {}
        tk.Label(cuerpo, text="Ajustes", font=app.fuente(28, negrita=True, display=True),
                 bg=COLORES["panel"], fg=COLORES["texto"]).pack(anchor="w", pady=(0, S(18)))
        self._titulo_seccion(cuerpo, "Apariencia y experiencia")
        for clave, titulo, descripcion in self.OPCIONES:
            self._fila_opcion(cuerpo, clave, titulo, descripcion)
        self._titulo_seccion(cuerpo, "Atajos de teclado")
        self._tabla_atajos(cuerpo)
        self._titulo_seccion(cuerpo, "Acerca de")
        for texto in ("CIRCULAR MUSIC · Powered by Linked Structures",
                      "Interfaz en Tkinter, sin dependencias externas. "
                      "La lógica de la lista y el audio pertenecen al backend.",
                      f"Preferencias guardadas en: {ruta_preferencias()}"):
            tk.Label(cuerpo, text=texto, font=app.fuente(9), bg=COLORES["panel"],
                     fg=COLORES["texto_sec"], anchor="w", justify="left",
                     wraplength=S(720)).pack(anchor="w", pady=S(2))

    def _titulo_seccion(self, padre, texto) -> None:
        tk.Label(padre, text=texto, font=self.app.fuente(13, negrita=True), bg=COLORES["panel"],
                 fg=COLORES["texto"]).pack(anchor="w", pady=(S(18), S(8)))

    def _fila_opcion(self, padre, clave, titulo, descripcion) -> None:
        fila = tk.Frame(padre, bg=COLORES["panel"])
        fila.pack(fill="x", pady=S(6))
        fila.columnconfigure(0, weight=1)
        tk.Label(fila, text=titulo, font=self.app.fuente(10), bg=COLORES["panel"],
                 fg=COLORES["texto"], anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(fila, text=descripcion, font=self.app.fuente(9), bg=COLORES["panel"],
                 fg=COLORES["texto_sec"], anchor="w").grid(row=1, column=0, sticky="w")
        interruptor = Interruptor(fila, self.app.prefs[clave],
                                  lambda valor, c=clave: self.app.establecer_preferencia(c, valor),
                                  COLORES["panel"])
        interruptor.grid(row=0, column=1, rowspan=2, padx=(S(16), 0))
        self.interruptores[clave] = interruptor

    def _tabla_atajos(self, padre) -> None:
        tabla = tk.Frame(padre, bg=COLORES["panel"])
        tabla.pack(anchor="w", fill="x")
        for i, (tecla, descripcion) in enumerate(self.ATAJOS):
            fila, columna = divmod(i, 2)
            celda = tk.Frame(tabla, bg=COLORES["panel"])
            celda.grid(row=fila, column=columna, sticky="w", padx=(0, S(36)), pady=S(4))
            tk.Label(celda, text=tecla, font=self.app.fuente(9, mono=True), bg=COLORES["elevado"],
                     fg=COLORES["texto"], padx=S(8), pady=S(3)).pack(side="left")
            tk.Label(celda, text=descripcion, font=self.app.fuente(9), bg=COLORES["panel"],
                     fg=COLORES["texto_sec"]).pack(side="left", padx=(S(10), 0))

    def refrescar(self, cambios: set) -> None:
        if "prefs" in cambios:
            for clave, interruptor in self.interruptores.items():
                interruptor.establecer(self.app.prefs[clave])


# ----------------------------------------------------------------------
# 7.8 Panel derecho "Ahora suena"
# ----------------------------------------------------------------------

class ContenidoAhoraSuena(CanvasInteractivo):
    MAX_COLA = 8

    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["panel"], yscrollincrement=S(20))
        self._al_rueda = self._desplazar

    def _desplazar(self, pasos):
        self.yview_scroll(pasos * 3, "units")

    def dibujar(self, ancho, alto) -> None:
        app, C = self.app, COLORES
        pad = S(16)
        actual = app.cancion_actual()
        titulo = actual["titulo"] if actual else "Ahora suena"
        f_cab = app.fuente(11, negrita=True)
        self.create_text(pad, S(28), anchor="w", fill=C["texto"], font=f_cab,
                         text=truncar_texto(titulo, f_cab, ancho - pad - S(56)))
        self.boton_icono("cerrar", ancho - S(28), S(28), icono_cerrar, S(14),
                         app.alternar_panel_derecho, tooltip="Ocultar «Ahora suena» (Ctrl+J)")
        y = S(58)
        if app.esperando_backend:
            self.create_rectangle(pad, y, ancho - pad, y + ancho - 2 * pad, fill=C["esqueleto"],
                                  outline="", tags=("esqueleto",))
            self.configure(scrollregion=(0, 0, ancho, alto))
            return
        if actual is None:
            self._dibujar_vacio(ancho, y)
            self.configure(scrollregion=(0, 0, ancho, alto))
            return
        tam = ancho - 2 * pad
        self.portada(actual["id"], pad, y, tam, self.fondo, radio=S(8), prioridad=True)
        y += tam + S(22)
        f_titulo = app.fuente(17, negrita=True, display=True)
        self.create_text(pad, y, anchor="w", fill=C["texto"], font=f_titulo,
                         text=truncar_texto(actual["titulo"], f_titulo, tam - S(44)))
        f_artista = app.fuente(10)
        self.create_text(pad, y + S(26), anchor="w", fill=C["texto_sec"], font=f_artista,
                         text=truncar_texto(actual["artista"], f_artista, tam - S(44)))
        favorita = app.es_favorita(actual["id"])
        self.boton_icono("favorita", ancho - pad - S(16), y + S(10), icono_corazon, S(20),
                         lambda: app.alternar_favorito(actual["id"]),
                         tooltip="Quitar de favoritas" if favorita else "Agregar a favoritas",
                         activo=favorita, relleno=favorita)
        y += S(58)
        y = self._tarjeta_nodo(ancho, y, actual)
        y = self._tarjeta_cola(ancho, y + S(14), actual)
        self.configure(scrollregion=(0, 0, ancho, max(alto, y + S(20))))

    def _tarjeta_nodo(self, ancho, y, actual) -> float:
        app, C = self.app, COLORES
        pad = S(16)
        canciones = app.estado["canciones"]
        i = app.indices[actual["id"]]
        n = len(canciones)
        anterior, siguiente = canciones[i - 1], canciones[(i + 1) % n]
        alto_tarjeta = S(176)
        rect_redondeado(self, pad, y, ancho - pad, y + alto_tarjeta, S(10), C["elevado"], self.fondo)
        self.create_text(pad + S(16), y + S(26), anchor="w", text="Nodo en la estructura",
                         font=app.fuente(11, negrita=True), fill=C["texto"])
        self.create_text(ancho - pad - S(16), y + S(26), anchor="e", text=f"{i + 1} de {n}",
                         font=app.fuente(9, mono=True), fill=C["texto_sec"])
        self.create_text(pad + S(16), y + S(52), anchor="w", text=f"ID {actual['id']}",
                         font=app.fuente(9, mono=True), fill=C["texto_sec"])
        fila_y = y + S(84)
        for clave, etiqueta, color, vecino in (("ant", "← anterior", C["anterior"], anterior),
                                               ("sig", "siguiente →", C["siguiente"], siguiente)):
            hover = self.hover == ("vecino", clave)
            if hover:
                rect_redondeado(self, pad + S(6), fila_y - S(20), ancho - pad - S(6), fila_y + S(20),
                                S(6), C["hover"], C["elevado"])
            self.create_text(pad + S(16), fila_y - S(8), anchor="w", text=etiqueta,
                             font=app.fuente(8, negrita=True), fill=color)
            mismo = vecino["id"] == actual["id"]
            texto = "sí mismo (un solo nodo)" if mismo else vecino["titulo"]
            f_vecino = app.fuente(10)
            self.create_text(pad + S(16), fila_y + S(9), anchor="w", font=f_vecino,
                             fill=C["texto"] if hover else C["texto_sec"],
                             text=truncar_texto(f"{texto}  ·  ID {vecino['id']}", f_vecino,
                                                ancho - 2 * pad - S(32)))
            id_vecino = vecino["id"]
            self.region(pad + S(6), fila_y - S(20), ancho - pad - S(6), fila_y + S(20),
                        ("vecino", clave), al_clic=lambda v=id_vecino: app.activar_cancion(v),
                        tooltip="Reproducir este nodo")
            fila_y += S(44)
        return y + alto_tarjeta

    def _tarjeta_cola(self, ancho, y, actual) -> float:
        app, C = self.app, COLORES
        pad = S(16)
        cola = app.cola_siguientes(self.MAX_COLA)
        alto_fila = S(54)
        n = len(app.estado["canciones"])
        da_la_vuelta = n - 1 <= self.MAX_COLA and n > 1
        alto_tarjeta = S(64) + max(1, len(cola)) * alto_fila + (S(30) if da_la_vuelta else S(8))
        rect_redondeado(self, pad, y, ancho - pad, y + alto_tarjeta, S(10), C["elevado"], self.fondo)
        self.create_text(pad + S(16), y + S(26), anchor="w", text="A continuación",
                         font=app.fuente(11, negrita=True), fill=C["texto"])
        self.create_text(pad + S(16), y + S(46), anchor="w", font=app.fuente(8), fill=C["texto_tenue"],
                         text="Siguiendo las referencias «siguiente»")
        fila_y = y + S(64)
        if not cola:
            self.create_text(pad + S(16), fila_y + S(20), anchor="w", font=app.fuente(9),
                             fill=C["texto_sec"],
                             text="El siguiente nodo es el mismo (un solo nodo).")
        for cancion in cola:
            id_cancion = cancion["id"]
            hover = self.hover == ("cola", id_cancion)
            if hover:
                rect_redondeado(self, pad + S(6), fila_y + S(2), ancho - pad - S(6),
                                fila_y + alto_fila - S(2), S(6), C["hover"], C["elevado"])
            fondo = C["hover"] if hover else C["elevado"]
            cy = fila_y + alto_fila / 2
            self.portada(id_cancion, pad + S(14), cy - S(20), S(40), fondo)
            ancho_texto = ancho - 2 * pad - S(80)
            f_t, f_a = app.fuente(10, negrita=True), app.fuente(9)
            self.create_text(pad + S(64), cy - S(9), anchor="w", font=f_t, fill=C["texto"],
                             text=truncar_texto(cancion["titulo"], f_t, ancho_texto))
            self.create_text(pad + S(64), cy + S(10), anchor="w", font=f_a, fill=C["texto_sec"],
                             text=truncar_texto(cancion["artista"], f_a, ancho_texto))
            self.region(pad + S(6), fila_y, ancho - pad - S(6), fila_y + alto_fila,
                        ("cola", id_cancion), al_clic=lambda c=id_cancion: app.seleccionar(c),
                        al_doble=lambda c=id_cancion: app.activar_cancion(c),
                        al_menu=lambda xr, yr, c=id_cancion: app.mostrar_menu_cancion(c, xr, yr))
            fila_y += alto_fila
        if da_la_vuelta:
            f = app.fuente(9)
            self.create_text(pad + S(16), fila_y + S(14), anchor="w", font=f, fill=C["texto_tenue"],
                             text=truncar_texto(f"↻ Después vuelve a «{actual['titulo']}»", f,
                                                ancho - 2 * pad - S(32)))
        return y + alto_tarjeta

    def _dibujar_vacio(self, ancho, y) -> None:
        app, C = self.app, COLORES
        cx = ancho / 2
        dibujar_circulo(self, cx, y + S(90), S(96), C["elevado"], self.fondo)
        icono_nota(self, cx, y + S(90), S(40), C["texto_sec"])
        self.create_text(cx, y + S(170), text="Nada sonando", font=app.fuente(13, negrita=True),
                         fill=C["texto"])
        self.create_text(cx, y + S(196), font=app.fuente(9), fill=C["texto_sec"], justify="center",
                         width=ancho - S(48),
                         text="Elige una canción para ver aquí sus nodos vecinos y la cola.")


class PanelDerecho(PanelRedondeado):
    def __init__(self, padre, app):
        super().__init__(padre, COLORES["panel"], COLORES["fondo"], S(10), width=S(330))
        self.app = app
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.contenido = ContenidoAhoraSuena(self, app)
        self.contenido.grid(row=0, column=0, sticky="nsew", padx=S(2), pady=S(4))
        self.after_idle(self.levantar_esquinas)

    def refrescar(self, cambios: set) -> None:
        if cambios & {"lista", "actual", "favoritos", "esperando", "seleccion"}:
            if "actual" in cambios:
                self.contenido.yview_moveto(0)
            self.contenido.redibujar()


# ----------------------------------------------------------------------
# 7.9 Barra de reproducción inferior
# ----------------------------------------------------------------------

class BarraReproductor(CanvasInteractivo):
    def __init__(self, padre, app):
        super().__init__(padre, app, COLORES["fondo"], height=S(92))
        self.progreso = Deslizador(self, COLORES["fondo"], al_mover=app.al_mover_progreso,
                                   al_soltar=app.al_soltar_progreso)
        self.volumen = Deslizador(self, COLORES["fondo"], al_mover=app.al_mover_volumen,
                                  al_soltar=app.al_soltar_volumen)
        self._item_progreso = None
        self._item_volumen = None

    def refrescar(self, cambios: set) -> None:
        if cambios <= {"posicion"}:
            self.actualizar_tiempos()
        else:
            self.redibujar()

    def dibujar(self, ancho, alto) -> None:
        cy = alto / 2
        ancho_zona = min(S(720), ancho * 0.42)
        self._dibujar_cancion(cy, ancho / 2 - ancho_zona / 2 - S(24))
        self._dibujar_controles(ancho / 2, ancho_zona)
        self._dibujar_volumen(ancho, cy)
        self.actualizar_tiempos()

    def _dibujar_cancion(self, cy, ancho_max) -> None:
        app, C = self.app, COLORES
        actual = app.cancion_actual()
        x = S(16)
        tam = S(56)
        if actual is None:
            rect_redondeado(self, x, cy - tam / 2, x + tam, cy + tam / 2, S(4), C["elevado"], self.fondo)
            icono_nota(self, x + tam / 2, cy, S(22), C["texto_tenue"])
            self.create_text(x + tam + S(14), cy, anchor="w", text="Nada sonando",
                             font=app.fuente(10, negrita=True), fill=C["texto_sec"])
            return
        self.portada(actual["id"], x, cy - tam / 2, tam, self.fondo)
        ancho_texto = max(S(40), ancho_max - tam - S(70))
        f_t, f_a = app.fuente(10, negrita=True), app.fuente(9)
        titulo = truncar_texto(actual["titulo"], f_t, ancho_texto)
        artista = truncar_texto(actual["artista"], f_a, ancho_texto)
        hover = self.hover == "titulo"
        xt = x + tam + S(14)
        self.create_text(xt, cy - S(9), anchor="w", text=titulo, font=f_t, fill=C["texto"])
        if hover:
            self.create_line(xt, cy + S(1), xt + f_t.measure(titulo), cy + S(1), fill=C["texto"])
        self.create_text(xt, cy + S(11), anchor="w", text=artista, font=f_a, fill=C["texto_sec"])
        self.region(xt, cy - S(20), xt + f_t.measure(titulo), cy + S(2), "titulo",
                    lambda: app.navegar("inicio"), tooltip="Ver en Inicio")
        favorita = app.es_favorita(actual["id"])
        x_corazon = xt + max(f_t.measure(titulo), f_a.measure(artista)) + S(26)
        self.boton_icono("favorita", x_corazon, cy, icono_corazon, S(16),
                         lambda: app.alternar_favorito(actual["id"]),
                         tooltip="Quitar de favoritas" if favorita else "Agregar a favoritas",
                         activo=favorita, relleno=favorita)

    def _dibujar_controles(self, cx, ancho_zona) -> None:
        app = self.app
        hay = bool(app.estado["canciones"])
        y_botones = S(32)
        reproduciendo = app.estado["reproduciendo"]
        self.boton_icono("aleatorio", cx - S(104), y_botones, icono_aleatorio, S(18),
                         lambda: app._invocar("alternar_aleatorio"),
                         tooltip="Desactivar aleatorio" if app.estado["aleatorio"] else "Activar aleatorio",
                         activo=app.estado["aleatorio"],
                         habilitado=hay and "alternar_aleatorio" in app._callbacks)
        self.boton_icono("repeticion", cx + S(104), y_botones, icono_repetir, S(18),
                         lambda: app._invocar("alternar_repeticion"),
                         tooltip="Repetir todo (circular)" if app.estado["repetir_uno"] else "Repetir una canción",
                         activo=app.estado["repetir_uno"],
                         habilitado=hay and "alternar_repeticion" in app._callbacks)
        self.boton_icono("anterior", cx - S(52), y_botones, icono_anterior, S(16), app.accion_anterior,
                         tooltip="Anterior (Ctrl+←)", habilitado=hay)
        self.boton_reproducir("reproducir", cx, y_botones, S(36), reproduciendo, app.accion_alternar,
                              COLORES["texto"], "#FFFFFF", habilitado=hay,
                              tooltip="Pausar (Espacio)" if reproduciendo else "Reproducir (Espacio)")
        self.boton_icono("siguiente", cx + S(52), y_botones, icono_siguiente, S(16),
                         app.accion_siguiente, tooltip="Siguiente (Ctrl+→)", habilitado=hay)
        y = S(68)
        x0, x1 = cx - ancho_zona / 2 + S(48), cx + ancho_zona / 2 - S(48)
        fuente = app.fuente(8, mono=True)
        self.create_text(x0 - S(6), y, anchor="e", text="", font=fuente, fill=COLORES["texto_sec"],
                         tags=("tiempo_actual",))
        self.create_text(x1 + S(6), y, anchor="w", text="", font=fuente, fill=COLORES["texto_sec"],
                         tags=("tiempo_total",))
        self._item_progreso = self._colocar(self._item_progreso, self.progreso, x0, y, x1 - x0)

    def _dibujar_volumen(self, ancho, cy) -> None:
        app = self.app
        ancho_slider = S(104)
        x_slider = ancho - S(20) - ancho_slider
        volumen = self.volumen.valor if self.volumen.arrastrando else app.estado["volumen"]
        cx_icono = x_slider - S(18)

        def icono(lienzo, x, y, tam, color, relleno=False):
            icono_volumen(lienzo, x, y, tam, color, volumen)

        self.boton_icono("volumen", cx_icono, cy, icono, S(16), app.alternar_silencio,
                         tooltip=lambda: (f"Volumen {round(app.estado['volumen'] * 100)} % · "
                                          "clic para silenciar" if app.estado["volumen"] > 0
                                          else "Activar sonido"))
        self.boton_icono("panel", cx_icono - S(42), cy, icono_ahora_suena, S(17),
                         app.alternar_panel_derecho,
                         tooltip="Ocultar «Ahora suena»" if app.panel_derecho_visible
                         else "Mostrar «Ahora suena» (Ctrl+J)",
                         activo=app.panel_derecho_visible)
        self._item_volumen = self._colocar(self._item_volumen, self.volumen, x_slider, cy, ancho_slider)
        self.volumen.establecer_valor(app.estado["volumen"])

    def _colocar(self, item, widget, x, y, ancho):
        if item is None:
            return self.create_window(x, y, window=widget, anchor="w", width=ancho, height=S(16),
                                      tags=("fijo",))
        self.coords(item, x, y)
        self.itemconfigure(item, width=ancho)
        return item

    def actualizar_tiempos(self) -> None:
        app = self.app
        actual = app.cancion_actual()
        if self.progreso.arrastrando:
            return
        if actual is None:
            self.itemconfigure("tiempo_actual", text="--:--")
            self.itemconfigure("tiempo_total", text="--:--")
            self.progreso.establecer_valor(0.0)
            self.progreso.configurar_interactivo(False)
            return
        posicion, duracion = app.estado["posicion"], actual["duracion"]
        self.itemconfigure("tiempo_actual", text=formatear_tiempo(posicion))
        self.itemconfigure("tiempo_total", text=formatear_tiempo(duracion))
        self.progreso.establecer_valor(posicion / duracion if duracion else 0.0)
        self.progreso.configurar_interactivo(app.puede_buscar())

    def mostrar_tiempo_provisional(self, segundos: float) -> None:
        self.itemconfigure("tiempo_actual", text=formatear_tiempo(segundos))


# ======================================================================
# 8. VENTANA PRINCIPAL (contrato con el backend)
# ======================================================================

class ReproductorUI(tk.Tk):
    """Ventana principal de CIRCULAR MUSIC.

    Métodos públicos (contrato con el backend):
        configurar_callbacks(callbacks: dict) -> None
        actualizar_estado(estado: dict) -> None
    """

    def __init__(self, preferencias=None):
        global _ESCALA, _FABRICA
        activar_alta_resolucion()
        super().__init__()
        _ESCALA = max(1.0, self.winfo_fpixels("1i") / 96.0)
        _FABRICA = self.fabrica = FabricaImagenes(self)

        self._hilo_tk = threading.get_ident()
        self._callbacks: dict[str, Callable] = {}
        self.estado = normalizar_estado(ESTADO_INICIAL)
        self._firma_canciones: tuple = ()
        self.indices: dict[int, int] = {}
        self.seleccion_id: int | None = None
        self.favoritos: set[int] = set()
        self.recientes: list[int] = []
        self.consulta_busqueda = ""
        self.filtro_favoritas = False
        self.esperando_backend = True
        self.prefs = cargar_preferencias()
        # Compatibilidad con las preferencias originales de ORBIT.
        if isinstance(preferencias, dict):
            if "panel_derecho" in preferencias:
                self.prefs["panel_derecho"] = bool(preferencias["panel_derecho"])
            if "barra_lateral" in preferencias:
                self.prefs["barra_contraida"] = not bool(preferencias["barra_lateral"])
        self.vista_actual = "inicio"
        self._historial = ["inicio"]
        self._posicion_historial = 0
        self._ultimo_mensaje_backend = ""
        self._cola_estados: queue.Queue = queue.Queue()
        self._cerrando = False
        self._fuentes: dict = {}
        self._lienzos: list[CanvasInteractivo] = []
        self._componentes: list = []
        self._id_animacion = None
        self._fase = 0.0
        self._volumen_previo = 0.75
        self.panel_derecho_visible = False

        self._configurar_ventana()
        self._elegir_familias()
        self._configurar_estilos_ttk()
        self.tooltips = GestorTooltips(self)
        self._construir_interfaz()
        self.menu = MenuContextual(self)
        self.notificador = Notificador(self, self.panel_centro)
        self._registrar_atajos()
        self._registrar_rueda()

        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)
        self.bind("<Configure>", self._al_redimensionar, add="+")
        self.bind_all("<ButtonPress-1>", self._al_clic_global, add="+")
        self._mostrar_vista("inicio")
        self._aplicar_estado(ESTADO_INICIAL, forzar=True)
        self._id_sondeo = self.after(INTERVALO_COLA_MS, self._procesar_cola_estados)
        self._programar_animacion()

    # ==================================================================
    # CONTRATO PÚBLICO
    # ==================================================================

    def configurar_callbacks(self, callbacks: dict) -> None:
        """Registra las funciones del backend (reemplaza las anteriores).

        Las claves desconocidas se ignoran con una advertencia y los valores
        ``None`` se tratan como callbacks no proporcionados.
        """
        if not isinstance(callbacks, dict):
            raise TypeError("configurar_callbacks espera un diccionario.")
        registrados = {}
        for nombre, funcion in callbacks.items():
            if nombre not in CALLBACKS_CONOCIDOS:
                warnings.warn(f"Callback desconocido ignorado: {nombre!r}", stacklevel=2)
                continue
            if funcion is None:
                continue
            if not callable(funcion):
                raise TypeError(f"El callback {nombre!r} no es invocable.")
            registrados[nombre] = funcion
        self._callbacks = registrados
        self._notificar({"callbacks"})

    def actualizar_estado(self, estado: dict) -> None:
        """Recibe el estado del backend y actualiza solo lo que cambió.

        Es seguro llamarlo desde cualquier hilo: fuera del hilo de Tkinter
        el estado se encola y se aplica en el hilo principal.
        """
        if self._cerrando:
            return
        if threading.get_ident() == self._hilo_tk:
            self._aplicar_estado_seguro(estado)
        else:
            self._cola_estados.put(copy.deepcopy(estado))

    # ==================================================================
    # CONSTRUCCIÓN
    # ==================================================================

    def _configurar_ventana(self) -> None:
        self.title("Circular Music")
        self.configure(bg=COLORES["fondo"])
        pantalla_ancho, pantalla_alto = self.winfo_screenwidth(), self.winfo_screenheight()
        ancho = min(S(1380), pantalla_ancho - S(40))
        alto = min(S(880), pantalla_alto - S(90))
        x = max(0, (pantalla_ancho - ancho) // 2)
        y = max(0, (pantalla_alto - alto) // 2 - S(16))
        self.geometry(f"{ancho}x{alto}+{x}+{y}")
        self.minsize(min(S(900), ancho), min(S(600), alto))

    def _elegir_familias(self) -> None:
        familias = set(tkfont.families(self))

        def primera(opciones, respaldo):
            return next((f for f in opciones if f in familias),
                        tkfont.nametofont(respaldo).actual("family"))

        self._familia_texto = primera(FUENTES_TEXTO, "TkDefaultFont")
        self._familia_titulo = primera(FUENTES_TITULO, "TkDefaultFont")
        self._familia_mono = primera(FUENTES_MONO, "TkFixedFont")

    def fuente(self, tamano: int, negrita: bool = False, display: bool = False,
               mono: bool = False) -> tkfont.Font:
        """Devuelve (y guarda) una fuente. Los tamaños están en puntos."""
        clave = (tamano, negrita, display, mono)
        if clave not in self._fuentes:
            familia = (self._familia_mono if mono else
                       self._familia_titulo if display else self._familia_texto)
            self._fuentes[clave] = tkfont.Font(root=self, family=familia, size=tamano,
                                               weight="bold" if negrita else "normal")
        return self._fuentes[clave]

    def _configurar_estilos_ttk(self) -> None:
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        for orientacion in ("Vertical", "Horizontal"):
            nombre = f"Fina.{orientacion}.TScrollbar"
            estilo.layout(nombre, [(f"{orientacion}.Scrollbar.trough", {
                "sticky": "nswe",
                "children": [(f"{orientacion}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})],
            })])
            estilo.configure(nombre, troughcolor=COLORES["panel"], background="#3A3D46",
                             bordercolor=COLORES["panel"], lightcolor="#3A3D46",
                             darkcolor="#3A3D46", arrowsize=S(8), gripcount=0, relief="flat")
            estilo.map(nombre, background=[("pressed", "#6A6E79"), ("active", "#555963")])

    def registrar_lienzo(self, lienzo: CanvasInteractivo) -> None:
        self._lienzos.append(lienzo)

    def _construir_interfaz(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.barra_superior = BarraSuperior(self, self)
        self.barra_superior.grid(row=0, column=0, sticky="ew")

        cuerpo = tk.Frame(self, bg=COLORES["fondo"])
        cuerpo.grid(row=1, column=0, sticky="nsew", padx=S(8))
        cuerpo.rowconfigure(0, weight=1)
        cuerpo.columnconfigure(1, weight=1)
        self.lateral = BarraLateral(cuerpo, self)
        self.lateral.grid(row=0, column=0, sticky="ns", padx=(0, S(8)))
        self.panel_centro = PanelRedondeado(cuerpo, COLORES["panel"], COLORES["fondo"], S(10))
        self.panel_centro.grid(row=0, column=1, sticky="nsew")
        self.panel_centro.rowconfigure(0, weight=1)
        self.panel_centro.columnconfigure(0, weight=1)
        self.panel_derecho = PanelDerecho(cuerpo, self)

        self.vistas = {
            "inicio": VistaInicio(self.panel_centro, self),
            "biblioteca": VistaBiblioteca(self.panel_centro, self),
            "estructura": VistaEstructura(self.panel_centro, self),
            "ajustes": VistaAjustes(self.panel_centro, self),
        }
        for vista in self.vistas.values():
            vista.grid(row=0, column=0, sticky="nsew")

        self.reproductor = BarraReproductor(self, self)
        self.reproductor.grid(row=2, column=0, sticky="ew")
        self._componentes = [self.lateral, *self.vistas.values(), self.panel_derecho,
                             self.reproductor]

    # ==================================================================
    # ESTADO
    # ==================================================================

    def _procesar_cola_estados(self) -> None:
        ultimo = None
        try:
            while True:
                ultimo = self._cola_estados.get_nowait()
        except queue.Empty:
            pass
        if ultimo is not None:
            self._aplicar_estado_seguro(ultimo)
        if not self._cerrando:
            self._id_sondeo = self.after(INTERVALO_COLA_MS, self._procesar_cola_estados)

    def _aplicar_estado_seguro(self, estado) -> None:
        try:
            self._aplicar_estado(estado)
        except Exception as error:  # noqa: BLE001 - la interfaz debe sobrevivir
            traceback.print_exc()
            self.notificar(f"Estado inválido recibido: {error}", "error")

    def _aplicar_estado(self, estado: dict, forzar: bool = False) -> None:
        nuevo = normalizar_estado(estado)
        anterior = self.estado
        firma = tuple((c["id"], c["titulo"], c["artista"], c["duracion"]) for c in nuevo["canciones"])
        cambios = set()
        if forzar or firma != self._firma_canciones:
            cambios.add("lista")
        if forzar or nuevo["actual_id"] != anterior["actual_id"]:
            cambios.add("actual")
        if forzar or nuevo["reproduciendo"] != anterior["reproduciendo"]:
            cambios.add("reproduccion")
        if forzar or abs(nuevo["posicion"] - anterior["posicion"]) > 1e-6:
            cambios.add("posicion")
        if forzar or abs(nuevo["volumen"] - anterior["volumen"]) > 1e-6:
            cambios.add("volumen")
        if forzar or nuevo["aleatorio"] != anterior.get("aleatorio", False) or nuevo["repetir_uno"] != anterior.get("repetir_uno", False):
            cambios.add("modos")
        if not forzar and self.esperando_backend:
            self.esperando_backend = False
            cambios |= {"esperando", "lista", "actual"}

        self.estado = nuevo
        self._firma_canciones = firma
        self.indices = {c["id"]: i for i, c in enumerate(nuevo["canciones"])}
        if self.seleccion_id is not None and self.seleccion_id not in self.indices:
            self.seleccion_id = None
            cambios.add("seleccion")
        # El backend es la fuente de verdad de favoritos y recientes persistentes.
        # En el modo demostración standalone, la interfaz conserva su propio estado.
        if nuevo["favoritos"] is not None:
            rutas_fav = {os.path.normcase(os.path.abspath(r)) for r in nuevo["favoritos"]}
            sincronizados = {c["id"] for c in nuevo["canciones"]
                             if c["ruta"] and os.path.normcase(os.path.abspath(c["ruta"])) in rutas_fav}
            if sincronizados != self.favoritos:
                self.favoritos = sincronizados
                cambios.add("favoritos")
        elif self.favoritos - set(self.indices):
            self.favoritos &= set(self.indices)
            cambios.add("favoritos")
        if nuevo["recientes"] is not None:
            ruta_ids = {os.path.normcase(os.path.abspath(c["ruta"])): c["id"]
                        for c in nuevo["canciones"] if c["ruta"]}
            sincronizados = []
            for ruta in nuevo["recientes"]:
                ident = ruta_ids.get(os.path.normcase(os.path.abspath(ruta)))
                if ident is not None and ident not in sincronizados:
                    sincronizados.append(ident)
            sincronizados = sincronizados[:MAX_RECIENTES]
            if sincronizados != self.recientes:
                self.recientes = sincronizados
                cambios.add("recientes")
        if nuevo["recientes"] is None and "actual" in cambios and nuevo["actual_id"] is not None and not forzar:
            if nuevo["actual_id"] in self.recientes:
                self.recientes.remove(nuevo["actual_id"])
            self.recientes.insert(0, nuevo["actual_id"])
            del self.recientes[MAX_RECIENTES:]
            cambios.add("recientes")
        if "lista" in cambios:
            self.recientes = [i for i in self.recientes if i in self.indices]
            cambios.add("recientes")

        if cambios:
            self._notificar(cambios)
        if cambios & {"actual", "lista"}:
            actual = self.cancion_actual()
            self.title(f"{actual['titulo']} — Circular Music" if actual else "Circular Music")
            self.actualizar_esquinas_centro()
        if not forzar and nuevo["mensaje"] and nuevo["mensaje"] != self._ultimo_mensaje_backend:
            self.notificar(nuevo["mensaje"], clasificar_mensaje(nuevo["mensaje"]))
        self._ultimo_mensaje_backend = nuevo["mensaje"]
        self._programar_animacion()

    def _notificar(self, cambios: set) -> None:
        for componente in self._componentes:
            componente.refrescar(cambios)
        if cambios & {"vista", "callbacks", "lista"}:
            self.barra_superior.redibujar()

    # ---------------- Consultas para los componentes ----------------

    def cancion_actual(self) -> dict | None:
        indice = self.indices.get(self.estado["actual_id"])
        return None if indice is None else self.estado["canciones"][indice]

    def es_favorita(self, id_cancion) -> bool:
        return id_cancion in self.favoritos

    def puede_buscar(self) -> bool:
        actual = self.cancion_actual()
        return (actual is not None and actual["duracion"] is not None
                and "buscar_posicion" in self._callbacks)

    def color_ambiente(self) -> str:
        """Color del degradado superior en Inicio (según la canción actual)."""
        actual = self.cancion_actual()
        if actual is None:
            return mezclar_color(COLORES["acento"], "#000000", 0.62)
        claro = PALETAS_PORTADA[actual["id"] % len(PALETAS_PORTADA)][0]
        return mezclar_color(claro, "#000000", 0.5)

    def texto_duracion_total(self) -> str:
        canciones = self.estado["canciones"]
        conocidas = [c["duracion"] for c in canciones if c["duracion"] is not None]
        texto = formatear_duracion_total(sum(conocidas))
        return texto + " +" if len(conocidas) < len(canciones) else texto

    def canciones_desde_actual(self) -> list[dict]:
        """Recorrido completo empezando en el nodo actual (orden «siguiente»)."""
        canciones = self.estado["canciones"]
        inicio = self.indices.get(self.estado["actual_id"], 0)
        return canciones[inicio:] + canciones[:inicio]

    def cola_siguientes(self, limite: int) -> list[dict]:
        canciones = self.estado["canciones"]
        inicio = self.indices.get(self.estado["actual_id"])
        if inicio is None:
            return []
        n = len(canciones)
        return [canciones[(inicio + k) % n] for k in range(1, min(limite, n - 1) + 1)]

    def canciones_recientes(self) -> list[dict]:
        canciones = self.estado["canciones"]
        return [canciones[self.indices[i]] for i in self.recientes if i in self.indices]

    def canciones_lateral(self) -> list[dict]:
        canciones = self.estado["canciones"]
        if self.filtro_favoritas:
            return [c for c in canciones if c["id"] in self.favoritos]
        return canciones

    def canciones_filtradas(self) -> list[dict]:
        canciones = self.canciones_lateral()
        consulta = normalizar_busqueda(self.consulta_busqueda)
        if not consulta:
            return canciones
        return [c for c in canciones
                if consulta in normalizar_busqueda(f"{c['titulo']} {c['artista']}")]

    # ==================================================================
    # NAVEGACIÓN, BÚSQUEDA Y DISEÑO
    # ==================================================================

    def navegar(self, vista: str, registrar: bool = True) -> None:
        if vista not in self.vistas or vista == self.vista_actual:
            return
        if registrar:
            del self._historial[self._posicion_historial + 1:]
            self._historial.append(vista)
            self._posicion_historial = len(self._historial) - 1
        self._mostrar_vista(vista)

    def _mostrar_vista(self, vista: str) -> None:
        self.vista_actual = vista
        self.vistas[vista].tkraise()
        self.panel_centro.levantar_esquinas()
        self.notificador.levantar()
        self.menu.ocultar()
        self.actualizar_esquinas_centro()
        self.lateral.refrescar({"vista"})
        self.barra_superior.redibujar()

    def puede_retroceder(self) -> bool:
        return self._posicion_historial > 0

    def puede_avanzar(self) -> bool:
        return self._posicion_historial < len(self._historial) - 1

    def retroceder(self) -> None:
        if self.puede_retroceder():
            self._posicion_historial -= 1
            self._mostrar_vista(self._historial[self._posicion_historial])

    def avanzar(self) -> None:
        if self.puede_avanzar():
            self._posicion_historial += 1
            self._mostrar_vista(self._historial[self._posicion_historial])

    def establecer_busqueda(self, texto: str) -> None:
        texto = texto.strip()
        if texto == self.consulta_busqueda:
            return
        self.consulta_busqueda = texto
        if texto and self.vista_actual != "biblioteca":
            self.navegar("biblioteca")
        self._notificar({"filtro"})

    def limpiar_busqueda(self) -> None:
        self.barra_superior.limpiar()
        self.establecer_busqueda("")

    def enfocar_busqueda(self) -> None:
        self.barra_superior.enfocar()

    def establecer_filtro_favoritas(self, activo: bool) -> None:
        if activo != self.filtro_favoritas:
            self.filtro_favoritas = activo
            self._notificar({"filtro"})

    def actualizar_esquinas_centro(self) -> None:
        """Las esquinas superiores del panel central siguen al degradado."""
        if not hasattr(self, "vistas"):
            return
        color = COLORES["panel"]
        if self.vista_actual == "inicio" and self.vistas["inicio"].en_la_cima():
            color = self.color_ambiente()
        elif self.vista_actual == "biblioteca":
            color = COLOR_BIBLIOTECA
        self.panel_centro.configurar_color_esquinas(color, ("nw", "ne"))

    def _al_redimensionar(self, evento) -> None:
        if evento.widget is self:
            self._aplicar_diseno()

    def _aplicar_diseno(self) -> None:
        ancho = self.winfo_width()
        if ancho <= 1:
            return
        self.lateral.establecer_contraida(self.prefs["barra_contraida"] or ancho < S(980))
        mostrar = self.prefs["panel_derecho"] and ancho >= S(1180)
        if mostrar != self.panel_derecho_visible:
            self.panel_derecho_visible = mostrar
            if mostrar:
                self.panel_derecho.grid(row=0, column=2, sticky="ns", padx=(S(8), 0))
                self.panel_derecho.refrescar({"lista"})
            else:
                self.panel_derecho.grid_remove()
            self.reproductor.redibujar()

    def establecer_preferencia(self, clave: str, valor) -> None:
        self.prefs[clave] = valor
        if "guardar_preferencia" in self._callbacks:
            nombre = "barra_lateral" if clave == "barra_contraida" else clave
            valor_backend = not valor if clave == "barra_contraida" else valor
            self._invocar("guardar_preferencia", nombre, valor_backend)
        if not guardar_preferencias(self.prefs):
            self.notificar("No se pudieron guardar las preferencias", "advertencia")
        self._aplicar_diseno()
        self._notificar({"prefs"})
        self._programar_animacion()

    def alternar_barra_lateral(self) -> None:
        self.establecer_preferencia("barra_contraida", not self.lateral.contraida)

    def alternar_panel_derecho(self) -> None:
        if not self.panel_derecho_visible and self.winfo_width() < S(1180):
            self.notificar("Agranda la ventana para ver el panel «Ahora suena»", "advertencia")
        self.establecer_preferencia("panel_derecho", not self.panel_derecho_visible)

    # ==================================================================
    # ACCIONES DEL USUARIO -> CALLBACKS DEL BACKEND
    # ==================================================================

    def _invocar(self, nombre: str, *argumentos) -> bool:
        """Llama a un callback del backend sin que un error cierre la ventana."""
        funcion = self._callbacks.get(nombre)
        if funcion is None:
            self.notificar(f"Acción no disponible: el backend no configuró «{nombre}»",
                           "advertencia")
            return False
        try:
            funcion(*argumentos)
        except Exception as error:  # noqa: BLE001 - la interfaz debe sobrevivir
            traceback.print_exc()
            self.notificar(f"Error en «{nombre}»: {error}", "error")
            return False
        return True

    def accion_agregar(self) -> None:
        if "agregar_archivos" not in self._callbacks:
            self._invocar("agregar_archivos")
            return
        rutas = filedialog.askopenfilenames(parent=self, title="Agregar canciones",
                                            filetypes=TIPOS_AUDIO)
        if isinstance(rutas, str):
            rutas = self.tk.splitlist(rutas)
        if rutas:
            self._invocar("agregar_archivos", list(rutas))

    def eliminar_cancion(self, id_cancion: int) -> None:
        if id_cancion in self.indices:
            self._invocar("eliminar_cancion", id_cancion)

    def eliminar_seleccion(self) -> None:
        if self.seleccion_id is None:
            if self.estado["canciones"]:
                self.notificar("Selecciona una canción para eliminarla", "advertencia")
            return
        self.eliminar_cancion(self.seleccion_id)

    def accion_alternar(self) -> None:
        if self.estado["canciones"]:
            self._invocar("alternar_reproduccion")

    def accion_reproducir_principal(self) -> None:
        """Botón grande de Inicio: si no hay canción actual, empieza por la cabeza."""
        if self.cancion_actual() is None and self.estado["canciones"]:
            self.activar_cancion(self.estado["canciones"][0]["id"])
        else:
            self.accion_alternar()

    def accion_siguiente(self) -> None:
        if self.estado["canciones"]:
            self._invocar("siguiente")

    def accion_anterior(self) -> None:
        if self.estado["canciones"]:
            self._invocar("anterior")

    def seleccionar(self, id_cancion: int) -> None:
        """Selección local (no cambia la reproducción)."""
        if id_cancion in self.indices and id_cancion != self.seleccion_id:
            self.seleccion_id = id_cancion
            self._notificar({"seleccion"})

    def activar_cancion(self, id_cancion: int) -> None:
        """Pide al backend que la canción sea la actual (callback seleccionar_cancion)."""
        self.seleccionar(id_cancion)
        self._invocar("seleccionar_cancion", id_cancion)

    def alternar_favorito(self, id_cancion: int) -> None:
        if id_cancion not in self.indices:
            return
        if "alternar_favorito" in self._callbacks:
            self._invocar("alternar_favorito", id_cancion)
            return  # Backend guarda en JSON y enviará el nuevo estado.
        cancion = self.estado["canciones"][self.indices[id_cancion]]
        if id_cancion in self.favoritos:
            self.favoritos.discard(id_cancion)
            self.notificar(f"Se quitó «{cancion['titulo']}» de favoritas", "info")
        else:
            self.favoritos.add(id_cancion)
            self.notificar(f"«{cancion['titulo']}» se agregó a favoritas", "exito")
        self._notificar({"favoritos"})

    def alternar_silencio(self) -> None:
        if self.estado["volumen"] > 0:
            self._volumen_previo = self.estado["volumen"]
            self._invocar("cambiar_volumen", 0.0)
        else:
            self._invocar("cambiar_volumen", self._volumen_previo or 0.75)

    def mostrar_menu_cancion(self, id_cancion: int, x_root: int, y_root: int) -> None:
        if id_cancion not in self.indices:
            return
        self.seleccionar(id_cancion)
        es_actual = id_cancion == self.estado["actual_id"]
        sonando = es_actual and self.estado["reproduciendo"]
        favorita = self.es_favorita(id_cancion)
        if es_actual:
            primera = ("Pausar" if sonando else "Reanudar", self.accion_alternar, False)
        else:
            primera = ("Reproducir", lambda: self.activar_cancion(id_cancion), False)

        def ver_en_estructura():
            self.navegar("estructura")
            self.vistas["estructura"].visualizador.centrar_en(id_cancion)

        self.menu.mostrar([
            primera,
            ("Quitar de favoritas" if favorita else "Agregar a favoritas",
             lambda: self.alternar_favorito(id_cancion), False),
            ("Ver nodo en la estructura", ver_en_estructura, False),
            None,
            ("Eliminar de la lista", lambda: self.eliminar_cancion(id_cancion), True),
        ], x_root, y_root)

    def _mover_seleccion(self, paso: int) -> None:
        if self.vista_actual == "biblioteca":
            elementos = self.canciones_filtradas()
        else:
            elementos = self.canciones_lateral()
        if not elementos:
            return
        ids = [c["id"] for c in elementos]
        if self.seleccion_id in ids:
            indice = int(limitar(ids.index(self.seleccion_id) + paso, 0, len(ids) - 1))
        else:
            indice = ids.index(self.estado["actual_id"]) if self.estado["actual_id"] in ids else 0
        self.seleccionar(ids[indice])
        self.vistas["biblioteca"].tabla.asegurar_visible(ids[indice])
        self.lateral.lista.asegurar_visible(ids[indice])

    # ---------------- Barras deslizantes ----------------

    def al_mover_progreso(self, fraccion: float) -> None:
        actual = self.cancion_actual()
        if actual and actual["duracion"]:
            self.reproductor.mostrar_tiempo_provisional(fraccion * actual["duracion"])

    def al_soltar_progreso(self, fraccion: float) -> None:
        actual = self.cancion_actual()
        if actual and actual["duracion"]:
            self._invocar("buscar_posicion", fraccion * actual["duracion"])

    def al_mover_volumen(self, valor: float) -> None:
        if "cambiar_volumen" in self._callbacks:
            self._invocar("cambiar_volumen", round(valor, 3))

    def al_soltar_volumen(self, valor: float) -> None:
        if "cambiar_volumen" not in self._callbacks:
            self._invocar("cambiar_volumen", valor)
            self.reproductor.volumen.establecer_valor(self.estado["volumen"])  # no simula
        self.reproductor.redibujar()

    # ==================================================================
    # NOTIFICACIONES, ANIMACIONES Y EVENTOS GLOBALES
    # ==================================================================

    def notificar(self, texto: str, tipo: str = "info") -> None:
        if hasattr(self, "notificador"):
            self.notificador.mostrar(texto, tipo)

    def animar(self, duracion_ms: int, al_paso: Callable[[float], None],
               al_terminar: Callable | None = None) -> None:
        """Animación con suavizado. Si están desactivadas, salta al final."""
        if not self.prefs["animaciones"]:
            al_paso(1.0)
            if al_terminar:
                al_terminar()
            return
        inicio = time.perf_counter()

        def tic():
            progreso = min(1.0, (time.perf_counter() - inicio) * 1000 / duracion_ms)
            try:
                al_paso(1 - (1 - progreso) ** 3)
            except tk.TclError:
                return
            if progreso < 1.0:
                self.after(16, tic)
            elif al_terminar:
                al_terminar()

        tic()

    def _programar_animacion(self) -> None:
        if self._id_animacion is None and not self._cerrando:
            self._id_animacion = self.after(90, self._tic_animacion)

    def _tic_animacion(self) -> None:
        """Pulso de los skeletons y ecualizadores animados."""
        self._id_animacion = None
        activo = False
        self._fase += 0.5
        animaciones = self.prefs["animaciones"]
        if self.esperando_backend or self.fabrica.hay_trabajo():
            color = (mezclar_color(COLORES["esqueleto"], COLORES["esqueleto_brillo"],
                                   0.5 + 0.5 * math.sin(self._fase * 0.6))
                     if animaciones else COLORES["esqueleto"])
            for lienzo in self._lienzos:
                lienzo.itemconfigure("esqueleto", fill=color)
            activo = True
        if self.estado["reproduciendo"] and animaciones:
            for lienzo in self._lienzos:
                lienzo.animar_ecualizador(self._fase)
            activo = True
        if activo:
            self._id_animacion = self.after(90, self._tic_animacion)

    def _registrar_rueda(self) -> None:
        """Una sola rueda del mouse para toda la app: busca el widget bajo el cursor."""
        def rueda(evento, horizontal=False):
            if getattr(evento, "num", None) == 4:
                pasos = -1
            elif getattr(evento, "num", None) == 5:
                pasos = 1
            else:
                pasos = -1 if evento.delta > 0 else 1
            try:
                widget = self.winfo_containing(evento.x_root, evento.y_root)
            except (KeyError, tk.TclError):
                return
            atributo = "_al_rueda_h" if horizontal else "_al_rueda"
            while widget is not None:
                funcion = getattr(widget, atributo, None)
                if funcion is not None:
                    funcion(pasos)
                    break
                widget = getattr(widget, "master", None)
            self.menu.ocultar()
            self.tooltips.ocultar()

        self.bind_all("<MouseWheel>", rueda)
        self.bind_all("<Shift-MouseWheel>", lambda e: rueda(e, True))
        self.bind_all("<Button-4>", rueda)
        self.bind_all("<Button-5>", rueda)
        self.bind_all("<Shift-Button-4>", lambda e: rueda(e, True))
        self.bind_all("<Shift-Button-5>", lambda e: rueda(e, True))

    def _al_clic_global(self, evento) -> None:
        if self.menu.visible and not self.menu.contiene(evento.widget):
            self.menu.ocultar()
        if evento.widget is not self.barra_superior.entrada and \
                isinstance(self.focus_get(), tk.Entry):
            self.focus_set()

    def _registrar_atajos(self) -> None:
        def atajo(funcion, en_texto=False):
            def manejador(_evento):
                if not en_texto and isinstance(self.focus_get(), tk.Entry):
                    return None
                funcion()
                return "break"
            return manejador

        def escape():
            if self.menu.visible:
                self.menu.ocultar()
            elif self.consulta_busqueda or isinstance(self.focus_get(), tk.Entry):
                self.limpiar_busqueda()
                self.focus_set()

        enlaces = {
            "<space>": atajo(self.accion_alternar),
            "<Control-Right>": atajo(self.accion_siguiente),
            "<Control-Left>": atajo(self.accion_anterior),
            "<Up>": atajo(lambda: self._mover_seleccion(-1)),
            "<Down>": atajo(lambda: self._mover_seleccion(1)),
            "<Return>": atajo(lambda: self.seleccion_id is not None
                              and self.activar_cancion(self.seleccion_id)),
            "<Delete>": atajo(self.eliminar_seleccion),
            "<Control-o>": atajo(self.accion_agregar, True),
            "<Control-f>": atajo(self.enfocar_busqueda, True),
            "<Control-k>": atajo(self.enfocar_busqueda, True),
            "<Escape>": atajo(escape, True),
            "<Alt-Left>": atajo(self.retroceder, True),
            "<Alt-Right>": atajo(self.avanzar, True),
            "<Control-Key-1>": atajo(lambda: self.navegar("inicio"), True),
            "<Control-Key-2>": atajo(lambda: self.navegar("biblioteca"), True),
            "<Control-Key-3>": atajo(lambda: self.navegar("estructura"), True),
            "<Control-comma>": atajo(lambda: self.navegar("ajustes"), True),
            "<Control-b>": atajo(self.alternar_barra_lateral, True),
            "<Control-j>": atajo(self.alternar_panel_derecho, True),
        }
        for secuencia, manejador in enlaces.items():
            self.bind(secuencia, manejador)
            if secuencia.startswith("<Control-") and secuencia[-2].isalpha() and secuencia[-3] == "-":
                self.bind(secuencia[:-2] + secuencia[-2].upper() + ">", manejador)

    def _al_cerrar(self) -> None:
        if self._cerrando:
            return
        self._cerrando = True
        for identificador in (self._id_sondeo, self._id_animacion):
            if identificador is not None:
                try:
                    self.after_cancel(identificador)
                except (tk.TclError, ValueError):
                    pass
        funcion = self._callbacks.get("cerrar")
        try:
            if funcion is not None:
                funcion()   # el backend libera pygame
        except Exception:  # noqa: BLE001 - cerrar siempre debe funcionar
            traceback.print_exc()
        finally:
            try:
                self.destroy()
            except tk.TclError:
                pass


# ======================================================================
# 9. MODO DEMOSTRACIÓN (solo al ejecutar: python interfaz.py)
# ======================================================================

def _ejecutar_demostracion(argumentos: list[str]) -> None:
    """Abre la interfaz con un backend SIMULADO para revisar el diseño.

    IMPORTANTE: el diccionario ``simulado`` usa una lista normal de Python
    solo para imitar las respuestas del backend. NO es la lista doblemente
    enlazada circular del proyecto (esa vive en lista_circular.py).

    Opciones:  --vacia  |  --una  |  --muchas   (por defecto: 3 canciones)
    """
    ejemplos = [
        {"id": 1, "titulo": "Aurora Boreal", "artista": "Nébula", "duracion": 180.0},
        {"id": 2, "titulo": "Ecos del Pacífico", "artista": "Marea Alta", "duracion": 210.0},
        {"id": 3, "titulo": "Nodos en Órbita", "artista": "Los Punteros", "duracion": 195.0},
    ]
    if "--vacia" in argumentos:
        ejemplos = []
    elif "--una" in argumentos:
        ejemplos = ejemplos[:1]
    elif "--muchas" in argumentos:
        nombres = ["Puntero Nulo", "Recorrido Infinito", "Cabeza y Cola", "Memoria Dinámica",
                   "Inserción al Final", "Doble Enlace", "Ciclo Perfecto", "Nodo Centinela",
                   "Complejidad O(1)", "Referencia Perdida", "Vuelta Completa", "Pila de Llamadas"]
        artistas = ["Los Punteros", "Nébula", "Marea Alta", "Big O", "Heap Sort", "Árbol Binario"]
        for i in range(4, 25):
            ejemplos.append({"id": i, "titulo": f"{nombres[i % len(nombres)]} (versión {i})",
                             "artista": artistas[i % len(artistas)], "duracion": 150.0 + i * 7})

    simulado = {
        "canciones": ejemplos,
        "actual_id": ejemplos[0]["id"] if ejemplos else None,
        "reproduciendo": False,
        "posicion": 0.0,
        "volumen": 0.75,
        "mensaje": "Modo demostración: backend simulado, sin audio real",
    }
    proximo_id = [max((c["id"] for c in ejemplos), default=0) + 1]
    ui = ReproductorUI()

    def publicar(mensaje: str | None = None) -> None:
        if mensaje is not None:
            simulado["mensaje"] = mensaje
        ui.actualizar_estado(simulado)

    def indice_de(id_cancion):
        return next((i for i, c in enumerate(simulado["canciones"]) if c["id"] == id_cancion), None)

    def mover(paso: int) -> None:
        canciones = simulado["canciones"]
        if not canciones:
            return
        indice = indice_de(simulado["actual_id"])
        indice = 0 if indice is None else (indice + paso) % len(canciones)
        simulado["actual_id"] = canciones[indice]["id"]
        simulado["posicion"] = 0.0
        publicar(f"Ahora: {canciones[indice]['titulo']}")

    def agregar_archivos(rutas: list[str]) -> None:
        for ruta in rutas:
            simulado["canciones"].append({
                "id": proximo_id[0],
                "titulo": os.path.splitext(os.path.basename(ruta))[0],
                "artista": "Archivo local",
                "duracion": None,   # la demo no lee audio: duración desconocida
            })
            proximo_id[0] += 1
        if simulado["actual_id"] is None and simulado["canciones"]:
            simulado["actual_id"] = simulado["canciones"][0]["id"]
        publicar(f"{len(rutas)} archivo(s) agregado(s) (simulado)")

    def eliminar_cancion(id_cancion: int) -> None:
        indice = indice_de(id_cancion)
        if indice is None:
            return
        eliminada = simulado["canciones"].pop(indice)
        if simulado["actual_id"] == id_cancion:
            restantes = simulado["canciones"]
            simulado["actual_id"] = restantes[indice % len(restantes)]["id"] if restantes else None
            simulado["posicion"] = 0.0
            if not restantes:
                simulado["reproduciendo"] = False
        publicar(f"Eliminada: {eliminada['titulo']}")

    def seleccionar_cancion(id_cancion: int) -> None:
        simulado["actual_id"] = id_cancion
        simulado["posicion"] = 0.0
        simulado["reproduciendo"] = True
        publicar("Reproduciendo (simulado)")

    def alternar_reproduccion() -> None:
        if simulado["actual_id"] is None:
            return
        simulado["reproduciendo"] = not simulado["reproduciendo"]
        publicar("Reproduciendo (simulado)" if simulado["reproduciendo"] else "En pausa")

    def cambiar_volumen(volumen: float) -> None:
        simulado["volumen"] = volumen
        publicar()

    def buscar_posicion(segundos: float) -> None:
        simulado["posicion"] = segundos
        publicar()

    def cerrar() -> None:
        print("[demo] cerrar(): aquí el backend liberaría los recursos de Pygame")

    def avanzar_reloj() -> None:
        """Simula el avance del tiempo mientras 'suena' una canción."""
        if simulado["reproduciendo"]:
            indice = indice_de(simulado["actual_id"])
            if indice is not None:
                simulado["posicion"] += 0.25
                duracion = simulado["canciones"][indice]["duracion"]
                if duracion and simulado["posicion"] >= duracion:
                    mover(1)
                else:
                    publicar()
        ui.after(250, avanzar_reloj)

    ui.configurar_callbacks({
        "agregar_archivos": agregar_archivos,
        "eliminar_cancion": eliminar_cancion,
        "seleccionar_cancion": seleccionar_cancion,
        "alternar_reproduccion": alternar_reproduccion,
        "siguiente": lambda: mover(1),
        "anterior": lambda: mover(-1),
        "cambiar_volumen": cambiar_volumen,
        "buscar_posicion": buscar_posicion,
        "cerrar": cerrar,
    })
    # Pequeña espera para mostrar el estado de carga (skeleton) del inicio.
    ui.after(900, publicar)
    ui.after(900, avanzar_reloj)
    ui.mainloop()


if __name__ == "__main__":
    _ejecutar_demostracion(sys.argv[1:])
