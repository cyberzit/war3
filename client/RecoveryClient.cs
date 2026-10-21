using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

// Local prototype. Network recovery is not yet integrated or verified.
class RecoveryClient : Form {
    TextBox game = new TextBox(); CheckBox enabled = new CheckBox();
    Label status = new Label(); ComboBox[] keys = new ComboBox[6];
    int[] targets = {103,104,100,101,97,98}; // inventory: numpad 7,8,4,5,1,2
    int[] sources = new int[6]; bool[] held = new bool[6];
    uint gamePid; bool chatting; IntPtr hook; HookProc callback;
    string settings = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "LoDRecovery", "keys.txt");
    delegate IntPtr HookProc(int code, IntPtr message, IntPtr data);
    [StructLayout(LayoutKind.Sequential)] struct KeyData { public uint vk, scan, flags, time; public UIntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct KeyboardInput { public ushort vk, scan; public uint flags, time; public UIntPtr extra; }
    [StructLayout(LayoutKind.Explicit)] struct InputUnion {
        [FieldOffset(0)] public KeyboardInput keyboard;
        [FieldOffset(0)] public MouseInput mouse;
    }
    [StructLayout(LayoutKind.Sequential)] struct MouseInput { public int x,y; public uint data,flags,time; public UIntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct Input { public uint type; public InputUnion value; }
    [DllImport("user32.dll", SetLastError=true)] static extern IntPtr SetWindowsHookEx(int kind, HookProc cb, IntPtr module, uint thread);
    [DllImport("kernel32.dll", CharSet=CharSet.Auto)] static extern IntPtr GetModuleHandle(string name);
    [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr handle);
    [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr h,int c,IntPtr m,IntPtr d);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window,out uint pid);
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint count,Input[] input,int size);
    bool Send(int key,bool up) {
        Input input=new Input(); input.type=1; input.value.keyboard.vk=(ushort)key;
        input.value.keyboard.flags=up?2u:0u;
        return SendInput(1,new Input[]{input},Marshal.SizeOf(typeof(Input)))==1;
    }
    void Release() { for(int i=0;i<6;i++) if(held[i]) { Send(targets[i],true); held[i]=false; } }
    IntPtr HandleKey(int code,IntPtr message,IntPtr data) {
        if(code<0) return CallNextHookEx(hook,code,message,data);
        KeyData key=(KeyData)Marshal.PtrToStructure(data,typeof(KeyData));
        if((key.flags&16)!=0) return CallNextHookEx(hook,code,message,data);
        bool down=message.ToInt64()==0x100 || message.ToInt64()==0x104;
        bool up=message.ToInt64()==0x101 || message.ToInt64()==0x105;
        uint pid; GetWindowThreadProcessId(GetForegroundWindow(),out pid);
        if(!enabled.Checked || gamePid==0 || pid!=gamePid) {
            Release(); return CallNextHookEx(hook,code,message,data);
        }
        if(down && key.vk==123) { enabled.Checked=false; return new IntPtr(1); } // F12 off
        if(down && key.vk==13) { chatting=!chatting; Release(); }
        if(down && key.vk==27) chatting=false;
        for(int i=0;i<6;i++) {
            if(key.vk!=sources[i]) continue;
            if(up && held[i]) { Send(targets[i],true); held[i]=false; return new IntPtr(1); }
            if(down && !chatting && GetAsyncKeyState(17)>=0 && GetAsyncKeyState(18)>=0 && GetAsyncKeyState(16)>=0) {
                if(Send(targets[i],false)) { held[i]=true; return new IntPtr(1); }
            }
        }
        return CallNextHookEx(hook,code,message,data);
    }
    RecoveryClient() {
        Text="LoD Client — туршилтын хувилбар"; Width=580; Height=420;
        FormBorderStyle=FormBorderStyle.FixedDialog; MaximizeBox=false;
        var title=new Label { Left=20,Top=15,Width=520,Height=42,Text="Товчны тохиргооны туршилт.\nFatal error reconnect хараахан бэлэн болоогүй." }; Controls.Add(title);
        game.SetBounds(20,65,435,25); Controls.Add(game);
        string bundled=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","Game","war3.exe"));
        if(File.Exists(bundled)) game.Text=bundled;
        var browse=new Button {Left=460,Top=63,Width=85,Text="Тоглоом"}; Controls.Add(browse);
        browse.Click+=delegate { using(var dialog=new OpenFileDialog {Filter="Warcraft III|war3.exe"}) if(dialog.ShowDialog()==DialogResult.OK) game.Text=dialog.FileName; };
        for(int i=0;i<6;i++) {
            Controls.Add(new Label {Left=20+(i%2)*260,Top=105+(i/2)*40,Width=125,Text="Item "+(i+1)});
            keys[i]=new ComboBox {Left=145+(i%2)*260,Top=100+(i/2)*40,Width=100,DropDownStyle=ComboBoxStyle.DropDownList};
            for(char c='A';c<='Z';c++) keys[i].Items.Add(c.ToString());
            keys[i].SelectedItem=new string[]{"Z","X","C","V","B","N"}[i]; Controls.Add(keys[i]);
        }
        enabled.SetBounds(20,230,520,25); enabled.Text="Товч солихыг идэвхжүүлэх (F12: унтраах)"; Controls.Add(enabled);
        enabled.CheckedChanged+=delegate {
            Release(); chatting=false;
            if(enabled.Checked) {
                for(int i=0;i<6;i++) { sources[i]=keys[i].Text[0]; for(int j=0;j<i;j++) if(sources[j]==sources[i]) { enabled.Checked=false; status.Text="Давхардсан товч сонгож болохгүй."; return; } }
            }
            foreach(var box in keys) box.Enabled=!enabled.Checked;
        };
        var launch=new Button {Left=20,Top=270,Width=180,Text="Warcraft эхлүүлэх"}; Controls.Add(launch);
        launch.Click+=delegate {
            try {
                if(Process.GetProcessesByName("war3").Length>0) throw new Exception("Нээлттэй Warcraft-аа эхлээд хаана уу.");
                if(!File.Exists(game.Text) || !String.Equals(Path.GetFileName(game.Text),"war3.exe",StringComparison.OrdinalIgnoreCase)) throw new Exception("war3.exe файлаа сонгоно уу.");
                var process=Process.Start(new ProcessStartInfo(game.Text){WorkingDirectory=Path.GetDirectoryName(game.Text),UseShellExecute=false});
                gamePid=(uint)process.Id; chatting=false; status.Text="Warcraft эхэлсэн. Enter: чат, F12: товч солилт унтарна.";
                Directory.CreateDirectory(Path.GetDirectoryName(settings));
                string[] lines=new string[7]; lines[0]=game.Text; for(int i=0;i<6;i++) lines[i+1]=keys[i].Text; File.WriteAllLines(settings,lines);
            } catch(Exception ex) {status.Text=ex.Message;}
        };
        status.SetBounds(20,315,520,55); status.Text="Товч солилт анхнаасаа унтраалттай. Чат нээлттэй үед бүү идэвхжүүл."; Controls.Add(status);
        if(File.Exists(settings)) { try { var lines=File.ReadAllLines(settings); game.Text=lines[0]; for(int i=0;i<6;i++) if(lines.Length>i+1 && keys[i].Items.Contains(lines[i+1])) keys[i].SelectedItem=lines[i+1]; } catch(IOException){} }
        callback=HandleKey; hook=SetWindowsHookEx(13,callback,GetModuleHandle(null),0);
        if(hook==IntPtr.Zero) { enabled.Enabled=false; status.Text="Товч солих үйлчилгээг эхлүүлж чадсангүй."; }
        FormClosed+=delegate { Release(); if(hook!=IntPtr.Zero) UnhookWindowsHookEx(hook); };
        var timer=new Timer {Interval=100}; timer.Tick+=delegate {uint pid; GetWindowThreadProcessId(GetForegroundWindow(),out pid); if(pid!=gamePid) Release();}; timer.Start();
    }
    [STAThread] static void Main() {Application.EnableVisualStyles(); Application.Run(new RecoveryClient());}
}
