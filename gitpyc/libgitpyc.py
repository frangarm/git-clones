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
import warnings
warnings.filterwarnings(
    "ignore", 
    category=DeprecationWarning, 
    message=".*st_ctime.*"
)
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
        case "shortlog": cmd_shortlog(args)
        case "ls-tree": cmd_ls_tree(args)
        case "checkout": cmd_checkout(args)
        case "show-ref": cmd_show_ref(args)
        case "tag": cmd_tag(args)
        case "branch": cmd_branch(args)
        case "rev-parse": cmd_rev_parse(args)
        case "ls-files": cmd_ls_files(args)
        case "check-ignore": cmd_check_ignore(args)
        case "status": cmd_status(args)
        case "rm": cmd_rm(args)
        case "add": cmd_add(args)
        case "commit": cmd_commit(args)
        case "diff": cmd_diff(args)
        case "cherry-pick": cmd_cherry_pick(args)
        case "stash": cmd_stash(args)
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
    
    while True:
        if os.path.isdir(os.path.join(path, ".gitpyc")):
            return GitPyCRepository(path)
        parent = os.path.realpath(os.path.join(path, ".."))
        if parent == path:
            if required:
                raise Exception("No gitpyc directory.")
            return None
        path = parent

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
        case b'tree': c = GitPyCTree
        case b'tag': c = GitPyCTag
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
    obj = object_read(repo, object_find(repo, obj, fmt=fmt))
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
    log_graph(repo, object_find(repo, args.commit), set())
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

argsp = argsubparser.add_parser("shortlog", help="Summarise commit history by author.")
argsp.add_argument("commit", default="HEAD", nargs="?")
argsp.add_argument("-n", "--numbered", action="store_true", help="Sort by number of commits.")

def cmd_shortlog(args):
    repo = repo_find()
    authors = {}
    
    def walk(sha, seen):
        if sha in seen:
            return
        
        seen.add(sha)
        commit = object_read(repo, sha)
        
        if commit.fmt != b'commit':
            return
        
        author_raw = commit.kvlm.get(b'author', b'Unknown').decode("utf8")
        #Author line: "Name <email> timestamp timezone"
        m = re.match(r'^(.*?)\a+<', author_raw)
        author = m.group(1) if m else author_raw
        msg = commit.kvlm[None].decode("utf8").strip().splitlines()[0]
        authors.setdefault(author, []).append(msg)
        
        if b'parent' in commit.kvlm:
            parents = commit.kvlm[b'parent']
            
            if type(parents) != list:
                parents = [parents]
            
            for p in parents:
                walk(p.decode("ascii"), seen)
    
    walk(object_find(repo, args.commit), set())
    
    items = list(authors.items())
    
    if args.numbered:
        items.sort(key=lambda x : -len(x[1]))
    
    for author, messages in items:
        print(f"\n{len(messages):6}  {author}")
        
        for msg in messages:
            print(f"   {msg}")

class GitPyCTreeLeaf:
    def __init__(self, mode, path, sha):
        self.mode = mode
        self.path = path
        self.sha = sha

def tree_parse_one(raw, start=0):
    x = raw.find(b' ', start)
    assert x - start in (5, 6)
    mode = raw [start:x]
    
    if len(mode) == 5:
        mode = b"0" + mode
    
    y = raw.find(b'\x00', x)
    path = raw[x+1:y]
    raw_sha = int.from_bytes(raw[y+1:y+21], "big")
    sha = format(raw_sha, "040x")
    
    return y+21, GitPyCTreeLeaf(mode, path.decode("utf8"), sha)

def tree_parse(raw):
    pos, max_pos, ret = 0, len(raw), []
    
    while pos < max_pos:
        pos, data = tree_parse_one(raw, pos)
        ret.append(data)
    
    return ret

def tree_leaf_sort_key(leaf):
    return leaf.path + "/" if leaf.mode.startswith(b"4") else leaf.path

def tree_serialize(obj):
    obj.items.sort(key=tree_leaf_sort_key)
    ret = b''
    
    for i in obj.items:
        ret += i.mode + b' ' + i.path.encode("utf8") + b'\x00'
        ret += int(i.sha, 16).to_bytes(20, byteorder="big")
    
    return ret

class GitPyCTree(GitPyCObject):
    fmt = b'tree'
    
    def deserialize(self, data):
        self.items = tree_parse(data)
    
    def serialize(self):
        return tree_serialize(self)

    def init(self):
        self.items = []

argsp = argsubparser.add_parser("ls-tree", help = "Pretty-print a tree object.")
argsp.add_argument("-r", dest="recursive", action="store_true")
argsp.add_argument("tree")

def cmd_ls_tree(args):
    repo = repo_find()
    ls_tree(repo, args.tree, args.recursive)

def ls_tree(repo, ref, recursive=None, prefix=""):
    sha = object_find(repo, ref, fmt=b"tree")
    obj = object_read(repo, sha)
    
    for item in obj.items:
        type_bytes = item.mode[0:1] if len(item.mode) == 5 else item.mode[0:2]
        
        match type_bytes:
            case b'04': t = "tree"
            case b'10': t = "blob"
            case b'12': t = "blob"
            case b'16': t = "commit"
            case _: raise Exception(f"Strange tree lead mode {item.mode}.")
            
        full = os.path.join(prefix, item.path)
        
        if not (recursive and t == 'tree'):
            pad = '0' * (6-len(item.mode))
            print(f"{pad}{item.mode.decode()} {t} {item.sha}\t{full}")
        else:
            ls_tree(repo, item.sha, recursive, full)

