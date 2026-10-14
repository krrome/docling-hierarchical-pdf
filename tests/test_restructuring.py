"""How `ResultPostprocessor.process` moves the items of a document below its headings.

Each test builds a small document, runs `process` with the given headings and compares the resulting tree, written
as an indented outline:

    # text      a heading (SectionHeaderItem)
    - text      a list item
    [list]      a list group
    [picture]   a picture
    text        any other text item

Only the tree is compared. Markdown hides most of these cases, as it renders a heading's level from the heading,
not from where it sits in the tree, but anything walking the tree (chunkers, JSON or HTML export) sees them.
"""

from textwrap import dedent
from types import SimpleNamespace

import pytest
from docling_core.types.doc import BoundingBox, DocItemLabel, DoclingDocument, GroupLabel, ProvenanceItem
from docling_core.types.doc.document import GroupItem, ListItem, NodeItem, PictureItem, SectionHeaderItem

from hierarchical.postprocessor import ResultPostprocessor

PROV = ProvenanceItem(page_no=1, bbox=BoundingBox(l=0, t=10, r=10, b=0), charspan=(0, 1))


def outline(doc: DoclingDocument) -> str:
    lines = []

    def walk(node: NodeItem, depth: int) -> None:
        for ref in node.children:
            item = ref.resolve(doc)
            if isinstance(item, SectionHeaderItem):
                line = f"# {item.text}"
            elif isinstance(item, ListItem):
                line = f"- {item.text}"
            elif isinstance(item, PictureItem):
                line = "[picture]"
            elif isinstance(item, GroupItem):
                line = f"[{item.label.value}]"
            else:
                line = item.text
            lines.append("    " * depth + line)
            walk(item, depth + 1)

    walk(doc.body, 0)
    return "\n".join(lines)


def process(monkeypatch: pytest.MonkeyPatch, doc: DoclingDocument, *headings: NodeItem) -> str:
    """Run `process` with `headings` as the detected headings (levels come from their numbering)."""
    detected = [
        {"text": h.text, "font_size": 12, "is_bold": False, "is_italic": False, "top_left": 0,
         "text_direction:": None, "font": "", "reference": h.self_ref}
        for h in headings
    ]  # fmt: skip
    # no PDF behind the document: no bookmarks, and the headings as given
    monkeypatch.setattr("hierarchical.postprocessor.HierarchyBuilderMetadata", lambda *args: SimpleNamespace(toc=[]))
    monkeypatch.setattr(ResultPostprocessor, "get_headers", lambda self: detected)
    ResultPostprocessor(SimpleNamespace(document=doc)).process()
    return outline(doc)


def expect(text: str) -> str:
    return dedent(text).strip("\n")


def test_list_stays_a_list(monkeypatch):
    doc = DoclingDocument(name="doc")
    intro = doc.add_heading(text="1 Intro", prov=PROV)
    group = doc.add_group(label=GroupLabel.LIST)
    doc.add_list_item(text="a", parent=group, prov=PROV)
    doc.add_list_item(text="b", parent=group, prov=PROV)
    doc.add_text(label=DocItemLabel.TEXT, text="closing", prov=PROV)

    # old code: the items were taken out of the list, leaving it empty:
    #     # 1 Intro
    #         [list]
    #         - a
    #         - b
    #         closing
    assert process(monkeypatch, doc, intro) == expect("""
        # 1 Intro
            [list]
                - a
                - b
            closing
    """)


def test_nested_list_keeps_nesting_and_reading_order(monkeypatch):
    doc = DoclingDocument(name="doc")
    intro = doc.add_heading(text="1 Intro", prov=PROV)
    group = doc.add_group(label=GroupLabel.LIST)
    first = doc.add_list_item(text="first", parent=group, prov=PROV)
    sublist = doc.add_group(label=GroupLabel.LIST, parent=first)
    doc.add_list_item(text="first.a", parent=sublist, prov=PROV)
    doc.add_list_item(text="first.b", parent=sublist, prov=PROV)
    doc.add_list_item(text="second", parent=group, prov=PROV)

    # old code: flattened, and "second" ended up before the sub-items of "first":
    #     # 1 Intro
    #         [list]
    #         - first
    #         - second
    #         [list]
    #         - first.a
    #         - first.b
    assert process(monkeypatch, doc, intro) == expect("""
        # 1 Intro
            [list]
                - first
                    [list]
                        - first.a
                        - first.b
                - second
    """)


