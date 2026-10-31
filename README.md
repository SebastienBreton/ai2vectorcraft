# ai2vectorcraft

Convert Adobe Illustrator `.ai` files into [VectorCraft](https://github.com/storytold/vectorcraft) `.vectorcraft` documents, with **editable text**, every artboard, and linked images in the right place.

## Why

VectorCraft can open a `.ai` file by reading its PDF-compatible part. But Illustrator sometimes writes wrong positions for **linked images** in that PDF part: rotated placed images end up shifted by tens of points and clipped. The file looks broken in every PDF reader (Preview, Poppler, VectorCraft…), even though it looks right in Illustrator.

`ai2vectorcraft` reads Illustrator's own data inside the file (`AIPrivateData`), recomputes the correct matrix of every linked image, writes a corrected copy of the PDF part, and then drives VectorCraft through its local control port to import it and save a `.vectorcraft` file.

```
file.ai ──► read AIPrivateData (zstd / zlib) ──► fix linked image positions ──► VectorCraft import ──► file.vectorcraft
```

## Requirements

- macOS with [VectorCraft](https://github.com/storytold/vectorcraft) installed in `/Applications` (tested with 0.18.0). Set `VECTORCRAFT_BIN` to use another location.
- Python 3.9 or later, no third-party packages.
  - Illustrator 2020+ files are compressed with Zstandard: Python 3.14 reads them natively; on older Python the [`zstd`](https://github.com/facebook/zstd) command is used (`brew install zstd`).
- The fonts used in the document, installed on the system. Otherwise VectorCraft substitutes a fallback font.

> **Variable fonts:** VectorCraft 0.18 may draw a variable font (for example `PlaypenSans[wght].ttf`) in its thinnest weight. Install static instances instead, for example with fonttools:
> `fonttools varLib.instancer "Font[wght].ttf" wght=400 --update-name-table -o Font-Regular.ttf`

## Usage

```sh
./ai2vectorcraft.py invitation.ai                 # writes invitation.vectorcraft next to it
./ai2vectorcraft.py *.ai -o converted/            # several files, one output folder
./ai2vectorcraft.py invitation.ai --keep-pdf      # also keep the corrected PDF
./ai2vectorcraft.py invitation.ai --port 8123     # another control port
```

VectorCraft starts (or is reused if it already listens on the port) and its window stays visible during the conversion. Each file takes about 20 seconds.

Example output:

```
invitation.ai
  page 1: image moved by (+82.7, +98.3) pt
  48 linked images checked, 8 repositioned
  -> invitation.vectorcraft  (5 artboards, 28 text objects)
```

## What you get

| | |
|---|---|
| Artboards | all of them, with their Illustrator names and positions |
| Text | live text objects with font, size, colour and tracking |
| Linked images | embedded, at the position Illustrator shows |
| Embedded images, vector paths, opacity | as in the PDF part |

## Limitations

- Text comes in **one object per line**: paragraphs are not rebuilt, so a longer line does not push the next one down.
- Letter spacing comes from the PDF and can differ slightly from Illustrator.
- Only `.ai` files saved with **Create PDF Compatible File** (Illustrator's default) are supported.
- PDF parts that use cross-reference streams instead of a classic xref table are not supported yet.
- Illustrator-only features (live effects, symbols as symbols, layer structure beyond what the PDF carries) come in as their PDF appearance.

## How the fix works

1. The PDF part's `PieceInfo` points to the `AIPrivateData` streams; concatenated and decompressed, they hold Illustrator's PostScript-like document.
2. Each `%AI5_BeginPlace` block gives a linked image's matrix and bounds. From them the script computes the image matrix `[a b c d e f]` the PDF should use.
3. Each image drawn in the PDF is matched to its Illustrator object by the linear part of its matrix (scale and rotation are right, only the translation is wrong). Its translation is replaced, relative to its artboard.
4. The changes are appended as an incremental PDF update, so the original bytes are untouched.

## Contributing

Issues and pull requests are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md). Please do not attach `.ai` files that contain personal data to public issues.

## License

[MIT](LICENSE). Not affiliated with Adobe or the VectorCraft project. Adobe and Illustrator are trademarks of Adobe Inc.
