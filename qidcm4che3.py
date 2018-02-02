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

from . structures import *


# Try and locate a working dcm4che3 program, raising ImportError if we can't
# Prepend rather than append to path as otherwise we bump into the dcmtk prog called findscu
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
            status = subprocess.call(cmdlist, shell=USESHELL, stdout=null, stderr=null)
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
        [pkg_path, '/usr/local/dcm4che3/bin', '/usr/local/dcm4che/bin', '/usr/local/bin']
    )
    if not FINDSCU:
        msg = "Can't find external dcm4che commmand 'findscu'"
        raise NotImplementedError(msg)
    GETSCU = _which(
        'getscu',
        [pkg_path, '/usr/local/dcm4che3/bin', '/usr/local/dcm4che/bin', '/usr/local/bin']
    )
    if not FINDSCU:
        msg = "Can't find external dcm4che commmand 'getscu'"
        raise NotImplementedError(msg)
    USEQUOTES = USESHELL = False
elif os.name == 'nt':
    FINDSCU = _which(
        'findscu',
        [pkg_path, join(r'c:/', 'dcm4che3', 'bin'), join('dcm4che', 'bin'), join('dcm4che3', 'bin'), 'bin']
    )
    if not FINDSCU:
        msg = "Can't find external dcm4che commmand 'findscu.bat/exe'"
        raise NotImplementedError(msg)
    GETSCU = _which(
        'getscu',
        [pkg_path, join(r'c:/', 'dcm4che3', 'bin'), join('dcm4che', 'bin'), join('dcm4che3', 'bin'), 'bin']
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
# TODO: A better solution may be to generate this internally and so make it more configurable
CONTEXTS = join(pkg_path, 'store-tcs.properties')


def dcm_pat_level_find(aet, node, port, laet, patname, patid, birthdate, sex):
    ''' Use dcm4che3 tool findscu to perform a patient level query.
        The result is a list of PatientLevelFields records.
    '''
    tmpdir = mkdtemp(prefix='dcmfetch')
    if USEQUOTES:
        # Fix up broken behaviour on windows, dicom wild cards were getting
        # glob expanded even though we have not set shell = True
        # But then seems to be differently broken on win7/python3
        # so don't use quotes (or shell=True) in that case
        patname = '"%s"' % patname
        patid = '"%s"' % patid
        birthdate = '"%s"' % birthdate
        sex = '"%s"' % sex

    find_cmd = [FINDSCU]
    find_cmd += ['--bind', laet]
    find_cmd += ['--connect', '%s@%s:%s' % (aet, node, port)]
    find_cmd += ['-M', 'PatientRoot']
    find_cmd += ['-L', 'PATIENT']
    find_cmd += ['-X', '-I']
    find_cmd += ['--out-dir', tmpdir]
    find_cmd += ['--out-file', 'match']

    if patname:
        find_cmd += ['-m', 'PatientName=%s' % patname]
    else:
        find_cmd += ['-r', 'PatientName']
    if patid:
        find_cmd += ['-m', 'PatientID=%s' % patid]
    else:
        find_cmd += ['-r', 'PatientID']
    if birthdate:
        find_cmd += ['-m', 'PatientBirthDate=%s' % birthdate]
    else:
        find_cmd += ['-r', 'PatientBirthDate']
    if sex:
        find_cmd += ['-m', 'PatientSex=%s' % sex]
    else:
        find_cmd += ['-r', 'PatientSex']

    subproc = _popen_with_pipe(find_cmd)
    output = subproc.communicate()[0]
    if subproc.returncode != 0:
        raise QIError("Query to %s failed: %s, Command line was %s" % (aet, output, find_cmd))

    responses = [
        _parse_dcm4che_pat_level_find(f) for f in glob(join(tmpdir, '*'))
    ]
    shutil.rmtree(tmpdir)
    return sorted(responses, key=lambda x: x.patid)


def _parse_dcm4che_pat_level_find(xmlfile):
    ''' Parse xml output file of the dcm4che3 tool findscu in a patient level query.
        Returns PatientLevelFields struct.
    '''
    patname, patid, patdob, patsex = '', '', '', ''
    root = ElementTree.parse(xmlfile).getroot()
    for e in root.findall('DicomAttribute'):
        tag = e.get('keyword')
        if tag == 'PatientName':
            pn = e.find('PersonName')
            if pn is not None:
                a = pn.find('Alphabetic')
                if a is not None:
                    fn = a.find('FamilyName')
                    if fn is not None:
                        patname = fn.text
        elif tag == 'PatientID':
            val = e.find('Value')
            if val is not None:
                patid = val.text
        elif tag == 'PatientBirthDate':
            val = e.find('Value')
            if val is not None:
                patdob = val.text
        elif tag == 'PatientSex':
            val = e.find('Value')
            if val is not None:
                patsex = val.text

    return PatientLevelFields(patname, patid, patdob, patsex, 0)


def dcm_stu_level_find(aet, node, port, laet, patid):
    ''' Use dcm4che3 tool findscu to perform a study level query.
        The result is a list of StudyLevelFields records.
    '''
    tmpdir = mkdtemp(prefix='dcmfetch')

    find_cmd = [FINDSCU]
    find_cmd += ['--bind', laet]
    find_cmd += ['--connect', '%s@%s:%s' % (aet, node, port)]
    find_cmd += ['-M', 'PatientRoot']
    find_cmd += ['-L', 'STUDY']
    find_cmd += ['-m', 'PatientID=%s' % patid]
    find_cmd += ['-r', 'StudyID']
    find_cmd += ['-r', 'StudyInstanceUID']
    find_cmd += ['-r', 'StudyDate']
    find_cmd += ['-r', 'StudyDescription']
    find_cmd += ['-X', '-I']
    find_cmd += ['--out-dir', tmpdir]
    find_cmd += ['--out-file', 'match']

    subproc = _popen_with_pipe(find_cmd)
    output = subproc.communicate()[0]

    if subproc.returncode != 0:
        raise QIError("Query to %s failed: %s, Command line was %s" % (aet, output, find_cmd))

    responses = [
        _parse_dcm4che_stu_level_find(f) for f in glob(join(tmpdir, '*'))
    ]
    shutil.rmtree(tmpdir)
    return sorted(responses, key=lambda x: x.studyid)


def _parse_dcm4che_stu_level_find(xmlfile):
    ''' Parse xml file with results of study level find.
        Return StudyLevelFields struct.
    '''
    studyid, studyuid, studydate, description = '', '', '', ''
    root = ElementTree.parse(xmlfile).getroot()
    for e in root.findall('DicomAttribute'):
        tag = e.get('keyword')
        if tag == 'StudyID':
            val = e.find('Value')
            if val is not None:
                studyid = val.text
        elif tag == 'StudyInstanceUID':
            val = e.find('Value')
            if val is not None:
                studyuid = val.text
        elif tag == 'StudyDate':
            val = e.find('Value')
            if val is not None:
                studydate = val.text
        elif tag == 'StudyDescription':
            val = e.find('Value')
            if val is not None:
                description = val.text

    return StudyLevelFields(studyid, studyuid, studydate, description, 0)


def dcm_ser_level_find(aet, node, port, laet, patid, studyuid):
    ''' Use dcm4che3 tool findscu to perform a series level query.
        The result is a list of SeriesLevelFields records.
    '''
    tmpdir = mkdtemp(prefix='dcmfetch')

    find_cmd = [FINDSCU]
    find_cmd += ['--bind', laet]
    find_cmd += ['--connect', '%s@%s:%s' % (aet, node, port)]
    find_cmd += ['-M', 'PatientRoot']
    find_cmd += ['-L', 'SERIES']
    find_cmd += ['-m', 'PatientID=%s' % patid]
    find_cmd += ['-m', 'StudyInstanceUID=%s' % studyuid]
    find_cmd += ['-r', 'Modality']
    find_cmd += ['-r', 'SeriesNumber']
    find_cmd += ['-r', 'SeriesInstanceUID']
    find_cmd += ['-r', 'SeriesDescription']
    find_cmd += ['-r', 'BodyPartExamined']
    find_cmd += ['-X', '-I']
    find_cmd += ['--out-dir', tmpdir]
    find_cmd += ['--out-file', 'match']

    subproc = _popen_with_pipe(find_cmd)
    output = subproc.communicate()[0]
    if subproc.returncode != 0:
        raise QIError("Query to %s failed: %s, Command line was %s" % (aet, output, find_cmd))

    responses = [
        _parse_dcm4che_ser_level_find(f) for f in glob(join(tmpdir, '*'))
    ]
    shutil.rmtree(tmpdir)
    return sorted(responses, key=lambda x: x.seriesnumber)


def _parse_dcm4che_ser_level_find(xmlfile):
    ''' Parse xml file with results of series level find.
        Return SeriesLevelFields struct.
    '''
    modality, seriesnumber, seriesuid, description, bodypart = '', 0, '', '', ''
    root = ElementTree.parse(xmlfile).getroot()
    for e in root.findall('DicomAttribute'):
        tag = e.get('keyword')
        if tag == 'Modality':
            val = e.find('Value')
            if val is not None:
                modality = val.text
        elif tag == 'SeriesNumber':
            val = e.find('Value')
            if val is not None:
                seriesnumber = int(val.text)
        elif tag == 'SeriesInstanceUID':
            val = e.find('Value')
            if val is not None:
                seriesuid = val.text
        elif tag == 'SeriesDescription':
            val = e.find('Value')
            if val is not None:
                description = val.text
        elif tag == 'BodyPartExamined':
            val = e.find('Value')
            if val is not None:
                bodypart = val.text

    return SeriesLevelFields(modality, seriesnumber, seriesuid, description, bodypart, 0)


def dcm_img_level_find(aet, node, port, laet, patid, studyuid, seriesuid):
    ''' Use dcm4che3 tool findscu to perform an image level query.
        The result is a list of ImageLevelFields records.
    '''
    tmpdir = mkdtemp(prefix='dcmfetch')

    find_cmd = [FINDSCU]
    find_cmd += ['--bind', laet]
    find_cmd += ['--connect', '%s@%s:%s' % (aet, node, port)]
    find_cmd += ['-M', 'PatientRoot']
    find_cmd += ['-L', 'IMAGE']
    find_cmd += ['-m', 'PatientID=%s' % patid]
    find_cmd += ['-m', 'StudyInstanceUID=%s' % studyuid]
    find_cmd += ['-m', 'SeriesInstanceUID=%s' % seriesuid]
    find_cmd += ['-r', 'InstanceNumber']
    find_cmd += ['-r', 'SOPInstanceUID']
    find_cmd += ['-X', '-I']
    find_cmd += ['--out-dir', tmpdir]
    find_cmd += ['--out-file', 'match']

    subproc = _popen_with_pipe(find_cmd)
    output = subproc.communicate()[0]
    if subproc.returncode != 0:
        raise QIError("Query to %s failed: %s, Command line was %s" % (aet, output, find_cmd))

    responses = [
        _parse_dcm4che_img_level_find(f) for f in glob(join(tmpdir, '*'))
    ]
    shutil.rmtree(tmpdir)
    return sorted(responses, key=lambda x: x.imagenumber)


def _parse_dcm4che_img_level_find(xmlfile):
    ''' Return ImageLevelFields struct.
    '''
    imageuid, imagenumber = '', 0
    root = ElementTree.parse(xmlfile).getroot()
    for e in root.findall('DicomAttribute'):
        tag = e.get('keyword')
        if tag == 'SOPInstanceUID':
            val = e.find('Value')
            if val is not None:
                imageuid = val.text
        elif tag == 'InstanceNumber':
            val = e.find('Value')
            if val is not None:
                imagenumber = int(val.text)

    return ImageLevelFields(imageuid, imagenumber)


def dcm_ser_level_get(aet, node, port, laet, patid, studyuid, seriesuid, savedir):
    ''' Use dcm4che3 tool getscu to perform a series level c-get fetch. This is a coroutine.
        Each c-store response yields a CStoreResponse record.
    '''
    get_cmd = [GETSCU]
    get_cmd += ['--bind', laet]
    get_cmd += ['--connect', '%s@%s:%s' % (aet, node, port)]
    get_cmd += ['-M', 'PatientRoot']
    get_cmd += ['-L', 'SERIES']
    get_cmd += ['-m', 'PatientID=%s' % patid]
    get_cmd += ['-m', 'StudyInstanceUID=%s' % studyuid]
    get_cmd += ['-m', 'SeriesInstanceUID=%s' % seriesuid]
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
            # print(type(response))
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
        raise QIError("C-get from %s failed (%d), Command line was %s" % (aet, subproc.returncode, get_cmd))


def dcm_img_level_get(aet, node, port, laet, patid, studyuid, seriesuid, imageuid, savedir):
    ''' Use dcm4che3 tool getscu to perform an image level c-get fetch. This is a coroutine.
        Each c-store response yields a CStoreResponse record.
    '''
    get_cmd = [GETSCU]
    get_cmd += ['--bind', laet]
    get_cmd += ['--connect', '%s@%s:%s' % (aet, node, port)]
    get_cmd += ['-M', 'PatientRoot']
    get_cmd += ['-L', 'IMAGE']
    get_cmd += ['-m', 'PatientID=%s' % patid]
    get_cmd += ['-m', 'StudyInstanceUID=%s' % studyuid]
    get_cmd += ['-m', 'SeriesInstanceUID=%s' % seriesuid]
    get_cmd += ['-m', 'SOPInstanceUID=%s' % imageuid]
    get_cmd += ['--directory', savedir]
    if isfile(CONTEXTS):
        get_cmd += ['--store-tcs', CONTEXTS]

    subproc = _popen_with_pipe(get_cmd)

    # get lines of output from command
    linecount = 0
    responsecount = 0
    for line in subproc.stdout:
        linecount += 1
        # print("Parsing: %s" % line.strip())
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
        raise QIError("C-get from %s failed (%d), Command line was %s" % (aet, subproc.returncode, get_cmd))
    # print("subprocess termination: images in %s" % savedir)


# unfortunately we don't seem to get the C-GET-RSP until the end
# example: 23:00:36,960 INFO  - FINDSCU->CRICStore(1) >> 1:C-GET-RSP[pcid=1, completed=3, failed=0, warning=0, status=0H
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


# example: 23:00:36,845 INFO  - FINDSCU->CRICStore(1) << 4:C-STORE-RSP[pcid=87, status=0H
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
