import copy
import struct
import unittest
from tools.lab_allocator_graph import ACTIVE, END, free_chain, relocate_listeners


def detail(index, serial, pointer):
    words = [0]*32
    words[3:7] = [0x5e6c6973, 0x6072746c, index, serial]
    words[18:21] = [0xd01b7, 0x20090400, 0xbdcccccd]
    owner, prop = [0]*32, [0]*32
    owner[5:7], prop[5:7] = [10, 10], [11, 11]
    encode = lambda values: struct.pack('<32I', *values).hex()
    return {'vtable_rva':'0x952b6c','address':hex(pointer),'header':encode(words),
            'listener_links':{'0x30':{'header':encode(owner)},'0x40':{'header':encode(prop)}}}


class AllocatorGraphTests(unittest.TestCase):
    def setUp(self):
        self.a = {'sync_allocator_graph':{'count':3,'head':2,'serial':12,
            'entries':[[ACTIVE,100],[ACTIVE,200],[END,0]],'free_chain':[2]},
            'sync_object_details':{'1':detail(1,5,200)}}
        self.b = {'sync_allocator_graph':{'count':3,'head':1,'serial':15,
            'entries':[[ACTIVE,400],[END,0],[ACTIVE,600]],'free_chain':[1]},
            'sync_object_details':{'2':detail(2,14,600)}}

    def test_relocation_preserves_graph_and_live_object_pointer(self):
        before = copy.deepcopy((self.a,self.b))
        graph,moves=relocate_listeners(self.a,self.b)
        self.assertEqual(graph['entries'],[[ACTIVE,400],[ACTIVE,600],[END,0]])
        self.assertEqual(graph['free_chain'],[2])
        self.assertEqual(graph['serial'],15)
        self.assertEqual(moves[0]['serial'],5)
        self.assertEqual((self.a,self.b),before)

    def test_rejects_cycle_active_free_and_unreachable_free(self):
        for entries,head in (([[0,0]],0),([[ACTIVE,100]],0),([[END,0]],END)):
            with self.assertRaises(ValueError):free_chain(entries,head)

    def test_rejects_occupied_destination_or_wrong_owner(self):
        self.b['sync_allocator_graph']['entries'][1]=[ACTIVE,700]
        self.b['sync_allocator_graph'].update(head=END,free_chain=[])
        with self.assertRaises(ValueError):relocate_listeners(self.a,self.b)
        self.setUp()
        raw=bytearray.fromhex(self.b['sync_object_details']['2']['listener_links']['0x30']['header'])
        struct.pack_into('<I',raw,0x14,99)
        self.b['sync_object_details']['2']['listener_links']['0x30']['header']=raw.hex()
        with self.assertRaises(ValueError):relocate_listeners(self.a,self.b)
