import numpy as np
import pandas as pd
import pytest
from src.service import shifts
from src.service.shifts import (
    NEVER_SHIFT,
    RATE_FEATURES,
    SIZE_FEATURES,
    TIME_FEATURES,
    apply_realistic_shift,
    build_shift_context,
)

FEATURES = list(dict.fromkeys(
    ["Destination Port", "Total Fwd Packets", "Total Length of Fwd Packets", "Fwd Packet Length Std",
     "PSH Flag Count", "Init_Win_bytes_forward"] + TIME_FEATURES + RATE_FEATURES + SIZE_FEATURES
))
FI = {c: i for i, c in enumerate(FEATURES)}


def _frame(seed: int = 0) -> pd.DataFrame:
    """Benign flows and DDoS flows; DDoS differs most on Flow IAT Mean and Bwd Packet Length Mean."""
    rng = np.random.default_rng(seed)
    n_b, n_a = 300, 100
    df = pd.DataFrame(rng.uniform(1, 100, size=(n_b + n_a, len(FEATURES))), columns=FEATURES)
    df["target"] = ["BENIGN"] * n_b + ["DDoS"] * n_a
    df.loc[df.target == "DDoS", "Flow IAT Mean"] += 1_000
    df.loc[df.target == "DDoS", "Bwd Packet Length Mean"] += 500
    df.loc[df.target == "DDoS", "Destination Port"] = 80  # most distinctive, but must never be shifted
    df["Total Fwd Packets"] = np.round(df["Total Fwd Packets"])
    # make byte rate consistent with packet rate so the padding check is meaningful
    df["Flow Bytes/s"] = df["Flow Packets/s"] * df["Packet Length Mean"]
    return df


@pytest.fixture()
def setup():
    df = _frame()
    ctx = build_shift_context(df, FEATURES, ["DDoS"], seed=0, num_mimicry_features=3, pool_size=200)
    X = df[FEATURES].to_numpy(np.float32)
    y = df["target"].to_numpy()
    return df, ctx, X, y


def _changed_cols(X, X2, rows):
    return set(np.flatnonzero(~np.isclose(X[rows], X2[rows]).all(axis=0)))


def test_mimicry_features_are_model_free_and_skip_protected_fields(setup):
    _, ctx, _, _ = setup
    feats = ctx.mimicry_features["DDoS"]
    assert "Destination Port" not in feats
    assert {"Flow IAT Mean", "Bwd Packet Length Mean"} <= set(feats)


@pytest.mark.parametrize("shift", ["benign_slowdown", "attack_low_rate", "attack_padding", "attack_mimicry"])
def test_protected_fields_and_other_rows_never_change(setup, shift):
    _, ctx, X, y = setup
    X2 = apply_realistic_shift(X, y, "DDoS", shift, 1.0, ctx, np.random.default_rng(1))
    protected = [FI[c] for c in NEVER_SHIFT if c in FI]
    assert np.array_equal(X[:, protected], X2[:, protected])
    untouched = np.flatnonzero(y == ("DDoS" if shift == "benign_slowdown" else "BENIGN"))
    assert np.array_equal(X[untouched], X2[untouched])
    assert not np.array_equal(X, X2)
    assert np.array_equal(X, setup[2])  # the input window is not modified in place


def test_zero_severity_is_a_no_op(setup):
    _, ctx, X, y = setup
    assert apply_realistic_shift(X, y, "DDoS", "attack_padding", 0.0, ctx, np.random.default_rng(0)) is X


def test_low_rate_scales_time_up_and_rates_down_consistently(setup):
    _, ctx, X, y = setup
    rows = np.flatnonzero(y == "DDoS")
    X2 = apply_realistic_shift(X, y, "DDoS", "attack_low_rate", 1.0, ctx, np.random.default_rng(0))
    assert np.allclose(X2[rows, FI["Flow Duration"]], X[rows, FI["Flow Duration"]] * 10.0, rtol=1e-5)
    # packets = rate x duration is unchanged by slowing down
    pk = lambda A: A[rows, FI["Flow Packets/s"]] * A[rows, FI["Flow Duration"]]
    assert np.allclose(pk(X2), pk(X), rtol=1e-4)
    assert _changed_cols(X, X2, rows) == {FI[c] for c in TIME_FEATURES + RATE_FEATURES}


