import pickle
import os
from test_simple_clustDp2 import create_toc

if not os.path.exists("all_headers_preprocessed.pkl"):
    with open("all_headers.pkl", "rb") as fh:
        all_headers = pickle.load(fh)

    all_headings = {}
    for fn, header_obj in all_headers.items():
        if not header_obj["elements"] or not isinstance(header_obj["elements"][0], list):
            continue
        toc = header_obj["toc"]
        # docling_res = header_obj["result"]
        headings = header_obj["elements"]
        preprocessed_headings = []
        for cluster in headings:
            if not cluster:
                continue
            if hasattr(cluster[0], "font_name"):
                font_split = cluster[0].font_name.split("-")
            else:
                font_split = [""]
            
            preprocessed_headings.append({"text": " ".join([cell.text for cell in cluster]),
            "font_size": cluster[0].rect.height,
            "is_bold": "Bold" in font_split[1] if len(font_split) > 1 else False,
            "is_italic": "Italic" in font_split[1] if len(font_split) > 1 else False,
            "top_left": cluster[0].rect.r_y0,
            "text_direction:": cluster[0].text_direction,
            "font": font_split[0]
            })
        all_headings[fn] = preprocessed_headings

    with open("all_headers_preprocessed.pkl", "wb") as fh:
        pickle.dump(all_headings, fh)

with open("all_headers_preprocessed.pkl", "rb") as fh:
    all_headings = pickle.load(fh)

to_correct = [
    "/project/data/external/interim/parsed/3f9fb84f9f112158773a959cdf60a8f4bd142d9b3a8609629d78f6a73134ba96/docling_dev/9b958882-0d51-46c9-bd87-e1b0f4f410a4--pflichtenheft%20lohnbrennereien%20mit%20alco-dec_de.pdf__.pickle",
    "/project/data/external/interim/parsed/3f9fb84f9f112158773a959cdf60a8f4bd142d9b3a8609629d78f6a73134ba96/docling_dev/b4e29f03-b366-4480-bfaa-069c3a707eba--Produktionserkl%C3%A4rung%20Notfallverfahren%20alco-dec_DE_def.pdf__.pickle"
]

for i, [fn, headings] in enumerate(all_headings.items()):
    if i < 62:
        continue
    if len(headings) < 2:
        continue
    print(f"======{i}========")
    print(fn)
    print("==============")
    print(create_toc(headings))
    input()
