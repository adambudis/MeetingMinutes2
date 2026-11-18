import asyncio
import json

import pytest

from app.schemas import ActionItem, MapChunkResult, TranscriptSegment
from app.services.interfaces import ChunkStarted, Done, Token
from app.services.summarization import (
    ACTION_ITEMS_SCHEMA,
    MapReduceSummarizationService,
    _parse_action_items,
    SummarizationFailedError,
    chunk_transcript,
    chunk_transcript_string,
    dedup_map_results,
    normalize_for_quote_match,
    remove_action_items_table,
    render_action_items_table,
    strip_markdown_fence,
    validate_source_quotes,
)
from tests.fakes import SEGMENTS, FakeLlm


def _segments(n: int) -> list[TranscriptSegment]:
    # "S: " + 96 chars = 99 chars per line, 100 with the newline.
    return [TranscriptSegment(start=i, speaker="S", text=f"{i}" * 96) for i in range(1, n + 1)]


class TestChunking:
    def test_short_transcript_is_one_chunk(self) -> None:
        assert chunk_transcript(SEGMENTS) == ["SPEAKER_00: Dobrý den, začneme.\nSPEAKER_01: Petr připraví návrh do pátku."]

    def test_chunks_split_at_turns_with_two_turn_overlap(self) -> None:
        chunks = chunk_transcript(_segments(5), max_tokens=75)  # 300 chars -> 3 lines per chunk
        firsts = [[line[3] for line in c.split("\n")] for c in chunks]
        assert firsts == [["1", "2", "3"], ["2", "3", "4"], ["3", "4", "5"]]

    def test_string_chunking_drops_empty_lines_and_has_no_overlap(self) -> None:
        text = "\n".join(["a" * 99] * 4) + "\n\n"
        chunks = chunk_transcript_string(text, max_tokens=50)  # 200 chars -> 2 lines per chunk
        assert [c.count("\n") + 1 for c in chunks] == [2, 2]


class TestDedup:
    def test_merges_case_insensitively_and_keeps_first_spelling(self) -> None:
        merged = dedup_map_results([
            MapChunkResult.model_validate({
                "participants": ["Petr", " ", None],
                "topics": [{"title": "Rozpočet", "points": ["a"]}],
                "decisions": [{"decision": "Schváleno"}],
                "tasks": [{"task": "Návrh", "owner": "Petr", "due": None}],
            }),
            MapChunkResult.model_validate({
                "participants": ["petr ", "Jana"],
                "topics": [{"title": "rozpočet ", "points": ["b"]}, {"title": None, "points": None}],
                "decisions": [{"decision": "schváleno"}, None],
                "tasks": [{"task": "návrh", "owner": "PETR"}, {"task": "Návrh", "owner": "Jana"}],
                "extra": "ignored",
            }),
        ])
        assert merged.participants == ["Petr", "Jana"]
        assert [(t.title, t.points) for t in merged.topics] == [("Rozpočet", ["a", "b"])]
        assert [d.decision for d in merged.decisions] == ["Schváleno"]
        assert [(t.task, t.owner) for t in merged.tasks] == [("Návrh", "Petr"), ("Návrh", "Jana")]

    def test_null_lists_from_llm_are_accepted(self) -> None:
        result = MapChunkResult.model_validate({"participants": None, "topics": None, "decisions": None, "tasks": None})
        assert result.participants == [] and result.topics == []


