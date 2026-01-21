from __future__ import annotations
from collections import deque
from typing import Deque, Iterable
import numpy as np


class RollingWindow:
    def __init__(self, maxlen: int):
        self.maxlen = maxlen
        self._data: Deque[float] = deque(maxlen=maxlen)

    def add(self, x: float) -> None:
        self._data.append(x)

    def values(self) -> np.ndarray:
        if not self._data:
            return np.array([], dtype=float)
        return np.fromiter(self._data, dtype=float)

    def mean(self) -> float:
        if not self._data:
            return 0.0
        return float(np.mean(self.values()))

    def std(self) -> float:
        if len(self._data) < 2:
            return 0.0
        return float(np.std(self.values(), ddof=1))

    def last(self) -> float:
        return self._data[-1] if self._data else 0.0

    def __len__(self) -> int:
        return len(self._data)


class RollingStats:
    def __init__(self, maxlen: int):
        self.window = RollingWindow(maxlen)

    def update(self, x: float) -> None:
        self.window.add(x)

    def mean(self) -> float:
        return self.window.mean()

    def std(self) -> float:
        return self.window.std()
