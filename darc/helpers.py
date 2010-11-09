import argparse
from datetime import datetime
from fnmatch import fnmatchcase
import grp
import os
import pwd
import re
import stat


def encode_long(v):
    bytes = []
    while True:
        if v > 0x7f:
            bytes.append(0x80 | (v % 0x80))
            v >>= 7
        else:
            bytes.append(v)
            return ''.join(chr(x) for x in bytes)


def decode_long(bytes):
    v = 0
    base = 0
    for x in bytes:
        b = ord(x)
        if b & 0x80:
            v += (b & 0x7f) << base
            base += 7
        else:
            return v + (b << base)


def zero_pad(data, length):
    """Make sure data is `length` bytes long by prepending zero bytes

    >>> zero_pad('foo', 5)
    '\\x00\\x00foo'
    >>> zero_pad('foo', 3)
    'foo'
    """
    return '\0' * (length - len(data)) + data


def exclude_path(path, patterns):
    """Used by create and extract sub-commands to determine
    if an item should be processed or not
    """
    for pattern in (patterns or []):
        if pattern.match(path):
            return isinstance(pattern, ExcludePattern)
    return False


class IncludePattern(object):
    """--include PATTERN

    >>> py = IncludePattern('*.py')
    >>> foo = IncludePattern('/foo')
    >>> py.match('/foo/foo.py')
    True
    >>> py.match('/bar/foo.java')
    False
    >>> foo.match('/foo/foo.py')
    True
    >>> foo.match('/bar/foo.java')
    False
    >>> foo.match('/foobar/foo.py')
    False
    """
    def __init__(self, pattern):
        self.pattern = self.dirpattern = pattern
        if not pattern.endswith(os.path.sep):
            self.dirpattern += os.path.sep

    def match(self, path):
        dir, name = os.path.split(path)
        return (dir + os.path.sep).startswith(self.dirpattern) or fnmatchcase(name, self.pattern)

    def __repr__(self):
        return '%s(%s)' % (type(self), self.pattern)


class ExcludePattern(IncludePattern):
    """
    """


def walk_path(path, skip_inodes=None):
    st = os.lstat(path)
    if skip_inodes and (st.st_ino, st.st_dev) in skip_inodes:
        return
    yield path, st
    if stat.S_ISDIR(st.st_mode):
        for f in os.listdir(path):
            for x in walk_path(os.path.join(path, f), skip_inodes):
                yield x


def format_time(t):
    """Format datetime suitable for fixed length list output
    """
    if (datetime.now() - t).days < 365:
        return t.strftime('%b %d %H:%M')
    else:
        return t.strftime('%b %d  %Y')


def format_file_mode(mod):
    """Format file mode bits for list output
    """
    def x(v):
        return ''.join(v & m and s or '-'
                       for m, s in ((4, 'r'), (2, 'w'), (1, 'x')))
    return '%s%s%s' % (x(mod / 64), x(mod / 8), x(mod))

def format_file_size(v):
    """Format file size into a human friendly format
    """
    if v > 1024 * 1024 * 1024:
        return '%.2f GB' % (v / 1024. / 1024. / 1024.)
    elif v > 1024 * 1024:
        return '%.2f MB' % (v / 1024. / 1024.)
    elif v > 1024:
        return '%.2f kB' % (v / 1024.)
    else:
        return str(v)

class IntegrityError(Exception):
    """
    """

def memoize(function):
    cache = {}
    def decorated_function(*args):
        try:
            return cache[args]
        except KeyError:
            val = function(*args)
            cache[args] = val
            return val
    return decorated_function

@memoize
def uid2user(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return None

@memoize
def user2uid(user):
    try:
        return pwd.getpwnam(user).pw_uid
    except KeyError:
        return None

@memoize
def gid2group(gid):
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return None

@memoize
def group2gid(group):
    try:
        return grp.getgrnam(group).gr_gid
    except KeyError:
        return None


class Location(object):

    loc_re = re.compile(r'^((?:(?P<user>[^@]+)@)?(?P<host>[^:]+):)?'
                        r'(?P<path>[^:]*)(?:::(?P<archive>[^:]+))?$')

    def __init__(self, text):
        loc = self.loc_re.match(text)
        loc = loc and loc.groupdict()
        if not loc:
            raise ValueError
        self.user = loc['user']
        self.host = loc['host']
        self.path = loc['path']
        if not self.host and not self.path:
            raise ValueError
        self.archive = loc['archive']

    def __str__(self):
        text = ''
        if self.user:
            text += '%s@' % self.user
        if self.host:
            text += '%s::' % self.host
        if self.path:
            text += self.path
        if self.archive:
            text += ':%s' % self.archive
        return text

    def __repr__(self):
        return "Location('%s')" % self


def location_validator(archive=None):
    def validator(text):
        try:
            loc = Location(text)
        except ValueError:
            raise argparse.ArgumentTypeError('Invalid location format: "%s"' % text)
        if archive is True and not loc.archive:
            raise argparse.ArgumentTypeError('"%s": No archive specified' % text)
        elif archive is False and loc.archive:
            raise argparse.ArgumentTypeError('"%s" No archive can be specified' % text)
        return loc
    return validator


