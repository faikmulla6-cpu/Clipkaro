import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.services.roman_hinglish_policy_v3 import normalize_v3
from app.services.roman_hinglish_display_v1 import display_text,payload,sha256
D=ROOT/'asr-qualification-evidence/elevenlabs-roman-v3-real-video-qa';T=D/'bassi-native-word-timeline.json'
expected='83722be8d5acccecc8fde46f316e242fdb9d37ce1105bec6a752009739025522'
if hashlib.sha256(T.read_bytes()).hexdigest()!=expected:raise RuntimeError('timeline integrity failure')
timeline=json.loads(T.read_text(encoding='utf-8'));policy={'ROMAN_HINGLISH_DISPLAY_V1_SHA256':sha256(),**payload()};(D/'display-policy-v1.json').write_text(json.dumps(policy,indent=2,sort_keys=True)+'\n')
rows=[]
for w in timeline['native_words']:
 v3=' '.join(normalize_v3(w['word']).split());display=display_text(v3);rows.append({'source_index':w['index'],'raw_word':w['word'],'v3_word':v3,'display_word':display,'start':w['start'],'end':w['end'],'timing_source':'ELEVENLABS_NATIVE_WORD'})
out={'timeline_sha256':expected,'display_policy_sha256':sha256(),'words':rows};p=D/'bassi-display-word-map.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'words':len(rows),'normalized':sum(x['v3_word']!=x['display_word']for x in rows),'hash':sha256()}))
