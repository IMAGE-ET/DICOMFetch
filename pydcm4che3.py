#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DICOM query fetch interface based on the dcm4che3 toolkit.

This is a plugin for the generic query interface that uses the more modern dcm4che3
command line DICOM tools. Both the `findscu` and `getscu` tools are required. These may
also be installed as standalone tools in the ext subdirectory of the package.
"""
from __future__ import print_function, division, absolute_import

import subprocess
import re
import os
import sys
import pkg_resources

from xml.etree import ElementTree
from tempfile import mkdtemp
import shutil
from glob import glob
from os.path import join, isfile, split, abspath, dirname
from operator import attrgetter
from structures import *


# Try and locate a working dcm4che3 program, raising ImportError if we can't
# Prepend rather than append to path as otherwise we bump into the dcmtk
# prog called findscu
def _which(program, path_prepend=None):
    '''Find program on the system path or any additional locations specified.
    '''
    if path_prepend is None:
        path_prepend = []

    def is_executable(fpath):
        if os.name == 'posix':
            return isfile(fpath) and os.access(fpath, os.X_OK)
        elif os.name == 'nt':
            return any(isfile('.'.join([fpath, ext])) for ext in ['exe', 'bat'])

    def executable_name(fpath):
        if os.name == 'posix':
            return fpath
        elif os.name == 'nt':
            paths = [
                '.'.join([fpath, ext])
                for ext in ['exe', 'bat']
                if isfile('.'.join([fpath, ext]))
            ]
            return paths[0] if paths else path

    fpath, fname = split(program)
    if fpath:
        if is_executable(program):
            return abspath(executable_name(program))
    else:
        for path in path_prepend + os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            executable_file = join(path, program)
            if is_executable(executable_file):
                return abspath(executable_name(executable_file))

    return None


def _call_quietly(cmdlist):
    '''Run a program suppressing stdout/stderr on posix and avoiding flashing dos boxes on mswindows
       Raises NotImplementedError if program fails with not zero exit code
    '''
    if os.name == 'posix':
        with open(os.devnull, 'w') as null:
            status = subprocess.call(
                cmdlist, shell=USESHELL, stdout=null, stderr=null)
            if status != 0:
                raise NotImplementedError(cmdlist[0])
    elif os.name == 'nt':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        status = subprocess.call(cmdlist, shell=USESHELL, startupinfo=si)
        if status != 0:
            raise NotImplementedError(cmdlist[0])
    else:
        raise NotImplementedError('Unsupported OS', os.name)


def _popen_with_pipe(cmdlist):
    '''Run a program with piped output and avoiding flashing dos boxes on mswindows
       Returns a subprocess.Popen instance representing the child process
    '''
    if os.name == 'posix':
        return subprocess.Popen(
            cmdlist,
            stdout=subprocess.PIPE,
            shell=USESHELL,
            universal_newlines=True
        )
    elif os.name == 'nt':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return subprocess.Popen(
            cmdlist,
            stdout=subprocess.PIPE,
            shell=USESHELL,
            universal_newlines=True,
            startupinfo=si
        )
    else:
        raise NotImplementedError('Unsupported OS', os.name)

#
# Try and find working dcm4che commands, raise NotImplemented if we can't
#
pkg_path = pkg_resources.resource_filename(__name__, 'ext')

if os.name == 'posix':
    FINDSCU = _which(
        'findscu',
        [pkg_path, '/usr/local/dcm4che3/bin',
            '/usr/local/dcm4che/bin', '/usr/local/bin']
    )
    if not FINDSCU:
        msg = "Can't find external dcm4che commmand 'findscu'"
        raise NotImplementedError(msg)
    GETSCU = _which(
        'getscu',
        [pkg_path, '/usr/local/dcm4che3/bin',
            '/usr/local/dcm4che/bin', '/usr/local/bin']
    )
    if not FINDSCU:
        msg = "Can't find external dcm4che commmand 'getscu'"
        raise NotImplementedError(msg)
    USEQUOTES = USESHELL = False
elif os.name == 'nt':
    FINDSCU = _which(
        'findscu',
        [pkg_path, join(r'c:/', 'dcm4che3', 'bin'),
         join('dcm4che', 'bin'), join('dcm4che3', 'bin'), 'bin']
    )
    if not FINDSCU:
        msg = "Can't find external dcm4che commmand 'findscu.bat/exe'"
        raise NotImplementedError(msg)
    GETSCU = _which(
        'getscu',
        [pkg_path, join(r'c:/', 'dcm4che3', 'bin'),
         join('dcm4che', 'bin'), join('dcm4che3', 'bin'), 'bin']
    )
    if not GETSCU:
        msg = "Can't find external dcm4che commmand 'getscu.bat/exe'"
        raise NotImplementedError(msg)
    if 'DCM4CHE_HOME' not in os.environ:
        os.environ['DCM4CHE_HOME'] = abspath(join(dirname(FINDSCU), '..'))
    USEQUOTES = USESHELL = sys.version_info[:2] < (3, 0)

    JAVA = _which('java')
    if not JAVA:
        JAVA = _which('java', [join('jre', 'bin'), join('jre7', 'bin')])
        if not JAVA:
            raise NotImplementedError('Java not available')
        else:
            os.environ['JAVA_HOME'] = abspath(join(dirname(JAVA), '..'))
            print('JAVA_HOME =', os.environ['JAVA_HOME'])
else:
    msg = "Don't know where external dcm4che3 commmands 'findscu/getscu' are on %s" % os.name
    raise NotImplementedError(msg)


# Check we can run the commands we've found
try:
    _call_quietly([FINDSCU, '-V'])
    _call_quietly([GETSCU, '-V'])
except OSError as e:
    raise NotImplementedError(str(e))


# Explicit omnibus list of contexts to put into association to allow c-store
# TODO: A better solution may be to generate this internally and so make
# it more configurable
CONTEXTS = join(pkg_path, 'store-tcs.properties')


class Parser(object):

    @staticmethod
    def tag_parser(xmlfile, tags):
        ''' Parse xml output file of the dcm4che3 tool findscu in a patient level query.
            Returns PatientLevelFields struct.
        '''
        root = ElementTree.parse(xmlfile).getroot()
        _tags = {}
        for e in root.findall('DicomAttribute'):
            tag = e.get('keyword')
            if tag == 'PatientName':
                val = e.find('PersonName').find(
                    'Alphabetic').find('FamilyName')
                _tags[tag] = val.text
            if tag in tags:
                val = e.find('Value')
                if val is not None:
                    _tags[tag] = val.text
        return _tags


def combo_cmd(cmd):
    level_map = {
        'patient': [['-M', 'PatientRoot'], ['-L', 'PATIENT']],
        'study': [['-M', 'StudyRoot'], ['-L', 'STUDY']],
        'series': [['-M', 'PatientRoot'], ['-L', 'SERIES']],
        'image': [['-M', 'PatientRoot'], ['-L', 'IMAGE']],
    }

    level_required_keys_map = {
        'patient': ['PatientName', 'PatientID',
                    'PatientBirthDate', 'PatientSex'],
        'study': ['PatientID', 'StudyID', 'StudyInstanceUID', 'StudyDate', 'StudyDescription'],
        'series': ['PatientID', 'StudyInstanceUID', 'Modality', 'SeriesNumber', 'SeriesInstanceUID', 'SeriesDescription', 'BodyPartExamined'],
        'image': ['PatientID', 'StudyInstanceUID', 'SeriesInstanceUID', 'InstanceNumber', 'SOPInstanceUID'],
    }

    for level_arg in level_map[level]:
        cmd += level_arg

    level_required_keys = level_required_keys_map[level]
    for k, v in query_map.items():
        if v == '':
            cmd += ['-r', '{key}'.format(key=k)]
            continue
        if USEQUOTES:
            k = '"%s"' % k
        cmd += ['-m', '{key}={value}'.format(key=k, value=v)]
        if k in level_required_keys:
            level_required_keys.remove(k)

    for k in level_required_keys:
        cmd += ['-r', '{key}'.format(key=k)]
    return cmd


def finder(aet, node, port, laet, level,  parser, ording_key=None, **query_map):
    ''' Use dcm4che3 tool findscu to perform a patient level query.
        The result is a list of PatientLevelFields records.
    '''
    tmpdir = mkdtemp(prefix='dcmfetch')
    find_cmd = [FINDSCU]
    find_cmd += ['--bind', laet]
    find_cmd += ['--connect', '%s@%s:%s' % (aet, node, port)]
    find_cmd = combo_cmd(find_cmd)
    find_cmd += ['-X', '-I']
    find_cmd += ['--out-dir', tmpdir]
    find_cmd += ['--out-file', 'match']
    print(' '.join(find_cmd))
    subproc = _popen_with_pipe(find_cmd)
    output = subproc.communicate()[0]
    if subproc.returncode != 0:
        raise QIError("Query to %s failed: %s, Command line was %s" %
                      (aet, output, find_cmd))

    responses = [
        parser(f, query_map.keys()) for f in glob(join(tmpdir, '*'))
    ]
    shutil.rmtree(tmpdir)
    if ording_key:
        responses = sorted(responses, key=attrgetter(ording_key))
        return responses
    return responses


def geter(aet, node, port, laet, level, savedir, **query_map):
    get_cmd = [GETSCU]
    get_cmd += ['--bind', laet]
    get_cmd += ['--connect', '%s@%s:%s' % (aet, node, port)]
    get_cmd = combo_cmd(get_cmd)
    get_cmd += ['--directory', savedir]
    if isfile(CONTEXTS):
        get_cmd += ['--store-tcs', CONTEXTS]

    subproc = _popen_with_pipe(get_cmd)

    # get lines of output from command
    linecount = 0
    responsecount = 0
    for line in subproc.stdout:
        linecount += 1
        response = _parse_cget_response(line)
        if response is not None:
            responsecount += 1
            yield response
        else:
            response = _parse_cstore_response(line)
            if response is not None:
                responsecount += 1
                yield response

    # wait for termination
    subproc.communicate()
    if subproc.returncode != 0:
        raise QIError("C-get from %s failed (%d), Command line was %s" %
                      (aet, subproc.returncode, get_cmd))


# unfortunately we don't seem to get the C-GET-RSP until the end
# example: 23:00:36,960 INFO  - FINDSCU->CRICStore(1) >>
# 1:C-GET-RSP[pcid=1, completed=3, failed=0, warning=0, status=0H
def _parse_cget_response(line):
    ''' Parse a line of query output that may contain a c-get info field.
        Returns None if no match to this.
    '''
    r = r"\d\d:\d\d:\d\d,[\d]{1,3}\s+INFO\s+.*[\d]+:C-GET-RSP\[pcid=([\d]+),\s+completed=([\d]+),\s+failed=([\d]+),\s+warning=([\d]+),\s+status=([\dA-Fa-f]{1,4})H.*"
    m = re.match(r, line)
    if m:
        pcid = int(m.group(1))
        completed = int(m.group(2))
        failed = int(m.group(3))
        warning = int(m.group(4))
        status = int(m.group(4), 16)
        remaining = 0
        return CGetResponse(pcid, remaining, completed, failed, warning, status)
    else:
        return None


# example: 23:00:36,845 INFO  - FINDSCU->CRICStore(1) <<
# 4:C-STORE-RSP[pcid=87, status=0H
def _parse_cstore_response(line):
    ''' Parse a line of query output that may contain a c-get info field.
        Returns None if no match to this.
    '''
    r = r"\d\d:\d\d:\d\d,[\d]{1,3}\s+INFO\s+-\s+.*[\d]+:C-STORE-RSP\[pcid=([\d]+),\s+status=([\dA-Fa-f]{1,4})H"
    m = re.match(r, line)
    if m:
        pcid = int(m.group(1))
        status = int(m.group(2), 16)
        return CStoreResponse(pcid, status)
    else:
        return None


if __name__ == '__main__':
    print("Module qidcm4che3.py - see tests/ dir for unit tests")
