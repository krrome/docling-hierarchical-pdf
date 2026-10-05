import random
from types import SimpleNamespace
from typing import Optional

import pytest
from docling_core.types.doc import DocItemLabel, DoclingDocument, GroupLabel
from docling_core.types.doc.document import ContentLayer, ListItem, RefItem, SectionHeaderItem, TextItem

import hierarchical.postprocessor as hp
from hierarchical.types.hierarchical_header import HierarchicalHeader


def _restart_walk_process(self: hp.ResultPostprocessor) -> None:  # noqa: C901
    """`ResultPostprocessor.process` as of 0.1.9, which walks the document again after each moved item."""
    hbm = hp.HierarchyBuilderMetadata(self.result, self.source, self.raise_on_error)
    header_correction = False
    if len(hbm.toc) > 0:
        root = hbm.infer()
        if root.children:
            header_correction = True
    else:
        root = hp.create_toc(self.get_headers())
    doc = self.result.document
    by_ref = {el[0].doc_ref: el for el in hp.flatten_hierarchy_tree(root, 0)}
    current_header = root
    new_parent_ref = None
    processed: set[str] = set()
    last_len_processed = -1
    while last_len_processed < len(processed):
        last_len_processed = len(processed)
        for item, _ in self.result.document.iterate_items(with_groups=True):
            if item.self_ref in processed:
                continue
            if isinstance(item, SectionHeaderItem) and item.self_ref not in by_ref and header_correction:
                text_item = TextItem(
                    label=DocItemLabel.TEXT,
                    **{k: v for k, v in item.model_dump().items() if k != "label" and k in TextItem.model_fields},
                )
                hp.set_item_in_doc(doc, text_item)
                item = text_item
            if item.self_ref in by_ref:
                if not isinstance(item, SectionHeaderItem):
                    if isinstance(item, (TextItem, ListItem)):
                        header_item = SectionHeaderItem(**{
                            k: v
                            for k, v in item.model_dump().items()
                            if k != "label" and k in SectionHeaderItem.model_fields
                        })
                        if isinstance(item, ListItem):
                            header_item.text = header_item.orig
                        hp.set_item_in_doc(doc, header_item)
                        item = header_item
                    else:
                        raise hp.ItemInconsitencyException()
                current_header, level = by_ref[item.self_ref]
                new_parent_ref = (
                    RefItem(cref=current_header.parent.doc_ref)
                    if current_header.parent is not None and current_header.parent.doc_ref is not None
                    else None
                )
                item.level = level
            elif current_header.doc_ref is not None:
                if isinstance(item, SectionHeaderItem):
                    item.level = level + 1
                new_parent_ref = RefItem(cref=current_header.doc_ref)
            if new_parent_ref is not None and item.parent is None:
                raise hp.ItemNotRegisteredAsChildException(item)
            if new_parent_ref is not None and item.parent is not None:
                old_parent = item.parent.resolve(doc)
                new_parent = new_parent_ref.resolve(doc)
                item_i = [i for i, c in enumerate(old_parent.children) if c.cref == item.self_ref]
                if item_i:
                    child_ref = old_parent.children.pop(item_i[0])
                    item.parent = new_parent_ref
                    new_parent.children.append(child_ref)
                else:
                    raise hp.ItemNotRegisteredAsChildException(item)
                processed.add(item.self_ref)
                break
            processed.add(item.self_ref)


def _random_doc(r: random.Random):
    doc = DoclingDocument(name="t")
    containers: list = [None]
    lists, items = [], []
    for n in range(r.randint(1, r.choice([10, 40, 120]))):
        parent = r.choice(containers)
        layer = ContentLayer.FURNITURE if r.random() < 0.05 else None
        k = r.random()
        if k < 0.25:
            it = doc.add_heading(text=f"h{n}", level=r.randint(1, 3), parent=parent, content_layer=layer)
            if r.random() < 0.3:
                containers.append(it)
        elif k < 0.63 and r.random() < 0.8:
            it = doc.add_text(label=DocItemLabel.TEXT, text=f"t{n}", parent=parent, content_layer=layer)
        elif k < 0.7:
            it = doc.add_list_group(parent=parent, content_layer=layer)
            containers.append(it)
            lists.append(it)
        elif k < 0.8 and lists:
            it = doc.add_list_item(text=f"l{n}", parent=r.choice(lists), content_layer=layer)
        elif k < 0.88:
            it = doc.add_group(label=GroupLabel.SECTION, parent=parent, content_layer=layer)
            containers.append(it)
        else:
            it = doc.add_picture(parent=parent, content_layer=layer)
            if r.random() < 0.6:
                cap = doc.add_text(label=DocItemLabel.CAPTION, text=f"c{n}", parent=it)
                it.captions.append(cap.get_ref())
                items.append(cap)
            if r.random() < 0.4:
                items.append(doc.add_text(label=DocItemLabel.TEXT, text=f"hidden{n}", parent=it))
        items.append(it)
    return doc, items