argsp = argsubparser.add_parser("checkout", help = "Checkout a commit into a directory.")
argsp.add_argument("commit")
argsp.add_argument("path")

def cmd_checkout(args):
    repo = repo_find()
    obj = object_read(repo, object_find(repo, args.commit))
    
    if obj.fmt == b'commit':
        obj = object_read(repo, obj.kvlm[b'tree'].decode("ascii"))
        
    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception (f"Not a directory: {args.path}.")
        if os.listdir(args.path):
            raise Exception(f"Not empty: {args.path}.")
    else:
        os.makedirs(args.path)
    
    tree_checkout(repo, obj, os.path.realpath(args.path))

def tree_checkout(repo, tree, path):
    for item in tree.items:
        obj = object_read(repo, item.sha)
        dest = os.path.join(path, item.path)
        
        if obj.fmt == b'tree':
            os.mkdir(dest)
            tree_checkout(repo, obj, dest)
        elif obj.fmt == b'blob':
            with open(dest, 'wb') as f:
                f.write(obj.blobdata)

def ref_resolve(repo, ref):
    path = repo_file(repo, ref)
    
    if not os.path.isfile(path):
        return None
    
    with open(path, 'r') as fp:
        data = fp.read() [:-1]
        
    if data.startswith("ref: "):
        return ref_resolve(repo, data[5:])
    
    return data

def ref_list(repo, path=None):
    if not path:
        path = repo_dir(repo, "refs")
    
    ret = {}
    
    for f in sorted(os.listdir(path)):
        can = os.path.join(path, f)
        if os.path.isdir(can):
            ret[f] = ref_list(repo, can)
        else:
            ret[f] = ref_resolve(repo, can)

    return ret

