"""Controlador Circular Music: modelo doblemente circular + audio + vista."""
import random
from pathlib import Path

from lista_circular import ListaCircularDoble
from audio import ReproductorAudio
from preferencias import Preferencias
from interfaz import ReproductorUI

try:
    from mutagen import File as ArchivoMutagen
except ImportError:
    ArchivoMutagen = None


class Aplicacion:
    def __init__(self):
        self.lista = ListaCircularDoble()
        self.prefs = Preferencias()
        self.audio = ReproductorAudio()
        self.audio.cambiar_volumen(self.prefs.datos['volumen'])
        self.ui = ReproductorUI(preferencias=self.prefs.datos)
        self.mensaje = 'Tu música, lista para explorar.'
        self._cerrado = False
        self._historial_aleatorio = []
        self._ultimo_estado = None
        self._version_cache = None
        self._cache_canciones = []
        self._temporizador = None
        self._guardado_pendiente = None
        self.ui.configurar_callbacks({
            'agregar_archivos': self.agregar_archivos,
            'eliminar_cancion': self.eliminar_cancion,
            'seleccionar_cancion': self.seleccionar_cancion,
            'alternar_reproduccion': self.alternar_reproduccion,
            'siguiente': self.siguiente,
            'anterior': self.anterior,
            'cambiar_volumen': self.cambiar_volumen,
            'buscar_posicion': self.buscar_posicion,
            'alternar_favorito': self.alternar_favorito,
            'alternar_aleatorio': self.alternar_aleatorio,
            'alternar_repeticion': self.alternar_repeticion,
            'guardar_preferencia': self.guardar_preferencia,
            'cerrar': self.cerrar,
        })
        self._cargar_musica_de_ejemplo()
        self._actualizar_interfaz()
        self._temporizador = self.ui.after(400, self._comprobar_reproduccion)

    def _cargar_musica_de_ejemplo(self):
        """Carga una única vez los ficheros locales, nunca desde el temporizador."""
        if getattr(self, '_ejemplos_cargados', False):
            return
        self._ejemplos_cargados = True
        carpeta = Path(__file__).resolve().parent / 'musica'
        if not carpeta.is_dir():
            return
        archivos = sorted((p for p in carpeta.iterdir()
                           if p.is_file() and p.suffix.lower() in ('.mp3', '.wav', '.ogg')),
                          key=lambda p: p.name.casefold())
        if archivos:
            self.agregar_archivos([str(p) for p in archivos])
            self.mensaje = f'{len(archivos)} canciones locales listas para escuchar.'

    def _leer_metadatos(self, ruta):
        titulo, artista, album, duracion = Path(ruta).stem, 'Artista desconocido', 'Sin álbum', None
        if ArchivoMutagen is not None:
            try:
                archivo = ArchivoMutagen(ruta, easy=True)
                if archivo is not None:
                    titulo = (archivo.get('title', [titulo])[0] or titulo)
                    artista = (archivo.get('artist', [artista])[0] or artista)
                    album = (archivo.get('album', [album])[0] or album)
                    info = getattr(archivo, 'info', None)
                    if info is not None:
                        duracion = float(info.length)
            except Exception:
                pass
        return titulo, artista, duracion, album

    def agregar_archivos(self, rutas):
        agregadas = rechazadas = 0
        for ruta in rutas:
            archivo = Path(ruta)
            if archivo.suffix.lower() not in ('.mp3', '.wav', '.ogg') or not archivo.is_file():
                rechazadas += 1
                continue
            datos = self._leer_metadatos(str(archivo))
            titulo, artista, duracion = datos[:3]
            album = datos[3] if len(datos) > 3 else 'Sin álbum'
            self.lista.agregar(str(archivo), titulo, artista, duracion, album)
            agregadas += 1
        self.mensaje = f'{agregadas} canción(es) añadida(s) a la biblioteca'
        if rechazadas:
            self.mensaje += f' · {rechazadas} no válidas'
        self._actualizar_interfaz()

    def _anotar_reciente(self):
        if not hasattr(self, 'prefs') or not self.lista.actual:
            return
        ruta = str(Path(self.lista.actual.ruta).resolve())
        anteriores = [r for r in self.prefs.datos['recientes'] if r != ruta]
        self.prefs.datos['recientes'] = [ruta] + anteriores[:29]
        self._programar_guardado()

    def _iniciar_actual(self):
        nodo = self.lista.actual
        if nodo is None:
            self.audio.detener()
            self.mensaje = 'Biblioteca vacía: añade música para comenzar.'
            return
        try:
            self.audio.reproducir(nodo.ruta)
            self.mensaje = f'Reproduciendo · {nodo.titulo}'
            self._anotar_reciente()
        except Exception as error:
            self.audio.detener()
            self.mensaje = f'No se pudo reproducir el archivo: {error}'

    def seleccionar_cancion(self, identificador):
        if self.lista.seleccionar(identificador):
            self._historial_aleatorio = []
            self._iniciar_actual()
        else:
            self.mensaje = 'No se encontró la canción seleccionada.'
        self._actualizar_interfaz()

    def eliminar_cancion(self, identificador):
        era_actual = self.lista.actual is not None and self.lista.actual.id == identificador
        estaba_reproduciendo = self.audio.reproduciendo
        if not self.lista.eliminar(identificador):
            self.mensaje = 'No se encontró la canción para eliminar.'
        elif era_actual:
            self.audio.detener()
            if estaba_reproduciendo and self.lista.actual:
                self._iniciar_actual()
            else:
                self.mensaje = 'Canción eliminada.'
        else:
            self.mensaje = 'Canción eliminada.'
        self._actualizar_interfaz()

    def alternar_reproduccion(self):
        if self.lista.actual is None:
            self.mensaje = 'Añade una canción para comenzar.'
        elif self.audio.pausado:
            self.audio.reanudar()
            self.mensaje = 'Reproducción reanudada.'
        elif self.audio.reproduciendo:
            self.audio.pausar()
            self.mensaje = 'En pausa.'
        else:
            self._iniciar_actual()
        self._actualizar_interfaz()

    def _avanzar(self):
        if not self.lista.actual:
            return None
        if not getattr(self, 'prefs', None) or not self.prefs.datos['aleatorio'] or self.lista.cantidad < 2:
            return self.lista.siguiente()
        actual = self.lista.actual
        objetivo = random.randrange(self.lista.cantidad - 1)
        if objetivo >= self._indice_actual():
            objetivo += 1
        nodo = self.lista.primero
        for _ in range(objetivo):
            nodo = nodo.siguiente
        self._historial_aleatorio.append(actual.id)
        self._historial_aleatorio = self._historial_aleatorio[-100:]
        self.lista.actual = nodo
        return nodo

    def _indice_actual(self):
        nodo = self.lista.primero
        for i in range(self.lista.cantidad):
            if nodo is self.lista.actual:
                return i
            nodo = nodo.siguiente
        return 0

    def siguiente(self):
        if self._avanzar():
            self._iniciar_actual()
        else:
            self.mensaje = 'Tu biblioteca está vacía.'
        self._actualizar_interfaz()

    def anterior(self):
        if getattr(self, 'prefs', None) and self.prefs.datos['aleatorio'] and self._historial_aleatorio:
            while self._historial_aleatorio:
                if self.lista.seleccionar(self._historial_aleatorio.pop()):
                    break
            else:
                self.lista.anterior()
        else:
            self.lista.anterior()
        if self.lista.actual:
            self._iniciar_actual()
        else:
            self.mensaje = 'Tu biblioteca está vacía.'
        self._actualizar_interfaz()

    def cambiar_volumen(self, volumen):
        self.audio.cambiar_volumen(volumen)
        if hasattr(self, 'prefs'):
            self.prefs.datos['volumen'] = self.audio.volumen
            self._programar_guardado()
        self._actualizar_interfaz()

    def buscar_posicion(self, segundos):
        nodo = self.lista.actual
        if nodo is None or nodo.duracion is None:
            self.mensaje = 'No hay duración disponible para buscar.'
        else:
            try:
                self.audio.buscar(max(0, min(float(segundos), nodo.duracion - .15)))
                self.mensaje = 'Posición de reproducción actualizada.'
            except Exception as error:
                self.mensaje = f'No se puede adelantar este archivo: {error}'
        self._actualizar_interfaz()

    def alternar_favorito(self, identificador):
        nodo = self.lista.buscar(identificador)
        if nodo is None:
            return
        ruta = str(Path(nodo.ruta).resolve())
        favoritos = self.prefs.datos['favoritos']
        if ruta in favoritos:
            favoritos.remove(ruta)
            self.mensaje = 'Eliminada de favoritos.'
        else:
            favoritos.append(ruta)
            self.mensaje = 'Guardada en favoritos.'
        self._programar_guardado()
        self._actualizar_interfaz()

    def alternar_aleatorio(self):
        self.prefs.datos['aleatorio'] = not self.prefs.datos['aleatorio']
        self._historial_aleatorio = []
        self.mensaje = 'Orden aleatorio activado.' if self.prefs.datos['aleatorio'] else 'Orden circular restaurado.'
        self._programar_guardado()
        self._actualizar_interfaz()

    def alternar_repeticion(self):
        self.prefs.datos['repetir_uno'] = not self.prefs.datos['repetir_uno']
        self.mensaje = 'Repetir una canción.' if self.prefs.datos['repetir_uno'] else 'Repetir todo (lista circular).'
        self._programar_guardado()
        self._actualizar_interfaz()

    def guardar_preferencia(self, clave, valor):
        if clave in ('panel_derecho', 'barra_lateral'):
            self.prefs.datos[clave] = bool(valor)
            self._programar_guardado()

    def _programar_guardado(self):
        if not hasattr(self, 'prefs') or getattr(self, '_cerrado', False):
            return
        pendiente = getattr(self, '_guardado_pendiente', None)
        if pendiente:
            self.ui.after_cancel(pendiente)
        self._guardado_pendiente = self.ui.after(600, self._guardar)

    def _guardar(self):
        self._guardado_pendiente = None
        self.prefs.guardar()

    def _actualizar_interfaz(self):
        if self._cerrado:
            return
        actual = self.lista.actual
        posicion = self.audio.posicion()
        if actual is not None and actual.duracion is not None:
            posicion = min(posicion, actual.duracion)
        pref = getattr(self, 'prefs', None)
        version = getattr(self.lista, 'version', None)
        if version != getattr(self, '_version_cache', None):
            self._cache_canciones = self.lista.obtener_canciones()
            self._version_cache = version
        estado = {
            'canciones': self._cache_canciones,
            'actual_id': actual.id if actual else None,
            'reproduciendo': self.audio.reproduciendo,
            'pausado': self.audio.pausado,
            'posicion': posicion,
            'volumen': self.audio.volumen,
            'mensaje': self.mensaje,
            'favoritos': pref.datos['favoritos'][:] if pref else [],
            'recientes': pref.datos['recientes'][:] if pref else [],
            'aleatorio': pref.datos['aleatorio'] if pref else False,
            'repetir_uno': pref.datos['repetir_uno'] if pref else False,
        }
        self.ui.actualizar_estado(estado)

    def _comprobar_reproduccion(self):
        if self._cerrado:
            return
        if self.audio.ha_terminado():
            if getattr(self, 'prefs', None) and self.prefs.datos['repetir_uno']:
                self._iniciar_actual()
            elif self._avanzar():
                self._iniciar_actual()
        # El temporizador NO carga canciones ni duplica nodos.
        self._actualizar_interfaz()
        self._temporizador = self.ui.after(400, self._comprobar_reproduccion)

    def cerrar(self):
        self._cerrado = True
        if getattr(self, '_temporizador', None):
            self.ui.after_cancel(self._temporizador)
        if getattr(self, '_guardado_pendiente', None):
            self.ui.after_cancel(self._guardado_pendiente)
        if hasattr(self, 'prefs'):
            self.prefs.guardar()
        self.audio.cerrar()
        self.ui.destroy()

    def ejecutar(self):
        self.ui.mainloop()


if __name__ == '__main__':
    # Escalado correcto en Windows cuando el sistema usa pantallas HiDPI.
    import sys
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError, ValueError):
            pass
    Aplicacion().ejecutar()
