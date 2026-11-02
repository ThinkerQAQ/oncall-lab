#!/usr/bin/env python3
"""Read-only synthetic deployment snapshot: no environment, secrets or logs."""
import datetime
import json
import subprocess
import sys
from pathlib import Path


def command(*argv):
    return subprocess.check_output(argv, text=True).strip()


def main():
    services = ('gateway-zone-a1','gateway-zone-a2','gateway-zone-b1','gateway-zone-b2','gateway-zone-c1','gateway-zone-c2','metadata-zone-a1','metadata-zone-a2','metadata-zone-b1','metadata-zone-b2','metadata-zone-c1','metadata-zone-c2')
    result = {'collected_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'git_commit': command('git','rev-parse','HEAD'),'services':{}}
    for service in services:
        ids = command('docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=oncall-lab', '--filter', f'label=com.docker.compose.service={service}').splitlines()
        if len(ids) != 1:
            raise RuntimeError(f'expected exactly one running {service}, found {len(ids)}')
        entry = json.loads(command('docker','inspect',ids[0]))[0]
        result['services'][service] = {'container':entry['Name'].lstrip('/'),'created':entry['Created'],'started_at':entry['State']['StartedAt'],'image_id':entry['Image'],'image_tag':entry['Config']['Image'],'status':entry['State']['Status']}
    file = Path(sys.argv[1]) if len(sys.argv)>1 else Path('evidence')/f'deployments-{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}.json'
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(json.dumps(result,indent=2)+'\n')
    print('Saved real Docker container versions and start timestamps:',file)
    print('Services observed:',len(result['services']))
    print('Note: Docker container restart does not prove new source code was deployed.')

if __name__=='__main__': main()
