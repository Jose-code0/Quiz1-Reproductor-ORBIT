"""Pruebas automáticas de la estructura: python probar_backend.py"""
import unittest
from lista_circular import ListaCircularDoble


class PruebasListaCircular(unittest.TestCase):
    def setUp(self):
        self.lista = ListaCircularDoble()

    def verificar_enlaces(self):
        lista = self.lista
        if lista.cantidad == 0:
            self.assertIsNone(lista.primero)
            self.assertIsNone(lista.actual)
            return
        nodo = lista.primero
        for _ in range(lista.cantidad):
            self.assertIs(nodo.siguiente.anterior, nodo)
            self.assertIs(nodo.anterior.siguiente, nodo)
            nodo = nodo.siguiente
        self.assertIs(nodo, lista.primero)

    def test_lista_vacia(self):
        self.assertIsNone(self.lista.siguiente())
        self.assertIsNone(self.lista.anterior())
        self.assertFalse(self.lista.eliminar(99))
        self.verificar_enlaces()

    def test_un_solo_nodo(self):
        ident = self.lista.agregar("a.mp3")
        self.assertEqual(self.lista.actual.id, ident)
        self.assertIs(self.lista.actual.siguiente, self.lista.actual)
        self.assertIs(self.lista.actual.anterior, self.lista.actual)
        self.verificar_enlaces()

    def test_tres_nodos_y_circularidad(self):
        ids = [self.lista.agregar(f"{n}.mp3") for n in (1, 2, 3)]
        self.assertEqual(self.lista.anterior().id, ids[-1])
        self.assertEqual(self.lista.siguiente().id, ids[0])
        self.verificar_enlaces()

    def test_eliminar_primero(self):
        primero = self.lista.agregar("a.mp3")
        segundo = self.lista.agregar("b.mp3")
        self.assertTrue(self.lista.eliminar(primero))
        self.assertEqual(self.lista.actual.id, segundo)
        self.verificar_enlaces()

    def test_eliminar_intermedio(self):
        ids = [self.lista.agregar(f"{n}.mp3") for n in (1, 2, 3)]
        self.assertTrue(self.lista.eliminar(ids[1]))
        self.assertEqual(self.lista.cantidad, 2)
        self.assertEqual([c["id"] for c in self.lista.obtener_canciones()], [ids[0], ids[2]])
        self.verificar_enlaces()

    def test_eliminar_ultimo(self):
        ids = [self.lista.agregar(f"{n}.mp3") for n in (1, 2, 3)]
        self.assertTrue(self.lista.eliminar(ids[-1]))
        self.verificar_enlaces()

    def test_eliminar_unico(self):
        identificador = self.lista.agregar("a.mp3")
        self.assertTrue(self.lista.eliminar(identificador))
        self.verificar_enlaces()

    def test_nombres_repetidos_ids_unicos(self):
        primero = self.lista.agregar("a.mp3", "Mismo título")
        segundo = self.lista.agregar("b.mp3", "Mismo título")
        self.assertNotEqual(primero, segundo)
        self.assertTrue(self.lista.seleccionar(segundo))
        self.assertEqual(self.lista.actual.id, segundo)
        self.verificar_enlaces()

    def test_eliminar_actual_seleccionado(self):
        ids = [self.lista.agregar(f"{n}.mp3") for n in (1, 2, 3)]
        self.lista.seleccionar(ids[1])
        self.lista.eliminar(ids[1])
        self.assertEqual(self.lista.actual.id, ids[2])
        self.verificar_enlaces()


    def test_dos_nodos_y_regreso_al_mismo(self):
        ids = [self.lista.agregar("a.mp3"), self.lista.agregar("b.mp3")]
        self.assertEqual(self.lista.siguiente().id, ids[1])
        self.assertEqual(self.lista.siguiente().id, ids[0])
        self.assertEqual(self.lista.anterior().id, ids[1])
        self.assertTrue(self.lista.eliminar(ids[1]))
        self.assertIs(self.lista.primero.siguiente, self.lista.primero)
        self.assertIs(self.lista.primero.anterior, self.lista.primero)
        self.verificar_enlaces()

    def test_eliminacion_de_id_inexistente_no_altera_lista(self):
        ids = [self.lista.agregar(f"{n}.mp3") for n in range(4)]
        self.assertFalse(self.lista.eliminar(9999))
        self.assertEqual([c["id"] for c in self.lista.obtener_canciones()], ids)
        self.assertEqual(self.lista.cantidad, 4)
        self.verificar_enlaces()

    def test_insertar_de_nuevo_tras_vaciar(self):
        original = self.lista.agregar("original.mp3")
        self.lista.eliminar(original)
        nuevo = self.lista.agregar("nuevo.mp3")
        self.assertNotEqual(nuevo, original)
        self.assertEqual(self.lista.actual.id, nuevo)
        self.assertEqual(self.lista.cantidad, 1)
        self.verificar_enlaces()

    def test_navegacion_multiple_sin_perder_circularidad(self):
        ids = [self.lista.agregar(f"{n}.mp3") for n in range(5)]
        for _ in range(10):
            self.lista.siguiente()
        self.assertEqual(self.lista.actual.id, ids[0])
        for _ in range(6):
            self.lista.anterior()
        self.assertEqual(self.lista.actual.id, ids[-1])
        self.verificar_enlaces()


if __name__ == "__main__":
    unittest.main(verbosity=2)
