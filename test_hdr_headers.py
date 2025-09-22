import pickle
from pathlib import Path
from docling_core.types.doc.document import SectionHeaderItem
from test_simple_clustDp2 import create_toc
from pprint import pprint

all_headings = {}
for p in Path("/mnt/hgfs/virtual_machines/hrdoc_items/hrdoc_items/").glob("*.pickle"):
    with open(p, "rb")as fh:
        item_list = pickle.load(fh)
    
    preprocessed_headings = []
    for header_item in [el[0] for el in item_list if isinstance(el[0], SectionHeaderItem)]:
        prov = header_item.prov[0]
        preprocessed_headings.append({"text": " ".join(header_item.text.split("\n")),
            "font_size": prov.bbox.height,
            "is_bold": False,
            "is_italic": False,
            "top_left": prov.bbox.t,
            "text_direction:": None,
            "font": ""
            })
    all_headings[p.name] = preprocessed_headings

for i, [fn, headings] in enumerate(all_headings.items()):
    if i < 15:
        continue
    if len(headings) < 2:
        continue
    print(f"======{i}========")
    print(fn)
    print("==============")
    pprint(headings)
    print("==============")
    print(create_toc(headings))
    input()
