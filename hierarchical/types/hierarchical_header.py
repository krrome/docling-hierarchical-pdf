from dataclasses import dataclass, field
from typing import Optional, Union

from hierarchical.enums import NumberingLevel, StyleAttributes


class UnkownNumberingLevel(Exception):
    def __init__(self, level_name: NumberingLevel):
        super().__init__(f"Level kind must be one of {NumberingLevel.__members__.values()}, not '{level_name}'.")


@dataclass
class HierarchicalHeader:
    index: Optional[int] = None
    level_fontsize: Optional[int] = None
    style_attrs: list[StyleAttributes] = field(default_factory=lambda: [])
    level_latin: list[int] = field(default_factory=lambda: [])
    level_alpha: list[int] = field(default_factory=lambda: [])
    level_numerical: list[int] = field(default_factory=lambda: [])
    parent: Optional["HierarchicalHeader"] = None
    children: list["HierarchicalHeader"] = field(default_factory=lambda: [])
    doc_ref: Optional[str] = None
    text: Optional[str] = None

    def any_level(self) -> bool:
        return bool(self.level_alpha or self.level_alpha or self.level_numerical)

    def last_level_of_kind(self, kind: NumberingLevel) -> tuple[list[int], Union["HierarchicalHeader", None]]:
        if kind not in NumberingLevel.__members__.values():
            raise UnkownNumberingLevel(kind)
        if self.parent:
            if last := getattr(self.parent, kind.value):
                return last, self.parent
            return self.parent.last_level_of_kind(kind)
        return [], None

    def string_repr(self, prefix: str = "") -> str:
        out_text = ""
        if self.text:
            out_text += prefix + self.text + "\n"
        for child in self.children:
            out_text += child.string_repr(prefix + "  ")
        return out_text

    def __str__(self) -> str:
        return self.string_repr()
