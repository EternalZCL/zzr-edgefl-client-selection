"""Re-execute a frozen campaign under fresh run IDs without overwriting evidence."""
import argparse
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flbench.environment import configure_cpu_runtime, environment_errors
from flbench.repository import find_root,load_json,protocol_hash
from flbench.research import run_campaign,write_json

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',type=Path,default=Path('configs/final/core-final-v2.json'))
    parser.add_argument('--replicate-id',default='core-final-replay-v1')
    parser.add_argument('--plan-only',action='store_true')
    args=parser.parse_args()
    root=find_root()
    if environment_errors(root):
        raise ValueError('Use the pinned checkout-local uv environment.')
    configure_cpu_runtime(root,11)
    original=load_json((root/args.campaign).resolve())
    if original['status']!='frozen' or original['protocol_hash']!=protocol_hash(root):
        raise ValueError('Only an unchanged frozen campaign may be reproduced.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,70}',args.replicate_id) or args.replicate_id==original['campaign_id']:
        raise ValueError('Choose a fresh lowercase campaign ID.')
    replica={**original,'campaign_id':args.replicate_id,'kind':'reproduction',
             'reproduces_campaign':original['campaign_id'],
             'reproduction_only_not_additional_independent_seeds':True}
    target=root/'artifacts/reproductions'/f'{args.replicate_id}.json'
    if target.exists() and load_json(target)!=replica:
        raise ValueError('Refusing to alter an existing reproduction manifest.')
    write_json(target,replica)
    print(target,flush=True)
    if not args.plan_only:
        run_campaign(root,target)
