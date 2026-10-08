"""Pruebas de contrato entre la nueva interfaz Circular Music y el backend.

No abren una ventana ni requieren archivos de audio o servidor gráfico.
Para ejecutar: py probar_interfaz.py
"""
import unittest
from interfaz import CALLBACKS_CONOCIDOS, normalizar_estado


class TestContratoInterfaz(unittest.TestCase):
    def test_reconoce_callbacks_del_controlador_original(self):
        for clave in ('agregar_archivos', 'eliminar_cancion', 'seleccionar_cancion',
                      'alternar_reproduccion', 'siguiente', 'anterior', 'buscar_posicion',
                      'cambiar_volumen', 'alternar_favorito', 'alternar_aleatorio',
                      'alternar_repeticion', 'guardar_preferencia', 'cerrar'):
            self.assertIn(clave, CALLBACKS_CONOCIDOS)

    def test_preserva_orden_rutas_y_metadatos(self):
        canciones = [
            {'id': 3, 'titulo': 'Tres', 'artista': 'Artista', 'ruta': '/tres.mp3',
             'album': 'Disco', 'duracion': 60},
            {'id': 1, 'titulo': 'Uno', 'ruta': '/uno.mp3', 'duracion': 30},
        ]
        datos = normalizar_estado({'canciones': canciones, 'actual_id': 3})
        self.assertEqual([c['id'] for c in datos['canciones']], [3, 1])
        self.assertEqual(datos['canciones'][0]['ruta'], '/tres.mp3')
        self.assertEqual(datos['canciones'][0]['album'], 'Disco')

    def test_favoritos_aleatorio_y_repeticion_en_estado(self):
        datos = normalizar_estado({'canciones': [{'id': 5}], 'actual_id': 5,
                                   'favoritos': ['/musica/uno.mp3'],
                                   'recientes': ['/musica/dos.mp3'],
                                   'aleatorio': True, 'repetir_uno': True})
        self.assertEqual(datos['favoritos'], ['/musica/uno.mp3'])
        self.assertEqual(datos['recientes'], ['/musica/dos.mp3'])
        self.assertTrue(datos['aleatorio'])
        self.assertTrue(datos['repetir_uno'])

    def test_estados_vacio_y_unico(self):
        vacio = normalizar_estado({'canciones': [], 'actual_id': 777})
        self.assertIsNone(vacio['actual_id'])
        self.assertFalse(vacio['reproduciendo'])
        uno = normalizar_estado({'canciones': [{'id': 7, 'duracion': 42}],
                                 'actual_id': 7, 'posicion': 200,
                                 'reproduciendo': True})
        self.assertEqual(uno['posicion'], 42)
        self.assertTrue(uno['reproduciendo'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
