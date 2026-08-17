#!/usr/bin/env python3
"""Read-only forensic analysis for the failed STEP 2B API-ASR qualification."""
from __future__ import annotations
import json, re, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from app.services.asr_benchmark import error_rate, normalize_text

E=ROOT/'asr-qualification-evidence'/'api-step2b-2026-08-13'
TOKEN=re.compile(r"[\w\u0900-\u097f]+",re.UNICODE)
ANNOTATION=re.compile(r"<[^>]*>|\{[^}]*\}|\[[^]]*\]")

def tokens(text, diagnostic=False):
    value=unicodedata.normalize('NFKC',str(text or '')).casefold().replace('\u200c','').replace('\u200d','')
    if diagnostic: value=ANNOTATION.sub(' ',value).replace('\u0964',' ').replace('\u0965',' ')
    return TOKEN.findall(value)
def align(ref,hyp,diagnostic=False):
    a,b=tokens(ref,diagnostic),tokens(hyp,diagnostic); n,m=len(a),len(b)
    dp=[[0]*(m+1) for _ in range(n+1)]
    for i in range(n+1): dp[i][0]=i
    for j in range(m+1): dp[0][j]=j
    for i in range(1,n+1):
      for j in range(1,m+1): dp[i][j]=min(dp[i-1][j]+1,dp[i][j-1]+1,dp[i-1][j-1]+(a[i-1]!=b[j-1]))
    i,j=n,m; ops=[]
    while i or j:
      if i and j and dp[i][j]==dp[i-1][j-1]+(a[i-1]!=b[j-1]): ops.append(('=',a[i-1],b[j-1]) if a[i-1]==b[j-1] else ('S',a[i-1],b[j-1]));i-=1;j-=1
      elif i and dp[i][j]==dp[i-1][j]+1: ops.append(('D',a[i-1],''));i-=1
      else: ops.append(('I','',b[j-1]));j-=1
    ops.reverse(); c=Counter(op[0] for op in ops)
    return {'S':c['S'],'D':c['D'],'I':c['I'],'N':n,'H':m,'ops':ops,'wer':(c['S']+c['D']+c['I'])/max(n,1)}
def diagnostic_cer(ref,hyp):
    a=list(''.join(tokens(ref,True))); b=list(''.join(tokens(hyp,True))); n,m=len(a),len(b)
    previous=list(range(m+1))
    for i,x in enumerate(a,1):
      current=[i]
      for j,y in enumerate(b,1): current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
      previous=current
    return previous[-1]/max(n,1)
def load(name): return json.loads((E/name).read_text(encoding='utf-8'))['results']
def ref_for(case,row):
    refs=case.get('raw_references') or {'reference':case['reference']}
    # Same frozen rule: independently select minimum WER reference, preserving all scores.
    scored=[(align(reference,row['transcript']),key,reference) for key,reference in refs.items()]
    return min(scored,key=lambda value:value[0]['wer'])
