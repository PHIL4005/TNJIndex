from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ItemSummary(BaseModel):
    id: int
    title: str
    thumbnail_url: Optional[str] = None
    tags: list[str]
    score: Optional[float] = None


class ItemDetail(BaseModel):
    id: int
    title: str
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    tags: list[str]
    description: Optional[str] = None
    composition: Optional[str] = None


class TagCount(BaseModel):
    name: str
    count: int


class SearchResponse(BaseModel):
    results: list[ItemSummary]
    query: str
    total: int
