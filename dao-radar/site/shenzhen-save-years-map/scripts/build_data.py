#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'data'/'communities.json'
if not source.exists(): source=ROOT/'data'/'seed.json'
data=json.loads(source.read_text(encoding='utf-8'))
(ROOT/'data'/'communities.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'data'/'communities.js').write_text('window.HOUSING_DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
print(f"built {len(data.get('communities',[]))} communities")
