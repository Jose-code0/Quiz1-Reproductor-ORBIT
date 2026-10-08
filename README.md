# CIRCULAR MUSIC — Quiz 1: Listas Aplicadas

Aplicación de escritorio en **Python + Tkinter** con motor de audio **Pygame CE**. El diseño visual de `interfaz.py` corresponde a la nueva interfaz **Circular Music / Dark Premium** facilitada para este proyecto, integrada con el backend anterior.

## Ejecución rápida (Windows / Visual Studio Code)

1. Extrae **todo** el contenido del ZIP en una carpeta normal.
2. En VS Code, abre esa carpeta con `Archivo → Abrir carpeta`.
3. En la terminal, ejecuta:

```powershell
py -m pip install -r requirements.txt
py main.py
```

Alternativamente, ejecuta `Iniciar_CircularMusic.bat` para instalar dependencias y arrancar desde Windows.

> **IMPORTANTE**: ejecuta `main.py`, no `interfaz.py`. Este último, ejecutado por sí solo, abre una demostración sin conexión al audio ni a la lista real; `main.py` une todas las capas.

## Arquitectura y archivos

- **`lista_circular.py`**: clases `Nodo` y `ListaCircularDoble` implementadas desde cero, con referencias `anterior` y `siguiente`; incluye al inicio la justificación solicitada por el docente.
- **`audio.py`**: reproducción, pausa, búsqueda temporal, volumen y detección del final de canción mediante Pygame.
- **`main.py`**: controlador original que conecta backend, audio y nueva interfaz; conserva la carga inicial única de archivos y la gestión de modos.
- **`interfaz.py`**: nueva interfaz Circular Music (Tkinter), con paneles, tema oscuro/violeta, biblioteca, búsqueda, favoritos, cola, navegación y **visualización gráfica completa de los nodos**.
- **`preferencias.py`**: estado persistente del backend: favoritos, historial, volumen y reproducción aleatoria/repetición.
- **`musica/`**: canciones locales para la demostración (solo en el ZIP completo, excluidas de la entrega pública).
- **`probar_backend.py`**, **`probar_integracion.py`**, **`probar_premium.py`**, **`probar_interfaz.py`**: pruebas de lógica y normalización de la interfaz.

## Características reales

- Agregar y eliminar canciones sin reconstruir la estructura ni duplicar nodos.
- Reproducción con avance y retroceso **circular**, incluidos los casos vacío/un solo nodo/dos nodos/muchos nodos.
- Biblioteca, búsqueda, selección, favoritos, recientes y clic derecho con acciones.
- **Mapa gráfico de toda la lista** en la sección `Estructura`, con enlaces bidireccionales y cierre circular, además del detalle de vecinos de la canción actual.
- Barra de reproducción con reproducción/pausa, anterior/siguiente, orden aleatorio, repetir una/todas, control de volumen y barra de progreso.
- Preferencias de la interfaz guardadas y opciones para ocultar paneles, ampliar espacio de trabajo y configurar animaciones.

## Justificación breve (incluida en `lista_circular.py`)

**Caso 2, reproductor en modo «repetir todo».** Se eligió una lista doblemente enlazada circular porque permite avanzar y retroceder sin recorrer la lista buscando el predecesor. Las referencias de la última y primera canción cierran el ciclo, así que no es necesario tratar los extremos como casos especiales al cambiar de pista. Su costo es mantener dos referencias por nodo y actualizarlas con cuidado cuando se inserta o elimina una canción. Esta explicación también se encuentra como comentario en el archivo de implementación, tal como permite la rúbrica del Quiz.

## Pruebas

```powershell
py probar_backend.py
py probar_integracion.py
py probar_premium.py
py probar_interfaz.py
```

Prueba además con la aplicación abierta: agregar varias canciones; avanzar desde la última a la primera; retroceder desde la primera a la última; eliminar un nodo intermedio y el nodo actual; dejarla vacía y agregar otra canción. Revisa que el mapa gráfico y contador de nodos siempre se correspondan.

## Notas de instalación/entrega

- Requiere Python con Tkinter y las dos dependencias de `requirements.txt`. No necesita Pillow para dibujar la nueva interfaz.
- El ZIP para **GitHub** excluye los MP3 comerciales; cada persona puede cargar canciones propias con **Agregar canciones**.
- El ZIP **completo** conserva las siete canciones locales para la demostración presencial, pero no es adecuado para publicarlo en un repositorio público con esos archivos.
- No hay streaming ni descargas de música. La reproducción real y el resultado visual en pantallas HiDPI deben comprobarse finalmente en tu PC.
