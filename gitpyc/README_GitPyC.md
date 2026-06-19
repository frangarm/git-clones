## GitPyC

A Python implementation of Git. GitPyC replicates core Git behaviour — from plumbing primitives through to branching, merging, remotes, and maintenance commands — using only the Python standard library.

### Requirements

- Python 3.10 or later (uses structural pattern matching)
- Unix-like OS recommended; Windows is partially supported (the `grp`/`pwd` modules are skipped automatically)

### Setup

Place both files in a directory on your `PATH`, or run directly from the project root.

```bash
chmod +x gitpyc
# Optionally symlink into your PATH:
ln -s "$(pwd)/gitpyc" ~/.local/bin/gitpyc
```

GitPyC reads your identity from the standard Git config files (`~/.gitconfig` or `$XDG_CONFIG_HOME/git/config`). Set these before committing:

```bash
gitpyc config --global user.name "Your Name"
gitpyc config --global user.email "you@example.com"
```

---

### Commands

#### Repository Initialisation

```bash
gitpyc init [directory]
```

Creates a new empty repository in the current directory, or in `directory` if specified. The default branch is `main`.

---

#### Staging & the Index

```bash
# Stage files
gitpyc add file.txt src/

# Unstage and remove files from the worktree
gitpyc rm file.txt

# List staged files
gitpyc ls-files
gitpyc ls-files --verbose      # includes mode, blob SHA, timestamps, uid/gid
```

---

#### Committing

```bash
gitpyc commit -m "your commit message"
```

Requires `user.name` and `user.email` to be configured (see Setup above).

---

#### Inspecting Status & Differences

```bash
# Show branch, staged changes, and unstaged changes
gitpyc status

# Diff index against worktree (unstaged changes)
gitpyc diff

# Diff HEAD (or a commit) against the index (staged changes)
gitpyc diff --cached
gitpyc diff --cached <commit>

# Diff two commits against each other
gitpyc diff <commit-a> <commit-b>

# Diff a commit against the worktree
gitpyc diff <commit>
```

---

#### History & Logging

```bash
# Outputs a Graphviz DOT digraph — pipe into dot to render
gitpyc log
gitpyc log <commit>
dot -Tpng <(gitpyc log) -o history.png

# Summarise commits grouped by author
gitpyc shortlog
gitpyc shortlog -n            # sort by commit count
gitpyc shortlog <commit>

# Annotate each line of a file with the commit that last changed it
gitpyc blame <file>
gitpyc blame <file> <commit>
```

> **Note:** `gitpyc log` outputs Graphviz DOT format, not human-readable text. Pipe it through `dot` (part of Graphviz) to produce an image, or use any DOT viewer.

---

#### Searching

```bash
# Search tracked files in the worktree
gitpyc grep "pattern"
gitpyc grep -i "pattern"           # case-insensitive
gitpyc grep -n "pattern"           # show line numbers
gitpyc grep --cached "pattern"     # search the index instead
gitpyc grep "pattern" <commit>     # search a specific commit's tree

# Check whether paths would be ignored
gitpyc check-ignore path/to/file
```

---

#### Branches

```bash
# List local branches (* marks the active branch)
gitpyc branch

# List local and remote-tracking branches
gitpyc branch -a

# Create a branch
gitpyc branch <name>
gitpyc branch <name> <start-point>

# Delete a branch
gitpyc branch -d <name>

# Rename a branch
gitpyc branch <old-name> -m <new-name>
```

---

#### Tags

```bash
# List tags
gitpyc tag

# Create a lightweight tag
gitpyc tag <name>
gitpyc tag <name> <object>

# Create an annotated tag object
gitpyc tag -a <name>
gitpyc tag -a <name> <object>

# Delete a tag
gitpyc tag -d <name>
```

---

#### Undoing Changes

```bash
# Reset HEAD (and optionally the index and worktree)
gitpyc reset <commit>           # mixed (default): moves HEAD, resets index
gitpyc reset --soft <commit>    # moves HEAD only
gitpyc reset --hard <commit>    # moves HEAD, resets index and worktree

# Revert a commit by creating a new inverse commit
gitpyc revert <commit>
gitpyc revert -n <commit>       # stage changes without committing

# Apply changes from an existing commit onto the current branch
gitpyc cherry-pick <commit>
gitpyc cherry-pick -n <commit>  # stage only, do not commit
```

