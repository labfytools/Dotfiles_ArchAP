#!/usr/bin/python3
"""Prépare un nouveau bundle V2 dans le LAB, sans écrire les destinations actives."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path);args=parser.parse_args()
    bundle=args.bundle.absolute()
    if os.getuid()!=1000 or os.geteuid()!=1000 or not bundle.is_relative_to('/var/tmp'):
        parser.error('Préparation utilisateur uniquement dans /var/tmp')
    source=Path(__file__).resolve().parent
    # Les deux outils préparent à partir de leurs sources actuelles ; jamais de .new V1 réutilisé.
    bundle.mkdir(mode=0o700)
    root,user=bundle/'root',bundle/'user'
    for tool,dest in [('session-update.py',root),('mosaic-user-update.py',user)]:
        subprocess.run(['/usr/bin/python3','-I','-B',str(source/tool),'prepare',str(dest)],check=True)
    rt=load('root_tool',source/'session-update.py')
    co=load('coordinator',source/'login-recovery-update.py')
    rt.atomic_write(root/'login-recovery-update.py',(source/'login-recovery-update.py').read_bytes(),0o600)
    seal={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in user.iterdir() if p.is_file()}
    rt.atomic_write(root/'user-seal.json',(json.dumps(seal,indent=2)+'\n').encode(),0o600)
    protected={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in co.PROTECTED}
    rt.atomic_write(root/'protected.json',(json.dumps(protected,indent=2)+'\n').encode(),0o600)
    subprocess.run(['/usr/bin/python3','-I','-B',str(root/'login-recovery-update.py'),'check',str(root),str(user)],check=True)
    sums={str(p.relative_to(bundle)):hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.rglob('*') if p.is_file()}
    rt.atomic_write(bundle/'SHA256.json',(json.dumps(sums,indent=2)+'\n').encode(),0o600)
    print('Bundle complet contrôlé, aucune installation :',bundle)


if __name__=='__main__':main()
