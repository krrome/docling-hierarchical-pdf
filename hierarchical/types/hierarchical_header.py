from dataclasses import dataclass, field

from hierarchical.enums import NumberingLevel


class UnkownNumberingLevel:
    def __init__(self, level_name):
        super().__init__(f"Level kind must be one of {NumberingLevel.__members__}, not '{level_name}'.")


@dataclass
class HierarchicalHeader:
    index: int = (None,)
    level_fontsize: int = None
    style_attrs: list[str] = field(default_factory=lambda: [])
    level_latin: list[int] = field(default_factory=lambda: [])
    level_alpha: list[int] = field(default_factory=lambda: [])
    level_numerical: list[int] = field(default_factory=lambda: [])
    parent: "HierarchicalHeader" = None
    children: list["HierarchicalHeader"] = field(default_factory=lambda: [])
    doc_ref = None
    text: str = None

    def any_level(self):
        return self.level_alpha or self.level_alpha or self.level_numerical

    def last_level_of_kind(self, kind):
        if kind not in NumberingLevel.__members__:
            raise UnkownNumberingLevel(kind)
        if self.parent:
            if last := getattr(self.parent, kind):
                return last, self.parent
            return self.parent.last_level_of_kind(kind)
        return [], None

    def string_repr(self, prefix=""):
        out_text = ""
        if self.text:
            out_text += prefix + self.text + "\n"
        for child in self.children:
            out_text += child.string_repr(prefix + "  ")
        return out_text

    def __str__(self):
        return self.string_repr()
