"""Compatibility checks for the research map writer, not reconnect claims."""
import hashlib
import unittest

from native import build_state_probe_map as probe


class StateProbeMapTests(unittest.TestCase):
    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_rebind_reuses_serialized_hook_and_module_relative_addresses(self):
        source = probe.SOURCE.read_bytes()
        result = probe.build(source, probe.PROBES[10])
        _, _, script = probe.read_script(result[512:])
        self.assertEqual(len(result), len(source))
        globals_part = script.split(b'endglobals', 1)[0]
        self.assertIn(b'trigger LRFT=null', globals_part)
        hook = script.split(b'function FGCBO takes', 1)[1].split(b'endfunction', 1)[0]
        self.assertIn(b'if LRFT==null then\nset LRFT=CreateTrigger()', hook)
        self.assertIn(b'call OBVOO(GetHandleId(LRFT))', hook)
        rebind = script.split(b'function LRCH takes', 1)[1].split(b'endfunction', 1)[0]
        self.assertIn(b'set GVOO=CBH+LRVA', rebind)
        self.assertIn(b'set p=CBH+LRPA', rebind)
        self.assertNotIn(b'UnitAddAbility', rebind)
        self.assertNotIn(b'CreateTrigger', rebind)
        lrbt = script.split(b'function LRBT takes', 1)[1].split(b'endfunction', 1)[0]
        self.assertIn(b'call LRCH()', lrbt)
        self.assertNotIn(b'call HHGVO()', lrbt)
        # The original new-match initialization still discovers addresses.
        self.assertIn(b'call HHGVO()', script.split(b'function LRBT takes')[0])

    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_helper_callbacks_reuse_saved_triggers(self):
        result = probe.build(probe.SOURCE.read_bytes(), probe.PROBES[12])
        _, _, script = probe.read_script(result[512:])
        callback = script.split(b'function OBFCO takes', 1)[1].split(b'endfunction', 1)[0]
        self.assertIn(b'if LROT==null then', callback)
        self.assertIn(b'endif\ncall OCHVO(GetHandleId(LROT))\ncall OBFGO(GetHandleId(LRGT))', callback)
        self.assertEqual(callback.count(b'CreateTrigger()'), 2)
        for line in (b'trigger LROT=null', b'trigger LRGT=null'):
            self.assertIn(line, script.split(b'endglobals', 1)[0])

    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_camera_waits_for_post_load_player_remap_without_new_handles(self):
        result = probe.build(probe.SOURCE.read_bytes(), probe.PROBES[11])
        _, _, script = probe.read_script(result[512:])
        load = script.split(b'function LRBT takes', 1)[1].split(b'endfunction', 1)[0]
        timer = script.split(b'function OVGVO takes', 1)[1].split(b'endfunction', 1)[0]
        self.assertIn(b'set LRCP=true', load)
        self.assertNotIn(b'PanCameraToTimed', load)
        self.assertIn(b'if LRCP then\nset LRCP=false', timer)
        self.assertIn(b'GetOwningPlayer(CGCH[CHHV])==GetLocalPlayer()', timer)
        self.assertIn(b'PanCameraToTimed', timer)
        for mutation in (b'CreateTimer', b'SelectUnit', b'SetPlayerAlliance', b'GetRandom'):
            self.assertNotIn(mutation, timer)

    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_camera_load_is_local_and_has_no_new_timer_or_selection(self):
        result = probe.build(probe.SOURCE.read_bytes(), probe.PROBES[9])
        _, _, script = probe.read_script(result[512:])
        lrbt = script.split(b'function LRBT takes', 1)[1].split(b'endfunction', 1)[0]
        self.assertIn(b'GetOwningPlayer(CGCH[CHHV])==GetLocalPlayer()', lrbt)
        self.assertIn(b'call PanCameraToTimed(GetUnitX(CGCH[CHHV]),GetUnitY(CGCH[CHHV]),0)', lrbt)
        for mutation in (b'CreateTimer', b'SelectUnit', b'SetPlayerAlliance', b'GetRandom'):
            self.assertNotIn(mutation, lrbt)

    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_view_probe_preserves_archive_members_and_fog_policy(self):
        source = probe.SOURCE.read_bytes()
        result = probe.build(source, probe.PROBES[8])
        before, index, _ = probe.read_script(source[512:])
        _, _, script = probe.read_script(result[512:])
        self.assertEqual(len(source), len(result))
        callback = script.split(b'function LVPF takes', 1)[1].split(b'endfunction', 1)[0]
        self.assertIn(b'call FogEnable(IsFogEnabled())', callback)
        self.assertIn(b'call FogMaskEnable(IsFogMaskEnabled())', callback)
        self.assertNotIn(b'SetPlayerAlliance', callback)
        for i, entry in enumerate(before.block_table):
            if i != index and entry.flags & probe.mpyq.MPQ_FILE_EXISTS:
                start = 512 + entry.offset
                end = start + entry.archived_size
                self.assertEqual(source[start:end], result[start:end])

    def test_sector_cipher_matches_independent_reader_and_preserves_tail(self):
        archive = object.__new__(probe.mpyq.MPQArchive)
        for size in (0, 1, 3, 4, 7, 8, 31, 8193):
            source = bytes(i % 251 for i in range(size))
            for key in (0, 0xFFFFFFFF, 0x13572468):
                with self.subTest(size=size, key=key):
                    self.assertEqual(probe.decrypt(archive, probe.encrypt(archive, source, key), key), source)

    def test_refuses_unrecognized_archive(self):
        with self.assertRaisesRegex(AssertionError, 'Unsupported map'):
            probe.build(b'not the pinned LoD map')

    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_changes_only_one_script_without_growing_archive(self):
        source = probe.SOURCE.read_bytes()
        result = probe.build(source)
        self.assertEqual(len(result), len(source))
        before, index, script_before = probe.read_script(source[512:])
        after, _, script_after = probe.read_script(result[512:])
        self.assertEqual(script_before.replace(b'call ExecuteFunc("OOHCO")', b''), script_after)
        for i, entry in enumerate(before.block_table):
            if i == index or not entry.flags & probe.mpyq.MPQ_FILE_EXISTS:
                continue
            start = 512 + entry.offset
            end = start + entry.archived_size
            self.assertEqual(source[start:end], result[start:end], 'Other member changed: ' + str(i))
        self.assertEqual(hashlib.sha256(probe.SOURCE.read_bytes()).hexdigest(), probe.EXPECTED)

    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_probe3_reads_live_game_state_without_growing_archive(self):
        source = probe.SOURCE.read_bytes()
        result = probe.build(source, probe.PROBES[3])
        self.assertEqual(len(result), len(source))
        _, _, script = probe.read_script(result[512:])
        self.assertIn(b'return OBCC(OBCC(CBH+0xAB65F4)+28)-4', script)
        self.assertNotIn(b'TestPrintAllTimers takes', script)
        self.assertNotIn(b'call ExecuteFunc("OOHCO")', script)

    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_probe4_reruns_lod_bootstrap_on_load_without_growing_archive(self):
        source = probe.SOURCE.read_bytes()
        result = probe.build(source, probe.PROBES[4])
        self.assertEqual(len(result), len(source))
        _, _, script = probe.read_script(result[512:])
        self.assertIn(b'call TriggerRegisterGameEvent(t,EVENT_GAME_LOADED)\ncall TriggerAddAction(t,function LRBT)', script)
        lrbt = script[script.find(b'function LRBT'):script.find(b'function main takes')]
        for line in (b'set GHC=false', b'set VFF=true', b'set OGH=0', b'set GHVO=0', b'call BVBC()', b'call OVGBO(true)'):
            self.assertIn(line, lrbt)
        self.assertLess(lrbt.find(b'set CHBV=false'), lrbt.find(b'call BVBC()'))

    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_probe6_saves_arrays_empty_and_reruns_runtime_hooks(self):
        source = probe.SOURCE.read_bytes()
        result = probe.build(source, probe.PROBES[6])
        self.assertEqual(len(result), len(source))
        _, _, script = probe.read_script(result[512:])
        self.assertIn(b'call TriggerRegisterGameEvent(t,EVENT_GAME_SAVE)\ncall TriggerAddAction(t,function LSAV)', script)
        self.assertIn(b'if LoadInteger(HY,h,2)==OBVO then', script)
        lrbt = script[script.find(b'function LRBT'):script.find(b'function main takes')]
        self.assertIn(b'call FCVHG()\ncall HHGVO()', lrbt)
        self.assertNotIn(b'call HOVC(FGC,0xFFFF681C)', lrbt)
        self.assertIn(b'if GetTriggerEventId()==EVENT_GAME_TIMER_EXPIRED then\ncall FCFVG()', script)

    @unittest.skipUnless(probe.SOURCE.is_file(), 'Pinned local LoD fixture unavailable')
    def test_probe7_keeps_save_counter_patch_guarded(self):
        source = probe.SOURCE.read_bytes()
        result = probe.build(source, probe.PROBES[7])
        self.assertEqual(len(result), len(source))
        _, _, script = probe.read_script(result[512:])
        self.assertIn(b'if OBCC(CBH+0x43F088)==0x01508D52 then\ncall BBGC(CBH+0x43F088,0x00508D52,true,true)', script)
        self.assertIn(b'call TriggerAddAction(t,function LSAV)\ncall LSVN()', script)
        self.assertIn(b'call OVGBO(true)\ncall LSVN()\ncall FCVHG()', script)
