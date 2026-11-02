#!/usr/bin/env python3
"""Verify Kind synthetic zones using real Kubernetes Pods, Nodes, EndpointSlices."""
import collections
import json
import sys
from pathlib import Path

def verify(nodes,pods,slices):
    node_zones={n['metadata']['name']:n.get('metadata',{}).get('labels',{}).get('topology.kubernetes.io/zone') for n in nodes['items']}
    all_pods=[p for p in pods['items'] if p['metadata'].get('labels',{}).get('app')=='metadata' and not p['metadata'].get('deletionTimestamp')]
    if len(all_pods)!=6:
        raise ValueError(f'expected 6 Metadata Pods; got {len(all_pods)}')
    zones=collections.Counter()
    pod_ips=set()
    for p in all_pods:
        node=p['spec']['nodeName']
        zone=node_zones.get(node)
        if zone not in {'lab-zone-a','lab-zone-b','lab-zone-c'}:
            raise ValueError(f'unexpected node zone {node}:{zone}')
        state={c['type']:c['status'] for c in p['status'].get('conditions',[])}
        if state.get('Ready')!='True':
            raise ValueError(f'Pod {p["metadata"]["name"]} not ready')
        zones[zone]+=1
        pod_ips.add(p['status']['podIP'])
    if set(zones.values())!={2} or len(zones)!=3:
        raise ValueError(f'Pods not evenly distributed: {zones}')
    endpoints=[]
    for sl in slices['items']:
        for e in sl.get('endpoints',[]):
            if e.get('conditions',{}).get('ready'):
                endpoints.extend(e['addresses'])
    if set(endpoints)!=pod_ips:
        raise ValueError(f'Service ready endpoints {sorted(endpoints)} do not match Pod IPs {sorted(pod_ips)}')
    return dict(sorted(zones.items()))

if __name__=='__main__':
    nodes,pods,slices=(json.loads(Path(f).read_text()) for f in sys.argv[1:4])
    print('PASS: real Kubernetes deployment topology:',verify(nodes,pods,slices))