def _random_hierarchy(r: random.Random, items) -> HierarchicalHeader:
    root, nodes, seen = HierarchicalHeader(), [], set()
    textual = r.random() < 0.95
    for it in items:
        if r.random() > 0.35 or it.self_ref in seen or (textual and not isinstance(it, (TextItem, ListItem))):
            continue
        seen.add(it.self_ref)
        parent = r.choice([*nodes[-3:], root])
        node = HierarchicalHeader(parent=parent, doc_ref=it.self_ref)
        parent.children.append(node)
        nodes.append(node)
    return root


@pytest.fixture
def hierarchy(monkeypatch):
    """Feed `process` a given hierarchy, as if inferred from the PDF."""
    state: dict = {}
    monkeypatch.setattr(
        hp,
        "HierarchyBuilderMetadata",
        lambda result, source, raise_on_error: SimpleNamespace(
            toc=[1] if state["header_correction"] else [], infer=lambda: state["root"]
        ),
    )
    monkeypatch.setattr(hp, "create_toc", lambda headings: state["root"])
    monkeypatch.setattr(hp.ResultPostprocessor, "get_headers", lambda self: [])

    def set_(root: HierarchicalHeader, header_correction: bool) -> None:
        state.update(root=root, header_correction=header_correction)

    return set_


def _run(process, doc: DoclingDocument) -> tuple[str, Optional[str]]:
    copy = doc.model_copy(deep=True)
    try:
        process(hp.ResultPostprocessor(SimpleNamespace(document=copy)))
    except Exception as e:
        return copy.model_dump_json(), type(e).__name__
    return copy.model_dump_json(), None


def test_walk_matches_the_restart_walk_on_random_documents(hierarchy):
    """Nested groups, lists, pictures with captions and hidden children, furniture, header correction."""
    r = random.Random(20261004)  # noqa: S311
    for _ in range(400):
        doc, items = _random_doc(r)
        hierarchy(_random_hierarchy(r, items), r.random() < 0.5)
        assert _run(hp.ResultPostprocessor.process, doc) == _run(_restart_walk_process, doc)


def test_walk_does_not_restart_on_a_plain_document(hierarchy, monkeypatch):
    doc = DoclingDocument(name="t")
    root = HierarchicalHeader()
    for n in range(300):
        if n % 10 == 0:
            h = doc.add_heading(text=f"h{n}", level=1)
            root.children.append(HierarchicalHeader(parent=root, doc_ref=h.self_ref))
        else:
            doc.add_text(label=DocItemLabel.TEXT, text=f"t{n}")
    hierarchy(root, False)
    expected = _run(_restart_walk_process, doc)
    iterate = DoclingDocument.iterate_items
    monkeypatch.setattr(DoclingDocument, "iterate_items", lambda *a, **k: pytest.fail("walked from the top"))

    assert _run(hp.ResultPostprocessor.process, doc) == expected
    monkeypatch.setattr(DoclingDocument, "iterate_items", iterate)


def test_a_document_that_is_not_a_tree_falls_back_to_the_restart_walk(hierarchy):
    doc = DoclingDocument(name="t")
    h = doc.add_heading(text="h", level=1)
    group = doc.add_group(label=GroupLabel.SECTION)
    t = doc.add_text(label=DocItemLabel.TEXT, text="t")
    group.children.append(t.get_ref())  # listed under the body and the group
    root = HierarchicalHeader()
    root.children.append(HierarchicalHeader(parent=root, doc_ref=h.self_ref))
    hierarchy(root, False)

    assert hp._Walk(doc).fallback is True
    assert _run(hp.ResultPostprocessor.process, doc) == _run(_restart_walk_process, doc)
