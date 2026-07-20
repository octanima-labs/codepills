# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: browpic
# version: 1.0.0
# author: octanima-labs
# description: Zero-dependency HTTP image viewer.
# repo: https://github.com/octanima-labs/codepills/blob/main/python/browpic.py
# license: MIT
# usage: python python/browpic.py
# tags:
#   - python
#   - script
# requires:
#   - Python standard library
# platforms:
#   - Linux
#   - macOS
#   - Windows
# CODEPILLS-META-END

"""browpic - Zero-dependency HTTP image viewer.

Serves images from the current working directory in a single-file script.
No external dependencies -- only Python stdlib.

Features:
    Thumbnail grid with zoom, drag-to-pan, arrow-key navigation,
    rename and delete from the browser, subdirectory navigation
    with breadcrumb bar.

Usage:
    python browpic.py [-p PORT] [-b BIND] [-t]

Image formats:
    .jpg .jpeg .png .gif .webp .ico .bmp .svg
    .tif .tiff .avif .heic .heif

API endpoints (served by default on port 9898):
    GET  /                          Viewer HTML page
    GET  /api/images[?dir=<path>]   JSON {"images":[...], "dirs":[...]}
    GET  /api/raw/<filename>        Raw image file
    DELETE /api/files/<filename>    Delete image
    POST /api/rename                Rename: body {"old":"...","new":"..."}

Testing:
    python browpic.py --tests       Run test suite and exit

Shutdown:
    Ctrl+C
"""

import argparse
import http.server
import json
import mimetypes
import os
import socketserver
import sys
import urllib.parse
from pathlib import Path


DEFAULT_PORT = 9898

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico",
    ".bmp", ".svg", ".tif", ".tiff", ".avif", ".heic", ".heif",
}

MIME_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".ico": "image/x-icon",
    ".bmp": "image/bmp", ".svg": "image/svg+xml",
    ".tif": "image/tiff", ".tiff": "image/tiff",
    ".avif": "image/avif", ".heic": "image/heic", ".heif": "image/heif",
}


def get_mime(path):
    """Return MIME type string for a file path.

    Args:
        path: File path (relative or absolute) as str or Path.

    Returns:
        MIME type string (e.g. ``"image/png"``). Falls back to
        ``mimetypes.guess_type``, then ``"application/octet-stream"``.
    """
    ext = Path(path).suffix.lower()
    return MIME_TYPES.get(ext, mimetypes.guess_type(path)[0] or "application/octet-stream")


