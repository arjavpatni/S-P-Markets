from pydantic import BaseModel
from datetime import datetime


class NewsArticle(BaseModel):
    headline: str
    summary: str
    body: str = ""
    url: str
    source: str = "moneycontrol"
    timestamp: datetime | None = None
    category: str | None = None


class NewsBundle(BaseModel):
    articles: list[NewsArticle]
    fetched_at: datetime
    count: int
