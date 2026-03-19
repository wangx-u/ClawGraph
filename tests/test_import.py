from clawgraph import ArtifactRecord, BranchRecord, FactEvent


def test_protocol_exports_available() -> None:
    assert FactEvent
    assert BranchRecord
    assert ArtifactRecord
