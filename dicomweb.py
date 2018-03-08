#!/usr/bin/env python
"""
Implements an interface to the DICOM WEB restful api.

The restful interface itself supports three services which correspond to native DICOM services:
 - qido-rs (c-find)
 - wado-rs (c-get)
 - stow-rs (c-store).

These are presented here in an api that matches the query interface one in queryinterface.py so it
can be used as a drop in alternative where the dicom server (eg Orthanc) supports this protocol.
"""

from __future__ import division, print_function, absolute_import
import sys
from os.path import join
import email
import requests

from .structures import (
    PatientLevelFields, StudyLevelFields,
    SeriesLevelFields, ImageLevelFields,
    CStoreResponse
)

PY3K = sys.version_info >= (3, 0)


def rst_pat_level_find(endpoint, node, port, auth, query_map):
    """Patient level find using DICOM QIDO-RS rest API.

    Behaves similarly to a DICOM Patient Level C-FIND
    but uses StudyRoot hierarchy of QI-RS API.

    Parameters
    ----------
    endpoint : str
        Root of QI-RS/WADO-RS in URL.
    node : str
        Hostname.
    port: int
        TCP port number
    auth: str
        Colon separated username:password combination
    Returns
    -------
    list
        Sorted list of matching PatientLevelFields structures
    """
    PATNAME = "00100010"
    PATID = "00100020"
    PATBDATE = "00100030"
    PATSEX = "00100040"
    accept = {'Accept': 'application/json'}
    url = 'http://%s:%d/%s/studies/' % (node, port, endpoint)
    with requests.Session() as s:
        if auth is not None:
            user, passwd = auth.split(':')
            http_response = s.get(url, auth=(user, passwd), headers=accept, params=query_map)
        else:
            http_response = s.get(url, headers=accept, params=query_map)

    matches = http_response.json()

    patients = [
        PatientLevelFields(
            str(match[PATNAME]['Value'][0]),
            str(match[PATID]['Value'][0]),
            str(match[PATBDATE]['Value'][0]),
            str(match[PATSEX]['Value'][0]),
            0
        ) for match in matches
    ]

    return sorted(set(patients))


def rst_stu_level_find(endpoint, node, port, auth, patid):
    """Study level find using DICOM QIDO-RS rest API.

    Behaves similarly to a DICOM Study Level C-FIND
    but uses QIDO-RS API. Assume that Patients are uniquely identified by ID.

    Parameters
    ----------
    endpoint : str
        Root of QIDO-RS/WADO-RS in URL.
    node : str
        Hostname.
    port: int
        TCP port number
    auth: str
        Colon separated username:password combination
    patid: str
        Explicit unique PatientID (no wild cards)

    Returns
    -------
    list
        Sorted list of matching StudyLevelFields structures for the specified Patient
    """
    STUDYID = "00200010"
    STUDYUID = "0020000D"
    STUDYDATE = "00080020"
    STUDYDESCR = "00081030"

    query = {'PatientID': patid, 'StudyDescription': '*'}
    accept = {'Accept': 'application/json'}
    url = 'http://%s:%d/%s/studies/' % (node, port, endpoint)

    with requests.Session() as s:
        if auth is not None:
            user, passwd = auth.split(':')
            http_response = s.get(url, auth=(user, passwd), headers=accept, params=query)
        else:
            http_response = s.get(url, headers=accept, params=query)

    matches = http_response.json()

    studies = [
        StudyLevelFields(
            str(match[STUDYID]['Value'][0]),
            str(match[STUDYUID]['Value'][0]),
            str(match[STUDYDATE]['Value'][0]),
            str(match[STUDYDESCR]['Value'][0]),
            0
        ) for match in matches
    ]

    return studies


