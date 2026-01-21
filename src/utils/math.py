from __future__ import annotations
import numpy as np


def zscore(x: float, mean: float, std: float) -> float:
    if std == 0.0:
        return 0.0
    return (x - mean) / std


def ols_beta(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or len(y) < 2:
        return 1.0
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    cov = float(np.mean((x - x_mean) * (y - y_mean)))
    var = float(np.mean((x - x_mean) ** 2))
    if var == 0.0:
        return 1.0
    return cov / var
