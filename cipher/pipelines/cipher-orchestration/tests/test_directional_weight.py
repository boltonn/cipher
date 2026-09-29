from types import SimpleNamespace

from cipher.datastores.postgres.repositories.entity_relationship import _directional_weight
from cipher.schemas.graph.entity_relationship import TraversalDirection

OUT, IN, BOTH = TraversalDirection.OUT, TraversalDirection.IN, TraversalDirection.BOTH


def test_directed_edge_counts_only_from_the_matching_end():
    emailed = SimpleNamespace(directed=True, weight=3.0)
    assert _directional_weight(emailed, seed_is_src=True, direction=OUT) == 3.0
    assert _directional_weight(emailed, seed_is_src=True, direction=IN) == 0.0
    assert _directional_weight(emailed, seed_is_src=False, direction=IN) == 3.0
    assert _directional_weight(emailed, seed_is_src=False, direction=BOTH) == 3.0


def test_undirected_edge_has_no_direction():
    communicates = SimpleNamespace(directed=False, weight=4.0)
    assert _directional_weight(communicates, seed_is_src=True, direction=BOTH) == 4.0
    assert _directional_weight(communicates, seed_is_src=True, direction=OUT) is None
