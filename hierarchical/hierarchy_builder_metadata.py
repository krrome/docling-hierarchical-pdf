import re
from collections.abc import Generator
from contextlib import contextmanager
from functools import cached_property
from io import BytesIO
from logging import Logger
from pathlib import Path, PurePath
from typing import Optional, Union

from docling.datamodel.base_models import DocumentStream
from docling.datamodel.document import ConversionResult
from docling_core.types.doc import BoundingBox, ListItem, TextItem
from pymupdf import Document as FitzDocument

from .types.hierarchical_header import HierarchicalHeader

logger = Logger(__name__)


class HeaderNotFoundException(Exception):
    def __init__(self, heading: dict):
        super().__init__(f"Following heading was not found in the document: {heading}")


class ImplausibleHeadingStructureException(Exception):
    def __init__(self) -> None:
        super().__init__("Hierarchy demands equal level heading, but no common parent was found!")


class PDFFileNotFoundException(Exception):
    def __init__(self, path: PurePath) -> None:
        super().__init__(f"PDF file {path} does not exist!")


class PDFFileStreamClosed(Exception):
    def __init__(self) -> None:
        super().__init__("The (byte)stream of the PDF was closed. Can't process this input for ToC extraction.")


class InvalidSourceTypeException(Exception):
    pass


