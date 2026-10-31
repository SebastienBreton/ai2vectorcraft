import os
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import ai2vectorcraft as a2v  # noqa: E402

PAGE_H = 841.889831543

# Illustrator data for one A4 artboard and one linked image (823 x 553 px at 0.24).
AI_TEXT = (
    b'%_0 0 /RealPointRelToROrigin\n%_ (PositionPoint1) ,\n'
    b'%_595.2755737305 -841.889831543 /RealPointRelToROrigin\n%_ (PositionPoint2) ,\n'
    b'%AI5_BeginPlace\n%%FileType: 1\n'
    b'[0.24 0 0 0.24 -1893.32 -1997.93761801967] 7893 7770 8716 8323 4 4 0\n'
    b'(/Volumes/Disk/project/Calque 10.png)`\n'
    b'%AI5_EndPlace\n'
)

# The PDF draws that image at a wrong translation, clipped by its wrong outline.
CONTENT = (
    b'q\n0 0 m\n10 0 l\n10 10 l\nh\nW n\nq\n/GS0 gs\n'
    b'197.52 0 0 -132.72 50 800 cm\n/Im0 Do\nQ\nQ\n'
)


def make_pdf(objs):
    """Build a PDF with a classic xref table from (number, dict, stream or None)."""
    out = bytearray(b'%PDF-1.6\n')
    offs = {}
    for n, d, s in objs:
        offs[n] = len(out)
        if s is None:
            out += b'%d 0 obj\n%s\nendobj\n' % (n, d)
        else:
            out += b'%d 0 obj\n%s\nstream\n%s\nendstream\nendobj\n' % (n, d % len(s), s)
    x = len(out)
    size = max(offs) + 1
    out += b'xref\n0 %d\n0000000000 65535 f \n' % size
    for n in range(1, size):
        out += b'%010d 00000 n \n' % offs[n] if n in offs else b'0000000000 65535 f \n'
    out += b'trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n' % (size, x)
    return bytes(out)


def sample_pdf(private=AI_TEXT, content=CONTENT):
    priv = b'%AI12_CompressedData' + zlib.compress(private)
    return make_pdf([
        (1, b'<</Type/Catalog/Pages 2 0 R>>', None),
        (2, b'<</Type/Pages/Kids[3 0 R]/Count 1>>', None),
        (3, b'<</Type/Page/Parent 2 0 R/MediaBox[0 0 595.276 841.89]/Contents 4 0 R'
            b'/Resources<</XObject<</Im0 5 0 R>>>>/PieceInfo<</Illustrator 6 0 R>>>>', None),
        (4, b'<</Length %d>>', content),
        (5, b'<</Subtype/Image/Width 823/Height 553/Length %d>>', b'x'),
        (6, b'<</Private 7 0 R>>', None),
        (7, b'<</AIPrivateData1 8 0 R>>', None),
        (8, b'<</Length %d>>', priv),
    ])


class IllustratorData(unittest.TestCase):
    def test_artboards(self):
        self.assertEqual(a2v.ai_artboards(AI_TEXT), [(0.0, 0.0, 595.2755737305, -PAGE_H)])

    def test_places(self):
        (line, name, M, bb), = a2v.ai_places(AI_TEXT)
        self.assertEqual(name, 'Calque 10.png')
        self.assertEqual(bb, [7893, 7770, 8716, 8323])
        self.assertAlmostEqual(M[0], 0.24)

    def test_matrix(self):
        _, _, M, bb = a2v.ai_places(AI_TEXT)[0]
        cm = a2v.ai_cm(M, bb)
        for got, want in zip(cm, [197.52, 0, 0, -132.72, 1.0, -0.4176]):
            self.assertAlmostEqual(got, want, places=3)

    def test_private_text_zlib(self):
        pdf = a2v.PDF(sample_pdf())
        self.assertEqual(a2v.ai_private_text(pdf), AI_TEXT)


class Fix(unittest.TestCase):
    def test_moves_image_and_drops_clip(self):
        pdf = a2v.PDF(sample_pdf())
        changes = a2v.fix_placed_images(pdf, AI_TEXT, lambda s: None)
        self.assertEqual(list(changes), [4])
        new = changes[4]
        self.assertNotIn(b'W n', new)
        nums = [float(v) for v in new.split(b' cm')[0].split()[-6:]]
        self.assertAlmostEqual(nums[4], 1.0, places=3)
        self.assertAlmostEqual(nums[5], PAGE_H - 0.4176, places=3)

    def test_incremental_update_round_trip(self):
        pdf = a2v.PDF(sample_pdf())
        changes = a2v.fix_placed_images(pdf, AI_TEXT, lambda s: None)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'fixed.pdf')
            a2v.write_update(pdf, changes, out)
            again = a2v.PDF(open(out, 'rb').read())
        self.assertEqual(again.stream(4), changes[4])
        self.assertEqual(again.pages(), [3])
        self.assertEqual(a2v.fix_placed_images(again, AI_TEXT, lambda s: None), {})

    def test_no_change_when_positions_are_right(self):
        right = CONTENT.replace(b'50 800', b'1.0 841.472231')
        pdf = a2v.PDF(sample_pdf(content=right))
        self.assertEqual(a2v.fix_placed_images(pdf, AI_TEXT, lambda s: None), {})


if __name__ == '__main__':
    unittest.main()
