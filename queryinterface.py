from __future__ import print_function, division, absolute_import

from operator import attrgetter
from platform import node
from importlib import import_module
import os

from aettable import AetTable
from dicomweb import *
from collections import namedtuple

toolkit = os.environ.get('DCMTOOLKIT', None)
toolkits = ['dcm4che3', 'dcm4che', 'pynetdicom', 'mock']
if toolkit:
    toolkits.insert(0, toolkit)

from pydcm4che3 import finder, getter, Parser

CGetResponse = namedtuple(
    'CGetResponse',
    'pcid, remaining, completed, failed, warning, status'
)
CStoreResponse = namedtuple(
    'CStoreResponse',
    'pcid, status'
)

query_level_souported = {
    'W': {
        'patient': rst_pat_level_find,
        'study': rst_stu_level_find,
        'series': rst_ser_level_find,
        'image': rst_img_level_find,
    },
    'F': {
        'patient': finder,
        'study': finder,
        'series': finder,
        'image': finder,
    }
}

fetch_level_souported = {
    'W': {
        'patient': rst_pat_level_find,
        'study': rst_stu_level_find,
        'series': rst_ser_level_find,
        'image': rst_img_level_find,
    },
    'G': {
        'patient': getter,
        'study': getter,
        'series': getter,
        'image': getter,
    }
}

if 'query_level_souported' not in locals():
    raise Exception('no toolkit supported')


class Interface(object):

    def __init__(self, aettable=None, localaet=None):
        ''' Initialise with the node table and the local (calling) aet to use.
        '''
        if aettable is None:
            aettable = AetTable()
        if localaet is None:
            # NB: max len of aet is 16 chars; the 'Store' suffix is historical
            localaet = node().split('.')[0].replace('-', '')[:11] + 'Store'
        self.aettable = aettable
        self.localaet = localaet

    def fetch(self, servername, level, save_dir, **query_map):
        """ Fetch an image series from the dicom server.
            Implement as C-GET only for now."""
        print('####################')
        if servername not in self.aettable:
            raise QIError("%s is not in dicom node table" % servername)
        server = self.aettable[servername]
        completed = 0
        remaining = -1
        server_mark = None
        if 'W' in server.facilities:
            server_mark = 'W'
        elif 'G' in server.facilities:
            server_mark = 'G'
        getter = fetch_level_souported[server_mark][level]
        if server_mark == 'W':
            fetch_iter = rst_ser_level_get(
                endpoint=server.aet, node=server.host,
                port=server.port, auth=server.auth,
                **query_map)
        elif server_mark == 'G':
            fetch_iter = getter(
                aet=server.aet, node=server.host,
                port=server.port, laet=self.localaet,
                level=level, savedir=save_dir, **query_map)
        else:
            raise QIError(
                "%s supports neither direct (c-get) retrieve operations nor a web rest api" % servername)
        response = None
        for response in fetch_iter:
            if type(response) == CGetResponse:
                completed = response.completed
                remaining = response.remaining
                yield (completed, remaining)
            elif type(response) == CStoreResponse:
                completed += 1
                yield (completed, remaining)
        if response is None:
            return
        if response.status != 0:
            raise QIError("cget final response status non zero (%x)" % response.status)

    def query(self, servername, level, parser, ording_key=None, **query_map):
        ''' query interface to query the dicom files.
        '''

        server = self.aettable[servername]
        if 'W' in server.facilities:
            server_mark = 'W'
        elif 'F' in server.facilities:
            server_mark = 'F'

        if servername not in self.aettable:
            raise Exception("%s is not in dicom node table" % servername)
        if level not in query_level_souported[server_mark]:
            raise Exception('the level not supported, the supported choices are {}'.format(
                [key for key in query_level_souported[server_mark]]))
        finder = query_level_souported[server_mark][level]
        if server_mark == 'W':
            res = finder(
                endpoint=server.aet, node=server.host,
                port=server.port, auth=server.auth,
                ording_key=ording_key,
                parser=parser,
                level=level,
                **query_map,
            )
        elif server_mark == 'F':
            res = finder(
                aet=server.aet, node=server.host,
                port=server.port, laet=self.localaet,
                ording_key=ording_key,
                parser=parser,
                level=level,
                **query_map,

            )
        else:
            raise Exception(
                "%s supports neither dicom query (c-find) operations nor a web rest api" % servername)
        if ording_key:
            return sorted(res, key=attrgetter(ording_key))
        return res


if __name__ == '__main__':
    interface = Interface()
    print("Successfully instantiated a QueryInterface()")
    print('Aettable:')
    print(interface.aettable)
    print('Local AET =', interface.localaet)

    # query_map = {
    #     'PatientID': '',
    #     'PatientName': '',
    #     'PatientSex': '',
    #     'StudyID': '',
    #     'StudyInstanceUID': '',
    #     'StudyDate': '20180205',
    # }

    # query_maps = interface.query(servername='Server',
    #                           level='study', parser=Parser.tag_parser, **query_map)
    # print(query_maps[:10])
    # for query_map in query_maps[:10]:
    #     print('study', query_map)
    #     query_map.update({
    #         'SeriesInstanceUID': '',
    #     })
    #     _query_maps = interface.query(servername='Server', level='series', parser=Parser.tag_parser, **query_map)
    #     print('series', _query_maps)
    #     for query_map in _query_maps:
    #         query_map.update({
    #             'SOPInstanceUID': '',
    #         })
    #         __query_maps = interface.query(servername='Server', level='image', parser=Parser.tag_parser, **query_map)
    #         print('image', __query_maps)
    #         for query_map in __query_maps:
    #             print('fetch', query_map)
    query_map = {
    'SOPInstanceUID': 'AU614718.2018-02-0515:27:23', 
    'PatientID': '02401845', 
    # 'PatientSex': 'M', 
    'StudyInstanceUID': 'APPLYSHEET614718', 
    'SeriesInstanceUID': 'APPLYSHEET6147181'}
    query_maps = interface.query(servername='Server',
                              level='image', parser=Parser.tag_parser, **query_map)
    print(query_maps)
    # list(interface.fetch(servername='Server', level='series', save_dir='./', **query_map))