def test_picture_keeps_its_caption(monkeypatch):
    doc = DoclingDocument(name="doc")
    intro = doc.add_heading(text="1 Intro", prov=PROV)
    picture = doc.add_picture(prov=PROV)
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="Figure 1", parent=picture, prov=PROV)
    picture.captions.append(caption.get_ref())

    # old code: the caption was taken out of its picture:
    #     # 1 Intro
    #         [picture]
    #         Figure 1
    assert process(monkeypatch, doc, intro) == expect("""
        # 1 Intro
            [picture]
                Figure 1
    """)


def test_top_level_heading_in_a_list_becomes_top_level(monkeypatch):
    # a numbered heading that docling recognized as a list item, in a document without a title
    doc = DoclingDocument(name="doc")
    intro = doc.add_heading(text="1 Intro", prov=PROV)
    doc.add_text(label=DocItemLabel.TEXT, text="intro text", prov=PROV)
    group = doc.add_group(label=GroupLabel.LIST)
    usage = doc.add_list_item(text="2 Usage", parent=group, prov=PROV)
    doc.add_text(label=DocItemLabel.TEXT, text="usage text", prov=PROV)

    # old code: "2 Usage" stayed in its list, so it ended up inside "1 Intro":
    #     # 1 Intro
    #         intro text
    #         [list]
    #             # 2 Usage
    #                 usage text
    assert process(monkeypatch, doc, intro, usage) == expect("""
        # 1 Intro
            intro text
            [list]
        # 2 Usage
            usage text
    """)


def test_two_top_level_headings_in_one_list(monkeypatch):
    doc = DoclingDocument(name="doc")
    intro = doc.add_heading(text="1 Intro", prov=PROV)
    group = doc.add_group(label=GroupLabel.LIST)
    usage = doc.add_list_item(text="2 Usage", parent=group, prov=PROV)
    doc.add_list_item(text="a", parent=group, prov=PROV)
    doc.add_list_item(text="b", parent=group, prov=PROV)
    faq = doc.add_list_item(text="3 FAQ", parent=group, prov=PROV)
    doc.add_text(label=DocItemLabel.TEXT, text="faq text", prov=PROV)

    # old code: both headings stayed in the list, so they ended up inside "1 Intro":
    #     # 1 Intro
    #         [list]
    #             # 2 Usage
    #                 - a
    #                 - b
    #             # 3 FAQ
    #                 faq text
    assert process(monkeypatch, doc, intro, usage, faq) == expect("""
        # 1 Intro
            [list]
        # 2 Usage
            [list]
                - a
                - b
        # 3 FAQ
            faq text
    """)


def test_list_split_by_a_heading_keeps_its_items_in_lists(monkeypatch):
    doc = DoclingDocument(name="doc")
    intro = doc.add_heading(text="1 Intro", prov=PROV)
    group = doc.add_group(label=GroupLabel.LIST)
    doc.add_list_item(text="a", parent=group, prov=PROV)
    details = doc.add_list_item(text="1.1 Details", parent=group, prov=PROV)
    doc.add_list_item(text="b", parent=group, prov=PROV)
    doc.add_list_item(text="c", parent=group, prov=PROV)

    # old code: the items were taken out of the list:
    #     # 1 Intro
    #         [list]
    #         - a
    #         # 1.1 Details
    #             - b
    #             - c
    assert process(monkeypatch, doc, intro, details) == expect("""
        # 1 Intro
            [list]
                - a
            # 1.1 Details
                [list]
                    - b
                    - c
    """)


def test_no_content_lost_if_toc_and_reading_order_disagree(monkeypatch):
    # The toc puts "1.1 Details" below "1 Overview", which comes later in the reading order, e.g. because the
    # bookmarks of a PDF don't match the reading order docling found.
    doc = DoclingDocument(name="doc")
    details = doc.add_heading(text="1.1 Details", prov=PROV)
    group = doc.add_group(label=GroupLabel.LIST)
    overview = doc.add_list_item(text="1 Overview", parent=group, prov=PROV)

    # old code: the list was moved below "1.1 Details", which it holds itself (via "1 Overview"): everything but
    # the body was cut off the document, the outline was empty
    assert process(monkeypatch, doc, overview, details) == expect("""
        [list]
        # 1 Overview
            # 1.1 Details
    """)
