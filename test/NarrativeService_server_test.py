# -*- coding: utf-8 -*-
import unittest
import os  # noqa: F401
import json  # noqa: F401
import time
import requests

from os import environ
from NarrativeService.NarrativeManager import NarrativeManager
try:
    from ConfigParser import ConfigParser  # py2
except:
    from configparser import ConfigParser  # py3

from pprint import pprint  # noqa: F401

from Workspace.WorkspaceClient import Workspace
from NarrativeService.NarrativeServiceImpl import NarrativeService
from NarrativeService.NarrativeServiceServer import MethodContext
from SetAPI.SetAPIClient import SetAPI
from NarrativeService.WorkspaceListObjectsIterator import WorkspaceListObjectsIterator
from FakeObjectsForTests.FakeObjectsForTestsClient import FakeObjectsForTests
from DataPaletteService.DataPaletteServiceClient import DataPaletteService


class NarrativeServiceTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        token = environ.get('KB_AUTH_TOKEN', None)
        user_id = requests.post(
            'https://kbase.us/services/authorization/Sessions/Login',
            data='token={}&fields=user_id'.format(token)).json()['user_id']
        # WARNING: don't call any logging methods on the context object,
        # it'll result in a NoneType error
        cls.ctx = MethodContext(None)
        cls.ctx.update({'token': token,
                        'user_id': user_id,
                        'provenance': [
                            {'service': 'NarrativeService',
                             'method': 'please_never_use_it_in_production',
                             'method_params': []
                             }],
                        'authenticated': 1})
        config_file = environ.get('KB_DEPLOYMENT_CONFIG', None)
        cls.cfg = {}
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items('NarrativeService'):
            cls.cfg[nameval[0]] = nameval[1]
        cls.wsURL = cls.cfg['workspace-url']
        cls.serviceWizardURL = cls.cfg['service-wizard']
        cls.wsClient = Workspace(cls.wsURL, token=token)
        cls.serviceImpl = NarrativeService(cls.cfg)
        cls.SetAPI_version = cls.cfg['setapi-version']
        cls.DataPalette_version = cls.cfg['datapaletteservice-version']
        cls.intro_text_file = cls.cfg['intro-markdown-file']
        cls.example_ws_name = cls.createWsStatic()
        # Reads
        cls.example_reads_name = "example_reads.1"
        foft = FakeObjectsForTests(os.environ['SDK_CALLBACK_URL'])
        info1 = foft.create_fake_reads({'ws_name': cls.example_ws_name, 
                                        'obj_names': [cls.example_reads_name]})[0]
        cls.example_reads_ref = str(info1[6]) + '/' + str(info1[0]) + '/' + str(info1[4])
        # Genome
        cls.example_genome_name = "example_genome.1"
        foft = FakeObjectsForTests(os.environ['SDK_CALLBACK_URL'])
        info2 = foft.create_fake_genomes({'ws_name': cls.example_ws_name, 
                                          'obj_names': [cls.example_genome_name]})[0]
        cls.example_genome_ref = str(info2[6]) + '/' + str(info2[0]) + '/' + str(info2[4])
        # Other objects
        foft.create_any_objects({'ws_name': cls.example_ws_name,
                                 'obj_names': ['any_obj_' + str(i) for i in range(0, 30)]})

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'createdWorkspaces'):
            for wsName in cls.createdWorkspaces:
                try:
                    cls.wsClient.delete_workspace({'workspace': wsName})
                    print('Test workspace was deleted')
                except:
                    print('Error deleting test workspace')

    def getWsClient(self):
        return self.__class__.wsClient

    def createWs(self):
        return self.__class__.createWsStatic()
        
    @classmethod
    def createWsStatic(cls):
        suffix = int(time.time() * 1000)
        wsName = "test_NarrativeService_" + str(suffix)
        cls.wsClient.create_workspace({'workspace': wsName})  # noqa
        createdWorkspaces = None
        if hasattr(cls, 'createdWorkspaces'):
            createdWorkspaces = cls.createdWorkspaces
        else:
            createdWorkspaces = []
            cls.createdWorkspaces = createdWorkspaces
        createdWorkspaces.append(wsName)
        return wsName

    def getImpl(self):
        return self.__class__.serviceImpl

    def getContext(self):
        return self.__class__.ctx

    # NOTE: According to Python unittest naming rules test method names should start from 'test'. # noqa
    def test_list_object_with_sets(self):
        ws_name1 = self.createWs()
        reads_obj_ref = self.__class__.example_reads_ref
        set_obj_name = "MyReadsSet.1"
        sapi = SetAPI(self.__class__.serviceWizardURL, token=self.getContext()['token'],
                      service_ver=self.__class__.SetAPI_version)
        sapi.save_reads_set_v1({'workspace': ws_name1, 'output_object_name': set_obj_name,
                                'data': {'description': '', 'items': [{'ref': reads_obj_ref}]}})
        list_ret = self.getImpl().list_objects_with_sets(self.getContext(),
                                                         {"ws_name": ws_name1})[0]
        ret = list_ret['data']
        self.assertTrue(len(ret) > 0)
        set_count = 0
        for item in ret:
            self.assertTrue("object_info" in item)
            if "set_items" in item:
                set_count += 1
                set_items = item["set_items"]["set_items_info"]
                self.assertEqual(1, len(set_items))
        self.assertEqual(1, set_count)
        self.assertIn('data_palette_refs', list_ret)
        ws_id = self.getWsClient().get_workspace_info({"workspace": ws_name1})[0]
        ret2 = self.getImpl().list_objects_with_sets(self.getContext(),
                                                     {"ws_id": ws_id})[0]["data"]
        self.assertEqual(len(ret), len(ret2))
        type_filter = "KBaseSets.ReadsSet"
        ret3 = self.getImpl().list_objects_with_sets(self.getContext(),
                                                     {"types": [type_filter],
                                                     "workspaces": [str(ws_id)]})[0]["data"]
        self.assertTrue(len(ret3) > 0)
        for item in ret3:
            info = item['object_info']
            obj_type = info[2].split('-')[0]
            self.assertEqual(type_filter, obj_type)
        type_filter = "KBaseGenomes.Genome"
        ret4 = self.getImpl().list_objects_with_sets(self.getContext(),
                                                     {"types": [type_filter],
                                                     "workspaces": [str(ws_id)]})[0]["data"]
        self.assertTrue(len(ret4) == 0)

    def test_list_objects_meta(self):
        ws_name = self.createWs()
        reads_obj_ref = self.__class__.example_reads_ref
        target_name = "TestReads"
        self.getWsClient().copy_object({'from': {'ref': reads_obj_ref},
                                        'to': {'workspace': ws_name,
                                               'name': target_name}})

        ret = self.getImpl().list_objects_with_sets(self.getContext(),
                                                    {"ws_name": ws_name,
                                                     "includeMetadata": 0})[0]["data"]
        for item in ret:
            if 'set_items' not in item and 'dp_info' not in item:
                info = item.get("object_info", [])
                self.assertIsNone(info[10])

        ret = self.getImpl().list_objects_with_sets(self.getContext(),
                                                    {"ws_name": ws_name,
                                                     "includeMetadata": 1})[0]["data"]
        for item in ret:
            if 'set_items' not in item and 'dp_info' not in item:
                info = item.get("object_info", [])
                self.assertIsNotNone(info[10])

    def test_copy_narrative(self):
        ws = self.getWsClient()
        with open("/kb/module/test/data/narrative1.json", "r") as f1:
            nar_obj_data = json.load(f1)
        user_id = self.getContext()['user_id']
        ws_name = self.createWs()
        nar_obj_data['metadata']['creator'] = user_id
        nar_obj_data['metadata']['ws_name'] = ws_name
        nar_obj_data['metadata']['kbase']['creator'] = user_id
        nar_obj_data['metadata']['kbase']['ws_name'] = ws_name
        nar_obj_name = "Narrative." + str(int(round(time.time() * 1000)))
        nar_obj_type = "KBaseNarrative.Narrative-4.0"
        job_info = json.dumps({"queue_time": 0, "running": 0, "completed": 0,
                               "run_time": 0, "error": 0})
        nar_obj_meta = {"description": "",
                        "format": "ipynb",
                        "creator": user_id,
                        "job_info": job_info,
                        "data_dependencies": "[]",
                        "jupyter.markdown": "1",
                        "ws_name": ws_name,
                        "type": "KBaseNarrative.Narrative",
                        "name": "NarrativeCopyTest"}
        ws.save_objects({'workspace': ws_name, 'objects':
                         [{'type': nar_obj_type,
                           'data': nar_obj_data,
                           'name': nar_obj_name,
                           'meta': nar_obj_meta}]})
        # Adding DP object:
        reads_ref = self.__class__.example_reads_ref
        target_reads_name = "MyReads.copy.1"
        reads_info = ws.copy_object({'from': {'ref': reads_ref},
                                     'to': {'workspace': ws_name,
                                            'name': target_reads_name}})
        copy_nar_name = "NarrativeCopyTest - Copy"
        ret = self.getImpl().copy_narrative(self.getContext(),
                                            {'workspaceRef': ws_name + '/' + nar_obj_name,
                                             'newName': copy_nar_name})[0]
        copy_ws_id = ret['newWsId']
        copy_nar_id = ret['newNarId']
        try:
            copy_nar = ws.get_objects([{'ref': str(copy_ws_id) + '/' + str(copy_nar_id)}])[0]
            #print("Copy object: " + json.dumps(copy_nar, indent=4, sort_keys=True))
            copy_nar_data = copy_nar['data']
            # This is weird, so ws_name is the same as for old narrative:
            self.assertEqual(ws_name, copy_nar_data['metadata']['kbase']['ws_name'])
            # And here is proper new ws_name:
            self.assertNotEqual(ws_name, copy_nar_data['metadata']['ws_name'])
            self.assertEqual(copy_nar_name, copy_nar_data['metadata']['name'])
            ret = self.getImpl().list_objects_with_sets(self.getContext(),
                                                        {"ws_id": copy_ws_id})[0]["data"]
            dp_found = False
            for item in ret:
                obj_info = item["object_info"]
                if obj_info[7] == ws_name:
                    self.assertEqual(target_reads_name, obj_info[1])
                    self.assertTrue('dp_info' in item)
                    self.assertEqual(reads_info[6], obj_info[6])
                    self.assertEqual(reads_info[0], obj_info[0])
                    dp_found = True
                else:
                    object_type = obj_info[2].split('-')[0]
                    self.assertTrue(object_type != "KBaseFile.SingleEndLibrary",
                                    "Unexpected type: " + object_type)
            self.assertTrue(dp_found)
        finally:
            # Cleaning up new created workspace
            ws.delete_workspace({'id': copy_ws_id})
        #################################################################################
        # Now it's copy with refs in DataPalette
        reads_ws_name = self.__class__.example_ws_name
        reads_obj_name = self.__class__.example_reads_name
        reads_ref = reads_ws_name + '/' + reads_obj_name
        # This reads object should appear in Narrative copy as well:
        self.getImpl().copy_object(self.getContext(), {'ref': reads_ref,
                                                       'target_ws_name': ws_name})
        copy_nar_name = "NarrativeCopyTest - Copy2"
        ret = self.getImpl().copy_narrative(self.getContext(),
                                            {'workspaceRef': ws_name + '/' + nar_obj_name,
                                             'newName': copy_nar_name})[0]
        copy_ws_id = ret['newWsId']
        try:
            ret = self.getImpl().list_objects_with_sets(self.getContext(),
                                                        {"ws_id": copy_ws_id})[0]["data"]
            dp_found = False
            for item in ret:
                obj_info = item["object_info"]
                if obj_info[7] == reads_ws_name:
                    self.assertTrue('dp_info' in item)
                    self.assertTrue('ref' in item['dp_info'])
                    self.assertTrue('refs' in item['dp_info'])
                    self.assertEqual(str(copy_ws_id), item['dp_info']['ref'].split('/')[0])
                    self.assertEqual(reads_obj_name, obj_info[1])
                    dp_found = True
            self.assertTrue(dp_found)
        finally:
            # Cleaning up new created workspace
            ws.delete_workspace({'id': copy_ws_id})


    def test_create_new_narrative(self):
        import_ref = self.__class__.example_reads_ref
        ws = self.getWsClient()
        ret = self.getImpl().create_new_narrative(self.getContext(),
                                                  {"method": "AssemblyUtil/import_assembly_fasta_ftp",
                                                   "appparam": "0,param1,value1;0,param2,value2",
                                                   "copydata": import_ref})[0]
        try:
            self.assertTrue('narrativeInfo' in ret)
        finally:
            new_ws_id = ret['workspaceInfo']['id']
            ws.delete_workspace({'id': new_ws_id})

    def test_new_narrative_welcome(self):
        ws = self.getWsClient()
        narr_info = self.getImpl().create_new_narrative(self.getContext(), {'includeIntroCell': 1})[0]
        with open(self.intro_text_file) as f:
            intro_text = f.read()

        try:
            self.assertTrue('narrativeInfo' in narr_info)
            narr_obj = ws.get_objects([{'ref': narr_info['narrativeInfo']['ref']}])[0]
            cells = narr_obj['data']['cells']
            self.assertTrue(len(cells) > 0)
            self.assertEqual(str(cells[0]['source']), str(intro_text))
        finally:
            new_ws_id = narr_info['workspaceInfo']['id']
            ws.delete_workspace({'id': new_ws_id})

    def test_copy_object(self):
        # Reads
        example_ws = self.__class__.example_ws_name
        ws_name = self.createWs()
        import_ref = self.__class__.example_reads_ref
        ret = self.getImpl().copy_object(self.getContext(), {'ref': import_ref,
                                                             'target_ws_name': ws_name})
        self.assertEqual(example_ws, ret[0]['info']['ws'])
        # Let's check that we see reads copy in list_objects_with_sets
        ret = self.getImpl().list_objects_with_sets(self.getContext(),
                                                    {"ws_name": ws_name})[0]["data"]
        found = False
        for item in ret:
            obj_info = item["object_info"]
            if obj_info[7] == example_ws:
                self.assertTrue('dp_info' in item)
                found = True
        self.assertTrue(found)
        # Genome
        import_ref = self.__class__.example_genome_ref
        target_name = "MyGenome.1"
        ret = self.getImpl().copy_object(self.getContext(), {'ref': import_ref,
                                                             'target_ws_name': ws_name,
                                                             'target_name': target_name})
        self.assertEqual(target_name, ret[0]['info']['name'])

    def test_workspace_list_objects_iterator(self):
        ws_name = self.__class__.example_ws_name
        part_size = 10
        ws_info = self.getWsClient().get_workspace_info({'workspace': ws_name})
        max_obj_count = ws_info[4]
        min_obj_id = 1
        obj_count = 0
        while min_obj_id <= max_obj_count:
            max_obj_id = min_obj_id + 10000 - 1
            part = self.getWsClient().list_objects({'workspaces': [ws_name],
                                                    'minObjectID': min_obj_id,
                                                    'maxObjectID': max_obj_id})
            obj_count += len(part)
            min_obj_id += 10000
        obj_count2 = 0
        for info in WorkspaceListObjectsIterator(self.getWsClient(), ws_info_list=[ws_info],
                                                 part_size=part_size):
            self.assertEqual(11, len(info))
            obj_count2 += 1
        self.assertEqual(obj_count, obj_count2)

    def test_list_available_types(self):
        ws_name = self.__class__.example_ws_name
        type_stat = self.getImpl().list_available_types(self.getContext(),
                                                        {"workspaces": [ws_name]})[0]['type_stat']
        self.assertTrue("KBaseGenomes.Genome" in type_stat)
        self.assertTrue("KBaseFile.SingleEndLibrary" in type_stat)

    def test_unique_items(self):
        # Create original workspace with reads object + ReadsSet object
        ws_name1 = self.createWs()
        foft = FakeObjectsForTests(os.environ['SDK_CALLBACK_URL'])
        reads_obj_name = "test.reads.1"
        foft.create_fake_reads({'ws_name': ws_name1, 'obj_names': [reads_obj_name]})
        reads_obj_ref = ws_name1 + '/' + reads_obj_name
        set_obj_name = "test.reads_set.1"
        sapi = SetAPI(self.__class__.serviceWizardURL, token=self.getContext()['token'],
                      service_ver=self.__class__.SetAPI_version)
        sapi.save_reads_set_v1({'workspace': ws_name1, 'output_object_name': set_obj_name,
                                'data': {'description': '', 'items': [{'ref': reads_obj_ref}]}})
        set_obj_ref = ws_name1 + '/' + set_obj_name
        # Create workspace with DataPalette copy of Reads object and copy of ReadsSet
        ws_name2 = self.createWs()
        dps = DataPaletteService(self.__class__.serviceWizardURL, token=self.getContext()['token'],
                                 service_ver=self.__class__.DataPalette_version)
        dps.add_to_palette({'workspace': ws_name2, 'new_refs': [{'ref': reads_obj_ref},
                                                                {'ref': set_obj_ref}]})
        # Check if listing in both these workspaces at the same time gives unique items
        ret = self.getImpl().list_objects_with_sets(self.getContext(),
                                                    {"workspaces": [ws_name1, ws_name2]})[0]["data"]
        self.assertEqual(2, len(ret))

    def test_bulk_list(self):
        try:
            ids = []
            for ws_info in self.getWsClient().list_workspace_info({'perm': 'r', 'excludeGlobal': 1}):
                #ws_name_parts = ws_info[1].split(':')
                #if len(ws_name_parts) == 2 and ws_name_parts[1].isdigit():
                #    continue
                if ws_info[4] < 1000:
                    ids.append(str(ws_info[0]))
                    if len(ids) >= 100:
                        break
            print("Workspaces selected for bulk list_objects_with_sets: " + str(len(ids)))
            if len(ids) > 0:
                self.getImpl().list_objects_with_sets(self.getContext(), {'workspaces': [ids[0]]})
            NarrativeManager.DEBUG = False  #True
            t1 = time.time()
            ret = self.getImpl().list_objects_with_sets(self.getContext(), {'workspaces': ids})[0]["data"]
            print("Objects found: " + str(len(ret)) + ", time=" + str(time.time() - t1))
        finally:
            NarrativeManager.DEBUG = False
