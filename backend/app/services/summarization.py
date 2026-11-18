"""Port of SummarizationService.cs: map-reduce summarization + action-items extraction."""

import json
import logging
import re
import unicodedata
from collections.abc import AsyncIterator

from pydantic import TypeAdapter, ValidationError

from app.schemas import (
    ActionItem,
    LlmMessage,
    MapChunkResult,
    MapDecision,
    MapTask,
    MapTopic,
    SummarizationResult,
    TranscriptSegment,
)
from app.services.interfaces import ChunkStarted, Done, LlmService, SummaryEvent, Token

log = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4
MAX_CHUNK_TOKENS = 4000
OVERLAP_TURNS = 2

FOLLOWUP_SYSTEM_PROMPT = (
    "Jsi asistent pro práci s přepisem a shrnutím schůzky. Odpovídej výhradně česky. "
    "Odpovídej pouze na základě dosavadní konverzace a přepisu — nic si nevymýšlej. "
    'Pokud informace v přepisu chybí, napiš "není uvedeno". '
    "Buď stručný a věcný. Zachovej původní význam výroků z přepisu — neinterpretuj je vlastními slovy."
)

MAP_SYSTEM_PROMPT = (
    "Jsi asistent pro analýzu schůzek. Přečti část přepisu schůzky a vrať POUZE JSON objekt "
    "odpovídající tomuto schématu (žádný jiný text, žádné Markdown ohrady):\n"
    "{\n"
    '  "participants": ["jméno"],\n'
    '  "topics": [{"title": "název tématu", "points": ["klíčový bod"]}],\n'
    '  "decisions": [{"decision": "text rozhodnutí"}],\n'
    '  "tasks": [{"task": "popis úkolu", "owner": "zodpovědná osoba nebo null", "due": "termín nebo null"}]\n'
    "}\n\n"
    "Pravidla:\n"
    "- Odpovídej POUZE platným JSON objektem. Žádná próza, žádné Markdown ohrady, žádný jiný text.\n"
    "- Použij přesně pole: participants, topics, decisions, tasks.\n"
    "- U topics vnořuj pole points.\n"
    "- Pokud nejsou žádné položky dané kategorie, vrať prázdné pole.\n"
    "- Jazyk výstupu: čeština.\n"
    "- do participants zapisuj POUZE skutečná jména osob. "
    "Pokud mluvčí jsou označeni jako SPEAKER_XX (anonymní), vrať prázdné pole."
)

REDUCE_SYSTEM_PROMPT = (
    "Jsi asistent pro tvorbu zápisů ze schůzek. Obdržíš JSON pole výsledků z map fáze analýzy "
    "přepisu schůzky. Vytvoř jedno konsolidované Markdown shrnutí v češtině.\n\n"
    "Struktura shrnutí (povinné sekce v tomto pořadí):\n"
    "1. `# Souhrn schůzky` — nadpis\n"
    "2. Výkonný souhrn — odstavec 2–3 věty.\n"
    "3. `## Účastníci` — odrážkový seznam skutečných jmen (SPEAKER_XX vynechej).\n"
    "4. `## Témata` — pro každé téma `### Téma N: {název}` se třemi podsekemi:\n"
    "   - `**Shrnutí:**` (1–2 věty)\n"
    "   - `**Klíčové body:**` (odrážky)\n"
    '   - `**Rozhodnutí:**` (odrážky; "není uvedeno" pokud žádné)\n'
    '5. `## Otevřené otázky` — odrážkový seznam; "není uvedeno" pokud žádné.\n\n'
    "KRITICKÉ OMEZENÍ: Shrnutí NESMÍ obsahovat sekci ani tabulku s akčními položkami. "
    "NEemituj nadpisy ani tabulky obsahující slova: "
    '"Akční položky", "Akční úkoly", "Akce", "Action items", "Tasks", "Úkoly". '
    "Sekci s úkoly/akcemi ZCELA vynech — bude přidána samostatně.\n\n"
    "Pravidla:\n"
    "- Pouze čeština.\n"
    "- Nevymýšlej informace, které nejsou v datech.\n"
    '- Kde data chybí, piš "není uvedeno".\n'
    "- Nezobecňuj — vycházej pouze z poskytnutých dat."
)