def ref_create(repo, ref_name, sha):
    path = repo_file(repo, "refs/" + ref_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    with open(path, 'w') as fp:
        fp.write(sha + "\n")

argsp = argsubparser.add_parser("show-ref", help="List references.")

def cmd_show_ref(args):
    repo = repo_find()
    refs = ref_list(repo)
    show_ref(repo, refs, prefix="refs")

def show_ref(repo, refs, with_hash=True, prefix=""):
    if prefix:
        prefix = prefix + '/'
    
    for k, v in refs.items():
        if type(v) == str:
            if with_hash:
                print(f"{v} {prefix}{k}")
            else:
                print(f"{prefix}{k}")
        else:
            show_ref(repo, v, with_hash=with_hash, prefix=f"{prefix}{k}")

class GitPyCTag(GitPyCCommit):
    fmt = b'tag'

argsp = argsubparser.add_parser("tag", help="List and create tags")
argsp.add_argument("-a", action="store_true", dest="create_tag_object")
argsp.add_argument("-d", "--delete", dest="delete", action="store_true", help="Delete a tag")
argsp.add_argument("name", nargs="?")
argsp.add_argument("object", default="HEAD", nargs="?")

def cmd_tag(args):
    repo = repo_find()
    
    if args.name:
        if args.delete:
            tag_delete(repo, args.name)
        else:
            tag_create(repo, args.name, args.object, create_tag_object=args.create_tag_object)
    else:
        refs = ref_list(repo)
        if "tags" in refs:
            show_ref(repo, refs["tags"], with_hash=False)

def tag_create(repo, name, ref, create_tag_object=False):
    sha = object_find(repo, ref)
    
    if create_tag_object:
        tag = GitPyCTag()
        tag.kvlm = dict()
        tag.kvlm[b'object'] = sha.encode()
        tag.kvlm[b'type'] = b'commit'
        tag.kvlm[b'tag'] = name.encode()
        tag.kvlm[b'tagger'] = b'GitPyC <gitpyc@example.com>'
        tag.kvlm[None] = b"Tag created by GitPyC.\n"
        tag_sha = object_write(tag, repo)
        ref_create(repo, "tags/" + name, tag_sha)
    else:
        ref_create(repo, "tags/" + name, sha)

def tag_delete(repo, name):
    tag_path = repo_file(repo, "refs/tags/" + name)
    
    if not os.path.exists(tag_path):
        raise Exception(f"Tag '{name}' not found.")

    os.remove(tag_path)
    print(f"Deleted tag '{name}'")
    
argsp = argsubparser.add_parser("branch", help="List, create, or delete branches.")
argsp.add_argument("name", nargs="?", help="Branch name")
argsp.add_argument("start_point", nargs="?", default="HEAD", help="Starting commit (default: HEAD)")
argsp.add_argument("-d", "--delete", action="store_true", help="Delete the branch.")
argsp.add_argument("-m", "--move", dest="new_name", metavar="NEW_NAME", help="Rename the branch.")
argsp.add_argument("-a", "--all", action="store_true", help="List all branches including remotes")

def cmd_branch(args):
    repo = repo_find()
    
    if args.name:
        if args.delete:
            branch_delete(repo, args.name)
        elif args.new_name:
            branch_rename(repo, args.name, args.new_name)
        else:
            branch_create(repo, args.name, args.start_point)
    else:
        branch_list(repo, all_branches=args.all)

def branch_get_active(repo):
    with open(repo_file(repo, "HEAD"), "r") as f:
        head = f.read()
    
    if head.startswith("ref: refs/heads/"):
        return head[16:].strip()
    
    return False

def branch_create(repo, name, start_point="HEAD"):
    sha = object_find(repo, start_point)
    ref_path = repo_file(repo, "refs/heads/" + name)
    
    if os.path.exists(ref_path):
        raise Exception(f"Branch '{name}' already exists.")
    
    ref_create(repo, "heads/" + name, sha)
    print(f"Branch '{name}' created at {sha[:7]}")

def branch_delete(repo, name):
    active = branch_get_active(repo)
    
    if active == name:
        raise Exception(f"Cannot delete the currently checked-out branch '{name}'.")
    
    ref_path = repo_file(repo, "refs/heads/" + name)
    
    if not os.path.exists(ref_path):
        raise Exception(f"Branch '{name}' not found.")
    
    os.remove(ref_path)
    print(f"Deleted branch '{name}'.")

def branch_rename(repo, old_name, new_name):
    old_path = repo_file(repo, "refs/heads/" + old_name)
    new_path = repo_file(repo, "refs/heads/" + new_name)

    if not os.path.exists(old_path):
        raise Exception(f"Branch '{old_name}' not found.")
    
    if os.path.exists(new_path):
        raise Exception(f"Branch '{new_path}' already exists.")
    
    sha = ref_resolve(repo, "refs/heads/" + old_name)
    ref_create(repo, "heads/" + new_name, sha)
    os.remove(old_path)
    
    #Update HEAD if we renamed the active branch
    if branch_get_active(repo) == old_name:
        with open(repo_file(repo, "HEAD"), "w") as f:
            f.write(f"ref: refs/heads/{new_name}\n")
    
    print(f"Renamed branch '{old_name} to '{new_name}'.")

def branch_list(repo, all_branches=False):
    active = branch_get_active(repo)
    heads_dir = repo_dir(repo, "refs", "heads")
    
    if heads_dir:
        for name in sorted(os.listdir(heads_dir)):
            prefix = "* " if name == active else " "
            print(f"{prefix}{name}")
    
    if all_branches:
        remotes_dir = repo_dir(repo, "refs", "remotes")
        if remotes_dir:
            for remote in sorted(os.listdir(remotes_dir)):
                remote_dir = os.path.join(remotes_dir, remote)
                if os.path.isdir(remote_dir):
                    for branch in sorted(os.listdir(remote_dir)):
                        print(f"  remotes/{remote}/{branch}")
                        
def object_resolve(repo, name):
    candidates = []
    hashRE = re.compile(r"^[0-9A-Fa-f]{4,40}$")

    if not name.strip():
        return None
    if name == "HEAD":
        return [ref_resolve(repo, "HEAD")]
    if hashRE.match(name):
        name = name.lower()
        prefix = name[0:2]
        path = repo_dir(repo, "objects", prefix, mkdir=False)
        
        if path:
            rem = name[2:]
            
            for f in os.listdir(path):
                if f.startswith(rem):
                    candidates.append(prefix + f)
    
    as_tag = ref_resolve(repo, "refs/tags/" + name)
    
    if as_tag:
        candidates.append(as_tag)
    
    as_branch = ref_resolve(repo, "refs/heads/" + name)
    
    if as_branch:
        candidates.append(as_branch)
        
    as_remote = ref_resolve(repo, "refs/remotes/" + name)
    
    if as_remote:
        candidates.append(as_remote)
    
    return candidates

def object_find(repo, name, fmt=None, follow=True):
    sha = object_resolve(repo, name)
    if not sha:
        raise Exception(f"No such reference: {name}.")
    if len(sha) > 1:
        raise Exception(
            f"Ambiguous reference {name}: candidates are:\n - " +
            "\n - ".join(sha))
    sha = sha[0]
    if not fmt:
        return sha
    while True:
        obj = object_read(repo, sha)
        if obj.fmt == fmt:
            return sha
        if not follow:
            raise Exception(
                f"Object {sha} is a {obj.fmt.decode()!r}, not {fmt.decode()!r} "
                f"(follow=False — no tag/commit dereference attempted)")
        if obj.fmt == b'tag':
            sha = obj.kvlm[b'object'].decode("ascii")
        elif obj.fmt == b'commit' and fmt == b'tree':
            sha = obj.kvlm[b'tree'].decode("ascii")
        else:
            raise Exception(
                f"Cannot follow {obj.fmt.decode()!r} object {sha} "
                f"to type {fmt.decode()!r}")

argsp = argparser.add_parser("rev-parse", help="Parse revision identifiers")
argsp.add_argument("--gitpyc-type", metavar="type", dest="type", choices=["blob", "commit", "tag", "tree"], default=None)
argsp.add_argument("name")

def cmd_rev_parse(args):
    fmt = args.type.encode() if args.type else None
    repo = repo_find()
    print(object_find(repo, args.name, fmt, follow=True))

class GitPyCIndexEntry:
    def __init__(self, ctime=None, mtime=None, dev=None, ino=None, mode_type=None, mode_perms=None, 
                 uid=None, gid=None, fsize=None, sha=None, flag_assume_valid=None, flag_stage=None, 
                 name=None):
        self.ctime = ctime
        self.mtime = mtime
        self.dev = dev
        self.ino = ino
        self.mode_type = mode_type
        self.mode_perms = mode_perms
        self.uid = uid
        self.gid = gid
        self.fsize = fsize
        self.sha = sha
        self.flag_assume_valid = flag_assume_valid
        self.flag_stage = flag_stage
        self.name = name

class GitPyCIndex:
    def __init__(self, version=2, entries=None):
        self.version = version
        self.entries = entries if entries else []
        
def index_read(repo):
    index_file = repo_file(repo, "index")
    if not os.path.exists(index_file):
        return GitPyCIndex()
    with open(index_file, 'rb') as f:
        raw = f.read()

    header = raw[:12]

    if header[:4] != b"DIRC":
        raise Exception(f"Invalid index file: bad magic {header[:4]!r}")
    version = int.from_bytes(header[4:8], "big")
    if version != 2:
        raise Exception(f"Unsupported index version {version} (GitPyC supports v2 only)")
    count = int.from_bytes(header[8:12], "big")

    entries = []
    content = raw[12:]
    idx = 0
    for i in range(count):
        ctime_s  = int.from_bytes(content[idx:    idx+4],  "big")
        ctime_ns = int.from_bytes(content[idx+4:  idx+8],  "big")
        mtime_s  = int.from_bytes(content[idx+8:  idx+12], "big")
        mtime_ns = int.from_bytes(content[idx+12: idx+16], "big")
        dev      = int.from_bytes(content[idx+16: idx+20], "big")
        ino      = int.from_bytes(content[idx+20: idx+24], "big")
        unused   = int.from_bytes(content[idx+24: idx+26], "big")
        mode     = int.from_bytes(content[idx+26: idx+28], "big")
        mode_type = mode >> 12
        if mode_type not in (0b1000, 0b1010, 0b1110):
            raise Exception(f"Unknown mode type {mode_type:#05b} in entry {i}")
        mode_perms = mode & 0b0000000111111111
        uid    = int.from_bytes(content[idx+28: idx+32], "big")
        gid    = int.from_bytes(content[idx+32: idx+36], "big")
        fsize  = int.from_bytes(content[idx+36: idx+40], "big")
        sha    = format(int.from_bytes(content[idx+40: idx+60], "big"), "040x")
        flags  = int.from_bytes(content[idx+60: idx+62], "big")
        flag_assume_valid = (flags & 0b1000000000000000) != 0
        flag_extended     = (flags & 0b0100000000000000) != 0
        if flag_extended:
            raise Exception(f"Extended flag set in entry {i}; v3 index not supported")
        flag_stage  = flags & 0b0011000000000000
        name_length = flags & 0b0000111111111111
        idx += 62
        if name_length < 0xFFF:
            assert content[idx + name_length] == 0x00
            raw_name = content[idx:idx+name_length]
            idx += name_length + 1
        else:
            null_idx = content.find(b'\x00', idx + 0xFFF)
            raw_name = content[idx:null_idx]
            idx = null_idx + 1
        name = raw_name.decode("utf8")
        idx = 8 * ceil(idx / 8)
        entries.append(GitPyCIndexEntry(
            ctime=(ctime_s, ctime_ns), mtime=(mtime_s, mtime_ns),
            dev=dev, ino=ino, mode_type=mode_type, mode_perms=mode_perms,
            uid=uid, gid=gid, fsize=fsize, sha=sha,
            flag_assume_valid=flag_assume_valid, flag_stage=flag_stage,
            name=name))
    return GitPyCIndex(version=version, entries=entries)

def index_write(repo, index):
    with open(repo_file(repo, "index"), "wb") as f:
        f.write(b"DIRC")
        f.write(index.version.to_bytes(4, "big"))
        f.write(len(index.entries)).to_bytes(4, "big")
        idx = 0
        
        for e in index.entries:
            f.write(e.ctime[0].to_bytes(4, "big"))
            f.write(e.ctime[1].to_bytes(4, "big"))   
            f.write(e.mtime[0].to_bytes(4, "big"))   
            f.write(e.mtime[1].to_bytes(4, "big"))  
            f.write(e.dev.to_bytes(4, "big"))
            f.write(e.ino.to_bytes(4, "big"))  
            mode = (e.mode_type << 12) | e.mode_perms
            f.write(mode.to_bytes(4, "big"))
            f.write(e.uid.to_bytes(4, "big"))
            f.write(e.gid.to_bytes(4, "big"))
            f.write(e.fsize.to_bytes(4, "big"))
            f.write(int(e.sha, 16).to_bytes(20, "big"))
            flag_av = 0x1 << 15 if e.flag_assume_valid else 0
            name_bytes = e.name.encode("utf8")
            bytes_len = len(name_bytes)
            name_length = min(bytes_len, 0xFFF)
            f.write((flag_av | e.flag_stage | name_length).to_bytes(2, "big"))
            f.write(name_bytes)
            f.write((0).to_bytes(1, "big"))
            idx += 62 + len(name_bytes) + 1
            
            if idx % 8 !=0:
                pad = 8 - (idx % 8)
                f.write((0).to_bytes(pad, "big"))
                idx += pad
                
argsp = argsubparser.add_parser("ls-files", help="List all staged files")
argsp.add_argument("--verbose", action="store_true")

def cmd_ls_files(args):
    repo = repo_find()
    index = index_read(repo)
    
    if args.verbose:
        print(f"Index file format v{index.version}, {len(index.entries)} entries.")
    
    for e in index.entries:
        print(e.name)
        
        if args.verbose:
            entry_type = {0b1000:"regular file", 0b1010: "symlink", 0b1110: "gitpyc link"}[e.mode_type]
            print(f"  {entry_type} with perms: {e.mode_perms:o}")
            print(f"  on blob: {e.sha}")
            print(f"  created: {datetime.fromtimestamp(e.ctime[0])}.{e.ctime[1]}, "
                  f"modified: {datetime.fromtimestamp(e.mtime[0])}.{e.mtime[1]}")
            print(f"  device: {e.dev}, inode: {e.ino}")
            try:
                print(f"  user: {pwd.getpwuid(e.uid).pw_name} ({e.uid})  "
                      f"group: {grp.getgrgid(e.gid).gr_name} ({e.gid})")
            except (NameError, KeyError):
                print(f"  user: {e.uid}  group: {e.gid}")
            print(f"  flags: stage={e.flag_stage} assume_valid={e.flag_assume_valid}")

class GitPyCIgnore:
    def __init__(self, absolute, scoped):
        self.absolute = absolute
        self.scoped = scoped

def gitpycignore_parsel(raw):
    raw = raw.strip()
    
    if not raw or raw[0] == "#":
        return None
    elif raw[0] == "!":
        return (raw[1:], False)
    elif raw[0] == "\\":
        return (raw[1:], True)
    else:
        return (raw, True)

def gitpycignore_parse(lines):
    return [p for p in (gitpycignore_parsel(l) for l in lines) if p]

def gitpycignore_read(repo):
    ret = GitPyCIgnore(absolute=[], scoped={})
    exclude = os.path.join(repo.gitdir, "info/exclude")
    
    if os.path.exists(exclude):
        with open(exclude, "r") as f:
            ret.absolute.append(gitpycignore_parse(f.readlines()))
    
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    global_file = os.path.join(config_home, "gitpyc/ignore")
    
    if os.path.exists(global_file):
        with open(global_file, "r") as f:
            ret.absolute.append(gitpycignore_parse(f.readlines()))
    
    index = index_read(repo)
    
    for entry in index.entries:
        if entry.name == ".gitpycignore" or entry.name.endswith("/.gitpycignore"):
            dir_name = os.path.dirname(entry.name)
            contents = object_read(repo, entry.sha)
            lines = contents.blobdata.decode("utf8").splitlines()
            ret.scoped[dir_name] = gitpycignore_parse(lines)
    
    return ret

def check_ignore1(rules, path):
    result = None
    for pattern, value in rules:
        if fnmatch.fnmatch(path, pattern):
            result = value
    
    return result

def check_ignored_scoped(rules, path):
    parent = os.path.dirname(path)
    
    while True:
        if parent in rules:
            rel_path = os.path.relpath(path, parent) if parent else path
            result = check_ignore1(rules[parent], rel_path)
            if result is not None:
                return result
        if parent == "":
            break
        parent = os.path.dirname(parent)
    return None

def check_ignore_absolute(rules, path):
    for ruleset in rules:
        result = check_ignore1(ruleset, path)
        
        if result is not None:
            return result
    
    return False

def check_ignore(rules, path):
    if os.path.isabs(path):
        raise Exception("Path must be relative to repository root")
    
    result = check_ignored_scoped(rules.scoped, path)
    
    if result is not None:
        return result
    
    return check_ignore_absolute(rules.absolute, path)

argsp = argsubparser.add_parser("check-ignore", help="Check path(s) against ignore rules.")
argsp.add_argument("path", nargs="+")

def cmd_check_ignore(args):
    repo = repo_find()
    rules = gitpycignore_read(repo)
    
    for path in args.path:
        if check_ignore(rules, path):
            print(path)  
argsp = argsubparser.add_parser("status", help="Show the working tree.")

def cmd_status(_):
    repo = repo_find()
    index = index_read(repo)
    cmd_status_branch(repo)
    cmd_status_head_index(repo, index)
    print()
    cmd_status_index_worktree(repo, index)

def cmd_status_branch(repo):
    branch = branch_get_active(repo)
    
    if branch:
        print(f"On branch {branch}.")
    else:
        print(f"HEAD detached at {object_find(repo, 'HEAD')}")

def tree_to_dict(repo, ref, prefix=""):
    ret = {}
    tree_sha = object_find(repo, ref, fmt=b"tree")
    tree = object_read(repo, tree_sha)
    
    for leaf in tree.items:
        full_path = os.path.join(prefix, leaf.path)
        
        if leaf.mode.startswith(b'40000') or leaf.mode.startswith(b'040000'):
            ret.update(tree_to_dict(repo, leaf.sha, full_path))
        else:
            ret[full_path] = leaf.sha
    
    return ret

def cmd_status_head_index(repo, index):
    print("Changes to be committed:")
    try:
        head = tree_to_dict(repo, "HEAD")
    except Exception:
        head = {}
    
    for entry in index.entries:
        if entry.name in head:
            if head[entry.name] != entry.sha:
                print(" modified:", entry.name)
            del head[entry.name]
        else:
            print(" added:  ", entry.name)
    
    for entry in head.keys():
        print(" deleted: ", entry)

def cmd_status_index_worktree(repo, index):
    print("Changes not staged for commit:")
    ignore = gitpycignore_read(repo)
    gitdir_prefix = repo.gitdir + os.path.sep
    all_files = []
    
    for root, _, files in os.walk(repo.worktree, True):
        if root == repo.gitdir or root.startswith(gitdir_prefix):
            continue
        
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, repo.worktree)
            all_files.append(rel)
    
    for entry in index.entries:
        full_path = os.path.join(repo.worktree, entry.name)
        
        if not os.path.exists(full_path):
            print(" deleted: ", entry.name)
        else:
            stat = os.stat(full_path)
            ctime_ns = entry.ctime[0] * 10**9 + entry.ctime[1]
            mtime_ns = entry.mtime[0] * 10**9 + entry.mtime[1]
            
            if stat.st_ctime_ns != ctime_ns or stat.st_mtime_ns != mtime_ns:
                with open(full_path, "rb") as fd:
                    new_sha = object_hash(fd, b"blob", None)
                if entry.sha != new_sha:
                    print(" modified:", entry.name)
        if entry.name in all_files:
            all_files.remove(entry.name)
    print()
    print("Untracked files:")
    
    for f in all_files:
        if not check_ignore(ignore, f):
            print(" ", f)
            