def send_json(handler, data, status=200):
    """Send a JSON response.

    Args:
        handler: ``BaseHTTPRequestHandler`` instance.
        data: Python object serialized as JSON.
        status: HTTP status code (default 200).
    """
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_file_data(handler, path):
    """Serve a file from the server root directory.

    Blocks path traversal by resolving and checking the resulting
    path stays within the server root.

    Args:
        handler: ``BaseHTTPRequestHandler`` instance.
        path: File path relative to the server root.
    """
    try:
        resolved = (handler.server.root / path).resolve()
        if not str(resolved).startswith(str(handler.server.root)):
            handler.send_error(403)
            return
        with open(resolved, "rb") as f:
            data = f.read()
        handler.send_response(200)
        handler.send_header("Content-Type", get_mime(str(resolved)))
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
    except FileNotFoundError:
        handler.send_error(404)
    except PermissionError:
        handler.send_error(403)


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>browpic</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#eee;min-height:100vh}
header{background:#16213e;padding:1rem 2rem;display:flex;justify-content:space-between;align-items:center}
header h1{font-size:1.3rem;font-weight:600}
.breadcrumb{padding:.5rem 2rem;display:flex;align-items:center;gap:.25rem;font-size:.85rem;background:#0d1b36}
.breadcrumb a{color:#aaa;text-decoration:none;cursor:pointer}
.breadcrumb a:hover{color:#fff}
.breadcrumb .sep{color:#555;margin:0 .15rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;padding:1rem}
.card{background:#0f3460;border-radius:8px;overflow:hidden;cursor:pointer;transition:transform .15s}
.card:hover{transform:scale(1.03)}
.card img{width:100%;height:200px;object-fit:cover;display:block}
.card .info{padding:.6rem;display:flex;justify-content:space-between;align-items:center}
.card .name{font-size:.85rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:110px}
.card .actions{display:flex;gap:.35rem}
.card .actions button{background:none;border:1px solid #555;color:#ccc;padding:3px 7px;border-radius:4px;cursor:pointer;font-size:.75rem;line-height:1}
.card .actions button:hover{background:#e94560;border-color:#e94560;color:#fff}
.dir-card{background:#16214a;display:flex;flex-direction:column;align-items:center;justify-content:center;height:240px}
.dir-card .dir-icon{font-size:2.5rem;margin-bottom:.4rem;opacity:.7}
.dir-card .dir-name{font-size:.85rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:160px;text-align:center;padding:.1rem .5rem}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.92);z-index:1000;justify-content:center;align-items:center;overflow:hidden}
.modal.active{display:flex}
.modal img{max-width:90%;max-height:90%;object-fit:contain;transition:transform .15s;user-select:none;cursor:grab}
.modal img.panning{cursor:grabbing}
.modal .toolbar{position:fixed;top:1rem;right:1rem;display:flex;gap:.5rem;z-index:1001}
.modal .toolbar button{background:rgba(255,255,255,.1);border:1px solid #666;color:#fff;padding:.4rem .75rem;border-radius:4px;cursor:pointer;font-size:.9rem;min-width:32px}
.modal .toolbar button:hover{background:rgba(255,255,255,.2)}
.modal .zoom-info{position:fixed;bottom:1.2rem;left:50%;transform:translateX(-50%);background:rgba(255,255,255,.12);padding:.35rem .9rem;border-radius:4px;font-size:.85rem;z-index:1001}
.modal .nav-btn{position:fixed;top:50%;transform:translateY(-50%);background:rgba(255,255,255,.08);border:1px solid #555;color:#fff;font-size:1.5rem;padding:.5rem .8rem;cursor:pointer;z-index:1001;border-radius:4px}
.modal .nav-btn:hover{background:rgba(255,255,255,.2)}
.modal .nav-btn.prev{left:1rem}
.modal .nav-btn.next{right:1rem}
.empty{grid-column:1/-1;text-align:center;padding:4rem 1rem;color:#888}
.empty p{font-size:1.1rem}
</style>
</head>
<body>
<header>
  <h1>browpic</h1>
  <span id="count"></span>
</header>
<nav id="breadcrumb" class="breadcrumb"></nav>
<div id="grid" class="grid"></div>

<div id="modal" class="modal">
  <div class="toolbar">
    <button onclick="zoomIn()" title="Zoom in">+</button>
    <button onclick="zoomOut()" title="Zoom out">&minus;</button>
    <button onclick="zoomReset()" title="Reset zoom">1:1</button>
    <button onclick="closeModal()" title="Close">&times;</button>
  </div>
  <button class="nav-btn prev" onclick="navigate(-1)" title="Previous">&lsaquo;</button>
  <button class="nav-btn next" onclick="navigate(1)" title="Next">&rsaquo;</button>
  <img id="modal-img" src="" alt="" draggable="false">
  <div id="zoom-info" class="zoom-info"></div>
</div>

<script>
let scale=1,panX=0,panY=0,currentImg='',panning=false,psX=0,psY=0,pbX=0,pbY=0;
let currentDir='',imageList=[];

function esc(s){return s.replace(/\\/g,'\\\\').replace(/'/g,"\\'")}
function he(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}

function loadItems(){
  var url='/api/images';
  if(currentDir)url+='?dir='+encodeURIComponent(currentDir);
  fetch(url).then(function(r){return r.json()}).then(function(d){
    imageList=d.images||[];
    var dirs=d.dirs||[];
    var parts=[];
    if(imageList.length)parts.push(imageList.length+' images');
    if(dirs.length)parts.push(dirs.length+' dirs');
    document.getElementById('count').textContent=parts.join(', ')||'empty';
    renderBreadcrumb();
    var g=document.getElementById('grid');
    var h='';
    dirs.forEach(function(dn){
      var base=dn.split('/').pop();
      h+='<div class="card dir-card" onclick="enterDir(\''+esc(dn)+'\')">'+
        '<div class="dir-icon">&#128193;</div>'+
        '<div class="dir-name" title="'+he(dn)+'">'+he(base)+'</div></div>'
    });
    imageList.forEach(function(n,i){
      var base=n.split('/').pop();
      h+='<div class="card">'+
        '<img src="/api/raw/'+encodeURIComponent(n)+'" alt="'+he(base)+'" loading="lazy" onclick="openModal('+i+')">'+
        '<div class="info"><span class="name" title="'+he(base)+'">'+he(base)+'</span>'+
        '<div class="actions">'+
        '<button onclick="event.stopPropagation();renameImage(\''+esc(n)+'\')" title="Rename">Ren</button>'+
        '<button onclick="event.stopPropagation();deleteImage(\''+esc(n)+'\')" title="Delete">Del</button>'+
        '</div></div></div>'
    });
    if(!h)h='<div class="empty"><p>No images or directories found</p></div>';
    g.innerHTML=h
  }).catch(function(){console.error('failed to load')});
}

function renderBreadcrumb(){
  var b=document.getElementById('breadcrumb');
  if(!currentDir){b.innerHTML='';return}
  var parts=currentDir.split('/');
  var h='<a onclick="enterDir(\'\')">browpic</a>';
  var path='';
  parts.forEach(function(p){
    path+=(path?'/':'')+p;
    h+=' <span class="sep">/</span> <a onclick="enterDir(\''+esc(path)+'\')">'+he(p)+'</a>';
  });
  b.innerHTML=h;
}

function enterDir(dir){
  currentDir=dir;
  loadItems();
}

function openModal(idx){
  currentImg=imageList[idx];
  scale=1;panX=0;panY=0;
  var img=document.getElementById('modal-img');
  img.src='/api/raw/'+encodeURIComponent(currentImg);
  img.style.transform='';
  img.setAttribute('data-idx',idx);
  img.onerror=function(){img.src='';closeModal();alert('Failed to load '+currentImg)};
  document.getElementById('modal').classList.add('active');
  updateZoomInfo();
}
function closeModal(){
  document.getElementById('modal').classList.remove('active');
}
function applyTransform(){
  var img=document.getElementById('modal-img');
  img.style.transform='scale('+scale+') translate('+panX+'px,'+panY+'px)';
}
function updateZoomInfo(){
  document.getElementById('zoom-info').textContent=Math.round(scale*100)+'%';
}
function zoomIn(){scale*=1.3;applyTransform();updateZoomInfo()}
function zoomOut(){scale/=1.3;applyTransform();updateZoomInfo()}
function zoomReset(){scale=1;panX=0;panY=0;applyTransform();updateZoomInfo()}

function navigate(dir){
  var el=document.getElementById('modal-img');
  var idx=parseInt(el.getAttribute('data-idx')||0);
  var nidx=((idx+dir)%imageList.length+imageList.length)%imageList.length;
  openModal(nidx);
}

async function deleteImage(fn){
  if(!confirm('Delete '+fn+'?'))return;
  var r=await fetch('/api/files/'+encodeURIComponent(fn),{method:'DELETE'});
  if(r.ok)location.reload();else alert('Failed to delete')
}
async function renameImage(oldName){
  var nn=prompt('New name:',oldName.split('/').pop());
  if(!nn||nn===oldName)return;
  if(nn.indexOf('/')!==-1||nn.indexOf('\\')!==-1){alert('Invalid name');return}
  var r=await fetch('/api/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old:oldName,new:nn})});
  if(r.ok)location.reload();
  else{var e=await r.json();alert(e.error||'Failed to rename')}
}

// modal click outside image
document.getElementById('modal').addEventListener('click',function(e){if(e.target===this)closeModal()});
// mouse wheel zoom
document.getElementById('modal').addEventListener('wheel',function(e){
  if(!document.getElementById('modal').classList.contains('active'))return;
  e.preventDefault();
  if(e.deltaY<0)zoomIn();else zoomOut()
},{passive:false});
// keyboard
document.addEventListener('keydown',function(e){
  if(!document.getElementById('modal').classList.contains('active'))return;
  if(e.key==='Escape')closeModal();
  else if(e.key==='ArrowLeft'){e.preventDefault();navigate(-1)}
  else if(e.key==='ArrowRight'){e.preventDefault();navigate(1)}
  else if(e.key==='+'||e.key==='='){e.preventDefault();zoomIn()}
  else if(e.key==='-'){e.preventDefault();zoomOut()}
  else if(e.key==='0'){e.preventDefault();zoomReset()}
  else if(e.key==='r'||e.key==='R'){renameImage(currentImg)}
  else if(e.key==='Delete'){deleteImage(currentImg)}
});
// drag to pan
(function(){
  var img=document.getElementById('modal-img');
  img.addEventListener('mousedown',function(e){
    if(scale<=1)return;
    e.preventDefault();
    panning=true;psX=e.clientX;psY=e.clientY;pbX=panX;pbY=panY;
    img.classList.add('panning')
  });
  window.addEventListener('mousemove',function(e){
    if(!panning)return;
    panX=pbX+(e.clientX-psX)/scale;
    panY=pbY+(e.clientY-psY)/scale;
    applyTransform()
  });
  window.addEventListener('mouseup',function(){
    if(!panning)return;
    panning=false;
    document.getElementById('modal-img').classList.remove('panning')
  })
})();

loadItems();
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the browpic image viewer.

    Routes API calls and serves the viewer HTML page.  Expects
    ``server.root`` (set at startup) as the base directory for all
    file operations.  Suppresses access-log output.
    """
    def _path_parts(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        return path.strip("/").split("/"), parsed

    def do_GET(self):
        parts, parsed = self._path_parts()
        if self.path == "/" or self.path == "":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE.encode("utf-8"))
        elif parts[0] == "api" and parts[1] == "images":
            qs = urllib.parse.parse_qs(parsed.query)
            rel_dir = qs.get("dir", [""])[0]
            target = (self.server.root / rel_dir).resolve()
            if not str(target).startswith(str(self.server.root)):
                send_json(self, {"error": "Access denied"}, 403)
                return
            if not target.is_dir():
                send_json(self, {"error": "Not a directory"}, 404)
                return
            images = []
            dirs = []
            for f in sorted(target.iterdir()):
                rel = str(f.resolve().relative_to(self.server.root))
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                    images.append(rel)
                elif f.is_dir() and not f.name.startswith("."):
                    dirs.append(rel)
            send_json(self, {"images": images, "dirs": dirs})
        elif parts[0] == "api" and parts[1] == "raw":
            filepath = "/".join(parts[2:])
            send_file_data(self, filepath)
        else:
            self.send_error(404)

    def do_DELETE(self):
        parts, _ = self._path_parts()
        if parts[0] == "api" and parts[1] == "files" and len(parts) >= 3:
            filename = "/".join(parts[2:])
            try:
                resolved = (self.server.root / filename).resolve()
                if not str(resolved).startswith(str(self.server.root)):
                    send_json(self, {"error": "Access denied"}, 403)
                    return
                if not resolved.is_file():
                    send_json(self, {"error": "Not found"}, 404)
                    return
                resolved.unlink()
                send_json(self, {"ok": True})
            except FileNotFoundError:
                send_json(self, {"error": "Not found"}, 404)
            except PermissionError:
                send_json(self, {"error": "Access denied"}, 403)
        else:
            self.send_error(404)

    def do_POST(self):
        parts, _ = self._path_parts()
        if parts[0] == "api" and parts[1] == "rename":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            old = body.get("old", "")
            new = body.get("new", "")
            if not old or not new:
                send_json(self, {"error": "old and new names required"}, 400)
                return
            if "/" in new or "\\" in new:
                send_json(self, {"error": "Invalid filename"}, 400)
                return
            try:
                old_path = (self.server.root / old).resolve()
                new_path = (old_path.parent / new).resolve()
                if not str(old_path).startswith(str(self.server.root)) or not str(new_path).startswith(str(self.server.root)):
                    send_json(self, {"error": "Access denied"}, 403)
                    return
                if not old_path.is_file():
                    send_json(self, {"error": "Source not found"}, 404)
                    return
                if new_path.exists():
                    send_json(self, {"error": "Target already exists"}, 409)
                    return
                old_path.rename(new_path)
                send_json(self, {"ok": True})
            except FileNotFoundError:
                send_json(self, {"error": "Source not found"}, 404)
            except PermissionError:
                send_json(self, {"error": "Access denied"}, 403)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass


def main():
    """Parse CLI arguments and start the HTTP server.

    If ``--tests`` is given, runs the test suite and exits.  Otherwise
    starts a threaded HTTP server bound to the requested address and
    port, serving the current working directory.
    """
    parser = argparse.ArgumentParser(
        description="Zero-dependency HTTP image viewer. Serves images from CWD.",
        epilog=(
            "examples:\n"
            "  python browpic.py                 serve CWD on port 9898\n"
            "  python browpic.py -p 3000         serve on port 3000\n"
            "  python browpic.py -b 127.0.0.1    bind to localhost only\n"
            "  python browpic.py --tests         run test suite\n"
            "\nSupported formats: .jpg .jpeg .png .gif .webp .ico"
            " .bmp .svg .tif .tiff .avif .heic .heif"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT,
                        help="Port to listen on (default: %(default)s)")
    parser.add_argument("-b", "--bind", default="",
                        help="Address to bind to (default: all interfaces)")
    parser.add_argument("-t", "--tests", action="store_true",
                        help="Run test suite and exit")
    args = parser.parse_args()

    if args.tests:
        run_tests()

    class _Handler(Handler):
        pass

    server = socketserver.ThreadingTCPServer((args.bind, args.port), _Handler)
    server.root = Path.cwd().resolve()
    server.allow_reuse_address = True
    server.daemon_threads = True

    print(f"Serving {server.root} at http://{args.bind or 'localhost'}:{args.port}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.stdout.flush()
        os._exit(0)


def run_tests():
    """Run the built-in test suite.

    Creates a temporary directory with sample PNG images, starts a
    test ``ThreadingTCPServer`` on a random port, and validates all
    API endpoints and edge cases via ``unittest``.  Exits the process
    with code 0 on success or 1 on failure.
    """
    import http.client
    import shutil
    import struct
    import tempfile
    import threading
    import unittest
    import zlib

    def make_png(path, w=100, h=100):
        def chunk(ctype, data):
            c = ctype + data
            return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        raw = b''
        for y in range(h):
            raw += b'\x00' + bytes([255, 0, 0]) * w
        with open(path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n')
            f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)))
            f.write(chunk(b'IDAT', zlib.compress(raw)))
            f.write(chunk(b'IEND', b''))

    class _TestHandler(Handler):
        pass

    class TestBrowpic(unittest.TestCase):

        @classmethod
        def setUpClass(cls):
            cls.tmpdir = tempfile.TemporaryDirectory()
            root = Path(cls.tmpdir.name).resolve()
            make_png(root / 'alpha.png')
            make_png(root / 'beta.png')
            (root / 'subdir').mkdir()
            make_png(root / 'subdir' / 'one.png')
            make_png(root / 'subdir' / 'two.png')
            (root / 'subdir' / 'nested').mkdir()
            make_png(root / 'subdir' / 'nested' / 'deep.png')
            (root / 'empty').mkdir()
            cls.server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), _TestHandler)
            cls.server.root = root
            cls.server.allow_reuse_address = True
            cls.server.daemon_threads = True
            cls.port = cls.server.server_address[1]
            cls._thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
            cls._thread.start()

        @classmethod
        def tearDownClass(cls):
            cls.server.shutdown()
            cls.server.server_close()
            cls.tmpdir.cleanup()

        def setUp(self):
            root = Path(self.tmpdir.name).resolve()
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir()
            make_png(root / 'alpha.png')
            make_png(root / 'beta.png')
            (root / 'subdir').mkdir()
            make_png(root / 'subdir' / 'one.png')
            make_png(root / 'subdir' / 'two.png')
            (root / 'subdir' / 'nested').mkdir()
            make_png(root / 'subdir' / 'nested' / 'deep.png')
            (root / 'empty').mkdir()

        def request(self, method, path, body=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
            h = headers or {}
            if body is not None:
                h['Content-Length'] = str(len(body))
            conn.request(method, path, body=body, headers=h)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            return resp, data

        def test_root_page(self):
            resp, data = self.request('GET', '/')
            self.assertEqual(resp.status, 200)
            self.assertIn(b'<html', data)

        def test_list_images(self):
            resp, data = self.request('GET', '/api/images')
            self.assertEqual(resp.status, 200)
            body = json.loads(data)
            self.assertEqual(sorted(body['images']), ['alpha.png', 'beta.png'])
            self.assertEqual(sorted(body['dirs']), ['empty', 'subdir'])

        def test_list_subdir(self):
            resp, data = self.request('GET', '/api/images?dir=subdir')
            body = json.loads(data)
            self.assertEqual(sorted(body['images']), ['subdir/one.png', 'subdir/two.png'])
            self.assertEqual(sorted(body['dirs']), ['subdir/nested'])

        def test_raw_image(self):
            resp, data = self.request('GET', '/api/raw/alpha.png')
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.getheader('Content-Type'), 'image/png')
            self.assertGreater(len(data), 0)

        def test_delete(self):
            resp, data = self.request('DELETE', '/api/files/beta.png')
            self.assertEqual(resp.status, 200)
            self.assertTrue(json.loads(data).get('ok'))
            resp, data = self.request('GET', '/api/images')
            self.assertNotIn('beta.png', json.loads(data)['images'])

        def test_delete_nonexistent(self):
            resp, _ = self.request('DELETE', '/api/files/nope.png')
            self.assertEqual(resp.status, 404)

        def test_rename(self):
            resp, _ = self.request('POST', '/api/rename',
                json.dumps({"old": "alpha.png", "new": "renamed.png"}).encode(),
                {'Content-Type': 'application/json'})
            self.assertEqual(resp.status, 200)
            resp, data = self.request('GET', '/api/images')
            body = json.loads(data)
            self.assertIn('renamed.png', body['images'])
            self.assertNotIn('alpha.png', body['images'])

        def test_rename_in_subdir(self):
            resp, _ = self.request('POST', '/api/rename',
                json.dumps({"old": "subdir/one.png", "new": "x.png"}).encode(),
                {'Content-Type': 'application/json'})
            self.assertEqual(resp.status, 200)
            resp, data = self.request('GET', '/api/images?dir=subdir')
            body = json.loads(data)
            self.assertIn('subdir/x.png', body['images'])
            self.assertNotIn('subdir/one.png', body['images'])

        def test_rename_bad_name(self):
            resp, _ = self.request('POST', '/api/rename',
                json.dumps({"old": "alpha.png", "new": "bad/name.png"}).encode(),
                {'Content-Type': 'application/json'})
            self.assertEqual(resp.status, 400)

        def test_rename_conflict(self):
            resp, _ = self.request('POST', '/api/rename',
                json.dumps({"old": "alpha.png", "new": "beta.png"}).encode(),
                {'Content-Type': 'application/json'})
            self.assertEqual(resp.status, 409)

        def test_path_traversal_dir(self):
            resp, _ = self.request('GET', '/api/images?dir=../../../etc')
            self.assertEqual(resp.status, 403)

        def test_path_traversal_raw(self):
            resp, _ = self.request('GET', '/api/raw/../../../etc/passwd')
            self.assertEqual(resp.status, 403)

        def test_404(self):
            resp, _ = self.request('GET', '/api/nonexistent')
            self.assertEqual(resp.status, 404)

    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(unittest.TestLoader().loadTestsFromTestCase(TestBrowpic))
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
