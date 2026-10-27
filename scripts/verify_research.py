"""Replay a finalized real-HAPT SCAFFOLD run through a mid-run checkpoint."""
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flbench.environment import configure_cpu_runtime, environment_errors
from flbench.repository import CONFIG, COST, file_hash, find_root, load_json, protocol_hash
from flbench.research import load_policy, write_json

if __name__ == "__main__":
    root=find_root()
    if environment_errors(root):
        raise ValueError("Pinned environment is required.")
    configure_cpu_runtime(root, 101)
    import torch
    from benchmark.data import load_prepared
    from benchmark.simulator import run_experiment
    campaign=root/'configs/final/core-final-v2.json'
    spec=load_json(campaign)
    index=next(i for i,row in enumerate(spec['frozen_run_matrix'])
               if load_json(root/row['config']).get('scaffold') and row['scenario']=='natural_heterogeneous' and row['seed']==101)
    run_id=f'ghj-core-final-v2-{index+1:03d}'
    record=load_json(root/f'agents/ghj/runs/{run_id}.json')
    if record['status']!='complete':
        raise ValueError('Finalize the target run first; this check never changes the candidate.')
    row=spec['frozen_run_matrix'][index]
    method=load_json(root/row['config'])
    config=copy.deepcopy(load_json(root/CONFIG))
    config['training']['initial_learning_rate']=method.get('learning_rate',config['training']['initial_learning_rate'])
    costs=load_json(root/COST)
    dataset=load_prepared(root,scenario=row['scenario'],evaluation_stage='test',seed=101,campaign=campaign)
    original=torch.load(root/f'artifacts/{run_id}/checkpoint.pt',map_location='cpu',weights_only=True)
    temporary=root.parent/'verification'
    temporary.mkdir(exist_ok=True)
    checkpoint=temporary/'scaffold-partial.pt'
    common={'seed':101,'budget_seconds':config['evaluation']['budget_sim_seconds'],'scaffold':True,
            'server_learning_rate':method.get('server_learning_rate',1.0),'capture_curve':True}
    mid=min(70,original['completed_rounds']//2)
    run_experiment(root,config,dataset,load_policy(root,method,101),costs,max_rounds=mid,
                   checkpoint_path=checkpoint,**common)
    resumed=run_experiment(root,config,dataset,load_policy(root,method,101),costs,max_rounds=None,
                           resume_from=checkpoint,checkpoint_path=temporary/'scaffold-resumed.pt',**common)
    state=resumed['state']
    checks={
        'model_bitwise_equal':all(torch.equal(v,state['model'][k]) for k,v in original['model'].items()),
        'server_control_bitwise_equal':all(torch.equal(v,state['server_control'][k]) for k,v in original['server_control'].items()),
        'all_client_controls_bitwise_equal':all(torch.equal(v,state['client_controls'][c][k])
            for c,control in original['client_controls'].items() for k,v in control.items()),
        'client_rng_exact':all(torch.equal(v,state['client_rng'][c]) for c,v in original['client_rng'].items()),
        'global_rng_exact':torch.equal(original['torch_rng'],state['torch_rng'])
            and original['python_rng']==state['python_rng'] and original['numpy_rng']==state['numpy_rng'],
        'trace_exact':original['logs']==state['logs'],
        'histories_exact':original['histories']==state['histories'],
        'policy_exact':original['policy']==state['policy'],
        'budget_and_messages_exact':all(original[k]==state[k] for k in ('sim_seconds_used','up_bytes','down_bytes','training_steps','completed_rounds')),
        'identity_exact':original['identity_hash']==state['identity_hash']}
    report={'status':'passed' if all(checks.values()) else 'failed','source_run_id':run_id,
            'purpose':'post-freeze deterministic recovery verification; not an extra independent test seed',
            'code_commit':spec['code_commit'],'protocol_hash':protocol_hash(root),'checks':checks,
            'resume_round':mid,'completed_rounds':state['completed_rounds'],
            'verification_script_sha256':file_hash(Path(__file__)),
            'source_artifact_sha256':record['artifact_sha256']}
    write_json(root/'docs/validation/ghj-final-recovery.json',report)
    print(json.dumps(report,indent=2))
    if report['status']!='passed':
        raise AssertionError('Final real-data SCAFFOLD replay differed.')