# The WPF version asked for a bare JSON array. Ollama's JSON mode makes models answer with an
# object instead (typically just the first item), which the C# deserializer rejected, so the
# action-items table always came out empty. The array is therefore wrapped in {"items": [...]}
# and the shape is enforced with a JSON schema (ACTION_ITEMS_SCHEMA).
ACTION_ITEMS_EXTRACTION_PROMPT = (
    "Jsi asistent pro extrakci akčních položek ze záznamu schůzky. "
    "Obdržíš přepis schůzky a seznam úkolů identifikovaných v map fázi. "
    "Vrať POUZE JSON objekt s polem \"items\" obsahujícím VŠECHNY akční položky, "
    "odpovídající tomuto schématu (žádný jiný text, žádné Markdown ohrady):\n"
    '{"items": [{"task": "popis úkolu", "owner": "zodpovědná osoba nebo null", '
    '"due": "termín nebo null", '
    '"source_quote": "doslovný citát z přepisu prokazující úkol nebo null", '
    '"priority": "vysoká|střední|nízká nebo null"}]}\n\n'
    "Pravidla:\n"
    "- Odpovídej POUZE platným JSON objektem. Žádná próza, žádné Markdown ohrady.\n"
    "- source_quote MUSÍ být doslovný úryvek z poskytnutého přepisu. Pokud vhodný citát nenajdeš, vrať null.\n"
    '- Pokud nejsou žádné akční položky, vrať {"items": []}\n'
    "- Jazyk výstupu: čeština."
)

_NULLABLE_STRING = {"type": ["string", "null"]}
ACTION_ITEMS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": _NULLABLE_STRING,
                    "due": _NULLABLE_STRING,
                    "source_quote": _NULLABLE_STRING,
                    "priority": _NULLABLE_STRING,
                },
                "required": ["task", "owner", "due", "source_quote", "priority"],
            },
        }
    },
    "required": ["items"],
}

DEFAULT_SUMMARY_PROMPT = "Vytvoř shrnutí schůzky."

_action_items_adapter = TypeAdapter(list[ActionItem])


class SummarizationFailedError(Exception):
    """No transcript chunk could be processed in the map phase."""


# --- Transcript formatting & chunking ---------------------------------------------------


def format_for_llm(segments: list[TranscriptSegment]) -> str:
    return "\n".join(f"{s.speaker}: {s.text}" for s in segments)


def chunk_transcript_string(transcript: str, max_tokens: int = MAX_CHUNK_TOKENS) -> list[str]:
    max_chars = max_tokens * CHARS_PER_TOKEN
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for line in (ln for ln in transcript.split("\n") if ln):
        if length > 0 and length + len(line) + 1 > max_chars:
            chunks.append("\n".join(current).rstrip())
            current, length = [], 0
        current.append(line)
        length += len(line) + 1
    if current:
        chunks.append("\n".join(current).rstrip())
    return chunks


def chunk_transcript(
    segments: list[TranscriptSegment],
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_turns: int = OVERLAP_TURNS,
) -> list[str]:
    """Split at speaker-turn boundaries; each chunk repeats the last `overlap_turns` turns of the previous one."""
    max_chars = max_tokens * CHARS_PER_TOKEN
    chunks: list[str] = []
    current: list[str] = []
    length = 0

    for seg in segments:
        line = f"{seg.speaker}: {seg.text}"
        if length > 0 and length + len(line) + 1 > max_chars:
            chunks.append("\n".join(current).rstrip())
            current = current[-overlap_turns:] if overlap_turns > 0 else []
            length = sum(len(x) + 1 for x in current)
        current.append(line)
        length += len(line) + 1

    if current:
        chunks.append("\n".join(current).rstrip())
    return chunks


# --- Map result merging -----------------------------------------------------------------


