"""Start a local dashboard and open it once ready."""
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser


def main():
    root = Path(__file__).resolve().parent
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    process = subprocess.Popen([
        sys.executable, '-m', 'streamlit', 'run', str(root / 'app.py'),
        '--server.address=127.0.0.1', f'--server.port={port}',
        '--server.headless=true', '--browser.gatherUsageStats=false',
    ], cwd=root)
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError('Dashboard could not start. Check the error above.')
            try:
                with urlopen(f'{url}/_stcore/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError('Dashboard startup timed out.')
        print(f'Open {url} in your browser. Press Ctrl+C here to stop.')
        webbrowser.open(url)
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