def rst_ser_level_find(endpoint, node, port, auth, studyuid):
    """Series level find using DICOM QIDO-RS rest API.

    Behaves similarly to a DICOM Series Level C-FIND but uses QIDO-RS API.
    The patient id is not required as the rest api is study rooted.

    Parameters
    ----------
    endpoint : str
        Root of QIDO-RS/WADO-RS in URL.
    node : str
        Hostname.
    port: int
        TCP port number
    auth: str
        Colon separated username:password combination
    studyuid: str
        DICOM Study UID
    Returns
    -------
    list
        Sorted list of matching SeriesLevelFields structures for the specified Study
    """
    SERIESMODALITY = "00080060"
    SERIESNUMBER = "00200011"
    SERIESUID = "0020000E"
    SERIESDESCR = "0008103E"
    SERIESBODYPART = "00180015"

    query = {'Modality': '*', 'BodyPartExamined': '*'}
    accept = {'Accept': 'application/json'}
    url = 'http://%s:%d/%s/studies/%s/series' % (node, port, endpoint, studyuid)

    with requests.Session() as s:
        if auth is not None:
            user, passwd = auth.split(':')
            http_response = s.get(url, auth=(user, passwd), headers=accept, params=query)
        else:
            http_response = s.get(url, headers=accept, params=query)

    matches = http_response.json()

    series = [
        SeriesLevelFields(
            str(match[SERIESMODALITY]['Value'][0]),
            int(match[SERIESNUMBER]['Value'][0]),
            str(match[SERIESUID]['Value'][0]),
            str(match[SERIESDESCR]['Value'][0]),
            str(match[SERIESBODYPART]['Value'][0]),
            0
        ) for match in matches
    ]

    return series


def rst_img_level_find(endpoint, node, port, auth, studyuid, seriesuid):
    """Image level find using DICOM QIDO-RS rest API.

    Behaves similarly to a DICOM Image Level C-FIND but uses QIDO-RS API.
    The patient id is not required as the rest api is study rooted.

    Parameters
    ----------
    endpoint : str
        Root of QIDO-RS/WADO-RS in URL.
    node : str
        Hostname.
    port: int
        TCP port number
    auth: str
        Colon separated username:password combination
    studyuid: str
        DICOM Study UID
    seriesuid: str
        DICOM Series UID
    Returns
    -------
    list
        Sorted list of matching SeriesLevelFields structures for the specified Study
    """
    INSTANCENUMBER = "00200013"
    INSTANCEUID = "00080018"

    # need to get these from somewhere on a per host basis
    user, passwd = auth.split(':')

    query = {'InstanceNumber': '*'}
    accept = {'Accept': 'application/json'}
    url = 'http://%s:%d/%s/studies/%s/series/%s/instances' % (node, port, endpoint, studyuid, seriesuid)

    with requests.Session() as s:
        if auth is not None:
            user, passwd = auth.split(':')
            http_response = s.get(url, auth=(user, passwd), headers=accept, params=query)
        else:
            http_response = s.get(url, headers=accept, params=query)

    # need to check it's 200 and raise if not
    matches = http_response.json()
    images = [
        ImageLevelFields(
            str(match[INSTANCEUID]['Value'][0]),
            int(match[INSTANCENUMBER]['Value'][0])
        ) for match in matches
    ]

    return images


def rst_ser_level_get(endpoint, node, port, auth, studyuid, seriesuid, savedir):
    """Series level get using DICOM WADO-RS rest API.

    Behaves similarly to a DICOM Series Level C-GET but uses WADO-RS API.
    The patient id is not required as the rest api is study rooted.
    The function is a generator and yields for each dicom object extracted
    from the returned multipart and saved to the given directory as a part 10 file.

    Parameters
    ----------
    endpoint : str
        Root of QIDO-RS/WADO-RS in URL.
    node : str
        Hostname.
    port: int
        TCP port number
    auth: str
        Colon separated username:password combination
    studyuid: str
        DICOM Study UID
    seriesuid: str
        DICOM Series UID
    savedir: str
        Existing directory to save DICOM objects to.
    Returns
    -------
    Function is a generator
    """
    user, passwd = auth.split(':')

    url = 'http://%s:%d/%s/studies/%s/series/%s' % (node, port, endpoint, studyuid, seriesuid)

    with requests.Session() as s:
        if auth is not None:
            user, passwd = auth.split(':')
            http_response = s.get(url, auth=(user, passwd))
        else:
            http_response = s.get(url)

    #  Construct valid mime by prepending content type
    hdr = ('Content-Type: ' + http_response.headers['Content-Type']).encode()
    if PY3K:
        msg = email.message_from_bytes(hdr + b'\r\n' + http_response.content)
    else:
        msg = email.message_from_string(hdr + b'\r\n' + http_response.content)

    fileno = 1
    for part in msg.walk():
        dcmdata = part.get_payload(decode=True)
        if dcmdata is not None:
            filename = join(savedir, '%04d.dcm' % fileno)
            with open(filename, 'wb') as f:
                f.write(dcmdata)
            fileno += 1
            #  dummy
            yield CStoreResponse(0, 0)
    return


