"""Record only model JSON payloads, never transport headers or credentials."""
import json
from pathlib import Path
from .transport import request_json

def recording_transport(directory, transport=request_json):
    directory=Path(directory)
    counter=max((int(p.stem) for p in directory.glob('*.json') if p.stem.isdigit()),default=0)
    def send(url, payload, **kwargs):
        nonlocal counter
        counter+=1
        directory.mkdir(parents=True,exist_ok=True)
        (directory/f'{counter:03}.json').write_text(json.dumps({'sequence':counter,'request':payload},ensure_ascii=False,indent=2),encoding='utf-8')
        return transport(url,payload,**kwargs)
    return send
