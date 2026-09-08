"""Download official AASIST checkpoint + LICENSE from Hugging Face (pinned commit)."""
import os
import urllib.request

PIN = 'e842653505c2832ac9f46bbf56173b0f54ef82a7'
BASE = f'https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST/resolve/{PIN}/'
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models')
os.makedirs(OUT, exist_ok=True)


def fetch(name, dest):
    url = BASE + name
    print('GET', url)
    req = urllib.request.Request(url, headers={'User-Agent': 'VAuth/0.1'})
    with urllib.request.urlopen(req) as r, open(dest, 'wb') as f:
        total = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    print('wrote', dest, total, 'bytes')


fetch('AASIST.pth', os.path.join(OUT, 'AASIST.pth'))
fetch('LICENSE', os.path.join(OUT, 'AASIST.LICENSE'))
