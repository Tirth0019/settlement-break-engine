"""Quota detection — TPD vs transient rate limits."""

from sbe.engine.quota import QuotaExhaustedError, quota_exhausted_from_error


def test_tpd_detected_as_quota_exhausted():
    exc = Exception(
        "Error code: 429 - Rate limit reached for tokens per day (TPD): "
        "Limit 200000. Please try again in 21m7s."
    )
    qe = quota_exhausted_from_error(exc)
    assert isinstance(qe, QuotaExhaustedError)
    assert qe.reset_hint is not None


def test_rpm_not_tpd():
    exc = Exception("Error code: 429 - Rate limit exceeded")
    assert quota_exhausted_from_error(exc) is None