argsp = argsubparser.add_parser("rm", help="Remove files from the working tree and index.")
argsp.add_argument("path", nargs="+")

def cmd_rm(args):
    repo = repo_find()
    rm(repo, args.path)

def rm(repo, paths, delete=True, skip_missing=False):
    index = index_read(repo)
    worktree = repo.worktree + os.sep
    abspaths = set()
    
    for path in paths:
        abspath = os.path.abspath(path)
        if abspath.startswith(worktree):
            abspaths.add(abspath)
        else:
            raise Exception(f"Cannot remove paths outside of worktree: {paths}")
    
    kept_entries, remove = [], []
    
    for e in index.entries:
        full_path = os.path.abspath(os.path.join(repo.worktree, e.name))
        
        if full_path in abspaths:
            remove.append(full_path)
            abspaths.discard(full_path)
        else:
            kept_entries.append(e)
    
    if abspaths and not skip_missing:
        raise Exception(f"Cannot remove paths not in the index: {abspaths}")
    
    if delete:
        for path in remove:
            os.unlink(path)
    
    index.entries = kept_entries
    index_write(repo, index)

argsp = argsubparser.add_parser("add", help="Add file contents to the index.")
argsp.add_argument("path", nargs="+")

def cmd_add(args):
    repo = repo_find()
    add(repo, args.path)