def rst_img_level_get(endpoint, node, port, auth, studyuid, seriesuid, imageuid, savedir):
    """Image level get using DICOM WADO-RS rest API.

    Behaves similarly to a DICOM Image Level C-GET but uses WADO-RS API.
    The patient id is not required as the rest api is study rooted.
    The function is a generator and yields for each dicom object extracted
    from the returned multipart and saved to the given directory as a part 10 file
    for consistency with the series level get. However we expect a single object only.

    Parameters
    ----------
    endpoint : str
        Root of QIDO-RS/WADO-RS in URL.
    node : str
        Hostname.
    port: int
        TCP port number
    auth: str
        Colon separated username:password combination
    studyuid: str
        DICOM Study UID
    seriesuid: str
        DICOM Series UID
    imageuid: str
        DICOM SOP Instance (ie Image) UID
    savedir: str
        Existing directory to save DICOM objects to.
    Returns
    -------
    Function is a generator
    """
    url = (
        'http://%s:%d/%s/studies/%s/series/%s/instances/%s' %
        (node, port, endpoint, studyuid, seriesuid, imageuid)
    )

    with requests.Session() as s:
        if auth is not None:
            user, passwd = auth.split(':')
            http_response = s.get(url, auth=(user, passwd))
        else:
            http_response = s.get(url)

    if http_response.status_code != 200:
        return

    # Construct valid mime by prepending content type
    hdr = ('Content-Type: ' + http_response.headers['Content-Type']).encode()
    if PY3K:
        msg = email.message_from_bytes(hdr + b'\r\n' + http_response.content)
    else:
        msg = email.message_from_string(hdr + b'\r\n' + http_response.content)

    fileno = 1
    for part in msg.walk():
        dcmdata = part.get_payload(decode=True)
        if dcmdata is not None:
            filename = join(savedir, '%04d.dcm' % fileno)
            with open(filename, 'wb') as f:
                f.write(dcmdata)
            fileno += 1
            # dummy
            # TODO decide on form of response CGetResponse may be more logical
            # make a new one for WadoRsResponse
            yield CStoreResponse(0, 0)
    return


if __name__ == '__main__':
    try:
        import pydicom as dcm
    except ImportError:
        import dicom as dcm
    import tempfile
    from glob import glob
    from shutil import rmtree
    patients = rst_pat_level_find(
        endpoint='dicom-web',
        node='capella',
        port=8042,
        auth='orthanc:orthanc',
        patname='*', patid='*', birthdate='*', sex='*'
    )
    patid = patients[0].patid
    print(patid)

    studies = rst_stu_level_find(
        endpoint='dicom-web',
        node='capella',
        port=8042,
        auth='orthanc:orthanc',
        patid=patid
    )
    studyuid = studies[0].studyuid
    print(studyuid)

    series = rst_ser_level_find(
        endpoint='dicom-web',
        node='capella',
        port=8042,
        auth='orthanc:orthanc',
        studyuid=studyuid
    )
    seriesuid = series[0].seriesuid
    print(seriesuid)

    images = rst_img_level_find(
        endpoint='dicom-web',
        node='capella',
        port=8042,
        auth='orthanc:orthanc',
        studyuid=studyuid,
        seriesuid=seriesuid
    )
    imageuid = images[0].imageuid
    print(imageuid)

    tempd = tempfile.mkdtemp()
    fetch_iter = rst_ser_level_get(
        endpoint='dicom-web',
        node='capella',
        port=8042,
        auth='orthanc:orthanc',
        studyuid=studyuid,
        seriesuid=seriesuid,
        savedir=tempd)
    list(fetch_iter)

    dobjs = sorted([dcm.read_file(f) for f in glob(join(tempd, '*'))], key=lambda d: int(d.InstanceNumber))
    print([int(d.InstanceNumber) for d in dobjs])
    rmtree(tempd)

    tempd = tempfile.mkdtemp()
    fetch_iter = rst_img_level_get(
        endpoint='dicom-web',
        node='capella',
        port=8042,
        auth='orthanc:orthanc',
        studyuid=studyuid,
        seriesuid=seriesuid,
        imageuid=imageuid,
        savedir=tempd)
    list(fetch_iter)

    dobjs = sorted([dcm.read_file(f) for f in glob(join(tempd, '*'))], key=lambda d: int(d.InstanceNumber))
    print([int(d.InstanceNumber) for d in dobjs])
    rmtree(tempd)