def main():
    manifest=json.loads((ROOT/'stress_corpus'/'manifest.json').read_text(encoding='utf-8')); cases={x['id']:x for x in manifest['cases']}
    groq=[x for x in load('groq-results.json') if x['scenario']=='clean' and x.get('success')]; cf={x['case_id']:x for x in load('cloudflare-results.json') if x['scenario']=='clean' and x.get('success')}
    synthetic=[('identical','नमस्ते world','नमस्ते world',(0,0,0)),('insertion','a b','a x b',(0,0,1)),('deletion','a b c','a c',(0,1,0)),('substitution','a b','a x',(1,0,0)),('punctuation','नमस्ते, दुनिया!','नमस्ते दुनिया',(0,0,0)),('danda_punctuation_expected','यह है','यह है।',(0,0,0)),('whitespace','a   b',' a b ',(0,0,0)),('unicode_devanagari','क़िला','क़िला',(0,0,0)),('english_case','HELLO World','hello world',(0,0,0)),('mixed','मैं use करता हूँ AI','मैं use करता हूँ ai',(0,0,0))]
    scorer=[]
    for name,r,h,expected in synthetic:
      a=align(r,h); actual=(a['S'],a['D'],a['I']); scorer.append({'case':name,'expected':expected,'actual':actual,'pass':actual==expected,'wer':error_rate(r,h,unit='word'),'cer':error_rate(r,h,unit='char')})
    report={'immutable_inputs':{'corpus_lock':'35a7c63d6c2f645fb5b73ef33c2ef1989e9462aba8048b11394d4ae83626a78b','threshold_lock':'4f5e49ab72cebcf51c58b4f83204b1d9a29e0c607c6b19b5c324806b61f9347e'},'scorer_synthetic':scorer,'languages':{},'timestamps':{},'provider_comparison':{}}
    for lang in ('hi','mr','hinglish'):
      rows=[x for x in groq if x['language']==lang]; aggregate=Counter(); pairs=Counter(); categories=Counter(); diagnostic=[]
      for row in rows:
        case=cases[row['case_id']]; a,key,reference=ref_for(case,row); aggregate.update({k:a[k] for k in ('S','D','I','N','H')})
        diag=align(reference,row['transcript'],diagnostic=True)
        for op,r,h in a['ops']:
          if op=='S': pairs[(r,h)]+=1
          if op=='=': continue
          if r and (ANNOTATION.search(r) or r in {'noise','school','hospital'}): categories['REFERENCE_VARIATION']+=1
          elif r and h and (unicodedata.normalize('NFC',r)==unicodedata.normalize('NFC',h) or r.replace('\u0964','').replace('\u0965','')==h.replace('\u0964','').replace('\u0965','')): categories['NORMALIZATION_ERROR']+=1
          elif (any('a'<=z<='z' for z in r) if r else False) != (any('a'<=z<='z' for z in h) if h else False): categories['LANGUAGE_OR_SCRIPT_ERROR']+=1
          else: categories['GENUINE_ASR_ERROR']+=1
        diagnostic.append({'case_id':row['case_id'],'reference':reference,'reference_key':key,'provider_transcript':row['transcript'],'wer':row['wer'],'cer':row['cer'],'S':a['S'],'D':a['D'],'I':a['I'],'detected_language':row['detected_language'],'duration':row['duration_seconds'],'diagnostic_annotation_and_danda_stripped_wer':round(diag['wer'],4),'diagnostic_annotation_and_danda_stripped_cer':round(diagnostic_cer(reference,row['transcript']),4)})
      diagnostic.sort(key=lambda x:x['wer']); median=diagnostic[max(0,len(diagnostic)//2-5):len(diagnostic)//2+5]
      report['languages'][lang]={'authoritative_mean_wer':round(sum(x['wer'] for x in rows)/len(rows),4),'authoritative_mean_cer':round(sum(x['cer'] for x in rows)/len(rows),4),'diagnostic_annotation_and_danda_stripped_mean_wer':round(sum(x['diagnostic_annotation_and_danda_stripped_wer'] for x in diagnostic)/len(diagnostic),4),'diagnostic_annotation_and_danda_stripped_mean_cer':round(sum(x['diagnostic_annotation_and_danda_stripped_cer'] for x in diagnostic)/len(diagnostic),4),'edit_totals':dict(aggregate),'top_substitution_pairs':[{'reference':a,'hypothesis':b,'count':n} for (a,b),n in pairs.most_common(25)],'automated_discrepancy_classification':dict(categories),'lowest_10':diagnostic[:10],'median_10':median,'highest_10':diagnostic[-10:]}
    issues=Counter(); invalid=[x for x in load('groq-results.json') if x.get('success') and not x.get('timestamps_valid')]
    for row in invalid:
      for issue in row.get('timestamp_issues') or []:
        issue=re.sub(r'^segment_\d+_', '',issue); issue=re.sub(r'^word_\d+_', '',issue); issues[issue]+=1
    report['timestamps']={'total_successes':902,'invalid_cases':len(invalid),'invalid_percent':round(100*len(invalid)/902,2),'issue_counts':dict(issues),'root_cause':'MIXED: provider-native word ordering is non-monotonic, but the qualification runner validated raw merge_chunk_results output and omitted production _transcribe_api_impl() stabilize_word_timestamps(). The stored 91.46% timestamp rate is therefore not equivalent to the production-path stabilized timestamp rate. The separate >600s diagnostic applied stabilization and passed; a corrected timestamp qualification requires a separately versioned run.'}
    wins=Counter(); overlap=[]
    for row in groq:
      other=cf.get(row['case_id']);
      if not other: continue
      difference=row['wer']-other['wer']
      category='groq_clearly_wins' if difference<=-.10 else 'cloudflare_clearly_wins' if difference>=.10 else 'both_fail_similarly'
      wins[category]+=1
      if category=='both_fail_similarly' and row['wer']>.28 and other['wer']>.28: overlap.append(row['case_id'])
    report['provider_comparison']={'clean_cases_compared':sum(wins.values()),'outcomes':dict(wins),'both_fail_above_clean_threshold':len(overlap),'shared_failure_case_ids':overlap}
    report['reference_compatibility']={'vaani':'All three official references are individually scored; no concatenation. Frozen independent per-metric-minimum rule is reproduced. 76/90 Vaani references have angle annotations, 63 brace placeholders, and 43 square annotations; they can materially inflate conventional ASR WER because they are not spoken.','slr64':'line_index.tsv is a plain transcript index without markup; its two ZW characters are removed by diagnostic normalization but frozen NFKC/token policy does not explicitly remove them.','slr104':'Hinglish reference uses Devanagari Hindi plus Latin English words; this is appropriate for genuine code switch, but providers may return another script/transliteration, a real script-convention mismatch rather than punctuation.'}
    (E/'forensic-step3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    lines=['# STEP 3 forensic API-ASR analysis','',f"Scorer synthetic tests: {'PASS' if all(x['pass'] for x in scorer) else 'FAIL'}",'', 'The authoritative qualification remains unchanged.']
    for lang,data in report['languages'].items(): lines += ['',f'## {lang}',f"Frozen mean WER/CER: {data['authoritative_mean_wer']:.4f} / {data['authoritative_mean_cer']:.4f}",f"Diagnostic annotation/danda-stripped WER/CER: {data['diagnostic_annotation_and_danda_stripped_mean_wer']:.4f} / {data['diagnostic_annotation_and_danda_stripped_mean_cer']:.4f}",f"Edits: {data['edit_totals']}"]
    lines += ['',f"Timestamp-invalid cases: {report['timestamps']['invalid_cases']}/902 ({report['timestamps']['invalid_percent']:.2f}%)",f"Provider comparison: {report['provider_comparison']['outcomes']}"]
    (E/'forensic-step3.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'scorer_pass':all(x['pass'] for x in scorer),'report':str(E/'forensic-step3.json')}))
if __name__=='__main__': main()