def add(repo, paths, delete=True, skip_missing=False):
    rm(repo, paths, delete=False, skip_missing=True)
    worktree = repo.worktree + os.sep
    clean_paths = set()
    
    for path in paths:
        abspath = os.path.abspath(path)
        if not (abspath.startswith(worktree) and os.path.isfile(abspath)):
            raise Exception(f"Not a file, or outside worktree: {paths}")
        relpath = os.path.relpath(abspath, repo.worktree)
        clean_paths.add((abspath, relpath))
    
    index = index_read(repo)
    
    for abspath, relpath in clean_paths:
        with open(abspath, "rb") as fd:
            sha = object_hash(fd, b"blob", repo)
        
        stat = os.stat(abspath)
        ctime_s  = int(stat.st_ctime)
        ctime_ns = stat.st_ctime_ns % 10**9
        mtime_s  = int(stat.st_mtime)
        mtime_ns = stat.st_mtime_ns % 10**9
        entry = GitPyCIndexEntry(
            ctime=(ctime_s, ctime_ns), mtime=(mtime_s, mtime_ns),
            dev=stat.st_dev, ino=stat.st_ino,
            mode_type=0b1000, mode_perms=0o644,
            uid=stat.st_uid, gid=stat.st_gid,
            fsize=stat.st_size, sha=sha,
            flag_assume_valid=False, flag_stage=False, name=relpath)
        index.entries.append(entry)

    index.entries.sort(key=lambda x: x.name)
    index_write(repo, index)

