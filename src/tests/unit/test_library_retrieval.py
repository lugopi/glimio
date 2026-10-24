from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from seance.core.library import retrieve_passages


class PassageRetrievalTests(unittest.TestCase):
    def test_matches_whole_words_not_arbitrary_substrings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            false_positive = root / "2026-10-17_10-00-02"
            (false_positive / "summary").mkdir(parents=True)
            (false_positive / "summary" / "resume_audio.md").write_text(
                "The carpet is near the carless wall.", encoding="utf-8"
            )
            real_match = root / "2026-10-17_10-00-01"
            (real_match / "summary").mkdir(parents=True)
            (real_match / "summary" / "resume_audio.md").write_text(
                "The car starts after the inspection.", encoding="utf-8"
            )

            passages = retrieve_passages(root, "car", top_k=8)

        self.assertTrue(passages)
        self.assertTrue(all(item["session_id"] == real_match.name for item in passages))


    def test_library_search_and_ai_retrieval_scan_past_old_prefix_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = root / "2026-10-17_10-00-00"
            transcript = session / "transcript" / "transcription.md"
            transcript.parent.mkdir(parents=True)
            # Simulate a long transcript; the matching passage sits after the old 2 MB
            # library-search and 5 MB AI-retrieval prefix limits.
            with transcript.open("w", encoding="utf-8") as stream:
                for _ in range(190_000):
                    stream.write("Ordinary discussion without the target word.\n")
                stream.write("\nAt the very end is endmarkerneedle.\n")

            from seance.core.library import list_sessions

            listed = list_sessions(root, query="endmarkerneedle")
            retrieved = retrieve_passages(root, "endmarkerneedle", top_k=8)

        self.assertEqual([item["id"] for item in listed], [session.name])
        self.assertTrue(retrieved)
        self.assertIn("endmarkerneedle", retrieved[0]["text"])

    def test_session_scope_limits_retrieval_to_selected_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected = root / "2026-10-20_10-00-01"
            other = root / "2026-10-20_10-00-02"
            for session in (selected, other):
                summary = session / "summary" / "resume_audio.md"
                summary.parent.mkdir(parents=True)
                summary.write_text("Nebula budget decision approved.", encoding="utf-8")

            passages = retrieve_passages(root, "nebula budget", top_k=8, session_ids={selected.name})

        self.assertTrue(passages)
        self.assertTrue(all(item["session_id"] == selected.name for item in passages))

    def test_empty_session_scope_returns_no_matches_when_no_selected_session_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = root / "2026-10-20_10-00-01"
            summary = session / "summary" / "resume_audio.md"
            summary.parent.mkdir(parents=True)
            summary.write_text("Nebula budget decision approved.", encoding="utf-8")

            passages = retrieve_passages(root, "nebula budget", top_k=8, session_ids={"missing-session"})

        self.assertEqual(passages, [])

    def test_long_paragraph_chunking_does_not_split_a_keyword_mid_word(self) -> None:
        from seance.core.library import _iter_text_chunks

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "long.md"
            path.write_text("x" * 1188 + " ultrawidekeyword with more context", encoding="utf-8")
            chunks = list(_iter_text_chunks(path, max_chars=1200))
        self.assertTrue(any("ultrawidekeyword" in chunk for chunk in chunks))

    def test_live_progress_counts_total_hits_while_returning_only_top_k(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for session_index in range(12):
                session = root / f"2026-10-17_10-{session_index:02d}-00"
                summary = session / "summary" / "resume_audio.md"
                summary.parent.mkdir(parents=True)
                summary.write_text(
                    "\n\n".join(
                        f"Orbit discussion {session_index}, paragraph {paragraph}." for paragraph in range(16)
                    ),
                    encoding="utf-8",
                )
            updates: list[dict[str, int]] = []
            passages = retrieve_passages(
                root, "orbit", top_k=8,
                on_update=lambda _items, progress: updates.append(dict(progress)),
            )

        self.assertLessEqual(len(passages), 8)
        self.assertTrue(updates)
        self.assertEqual(updates[-1]["sessions_scanned"], 12)
        self.assertEqual(updates[-1]["passages_found"], 12 * 16)
        self.assertLessEqual(len({item["session_id"] for item in passages}), 8)


if __name__ == "__main__":
    unittest.main()
