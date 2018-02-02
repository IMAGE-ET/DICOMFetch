# -*- coding: utf-8 -*-
"""
DICOM node table support.

Provides look up of DICOM server details read fromn a dcmnoeds.cf configuration file.
"""

from __future__ import print_function, division, absolute_import

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

from collections import namedtuple

from os.path import join, expanduser, exists
import os
import re
import pkg_resources


AetEntry = namedtuple('AetEntry', 'aet, host, port, facilities, db, proxy, auth')


class AetTable(OrderedDict):
    '''A table of DICOM nodes accessible as a dictionary'''

    DFLT_NODES_FILE = 'dcmnodes.cf'
    if os.name == 'nt':
        DFLT_NODES_PATHS = [
            '.',
            os.environ.get('LOCALAPPDATA', join(expanduser('~'), 'AppData', 'Local')),
            os.environ.get('APPDATA', join(expanduser('~'), 'AppData', 'Roaming')),
            os.environ.get('ALLUSERSPROFILE', join('c:/', 'ProgramData')),
            os.environ.get('PROGRAMFILES', join('c:/', 'Program Files')),
            join('c:/', 'dcm4che3', 'etc'), join('c:/', 'dcm4che2', 'etc'),
            pkg_resources.resource_filename(__name__, 'ext')
        ]
    else:
        DFLT_NODES_PATHS = [
            '.', expanduser(join('~', '.config', 'dcmfetch')),
            join('/', 'etc'), join('/', 'usr', 'local', 'etc'),
            pkg_resources.resource_filename(__name__, 'ext')
        ]

    def __init__(self, aetfile=None):
        super(AetTable, self).__init__()
        if aetfile is None:
            aetfiles = [
                join(path, self.DFLT_NODES_FILE)
                for path in self.DFLT_NODES_PATHS
            ]
            aetfiles = list(filter(exists, aetfiles))
            if not aetfiles:
                raise IOError('Cannot find a dicom nodes file')
            aetfile = aetfiles[0]
        self.parse_file(aetfile)
        self.aetfile = aetfile

    def parse_file(self, aetfile):
        with open(aetfile) as f:
            for line in f:
                if line.lstrip().startswith('#'):
                    continue
                fields = line.split()
                if len(fields) < 5:
                    continue

                # NB for qi-rs/wado-rs the 'aet' field will be used for the
                # root rest endpoint so we'll allow '/' even though this is not
                # a valid aet character.
                name, aet, host, port, facilities = fields[0:5]
                if ( not re.match(r'[a-zA-Z0-9._-]+$', name) or
                     not re.match(r'[a-zA-Z0-9._/-]+$', aet) or
                     not re.match(r'[a-zA-Z]+[a-zA-Z0-9.-]*$|[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$', host) or
                     not re.match(r'[FSMGXIQCGABLW]+$', facilities, re.I)):
                    continue

                try:
                    port = int(port)
                except ValueError:
                    continue

                # The final optional field is overloaded depending on whether
                # we use direct local db access, another server as a proxy or
                # the qi-rs/wado ws web protocol. Auth is expected to be
                # a string of the form 'user:passwd'
                db = proxy = auth = None
                if len(fields) > 5:
                    if 'Q' in facilities.upper():
                        db = fields[5]
                        if not re.match(r'[a-zA-Z0-9_-]+$', db):
                            continue
                    elif 'C' in facilities.upper():
                        proxy = fields[5]
                        if not re.match(r'[a-zA-Z0-9._-]+$', proxy):
                            continue
                    elif 'W' in facilities.upper():
                        auth = fields[5]
                        if not re.match(r'[a-zA-Z0-9._-]+:[^ ]+$', auth):
                            continue
                self[name] = AetEntry(aet, host, port, facilities, db, proxy, auth)

        for k, v in self.items():
            if v.proxy and v.proxy not in self:
                print('Warning: Inconsistent proxy entry "%s" for "%s" in Aet File' % (v.proxy, k))


if __name__ == '__main__':
    '''Load and display defaults table.
    '''
    aettable = AetTable()

    print("Dicom Node Table ('%s')" % aettable.aetfile)
    print("=====================================")
    for k, v in aettable.items():
        print("%s: %s" % (k, v))
