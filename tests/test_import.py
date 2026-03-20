from clawgraph import (
    ArtifactRecord,
    BranchRecord,
    ClawGraphOpenAIClient,
    ClawGraphRuntimeClient,
    ClawGraphRuntimeResponse,
    ClawGraphSession,
    FactEvent,
)


def test_protocol_exports_available() -> None:
    assert FactEvent
    assert BranchRecord
    assert ArtifactRecord
    assert ClawGraphSession
    assert ClawGraphOpenAIClient
    assert ClawGraphRuntimeClient
    assert ClawGraphRuntimeResponse
