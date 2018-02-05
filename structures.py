#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Structures for DICOM requests and responses
"""

from __future__ import print_function, division, absolute_import

from collections import namedtuple

PatientLevelFields = namedtuple(
    'PatientLevelFields',
    'PatientName, PatientID, PatientDob, PatientSex, nStudies')
PatientStudyLevelFields = namedtuple(
    'StudyLevelFields',
    'PatientName, PatientID, PatientDob, PatientSex, StudyID, StudyUID, StudyDate, Description, nSeries'
)
StudyLevelFields = namedtuple(
    'StudyLevelFields',
    'StudyID, StudyUID, StudyDate, Description, nSeries'
)
SeriesLevelFields = namedtuple(
    'SeriesLevelFields',
    'Modality, SeriesNumber, SeriesUID, Description, BodyPart, nImages'
)
ImageLevelFields = namedtuple(
    'ImageLevelFields',
    'ImageUID, ImageNumber'
)

CGetResponse = namedtuple(
    'CGetResponse',
    'pcid, remaining, completed, failed, warning, status'
)
CStoreResponse = namedtuple(
    'CStoreResponse',
    'pcid, status'
)


class QIError(Exception):
    pass


if __name__ == '__main__':
    PatientLevelFields()
    StudyLevelFields()
    SeriesLevelFields()
    ImageLevelFields()
    ComboFields()
    CGetResponse()
    CStoreResponse()
    try:
        raise QIError('An Error')
    except QIError as e:
        assert str(e) == 'An Error'
