import argparse
import json
import logging
import mimetypes
import threading
import time
import re
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .service import APIError, Service, digest


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service):
        super().__init__(address, Handler)
        self.service = service
        self.rate_lock = threading.Lock()
        self.requests = defaultdict(deque)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Request bodies and bearer tokens must never enter logs.
        pass

    def reply(self, status, payload, content_type='application/json; charset=utf-8'):
        if not isinstance(payload, bytes):
            payload = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def handle_request(self, method):
        try:
            port = self.server.server_address[1]
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            if self.headers.get('Host') not in hosts:
                raise APIError(403, '本地开发版仅接受 localhost 主机名')
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://{host}' for host in hosts}:
                raise APIError(403, '不允许跨站请求')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise APIError(403, '不允许跨站请求')
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith('/media/') and method=='GET':
                return self.serve_media(path.removeprefix('/media/'))
            if path == '/api/dev-session' and method == 'GET':
                return self.reply(200, {'token': self.server.service.owner_token, 'mode': 'local-development'})
            if path.startswith('/api/'):
                token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                with self.server.rate_lock:
                    now = time.monotonic()
                    key = digest(token) if token else self.client_address[0]
                    events = self.server.requests[key]
                    while events and events[0] < now-60:
                        events.popleft()
                    if len(events) >= 120:
                        raise APIError(429, '请求过于频繁，请一分钟后重试')
                    events.append(now)
                if path=='/api/v1/media' and method=='POST':
                    with self.server.service.db() as db:
                        self.server.service.auth(db,token)
                    try:
                        length=int(self.headers.get('Content-Length','0'))
                    except ValueError:
                        raise APIError(400,'无效的文件大小')
                    mime=self.headers.get_content_type()
                    limit=self.server.service.policy.image_max_bytes if mime.startswith('image/') else self.server.service.policy.video_max_bytes
                    if not 0<length<=limit:
                        raise APIError(413,'图片最大 10 MB，视频最大 100 MB')
                    self.connection.settimeout(30)
                    content=self.rfile.read(length)
                    if len(content)!=length:
                        raise APIError(400,'上传不完整')
                    target=parse_qs(parsed.query).get('account_id',[None])[0]
                    return self.reply(200,self.server.service.upload(token,content,mime,target))
                data = {}
                if method == 'POST':
                    if self.headers.get_content_type() != 'application/json':
                        raise APIError(415, '请使用 application/json')
                    try:
                        length = int(self.headers.get('Content-Length','0'))
                    except ValueError:
                        raise APIError(400, '无效 Content-Length')
                    if length < 0 or length > 65536:
                        raise APIError(413, '请求体不能超过 64 KiB')
                    try:
                        data = json.loads(self.rfile.read(length))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        raise APIError(400, '请求体不是有效 JSON')
                query = {k:v[0] for k,v in parse_qs(parsed.query).items()}
                result = self.server.service.handle(method,path,data,token,query,self.headers.get('Idempotency-Key',''))
                return self.reply(200,result)
            files = {'/':'index.html','/app.js':'app.js','/markdown.js':'markdown.js','/style.css':'style.css'}
            if method != 'GET' or path not in files:
                raise APIError(404,'页面不存在')
            file = Path(__file__).with_name('static') / files[path]
            return self.reply(200,file.read_bytes(), (mimetypes.guess_type(file)[0] or 'text/plain') + '; charset=utf-8')
        except APIError as exc:
            self.reply(exc.status, {'error': exc.message})
        except Exception:
            logging.exception('Internal server error')
            self.reply(500, {'error':'服务内部错误，请查看本地日志'})

    def serve_media(self, media_id):
        if not re.fullmatch(r'[a-f0-9]{32}',media_id):
            raise APIError(404,'媒体不存在')
        file,mime=self.server.service.published_media(media_id)
        size=file.stat().st_size
        start,end,status=0,size-1,200
        range_header=self.headers.get('Range')
        if range_header:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header)
            if not match or not any(match.groups()):
                raise APIError(416,'不支持的 Range')
            a,b=match.groups()
            if a:
                start=int(a);end=min(int(b),size-1) if b else size-1
            else:
                start=max(0,size-int(b))
            if start>=size or start>end:
                raise APIError(416,'Range 超出文件大小')
            status=206
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Length',str(end-start+1))
        self.send_header('Cache-Control','no-store')
        if status==206:
            self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        with file.open('rb') as stream:
            stream.seek(start)
            remaining=end-start+1
            while remaining:
                chunk=stream.read(min(65536,remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining-=len(chunk)


def main():
    parser = argparse.ArgumentParser(description='Silisili 本地开发版（不用于公网部署）')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', default='.data/silisili.db')
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    server = Server(('127.0.0.1',args.port),Service(args.db))
    print(f'Silisili 本地开发版：http://127.0.0.1:{args.port} · Ctrl+C 停止', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