def tree_from_index(repo, index):
    contents = {"":[]}
    
    for entry in index.entries:
        dirname = os.path.dirname(entry.name)
        key = dirname
        
        while key != "":
            contents.setdefault(key, [])
            key = os.path.dirname(key)
        
        contents[dirname].append(entry)
    
    sha = None
    
    for path in sorted(contents.keys(), key=len, reverse=True):
        tree = GitPyCTree()
        
        for entry in contents[path]:
            if isinstance(entry, GitPyCIndexEntry):
                leaf_mode = f"{entry.mode_type:02o}{entry.mode_perms:04o}".encode("ascii")
                leaf = GitPyCTreeLeaf(mode=leaf_mode, path=os.path.basename(entry.name), sha=entry.sha)
            else:
                leaf = GitPyCTreeLeaf(mode=b"040000", path=entry[0], sha=entry[1])
            
            tree.items.append(leaf)
        
        sha = object_write(tree, repo)
        parent = os.path.dirname(path)
        base = os.path.basename(path)
        contents[parent].append((base, sha))
    
    return sha

def gitpycconfig_read():
    xdg = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    
    config_files = [
        os.path.expanduser(os.path.join(xdg, "gitpyc/config")),
        os.path.expanduser("~/.gitpycconfig")
    ]
    
    config = configparser.ConfigParser()
    config.read(config_files)
    
    return config

def gitpycconfig_user_get(config):
    if "user" in config:
        if "name" in config["user"] and "email" in config["user"]:
            return f"{config['user']['name']} <{config['user']['email']}>"
    
    return None

argsp = argsubparser.add_parser("commit", help="Record changes to the repository.")
argsp.add_argument("-m", metavar="message", dest="message", required=True)

def commit_create(repo, tree, parent, author, timestamp, message):
    commit = GitPyCCommit()
    commit.kvlm[b"tree"] = tree.encode("ascii")
    
    if parent:
        commit.kvlm[b"parent"] = parent.encode("ascii")
    
    message = message.strip() + "\n"
    offset = int(timestamp.astimezon().utcoffset().total_seconds())
    hours = offset // 3600
    minutes = (offset % 3600) // 60
    tz = "{}{:02}{:02}".format("+" if offset >= 0 else "-", abs(hours), abs(minutes))
    author_str = author + " " + str(int(timestamp.timestamp())) + " " + tz
    commit.kvlm[b"author"] = author_str.encode("utf8")
    commit.kvlm[b"committer"] = author_str.encode("utf8")
    commit.kvlm[None] = message.encode("utf8")
    
    return object_write(commit, repo)

