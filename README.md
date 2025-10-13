# docling-hierarchical-pdf

[![Commit activity](https://img.shields.io/github/commit-activity/m/krrome/docling-hierarchical-pdf)](https://img.shields.io/github/commit-activity/m/krrome/docling-hierarchical-pdf)
[![License](https://img.shields.io/github/license/krrome/docling-hierarchical-pdf)](https://img.shields.io/github/license/krrome/docling-hierarchical-pdf)

This package enables inference of header hierarchy in the docling PDF parsing pipeline.

- **Github repository**: <https://github.com/krrome/docling-hierarchical-pdf/>
- **Documentation** <https://krrome.github.io/docling-hierarchical-pdf/>

## What it does:

Docling currently does not support the extraction of header hierarchies from PDF documents. This package attempts to infer and correct the hierarchy of headings based on a few simple rules and then corrects the docling Document hierarchy accordingly.

### Import from bookmarks (PDF-metadata)

This package uses pymupdf to try to extract the TOC from "PDF-bookmarks". If successful, the headings and texts in a Docling result are corrected to match the structure in the PDF metadata. This means that the code doesn't only correct the hierarchy levels of section headings that were correctly parsed by docling, but it also attempts a best effort solution converting headings missed by docling into headings and vice versa.

### Stylistic inference

The rules are:
 - Numbering-based: Attempt to infer the hierarchy from heading numbering. Arabic and roman numbering as well as outline numbering using letters.
 - Style-based: If the above fails try to infer the headings by font size and style (bold / italic).

Results are as follows:

Header hierarchy before reconstruction:

```
Richtlinie 10-00
Einfuhrzollveranlagungsverfahren
Abkürzungsverzeichnis
1  Veranlagungsschritte im Zollveranlagungsverfahren
Ablaufschema Zollveranlagungsverfahren:
1.1  Zuführen
1.2  Zollüberwachung und Zollprüfung
1.3  Gestellen und summarisches Anmelden
1.3.1  Allgemeines
1.3.2  Form der summarischen Anmeldung
1.3.3  Manipulationen
...
```

After reconstruction:
```
  Richtlinie 10-00
  Einfuhrzollveranlagungsverfahren
  Abkürzungsverzeichnis
  1  Veranlagungsschritte im Zollveranlagungsverfahren
    Ablaufschema Zollveranlagungsverfahren:
    1.1  Zuführen
    1.2  Zollüberwachung und Zollprüfung
    1.3  Gestellen und summarisches Anmelden
      1.3.1  Allgemeines
      1.3.2  Form der summarischen Anmeldung
      1.3.3  Manipulationen
      ...
```

#### Applying the hierarchy

The current solution reorders the hierarchy tree of document items according to the inference results:
 - Headings become sorted into parent/child relationship as inferred from the heading hierarchy.
 - Heading get assigned with the inferred heading level (`level` attribute of `SectionHeaderItem`)
 - Any Items (except for furniture) that follow a heading become children of that last heading.

### Verification
The current solution has been tested on 60+ text-based PDF documents using the docling DocumentConverter with default parameters and gave satisfying results. In an attempt to test the performance with a public dataset 20+ document from the HDRDoc dataset have been tested. This dataset is based on images so the default VLM-pipeline of docling was used. Performance was inferior to pure-text PDFs, which was limited by the performance of docling VLM-parsing.

### Limitations
- The proposed solution uses the ConversionReult object rather than the DoclingDocument it produces, because DoclingDocument does not contain information on font style of text-based PDFs, which is present in the ConversionResult. The more information is available the is the inference result.
- The solution entirely relies on docling parsing - if docling does not identify a header then there is no way to get it back with this postprocessing - but docling does pretty well for text-based PDFs.
- The proposed solution has not yet been evaluated on the full HRDoc dataset.

## How to use it:

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

## FAQ

### Working with DocumentStream sources / PDFFileNotFoundException:

If you run into the `PDFFileNotFoundException` then your `source` attribute to `DocumentConverter().convert(source=source)` has either been of type `str` or of type `DocumentStream` so there is the Docling conversion result unfortunately does *not* hold a valid reference to the source file anymore. Hence the Postprocessor needs your help - if `source` was a string then you can add the `source=source` when instantiating `ResultPostprocessor` - full example:

```python
from docling.document_converter import DocumentConverter
from hierarchical.postprocessor import ResultPostprocessor

source = "my_file.pdf"  # document per local path or URL
converter = DocumentConverter()
result = converter.convert(source)
# the postprocessor modifies the result.document in place.
ResultPostprocessor(result, source=source).process()
# ...
```

If you have used a `DocumentStream` object as source you are unfortunately in the situation that you will have to pass a valid Path to the PDF as a `source` argument to `ResultPostprocessor` or a new, open BytesIO stream or `DocumentStream` object as a `source` argument to `ResultPostprocessor`. The reason is that docling *closes* the source stream when it is finished - so no more reading from that stream is possible.

### Exception handling for ToC extraction from metadata:

You want to handle exceptions regarding File-IO / Streams yourself - great, just set `raise_on_error` to `True` when instantiating `ResultPostprocessor`.


## Citation

If you use this software for your project please cite Docling as well as the following:

```
@software{docling_hierarchical,
  author = {Roman, Kayan},
  month = {09},
  title = {{docling-hierarchical-pdf}},
  url = {https://github.com/krrome/docling-hierarchical-pdf},
  version = {0.0.1},
  year = {2025}
}
```

---

Repository initiated with [fpgmaas/cookiecutter-uv](https://github.com/fpgmaas/cookiecutter-uv).
