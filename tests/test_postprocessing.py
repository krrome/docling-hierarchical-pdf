from io import BytesIO
from pathlib import Path

import pytest
from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter

from hierarchical.hierarchy_builder_metadata import PDFFileNotFoundException, PDFFileStreamClosed
from hierarchical.postprocessor import ResultPostprocessor

results_path = Path(__file__).parent / "results"
sample_path = Path(__file__).parent / "samples"


def compare(res_text, fn):
    p = results_path / fn
    if p.exists():
        assert res_text.strip() == p.read_text().strip()
    else:
        p.write_text(res_text)


@pytest.mark.skip(reason="runs too long for circleci.")
def test_nfl():
    source = sample_path / "2025-nfl-rulebook-final.pdf"  # document per local path or URL
    converter = DocumentConverter()
    result = converter.convert(source)
    ResultPostprocessor(result).process()

    headers = ResultPostprocessor(result)._get_headers_document()
    assert len(headers) > 0


def test_result_postprocessor_textpdf_no_bookmarks():
    source = sample_path / "sample_document_no_bookmarks.pdf"  # document per local path or URL
    converter = DocumentConverter()
    result = converter.convert(source)
    ResultPostprocessor(result).process()

    compare(result.document.export_to_markdown(), "sample_document_no_bookmarks.md")

    allowed_headers = [
        "Some kind of text document",
        "1. Introduction",
        "1.1 Background",
        "1.2 Purpose",
        "2. Main Content",
        "2.1 Section One",
        "2.1.1 Subsection",
        "2.1.2 Another Subsection",
        "2.2 Section Two",
        "3. Conclusion",
    ]

    for item_ref in result.document.body.children:
        item = item_ref.resolve(result.document)
        assert item.text in allowed_headers


def test_result_postprocessor_textpdf():
    source = sample_path / "sample_document.pdf"  # document per local path or URL
    converter = DocumentConverter()
    result = converter.convert(source)
    ResultPostprocessor(result).process()

    compare(result.document.export_to_markdown(), "sample_document.md")

    allowed_headers_res = [item_ref.resolve(result.document).text for item_ref in result.document.body.children]
    print(allowed_headers_res)

    allowed_headers = [
        "Some kind of text document",
        "1. Introduction",
        "1.1 Background",
        "1.2 Purpose",
        "2. Main Content",
        "2.1 Section One",
        "2.1.1 Subsection",
        "2.1.2 Another Subsection",
        "2.2 Section Two",
        "3. Conclusion",
    ]

    for item_ref in result.document.body.children:
        item = item_ref.resolve(result.document)
        assert item.text in allowed_headers


def test_result_postprocessor_textpdf_stream():
    source_path = sample_path / "sample_document.pdf"  # document per local path or URL
    with source_path.open("rb") as fh:
        source = DocumentStream(name=source_path.name, stream=BytesIO(fh.read()))
    converter = DocumentConverter()
    result = converter.convert(source)
    try:
        ResultPostprocessor(result, raise_on_error=True).process()
        raise Exception("FAIL NO STREAM!")  # noqa: TRY002 TRY003
    except PDFFileNotFoundException:
        pass
    try:
        ResultPostprocessor(result, source=source, raise_on_error=True).process()
        raise Exception("FAIL STREAM CLOSED!")  # noqa: TRY002 TRY003
    except PDFFileStreamClosed:
        pass

    with source_path.open("rb") as fh:
        source = DocumentStream(name=source_path.name, stream=BytesIO(fh.read()))
    ResultPostprocessor(result, source=source, raise_on_error=True).process()

    compare(result.document.export_to_markdown(), "sample_document.md")

    allowed_headers_res = [item_ref.resolve(result.document).text for item_ref in result.document.body.children]
    print(allowed_headers_res)

    allowed_headers = [
        "Some kind of text document",
        "1. Introduction",
        "1.1 Background",
        "1.2 Purpose",
        "2. Main Content",
        "2.1 Section One",
        "2.1.1 Subsection",
        "2.1.2 Another Subsection",
        "2.2 Section Two",
        "3. Conclusion",
    ]

    for item_ref in result.document.body.children:
        item = item_ref.resolve(result.document)
        assert item.text in allowed_headers


def test_result_postprocessor_textpdf_string():
    source_path = sample_path / "sample_document.pdf"  # document per local path or URL
    source = str(source_path)
    converter = DocumentConverter()
    result = converter.convert(source)
    ResultPostprocessor(result, source=source).process()

    compare(result.document.export_to_markdown(), "sample_document.md")

    allowed_headers_res = [item_ref.resolve(result.document).text for item_ref in result.document.body.children]
    print(allowed_headers_res)

    allowed_headers = [
        "Some kind of text document",
        "1. Introduction",
        "1.1 Background",
        "1.2 Purpose",
        "2. Main Content",
        "2.1 Section One",
        "2.1.1 Subsection",
        "2.1.2 Another Subsection",
        "2.2 Section Two",
        "3. Conclusion",
    ]

    for item_ref in result.document.body.children:
        item = item_ref.resolve(result.document)
        assert item.text in allowed_headers


@pytest.mark.skip(
    reason="just another example like test_result_postprocessor_textpdf. Not necessary for automated tests."
)
def test_result_postprocessor_textpdf_toc():
    source = (
        sample_path / "7261551c-3618-4641-81bb-08b101b3f5ad--Anmeldeformular%201%20ZLE%20Extern_d.pdf"
    )  # document per local path or URL
    converter = DocumentConverter()
    result = converter.convert(source)
    ResultPostprocessor(result).process()

    compare(
        result.document.export_to_markdown(),
        "7261551c-3618-4641-81bb-08b101b3f5ad--Anmeldeformular%201%20ZLE%20Extern_d.md",
    )


@pytest.mark.skip(
    reason="just another example like test_result_postprocessor_textpdf. Not necessary for automated tests."
)
def test_result_postprocessor_textpdf_toc_r10():
    source = sample_path / "R-10-00.pdf"  # document per local path or URL
    converter = DocumentConverter()
    result = converter.convert(source)
    ResultPostprocessor(result).process()

    compare(
        result.document.export_to_markdown(),
        "R-10-00.md",
    )


# vlm tests take way too long for automatic testing
# def test_result_postprocessor_vlmpdf():
#     from docling.datamodel.base_models import InputFormat
#     from docling.document_converter import DocumentConverter, PdfFormatOption
#     from docling.pipeline.vlm_pipeline import VlmPipeline

#     source = "/mnt/hgfs/virtual_machines/HRDH/HRDH/images/1401.3699/file_3pages.pdf"  # document per local path or URL

#     converter = DocumentConverter(
#         format_options={
#             InputFormat.PDF: PdfFormatOption(
#                 pipeline_cls=VlmPipeline,
#             ),
#         }
#     )
#     result = converter.convert(source=source)
#     ResultPostprocessor(result).process()

#     result.document.body.children
#     from pathlib import Path

#     Path("1401.3699.output.md").write_text(result.document.export_to_markdown())

#     for item_ref in result.document.body.children:
#         item = item_ref.resolve(result.document)
#         print(item)
#         print("---------------------------------------")
