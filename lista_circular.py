"""
QUIZ 1 - Caso 2: Reproductor de música en modo «repetir todo».
Variante: lista doblemente enlazada circular.

Justificación: cada canción es un nodo con referencias al nodo anterior y al
siguiente. Esta variante permite navegar en ambas direcciones y, gracias a su
circularidad, pasar directamente de la última canción a la primera y de la
primera a la última, sin condiciones especiales al llegar a los extremos.
Una lista simplemente enlazada dificulta retroceder; una doble no circular
requiere controlar sus extremos y una circular simple tampoco permite
retroceder directamente. El costo es guardar dos referencias por nodo y
actualizarlas cuidadosamente al insertar o eliminar canciones. Esta elección
resuelve las necesidades concretas del reproductor.
"""
from pathlib import Path


class Nodo:
    """Representa una canción y sus dos referencias."""

    def __init__(self, identificador, titulo, artista, ruta, duracion=None, album="Sin álbum"):
        self.id = identificador
        self.titulo = titulo
        self.artista = artista
        self.ruta = ruta
        self.duracion = duracion
        self.album = album
        self.siguiente = None
        self.anterior = None


class ListaCircularDoble:
    """Administra canciones usando nodos, no una list de Python."""

    def __init__(self):
        self.primero = None
        self.actual = None
        self.cantidad = 0
        self._siguiente_id = 1
        self.version = 0

    def agregar(self, ruta, titulo=None, artista="Desconocido", duracion=None, album="Sin álbum"):
        """Inserta una canción al final y devuelve su ID único."""
        if not ruta:
            raise ValueError("La ruta de la canción no puede estar vacía.")

        if not titulo:
            titulo = Path(ruta).stem

        nuevo = Nodo(self._siguiente_id, titulo, artista, str(ruta), duracion, album)
        self._siguiente_id += 1

        if self.primero is None:
            self.primero = nuevo
            self.actual = nuevo
            nuevo.siguiente = nuevo
            nuevo.anterior = nuevo
        else:
            ultimo = self.primero.anterior
            ultimo.siguiente = nuevo
            nuevo.anterior = ultimo
            nuevo.siguiente = self.primero
            self.primero.anterior = nuevo

        self.cantidad += 1
        self.version += 1
        return nuevo.id

    def buscar(self, identificador):
        """Busca por ID; permite canciones con nombres repetidos."""
        nodo = self.primero
        for _ in range(self.cantidad):
            if nodo.id == identificador:
                return nodo
            nodo = nodo.siguiente
        return None

    def seleccionar(self, identificador):
        """Cambia la canción actual. Devuelve True si existe."""
        nodo = self.buscar(identificador)
        if nodo is None:
            return False
        self.actual = nodo
        return True

    def siguiente(self):
        """Avanza circularmente y devuelve la nueva canción actual."""
        if self.actual is not None:
            self.actual = self.actual.siguiente
        return self.actual

    def anterior(self):
        """Retrocede circularmente y devuelve la nueva canción actual."""
        if self.actual is not None:
            self.actual = self.actual.anterior
        return self.actual

    def eliminar(self, identificador):
        """Elimina por ID, manteniendo las conexiones circulares."""
        nodo = self.buscar(identificador)
        if nodo is None:
            return False

        if self.cantidad == 1:
            self.primero = None
            self.actual = None
        else:
            nodo.anterior.siguiente = nodo.siguiente
            nodo.siguiente.anterior = nodo.anterior

            if nodo is self.primero:
                self.primero = nodo.siguiente
            if nodo is self.actual:
                self.actual = nodo.siguiente

        nodo.anterior = None
        nodo.siguiente = None
        self.cantidad -= 1
        self.version += 1
        return True

    def obtener_canciones(self):
        """Crea una copia para dibujar la interfaz; NO almacena la lista aquí."""
        datos = []
        nodo = self.primero
        for _ in range(self.cantidad):
            datos.append({
                "id": nodo.id,
                "titulo": nodo.titulo,
                "artista": nodo.artista,
                "duracion": nodo.duracion,
                "album": nodo.album,
                "ruta": nodo.ruta,
            })
            nodo = nodo.siguiente
        return datos


if __name__ == "__main__":
    lista = ListaCircularDoble()
    for titulo in ("Canción A", "Canción B", "Canción C"):
        lista.agregar(f"{titulo}.mp3", titulo)

    print("Inicio:", lista.actual.titulo)
    print("Siguiente:", lista.siguiente().titulo)
    print("Siguiente:", lista.siguiente().titulo)
    print("Siguiente (vuelve a A):", lista.siguiente().titulo)
    print("Anterior (vuelve a C):", lista.anterior().titulo)
    lista.eliminar(lista.actual.id)
    print("Después de eliminar C:", lista.obtener_canciones())
