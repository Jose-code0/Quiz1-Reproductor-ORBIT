"""Capa de audio; el motor es Pygame, independiente de Tkinter y los nodos."""
import os
import time
import pygame


class ReproductorAudio:
    def __init__(self):
        pygame.mixer.init()
        self.activo = False
        self.pausado = False
        self.volumen = .75
        self._ruta = None
        self._desplazamiento = 0.0
        self._posicion_pausa = 0.0
        self._inicio = 0.0
        pygame.mixer.music.set_volume(self.volumen)

    def reproducir(self, ruta):
        if not os.path.isfile(ruta):
            raise FileNotFoundError(f'Archivo no encontrado: {ruta}')
        pygame.mixer.music.stop()
        self.activo = self.pausado = False
        pygame.mixer.music.load(ruta)
        pygame.mixer.music.set_volume(self.volumen)
        pygame.mixer.music.play()
        self._ruta = ruta
        self._desplazamiento = self._posicion_pausa = 0.0
        self._inicio = time.monotonic()
        self.activo = True

    def pausar(self):
        if self.activo and not self.pausado:
            self._posicion_pausa = self.posicion()
            pygame.mixer.music.pause()
            self.pausado = True

    def reanudar(self):
        if self.activo and self.pausado:
            pygame.mixer.music.unpause()
            self.pausado = False

    def detener(self):
        pygame.mixer.music.stop()
        self.activo = self.pausado = False
        self._desplazamiento = self._posicion_pausa = 0.0

    def cambiar_volumen(self, volumen):
        self.volumen = max(0, min(1, float(volumen)))
        pygame.mixer.music.set_volume(self.volumen)

    @property
    def reproduciendo(self):
        return self.activo and not self.pausado

    def posicion(self):
        if not self.activo:
            return 0.0
        if self.pausado:
            return self._posicion_pausa
        ms = pygame.mixer.music.get_pos()
        return max(0.0, self._desplazamiento + max(0, ms) / 1000.0)

    def buscar(self, segundos):
        """Busca en MP3/OGG. WAV y codecs no compatibles devuelven error legible."""
        if not self.activo or not self._ruta:
            raise ValueError('No hay audio reproduciéndose.')
        if os.path.splitext(self._ruta)[1].lower() not in ('.mp3', '.ogg'):
            raise ValueError('El desplazamiento está disponible en MP3 y OGG.')
        segundos = max(0.0, float(segundos))
        estaba_pausado = self.pausado
        # Pygame admite start en MP3 y OGG, pero no en todos los codecs.
        pygame.mixer.music.play(start=segundos)
        self._desplazamiento = segundos
        self._inicio = time.monotonic()
        self.activo = True
        self.pausado = False
        if estaba_pausado:
            self.pausar()

    def ha_terminado(self):
        return (self.activo and not self.pausado
                and time.monotonic() - self._inicio >= .4
                and not pygame.mixer.music.get_busy())

    def cerrar(self):
        self.detener()
        pygame.mixer.quit()