def dedup_map_results(results: list[MapChunkResult]) -> MapChunkResult:
    participants: dict[str, str] = {}
    for r in results:
        for p in r.participants:
            if p and (name := p.strip()):
                participants.setdefault(name.lower(), name)

    topics: dict[str, MapTopic] = {}
    for r in results:
        for t in r.topics:
            if t is None or not t.title or not t.title.strip():
                continue
            title = t.title.strip()
            entry = topics.setdefault(title.lower(), MapTopic(title=title, points=[]))
            entry.points.extend(t.points)

    decisions: dict[str, MapDecision] = {}
    for r in results:
        for d in r.decisions:
            if d is not None and d.decision and d.decision.strip():
                decisions.setdefault(d.decision.strip().lower(), d)

    tasks: dict[tuple[str, str], MapTask] = {}
    for r in results:
        for t in r.tasks:
            if t is not None and t.task and t.task.strip():
                key = (t.task.strip().lower(), (t.owner or "").strip().lower())
                tasks.setdefault(key, t)

    return MapChunkResult(
        participants=list(participants.values()),
        topics=list(topics.values()),
        decisions=list(decisions.values()),
        tasks=list(tasks.values()),
    )


# --- Action items -----------------------------------------------------------------------

_QUOTE_CHAR_MAP = str.maketrans({
    "„": '"', "“": '"', "”": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'", "‹": "'", "›": "'",
    "–": "-", "—": "-", "−": "-",
    "…": " ",
})


def normalize_for_quote_match(text: str) -> str:
    """Diacritic-, case- and whitespace-blind normalisation for source-quote matching."""
    decomposed = unicodedata.normalize("NFD", text.translate(_QUOTE_CHAR_MAP))
    no_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(no_marks.lower().split())


def validate_source_quotes(items: list[ActionItem], transcript: str) -> list[ActionItem]:
    norm_transcript = normalize_for_quote_match(transcript)
    validated: list[ActionItem] = []
    for item in items:
        if not item.source_quote or not item.source_quote.strip():
            validated.append(item)
            continue
        norm_quote = normalize_for_quote_match(item.source_quote)
        if not norm_quote:
            validated.append(item.model_copy(update={"source_quote": None}))
        elif norm_quote in norm_transcript:
            validated.append(item)
        else:
            validated.append(item.model_copy(update={"source_quote": None, "task": "⚠ " + item.task}))
    return validated


def _escape_cell(value: str | None) -> str:
    if not value or not value.strip():
        return "—"
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_action_items_table(items: list[ActionItem]) -> str:
    if not items:
        return "_Žádné úkoly._"
    lines = [
        "| # | Úkol | Vlastník | Termín | Zdrojová citace | Priorita |",
        "|---|---|---|---|---|---|",
    ]
    for i, it in enumerate(items, start=1):
        cells = [it.task, it.owner, it.due, it.source_quote, it.priority]
        lines.append(f"| {i} | " + " | ".join(_escape_cell(c) for c in cells) + " |")
    return "\n".join(lines)


_ACTION_HEADING = re.compile(
    r"^(?P<indent>\s{0,3})(?P<hashes>#{1,4})\s+"
    r"(?:Akční položky|Akční úkoly|Akce|Action items|Tasks|Úkoly)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
# Same shape as the C# pattern, but whitespace classes are limited to [ \t]: with `\s` a blank
# line was swallowed as part of the body, so a following, unrelated table got deleted too.
_MD_TABLE = re.compile(
    r"^(?P<header>\|[^\n]+\|)[ \t]*\n[ \t]*\|[ \t\-:]+\|[ \t\-:|]*\n(?P<body>(?:[ \t]*\|[^\n]*\|[ \t]*\n?)+)",
    re.MULTILINE,
)
_TASK_HEADERS = {"ukol", "task", "akce", "action"}
_OWNER_HEADERS = {"vlastnik", "owner", "odpovedny", "assignee"}


def remove_action_items_table(md: str) -> str:
    """Strip any action-items section/table the Reduce step emitted despite instructions."""
    while m := _ACTION_HEADING.search(md):
        level = len(m.group("hashes"))
        next_heading = re.compile(rf"^\s{{0,3}}#{{1,{level}}}\s+\S", re.MULTILINE)
        nxt = next_heading.search(md, m.end())
        end = nxt.start() if nxt else len(md)
        md = md[: m.start()] + md[end:]

    for tm in reversed(list(_MD_TABLE.finditer(md))):
        header_cells = {normalize_for_quote_match(c) for c in tm.group("header").strip("|").split("|")}
        if header_cells & _TASK_HEADERS and header_cells & _OWNER_HEADERS:
            md = md[: tm.start()] + md[tm.end():]

    return md.rstrip() + "\n"


_FENCE_OPEN = re.compile(r"^\s*```(?:markdown|md)?[ \t]*\n", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"\n[ \t]*```\s*$")


def strip_markdown_fence(md: str) -> str:
    """Unwrap an answer the model put entirely inside a ```markdown fence (small models often do);
    otherwise the UI would show the summary as a raw code block."""
    opening = _FENCE_OPEN.match(md)
    if not opening:
        return md
    return _FENCE_CLOSE.sub("\n", md[opening.end():])


def _parse_action_items(raw: str) -> list[ActionItem]:
    """Accept {"items": [...]} (expected), a bare array, any object wrapping one list, or a single item."""
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data] if "task" in data else next((v for v in data.values() if isinstance(v, list)), [])
    return _action_items_adapter.validate_python(data or [])