class TestActionItems:
    def test_normalization_ignores_diacritics_quotes_and_whitespace(self) -> None:
        assert normalize_for_quote_match("Připraví  „návrh“\n do pátku…") == 'pripravi "navrh" do patku'

    def test_quote_validation(self) -> None:
        transcript = "SPEAKER_01: Petr připraví návrh do pátku."
        items = validate_source_quotes(
            [
                ActionItem(task="Návrh", source_quote="petr pripravi NAVRH"),
                ActionItem(task="Rozpočet", source_quote="nikdo tohle neřekl"),
                ActionItem(task="Bez citace", source_quote=None),
                ActionItem(task="Prázdná", source_quote="…"),
            ],
            transcript,
        )
        assert [(i.task, i.source_quote) for i in items] == [
            ("Návrh", "petr pripravi NAVRH"),
            ("⚠ Rozpočet", None),
            ("Bez citace", None),
            ("Prázdná", None),
        ]

    @pytest.mark.parametrize(
        "raw",
        [
            '{"items": [{"task": "A"}, {"task": "B"}]}',  # expected (schema) shape
            '[{"task": "A"}, {"task": "B"}]',  # bare array, as the original prompt asked
            '{"akcni_polozky": [{"task": "A"}, {"task": "B"}]}',  # some other wrapper key
        ],
    )
    def test_parse_action_item_shapes(self, raw: str) -> None:
        assert [i.task for i in _parse_action_items(raw)] == ["A", "B"]

    def test_parse_single_object_as_one_item(self) -> None:
        # what gemma3 returned for the original array prompt in Ollama JSON mode
        assert [i.owner for i in _parse_action_items('{"task": "Překlady", "owner": "Martin"}')] == ["Martin"]
        assert _parse_action_items('{"items": []}') == []

    def test_render_table(self) -> None:
        assert render_action_items_table([]) == "_Žádné úkoly._"
        table = render_action_items_table([ActionItem(task="A | B", owner="Petr", priority="vysoká")])
        assert table.splitlines() == [
            "| # | Úkol | Vlastník | Termín | Zdrojová citace | Priorita |",
            "|---|---|---|---|---|---|",
            "| 1 | A \\| B | Petr | — | — | vysoká |",
        ]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("```markdown\n# Souhrn\n\ntext\n```", "# Souhrn\n\ntext\n"),  # what gemma3:4b produced
            ("\n```MD \n# A\n```\n\n", "# A\n"),
            ("```\n# A\n", "# A\n"),  # truncated, no closing fence
            ("# Souhrn\n\n```python\ncode\n```", "# Souhrn\n\n```python\ncode\n```"),  # inner block kept
            ("```python\nprint()\n```", "```python\nprint()\n```"),  # other languages untouched
        ],
    )
    def test_strip_markdown_fence(self, raw: str, expected: str) -> None:
        assert strip_markdown_fence(raw) == expected

    def test_strips_stray_action_items_section(self) -> None:
        md = "# Souhrn\n\nText.\n\n## Úkoly\n\n- něco\n\n### Detail\n\nx\n\n## Otevřené otázky\n\n- není uvedeno\n"
        assert remove_action_items_table(md) == "# Souhrn\n\nText.\n\n## Otevřené otázky\n\n- není uvedeno\n"

    def test_strips_orphan_task_table_but_keeps_other_tables(self) -> None:
        md = (
            "# Souhrn\n\n| Úkol | Vlastník |\n|---|---|\n| A | Petr |\n\n"
            "| Téma | Stav |\n|---|---|\n| X | hotovo |\n"
        )
        out = remove_action_items_table(md)
        assert "Vlastník" not in out
        assert "| Téma | Stav |" in out


def _run(service: MapReduceSummarizationService, segments=SEGMENTS) -> list:
    async def collect() -> list:
        return [e async for e in service.summarize("", "gemma3:12b", segments)]

    return asyncio.run(collect())


class TestMapReduce:
    def test_full_pipeline(self) -> None:
        map_json = json.dumps({"participants": [], "topics": [{"title": "Návrh", "points": ["do pátku"]}],
                               "decisions": [], "tasks": [{"task": "Připravit návrh", "owner": "Petr", "due": "pátek"}]})
        actions_json = json.dumps({"items": [
            {"task": "Připravit návrh", "owner": "Petr", "due": "pátek", "source_quote": "Petr pripravi navrh", "priority": "vysoká"},
            {"task": "Vymyšlený", "owner": None, "due": None, "source_quote": "tohle nezaznělo", "priority": None},
        ]})
        llm = FakeLlm(
            json_responses=["this is not json", map_json, actions_json],
            streams=[["# Souhrn schůzky\n\nText.\n\n", "## Úkoly\n\n- stray\n\n", "## Otevřené otázky\n\n- není uvedeno\n"]],
        )
        events = _run(MapReduceSummarizationService(llm))

        assert events[0] == ChunkStarted(1, 1)
        assert next(e.text for e in events if isinstance(e, Token)) == "# Souhrn schůzky\n\nText.\n\n"
        done = events[-1]
        assert isinstance(done, Done)
        md = done.result.markdown
        assert done.result.map_success_ratio == 1.0
        assert "## Úkoly" not in md and "stray" not in md
        assert md.index("## Otevřené otázky") < md.index("## Akční položky")
        assert "| 1 | Připravit návrh | Petr | pátek | Petr pripravi navrh | vysoká |" in md
        assert "| 2 | ⚠ Vymyšlený | — | — | — | — |" in md
        # the retry asked for valid JSON; the action-items pass saw the full transcript
        assert llm.calls[1][1][-1].content == "respond with valid JSON only"
        assert "SPEAKER_01: Petr připraví návrh do pátku." in llm.calls[3][1][1].content
        # map uses plain JSON mode, action items the structured-output schema
        assert llm.schemas == [None, None, ACTION_ITEMS_SCHEMA]

    def test_all_chunks_failing_raises(self) -> None:
        llm = FakeLlm(json_responses=["nope", "still nope"])
        with pytest.raises(SummarizationFailedError):
            _run(MapReduceSummarizationService(llm))

    def test_action_items_failure_still_produces_summary(self) -> None:
        llm = FakeLlm(json_responses=["{}", "[broken"], streams=[["# Souhrn schůzky\n"]])
        done = _run(MapReduceSummarizationService(llm))[-1]
        assert done.result.markdown.endswith("## Akční položky\n\n_Žádné úkoly._")
