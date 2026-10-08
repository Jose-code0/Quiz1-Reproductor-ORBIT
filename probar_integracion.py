"""Pruebas de regresión: el temporizador no debe agregar canciones.

Ejecutar: py probar_integracion.py
No abre ventanas ni reproduce audio.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from lista_circular import ListaCircularDoble
from main import Aplicacion


class PruebasTemporizador(unittest.TestCase):
    def preparar_app(self):
        # Construye el controlador sin iniciar Tkinter ni Pygame.
        app = Aplicacion.__new__(Aplicacion)
        app.lista = ListaCircularDoble()
        for numero in range(3):
            app.lista.agregar(f"ejemplo{numero}.mp3")
        app.audio = Mock()
        app.audio.ha_terminado.return_value = False
        app.audio.posicion.return_value = 0.0
        app.audio.reproduciendo = False
        app.audio.pausado = False
        app.audio.volumen = 0.75
        app.ui = Mock()
        app.ui.after.return_value = "temporizador-falso"
        app.mensaje = "Prueba en progreso"
        app._cerrado = False
        # Si se llama a la carga inicial por error, falla la prueba.
        app._cargar_musica_de_ejemplo = Mock()
        return app

    def test_eliminar_no_regenera_canciones_con_el_tiempo(self):
        app = self.preparar_app()
        actual_id = app.lista.actual.id
        app.eliminar_cancion(actual_id)
        self.assertEqual(app.lista.cantidad, 2)
        for _ in range(100):
            app._comprobar_reproduccion()
        self.assertEqual(app.lista.cantidad, 2)
        app._cargar_musica_de_ejemplo.assert_not_called()
        self.assertEqual(app.ui.after.call_count, 100)

    def test_musica_inicial_se_carga_solo_una_vez(self):
        app = self.preparar_app()
        app.lista = ListaCircularDoble()
        app._leer_metadatos = Mock(return_value=("Demo", "Artista", 60))
        app._cargar_musica_de_ejemplo = Aplicacion._cargar_musica_de_ejemplo.__get__(app)
        with TemporaryDirectory() as ruta:
            carpeta = Path(ruta) / "musica"
            carpeta.mkdir()
            (carpeta / "a.mp3").touch()
            (carpeta / "b.mp3").touch()
            with patch("main.__file__", str(Path(ruta) / "main.py")):
                app._cargar_musica_de_ejemplo()
                app._cargar_musica_de_ejemplo()
        self.assertEqual(app.lista.cantidad, 2)

    def test_lista_vacia_permanece_vacia(self):
        app = self.preparar_app()
        for identificador in [c["id"] for c in app.lista.obtener_canciones()]:
            app.eliminar_cancion(identificador)
        self.assertEqual(app.lista.cantidad, 0)
        for _ in range(100):
            app._comprobar_reproduccion()
        self.assertEqual(app.lista.cantidad, 0)
        app._cargar_musica_de_ejemplo.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