class HierarchyBuilderMetadata:
    def __init__(
        self,
        conv_res: ConversionResult,
        source: Optional[Union[PurePath, str, DocumentStream, BytesIO]] = None,
        raise_on_error: bool = False,
    ):
        self.conv_res: ConversionResult = conv_res
        self.source: Optional[Union[PurePath, str, DocumentStream, BytesIO]] = source
        self.raise_on_error: bool = raise_on_error

    @cached_property
    def toc(self) -> list[tuple]:
        return self._extract_toc()

    @contextmanager
    def _get_source_kwargs(self) -> Generator[dict]:
        source = self.source
        if source is None:
            source = self.conv_res.input.file
        if isinstance(source, str):
            source = Path(source)
        if isinstance(source, PurePath):
            if not Path(source).exists():
                raise PDFFileNotFoundException(source)
            else:
                yield {"filename": str(source)}
        elif isinstance(source, DocumentStream):
            stream = source.stream
            if stream.closed:
                raise PDFFileStreamClosed()
            else:
                stream.seek(0)
                yield {"filetype": str(self.conv_res.input.file), "stream": stream}
        elif isinstance(source, BytesIO):
            stream = source
            if stream.closed:
                raise PDFFileStreamClosed()
            else:
                stream.seek(0)
                yield {"filetype": str(self.conv_res.input.file), "stream": stream}
        else:
            raise InvalidSourceTypeException()

    def _extract_toc(self) -> list[tuple]:  # noqa: C901
        toc_output = []
        try:
            with self._get_source_kwargs() as kwargs:
                doc = FitzDocument(**kwargs)
                toc = doc.get_toc(  # type: ignore[attr-defined]
                    simple=False
                )  # gives a list of lists [<hierarchy level>, <Header name>, <pdf-page number>, <dict of additional information including position of the bookmark>]
                # pages_dicts = {}
                for level, title, page, add_info in toc:
                    # alternative
                    rects = doc[page - 1].search_for(title)
                    # doc[page - 1].get_pixmap(clip=rects[0]).save("rect_x.png")
                    this_bbox = None
                    for b in rects:
                        if this_bbox is None:
                            this_bbox = BoundingBox(l=b.x0, t=b.y0, r=b.x1, b=b.y1)
                        else:
                            this_bbox = BoundingBox(
                                l=min(b.x0, this_bbox.l),
                                t=min(b.y0, this_bbox.t),
                                r=max(b.x1, this_bbox.r),
                                b=max(b.y1, this_bbox.b),
                            )
                    if this_bbox:
                        add_info["coords"] = this_bbox
                    # sometimes the bookmark still points to the previous page, but the header is at the top of the current page
                    # future todo - instead of this try to use the offset of the bookmark pointer!
                    for page_here in [page, page + 1]:
                        if "coords" not in add_info:
                            title_ref = re.sub(r"[^A-Za-z0-9]", "", title)
                            actual_title = ""
                            accum_blocks: list[tuple] = []
                            for block in doc[page_here - 1].get_textpage().extractBLOCKS():
                                potential_title = re.sub(r"[^A-Za-z0-9]", "", block[4])
                                if potential_title == title_ref and not accum_blocks:
                                    actual_title += potential_title
                                    add_info["coords"] = BoundingBox(l=block[0], t=block[1], r=block[2], b=block[3])
                                    add_info["actual_title"] = actual_title
                                    page = page_here
                                    break
                                elif potential_title and title_ref.startswith(potential_title):
                                    accum_blocks.append(block)
                                    actual_title += potential_title
                                    title_ref = title_ref[len(potential_title) :]
                                    if len(title_ref) == 0:
                                        this_bbox = None
                                        for b in accum_blocks:
                                            if this_bbox is None:
                                                this_bbox = BoundingBox(l=b[0], t=b[1], r=b[2], b=b[3])
                                            else:
                                                this_bbox = BoundingBox(
                                                    l=min(b[0], this_bbox.l),
                                                    t=min(b[1], this_bbox.t),
                                                    r=max(b[2], this_bbox.r),
                                                    b=max(b[3], this_bbox.b),
                                                )
                                        add_info["coords"] = this_bbox
                                        add_info["actual_title"] = actual_title
                                        page = page_here
                                        break
                        if "coords" in add_info:
                            break
                    if "coords" not in add_info:
                        logger.warning(f"WARNING: Could not find title '{title}', which was mentioned in TOC. ")
                    toc_output.append((level, title, page, add_info))
        except (InvalidSourceTypeException, PDFFileStreamClosed, PDFFileNotFoundException) as e:
            if self.raise_on_error:
                raise
            else:
                logger.warning(e)
        return toc_output

    def infer(self) -> HierarchicalHeader:
        heading_to_level = self._extract_toc()
        root = HierarchicalHeader()
        current = root
        doc = self.conv_res.document

        for level, title, page, add_info in heading_to_level:
            new_parent = None
            this_item = None
            # identify the text item in the document
            for item, _ in doc.iterate_items(page_no=page):
                # Future to do: fixme - better to look for an overlap with the 'to' pointer if possible...
                if isinstance(item, (TextItem, ListItem)) and re.sub(r"[^A-Za-z0-9]", "", title) == re.sub(
                    r"[^A-Za-z0-9]", "", item.orig
                ):
                    this_item = item
                    break
            if this_item is None:
                if self.raise_on_error:
                    raise HeaderNotFoundException(add_info)
                else:
                    logger.warning(HeaderNotFoundException(add_info))
                    continue

            if current.level_toc is None or level > current.level_toc:
                # print(f"gt: {this_fs_level, this_style_attr} VS: {current.level_fontsize, current.style_attrs}")
                new_parent = current
            elif level == current.level_toc:
                # print(f"eq: {this_fs_level, this_style_attr} VS: {current.level_fontsize, current.style_attrs}")
                if current.parent is not None:
                    new_parent = current.parent
                else:
                    raise ImplausibleHeadingStructureException()
            else:
                # go back up in hierarchy and try to find a new parent
                new_parent = current
                while new_parent.parent is not None and (level <= new_parent.level_toc):
                    new_parent = new_parent.parent
                # print(f"fit parent for : {this_fs_level, this_style_attr} parent: {new_parent.level_fontsize, new_parent.style_attrs}")
            new_obj = HierarchicalHeader(
                text=this_item.orig,
                parent=new_parent,
                level_toc=level,
                doc_ref=this_item.self_ref,
            )
            new_parent.children.append(new_obj)
            current = new_obj

        return root
