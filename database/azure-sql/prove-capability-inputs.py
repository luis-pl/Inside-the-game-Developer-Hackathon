"""Mathematical feasibility checks on points/edges SELECTed from Azure.

These are reproducible analysis examples, not the application's topology tools.
Only Python's standard library is needed.
"""
import collections
import json
import math
import pathlib

root=pathlib.Path(__file__).parents[2]
evidence=json.loads((root/'docs/data-capabilities-evidence.json').read_text(encoding='utf-8'))
assert evidence['status']=='passed'
points=evidence['sections']['spatialProof']
assert len(points)==22

def hull_area(points):
    pts=sorted(set(points))
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower=[]
    for p in pts:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
        lower.append(p)
    upper=[]
    for p in reversed(pts):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
        upper.append(p)
    h=lower[:-1]+upper[:-1]
    return abs(sum(h[i][0]*h[(i+1)%len(h)][1]-h[(i+1)%len(h)][0]*h[i][1] for i in range(len(h))))/2

spatial=[]
for team in sorted({p['position_team'] for p in points}):
    p=[p for p in points if p['position_team']==team and p['on_pitch_slot']!=1]
    xy=[(p['x_m'],p['y_m']) for p in p]
    n=len(p);matrix=[[math.dist(a,b) for b in xy] for a in xy]
    assert all(abs(matrix[i][j]-matrix[j][i])<1e-9 for i in range(n) for j in range(n))
    adjacency={i:{j for j in range(n) if i!=j and matrix[i][j]<=15} for i in range(n)}
    seen=set();components=0
    for i in range(n):
        if i in seen:continue
        components+=1;todo=[i]
        while todo:
            j=todo.pop()
            if j in seen:continue
            seen.add(j);todo.extend(adjacency[j]-seen)
    cx=sum(x for x,y in xy)/n;cy=sum(y for x,y in xy)/n
    edges=sum(len(a) for a in adjacency.values())//2
    spatial.append({'team_id':team,'outfield_players':n,'centroid_m':[cx,cy],
      'longitudinal_span_m':max(x for x,y in xy)-min(x for x,y in xy),'lateral_span_m':max(y for x,y in xy)-min(y for x,y in xy),
      'convex_hull_area_m2':hull_area(xy),'radius_of_gyration_m':math.sqrt(sum((x-cx)**2+(y-cy)**2 for x,y in xy)/n),
      'distance_matrix_shape':[n,n],'proximity_radius_m':15,'proximity_edges':edges,'proximity_components':components,
      'graph_cycle_rank':edges-n+components,'graph_cycle_rank_is_not_geometric_hole_count':True})

graphs=[]
for team in sorted({p['team_id'] for p in evidence['sections']['graphProof']}):
    rows=[r for r in evidence['sections']['graphProof'] if r['team_id']==team]
    nodes={r['source_player'] for r in rows}|{r['target_player'] for r in rows}
    assert all(r['source_player']!=r['target_player'] and r['passes']>0 for r in rows)
    strength=collections.Counter()
    for r in rows:strength[r['source_player']]+=r['passes'];strength[r['target_player']]+=r['passes']
    graphs.append({'team_id':team,'nodes':len(nodes),'directed_edges':len(rows),'completed_passes':sum(r['passes'] for r in rows),
      'directed_density':len(rows)/(len(nodes)*(len(nodes)-1)),
      'highest_total_strength_player':strength.most_common(1)[0][0],'highest_total_strength':strength.most_common(1)[0][1]})

result={'status':'passed','scope':'Feasibility examples using actual SELECT results; does not constitute an implemented analytics service',
 'snapshot':{k:points[0][k] for k in ['event_id','match_id','period','period_time_ms','run_id']},'spatial':spatial,'passing_graphs':graphs}
(root/'docs/data-capabilities-proofs.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
