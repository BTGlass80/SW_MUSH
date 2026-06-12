import sys, fitz  # pip install pymupdf
doc = fitz.open(sys.argv[1])
out = sys.argv[1].rsplit(".", 1)[0] + ".txt"
with open(out, "w", encoding="utf-8") as f:
    for i, page in enumerate(doc, 1):
        f.write(f"\n===== PAGE {i} =====\n{page.get_text()}")
print(f"{out}: {len(doc)} pages")