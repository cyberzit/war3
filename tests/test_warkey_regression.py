import ctypes
import unittest
from unittest.mock import patch
from core import warkey as w

class WarKeyRegression(unittest.TestCase):
    def setUp(self):
        self.engine=w.AegisWarKey({ord('U'):w.VK_NUMPAD7},{ord('Y'):ord('Q')})
        self.focus=patch.object(w,'war3_foreground',return_value=(10,20)).start()
        self.mods=patch.object(w.user32,'GetAsyncKeyState',return_value=0).start()
        self.next=patch.object(w.user32,'CallNextHookEx',return_value=0).start()
        self.send=patch.object(w,'send_hardware_scancode',return_value=True).start()
        self.addCleanup(patch.stopall)
    def key(self,v,down=True,extra=0):
        k=w.KBDLLHOOKSTRUCT(v,0,0,0,extra)
        return self.engine._hook_callback(0,w.WM_KEYDOWN if down else w.WM_KEYUP,ctypes.addressof(k))
    def tap(self,v):
        self.key(v);self.key(v,False)
    def test_native_input_layout(self):
        self.assertEqual(ctypes.sizeof(w.INPUT),40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)
        self.assertEqual(ctypes.sizeof(w.KBDLLHOOKSTRUCT),24 if ctypes.sizeof(ctypes.c_void_p)==8 else 20)
    def test_inventory_and_skill(self):
        self.tap(ord('U'));self.tap(ord('Y'))
        self.assertEqual(self.send.call_args_list,[unittest.mock.call(w.VK_NUMPAD7),unittest.mock.call(w.VK_NUMPAD7,key_up=True),unittest.mock.call(ord('Q')),unittest.mock.call(ord('Q'),key_up=True)])
    def test_chat_submit_and_cancel(self):
        self.tap(w.VK_RETURN);self.tap(ord('U'));self.send.assert_not_called()
        self.tap(w.VK_RETURN);self.tap(ord('U'));self.assertTrue(self.send.called)
        self.send.reset_mock();self.tap(w.VK_RETURN);self.tap(w.VK_ESCAPE);self.tap(ord('Y'));self.assertTrue(self.send.called)
    def test_enter_repeat(self):
        self.key(w.VK_RETURN);self.assertEqual(self.key(w.VK_RETURN),1)
        self.assertTrue(self.engine.chat_active)
        self.key(w.VK_RETURN,False);self.tap(w.VK_RETURN);self.assertFalse(self.engine.chat_active)
    def test_chat_survives_focus_switch(self):
        self.tap(w.VK_RETURN);self.focus.return_value=None;self.tap(ord('U'))
        self.focus.return_value=(10,20);self.tap(ord('U'));self.send.assert_not_called()
        self.tap(w.VK_ESCAPE);self.tap(ord('U'));self.assertTrue(self.send.called)
    def test_other_apps_transparent(self):
        self.focus.return_value=None;self.tap(ord('U'));self.tap(w.VK_RETURN);self.send.assert_not_called()
    def test_ctrl_f5_does_not_disable(self):
        self.mods.return_value=0x8000;self.tap(w.VK_F5);self.assertTrue(self.engine.enabled)
        self.mods.return_value=0;self.tap(ord('U'));self.assertTrue(self.send.called)
    def test_original_key_passes_on_injection_failure(self):
        self.send.return_value=False;self.assertEqual(self.key(ord('U')),0)
        self.assertEqual(self.key(ord('U'),False),0)
    def test_release_after_mapping_changes(self):
        self.key(ord('U'));self.engine.inv_mapping={};self.key(ord('U'),False)
        self.send.assert_called_with(w.VK_NUMPAD7,key_up=True)
    def test_own_injection_not_recursed(self):
        self.key(ord('U'),extra=w.AEGIS_EXTRA_INFO);self.send.assert_not_called()
    def test_alt_chords_not_remapped(self):
        self.mods.return_value=0x8000;self.assertEqual(self.key(ord('U')),0);self.send.assert_not_called()
    def test_chat_open_releases_held_target(self):
        self.key(ord('U'));self.tap(w.VK_RETURN);self.send.assert_called_with(w.VK_NUMPAD7,key_up=True)

    def test_ctrl_enter_tracks_chat(self):
        self.mods.side_effect=lambda key: 0x8000 if key==w.VK_CONTROL else 0
        self.tap(w.VK_RETURN)
        self.assertTrue(self.engine.chat_active)
        self.mods.side_effect=None;self.mods.return_value=0
        self.tap(ord('U'));self.send.assert_not_called()
    def test_tab_can_be_configured(self):
        self.engine.inv_mapping={9:w.VK_NUMPAD7}
        self.tap(9);self.send.assert_called_with(w.VK_NUMPAD7,key_up=True)
    def test_repeated_key_keeps_original_target(self):
        self.key(ord('U'));self.engine.inv_mapping={ord('U'):w.VK_NUMPAD8}
        self.key(ord('U'));self.key(ord('U'),False)
        self.assertEqual([c.args[0] for c in self.send.call_args_list],[w.VK_NUMPAD7]*3)

    def test_access_denied_does_not_swallow_keyboard(self):
        self.focus.side_effect=PermissionError('Access denied')
        self.assertEqual(self.key(ord('U')),0)
        self.send.assert_not_called()
        self.assertEqual(self.engine.last_error,'Access denied')

class ProcessIdentityRegression(unittest.TestCase):
    def test_process_identity_without_open_process(self):
        import os
        with patch.object(w.kernel32,'OpenProcess',side_effect=AssertionError('Must not open protected processes')):
            self.assertIn(w.process_name(os.getpid()),('python.exe','pythonw.exe'))
    def test_invalid_snapshot_fails_cleanly(self):
        with patch.object(w.kernel32,'CreateToolhelp32Snapshot',return_value=ctypes.c_void_p(-1).value):
            with self.assertRaises(OSError):w.process_name(0x7ffffffe)
    def test_foreground_requires_actual_game_process(self):
        def game_class(hwnd,buf,size):
            buf.value='Warcraft III';return len(buf.value)
        def pid_for_window(hwnd,ptr):
            ctypes.cast(ptr,ctypes.POINTER(w.wintypes.DWORD)).contents.value=123
        with patch.object(w.user32,'GetForegroundWindow',return_value=10), patch.object(w.user32,'GetClassNameW',side_effect=game_class), patch.object(w.user32,'GetWindowThreadProcessId',side_effect=pid_for_window), patch.object(w,'process_name',return_value='editor.exe') as name:
            self.assertIsNone(w.war3_foreground())
            name.return_value='war3.exe'
            self.assertEqual(w.war3_foreground(),(10,123))

if __name__=='__main__':unittest.main()
