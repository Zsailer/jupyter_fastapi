from pathlib import Path
from typing import Any
from datetime import datetime
from pydantic import BaseModel


class ContentsModel(BaseModel):
    name: str
    path: str
    type: str
    writable: bool
    created: datetime
    last_modified: datetime
    mimetype: str = None
    content: Any = None
    format: str = None


class RenameModel(BaseModel):
    path: Path


class CreateModel(BaseModel):
    copy_from: str = None
    ext: str
    type: str


class SaveModel(BaseModel):
    name: str
    path: str
    type: str
    format: str
    content: str