# --- Service ------------------------------------------------------------------------------


class MapReduceSummarizationService:
    def __init__(self, llm: LlmService) -> None:
        self._llm = llm

    async def _map_chunk(self, chunk: str, model: str, index: int, total: int) -> MapChunkResult | None:
        messages = [
            LlmMessage(role="system", content=MAP_SYSTEM_PROMPT),
            LlmMessage(role="user", content=chunk),
        ]
        try:
            return MapChunkResult.model_validate_json(await self._llm.complete_json(messages, model))
        except (ValidationError, ValueError):
            pass
        try:
            retry = [*messages, LlmMessage(role="user", content="respond with valid JSON only")]
            return MapChunkResult.model_validate_json(await self._llm.complete_json(retry, model))
        except (ValidationError, ValueError) as ex:
            log.warning("Map chunk %d/%d failed after retry: %s", index, total, ex)
            return None

    async def _extract_action_items(self, transcript: str, tasks: list[MapTask], model: str) -> list[ActionItem]:
        tasks_json = json.dumps([t.model_dump() for t in tasks], ensure_ascii=False)
        messages = [
            LlmMessage(role="system", content=ACTION_ITEMS_EXTRACTION_PROMPT),
            LlmMessage(role="user", content=f"PŘEPIS:\n{transcript}\n\nÚKOLY Z MAP FÁZE:\n{tasks_json}"),
        ]
        try:
            items = _parse_action_items(await self._llm.complete_json(messages, model, ACTION_ITEMS_SCHEMA))
            return validate_source_quotes(items, transcript)
        except (ValidationError, ValueError) as ex:
            log.warning("Action-items extraction failed: %s", ex)
            return []

    async def summarize(
        self,
        transcript: str,
        model: str,
        segments: list[TranscriptSegment] | None,
    ) -> AsyncIterator[SummaryEvent]:
        chunks = chunk_transcript(segments) if segments else chunk_transcript_string(transcript)
        if not chunks:
            raise SummarizationFailedError("Přepis je prázdný")

        map_results: list[MapChunkResult] = []
        for i, chunk in enumerate(chunks, start=1):
            yield ChunkStarted(i, len(chunks))
            if (result := await self._map_chunk(chunk, model, i, len(chunks))) is not None:
                map_results.append(result)

        if not map_results:
            raise SummarizationFailedError("Nepodařilo se zpracovat žádný chunk transkripce")

        merged = dedup_map_results(map_results)
        reduce_messages = [
            LlmMessage(role="system", content=REDUCE_SYSTEM_PROMPT),
            LlmMessage(role="user", content=merged.model_dump_json()),
        ]
        reduce_parts: list[str] = []
        async for token in self._llm.stream(reduce_messages, model):
            reduce_parts.append(token)
            yield Token(token)

        llm_transcript = format_for_llm(segments) if segments else transcript
        action_items = await self._extract_action_items(llm_transcript, merged.tasks, model)

        final_md = (
            remove_action_items_table(strip_markdown_fence("".join(reduce_parts)))
            + "\n\n## Akční položky\n\n"
            + render_action_items_table(action_items)
        )
        yield Done(SummarizationResult(markdown=final_md, map_success_ratio=len(map_results) / len(chunks)))

    async def continue_chat(self, messages: list[LlmMessage], model: str) -> AsyncIterator[str]:
        async for token in self._llm.stream(messages, model):
            yield token
