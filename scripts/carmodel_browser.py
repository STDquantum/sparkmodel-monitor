"""Visible, user-operated verification with one browser thread and session."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import Event
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler

from paths import ROOT


class BrowserUnavailable(RuntimeError):
    pass


def browser_executable(channel):
    """Find the installed browser, including custom Windows install locations."""
    filename = 'msedge.exe' if channel == 'msedge' else 'chrome.exe'
    candidates = []
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, rf'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{filename}', 0, winreg.KEY_READ | view) as key:
                        candidates.append(winreg.QueryValue(key, None).strip('"'))
                except OSError:
                    pass
        relative = 'Microsoft/Edge/Application/msedge.exe' if channel == 'msedge' else 'Google/Chrome/Application/chrome.exe'
        candidates.extend(str(Path(base) / relative) for name in ('LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)') if (base := os.environ.get(name)))
    executable = shutil.which(filename) or shutil.which('microsoft-edge' if channel == 'msedge' else 'google-chrome')
    if executable:
        candidates.append(executable)
    for candidate in candidates:
        if Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise BrowserUnavailable('未找到浏览器。请安装 Chrome，或使用 --browser-channel msedge。')


def browser_command(executable, profile, port):
    if not 1 <= port <= 65535:
        raise ValueError('A fixed nonzero local debugging port is required')
    return [executable, f'--user-data-dir={profile}', '--remote-debugging-address=127.0.0.1',
            f'--remote-debugging-port={port}', '--no-first-run', '--no-default-browser-check', 'about:blank']


# Only read real product/search content. A challenge/error page is never a result.
READY = r"""({url,image}) => {
  const target=new URL(url),current=new URL(location.href);
  const path=value=>value.replace(/^\/(en|it|de|fr|es|pt)(?=\/)/,'').replace(/\/$/,'');
  if(current.hostname.replace(/^www\./,'')!==target.hostname.replace(/^www\./,'') || path(current.pathname)!==path(target.pathname))return false;
  for(const key of ['keyword','nuOb','page']){
    const fallback=key==='page'?'1':'';
    if((current.searchParams.get(key)||fallback)!==(target.searchParams.get(key)||fallback))return false;
  }
  if(image)return document.contentType.startsWith('image/') && !!document.querySelector('img')?.naturalWidth;
  if(document.querySelector('#challenge-running,#challenge-stage,iframe[src*="challenges.cloudflare.com"]'))return false;
  if(target.pathname==='/search')return !!document.querySelector('article.prod-card') ||
    /did not return any results|no (?:items|results|products)|0 (?:items|results|products)|No models/i.test(document.body?.innerText||'');
  return !!document.querySelector('table.product-features') &&
    [...document.querySelectorAll('script[type="application/ld+json"]')].some(el=>{
      try{return JSON.parse(el.textContent)['@type']==='Product'}catch{return false}
    });
}"""


class BrowserSession:
    def __init__(self, *, force=False, channel='chrome', verification_timeout=120):
        self.active = force
        self.channel = channel
        self.verification_timeout = verification_timeout
        self.cancelled = Event()
        self.failed = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='carmodel-browser')
        self.playwright = self.context = self.page = None
        self.browser = self.process = None
        self.last_navigation = None
        self.last_request = 0

    def __enter__(self):
        self.previous_signal = signal.getsignal(signal.SIGINT)

        def interrupt(signum, frame):
            self.cancelled.set()
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, interrupt)
        return self

    def __exit__(self, *args):
        self.cancelled.set()
        try:
            self.executor.submit(self._close).result()
        finally:
            self.executor.shutdown(wait=True, cancel_futures=True)
            signal.signal(signal.SIGINT, self.previous_signal)

    def _start(self):
        if self.context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserUnavailable('浏览器模式需要 Playwright。请用当前 Python 执行：python -m pip install playwright') from error
        executable = browser_executable(self.channel)
        # Use a dedicated native profile; retain the previous profile and its files.
        profile = ROOT / '.carmodel-browser' / ('native-' + self.channel)
        profile.mkdir(parents=True, exist_ok=True)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        endpoint = f'http://127.0.0.1:{port}'
        try:
            # Launch installed Chrome normally, then attach; do not override UA,
            # navigator, Canvas/WebGL, locale or browser security settings.
            self.process = subprocess.Popen(browser_command(executable, profile, port),
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opener = build_opener(ProxyHandler({}))
            deadline = time.monotonic() + 20
            while True:
                if self.cancelled.is_set():
                    raise BrowserUnavailable('已取消 Carmodel 浏览器采集')
                if self.process.poll() is not None:
                    raise BrowserUnavailable('浏览器未正常启动。请先关闭上次打开的 Carmodel 专用窗口再运行。')
                try:
                    with opener.open(endpoint + '/json/version', timeout=1) as response:
                        info = json.load(response)
                    if info.get('webSocketDebuggerUrl'):
                        break
                except (URLError, TimeoutError, ConnectionError, ValueError):
                    pass
                if time.monotonic() >= deadline:
                    raise BrowserUnavailable('等待本机浏览器启动超时，请关闭旧的 Carmodel 专用窗口后重试。')
                self.cancelled.wait(.2)
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.connect_over_cdp(endpoint, timeout=15000)
            self.context = self.browser.contexts[0]
        except BrowserUnavailable:
            raise
        except Exception as error:
            raise BrowserUnavailable(
                '无法启动浏览器。请安装 Chrome，或使用 --browser-channel msedge；'
                '同一时间只能运行一个比美高刷新任务。') from error
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.on('response', self._response)
        print('已连接普通启动的 Carmodel 浏览器。遇到验证请手动完成，显示商品页面后自动继续。关闭窗口或按 Ctrl+C 可取消。', flush=True)

    def _response(self, response):
        if response.request.is_navigation_request() and response.frame == self.page.main_frame:
            self.last_navigation = response

    def get(self, url, *, image=False):
        self.active = True
        future = self.executor.submit(self._get, url, image)
        while True:
            if self.cancelled.is_set():
                raise BrowserUnavailable('已取消 Carmodel 浏览器采集')
            try:
                return future.result(timeout=.25)
            except FutureTimeout:
                continue

    def _get(self, url, image):
        try:
            if self.failed:
                raise BrowserUnavailable(self.failed)
            if self.cancelled.is_set():
                raise BrowserUnavailable('已取消 Carmodel 浏览器采集')
            if urlsplit(url).scheme not in {'https', 'http'}:
                raise BrowserUnavailable('不支持的 Carmodel 页面地址')
            self._start()
            from playwright.sync_api import TimeoutError as BrowserTimeout, Error as BrowserError
            # Serialize requests and leave a short gap, including image requests.
            delay = max(0, 3 - (time.monotonic() - self.last_request))
            if self.cancelled.wait(delay):
                raise BrowserUnavailable('已取消 Carmodel 浏览器采集')
            self.last_request = time.monotonic()
            if image:
                response = self.context.request.get(url, timeout=30000)
                try:
                    if response.ok and response.headers.get('content-type', '').startswith('image/'):
                        return response.body()
                    if response.status not in {401, 403, 429}:
                        raise BrowserUnavailable(f'Carmodel 图片请求失败：HTTP {response.status}')
                finally:
                    response.dispose()
            self.last_navigation = None
            try:
                response = self.page.goto(url, wait_until='domcontentloaded', timeout=45000)
                if response and response.status >= 400 and response.headers.get('cf-mitigated') != 'challenge':
                    raise BrowserUnavailable(f'Carmodel HTTP {response.status}；已停止本次采集')
            except BrowserTimeout:
                pass  # A verification/navigation can still finish in the visible window.
            except BrowserError as error:
                if 'net::ERR_ABORTED' not in str(error) or self.page.is_closed():
                    raise
            prompted = False
            deadline = time.monotonic() + self.verification_timeout
            while not self.cancelled.is_set():
                if self.page.is_closed():
                    raise BrowserUnavailable('浏览器已关闭；本次 Carmodel 采集取消')
                if time.monotonic() >= deadline:
                    raise BrowserUnavailable(f'等待正常页面超过 {self.verification_timeout:g} 秒；验证未通过或页面结构发生变化，已停止。请勿反复点击验证，先确认普通浏览器能否正常访问 Carmodel。')
                try:
                    self.page.wait_for_function(READY, arg={'url': url, 'image': image}, polling=250, timeout=1000)
                    if prompted:
                        print('页面已就绪，继续采集。', flush=True)
                    if image:
                        response = self.last_navigation
                        if response is None or not response.ok or not response.headers.get('content-type', '').startswith('image/'):
                            raise BrowserUnavailable('图片尚未正常载入；本次采集停止')
                        return response.body()
                    return self.page.content()
                except BrowserTimeout:
                    if not prompted:
                        self.page.bring_to_front()
                        print(f'等待你在浏览器中完成验证或确认页面正常显示：{url}\n不会自动点击验证码。完成后自动继续；若一直无法打开，可关闭窗口取消。', flush=True)
                        prompted = True
                except BrowserError as error:
                    # During a user-completed verification, the document may be replaced.
                    if 'Execution context was destroyed' not in str(error):
                        raise
            raise BrowserUnavailable('已取消 Carmodel 浏览器采集')
        except Exception as error:
            self.failed = str(error)
            if isinstance(error, BrowserUnavailable):
                raise
            raise BrowserUnavailable(f'Carmodel 浏览器采集停止：{error}') from error

    def _close(self):
        try:
            if self.browser or self.context:
                try:
                    (self.browser or self.context).close()
                except Exception:
                    pass  # The user may already have closed the verification window.
        finally:
            try:
                if self.playwright:
                    self.playwright.stop()
            finally:
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
