#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DICOM query fetch interface based on the the pynetdicom.

This is not currently functional due to problems with pynetdicom
which is also not python3 compatible (though there is a fork with a different
API that is python3 only.
"""

from __future__ import print_function, division, absolute_import

import os

import netdicom
# netdicom.debug(True)
netdicom.debug(False)
from netdicom.applicationentity import AE
from netdicom.SOPclass import PatientRootFindSOPClass, VerificationSOPClass

try:
    from pydicom.dataset import Dataset
    from pydicom.UID import ExplicitVRLittleEndian
except ImportError:
    from dicom.dataset import Dataset
    from dicom.UID import ExplicitVRLittleEndian

from threading import Thread
try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

from netdicom.SOPclass import (
    PatientRootGetSOPClass, RTPlanStorageSOPClass,
    CTImageStorageSOPClass, MRImageStorageSOPClass, RTImageStorageSOPClass
)

from . structures import *

# module global
msg_id = 1


def dcm_pat_level_find(aet, node, port, laet, patname, patid, birthdate, sex):
    ''' Use pynetdicom to perform a patient level query. The result is a list
        of PatientLevelFields records.
    '''
    global msg_id
    msg_id += 1

    # Create application entity and association with remote AE (port number of 0 to stop it putting up a listen)
    ae = AE(laet, port=0, SOPSCU=[PatientRootFindSOPClass], SOPSCP=[])
    ae.start()
    assoc = ae.RequestAssociation({'Address': node, 'Port': port, 'AET': aet})

    # Query object
    d = Dataset()
    d.PatientID = patid
    d.PatientName = patname
    d.PatientBirthDate = birthdate
    d.PatientSex = sex
    d.NumberOfPatientRelatedStudies = ''
    d.QueryRetrieveLevel = 'PATIENT'

    # Request returns a generator
    responses = []
    matches = assoc.PatientRootFindSOPClass.SCU(d, msg_id)

    for state, ds in matches:
        if state == 'Pending':
            patname  = ds.PatientName if 'PatientName' in ds else 'Unknown'
            patid    = ds.PatientID if 'PatientID' in ds else ''
            patdob   = ds.PatientBirthDate if 'PatientBirthDate' in ds else ''
            patsex   = ds.PatientSex if 'PatientSex' in ds else ''
            nstudies = ds.NumberOfPatientRelatedStudies if 'NumberOfPatientRelatedStudies' in ds else 0
            responses.append(PatientLevelFields(patname, patid, patdob, patsex, nstudies))

    assoc.Release(0)
    ae.Quit()

    return responses


def dcm_stu_level_find(aet, node, port, laet, patid):
    ''' Use pynetdicom to perform a study level query. The result is a list
        of StudyLevelFields records.
    '''
    global msg_id
    msg_id += 1

    # Create application entity and association with remote AE (port number of 0 to stop it putting up a listen)
    ae = AE(laet, port=0, SOPSCU=[PatientRootFindSOPClass], SOPSCP=[])
    ae.start()
    assoc = ae.RequestAssociation({'Address': node, 'Port': port, 'AET': aet})

    # Query object
    d = Dataset()
    d.PatientID = patid
    d.StudyInstanceUID = ''
    d.StudyID = ''
    d.StudyDate = ''
    d.StudyDescription = ''
    d.NumberOfStudyRelatedSeries = ''
    d.QueryRetrieveLevel = 'STUDY'

    # Request returns a generator
    responses = []
    matches = assoc.PatientRootFindSOPClass.SCU(d, msg_id)
    for state, ds in matches:
        if state == 'Pending':
            patid        = ds.PatientID if 'PatientID' in ds else ''
            studyid      = ds.StudyID if 'StudyID'   in ds else ''
            studyuid     = ds.StudyInstanceUID if 'StudyInstanceUID'  in ds else ''
            studydate    = ds.StudyDate if 'StudyDate' in ds else ''
            studydescr   = ds.StudyDescription if 'StudyDescription' in ds else ''
            nseries      = ds.NumberOfStudyRelatedSeries if 'NumberOfStudyRelatedSeries' in ds else 0
            responses.append(StudyLevelFields(studyid, studyuid, studydate, studydescr, nseries))

    assoc.Release(0)
    ae.Quit()

    return responses


def dcm_ser_level_find(aet, node, port, laet, patid, studyuid):
    ''' Use pynetdicom to perform a series level query. The result is a list
        of SeriesLevelFields records.
    '''
    global msg_id
    msg_id += 1

    # Create application entity and association with remote AE (port number of 0 to stop it putting up a listen)
    ae = AE(laet, port=0, SOPSCU=[PatientRootFindSOPClass], SOPSCP=[])
    ae.start()
    assoc = ae.RequestAssociation({'Address': node, 'Port': port, 'AET': aet})

    # Query object
    d = Dataset()
    d.PatientID = patid
    d.StudyInstanceUID = studyuid
    d.SeriesInstanceUID = ''
    d.Modality = ''
    d.SeriesDate = ''
    d.SeriesNumber = ''
    d.SeriesDescription = ''
    d.BodyPartExamined = ''
    d.NumberOfSeriesRelatedInstances = ''
    d.QueryRetrieveLevel = 'SERIES'

    # Request returns a generator
    responses = []
    matches = assoc.PatientRootFindSOPClass.SCU(d, msg_id)
    for state, ds in matches:
        if state == 'Pending':
            patid        = ds.PatientID if 'PatientID' in ds else ''
            studyuid     = ds.StudyInstanceUID if 'StudyInstanceUID'  in ds else ''
            seriesuid    = ds.SeriesInstanceUID  if 'SeriesInstanceUID'  in ds else ''
            seriesdate   = ds.SeriesDate if 'SeriesDate' in ds else ''
            seriesdescr  = ds.SeriesDescription if 'SeriesDescription' in ds else ''
            seriesnumber = ds.SeriesNumber if 'SeriesNumber' in ds else ''
            modality     = ds.Modality if 'Modality' in ds else ''
            bodypart     = ds.BodyPartExamined if 'BodyPartExamined' in ds else ''
            nimages      = ds.NumberOfSeriesRelatedInstances if 'NumberOfSeriesRelatedInstances' in ds else 0
            responses.append(SeriesLevelFields(modality, seriesnumber, seriesuid, seriesdescr, bodypart, nimages))

    assoc.Release(0)
    ae.Quit()

    return responses


def dcm_img_level_find(aet, node, port, laet, patid, studyuid, seriesuid):
    ''' Use pynetdicom to perform a image level query. The result is a list
        of ImageLevelFields records.
    '''
    global msg_id
    msg_id += 1

    # Create application entity and association with remote AE (port number of 0 to stop it putting up a listen)
    ae = AE(laet, port=0, SOPSCU=[PatientRootFindSOPClass], SOPSCP=[])
    ae.start()
    assoc = ae.RequestAssociation({'Address': node, 'Port': port, 'AET': aet})

    # Query object
    d = Dataset()
    d.PatientID = patid
    d.StudyInstanceUID = studyuid
    d.SeriesInstanceUID = seriesuid
    d.SOPInstanceUID = ''
    d.InstanceNumber = ''
    d.QueryRetrieveLevel = 'IMAGE'

    # Request returns a generator
    responses = []
    matches = assoc.PatientRootFindSOPClass.SCU(d, msg_id)
    for state, ds in matches:
        if state == 'Pending':
            patid       = ds.PatientID if 'PatientID' in ds else ''
            studyuid    = ds.StudyInstanceUID if 'StudyInstanceUID'  in ds else ''
            seriesuid   = ds.SeriesInstanceUID if 'SeriesInstanceUID'  in ds else ''
            imageuid    = ds.SOPInstanceUID if 'SOPInstanceUID' in ds else ''
            imagenumber = ds.InstanceNumber if 'InstanceNumber' in ds else ''
            responses.append(ImageLevelFields(imageuid, imagenumber))

    assoc.Release(0)
    ae.Quit()

    return responses


'''
This would be fine but it seems to cause corruption in PyQt4
'''


def dcm_ser_level_get(aet, node, port, laet, patid, studyuid, seriesuid, savedir):
    ''' Use pynetdicom to perform a series level c-get fetch. This is a coroutine/generator.
        Each response yields a CGetResponse record to the caller. The yield is tied to the
        c-store messages rather than (as would be more natural) the c-get reponses because
        dcm4chee doesn't seem to issue the intermediate pending c-get reponses.
    '''
    queue = Queue()
    returns = []
    dcmthread = Thread(target=_pynetdicom_ser_get_worker,
                       args=[aet, node, port, laet, patid, studyuid, seriesuid, savedir, queue, returns],
                       kwargs={})

    dcmthread.daemon = True
    dcmthread.start()

    while dcmthread.is_alive():
        try:
            item = queue.get(block=True, timeout=1)
            yield item
            queue.task_done()
        except Empty:
            pass

    return


def _pynetdicom_ser_get_worker(aet, node, port, laet, patid, studyuid, seriesuid, savedir, queue, returns):
    ''' Use pynetdicom to perform a series level c-get fetch. This is to be run in a separate worker thread.
        The c-store callbacks save the images and push a CStoreResponse object onto a queue for the main thread.
        The function returns normally, which will lead to the threading terminating. This is detected by the
        parent thread.
    '''
    global msg_id
    msg_id += 1

    # a slight kludge as python 2.7 doesn't have 'nonlocal' qualifier
    image_counter = [0]

    # The callback function for C-STORE sub-operations
    def on_receive_store(cget_obj, ds):
        try:
            # print 'C-STORE callback(cget=%s,instno=%d)' % (cget_obj, ds.InstanceNumber)
            # This is a bit of a hack but we need to add some file-meta
            file_meta = Dataset()
            file_meta.add_new((2, 0x01), 'OB', b'\0\1')                 # FileMetaInformationVersion
            file_meta.add_new((2, 0x02), 'UI', ds.SOPClassUID)          # MediaStorageSOPClassUID
            file_meta.add_new((2, 0x03), 'UI', ds.SOPInstanceUID)       # MediaStorageSOPInstanceUID
            file_meta.add_new((2, 0x10), 'UI', ExplicitVRLittleEndian)  # TransferSyntaxUID
            file_meta.add_new((2, 0x12), 'UI', '1.2.40.0.13.1.1')       # ImplementationClassUID
            file_meta.add_new((2, 0x13), 'SH', 'pynetdicom')            # ImplementationVersionName
            ds.file_meta = file_meta
            # and specify the encoding
            ds.is_implicit_VR = False
            ds.is_little_endian = True

            save_path = os.path.join(savedir, '%05d.dcm' % (image_counter[0] + 1))
            # the WriteLikeOriginal=False flag is need to get preamble etc right
            ds.save_as(filename=save_path, WriteLikeOriginal=False)
            image_counter[0] += 1
            pcid = image_counter[0]  # for the sake of argument
            # actually what we want here is the message object so we can extract the no of operations, status etc
            status = 0
            queue.put(CStoreResponse(pcid, status))

        except Exception as e:
            # print 'Error saving: C-STORE callback(cget=%s, instno=%d), saving to %s [%s]' % (cget_obj, ds.InstanceNumber, save_path, e)
            print('Error Saving: %s' % e)
            return 1  # ?? RHD
        # zero corresponds to DICOM Success
        return 0

    # Create application entity and association with remote AE (port number of 0 to stop it putting up a listen)
    ae = AE(laet, port=0, SOPSCU=[PatientRootGetSOPClass],
                          SOPSCP=[RTPlanStorageSOPClass,
                                  CTImageStorageSOPClass,
                                  MRImageStorageSOPClass,
                                  RTImageStorageSOPClass])
    ae.OnReceiveStore = on_receive_store
    ae.start()
    assoc = ae.RequestAssociation({'Address': node, 'Port': port, 'AET': aet})

    # Query object
    d = Dataset()
    d.PatientID = str(patid)
    d.StudyInstanceUID = str(studyuid)
    d.SeriesInstanceUID = str(seriesuid)
    d.QueryRetrieveLevel = 'SERIES'

    st_ds = assoc.PatientRootGetSOPClass.SCU(d, msg_id)
    if st_ds is not None:
        for status, ds in st_ds:
            pass
            # print 'status = %s, dataset = %s' % (status, ds)
    # print 'Done'

    returns.append(status)
    return


def dcm_img_level_get(aet, node, port, laet, patid, studyuid, seriesuid, imageuid, savedir):
    ''' Use pynetdicom to perform an image level c-get fetch. This is a coroutine/generator.
        Each response yields a CGetResponse record to the caller. The yield is tied to the
        c-store messages rather than (as would be more natural) the c-get reponses because
        dcm4chee doesn't seem to issue the intermediate pending c-get reponses.
    '''
    queue = Queue()
    returns = []
    dcmthread = Thread(target=_pynetdicom_img_get_worker,
                       args=[aet, node, port, laet, patid, studyuid, seriesuid, imageuid, savedir, queue, returns],
                       kwargs={})

    dcmthread.daemon = True
    dcmthread.start()

    while dcmthread.is_alive():
        try:
            item = queue.get(block=True, timeout=1)
            yield item
            queue.task_done()
        except Empty:
            pass

    return


def _pynetdicom_img_get_worker(aet, node, port, laet, patid, studyuid, seriesuid, imageuid, savedir, queue, returns):
    ''' Use pynetdicom to perform a series level c-get fetch. This is to be run in a separate worker thread.
        The c-store callbacks save the images and push a CStoreResponse object onto a queue for the main thread.
        The function returns normally, which will lead to the threading terminating. This is detected by the
        parent thread.
    '''
    global msg_id
    msg_id += 1

    # a slight kludge as python 2.7 doesn't have 'nonlocal' qualifier
    image_counter = [0]

    # The callback function for C-STORE sub-operations
    def on_receive_store(cget_obj, ds):
        try:
            # print 'C-STORE callback(cget=%s,instno=%d)' % (cget_obj, ds.InstanceNumber)
            # This is a bit of a hack but we need to add some file-meta
            file_meta = Dataset()
            file_meta.add_new((2, 0x01), 'OB', b'\0\1')                 # FileMetaInformationVersion
            file_meta.add_new((2, 0x02), 'UI', ds.SOPClassUID)          # MediaStorageSOPClassUID
            file_meta.add_new((2, 0x03), 'UI', ds.SOPInstanceUID)       # MediaStorageSOPInstanceUID
            file_meta.add_new((2, 0x10), 'UI', ExplicitVRLittleEndian)  # TransferSyntaxUID
            file_meta.add_new((2, 0x12), 'UI', '1.2.40.0.13.1.1')       # ImplementationClassUID
            file_meta.add_new((2, 0x13), 'SH', 'pynetdicom')            # ImplementationVersionName
            ds.file_meta = file_meta
            # and specify the encoding
            ds.is_implicit_VR = False
            ds.is_little_endian = True

            save_path = os.path.join(savedir, '%05d.dcm' % (image_counter[0] + 1))
            # the WriteLikeOriginal=False flag is need to get preamble etc right
            ds.save_as(filename=save_path, WriteLikeOriginal=False)
            image_counter[0] += 1
            pcid = image_counter[0]  # for the sake of argument
            # actually what we want here is the message object so we can extract the no of operations, status etc
            status = 0
            queue.put(CStoreResponse(pcid, status))

        except Exception as e:
            # print 'Error saving: C-STORE callback(cget=%s, instno=%d), saving to %s [%s]' % (cget_obj, ds.InstanceNumber, save_path, e)
            print('Error Saving: %s' % e)
            return 1  # ?? RHD
        # zero corresponds to DICOM Success
        return 0

    # Create application entity and association with remote AE (port number of 0 to stop it putting up a listen)
    ae = AE(laet, port=0, SOPSCU=[PatientRootGetSOPClass],
                          SOPSCP=[RTPlanStorageSOPClass,
                                  CTImageStorageSOPClass,
                                  MRImageStorageSOPClass,
                                  RTImageStorageSOPClass])
    ae.OnReceiveStore = on_receive_store
    ae.start()
    assoc = ae.RequestAssociation({'Address': node, 'Port': port, 'AET': aet})

    # Query object
    d = Dataset()
    d.PatientID = str(patid)
    d.StudyInstanceUID = str(studyuid)
    d.SeriesInstanceUID = str(seriesuid)
    d.SOPInstanceUID = str(imageuid)
    d.QueryRetrieveLevel = 'IMAGE'

    st_ds = assoc.PatientRootGetSOPClass.SCU(d, msg_id)
    if st_ds is not None:
        for status, ds in st_ds:
            pass
            # print 'status = %s, dataset = %s' % (status, ds)
    # print 'Done'

    returns.append(status)
    return


if __name__ == '__main__':
    print("TODO: Need to write tests for qipynetdicom.py")
