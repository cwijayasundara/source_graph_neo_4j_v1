"""Tests for the AST parser — runs without Neo4j."""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from code_context_graph.models import EntityKind, RelKind
from code_context_graph.parser import PythonASTParser


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    src = tmp_path / "src" / "myapp"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('"""My app."""\n')
    (src / "service.py").write_text(dedent("""\
        from __future__ import annotations
        from myapp.models import User

        class UserService:
            \"\"\"Manages user operations.\"\"\"

            def create_user(self, name: str) -> User:
                validate(name)
                return User(name=name)

            def delete_user(self, user_id: int) -> None:
                raise NotImplementedError("todo")

        def validate(name: str) -> None:
            if not name:
                raise ValueError("empty name")
    """))
    (src / "models.py").write_text(dedent("""\
        from pydantic import BaseModel

        class User(BaseModel):
            name: str
            email: str | None = None

        MAX_NAME_LENGTH = 100
    """))
    return tmp_path


def test_parse_finds_all_entities(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "service.py")

    names = {e.simple_name for e in result.entities}
    assert "UserService" in names
    assert "create_user" in names
    assert "delete_user" in names
    assert "validate" in names


def test_parse_captures_class_methods(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "service.py")

    methods = [e for e in result.entities if e.kind == EntityKind.METHOD]
    assert len(methods) == 2
    method_names = {m.simple_name for m in methods}
    assert method_names == {"create_user", "delete_user"}


def test_parse_extracts_imports(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "service.py")

    import_rels = [r for r in result.relationships if r.kind == RelKind.IMPORTS]
    targets = {r.target_qname for r in import_rels}
    assert "__future__.annotations" in targets
    assert "myapp.models.User" in targets


def test_parse_extracts_calls(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "service.py")

    call_rels = [r for r in result.relationships if r.kind == RelKind.CALLS]
    callees = {r.target_qname for r in call_rels}
    assert "validate" in callees
    assert "User" in callees


def test_parse_extracts_raises(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "service.py")

    raise_rels = [r for r in result.relationships if r.kind == RelKind.RAISES]
    exceptions = {r.target_qname for r in raise_rels}
    assert "NotImplementedError" in exceptions
    assert "ValueError" in exceptions


def test_parse_captures_inheritance(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "models.py")

    inherits = [r for r in result.relationships if r.kind == RelKind.INHERITS]
    assert any(r.source_qname.endswith("User") and r.target_qname == "BaseModel" for r in inherits)


def test_parse_captures_constants(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "models.py")

    constants = [e for e in result.entities if e.kind == EntityKind.CONSTANT]
    assert any(c.simple_name == "MAX_NAME_LENGTH" for c in constants)


def test_parse_captures_signatures(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "service.py")

    validate = next(e for e in result.entities if e.simple_name == "validate")
    assert "name: str" in validate.signature
    assert "-> None" in validate.signature


def test_parse_computes_complexity(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "service.py")

    validate = next(e for e in result.entities if e.simple_name == "validate")
    assert validate.complexity is not None
    assert validate.complexity >= 2  # base 1 + the `if`


def test_parse_docstrings(tmp_repo: Path) -> None:
    parser = PythonASTParser(tmp_repo)
    result = parser.parse_file(tmp_repo / "src" / "myapp" / "service.py")

    user_service = next(e for e in result.entities if e.simple_name == "UserService")
    assert user_service.docstring == "Manages user operations."


def test_parse_directory(tmp_repo: Path) -> None:
    from code_context_graph.parser import parse_directory

    results = parse_directory(tmp_repo)
    files = {r.file_path for r in results}
    assert len(files) == 3
    all_entities = [e for r in results for e in r.entities]
    assert len(all_entities) > 5


def test_parse_directory_handles_hidden_parent_directory(tmp_path: Path) -> None:
    from code_context_graph.parser import parse_directory

    repo_root = tmp_path / ".ccg" / "repos" / "owner" / "repo"
    repo_root.mkdir(parents=True)
    (repo_root / "app.py").write_text("def run() -> None:\n    pass\n")

    results = parse_directory(repo_root)

    assert [result.file_path for result in results] == ["app.py"]


def test_parse_directory_extracts_javascript_entities(tmp_path: Path) -> None:
    from code_context_graph.parser import parse_directory

    (tmp_path / "service.js").write_text(dedent("""\
        import express from "express";

        export function startServer() {
            return express();
        }

        class Router {
            handle() {
                startServer();
            }
        }
    """))

    result = next(r for r in parse_directory(tmp_path) if r.file_path == "service.js")
    entities = {(entity.kind, entity.simple_name) for entity in result.entities}
    calls = {rel.target_qname for rel in result.relationships if rel.kind == RelKind.CALLS}

    assert (EntityKind.FUNCTION, "startServer") in entities
    assert (EntityKind.CLASS, "Router") in entities
    assert (EntityKind.METHOD, "handle") in entities
    assert "startServer" in calls


def test_parse_directory_extracts_typescript_entities(tmp_path: Path) -> None:
    from code_context_graph.parser import parse_directory

    (tmp_path / "widget.ts").write_text(dedent("""\
        import { render } from "./render";

        export interface Widget {
            name: string;
        }

        export function buildWidget(name: string): Widget {
            return render(name);
        }
    """))

    result = next(r for r in parse_directory(tmp_path) if r.file_path == "widget.ts")
    names = {entity.simple_name for entity in result.entities}
    calls = {rel.target_qname for rel in result.relationships if rel.kind == RelKind.CALLS}

    assert "Widget" in names
    assert "buildWidget" in names
    assert "render" in calls


def test_parse_directory_extracts_go_entities(tmp_path: Path) -> None:
    from code_context_graph.parser import parse_directory

    (tmp_path / "main.go").write_text(dedent("""\
        package main

        import "fmt"

        type Server struct {}

        func Start() {
            fmt.Println("ok")
        }
    """))

    result = next(r for r in parse_directory(tmp_path) if r.file_path == "main.go")
    names = {entity.simple_name for entity in result.entities}
    calls = {rel.target_qname for rel in result.relationships if rel.kind == RelKind.CALLS}

    assert "Server" in names
    assert "Start" in names
    assert "fmt.Println" in calls


def test_parse_directory_extracts_rust_entities(tmp_path: Path) -> None:
    from code_context_graph.parser import parse_directory

    (tmp_path / "lib.rs").write_text(dedent("""\
        use std::fmt;

        struct Server;

        fn start() {
            println!("ok");
        }
    """))

    result = next(r for r in parse_directory(tmp_path) if r.file_path == "lib.rs")
    names = {entity.simple_name for entity in result.entities}
    calls = {rel.target_qname for rel in result.relationships if rel.kind == RelKind.CALLS}

    assert "Server" in names
    assert "start" in names
    assert "println!" in calls


def test_parse_directory_extracts_java_entities(tmp_path: Path) -> None:
    from code_context_graph.parser import parse_directory

    (tmp_path / "App.java").write_text(dedent("""\
        import java.util.List;

        public class App {
            public void run() {
                helper();
            }

            private void helper() {}
        }
    """))

    result = next(r for r in parse_directory(tmp_path) if r.file_path == "App.java")
    entities = {(entity.kind, entity.simple_name) for entity in result.entities}
    calls = {rel.target_qname for rel in result.relationships if rel.kind == RelKind.CALLS}

    assert (EntityKind.CLASS, "App") in entities
    assert (EntityKind.METHOD, "run") in entities
    assert (EntityKind.METHOD, "helper") in entities
    assert "helper" in calls
