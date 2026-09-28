"""Pure-logic tests for face-cluster graph handling (no DB)."""

from cipher.orchestration.cluster_faces import (
    _cluster_avg_similarity,
    _clusters_from_edges,
    _UnionFind,
)


def test_union_find_components():
    uf = _UnionFind()
    uf.union("a", "b")
    uf.union("b", "c")
    uf.union("x", "y")
    uf.add("lonely")
    groups = sorted(sorted(g) for g in uf.groups())
    assert groups == [["a", "b", "c"], ["x", "y"]]  # singletons dropped


def test_clusters_from_edges_transitive_merge():
    edges = [("a", "b", 0.9), ("c", "d", 0.8), ("b", "c", 0.7), ("m", "n", 0.95)]
    clusters = sorted(sorted(c) for c in _clusters_from_edges(edges))
    assert clusters == [["a", "b", "c", "d"], ["m", "n"]]


def test_cluster_avg_similarity_only_counts_internal_edges():
    edges = [("a", "b", 0.9), ("b", "c", 0.7), ("c", "z", 0.4)]
    assert _cluster_avg_similarity(edges, {"a", "b", "c"}) == 0.8  # (0.9 + 0.7) / 2


def test_cluster_avg_similarity_falls_back_when_no_internal_edge():
    # e.g. a cluster of one after filtering; never divides by zero
    assert _cluster_avg_similarity([("a", "b", 0.9)], {"solo"}) > 0
