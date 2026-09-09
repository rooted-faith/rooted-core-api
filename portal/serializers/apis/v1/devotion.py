from datetime import date

from pydantic import BaseModel, Field


class PassageResponse(BaseModel):
    start: str
    end: str
    ref: str
    verses: list[str] = Field(default_factory=list)


class AnonymousDailyLessonResponse(BaseModel):
    date: date
    passage: PassageResponse
    locked: list[str] = Field(default_factory=list)


class LessonNoteUpsertRequest(BaseModel):
    date: date
    body: str | None = None
    reflects: list[str | None] = Field(default_factory=list)


class LessonNoteResponse(BaseModel):
    date: date
    body: str | None = None
    reflects: list[str | None] = Field(default_factory=list)


class DailyLessonResponse(BaseModel):
    date: date
    passage: PassageResponse
    reflect: list[str] = Field(default_factory=list)
    apply: str
    pray: str
    note: LessonNoteResponse | None = None
    locked: list[str] = Field(default_factory=list)


class EncounterRequest(BaseModel):
    date: date


class EncounterResponse(BaseModel):
    date: date
    current_streak: int = Field(serialization_alias="currentStreak")
    longest_streak: int = Field(serialization_alias="longestStreak")
    welcome_back: bool = Field(serialization_alias="welcomeBack")
    message: str


class RhythmResponse(BaseModel):
    current_streak: int = Field(serialization_alias="currentStreak")
    longest_streak: int = Field(serialization_alias="longestStreak")
    completed_dates: list[date] = Field(default_factory=list, serialization_alias="completedDates")
