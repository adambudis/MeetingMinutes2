from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

Role = Literal["system", "user", "assistant"]
TranscriptionModel = Literal["canary", "parakeet"]
Language = Literal["cs", "en"]


class TranscriptSegment(BaseModel):
    start: float
    end: float | None = None
    speaker: str = "???"
    text: str


class LlmMessage(BaseModel):
    role: Role
    content: str


class SummarizeRequest(BaseModel):
    transcript: str = ""
    model: str | None = None
    segments: list[TranscriptSegment] | None = None


class ChatRequest(BaseModel):
    messages: list[LlmMessage]
    model: str | None = None


# --- Map phase structures (mirror MapReduceModels.cs) ---------------------------------
# LLMs sometimes emit `null` instead of `[]`; treat that as an empty list like the C# code did.


def _none_to_list(value: object) -> object:
    return [] if value is None else value


NullableList = BeforeValidator(_none_to_list)


class MapTopic(BaseModel):
    title: str | None = ""
    points: Annotated[list[str | None], NullableList] = Field(default_factory=list)


class MapDecision(BaseModel):
    decision: str | None = ""


class MapTask(BaseModel):
    task: str | None = ""
    owner: str | None = None
    due: str | None = None


class MapChunkResult(BaseModel):
    participants: Annotated[list[str | None], NullableList] = Field(default_factory=list)
    topics: Annotated[list[MapTopic | None], NullableList] = Field(default_factory=list)
    decisions: Annotated[list[MapDecision | None], NullableList] = Field(default_factory=list)
    tasks: Annotated[list[MapTask | None], NullableList] = Field(default_factory=list)


class ActionItem(BaseModel):
    task: str = ""
    owner: str | None = None
    due: str | None = None
    source_quote: str | None = None
    priority: str | None = None


class SummarizationResult(BaseModel):
    markdown: str
    map_success_ratio: float
