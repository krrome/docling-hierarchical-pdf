from functools import cached_property
from io import BytesIO
from pathlib import PurePath
from typing import Optional, Union

from docling.datamodel.base_models import DocumentStream
from docling.datamodel.document import ConversionResult
from docling_core.types.doc.document import (
    DEFAULT_CONTENT_LAYERS,
    DocItem,
    DocItemLabel,
    DoclingDocument,
    ListItem,
    NodeItem,
    PictureItem,
    RefItem,
    SectionHeaderItem,
    TextItem,
)

from hierarchical.hierarchy_builder import create_toc
from hierarchical.hierarchy_builder_metadata import HierarchyBuilderMetadata
from hierarchical.parsers import infer_header_level_letter, infer_header_level_numerical, infer_header_level_roman
from hierarchical.types.hierarchical_header import HierarchicalHeader


class DoclingResultNotReadyException(Exception):
    def __init__(self) -> None:
        super().__init__("It seems that the docling result has not been filled / is not ready for postprocessing.")


class ItemNotRegisteredAsChildException(Exception):
    def __init__(self, item: NodeItem):
        super().__init__(f"The item {item} does not seem to be registered as a child of its parent node!")


class ItemInconsitencyException(Exception):
    pass


def flatten_hierarchy_tree(node: HierarchicalHeader, parent_level: int = 0) -> list[tuple[HierarchicalHeader, int]]:
    children = []
    this_level = parent_level + 1
    for c in node.children:
        children.append((c, this_level))
        children.extend(flatten_hierarchy_tree(c, this_level))
    return children


def set_item_in_doc(doc: DoclingDocument, item: DocItem) -> None:
    _, path, index_str = item.self_ref.split("/")
    index = int(index_str)
    doc.__getattribute__(path)[index] = item
    item = item


class _Walk:
    """The first unprocessed item in `iterate_items(with_groups=True)` order, kept current as items move.

    Counts the unprocessed items of every subtree and keeps, per node, the index of its first child that still
    has some, so `process` finds its next item without walking the document again from the top. A document that
    is not a plain tree falls back to that full walk.
    """

    def __init__(self, doc: DoclingDocument):
        self.doc = doc
        self.processed: set[str] = set()
        self.count: dict[str, int] = {}
        self.parent: dict[str, Optional[str]] = {}
        self.start: dict[str, int] = {}
        try:
            self.fallback = not self._index()
        except Exception:  # a broken reference then fails in iterate_items, at the same point as before
            self.fallback = True

    def _visible_children(self, node: NodeItem) -> list[NodeItem]:
        # Same rule as DoclingDocument.iterate_items: under a picture, only its captions are walked.
        captions = {r.cref for r in node.captions} if isinstance(node, PictureItem) else None
        children = []
        for ref in node.children:
            child = ref.resolve(self.doc)
            if isinstance(child, NodeItem) and (captions is None or child.self_ref in captions):
                children.append(child)
        return children

    def _index(self) -> bool:
        order = []
        stack: list[tuple[NodeItem, Optional[str]]] = [(self.doc.body, None)]
        while stack:
            node, parent = stack.pop()
            if node.self_ref in self.parent:
                return False
            self.parent[node.self_ref] = parent
            self.start[node.self_ref] = 0
            order.append(node)
            stack.extend((child, node.self_ref) for child in reversed(self._visible_children(node)))
        for node in reversed(order):
            ref = node.self_ref
            self.count[ref] = self.count.get(ref, 0) + (node.content_layer in DEFAULT_CONTENT_LAYERS)
            parent = self.parent[ref]
            if parent is not None:
                self.count[parent] = self.count.get(parent, 0) + self.count[ref]
        return True

    def next(self) -> Optional[NodeItem]:
        if self.fallback:
            return next(
                (item for item, _ in self.doc.iterate_items(with_groups=True) if item.self_ref not in self.processed),
                None,
            )
        ref = self.doc.body.self_ref
        if self.count[ref] == 0:
            return None
        while True:
            node: NodeItem = RefItem(cref=ref).resolve(self.doc)
            if ref not in self.processed and node.content_layer in DEFAULT_CONTENT_LAYERS:
                return node
            children = node.children
            i = self.start[ref]
            while self.count.get(children[i].cref, 0) == 0:
                i += 1
            self.start[ref] = i
            ref = children[i].cref

    def index_in(self, item: NodeItem, parent: NodeItem) -> Optional[int]:
        """The first index of `item` in `parent.children`: where `next` found it, else by a scan."""
        children = parent.children
        i = None if self.fallback else self.start.get(parent.self_ref)
        if i is not None and i < len(children) and children[i].cref == item.self_ref:
            return i  # a plain tree lists each child once
        return next((i for i, c in enumerate(children) if c.cref == item.self_ref), None)

    def mark(self, item: NodeItem) -> None:
        ref: Optional[str] = item.self_ref
        self.processed.add(item.self_ref)
        if self.fallback:
            return
        while ref is not None:
            self.count[ref] -= 1
            ref = self.parent[ref]

    def _under(self, ref: Optional[str], ancestor: str) -> bool:
        while ref is not None:
            if ref == ancestor:
                return True
            ref = self.parent[ref]
        return False

    def moved(self, item: NodeItem, old_parent: NodeItem, index: int, new_parent: NodeItem) -> None:
        """Record that `item`, already marked, was popped from `old_parent.children[index]` and appended to `new_parent`."""
        if self.fallback:
            return
        ref, old, new = item.self_ref, old_parent.self_ref, new_parent.self_ref
        if (
            self.parent.get(ref) != old
            or new not in self.parent
            or isinstance(new_parent, PictureItem)
            or self._under(new, ref)
        ):
            self.fallback = True
            return
        if index < self.start[old]:
            self.start[old] -= 1
        self.parent[ref] = new
        moved = self.count[ref]
        if not moved:
            return
        node: Optional[str] = old
        while node is not None:
            self.count[node] -= moved
            node = self.parent[node]
        self.count[new] += moved
        child, node = new, self.parent[new]
        while node is not None:
            self.count[node] += moved
            children = RefItem(cref=node).resolve(self.doc).children
            j = next(k for k, r in enumerate(children) if r.cref == child)
            if j < self.start[node]:
                self.start[node] = j
            child, node = node, self.parent[node]