def cmd_commit(args):
    repo = repo_find() 
    index = index_read(repo)
    tree = tree_from_index(repo, index)
    try:
        parent = object_find(repo, "HEAD")
    except Exception:
        parent = None
    
    author = gitpycconfig_user_get(gitpycconfig_read())
    
    if not author:
        raise Exception("No user identity configured. Set user.name and user.email.")
    
    commit = commit_create(repo, tree, parent, author, datetime.now(), args.message)
    active_branch = branch_get_active(repo) 
    
    if active_branch:
        with open(repo_file(repo, "refs/heads", active_branch), "w") as fd:
            fd.write(commit + "\n")
    else:
        with open(repo_file(repo, "HEAD"), "w") as fd:
            fd.write(commit + "\n")
    
    #reflog_append
    print(f"Successfully rebased and updated refs/heads/{active_branch}.")

argsp = argsubparser.add_parser("diff", help="Show changes between commits, commit and index, or index and worktree.")
argsp.add_argument("a", nargs="?", default=None, help="First commit/tree (omit to diff index vs worktree)")
argsp.add_argument("b", nargs="?", default=None, help="Second commit/tree (omit to diff index vs worktree)")
argsp.add_argument("--cached", "--staged", action="store_true", help="Compare index against HEAD (or given commit)")

def cmd_diff(args):
    repo = repo_find()
    
    if args.cached:
        #diff HEAD (or args.a) against index
        ref = args.a or "HEAD"
        try:
            a_tree = tree_to_dict(repo, ref)
        except Exception:
            a_tree = {}
        index = index_read(repo)
        b_tree = {e.name: e.sha for e in index.entries}
        diff_trees(repo, a_tree, b_tree, worktree=None)
        
    elif args.a and args.b:
        #diff two commits
        a_tree = tree_to_dict(repo, args.a)
        b_tree = tree_to_dict(repo, args.b)
        diff_trees(repo, a_tree, b_tree, worktree=None)
        
    elif args.a:
        #diff commit against worktree via index tracker
        try:
            a_tree = tree_to_dict(repo, args.a)
        except Exception:
            a_tree = {}
        
        index = index_read(repo)
        b_tree = {e.name: e.sha for e in index.entries}
        # Fixed: Pass repo.worktree so diff_trees reads the disk files instead of index data
        diff_trees(repo, a_tree, b_tree, worktree=repo.worktree)
        
    else:
        #diff index against worktree
        index = index_read(repo)
        
        for entry in index.entries:
            full_path = os.path.join(repo.worktree, entry.name)
            
            if not os.path.exists(full_path):
                print(f"--- a/{entry.name}")
                print(f"+++ /dev/null")
                blob = object_read(repo, entry.sha)
                old_lines = blob.blobdata.decode("utf8", errors="replace").splitlines(True)
                
                for line in difflib.unified_diff(old_lines, [], lineterm=""):
                    print(line)
            else:
                with open(full_path, "rb") as f:
                    new_data = f.read()
                blob = object_read(repo, entry.sha)
                old_lines = blob.blobdata.decode("utf8", errors="replace").splitlines(True)
                new_lines = new_data.decode("utf8", errors="replace").splitlines(True)
                diff = list(difflib.unified_diff(old_lines, new_lines,
                                                 fromfile=f"a/{entry.name}",
                                                 tofile=f"b/{entry.name}"))
                for line in diff:
                    print(line, end="")

def diff_trees(repo, a_tree, b_tree, worktree=None):
    all_paths = sorted(set(list(a_tree.keys()) + list(b_tree.keys())))
    
    for path in all_paths:
        a_sha = a_tree.get(path)
        b_sha = b_tree.get(path)
        
        if a_sha == b_sha and worktree is None:
            continue
        
        a_lines = []
        if a_sha:
            blob = object_read(repo, a_sha)
            a_lines = blob.blobdata.decode("utf8", errors="replace").splitlines(True)
        
        b_lines = []
        if worktree and b_sha:
            full = os.path.join(worktree, path)
            if os.path.exists(full):
                with open(full, "rb") as f:
                    b_lines = f.read().decode("utf8", errors="replace").splitlines(True)
            else:
                b_lines = []
        elif b_sha:
            blob = object_read(repo, b_sha)
            b_lines = blob.blobdata.decode("utf8", errors="replace").splitlines(True)
            
        if a_lines == b_lines:
            continue
            
        diff = list(difflib.unified_diff(a_lines, b_lines,
                                         fromfile=f"a/{path}",
                                         tofile=f"b/{path}"))
        for line in diff:
            print(line, end="")

argsp = argsubparser.add_parser("cherry-pick", help="Apply the changes introduced by an existing commit.")
argsp.add_argument("commit", help="Commit to cherry-pick")
argsp.add_argument("-n", "--no-commit", action="store_true", help="Do not commit automatically")

