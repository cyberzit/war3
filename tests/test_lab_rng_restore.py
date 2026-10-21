import copy
import unittest
from tools.lab_rng_restore import digest, transfer_plan, auxiliary_plan
from tools.lab_checksum_report import reconstruct


class RngRestoreTests(unittest.TestCase):
    def setUp(self):
        def state(pid, player, data):
            components = [0] * 64
            components[3] = digest(data)
            return {'process_id':pid, 'sync_manager_candidates':[{'fields':{'0x1c70':12425}}], 'sync_trace':{'records':[{
                'sequence':10,'clock_ms':12325,'local_player':player,
                'random_streams':data.hex(),'components':components}]}}
        self.a=state(11,1,bytes(range(180))*2)
        self.b=state(22,7,bytes(360))
        self.command={'target_pid':22,'target_sequence':10,'clock_ms':12325,'current_clock_ms':12425}

    def test_copies_only_complete_real_rng_state(self):
        a,b=copy.deepcopy(self.a),copy.deepcopy(self.b)
        before,after=transfer_plan(a,b,self.command)
        self.assertEqual(before,bytes(360))
        self.assertEqual(after,bytes(range(180))*2)
        self.assertEqual((a,b),(self.a,self.b))

    def test_rejects_stale_sequence_clock_and_wrong_process(self):
        for key,value in [('target_pid',99),('target_sequence',9),('clock_ms',12300),('current_clock_ms',12325)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                transfer_plan(self.a,self.b,{**self.command,key:value})

    def test_rejects_wrong_donor_time_size_and_digest(self):
        for key,value in [('clock_ms',12300),('random_streams','00'*359),('random_streams','00'*360)]:
            a=copy.deepcopy(self.a);a['sync_trace']['records'][-1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                transfer_plan(a,self.b,self.command)

    def test_auxiliary_requires_native_check_reconstruction(self):
        for snapshot,raw in ((self.a, bytes(range(8))), (self.b, bytes(8))):
            snapshot['sync_auxiliary_state'] = raw.hex()
            snapshot['sync_components'] = {'threads':[{'components':[{'slot':3}]}]}
            row=snapshot['sync_trace']['records'][-1]
            row.update(full_agent_hash=0,handle_free=100,handle_count=110,handle_serial=111)
            row['checksum']=reconstruct(row,[3],raw)
        original=copy.deepcopy((self.a,self.b))
        self.assertEqual(auxiliary_plan(self.a,self.b),(bytes(8),bytes(range(8))))
        self.assertEqual((self.a,self.b),original)
        row=self.b['sync_trace']['records'][-1]
        row.update(auxiliary_state=bytes(8).hex(),auxiliary_digest=0)
        self.assertEqual(auxiliary_plan(self.a,self.b),(bytes(8),bytes(range(8))))
        self.b['sync_auxiliary_state']='01'*8
        with self.assertRaises(ValueError):
            auxiliary_plan(self.a,self.b)
