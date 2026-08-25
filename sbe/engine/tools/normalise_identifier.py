"""normalise_identifier tool — reconciles UTR vs UPI RRN namespaces and
truncated bank narrations back to a canonical transaction reference
(BUILD_PLAN archetype table: UTR_TRUNCATION, UPI_RRN_VS_UTR)."""

def normalise(raw_identifier: str, source: str) -> str:
    raise NotImplementedError
