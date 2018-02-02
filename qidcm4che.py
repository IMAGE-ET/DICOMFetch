#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DICOM query fetch interface based on the dcm4che2 toolkit.

This is a plugin for the generic query interface that uses the traditional dcm4che2
command line DICOM tools. Only the `dcmqr` tool is required as this provides a client (SCU)
for both C-FIND and C-GET.
"""
from __future__ import print_function, division, absolute_import

import subprocess
import re
import os
from os.path import join, isfile, abspath, split, dirname

from . structures import *


# Try and locate a working dcm4che2 program, raising ImportError if we can't
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
if os.name == 'posix':
    DCMQR = _which('dcmqr', ['/usr/local/dcm4che2/bin', '/usr/local/dcm4che/bin', '/usr/local/bin'])
    if not DCMQR:
        msg = "Can't find external dcm4che commmand 'dcmqr'"
        raise NotImplementedError(msg)
    USESHELL = False
elif os.name == 'nt':
    DCMQR = _which(
        'dcmqr.bat',
        [join(r'c:/', 'dcm4che2', 'bin'), join('dcm4che', 'bin'), join('dcm4che2', 'bin'), 'bin']
    )
    if not DCMQR:
        msg = "Can't find external dcm4che commmand 'dcmqr.bat'"
        raise NotImplementedError(msg)
    if 'DCM4CHE_HOME' not in os.environ:
        os.environ['DCM4CHE_HOME'] = abspath(join(dirname(DCMQR), '..'))
    USESHELL = True

    JAVA = _which('java.exe')
    if not JAVA:
        JAVA = _which('java.exe', [join('jre', 'bin'), join('jre7', 'bin')])
        if not JAVA:
            raise NotImplementedError('Java not available')
        else:
            os.environ['JAVA_HOME'] = abspath(join(dirname(JAVA), '..'))
            print('JAVA_HOME =', os.environ['JAVA_HOME'])
else:
    msg = "Don't know where external dcm4che commmand 'dcmqr' is on %s" % os.name
    raise NotImplementedError(msg)


# Check we can run the command we've found
try:
    _call_quietly([DCMQR, '-V'])
except OSError as e:
    raise NotImplementedError(str(e))


def dcm_pat_level_find(aet, node, port, laet, patname, patid, birthdate, sex):
    ''' Use dcm4che tool dcmqr to perform a patient level query. The result is a list
        of PatientLevelFields records.
    '''
    global DCMQR
    if os.name == 'nt':
        # Fix up broken behaviour on windows, dicom wild cards were getting
        # glob expanded even though we have not set shell = True
        patname = '"%s"' % patname
        patid = '"%s"' % patid
        birthdate = '"%s"' % birthdate
        sex = '"%s"' % sex

    find_cmd = [DCMQR]
    find_cmd += ['-device', laet]
    find_cmd += ['%s@%s:%s' % (aet, node, port)]
    find_cmd += ['-P']
    if patname:
        find_cmd += ['-q', 'PatientName=%s' % patname]
    else:
        find_cmd += ['-r', 'PatientsName']
    if patid:
        find_cmd += ['-q', 'PatientID=%s' % patid]
    else:
        find_cmd += ['-r', 'PatientID']
    if birthdate:
        find_cmd += ['-q', 'PatientBirthDate=%s' % birthdate]
    else:
        find_cmd += ['-r', 'PatientBirthDate']
    if sex:
        find_cmd += ['-q', 'PatientSex=%s' % sex]
    else:
        find_cmd += ['-r', 'PatientSex']

    subproc = _popen_with_pipe(find_cmd)
    output = subproc.communicate()[0]
    if subproc.returncode != 0:
        raise QIError("Query to %s failed: %s, Command line was %s" % (aet, output, find_cmd))
    return _parse_dcm4che_pat_level_find(output.split('\n'))


def _parse_dcm4che_pat_level_find(lines):
    ''' Parse the output of the dcm4che tool 'dcmqr' in a patient level query.
        Return list of PatientLevelFields structs, one for each reponse to query.
        If none found then returns empty list.
    '''

    class Response:
        def __init__(self):
            self.patname = ''
            self.patid = ''
            self.dob = ''
            self.sex = ''
            self.nstudies = 0

    responses = []
    response = None
    for line in lines:
        if _parse_response_start(line):
            if response is not None:
                responses.append(
                    PatientLevelFields(
                        response.patname, response.patid,
                        response.dob, response.sex, response.nstudies
                    )
                )
            response = Response()
        else:
            result = _parse_tag_value(line)
            if result and response is not None:
                gggg, eeee, vr, taglen, value = result
                if taglen > 0:
                    if gggg == 0x0010 and eeee == 0x0010:
                        response.patname = value
                    elif gggg == 0x0010 and eeee == 0x0020:
                        response.patid = value
                    elif gggg == 0x0010 and eeee == 0x0030:
                        response.dob = value
                    elif gggg == 0x0010 and eeee == 0x0040:
                        response.sex = value
                    elif gggg == 0x0020 and eeee == 0x1200:
                        try:
                            response.nstudies = int(value)
                        except ValueError:
                            response.nstudies = -1

    if response is not None and response.patname:
        responses.append(
            PatientLevelFields(
                response.patname, response.patid,
                response.dob, response.sex, response.nstudies
            )
        )
    return responses


def dcm_stu_level_find(aet, node, port, laet, patid):
    ''' Use dcm4che tool dcmqr to perform a study level query. The result is a list
        of StudyLevelFields records.
    '''
    global DCMQR
    find_cmd = [DCMQR]
    find_cmd += ['-device', laet]
    find_cmd += ['%s@%s:%s' % (aet, node, port)]
    find_cmd += ['-q', 'PatientID=%s' % patid]
    find_cmd += ['-r', 'StudyDescription']

    subproc = _popen_with_pipe(find_cmd)
    output = subproc.communicate()[0]

    if subproc.returncode != 0:
        raise QIError("Query to %s failed: %s, Command line was %s" % (aet, output, find_cmd))
    return _parse_dcm4che_stu_level_find(output.split('\n'))


def _parse_dcm4che_stu_level_find(lines):
    ''' Parse the output of the dcm4che tool 'dcmqr' in a study level query.
        Return list of StudyLevelFields structs, one for each reponse to query.
        If none found then returns empty list.
    '''
    class Response:
        def __init__(self):
            self.studyid = ''
            self.studyuid = ''
            self.studydate = ''
            self.description = ''
            self.nseries = 0

    responses = []
    response = None
    for line in lines:
        if _parse_response_start(line):
            if response is not None:
                responses.append(
                    StudyLevelFields(
                        response.studyid, response.studyuid,
                        response.studydate, response.description,
                        response.nseries
                    )
                )
            response = Response()
        else:
            result = _parse_tag_value(line)
            if result and response is not None:
                gggg, eeee, vr, taglen, value = result
                if gggg == 0x0008 and eeee == 0x0020:
                    response.studydate = value
                elif gggg == 0x0008 and eeee == 0x1030:
                    response.description = value
                elif gggg == 0x0020 and eeee == 0x000D:
                    response.studyuid = value
                elif gggg == 0x0020 and eeee == 0x0010:
                    response.studyid = value
                elif gggg == 0x0020 and eeee == 0x1206:
                    try:
                        response.nseries = int(value)
                    except ValueError:
                        response.nseries = -1

    if response is not None and response.studyuid:
        responses.append(
            StudyLevelFields(
                response.studyid, response.studyuid,
                response.studydate, response.description,
                response.nseries
            )
        )
    return responses


def dcm_ser_level_find(aet, node, port, laet, patid, studyuid, staudydate):
    ''' Use dcm4che tool dcmqr to perform a series level query.
        The result is a list of SeriesLevelFields records.
    '''
    global DCMQR
    find_cmd = [DCMQR]
    find_cmd += ['-device', laet]
    find_cmd += ['%s@%s:%s' % (aet, node, port)]
    find_cmd += ['-S']
    find_cmd += ['-q', 'PatientID=%s' % patid]
    find_cmd += ['-q', 'StudyInstanceUID=%s' % studyuid]
    find_cmd += ['-r', 'SeriesDescription']
    find_cmd += ['-r', 'BodyPartExamined']
    find_cmd += ['-m', 'StudyDate=%s' % staudydate]

    subproc = _popen_with_pipe(find_cmd)
    output = subproc.communicate()[0]
    if subproc.returncode != 0:
        raise QIError("Query to %s failed: %s, Command line was %s" % (aet, output, find_cmd))

    return _parse_dcm4che_ser_level_find(output.split('\n'))


def _parse_dcm4che_ser_level_find(lines):
    ''' Return list of SeriesLevelFields structs, one for each reponse to query
        if none found then returns empty list
    '''
    class Response:
        def __init__(self):
            self.modality = ''
            self.seriesnumber = ''
            self.seriesuid = ''
            self.description = ''
            self.bodypart = ''
            self.nimages = 0

    responses = []
    response = None
    for line in lines:
        if _parse_response_start(line):
            if response is not None:
                responses.append(
                    SeriesLevelFields(
                        response.modality, response.seriesnumber,
                        response.seriesuid, response.description,
                        response.bodypart, response.nimages
                    )
                )
            response = Response()
        else:
            result = _parse_tag_value(line)
            if result and response is not None:
                gggg, eeee, vr, taglen, value = result
                if gggg == 0x0008 and eeee == 0x0060:
                    response.modality = value
                elif gggg == 0x0008 and eeee == 0x103E:
                    response.description = value
                elif gggg == 0x0018 and eeee == 0x0015:
                    response.bodypart = value
                elif gggg == 0x0020 and eeee == 0x000E:
                    response.seriesuid = value
                elif gggg == 0x0020 and eeee == 0x0011:
                    try:
                        response.seriesnumber = int(value)
                    except ValueError:
                        response.seriesnumber = -1
                elif gggg == 0x0020 and eeee == 0x1209:
                    try:
                        response.nimages = int(value)
                    except ValueError:
                        response.nimages = -1

    if response is not None and response.seriesuid:
        responses.append(
            SeriesLevelFields(
                response.modality, response.seriesnumber,
                response.seriesuid, response.description,
                response.bodypart, response.nimages
            )
        )
    return responses


def dcm_img_level_find(aet, node, port, laet, patid, studyuid, seriesuid):
    ''' Use dcm4che tool dcmqr to perform an image level query.
        The result is a list of ImageLevelFields records.
    '''
    global DCMQR
    find_cmd = [DCMQR]
    find_cmd += ['-device', laet]
    find_cmd += ['%s@%s:%s' % (aet, node, port)]
    find_cmd += ['-I']
    find_cmd += ['-q', 'PatientID=%s' % patid]
    find_cmd += ['-q', 'StudyInstanceUID=%s' % studyuid]
    find_cmd += ['-q', 'SeriesInstanceUID=%s' % seriesuid]

    subproc = _popen_with_pipe(find_cmd)
    output = subproc.communicate()[0]
    if subproc.returncode != 0:
        raise QIError("Query to %s failed: %s, Command line was %s" % (aet, output, find_cmd))

    return _parse_dcm4che_img_level_find(output.split('\n'))


def _parse_dcm4che_img_level_find(lines):
    ''' Return list of ImageLevelFields structs, one for each reponse to query
        if none found then returns empty list
    '''
    class Response:
        def __init__(self):
            self.imageuid = ''
            self.imagenumber = 0

    responses = []
    response = None
    for line in lines:
        if _parse_response_start(line):
            if response is not None:
                responses.append(ImageLevelFields(response.imageuid, response.imagenumber))
            response = Response()
        else:
            result = _parse_tag_value(line)
            if result and response is not None:
                gggg, eeee, vr, taglen, value = result
                if gggg == 0x0008 and eeee == 0x0018:
                    response.imageuid = value
                elif gggg == 0x0020 and eeee == 0x0013:
                    try:
                        response.imagenumber = int(value)
                    except ValueError:
                        response.imagenumber = -1

    if response is not None and response.imageuid:
        responses.append(ImageLevelFields(response.imageuid, response.imagenumber))
    return responses


def dcm_ser_level_get(aet, node, port, laet, patid, studyuid, seriesuid, savedir):
    ''' Use dcm4che tool dcmqr to perform a series level c-get fetch. This is a coroutine.
        Each c-get response yields a CGetResponse record to the caller.
    '''
    global DCMQR
    get_cmd = [DCMQR]
    get_cmd += ['-async', '1']
    get_cmd += ['-device', laet]
    get_cmd += ['%s@%s:%s' % (aet, node, port)]
    get_cmd += ['-S']
    # get_cmd += ['-q', 'PatientID=%s' % patid]
    get_cmd += ['-q', 'StudyInstanceUID=%s' % studyuid]
    get_cmd += ['-q', 'SeriesInstanceUID=%s' % seriesuid]
    get_cmd += ['-cget']

    # we need every SOP class likely to occur or we get an error from the server and it all fails horribly
    # in particular Philips mix SC in with CT series and we'll need to cope with dose records and Siemens
    # private SOP classes and enhanced MR for philips fmri series
    sopclasses = [ 'MR:LE', 'CT:LE', 'SC:LE', 'US:LE', 'NM:LE', '1.3.12.2.1107.5.9.1:LE', '1.2.840.10008.5.1.4.1.1.4.1:LE']

    # interleave '-cstore' flags with sop class strings
    get_cmd += [item for items in zip(['-cstore'] * len(sopclasses), sopclasses) for item in items]
    get_cmd += ['-cstoredest', savedir]
    get_cmd += ['-reuseassoc']
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
        raise QIError("C-get from %s failed (%d), Command line was %s" % (aet, subproc.returncode, get_cmd))


def dcm_img_level_get(aet, node, port, laet, patid, studyuid, seriesuid, imageuid, savedir):
    ''' Use dcm4che tool dcmqr to perform an image level c-get fetch. This is a coroutine.
        Each c-get response yields a CGetResponse record to the caller.
    '''
    global DCMQR
    get_cmd = [DCMQR]
    get_cmd += ['-async', '1']
    get_cmd += ['-device', laet]
    get_cmd += ['%s@%s:%s' % (aet, node, port)]
    get_cmd += ['-I']
    get_cmd += ['-q', 'StudyInstanceUID=%s' % studyuid]
    get_cmd += ['-q', 'SeriesInstanceUID=%s' % seriesuid]
    get_cmd += ['-q', 'SOPInstanceUID=%s' % imageuid]
    get_cmd += ['-cget']

    # we need every SOP class likely to occur or we get an error from the server and it all fails horribly
    # in particular Philips mix SC in with CT series and we'll need to cope with dose records and Siemens
    # private SOP classes and enhanced MR for philips fmri series
    sopclasses = [ 'MR:LE', 'CT:LE', 'SC:LE', 'US:LE', 'NM:LE', '1.3.12.2.1107.5.9.1:LE', '1.2.840.10008.5.1.4.1.1.4.1:LE']

    # interleave '-cstore' flags with sop class strings
    get_cmd += [item for items in zip(['-cstore'] * len(sopclasses), sopclasses) for item in items]
    get_cmd += ['-cstoredest', savedir]
    get_cmd += ['-reuseassoc']
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


# example: 11:05:40,606 INFO   - CRICStore(1) >> 2:C-GET-RSP[pcid=5, remaining=null, completed=1, failed=0, warning=0, status=0H]
# unfortunately we don't seem to get the C-GET-RSP until the end
def _parse_cget_response(line):
    ''' Parse a line of query output that may contain a c-get info field.
        Returns None if no match to this.
    '''
    r = r"\d\d:\d\d:\d\d,[\d]{1,3}\s+INFO\s+-\s+[\w]+\([\d]+\)\s+>>\s+[\d]+:C-GET-RSP\[pcid=([\d]+),\s+remaining=([\d]+|null),\s+completed=([\d]+),\s+failed=([\d]+),\s+warning=([\d]+),\s+status=([\dA-Fa-f]{1,4})H"
    m = re.match(r, line)
    if m:
        pcid = int(m.group(1))
        if m.group(2) == 'null':
            remaining = 0
        else:
            remaining = int(m.group(2))
        completed = int(m.group(3))
        failed = int(m.group(4))
        warning = int(m.group(5))
        status = int(m.group(6), 16)
        return CGetResponse(pcid, remaining, completed, failed, warning, status)
    else:
        return None


# example: 13:30:51,755 INFO   - CRICStore(1) << 27:C-STORE-RSP[pcid=29, status=0H]
def _parse_cstore_response(line):
    ''' Parse a line of query output that may contain a c-get info field.
        Returns None if no match to this.
    '''
    r = r"\d\d:\d\d:\d\d,[\d]{1,3}\s+INFO\s+-\s+[\w]+\([\d]+\)\s+<<\s+[\d]+:C-STORE-RSP\[pcid=([\d]+),\s+status=([\dA-Fa-f]{1,4})H"
    m = re.match(r, line)
    if m:
        pcid = int(m.group(1))
        status = int(m.group(2), 16)
        return CStoreResponse(pcid, status)
    else:
        return None


def _parse_response_start(line):
    ''' Parse a line of query output that may contain a response header.
        Returns None if no match to this.
    '''
    r = r"\d\d:\d\d:\d\d,[\d]{1,3}\s+INFO\s+-\s+Query\s+Response\s+#([\d]{1,3}):"
    m = re.match(r, line)
    if m:
        response_number = m.group(1)
        return response_number
    else:
        return None


def _parse_tag_value(line):
    ''' Parse a line of query output that may contain a tag dump.
        Returns None if no match to this.
    '''
    r = r"\(([0-9A-Fa-f]{4}),([0-9A-Fa-f]{4})\)\s([A-Z]{2})\s#([\d]{1,3})\s\[([^\]]*)\]\s(.*)"
    m = re.match(r, line)
    if m:
        gggg = int(m.group(1), 16)
        eeee = int(m.group(2), 16)
        vr = m.group(3)
        taglen = int(m.group(4))
        value = m.group(5)
        return gggg, eeee, vr, taglen, value
    else:
        return None


if __name__ == '__main__':
    print("Module qidcm4che.py - see tests/ dir for unit tests")
