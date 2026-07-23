from scripts.run_phase2a_r5_windowed import WINDOW,OVERLAP,STEP,make_windows
class Tok:
 def __call__(self,text,**kw):
  words=text.split(); offsets=[]; p=0
  for w in words: s=text.index(w,p); offsets.append((s,s+len(w))); p=s+len(w)
  return {'input_ids':list(range(len(words))),'offset_mapping':offsets}
def test_fixed_window_contract():
 w=make_windows(' '.join(f'w{i}' for i in range(600)),Tok(),'c')
 assert (WINDOW,OVERLAP,STEP)==(254,32,222)
 assert [(x['start_token'],x['end_token']) for x in w]==[(0,254),(222,476),(444,600)]
