"""Open the local app only once the backend is ready."""
import json,time,webbrowser
from urllib.request import urlopen
url='http://127.0.0.1:8013'
for _ in range(120):
    try:
        with urlopen(url+'/api/health',timeout=1) as response:data=json.load(response)
        if data.get('status')=='ok' and data.get('pipeline_id')=='frequency_13_max_f1_validation_v1':
            webbrowser.open(url+'/?v=app-complete');break
    except Exception:pass
    time.sleep(.5)
