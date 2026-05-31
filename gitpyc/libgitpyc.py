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
        case "cat-file": cmd_cat_file(args)
        case "hash-object": cmd_hash_object(args)
        case "log": cmd_log(args)
        case _: print("Unkown Command")

class GitPyCRepository:
    #A GitPyC Repository
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

#Helper functions for GitPyC Repositories
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

#Finds a repo's root
def repo_find(path=".", required=True):
    path = os.path.realpath(path)
    
    if os.path.isdir(os.path.join(path, ".gitpyc")):
        return GitPyCRepository(path)

    parent = os.path.realpath(os.path.join(path, ".."))
    
    if parent == path:
        if required:
            raise Exception("No gitpyc directory.")
        return None
    
    return repo_find(parent, required)

#Creates repo
def repo_create(path):
    repo = GitPyCRepository(path, True)
        
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

#Command that creates a GitPyC repository
def cmd_init (args):
    repo_create(args.path)
    print(f"Initialized empty GitPyC repository in {os.path.realpath(args.path)}/.gitpyc")  
    
#Generic GitPyC Object class
class GitPyCObject:
    def __init__(self, data=None):
        if data is not None:
            self.deserialize(data)
        else:
            self.init()
    
    def serialize(self, repo=None):
        raise Exception("Unimplemented.")
    
    def deserialize(self, data):
        raise Exception("Unimplemented.")
    
    def init(self):
        pass

#GitPyC Object Helper Functions
def object_read(repo, sha):
    path = repo_file(repo, "objects", sha[0:2], sha[2:])
    
    if not os.path.isfile(path):
        return None
    
    with open(path, "rb") as f:
        raw = zlib.decompress(f.read())
        
    x = raw.find(b' ')
    fmt = raw[0:x]
    y = raw.find(b'\x00', x)
    size = int(raw[x:y].decode("ascii"))
    
    if size != len(raw) - y - 1:
        raise Exception(f"Malformed Object {sha}: bad length")

    match fmt:
        case b'commit': c = GitPyCCommit
        case b'tree': c = None
        case b'tag': c = None
        case b'blob': c = GitPyCBlob
        case _: raise Exception(f"Unknown type {fmt.decode('ascii')} for object {sha}")
    
    return c(raw[y+1:])

def object_write(obj, repo=None):
    data = obj.serialize()
    result = obj.fmt + b' ' + str(len(data)).encode() + b'\x00' + data
    sha = hashlib.sha1(result).hexdigest()
    
    if repo:
        path = repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)
        if not os.path.exists(path):
            with open(path, 'wb') as f:
                f.write(zlib.compress(result))
    
    return sha

class GitPyCBlob(GitPyCObject):
    fmt = b'blob'
    
    def serialize(self):
        return self.blobdata
    
    def deserialize(self, data):
        self.blobdata = data

argsp = argsubparser.add_parser("cat-file", help="Provide content of repository objects.")
argsp.add_argument("type", metavar="type", choices=["blob", "commit", "tag", "tree"])
argsp.add_argument("object", metavar="object")

def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())

def cat_file(repo, obj, fmt=None):
    obj = object_read(repo, #object_find(repo, obj, fmt=fmt))
    None)
    sys.stdout.buffer.write(obj.serialize())

argsp = argsubparser.add_parser("hash-object", help="Compute object ID and optionally store a blob from a file")
argsp.add_argument("-t", metavar="type", dest="type", choices=["blob", "commit", "tag", "tree"], default="blob")
argsp.add_argument("-w", dest="write", action="store_true")
argsp.add_argument("path")

def cmd_hash_object(args):
    repo = repo_find() if args.write else None
    
    with open(args.path, "rb") as fd:
        sha = object_hash(fd, args.type.encode(), repo)
        print(sha)

def object_hash(fd, fmt, repo=None):
    data = fd.read()
    
    match fmt:
        case b'commit': obj = GitPyCCommit(data)
        case b'tree': obj = None
        case b'tag': obj = None
        case b'blob': obj = GitPyCBlob(data)
        case _: raise Exception(f"Unknown type: {fmt}")
    
    return object_write(obj, repo)

def kvlm_parse(raw, start=0, dct=None):
    if not dct:
        dct = dict()
    
    spc = raw.find(b' ', start)
    nl = raw.find(b'\n', start)
    
    if (spc < 0) or (nl < spc):
        assert nl == start
        dct[None] = raw[start + 1:]
        return dct
    
    key = raw[start:spc]
    end = start
    
    while True:
        end = raw.find(b'\n', end+1)
        if raw[end+1] != ord(' '):
            break
    
    value = raw[spc+1:end].replace(b'\n ', b'\n')
    
    if key in dct:
        if type(dct[key]) == list: 
            dct[key].append(value)
        else:
            dct[key] = [dct[key], value]
    else:
        dct[key] = value
    
    return kvlm_parse(raw, start=end+1, dct=dct)

def kvlm_serialize(kvlm):
    ret = b''
    
    for k in kvlm.keys():
        if k is None:
            continue
        val = kvlm[k]
        if type(val) != list:
            val = [val]
        for v in val:
            ret += k + b' ' + v.replace(b'\n', b'\n ') + b'\n'
    ret += b'\n' + kvlm[None]
    
    return ret

class GitPyCCommit(GitPyCObject):
    fmt = b'commit'
    
    def deserialize(self, data):
        self.kvlm = kvlm_parse(data)
    
    def serialize(self):
        return kvlm_serialize(self.kvlm)
    
    def init(self):
        self.kvlm = dict()

argsp = argsubparser.add_parser("log", help="Display history of a given commit.")
argsp.add_argument("commit", default="Head", nargs="?")

def cmd_log(args):
    repo = repo_find()
    print("diagraph gitpyclog{")
    print(" node[shape=rect]")
    log_graph(repo, #object_find(repo, args.commit), set()
              None)
    print("}")
    
def log_graph(repo, sha, seen):
    if sha in seen:
        return
    
    seen.add(sha)
    commit = object_read(repo, sha)
    message = commit.kvlm[None].decode("utf8", "ignore").strip()
    message = message.replace("\\", "\\\\").replace('"', '\\"')
    
    if "\n" in message:
        message = message[:message.index("\n")]
    
    print(f'  c_{sha} [label="{sha[0:7]} : {message}"]')
    assert commit.fmt == b'commit'
    
    if b'parent' not in commit.kvlm:
        return
    
    parents = commit.kvlm[b'parent']
    
    if type(parents) != list:
        parents = [parents]
    
    for p in parents:
        p = p.decode("ascii")
        print(f" c_{sha} -> c_{p};")
        log_graph(repo, p, seen)