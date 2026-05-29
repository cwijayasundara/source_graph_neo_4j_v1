from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class EntityKind(str, Enum):
    MODULE = "Module"
    PACKAGE = "Package"
    FILE = "File"
    CLASS = "Class"
    FUNCTION = "Function"
    METHOD = "Method"
    GLOBAL_VAR = "GlobalVar"
    CONSTANT = "Constant"
    ENUM = "Enum"
    ENUM_MEMBER = "EnumMember"
    IMPORT = "Import"
    DECORATOR = "Decorator"
    PROGRAM = "Program"
    SECTION = "Section"
    PARAGRAPH = "Paragraph"
    COPYBOOK = "Copybook"


class RelKind(str, Enum):
    DEFINES = "DEFINES"
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    DECORATES = "DECORATES"
    INSTANTIATES = "INSTANTIATES"
    CONTAINS = "CONTAINS"
    READS = "READS"
    WRITES = "WRITES"
    RAISES = "RAISES"
    CATCHES = "CATCHES"
    RETURNS_TYPE = "RETURNS_TYPE"
    PARAM_TYPE = "PARAM_TYPE"
    AUTHORED_BY = "AUTHORED_BY"
    CO_CHANGED_WITH = "CO_CHANGED_WITH"
    TESTS = "TESTS"


class CodeEntity(BaseModel):
    kind: EntityKind
    qualified_name: str
    simple_name: str
    file_path: str
    start_line: int
    end_line: int
    docstring: str | None = None
    signature: str | None = None
    is_async: bool = False
    is_private: bool = False
    decorators: list[str] = Field(default_factory=list)
    base_classes: list[str] = Field(default_factory=list)
    complexity: int | None = None
    is_external: bool = False


class CodeRelationship(BaseModel):
    source_qname: str
    target_qname: str
    kind: RelKind
    file_path: str | None = None
    line: int | None = None
    metadata: dict[str, str | int] = Field(default_factory=dict)


class GitAuthor(BaseModel):
    name: str
    email: str
    commit_count: int = 0
    files_touched: list[str] = Field(default_factory=list)


class CoChange(BaseModel):
    file_a: str
    file_b: str
    times_changed_together: int
    confidence: float


class ParseResult(BaseModel):
    entities: list[CodeEntity]
    relationships: list[CodeRelationship]
    file_path: str
