"""The public timeline must never present carried-forward sensor values as observations."""
from app.data import generate_demo_patients
from app.engine import ReplaySession


def test_missing_sensor_history_is_not_misrepresented_as_measured_glucose():
    demo = generate_demo_patients()["HDT-027"]
    first = dict(demo.stream[0], quality="VALID", glucose=125.0)
    second = dict(demo.stream[1], quality="MISSING", glucose=None)
    third = dict(demo.stream[2], quality="MISSING", glucose=None)
    session = ReplaySession("TEST", demo.profile, [first, second, third], cadence_min=5)

    snapshot = session.step(3)
    history = snapshot["recent_history"]
    assert len(history) == 3
    assert history[0]["quality"] == "VALID"
    assert history[0]["glucose"] == 125.0
    assert history[1]["quality"] == "MISSING"
    assert history[1]["glucose"] is None
    assert history[2]["quality"] == "MISSING"
    assert history[2]["glucose"] is None
    # Short-gap extrapolation may still use internal last-observed data, but
    # public history may never portray that value as a new CGM measurement.
    assert session.history[-1]["glucose"] is not None


def test_outlier_is_not_drawn_as_direct_observation():
    demo = generate_demo_patients()["HDT-027"]
    first = dict(demo.stream[0], quality="VALID", glucose=125.0)
    second = dict(demo.stream[1], quality="OUTLIER", glucose=600.0)
    session = ReplaySession("TEST", demo.profile, [first, second], cadence_min=5)
    snapshot = session.step(2)
    assert snapshot["recent_history"][1]["quality"] == "OUTLIER"
    assert snapshot["recent_history"][1]["glucose"] is None
