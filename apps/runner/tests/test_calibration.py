from evalgate.calibration import cohens_kappa

def test_perfect_agreement():
    po, k = cohens_kappa([True, False, True], [True, False, True])
    assert po == 1.0 and k == 1.0

def test_chance_agreement_is_zero():
    # Judge always passes, human passes half. Agreement 0.5, but by chance.
    po, k = cohens_kappa([True]*4, [True, True, False, False])
    assert po == 0.5 and abs(k) < 1e-9

def test_worse_than_chance_is_negative():
    po, k = cohens_kappa([True, True, False, False], [False, False, True, True])
    assert k < 0