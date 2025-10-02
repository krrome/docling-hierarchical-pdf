# docling-hierarchical-pdf

[![Commit activity](https://img.shields.io/github/commit-activity/m/krrome/docling-hierarchical-pdf)](https://img.shields.io/github/commit-activity/m/krrome/docling-hierarchical-pdf)
[![License](https://img.shields.io/github/license/krrome/docling-hierarchical-pdf)](https://img.shields.io/github/license/krrome/docling-hierarchical-pdf)

This package enables inference of header hierarchy in the docling PDF parsing pipeline.

The docs are still in the making, but as a user all you need is:

Install it:
```bash
pip install docling-hierarchical-pdf
```

Use it:
```python
from docling.document_converter import DocumentConverter
from hierarchical.postprocessor import ResultPostprocessor

source = "my_file.pdf"  # document per local path or URL
converter = DocumentConverter()
result = converter.convert(source)
# the postprocessor modifies the result.document in place.
ResultPostprocessor(result).process()

# enjoy the reordered document - for example convert it to markdown
result.document.export_to_markdown()

# or use a chunker on it...
```

or for the VLM-pipeline:

```python
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline
from hierarchical.postprocessor import ResultPostprocessor

source = "my_scanned.pdf"  # document per local path or URL

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_cls=VlmPipeline,
        ),
    }
)
result = converter.convert(source=source)
ResultPostprocessor(result).process()

# enjoy the reordered document - for example convert it to markdown
result.document.export_to_markdown()

# or use a chunker on it...
```
