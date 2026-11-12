r"""
Utilitarios numericos com semantica identica a do MATLAB.

Este modulo isola as pequenas diferencas de comportamento entre MATLAB e
Python/NumPy que, se ignoradas, fazem o porte divergir do original:

* ``matlab_mode``      -> ``mode()`` do MATLAB (valor mais frequente, o menor
                          em caso de empate).
* ``matlab_colon``     -> ``a:d:b`` (o numero de elementos e ``floor((b-a)/d)+1``).
* ``interp1_linear``   -> ``interp1(...,'linear','extrap')``.
* ``solve2x2``         -> ``J\F`` para 2x2 (LU com pivotagem parcial, a mesma
                          ordem de operacoes que o LAPACK usado pelo MATLAB).
* ``EPS``              -> ``eps`` do MATLAB (2.220446049250313e-16).

Nada aqui depende do modelo de SCR: sao apenas primitivas de compatibilidade.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

__all__ = [
    "EPS",
    "matlab_mode",
    "matlab_colon",
    "interp1_linear",
    "solve2x2",
    "norm2",
    "safe_cosh",
    "safe_sinh",
]

#: ``eps`` do MATLAB (distancia de 1.0 ao double seguinte).
EPS: float = float(np.finfo(float).eps)


def matlab_mode(values: Sequence[float] | np.ndarray) -> float:
    """Valor mais frequente; em caso de empate devolve o MENOR (como o MATLAB).

    Usado para colapsar colunas que sao constantes por motor (rotacao, potencia
    nominal, geometria instalada) mas que aparecem repetidas em cada linha do
    dataset.
    """
    arr = np.asarray(values, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError("matlab_mode: vector vazio.")
    uniq, counts = np.unique(arr, return_counts=True)   # np.unique ja ordena
    return float(uniq[int(np.argmax(counts))])          # argmax -> 1o maximo = menor valor


def matlab_colon(start: float, step: float, stop: float) -> np.ndarray:
    """Equivalente a ``start:step:stop`` do MATLAB (aceita ``step`` negativo)."""
    if step == 0.0:
        raise ValueError("matlab_colon: passo nulo.")
    n = math.floor((stop - start) / step)
    if n < 0:
        return np.empty(0, dtype=float)
    return start + step * np.arange(n + 1, dtype=float)


def interp1_linear(x: np.ndarray, y: np.ndarray, xq: np.ndarray) -> np.ndarray:
    """``interp1(x, y, xq, 'linear', 'extrap')``.

    ``x`` tem de estar ordenado de forma crescente. Fora do dominio prolonga
    linearmente o segmento extremo (``np.interp`` saturaria, dai a implementacao
    explicita).
    """
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    xq = np.atleast_1d(np.asarray(xq, dtype=float))
    if x.size != y.size:
        raise ValueError("interp1_linear: x e y com tamanhos diferentes.")
    if x.size == 1:
        return np.full(xq.shape, y[0])

    out = np.interp(xq, x, y)

    left = xq < x[0]
    if np.any(left):
        m = (y[1] - y[0]) / (x[1] - x[0])
        out[left] = y[0] + m * (xq[left] - x[0])

    right = xq > x[-1]
    if np.any(right):
        m = (y[-1] - y[-2]) / (x[-1] - x[-2])
        out[right] = y[-1] + m * (xq[right] - x[-1])

    return out


def solve2x2(a11: float, a12: float, a21: float, a22: float,
             b1: float, b2: float) -> tuple[float, float]:
    r"""Resolve ``[a11 a12; a21 a22] * x = [b1; b2]``.

    Reproduz o ``\`` do MATLAB para uma matriz 2x2 densa: eliminacao de Gauss
    com pivotagem parcial, pela mesma ordem de operacoes do LAPACK (``dgesv``),
    para que o arredondamento coincida.

    Se a matriz for singular devolve ``(inf, inf)`` -- o chamador testa
    ``isfinite`` e aborta o passo de Newton, tal como o codigo MATLAB faz
    perante o ``Inf``/``NaN`` que o ``\`` produz nesse caso.
    """
    if abs(a21) > abs(a11):                       # pivotagem parcial
        a11, a12, a21, a22 = a21, a22, a11, a12
        b1, b2 = b2, b1
    if a11 == 0.0:
        return math.inf, math.inf
    factor = a21 / a11
    u22 = a22 - factor * a12
    y2 = b2 - factor * b1
    if u22 == 0.0:
        return math.inf, math.inf
    x2 = y2 / u22
    x1 = (b1 - a12 * x2) / a11
    return x1, x2


def norm2(a: float, b: float) -> float:
    """Norma-2 de um vector 2x1, com escalonamento (equivalente a ``norm``)."""
    return math.hypot(a, b)


def safe_cosh(x: float) -> float:
    """``cosh`` com overflow -> ``inf`` (semantica IEEE do MATLAB)."""
    try:
        return math.cosh(x)
    except OverflowError:
        return math.inf


def safe_sinh(x: float) -> float:
    """``sinh`` com overflow -> ``+/-inf`` (semantica IEEE do MATLAB)."""
    try:
        return math.sinh(x)
    except OverflowError:
        return math.inf if x > 0 else -math.inf