def test_padding_moves_sizes_and_byte_totals_consistently(setup):
    _, ctx, X, y = setup
    rows = np.flatnonzero(y == "DDoS")
    X2 = apply_realistic_shift(X, y, "DDoS", "attack_padding", 0.5, ctx, np.random.default_rng(0))
    pad = 128.0
    for c in SIZE_FEATURES:
        assert np.allclose(X2[rows, FI[c]], X[rows, FI[c]] + pad, rtol=1e-5)
    assert np.allclose(X2[rows, FI["Fwd Packet Length Std"]], X[rows, FI["Fwd Packet Length Std"]])
    assert np.allclose(
        X2[rows, FI["Total Length of Fwd Packets"]],
        X[rows, FI["Total Length of Fwd Packets"]] + pad * X[rows, FI["Total Fwd Packets"]], rtol=1e-5,
    )
    # bytes/s = packets/s x mean packet size still holds after padding
    assert np.allclose(
        X2[rows, FI["Flow Bytes/s"]], X2[rows, FI["Flow Packets/s"]] * X2[rows, FI["Packet Length Mean"]], rtol=1e-4
    )


def test_full_mimicry_copies_real_benign_values_on_selected_features_only(setup, monkeypatch):
    _, ctx, X, y = setup
    rows = np.flatnonzero(y == "DDoS")
    monkeypatch.setattr(shifts, "MIMICRY_MAX_ALPHA", 1.0)
    X2 = apply_realistic_shift(X, y, "DDoS", "attack_mimicry", 1.0, ctx, np.random.default_rng(3))
    cols = [FI[c] for c in ctx.mimicry_features["DDoS"]]
    pool_rows = {tuple(r) for r in np.round(ctx.benign_pool[:, cols], 3)}
    assert all(tuple(r) in pool_rows for r in np.round(X2[np.ix_(rows, cols)], 3))
    assert _changed_cols(X, X2, rows) <= set(cols)


def test_stochastic_mimicry_depends_on_seed_only(setup):
    _, ctx, X, y = setup
    a = apply_realistic_shift(X, y, "DDoS", "attack_mimicry", 1.0, ctx, np.random.default_rng(1))
    b = apply_realistic_shift(X, y, "DDoS", "attack_mimicry", 1.0, ctx, np.random.default_rng(1))
    c = apply_realistic_shift(X, y, "DDoS", "attack_mimicry", 1.0, ctx, np.random.default_rng(2))
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_linear_ramp_matches_the_v1_v4_schedule():
    for i in range(12):
        assert shifts.ramp_severity(i, 8, "linear") == pytest.approx(min(1.0, (i + 1) / 8.0))
    assert shifts.ramp_severity(-1, 8, "linear") == 0.0


def test_geometric_ramp_starts_at_one_byte_and_grows_steadily():
    sev = [shifts.ramp_severity(i, 20, "geometric") for i in range(25)]
    assert sev[0] == pytest.approx(1.0 / shifts.PADDING_MAX_BYTES)
    assert sev[19] == pytest.approx(1.0) and sev[24] == pytest.approx(1.0)
    ratios = np.diff(np.log(sev[:20]))
    assert np.allclose(ratios, ratios[0])  # constant growth factor per window
    assert shifts.ramp_severity(-3, 20, "geometric") == 0.0
    with pytest.raises(ValueError):
        shifts.ramp_severity(0, 20, "cubic")


def test_padding_uses_whole_bytes(setup):
    _, ctx, X, y = setup
    rows = np.flatnonzero(y == "DDoS")
    sev = shifts.ramp_severity(0, 20, "geometric") * 1.4  # 1.4 bytes requested -> 1 byte applied
    X2 = apply_realistic_shift(X, y, "DDoS", "attack_padding", sev, ctx, np.random.default_rng(0))
    col = FI["Packet Length Mean"]
    assert np.allclose(X2[rows, col] - X[rows, col], 1.0, atol=1e-3)
