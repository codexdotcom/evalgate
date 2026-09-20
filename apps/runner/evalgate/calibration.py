# apps/runner/evalgate/calibration.py
def cohens_kappa(judge: list[bool], human: list[bool]) -> tuple[float, float]:
    n = len(judge)
    if n == 0: return 0.0, 0.0
    po = sum(j == h for j, h in zip(judge, human)) / n
    pj, ph = sum(judge) / n, sum(human) / n
    pe = pj * ph + (1 - pj) * (1 - ph)
    kappa = 0.0 if pe == 1 else (po - pe) / (1 - pe)
    return po, kappa