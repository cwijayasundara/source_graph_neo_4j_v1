import re

from code_context_graph.brd.schema import (
    BRD, BRDSection, Requirement, Strategy,
)
from code_context_graph.brd.renderer import render_html


def _sample_brd() -> BRD:
    return BRD(
        sections=[
            BRDSection(
                title="Executive Summary",
                body_markdown="A **bold** summary.\n\n- bullet 1\n- bullet 2",
                requirements=[],
            ),
            BRDSection(
                title="Functional Requirements",
                body_markdown="Core features:",
                requirements=[
                    Requirement(id="FR-1", text="System SHALL authenticate users."),
                    Requirement(id="FR-2", text="System SHALL log all auth events."),
                ],
            ),
        ],
        evidence_map={"FR-1": ["Function:src/auth.py:login"]},
        repo_id="acme-app",
        model="claude-opus-4-7[1m]",
        strategy=Strategy.single_shot,
    )


def test_render_produces_self_contained_html():
    html = render_html(_sample_brd())
    assert html.startswith("<!DOCTYPE html>")
    # no external assets
    assert 'src="http' not in html
    assert "<link " not in html
    assert "<script" not in html
    # inline style block present
    assert "<style>" in html


def test_render_includes_all_sections_and_requirements():
    html = render_html(_sample_brd())
    assert "Executive Summary" in html
    assert "Functional Requirements" in html
    assert "<strong>bold</strong>" in html  # markdown converted
    assert "FR-1" in html and "FR-2" in html
    assert "System SHALL authenticate users." in html


def test_render_escapes_html_in_user_content():
    brd = _sample_brd()
    brd.sections[0].body_markdown = "Watch out for <script>alert(1)</script>"
    html = render_html(brd)
    assert "<script>alert(1)</script>" not in html  # raw script must not survive
    assert "&lt;script&gt;" in html or "&lt;script&gt;alert" in html


def test_render_evidence_map_section():
    html = render_html(_sample_brd())
    assert "Evidence" in html
    assert "Function:src/auth.py:login" in html