def cmd_cherry_pick(args):
    repo = repo_find()
    target_sha = object_find(repo, args.commit, fmt=b'commit')
    target = object_read(repo, target_sha)
    
    if b'parent' not in target.kvlm:
        raise Exception("Cannot cherry-pick the root commit.")
    
    parent_sha = target.kvlm[b'parent']
    if type(parent_sha) == list:
        parent_sha = parent_sha[0]
        
    parent_sha = parent_sha.decode("ascii")
    target_tree = tree_to_dict(repo, target_sha)
    parent_tree = tree_to_dict(repo, parent_sha)
    
    all_paths = set(list(target_tree.keys()) + list(parent_tree.keys()))
    actually_changed = set()  
    
    for path in all_paths:
        a = parent_tree.get(path)
        b = target_tree.get(path)
        
        if a == b:
            continue
            
        actually_changed.add(path)
        full_path = os.path.join(repo.worktree, path)
        os.makedirs(os.path.dirname(full_path) or repo.worktree, exist_ok=True)
        
        if b:
            blob = object_read(repo, b)
            with open(full_path, "wb") as f:
                f.write(blob.blobdata)
        elif os.path.exists(full_path):
            os.remove(full_path)
    
    new_files = [os.path.join(repo.worktree, p) for p in actually_changed if os.path.exists(os.path.join(repo.worktree, p))]
    if new_files:
        add(repo, new_files)
        
    removed = [os.path.join(repo.worktree, p) for p in actually_changed if not os.path.exists(os.path.join(repo.worktree, p))]
    if removed:
        rm(repo, removed, delete=False, skip_missing=True)

    if args.no_commit:
        print(f"Changes from {target_sha[:7]} staged. Commit manually.")
        return

    author = gitpycconfig_user_get(gitpycconfig_read())
    if not author:
        raise Exception("No user identity configured.")

    msg = target.kvlm[None].decode("utf8").strip()
    index = index_read(repo)
    tree  = tree_from_index(repo, index)
    try:
        parent = object_find(repo, "HEAD")
    except Exception:
        parent = None
        
    sha = commit_create(repo, tree, parent, author, datetime.now(), msg)
    active = branch_get_active(repo)
    
    if active:
        with open(repo_file(repo, "refs", "heads", active), "w") as f:
            f.write(sha + "\n")
            
    print(f"[{active or 'HEAD'} {sha[:7]}] {msg.splitlines()[0]}")

argsp = argsubparser.add_parser("stash", help="Stash the changes in a dirty working tree.")
stash_sub = argsp.add_subparsers(dest="stash_cmd")
stash_sub = argsp.add_subparsers("push", help="Save changes to stash (default)")
stash_sub = argsp.add_subparsers("pop", help="Apply and remove the latest stash")
stash_sub = argsp.add_subparsers("apply", help="Apply the latest stash (keep it)")
stash_sub = argsp.add_subparsers("list", help="List all stashes")
stash_sub = argsp.add_subparsers("drop", help="Discard the latest stash")
stash_sub = argsp.add_subparsers("clear", help="Remove all stashes")

def cmd_stash(args):
    repo = repo_find()
    cmd = getattr(args, 'stash_cmd', None) or "push"
    match cmd:
        case "push":  stash_push(repo)
        case "pop":   stash_pop(repo)
        case "apply": stash_apply(repo)
        case "list":  stash_list(repo)
        case "drop":  stash_drop(repo)
        case "clear": stash_clear(repo)
    
#Return list of stash Shas from .gitpyc/refs/stash (most recent first)
def _stash_list_shas(repo):
    stash_path = repo_file(repo, "refs/stash")
    
    if not stash_path or not os.path.exists(stash_path):
        return []
    
    with open(stash_path, "r") as f:
        sha = f.read().strip()
    
    #Walk the stash linked list (stash commits have their previous stash as parent)
    stashes = []
    current = sha
    
    while current:
        stashes.append(current)
        obj = object_read(repo, current)
        
        if obj.fmt == b'commit' and b'parent' in obj.kvlm:
            p = obj.kvlm[b'parent']
            
            if type(p) == list:
                p = p[0]
            
            current = p.decode("ascii")
        else:
            break
    
    return stashes

def stash_push(repo):
    author = gitpycconfig_user_get(gitpycconfig_read())
    
    if not author:
        raise Exception("No user identity configured.")
    
    #Save the current index as a tree
    index = index_read(repo)
    tree = tree_from_index(repo, index)
    
    try:
        head_sha = object_find(repo, "HEAD")
        msg = object_read(repo, head_sha).kvlm[None].decode("utf8").strip().splitlines()[0]
    except Exception:
        head_sha = None
        msg = "initial"
    
    stashes = _stash_list_shas(repo)
    prev_stash = stashes[0] if stashes else None
    
    #Build stash commit
    stash_commit = GitPyCCommit()
    stash_commit.kvlm[b"tree"] = tree.encode("ascii")
    
    if head_sha:
        stash_commit.kvlm[b"parent"] = head_sha.ecode("ascii") if not prev_stash else [head_sha.encode("ascii"), prev_stash.encode("ascii")]
    
    ts = datetime.now()
    off = int(ts.astimezone().utcoffset().total_seconds())
    h, m = off // 3600, (off % 3600) // 60
    tz = "{}{:02}{:02}".format("+" if off >= 0 else "-", abs(h), abs(m))
    a = f"{author} {int(ts.timestamp())} {tz}".encode("utf8")
    stash_commit.kvlm[b"author"]    = a
    stash_commit.kvlm[b"committer"] = a
    stash_commit.kvlm[None] = f"WIP on {branch_get_active(repo) or 'HEAD'}: {msg}\n".encode("utf8")
    sha = object_write(stash_commit, repo)

    #Write refs/stash
    with open(repo_path(repo, "refs/stash"), "w") as f:
        f.write(sha + "\n")

    #Reset index and worktree to HEAD
    if head_sha:
        cmd_reset_hard(repo, head_sha)
    print(f"Saved working directory and index state WIP on {branch_get_active(repo) or 'HEAD'}: {msg}")

def cmd_reset_hard(repo, sha):
    commit = object_read(repo, sha)
    tree_sha = commit.kvlm[b'tree'].decode("ascii")
    index = index_read(repo)
    
    for e in index.entries:
        fp = os.path.join(repo.worktree, e.name)
        if os.path.exists(fp):
            os.remove(fp)
    
    tree = object_read(repo, tree_sha)
    tree_checkout(repo, tree, repo.worktree)
    new_index = GitPyCIndex()
    #_tree_to_index(repo, tree_sha, new_index, "")
    index_write(repo, new_index)