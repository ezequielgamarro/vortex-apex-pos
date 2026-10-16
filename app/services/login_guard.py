"""Límite de intentos fallidos de login (fuerza bruta de contraseñas).

Cuenta los fallos por correo (haya o no usuario con ese correo, para no revelar
qué cuentas existen). Tras `MAX_INTENTOS` fallos dentro de la ventana, bloquea
ese correo durante `BLOQUEO_S` segundos. Un login correcto reinicia el contador.

Vive en memoria: es una instalación de un solo proceso y reiniciar el programa
también reinicia el límite. Alcanza para frenar la adivinanza de contraseñas;
no pretende defender de quien ya controla la PC.
"""

import threading
import time
from typing import Callable

MAX_INTENTOS = 5
VENTANA_S = 15 * 60
BLOQUEO_S = 5 * 60
_MAX_CLAVES = 1000  # tope de memoria ante un barrido de correos inventados


class LoginGuard:
    def __init__(
        self,
        max_intentos: int = MAX_INTENTOS,
        ventana_s: int = VENTANA_S,
        bloqueo_s: int = BLOQUEO_S,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_intentos
        self._ventana = ventana_s
        self._bloqueo = bloqueo_s
        self._reloj = reloj
        self._lock = threading.Lock()
        # clave -> [fallos, inicio_ventana, bloqueado_hasta]
        self._estado: dict[str, list[float]] = {}

    @staticmethod
    def clave(username: str | None) -> str:
        return (username or "").strip().lower()[:255]

    def segundos_bloqueado(self, clave: str) -> int:
        """Segundos que faltan para poder reintentar (0 si no está bloqueado)."""
        with self._lock:
            est = self._estado.get(clave)
            if not est:
                return 0
            restante = est[2] - self._reloj()
            return int(restante) + 1 if restante > 0 else 0

    def registrar_fallo(self, clave: str) -> None:
        ahora = self._reloj()
        with self._lock:
            est = self._estado.get(clave)
            if est is None or ahora - est[1] > self._ventana:
                if len(self._estado) >= _MAX_CLAVES:
                    self._estado.pop(next(iter(self._estado)))
                est = self._estado[clave] = [0, ahora, 0.0]
            est[0] += 1
            if est[0] >= self._max:
                est[2] = ahora + self._bloqueo
                est[0] = 0
                est[1] = ahora

    def registrar_exito(self, clave: str) -> None:
        with self._lock:
            self._estado.pop(clave, None)


# Instancia compartida por el router de autenticación.
login_guard = LoginGuard()
