#!/usr/bin/env python
import sys, os, glob, subprocess, time, sha
import options, git
from helpers import *

istty = os.isatty(1)
par2_ok = 0
nullf = open('/dev/null')

def debug(s):
    if opt.verbose:
        log(s)

def run(argv):
    # at least in python 2.5, using "stdout=2" or "stdout=sys.stderr" below
    # doesn't actually work, because subprocess closes fd #2 right before
    # execing for some reason.  So we work around it by duplicating the fd
    # first.
    fd = os.dup(2)  # copy stderr
    try:
        p = subprocess.Popen(argv, stdout=fd, close_fds=False)
        return p.wait()
    finally:
        os.close(fd)

def par2_setup():
    global par2_ok
    rv = 1
    try:
        p = subprocess.Popen(['par2', '--help'],
                             stdout=nullf, stderr=nullf, stdin=nullf)
        rv = p.wait()
    except OSError:
        log('fsck: warning: par2 not found; disabling recovery features.\n')
    else:
        par2_ok = 1

def parv(lvl):
    if opt.verbose >= lvl:
        if istty:
            return []
        else:
            return ['-q']
    else:
        return ['-qq']

def par2_generate(base):
    return run(['par2', 'create', '-n1', '-c200'] + parv(2)
               + ['--', base, base+'.pack', base+'.idx'])

def par2_verify(base):
    return run(['par2', 'verify'] + parv(3) + ['--', base])

def par2_repair(base):
    return run(['par2', 'repair'] + parv(2) + ['--', base])

def quick_verify(base):
    f = open(base + '.pack', 'rb')
    f.seek(-20, 2)
    wantsum = f.read(20)
    assert(len(wantsum) == 20)
    f.seek(0)
    sum = sha.sha()
    for b in chunkyreader(f, os.fstat(f.fileno()).st_size - 20):
        sum.update(b)
    if sum.digest() != wantsum:
        raise ValueError('expected %r, got %r' % (wantsum.encode('hex'),
                                                  sum.hexdigest()))
        

def git_verify(base):
    if opt.quick:
        try:
            quick_verify(base)
        except Exception, e:
            debug('error: %s\n' % e)
            return 1
        return 0
    else:
        return run(['git', 'verify-pack', '--', base])


optspec = """
bup fsck [options...] [filenames...]
--
r,repair    attempt to repair errors using par2 (dangerous!)
g,generate  generate auto-repair information using par2
v,verbose   increase verbosity (can be used more than once)
quick       just check pack sha1sum, don't use git verify-pack
par2-ok     immediately return 0 if par2 is ok, 1 if not
disable-par2  ignore par2 even if it is available
"""
o = options.Options('bup fsck', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

par2_setup()
if opt.par2_ok:
    if par2_ok:
        sys.exit(0)  # 'true' in sh
    else:
        sys.exit(1)
if opt.disable_par2:
    par2_ok = 0

git.check_repo_or_die()

if not extra:
    debug('fsck: No filenames given: checking all packs.\n')
    extra = glob.glob(git.repo('objects/pack/*.pack'))

code = 0
count = 0
for name in extra:
    if name.endswith('.pack'):
        base = name[:-5]
    elif name.endswith('.idx'):
        base = name[:-4]
    elif name.endswith('.par2'):
        base = name[:-5]
    elif os.path.exists(name + '.pack'):
        base = name
    else:
        raise Exception('%s is not a pack file!' % name)
    (dir,last) = os.path.split(base)
    par2_exists = os.path.exists(base + '.par2')
    if par2_exists and os.stat(base + '.par2').st_size == 0:
        par2_exists = 0
    sys.stdout.flush()
    debug('fsck: checking %s (%s)\n' 
          % (last, par2_ok and par2_exists and 'par2' or 'git'))
    if not opt.verbose and istty:
        log('fsck (%d/%d)\r' % (count, len(extra)))

    if par2_ok and par2_exists and (opt.repair or not opt.generate):
        vresult = par2_verify(base)
        if vresult != 0:
            if opt.repair:
                rresult = par2_repair(base)
                if rresult != 0:
                    print '%s par2 repair: failed (%d)' % (last, rresult)
                    code = code or rresult
                else:
                    print '%s par2 repair: succeeded (0)' % last
                    code = code or 100
            else:
                print '%s par2 verify: failed (%d)' % (last, vresult)
                code = code or vresult
        else:
            print '%s ok' % last
    elif not opt.generate or (par2_ok and not par2_exists):
        gresult = git_verify(base)
        if gresult != 0:
            print '%s git verify: failed (%d)' % (last, gresult)
            code = code or gresult
        else:
            if par2_ok and opt.generate:
                par2_generate(base)
            print '%s ok' % last
    else:
        assert(opt.generate and (not par2_ok or par2_exists))
        debug('    skipped: par2 file already generated.\n')
    count += 1

if not opt.verbose and istty:
    log('fsck done.           \n')
sys.exit(code)
