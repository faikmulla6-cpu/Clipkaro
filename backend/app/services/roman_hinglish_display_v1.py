"""Deterministic user-facing Roman Hinglish spelling policy; never a scorer."""
from __future__ import annotations
import hashlib,json,re
VERSION='2026-08-14-display-v1'
LEX={'kitane':'kitne','kitanee':'kitni','kisee':'kisi','ceej':'cheez','calegaa':'chalega','calegee':'chalegi','aaegee':'aayegi','aaegaa':'aayega','matalab':'matlab','bacce':'bacche','acchaa':'accha','acchee':'acchi','rahaa':'raha','rahee':'rahi','jaanaa':'jaana','tumhaare':'tumhare','kyon':'kyu'}
PROTECTED={'engineering','meeting','client','timing','cancel','roommate','hostel','show','video','ticket','college','donation','paper','time','scope','morale','artist','autopilot','student','sorry','thank','you'}
ENTITIES={'youtube':'YouTube','instagram':'Instagram','iit':'IIT','srm':'SRM','london':'London','chicago':'Chicago'}
TOKEN=re.compile(r"[A-Za-z0-9']+|[^A-Za-z0-9']+",re.UNICODE)
def display_token(token:str)->str:
 low=token.casefold()
 if low in ENTITIES:return ENTITIES[low]
 if token.isupper() and len(token)<=6:return token
 if low in PROTECTED:return low
 return LEX.get(low,low)
def display_text(text:str)->str:
 return ''.join(display_token(x) if x and x[0].isalnum() else x for x in TOKEN.findall(text))
def payload():return {'version':VERSION,'lexicon':LEX,'protected':sorted(PROTECTED),'entities':ENTITIES,'semantic_rewriting':False}
def sha256():return hashlib.sha256(json.dumps(payload(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
