#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from app.services.asr_policy_v2 import policy_payload,policy_sha256
def main():
  threshold=json.loads((ROOT/'asr-threshold-lock.json').read_text(encoding='utf-8'))
  payload=policy_payload(threshold['contract']); payload['historical_threshold_identifier']=threshold['threshold_sha256']; payload['ASR_POLICY_V2_SHA256']=policy_sha256(threshold['contract'])
  target=ROOT/'asr-policy-v2.json'; target.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(payload['ASR_POLICY_V2_SHA256'])
if __name__=='__main__': main()
