from functools import cached_property
from io import BytesIO
from pathlib import PurePath
from typing import Optional, Union

from docling.datamodel.base_models import DocumentStream
from docling.datamodel.document import ConversionResult
from docling_core.types.doc.document import (
    DocItem,
    DocItemLabel,
    DoclingDocument,
    ListItem,
    NodeItem,
    RefItem,
    SectionHeaderItem,
    TextItem,
)

from hierarchical.hierarchy_builder import create_toc
from hierarchical.hierarchy_builder_metadata import HierarchyBuilderMetadata
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

    def _get_headers_result(self) -> list[dict]:
        items: list[dict] = []
        for item, _ in self.result.document.iterate_items():
            if not isinstance(item, SectionHeaderItem):
                continue
            prov = item.prov[0]
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
            if isinstance(item, SectionHeaderItem):
                prov = item.prov[0]
                items.append({
                    "text": " ".join(item.text.split("\n")),
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

        processed: list[str] = []
        last_len_processed = -1
        while last_len_processed < len(processed):
            last_len_processed = len(processed)
            for item, _ in self.result.document.iterate_items(with_groups=True):
                if item.self_ref in processed:
                    continue
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
                        if header_correction and isinstance(item, (TextItem, ListItem)):
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
                if new_parent_ref is not None and item.parent is not None and item.parent.cref == doc.body.self_ref:
                    old_parent = item.parent.resolve(doc)
                    new_parent = new_parent_ref.resolve(doc)
                    item_i = [i for i, c in enumerate(old_parent.children) if c.cref == item.self_ref]
                    if item_i:
                        child_ref = old_parent.children.pop(item_i[0])
                        item.parent = new_parent_ref
                        new_parent.children.append(child_ref)
                    else:
                        raise ItemNotRegisteredAsChildException(item)
                    break
                processed.append(item.self_ref)
