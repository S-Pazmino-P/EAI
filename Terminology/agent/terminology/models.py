from pydantic import BaseModel
from typing import Optional


class Candidate(BaseModel):
    code: str
    display: str
    system: str


class ExpandResult(BaseModel):
    candidates: list[Candidate]
    total: int
    query: str
    vs_url: str


class LookupResult(BaseModel):
    code: str
    display: str
    system: str
    properties: dict[str, str]


class SubsumesResult(BaseModel):
    code: str
    ancestor: str
    is_subsumed: bool
