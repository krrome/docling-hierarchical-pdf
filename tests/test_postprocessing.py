from pathlib import Path

from docling.document_converter import DocumentConverter

from hierarchical.postprocessor import ResultPostprocessor

results_path = Path(__file__).parent / "results"
sample_path = Path(__file__).parent / "samples"


def compare(res_text, fn):
    p = results_path / fn
    if p.exists():
        assert res_text.strip() == p.read_text().strip()
    else:
        p.write_text(res_text)


def test_result_postprocessor_textpdf():
    source = sample_path / "sample_document.pdf"  # document per local path or URL
    converter = DocumentConverter()
    result = converter.convert(source)
    ResultPostprocessor(result).process()

    compare(result.document.export_to_markdown(), "sample_document.md")

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


# def test_result_postprocessor_vlmpdf():
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
