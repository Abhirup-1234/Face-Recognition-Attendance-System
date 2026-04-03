"""
FaceEngine tests — EmbeddingStore query, FPS sampling, normalisation.
Uses synthetic embeddings (no InsightFace model required).
"""
import numpy as np
import pytest


class TestEmbeddingStore:
    """Test the thread-safe embedding store with synthetic data."""

    def _make_store(self):
        from face_engine import EmbeddingStore
        return EmbeddingStore()

    def _random_emb(self, dim=512, seed=None):
        rng = np.random.RandomState(seed)
        v = rng.randn(dim).astype(np.float32)
        v /= np.linalg.norm(v)
        return v

    def test_add_and_query(self):
        store = self._make_store()
        emb1 = self._random_emb(seed=1)
        store.add("S001", [emb1])
        assert len(store) == 1
        sid, sim = store.query(emb1)
        assert sid == "S001"
        assert sim > 0.99  # Same embedding should be near-perfect match

    def test_query_empty_store(self):
        store = self._make_store()
        sid, sim = store.query(self._random_emb())
        assert sid is None
        assert sim == 0.0

    def test_remove(self):
        store = self._make_store()
        store.add("S001", [self._random_emb(seed=1)])
        store.add("S002", [self._random_emb(seed=2)])
        assert len(store) == 2
        store.remove("S001")
        assert len(store) == 1
        sid, _ = store.query(self._random_emb(seed=2))
        assert sid == "S002"

    def test_best_match_is_correct(self):
        store = self._make_store()
        emb_a = self._random_emb(seed=10)
        emb_b = self._random_emb(seed=20)
        store.add("ALICE", [emb_a])
        store.add("BOB", [emb_b])

        # Query with slight noise on emb_a — should match ALICE
        query = emb_a + np.random.RandomState(99).randn(512).astype(np.float32) * 0.05
        query /= np.linalg.norm(query)
        sid, sim = store.query(query)
        assert sid == "ALICE"
        assert sim > 0.5  # Noisy query should still match best candidate

    def test_multiple_embeddings_mean(self):
        store = self._make_store()
        rng = np.random.RandomState(42)
        base = rng.randn(512).astype(np.float32)
        base /= np.linalg.norm(base)
        # Add multiple slightly noisy versions
        embs = [base + rng.randn(512).astype(np.float32) * 0.01 for _ in range(5)]
        store.add("S001", embs)
        sid, sim = store.query(base)
        assert sid == "S001"
        assert sim > 0.98

    def test_remove_nonexistent(self):
        store = self._make_store()
        store.remove("NONEXISTENT")  # Should not raise
        assert len(store) == 0


class TestNormalise:
    """Test frame normalisation edge cases."""

    def test_none_input(self):
        from face_engine import FaceEngine
        assert FaceEngine._normalise(None) is None

    def test_empty_array(self):
        from face_engine import FaceEngine
        assert FaceEngine._normalise(np.array([])) is None

    def test_grayscale_input(self):
        from face_engine import FaceEngine
        gray = np.zeros((100, 100), dtype=np.uint8)
        result = FaceEngine._normalise(gray)
        assert result is not None
        assert result.shape[2] == 3  # Should be converted to BGR

    def test_bgra_input(self):
        from face_engine import FaceEngine
        bgra = np.zeros((100, 100, 4), dtype=np.uint8)
        result = FaceEngine._normalise(bgra)
        assert result is not None
        assert result.shape[2] == 3  # Should be converted to BGR

    def test_small_image_rejected(self):
        from face_engine import FaceEngine
        tiny = np.zeros((10, 10, 3), dtype=np.uint8)
        assert FaceEngine._normalise(tiny) is None

    def test_large_image_resized(self):
        from face_engine import FaceEngine
        large = np.zeros((4000, 3000, 3), dtype=np.uint8)
        result = FaceEngine._normalise(large)
        assert result is not None
        assert max(result.shape[:2]) <= 2560


class TestUtils:
    """Test shared utility functions."""

    def test_sort_classes(self):
        from utils import sort_classes
        unsorted = ["XII", "V", "Nursery", "I", "X", "UKG"]
        result = sort_classes(unsorted)
        assert result == ["Nursery", "UKG", "I", "V", "X", "XII"]

    def test_initials(self):
        from utils import initials
        assert initials("Arjun Sharma") == "AS"
        assert initials("Priya") == "P"
        assert initials("") == "X"   # empty string splits to [""] → first char fallback
        assert initials(None) == "X"   # "XX" is one word → first char
        assert initials("A B C") == "AB"  # Only first 2