class ResultPostprocessor:
    def __init__(
        self,
        result: ConversionResult,
        source: Optional[Union[PurePath, str, DocumentStream, BytesIO]] = None,
        raise_on_error: bool = False,
    ):
        self.result = result
        self.source = source
        self.raise_on_error = raise_on_error

    @cached_property
    def has_hierarchy_levels(self) -> bool:
        levels = set()
        for _, level in self.result.document.iterate_items():
            levels.add(level)

        return len(levels) > 1

    @staticmethod
    def _is_list_item_header(item: ListItem) -> bool:
        text = (item.orig if item.orig else item.text).strip()
        return bool(
            infer_header_level_numerical(text) or infer_header_level_letter(text) or infer_header_level_roman(text)
        )

    def _get_headers_result(self) -> list[dict]:
        items: list[dict] = []
        for item, _ in self.result.document.iterate_items():
            if not isinstance(item, SectionHeaderItem) and (
                not isinstance(item, ListItem) or not self._is_list_item_header(item)
            ):
                continue
            # item is now guaranteed to be a relevant header

            prov = item.prov[0]

            # For ListItems, we can't match clusters, so add them directly
            if isinstance(item, ListItem):
                text_to_use = item.orig if hasattr(item, "orig") and item.orig else item.text
                items.append({
                    "text": " ".join(text_to_use.split("\n")),
                    "font_size": prov.bbox.height,
                    "is_bold": False,
                    "is_italic": False,
                    "top_left": prov.bbox.t,
                    "text_direction:": None,
                    "font": "",
                    "reference": item.self_ref,
                })
                continue

            page = self.result.pages[prov.page_no - 1]
            if page.predictions.layout is None:
                return items
            for cluster in page.predictions.layout.clusters:
                if not cluster or cluster.label != "section_header":
                    continue
                first_cell = cluster.cells[0]
                if page.size is None:
                    raise DoclingResultNotReadyException()
                if (
                    prov.bbox.intersection_area_with(
                        first_cell.rect.to_bounding_box().to_bottom_left_origin(page_height=page.size.height)
                    )
                    == first_cell.rect.to_bounding_box().area()
                ):
                    font_split = first_cell.font_name.split("-") if hasattr(first_cell, "font_name") else [""]
                    items.append({
                        "text": " ".join([cell.text for cell in cluster.cells]),
                        "font_size": first_cell.rect.height,
                        "is_bold": "Bold" in font_split[1] if len(font_split) > 1 else False,
                        "is_italic": "Italic" in font_split[1] if len(font_split) > 1 else False,
                        "top_left": first_cell.rect.r_y0,
                        "text_direction:": first_cell.text_direction,
                        "font": font_split[0],
                        "reference": item.self_ref,
                    })
                    break
        return items

    def _get_headers_document(self) -> list[dict]:
        items = []
        for item, _ in self.result.document.iterate_items():
            if not isinstance(item, SectionHeaderItem) and (
                not isinstance(item, ListItem) or not self._is_list_item_header(item)
            ):
                continue
            # item is now guaranteed to be a relevant header

            prov = item.prov[0]
            # For ListItems, use orig field which contains full text with marker
            text_to_use = item.orig if isinstance(item, ListItem) and hasattr(item, "orig") and item.orig else item.text
            items.append({
                "text": " ".join(text_to_use.split("\n")),
                "font_size": prov.bbox.height,
                "is_bold": False,
                "is_italic": False,
                "top_left": prov.bbox.t,
                "text_direction:": None,
                "font": "",
                "reference": item.self_ref,
            })
        return items

    def get_headers(self) -> list[dict]:
        if not (items := self._get_headers_result()):
            return self._get_headers_document()
        return items

    def process(self) -> None:  # noqa: C901
        hbm = HierarchyBuilderMetadata(self.result, self.source, self.raise_on_error)
        header_correction = False
        if len(hbm.toc) > 0:
            root = hbm.infer()
            if root.children:
                header_correction = True
        else:
            headings = self.get_headers()
            root = create_toc(headings)
        doc = self.result.document
        # convert structure back to heading levels
        flat_hierarchy = flatten_hierarchy_tree(root, 0)
        # enable lookup by index
        by_ref = {el[0].doc_ref: el for el in flat_hierarchy}
        # maybe it is enough to alter the parent, pop the element from the current parent's children and add them to the new parent's children?
        current_header = root
        new_parent_ref = None

        walk = _Walk(doc)
        while True:
            item = walk.next()
            if item is None:
                break
            if isinstance(item, SectionHeaderItem) and item.self_ref not in by_ref and header_correction:
                # convert SectionHeaderItem to TextItem
                text_item = TextItem(
                    label=DocItemLabel.TEXT,
                    **{k: v for k, v in item.model_dump().items() if k != "label" and k in TextItem.model_fields},
                )
                # now swap the reference to SectionHeaderItem with the one of text_item in the doc.
                set_item_in_doc(doc, text_item)
                item = text_item
            if item.self_ref in by_ref:
                if not isinstance(item, SectionHeaderItem):
                    if isinstance(item, (TextItem, ListItem)):
                        header_item = SectionHeaderItem(**{
                            k: v
                            for k, v in item.model_dump().items()
                            if k != "label" and k in SectionHeaderItem.model_fields
                        })
                        # in case heading was numbered and the text was intepreted as a listitem
                        if isinstance(item, ListItem):
                            header_item.text = header_item.orig
                        # now swap the reference to TextItem with the one of header_item in the doc.
                        set_item_in_doc(doc, header_item)
                        item = header_item
                    else:
                        raise ItemInconsitencyException()
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
                # restructuring is needed
                new_parent_ref = RefItem(cref=current_header.doc_ref)
            if new_parent_ref is not None and item.parent is None:
                raise ItemNotRegisteredAsChildException(item)
            move = None
            if new_parent_ref is not None and item.parent is not None:
                old_parent = item.parent.resolve(doc)
                new_parent = new_parent_ref.resolve(doc)
                item_i = walk.index_in(item, old_parent)
                if item_i is None:
                    raise ItemNotRegisteredAsChildException(item)
                child_ref = old_parent.children.pop(item_i)
                item.parent = new_parent_ref
                new_parent.children.append(child_ref)
                move = (old_parent, item_i, new_parent)
            walk.mark(item)
            if move is not None:
                walk.moved(item, *move)