---

#### Merging & Rebasing

```bash
# Merge a branch into HEAD
gitpyc merge <branch>
gitpyc merge --no-ff <branch>   # force a merge commit even when fast-forward is possible

# Rebase the current branch onto another
gitpyc rebase <upstream>
gitpyc rebase <upstream> --onto <target>
```

When a merge produces conflicts, GitPyC writes standard conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) into the affected files. Resolve them manually, then `add` and `commit`.

---

#### Stashing

```bash
gitpyc stash            # save current changes (same as stash push)
gitpyc stash push
gitpyc stash pop        # apply latest stash and drop it
gitpyc stash apply      # apply latest stash (keep it)
gitpyc stash list       # show all stash entries
gitpyc stash drop       # discard the latest stash
gitpyc stash clear      # remove all stashes
```

---

#### Checkout

Checks out a commit's tree into a directory. The target directory must either not exist or be empty.

```bash
gitpyc checkout <commit> <path>
```

---

#### Plumbing Commands

```bash
# Display the contents of an object
gitpyc cat-file <type> <object>      # type: blob | commit | tag | tree

# Hash a file and optionally write it to the object store
gitpyc hash-object <file>
gitpyc hash-object -t blob -w <file>

# List the contents of a tree object
gitpyc ls-tree <tree>
gitpyc ls-tree -r <tree>             # recurse into subtrees

# Resolve a revision name to a SHA
gitpyc rev-parse <name>
gitpyc rev-parse --gitpyc-type commit HEAD

# List all references
gitpyc show-ref

# Describe a commit using the nearest reachable tag
gitpyc describe
gitpyc describe <commit>
gitpyc describe --tags              # include lightweight tags
```

---

#### Remotes

> **Important:** GitPyC's network commands (`clone`, `fetch`, `pull`, `push`) only support **local filesystem paths**. Remote URLs (SSH, HTTPS) are not implemented.

```bash
# Manage remotes
gitpyc remote show
gitpyc remote add <name> <path>
gitpyc remote remove <name>
gitpyc remote rename <old-name> <new-name>

# Clone a local repository
gitpyc clone <source-path> [destination]

# Fetch updates from a remote
gitpyc fetch [remote]              # default remote: origin

# Pull (fetch + merge)
gitpyc pull [remote] [branch]

# Push to a remote
gitpyc push [remote] [refspec]     # e.g. HEAD:refs/heads/main
```

---

#### Reflog

```bash
gitpyc reflog              # show HEAD reflog
gitpyc reflog <ref>        # show reflog for a specific ref
gitpyc reflog --all        # show all reflogs
```

Reflog entries are written automatically by `commit`, `reset`, and `rebase`.

---

#### Configuration

```bash
# Read a value
gitpyc config user.name

# Set a value (repo-local)
gitpyc config user.name "Alice"

# Set a value globally
gitpyc config --global user.email "alice@example.com"

# List all config entries
gitpyc config --list

# Remove an entry
gitpyc config --unset user.name
gitpyc config --global --unset user.email
```

---

#### Maintenance

```bash
# Find and optionally remove unreachable objects
gitpyc gc
gitpyc gc --prune

# Verify object integrity
gitpyc fsck                # check objects reachable from refs
gitpyc fsck --full         # check all objects in the database

# Remove untracked files
gitpyc clean -n            # dry run — show what would be removed
gitpyc clean -f            # actually remove untracked files
gitpyc clean -f -d         # also remove untracked directories

# Binary search for a regression
gitpyc bisect start
gitpyc bisect bad          # mark current commit as bad
gitpyc bisect good         # mark current commit as good
gitpyc bisect log          # show bisect session log
gitpyc bisect reset        # end bisect and restore original state
```

---

### Differences from Standard Git

| Behaviour | Standard Git | GitPyC |
|---|---|---|
| `log` output | Human-readable text | Graphviz DOT digraph |
| Network remotes | SSH, HTTPS, Git protocol | Local filesystem paths only |
| Index version | v2, v3 | v2 only |
| `checkout` | Switches branches | Exports a commit's tree to a directory |
| Windows support | Full | Partial (`grp`/`pwd` unavailable) |
| Config file | `.git/config`, `~/.gitconfig` | Same (read via `configparser`) |
