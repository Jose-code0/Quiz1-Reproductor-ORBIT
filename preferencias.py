"""Preferencias locales: independientes de la lista enlazada del Quiz."""
import json
import os
from pathlib import Path


def ruta_preferencias():
    raiz = os.environ.get('APPDATA') if os.name == 'nt' else None
    base = Path(raiz) if raiz else Path.home() / '.config'
    return base / 'OrbitMusicQuiz' / 'preferencias.json'


class Preferencias:
    POR_DEFECTO = {
        'favoritos': [], 'recientes': [], 'volumen': .75,
        'panel_derecho': True, 'barra_lateral': True,
        'aleatorio': False, 'repetir_uno': False,
    }

    def __init__(self, ruta=None):
        self.ruta = Path(ruta) if ruta else ruta_preferencias()
        self.datos = dict(self.POR_DEFECTO)
        try:
            contenido = json.loads(self.ruta.read_text(encoding='utf-8'))
            if isinstance(contenido, dict):
                for nombre in self.POR_DEFECTO:
                    if nombre in contenido and isinstance(contenido[nombre], type(self.POR_DEFECTO[nombre])):
                        self.datos[nombre] = contenido[nombre]
        except (OSError, ValueError, TypeError):
            pass
        self.datos['volumen'] = max(0, min(1, float(self.datos['volumen'])))
        self.datos['favoritos'] = [p for p in self.datos['favoritos'] if isinstance(p, str)][:2000]
        self.datos['recientes'] = [p for p in self.datos['recientes'] if isinstance(p, str)][:30]

    def guardar(self):
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.ruta.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.datos, indent=2, ensure_ascii=False), encoding='utf-8')
            tmp.replace(self.ruta)
        except OSError:
            pass  # La aplicación puede seguir aunque preferencias no sean escribibles.
