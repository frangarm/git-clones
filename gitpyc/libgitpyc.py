import argparse
import configparser
import difflib
import fnmatch
import hashlib
import math
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import zlib
from datetime import datetime, timezone, timedelta
from math import ceil
try:
    import grp, pwd
except ModuleNotFoundError:
    pass  #Not available on Windows

argparser = argparse.ArgumentParser(description="GitPyC - A Python Git Implementation")
argsubparser = argparser.add_subparsers(title="Commands", dest="command")
argsubparser.required = True

def main (argv=sys.argv[1:]):
    args = argparser.parse_args(argv)
    
    match args.command:
        case "init": cmd_init(args)
        case _: print("Unkown Command")

class GitRepository:
    #A Git Repository
    worktree = None
    gitdir = None
    conf = None
    
    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".gitpyc")
        
        if not (force or os.path.isdir(self.gitdir)):
            raise Exception(f"Not a GitPyC Repository: {path}")
        
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")
        
        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration file missing")
        
        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception(f"Unsupported repositoryformatvesion: {vers}")

def repo_path(repo, *path):
    return os.path.join(repo.gitdir, *path)
    
def repo_file(repo, *path, mkdir=False):
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)
    
def repo_dir(repo, *path, mkdir=False):
    path = repo_path(repo, *path)
    if os.path.exists(path):
        if os.path.isdir(path):
            return path
        else:
            raise Exception(f"Not a directory: {path}")
    if mkdir:
        os.makedirs(path)
        return path
        
    return None
    
def repo_create(path):
    repo = GitRepository(path, True)
        
    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"{path} is not a directory.")
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception(f"{path} is not empty!")
    else:
        os.makedirs(repo.worktree)
            
    assert repo_dir(repo, "branches", mkdir=True)
    assert repo_dir(repo, "objects", mkdir=True)
    assert repo_dir(repo, "refs", "tags", mkdir=True)
    assert repo_dir(repo, "refs", "heads", mkdir=True)
    assert repo_dir(repo, "logs", mkdir=True)
    assert repo_dir(repo, "logs", "refs", "heads", mkdir=True)
    
    with open(repo_file(repo, "description"), "w") as f:
        f.write("Unnamed repository. Edit this file 'description' to name the repository.\n")
    
    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/main\n")
    
    with open(repo_file(repo, "config"), "w") as f:
        repo_default_config().write(f)
    
    return repo

def repo_default_config():
    ret = configparser.ConfigParser()
    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")
    
    return ret

argsp = argsubparser.add_parser("init", help="Initialize a new, empty repository")
argsp.add_argument("path", metavar="directory", nargs="?", default=".", help="Where to create the repository.")

def cmd_init (args):
    repo_create(args.path)
    print(f"Initialized empty GitPyC repository in {os.path.realpath(args.path)}/.gitpyc")     