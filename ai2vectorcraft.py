#!/usr/bin/env python3
"""Convert Adobe Illustrator .ai files to VectorCraft .vectorcraft documents.

VectorCraft opens the PDF part of an .ai file. Illustrator sometimes writes wrong
positions for linked images in that PDF part (rotated placed images end up shifted
and clipped). This script reads Illustrator's own data (AIPrivateData), fixes those
positions in a temporary copy of the PDF, then drives VectorCraft over its control
port to import it and save a .vectorcraft file with editable text.

Usage: ai2vectorcraft.py file.ai [more.ai ...] [-o OUTDIR] [--port 7979] [--keep-pdf]
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import zlib

VECTORCRAFT = os.environ.get('VECTORCRAFT_BIN', '/Applications/VectorCraft.app/Contents/MacOS/VectorCraft')
NUM = rb'-?\d*\.?\d+'


# ---------------------------------------------------------------- PDF access

class PDF:
    def __init__(self, data):
        self.d = d = data
        self.offs = {}
        self.trailer = None
        self.startxref = pos = int(re.findall(rb'startxref\s*(\d+)', d[-4096:])[-1])
        while pos is not None:
            if d[pos:pos + 4] != b'xref':
                raise SystemExit('PDF part uses an xref stream, which this script does not handle')
            i = pos + 4
            while True:
                m = re.compile(rb'\s*(\d+) (\d+)\s*').match(d, i)
                if not m or d[i:i + 20].strip().startswith(b'trailer'):
                    break
                start, cnt = int(m.group(1)), int(m.group(2))
                i = m.end()
                for k in range(cnt):
                    e = d[i:i + 20]
                    i += 20
                    if e[17:18] == b'n':
                        self.offs.setdefault(start + k, int(e[:10]))
            t = re.compile(rb'\s*trailer\s*<<(.*?)>>\s*startxref', re.S).match(d, i)
            if self.trailer is None:
                self.trailer = t.group(1)
            pm = re.search(rb'/Prev (\d+)', t.group(1))
            pos = int(pm.group(1)) if pm else None

    def raw(self, n):
        o = self.offs[n]
        return self.d[o:self.d.find(b'endobj', o)]

    def dict(self, n):
        r = self.raw(n)
        s = r.find(b'stream')
        h = r if s < 0 else r[:s]
        return h[h.find(b'obj') + 3:].strip()

    def stream(self, n):
        o = self.offs[n]
        h = self.dict(n)
        L = re.search(rb'/Length (\d+)( 0 R)?', h)
        ln = int(L.group(1))
        if L.group(2):
            ln = int(re.search(rb'obj\s*(\d+)', self.raw(ln)).group(1))
        i = self.d.find(b'stream', o) + 6
        if self.d[i:i + 2] == b'\r\n':
            i += 2
        elif self.d[i:i + 1] in b'\r\n':
            i += 1
        raw = self.d[i:i + ln]
        return zlib.decompress(raw) if b'/FlateDecode' in h else raw

    def xobjects(self, h):
        m = re.search(rb'/XObject\s*<<(.*?)>>', h, re.S)
        return {k.decode(): int(v) for k, v in re.findall(rb'/(\w+) (\d+) 0 R', m.group(1))} if m else {}

    def root(self):
        return int(re.search(rb'/Root (\d+) 0 R', self.trailer).group(1))

    def pages(self):
        out = []
        def walk(n):
            h = self.dict(n)
            if re.search(rb'/Type\s*/Pages', h):
                kids = re.search(rb'/Kids\s*\[(.*?)\]', h, re.S).group(1)
                for k in re.findall(rb'(\d+) 0 R', kids):
                    walk(int(k))
            else:
                out.append(n)
        walk(int(re.search(rb'/Pages (\d+) 0 R', self.dict(self.root())).group(1)))
        return out

    def contents(self, page):
        m = re.search(rb'/Contents (\d+) 0 R', self.dict(page))
        return int(m.group(1)) if m else None


# ------------------------------------------------------ Illustrator data

def ai_private_text(pdf):
    """Concatenate and decompress the AIPrivateData streams of the first page."""
    pi = re.search(rb'/PieceInfo\s*<<\s*/Illustrator (\d+) 0 R', pdf.dict(pdf.pages()[0]))
    if not pi:
        raise SystemExit('no Illustrator data in this file (saved without "Create PDF Compatible File"?)')
    priv = int(re.search(rb'/Private (\d+) 0 R', pdf.dict(int(pi.group(1)))).group(1))
    refs = {int(k): int(v) for k, v in re.findall(rb'/AIPrivateData(\d+) (\d+) 0 R', pdf.dict(priv))}
    data = b''.join(pdf.stream(refs[k]) for k in sorted(refs))
    m = re.match(rb'%AI(\d+)_(ZStandard_Data|CompressedData)', data)
    if m:
        body = data[m.end():]
        if m.group(2) == b'ZStandard_Data':
            try:
                from compression import zstd  # Python 3.14+
                data = zstd.decompress(body)
            except ImportError:
                data = subprocess.run(['zstd', '-d', '-c'], input=body, capture_output=True, check=True).stdout
        else:
            data = zlib.decompress(body)
    return data.replace(b'\r', b'\n')


def ai_artboards(text):
    """Artboard rectangles (x1, ytop, x2, ybottom) in Illustrator document coordinates."""
    pts = re.findall(rb'%_(' + NUM + rb') (' + NUM + rb') /RealPointRelToROrigin\n%_ \(PositionPoint([12])\)', text)
    boards = []
    for i in range(0, len(pts) - 1, 2):
        (x1, y1, a), (x2, y2, b) = pts[i], pts[i + 1]
        if a == b'1' and b == b'2':
            boards.append((float(x1), float(y1), float(x2), float(y2)))
    return boards


def ai_places(text):
    """Placed (linked) images: (line, file name, matrix, bounds)."""
    lines = text.split(b'\n')
    out = []
    for i, l in enumerate(lines):
        if l.startswith(b'%AI5_BeginPlace'):
            mat, rest = lines[i + 2].decode('latin1')[1:].split(']')
            name = lines[i + 3].decode('latin1').strip().strip('(`)').rstrip(')')
            out.append((i + 1, os.path.basename(name), list(map(float, mat.split())), list(map(int, rest.split()[:4]))))
    return out


def ai_cm(M, bb):
    """PDF image matrix (unit square to document space) for a placed image."""
    a, b, c, d, e, f = M
    x0, y0, x1, y1 = bb
    W, H = x1 - x0, y1 - y0
    return [a * W, b * W, -c * H, -d * H, a * x0 + c * y1 + e, b * x0 + d * y1 + f]


# ------------------------------------------------------------- the fix

DRAW = re.compile(
    rb'(?P<clip>(?:' + NUM + rb' ' + NUM + rb' [ml]\s+|h\s+)+W n\s+)?'
    rb'(?P<pre>q\s+(?:' + NUM + rb' g\s+)?(?:/GS\d+ gs\s+)?)'
    rb'(?P<cm>(?:' + NUM + rb'\s+){6})cm(?P<post>\s+/(?P<name>\w+) Do)')


def fix_placed_images(pdf, text, log):
    boards = ai_artboards(text)
    pages = pdf.pages()
    if len(boards) != len(pages):
        log(f'  ! {len(boards)} artboards for {len(pages)} pages: positions left as they are')
        return {}
    origins = [(x1, min(y1, y2)) for x1, y1, x2, y2 in boards]
    places = [(ln, ai_cm(M, bb)) for ln, _, M, bb in ai_places(text)]
    used, changes, seen = set(), {}, set()
    stats = {'checked': 0, 'moved': 0}

    def fix_stream(n, xo, page):
        if n in seen:
            return
        seen.add(n)
        s = pdf.stream(n)

        def rep(m):
            x = xo.get(m.group('name').decode())
            if x is None or b'/Subtype/Image' not in pdf.dict(x):
                return m.group(0)
            cm = [float(v) for v in m.group('cm').split()]
            cands = [(ln, c) for ln, c in places if all(abs(c[k] - cm[k]) < 0.02 for k in range(4))]
            free = [c for c in cands if c[0] not in used] or cands
            if not free:
                return m.group(0)
            ln, c = free[0]
            used.add(ln)
            ox, oy = origins[page]
            new = cm[:4] + [c[4] - ox, c[5] - oy]
            stats['checked'] += 1
            if abs(new[4] - cm[4]) > 0.05 or abs(new[5] - cm[5]) > 0.05:
                stats['moved'] += 1
                log(f'  page {page + 1}: image moved by ({new[4] - cm[4]:+.1f}, {new[5] - cm[5]:+.1f}) pt')
            # The clip Illustrator wrote is the (wrong) image outline; the form BBox already clips correctly.
            return m.group('pre') + (' '.join(f'{v:.6f}' for v in new) + ' ').encode() + b'cm' + m.group('post')

        s2 = DRAW.sub(rep, s)
        if s2 != s:
            changes[n] = s2
        for x in xo.values():
            h = pdf.dict(x)
            if b'/Subtype/Form' in h:
                fix_stream(x, pdf.xobjects(h), page)

    for i, pg in enumerate(pages):
        c = pdf.contents(pg)
        if c is not None:
            fix_stream(c, pdf.xobjects(pdf.dict(pg)), i)
    log(f'  {stats["checked"]} linked images checked, {stats["moved"]} repositioned')
    return changes if stats['moved'] else {}


def write_update(pdf, changes, out):
    """Write the PDF with replaced streams as an incremental update."""
    buf = bytearray(pdf.d)
    if not buf.endswith(b'\n'):
        buf += b'\n'
    offs = []
    for n, s in changes.items():
        h = pdf.dict(n)
        data = zlib.compress(s, 9) if b'/FlateDecode' in h else s
        h2 = re.sub(rb'/Length \d+( 0 R)?', b'/Length %d' % len(data), h)
        offs.append((n, len(buf)))
        buf += b'%d 0 obj\n' % n + h2 + b'\nstream\n' + data + b'\nendstream\nendobj\n'
    x = len(buf)
    buf += b'xref\n'
    for n, o in sorted(offs):
        buf += b'%d 1\n%010d 00000 n \n' % (n, o)
    tr = re.sub(rb'/Prev \d+', b'', pdf.trailer)
    buf += b'trailer\n<<' + tr + b'/Prev %d>>\nstartxref\n%d\n%%%%EOF\n' % (pdf.startxref, x)
    with open(out, 'wb') as f:
        f.write(buf)


# ------------------------------------------------------ VectorCraft control

class VectorCraft:
    def __init__(self, port):
        self.port = port
        self.proc = None

    def call(self, method, params=None, timeout=300):
        s = socket.create_connection(('127.0.0.1', self.port), timeout=timeout)
        s.sendall((json.dumps({'id': 1, 'method': method, 'params': params or {}}) + '\n').encode())
        buf = b''
        while not buf.endswith(b'\n'):
            c = s.recv(1 << 20)
            if not c:
                break
            buf += c
        s.close()
        r = json.loads(buf)
        if not r.get('ok'):
            raise RuntimeError(f'{method}: {r.get("error")}')
        return r.get('result')

    def up(self):
        try:
            socket.create_connection(('127.0.0.1', self.port), timeout=1).close()
            return True
        except OSError:
            return False

    def start(self):
        if self.up():
            return
        self.proc = subprocess.Popen([VECTORCRAFT, '--control', str(self.port)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            if self.up():
                return
            time.sleep(0.5)
        raise SystemExit('VectorCraft did not start its control server')

    def state(self):
        return self.call('ui.inspect')

    def convert(self, pdf_path, out_path, log):
        before = len(self.state()['documents'])
        res = self.call('app.open', {'path': pdf_path})
        if res is None:
            st = self.state()
            kind = (st.get('ui', {}).get('dialog') or {}).get('kind')
            if kind != 'importPdf':
                raise RuntimeError(f'unexpected dialog: {kind}')
            self.call('ui.dialog.confirm')  # every page, one artboard per page
        for _ in range(600):
            st = self.state()
            if len(st['documents']) > before and not st['opening']:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('import timed out')
        if os.path.exists(out_path):
            os.remove(out_path)
        res = self.call('engine.execute', {'command': 'file.saveAs', 'params': {'path': out_path}})
        for w in res.get('warnings') or []:
            log(f'  ! {w}')
        last = -1
        for _ in range(600):  # saves run in the background: wait for the size to settle
            time.sleep(1)
            size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
            if size and size == last:
                break
            last = size
        else:
            raise RuntimeError('save timed out')
        try:
            self.call('engine.execute', {'command': 'file.close', 'params': {}})
        except RuntimeError:
            pass


def count_text(path):
    raw = open(path, 'rb').read()
    i = raw.find(b'\n\x00VCBLOBS\x00')
    doc = json.loads(raw[:i if i >= 0 else len(raw)])
    n = 0
    def walk(o):
        nonlocal n
        k = o.get('kind', {})
        n += k.get('type') == 'text'
        for c in k.get('children') or []:
            walk(c)
        if o.get('mask'):
            walk(o['mask']['art'])
    for layer in doc['document']['layers']:
        walk(layer)
    return n, len(doc['document']['artboards'])


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('files', nargs='+')
    ap.add_argument('-o', '--outdir', help='output folder (default: next to each .ai)')
    ap.add_argument('--port', type=int, default=7979)
    ap.add_argument('--keep-pdf', action='store_true', help='also keep the corrected PDF')
    args = ap.parse_args()
    log = lambda s: print(s, flush=True)
    vc = VectorCraft(args.port)
    vc.start()
    failed = 0
    for src in args.files:
        src = os.path.abspath(src)
        base = os.path.splitext(os.path.basename(src))[0]
        outdir = os.path.abspath(args.outdir or os.path.dirname(src))
        out = os.path.join(outdir, base + '.vectorcraft')
        log(f'{os.path.basename(src)}')
        try:
            os.makedirs(outdir, exist_ok=True)
            pdf = PDF(open(src, 'rb').read())
            changes = fix_placed_images(pdf, ai_private_text(pdf), log)
            with tempfile.TemporaryDirectory() as tmp:
                fixed = os.path.join(tmp, base + '.pdf')
                write_update(pdf, changes, fixed)
                if args.keep_pdf:
                    write_update(pdf, changes, os.path.join(outdir, base + '-corrige.pdf'))
                vc.convert(fixed, out, log)
            texts, boards = count_text(out)
            log(f'  -> {out}  ({boards} artboards, {texts} text objects)')
        except Exception as e:  # keep going with the other files
            failed += 1
            log(f'  ! failed: {e}')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
