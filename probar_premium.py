"""Pruebas adicionales de preferencias, rendimiento e integración del controlador."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from lista_circular import ListaCircularDoble
from preferencias import Preferencias
from main import Aplicacion
from audio import ReproductorAudio


class TestPremium(unittest.TestCase):
    def test_preferencias_guardadas_y_recuperadas(self):
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = Path(carpeta) / 'ajustes.json'
            p = Preferencias(archivo)
            p.datos['favoritos'] = ['C:/música/uno.mp3']
            p.datos['barra_lateral'] = False
            p.guardar()
            nuevo = Preferencias(archivo)
            self.assertEqual(nuevo.datos['favoritos'], ['C:/música/uno.mp3'])
            self.assertFalse(nuevo.datos['barra_lateral'])

    def test_preferencias_corruptas_no_rompen_inicio(self):
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = Path(carpeta) / 'ajustes.json'
            archivo.write_text('{archivo corrupto', encoding='utf-8')
            p = Preferencias(archivo)
            self.assertEqual(p.datos['volumen'], .75)

    def app_falsa(self):
        app = Aplicacion.__new__(Aplicacion)
        app.lista = ListaCircularDoble()
        for i in range(4):
            app.lista.agregar(f'{i}.mp3', f'Canción {i}', 'Artista')
        app.audio = Mock()
        app.audio.posicion.return_value = 0
        app.audio.volumen = .75
        app.audio.reproduciendo = False
        app.audio.pausado = False
        app.ui = Mock()
        app.ui.after.return_value = 'timer'
        app.prefs = Preferencias(Path(tempfile.gettempdir()) / 'orbit-no-escribir.json')
        app.prefs.datos = dict(Preferencias.POR_DEFECTO)
        app._cerrado = False
        app._historial_aleatorio = []
        app._version_cache = None
        app._cache_canciones = []
        app._guardado_pendiente = None
        app.mensaje = 'Listo'
        return app

    def test_version_invalida_cache_tras_eliminar(self):
        a = self.app_falsa()
        a._actualizar_interfaz()
        original = a._cache_canciones
        a._actualizar_interfaz()
        self.assertIs(a._cache_canciones, original)
        a.eliminar_cancion(2)
        self.assertIsNot(a._cache_canciones, original)
        self.assertEqual(len(a._cache_canciones), 3)

    def test_favorito_se_puede_poner_y_quitar(self):
        a = self.app_falsa()
        a.alternar_favorito(1)
        self.assertEqual(len(a.prefs.datos['favoritos']), 1)
        a.alternar_favorito(1)
        self.assertEqual(a.prefs.datos['favoritos'], [])

    def test_aleatorio_no_se_elige_a_si_mismo(self):
        a = self.app_falsa()
        a.prefs.datos['aleatorio'] = True
        original = a.lista.actual.id
        for _ in range(8):
            with patch('main.random.randrange',return_value=0):
                a.siguiente()
            self.assertNotEqual(a.lista.actual.id,original)
            original=a.lista.actual.id
        self.assertEqual(a.lista.cantidad, 4)

    def test_repetir_una_no_cambia_los_nodos(self):
        a = self.app_falsa()
        a.alternar_repeticion()
        actual=a.lista.actual.id
        a.audio.ha_terminado.return_value=True
        a._iniciar_actual=Mock()
        a._comprobar_reproduccion()
        self.assertEqual(a.lista.actual.id,actual)
        a._iniciar_actual.assert_called_once()

    def test_no_seek_wav_invalido(self):
        audio = ReproductorAudio.__new__(ReproductorAudio)
        audio.activo=True
        audio._ruta='ejemplo.wav'
        with self.assertRaises(ValueError):
            audio.buscar(42)


if __name__ == '__main__':
    unittest.main(verbosity=2)
