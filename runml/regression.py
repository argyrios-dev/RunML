from __future__ import annotations
import math


def _mean(values):
    return sum(values) / len(values)


def _std(values, mean):
    if len(values) < 2:
        return 0.0
    return math.sqrt(max(sum((x - mean) ** 2 for x in values) / len(values), 0.0))


def _solve(a, b):
    n = len(b)
    aug = [a[i][:] + [b[i]] for i in range(n)]

    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-10:
            aug[pivot][col] = 1e-10
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]

        div = aug[col][col]
        aug[col] = [v / div for v in aug[col]]

        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if abs(factor) < 1e-15:
                continue
            aug[row] = [aug[row][c] - factor * aug[col][c] for c in range(n + 1)]

    return [aug[i][-1] for i in range(n)]


def fit_ridge(rows, target, candidate_features, max_features=8, ridge=1e-4):
    if len(rows) < 3:
        raise ValueError("At least 3 samples are required.")

    y = [float(r[target]) for r in rows]
    y_mean = _mean(y)
    y_std = _std(y, y_mean)
    stats = {}
    ranked = []

    for feature in candidate_features:
        xs = [float(r[feature]) for r in rows]
        mean = _mean(xs)
        std = _std(xs, mean)
        stats[feature] = {"mean": mean, "std": std, "min": min(xs), "max": max(xs)}
        if std <= 1e-9:
            continue
        if y_std <= 1e-9:
            corr = 0.0
        else:
            cov = sum((x - mean) * (yy - y_mean) for x, yy in zip(xs, y)) / len(y)
            corr = abs(cov / (std * y_std))
        ranked.append((corr, feature))

    ranked.sort(reverse=True)
    features = [f for _, f in ranked[:max_features]]

    xrows = []
    for row in rows:
        vec = [1.0]
        for f in features:
            st = stats[f]
            vec.append((float(row[f]) - st["mean"]) / st["std"])
        xrows.append(vec)

    width = len(xrows[0])
    xtx = [[0.0] * width for _ in range(width)]
    xty = [0.0] * width

    for x, yy in zip(xrows, y):
        for i in range(width):
            xty[i] += x[i] * yy
            for j in range(width):
                xtx[i][j] += x[i] * x[j]

    for i in range(1, width):
        xtx[i][i] += ridge

    coeff = _solve(xtx, xty)
    preds = [sum(c * v for c, v in zip(coeff, x)) for x in xrows]
    mae = sum(abs(p - yy) for p, yy in zip(preds, y)) / len(y)

    return {
        "target": target,
        "features": features,
        "stats": {f: stats[f] for f in features},
        "coefficients": coeff,
        "training_samples": len(rows),
        "training_mae": mae,
    }


def predict_ridge(model, row):
    vec = [1.0]
    extrapolation = False
    for f in model["features"]:
        st = model["stats"][f]
        value = float(row[f])
        if value < st["min"] or value > st["max"]:
            extrapolation = True
        vec.append((value - st["mean"]) / st["std"])
    value = sum(c * v for c, v in zip(model["coefficients"], vec))
    return max(0.0, value), extrapolation
