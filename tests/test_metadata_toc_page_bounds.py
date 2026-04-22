from io import BytesIO
from types import SimpleNamespace

import hierarchical.hierarchy_builder_metadata as hierarchy_builder_metadata


def test_extract_toc_handles_last_page_without_overflow(monkeypatch):
    class FakeTextPage:
        @staticmethod
        def extractBLOCKS():
            return []

    class FakePage:
        @staticmethod
        def search_for(_title):
            return []

        @staticmethod
        def get_textpage():
            return FakeTextPage()

    class FakeDoc:
        def __init__(self, **_kwargs):
            self.pages = [FakePage(), FakePage()]

        def __len__(self):
            return len(self.pages)

        def __getitem__(self, index):
            if index < 0 or index >= len(self.pages):
                raise AssertionError(f"Unexpected page access: {index}")  # noqa: TRY003
            return self.pages[index]

        @staticmethod
        def get_toc(simple=False):
            assert simple is False
            return [[1, "Last section", 2, {}]]

    monkeypatch.setattr(hierarchy_builder_metadata, "FitzDocument", FakeDoc)
    conv_res = SimpleNamespace(input=SimpleNamespace(file="pdf"))
    hbm = hierarchy_builder_metadata.HierarchyBuilderMetadata(conv_res, source=BytesIO(b"%PDF-1.4"))

    assert hbm.toc == [(1, "Last section", 2, {})]
