import json
from pathlib import Path
def test_graph_config_frozen_and_pool_blind():
 root=Path(__file__).parents[1]; c=json.loads((root/'configs/graph_v2_frozen.json').read_text()); assert c['status']=='frozen_before_graph_results' and c['tuning_after_results'] is False
 blind=[json.loads(x) for x in (root/'runs/v2/phase3_graph/pool/graph_unseen_blind.jsonl').read_text().splitlines()]; sealed=[json.loads(x) for x in (root/'runs/v2/phase3_graph/pool/graph_unseen_sealed.jsonl').read_text().splitlines()]
 assert {x['display_id'] for x in blind}=={x['display_id'] for x in sealed}
 assert not ({'system','rank','score'} & set(blind[0]))
 assert {'system','rank','score'} <= set(sealed[0])
