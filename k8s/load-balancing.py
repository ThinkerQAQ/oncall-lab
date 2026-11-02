#!/usr/bin/env python3
"""Measure real per-Pod QPS bias through a Kubernetes Service and Kitex TCP pool.

A ClusterIP routes connections, not every individual Thrift message. Do not
infer physical AZ weights from this single-host experiment.
"""
import json
import os
import re
import subprocess
import time
import urllib.request
from collections import Counter
from pathlib import Path

BASE=Path(__file__).resolve().parent.parent
KUBECTL=os.environ.get('KUBECTL_BIN',str(BASE/'Data/bin/kubectl'))
CONFIG=str(BASE/'Data/kind-kubeconfig')
NAMESPACE='oncall-lab'

def k(*args):
    return subprocess.check_output([KUBECTL,'--kubeconfig',CONFIG,'-n',NAMESPACE,*args],text=True)

def counters():
    data=json.loads(k('get','pods','-l','app=metadata','-o','json'))
    seen={}
    for pod in data['items']:
        name=pod['metadata']['name']
        raw=k('exec',name,'--','wget','-q','-O-','http://127.0.0.1:9091/metrics')
        m=re.search(r'^rpc_server_requests_total\{result="success"\}\s+([0-9.]+)$',raw,re.M)
        seen[name]=float(m.group(1)) if m else 0.0
    return seen

if __name__=='__main__':
    before=counters()
    n=240
    started=time.monotonic()
    for i in range(n):
        u=f'http://127.0.0.1:28084/metadata?id=kube-clusterip-{i}'
        with urllib.request.urlopen(u,timeout=4) as resp:
            if resp.status!=200:
                raise RuntimeError(f'RPC {i} returned {resp.status}')
            resp.read()
    after=counters()
    delta={name:round(after[name]-before[name]) for name in before}
    print('Synthetic request total:',n,'measured seconds:',round(time.monotonic()-started,2))
    for name,number in sorted(delta.items()):
        print(f'{name}: {number}')
    print('Total server counts:',sum(delta.values()))
    if sum(delta.values()) != n:
        raise RuntimeError('Server counters did not match delivered requests')
    print('PASS: measured real per-Pod distribution; no assumed equal-weight result')
