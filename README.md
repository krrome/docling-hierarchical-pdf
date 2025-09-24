# docling-hierarchical-pdf

[![Release](https://img.shields.io/github/v/release/krrome/docling-hierarchical-pdf)](https://img.shields.io/github/v/release/krrome/docling-hierarchical-pdf)
[![Build status](https://img.shields.io/github/actions/workflow/status/krrome/docling-hierarchical-pdf/main.yml?branch=main)](https://github.com/krrome/docling-hierarchical-pdf/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/krrome/docling-hierarchical-pdf/branch/main/graph/badge.svg)](https://codecov.io/gh/krrome/docling-hierarchical-pdf)
[![Commit activity](https://img.shields.io/github/commit-activity/m/krrome/docling-hierarchical-pdf)](https://img.shields.io/github/commit-activity/m/krrome/docling-hierarchical-pdf)
[![License](https://img.shields.io/github/license/krrome/docling-hierarchical-pdf)](https://img.shields.io/github/license/krrome/docling-hierarchical-pdf)

This package enables inference of header hierarchy in the docling PDF parsing pipeline.

- **Github repository**: <https://github.com/krrome/docling-hierarchical-pdf/>
- **Documentation** <https://krrome.github.io/docling-hierarchical-pdf/>

## What it does:

Docling currently does not support the extraction of header hierarchies from PDF documents. This package attempts to infer and correct the hierarchy of headings based on a few simple rules and then corrects the docling Document hierarchy accordingly.

### Inference

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

### Applying the hierarchy

The current solution reorders the hierarchy tree of document items according to the inference results:
 - Headings become sorted into parent/child relationship as inferred from the heading hierarchy.
 - Heading get assigned with the inferred heading level (`level` attribute of `SectionHeaderItem`)
 - Any Items (except for furniture) that follow a heading become children of that last heading.

### Verification
The current solution has been tested on 60+ text-based PDF documents using the docling DocumentConverter with default parameters and gave satisfying results. In an attempt to test the performance with a public dataset 20+ document from the HDRDoc dataset have been tested. This dataset is based on images so the default VLM-pipeline of docling was used. Performance was inferior to pure-text PDFs, which was limited by the performance of docling VLM-parsing.

### Limitations
- The proposed solution uses the ConversionReult object rather than the DoclingDocument it produces, because DoclingDocument does not contain information on font style of text-based PDFs, which is present in the ConversionResult. The more information is available the is the inference result.
- The solution entirely relies on docling parsing - if docling does not identify a header then there is no way to get it back with this postprocessing - but docling does pretty well for text-based PDFs.
- The proposed solution currently does not take TOC-bookmarks into account, but I am planning to integrate that soon.
- The proposed solution has not yet been evaluated on the full HRDoc dataset, but I am planning to do this soon.

## How to use it:

Install it:
```bash
pip install XXXX
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

# enjoy the reordered document
result.document.export_to_markdown()
```

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
