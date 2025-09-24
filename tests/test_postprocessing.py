from pathlib import Path

from docling.document_converter import DocumentConverter

from hierarchical.postprocessor import ResultPostprocessor


def test_result_postprocessor_textpdf():
    source = "R-10-00.pdf"  # document per local path or URL
    converter = DocumentConverter()
    result = converter.convert(source)
    ResultPostprocessor(result).process()

    Path("R10.10.output.md").write_text(result.document.export_to_markdown())

    for item_ref in result.document.body.children:
        item = item_ref.resolve(result.document)
        print(item)
        print("---------------------------------------")


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
