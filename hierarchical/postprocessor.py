from functools import cached_property
from io import BytesIO
from itertools import chain
from pathlib import PurePath
from typing import Optional, Union

from docling.datamodel.base_models import DocumentStream
from docling.datamodel.document import ConversionResult
from docling_core.types.doc.document import (
    DocItem,
    DocItemLabel,
    DoclingDocument,
    GroupItem,
    ListItem,
    NodeItem,
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

        # Nodes containing a header must release it, so they can't be moved as a whole.
        holds_header: set[str] = set()
        for ref in by_ref:
            parent = RefItem(cref=ref).resolve(doc).parent if ref is not None else None
            while parent is not None and parent.cref not in holds_header:
                holds_header.add(parent.cref)
                parent = parent.resolve(doc).parent
        # Nodes that were moved together with their subtree (e.g. a list with its sublists, a picture with its
        # captions). Their descendants stay where they are, which keeps the structure and the reading order.
        carried: set[str] = set()
        # Per parent, where its last child was moved from: its children are processed in order, so the next one
        # is usually found right there instead of by scanning past all the children that stayed.
        hint: dict[str, int] = {}
        # Top-level headers that were lifted out of a node into the body, and where the last one went.
        lifted: set[str] = set()
        lifted_at = 0
        # Groups split by a header (e.g. a list holding a numbered heading): the group their later items went to.
        continued: dict[str, GroupItem] = {}

        def is_within(node: NodeItem, item: NodeItem) -> bool:
            ancestor: Optional[NodeItem] = node
            while ancestor is not None:
                if ancestor.self_ref == item.self_ref:
                    return True
                ancestor = ancestor.parent.resolve(doc) if ancestor.parent is not None else None
            return False

        def move(item: NodeItem, old_parent: NodeItem, new_parent: NodeItem, position: Optional[int] = None) -> None:
            """Move `item` from `old_parent` into `new_parent`, at `position` or else at the end."""
            # Moving a node below itself would cut it off the document in a cycle. That happens when the toc puts
            # a header below one that comes later in the reading order and is still inside `item`: keep it in place.
            if is_within(new_parent, item):
                return
            children = old_parent.children
            start = hint.get(old_parent.self_ref, 0)
            item_i = next((i for i in range(start, len(children)) if children[i].cref == item.self_ref), None)
            if item_i is None:  # not after the hint, search all
                item_i = next((i for i, c in enumerate(children) if c.cref == item.self_ref), None)
            if item_i is None:
                raise ItemNotRegisteredAsChildException(item)
            hint[old_parent.self_ref] = item_i
            child_ref = children.pop(item_i)
            item.parent = new_parent.get_ref()
            if position is None:
                new_parent.children.append(child_ref)
            else:
                new_parent.children.insert(position, child_ref)
            if item.self_ref not in holds_header:
                carried.add(item.self_ref)

        # Moving items doesn't change the reading order, so the original order can be walked once.
        for ref in [item.self_ref for item, _ in doc.iterate_items(with_groups=True)]:
            # resolve anew, as the item may have been swapped by set_item_in_doc in the meantime
            item = RefItem(cref=ref).resolve(doc)
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
            if item.parent is not None and item.parent.cref in carried:
                # already moved along with its parent
                carried.add(item.self_ref)
            elif new_parent_ref is not None and item.parent is not None:
                old_parent = item.parent.resolve(doc)
                new_parent = new_parent_ref.resolve(doc)
                if (
                    isinstance(old_parent, GroupItem)
                    and old_parent.self_ref != doc.body.self_ref
                    and old_parent.self_ref in holds_header
                    and item.self_ref not in by_ref
                    and not is_within(new_parent, item)
                ):
                    # The group is split by a header, so it isn't moved as a whole. Keep its items in a group like
                    # it below the new parent instead of loosely: in the group itself if it is the last thing there,
                    # else in the group continuing it there, or in a new one.
                    last = new_parent.children[-1].cref if new_parent.children else None
                    if last == old_parent.self_ref:
                        if item.self_ref not in holds_header:
                            carried.add(item.self_ref)
                    else:
                        group = continued.get(old_parent.self_ref)
                        if group is None or last != group.self_ref:
                            group = doc.add_group(
                                label=old_parent.label,
                                name=old_parent.name,
                                parent=new_parent,
                                content_layer=old_parent.content_layer,
                            )
                            continued[old_parent.self_ref] = group
                        move(item, old_parent, group)
                else:
                    move(item, old_parent, new_parent)
            elif item.self_ref in by_ref and item.parent is not None and item.parent.cref != doc.body.self_ref:
                # A top-level header inside some node, e.g. a numbered heading that was put into a list, is lifted
                # into the body. Appending it would put it behind the unprocessed items, so it goes right after the
                # body-level node holding it: everything before the header is in or before that node, or is one
                # of the headers lifted there before.
                outer = item.parent
                while (
                    outer_parent := outer.resolve(doc).parent
                ) is not None and outer_parent.cref != doc.body.self_ref:
                    outer = outer_parent
                # that node is usually the header lifted last, so search from there
                body_children = doc.body.children
                start = min(lifted_at, len(body_children) - 1)
                position = 1 + next(
                    i
                    for i in chain(range(start, -1, -1), range(start + 1, len(body_children)))
                    if body_children[i].cref == outer.cref
                )
                while position < len(body_children) and body_children[position].cref in lifted:
                    position += 1
                move(item, item.parent.resolve(doc), doc.body, position)
                lifted.add(item.self_ref)
                lifted_at = position
