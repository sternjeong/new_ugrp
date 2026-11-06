import collections,json
from pathlib import Path
p=Path(__file__).resolve().parent
def load(n):return json.loads((p/n).read_text())
a,b=load('weaklinks.json'),load('weaklinks2.json')
index=lambda rows:{(x['case_id'],x['method']):x for x in rows}
a,b=index(a),index(b);assert len(a)==len(b)==40 and set(a)==set(b)
counter1=load('counterfactual.json');counter2=load('counterfactual2.json')
interest1=load('interests.json');interest2=load('interests2.json')
assert all(len(x)==8 for x in (counter1,counter2,interest1,interest2))
key=load('control_key.json');control=load('control_ratings.json');assert len(control)==8 and {x['id'] for x in control}==set(key)
result={'weaklinks':{'n':40,'unsupported_1':sum(x['unsupported'] for x in a.values()),'unsupported_2':sum(x['unsupported'] for x in b.values()),
  'relation_exact_agreement':sum(a[k]['relation']==b[k]['relation'] for k in a),
  'unsupported_agreement':sum(a[k]['unsupported']==b[k]['unsupported'] for k in a)},
 'course_counterfactual':{'n_pairs':8,'first_change_score_2':sum(x['course_change_reflection']['score']==2 for x in counter1),
                          'second_scores':dict(collections.Counter(x['score'] for x in counter2))},
 'interest_counterfactual':{'n_pairs':8,'reviewer1_score_2':sum(x['score']==2 for x in interest1),'reviewer2_score_2':sum(x['score']==2 for x in interest2)},
 'control':{'inserted_detected':sum(x['unsupported'] for x in control if key[x['id']]),'inserted_total':sum(key.values()),
            'original_flagged':sum(x['unsupported'] for x in control if not key[x['id']]),'original_total':sum(not x for x in key.values())}}
(p/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
