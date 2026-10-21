// Diagnostic debugger and experimental recovery probe for the pinned 1.26a binary.
// Breakpoints are in process memory only; on exit the owned child is terminated.
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

class CloseTrace {
    [StructLayout(LayoutKind.Sequential)] struct PI { public IntPtr process,thread; public uint pid,tid; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string app,StringBuilder cmd,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,IntPtr startup,out PI pi);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool WaitForDebugEvent(IntPtr ev,uint timeout);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool ContinueDebugEvent(uint pid,uint tid,uint status);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool DebugBreakProcess(IntPtr process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetThreadContext(IntPtr thread,IntPtr context);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetThreadContext(IntPtr thread,IntPtr context);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr p,IntPtr address,byte[] bytes,int size,out IntPtr count);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool WriteProcessMemory(IntPtr p,IntPtr address,byte[] bytes,int size,out IntPtr count);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool FlushInstructionCache(IntPtr p,IntPtr address,int size);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern uint GetFinalPathNameByHandle(IntPtr file,StringBuilder path,uint length,uint flags);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr handle,uint code);
    [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr process,IntPtr address,UIntPtr size,uint allocation,uint protection);
    static PI child; static StreamWriter log;
    static uint restoredArena;
    static int timerEvents,gameStateRebinds;
    static JavaScriptSerializer json=new JavaScriptSerializer();
    static void Emit(object value) { string line=json.Serialize(value); log.WriteLine(line); log.Flush(); Console.WriteLine(line); }
    static void Check(bool value) { if(!value) throw new Win32Exception(Marshal.GetLastWin32Error()); }
    static IntPtr Ptr(uint v) {return new IntPtr(unchecked((int)v));}
    static uint U(IntPtr p,int offset) {return unchecked((uint)Marshal.ReadInt32(p,offset));}
    static byte[] Read(uint address,int size) {byte[] b=new byte[size]; IntPtr n; Check(ReadProcessMemory(child.process,Ptr(address),b,size,out n)); if(n.ToInt32()!=size) throw new IOException("Short native read"); return b;}
    static string TryReadHex(uint address,int size) {try{return BitConverter.ToString(Read(address,size)).Replace("-","");}catch(Win32Exception){return null;}catch(IOException){return null;}}
    static uint ReadU32(uint address) {return BitConverter.ToUInt32(Read(address,4),0);}
    static Dictionary<string,uint> InspectLodGlobals(uint frame,uint caller,uint gameBase) {
        // Before 45d187 the native-call dispatcher stores its VM at EBP-0x0c.
        // That slot is overwritten before the native itself is called.
        // Inspect only; saved pointers must not be treated as valid allocations.
        if(caller!=gameBase+0x45d1b8) throw new IOException("Unexpected JASS native caller");
        uint vm=ReadU32(frame-12);
        Emit(new {event_name="lod_vm_candidate",frame=frame.ToString("x"),vm=vm.ToString("x"),frame_bytes=TryReadHex(frame-32,48),vm_fields=TryReadHex(vm+0x2850,48)});
        uint table=ReadU32(vm+0x285c);
        Emit(new {event_name="lod_table_candidate",table=table.ToString("x"),header=TryReadHex(table,40)});
        uint step=ReadU32(table+4),node=ReadU32(table+12);
        if(step>256 || (step&3)!=0) throw new IOException("Unexpected global table step");
        var wanted=new HashSet<string>(new string[]{"BOO","BGO","BVH","BFH","CGH","FHF","GBF","CHVV","CHCV","CHBV","CGOV","GHC","OCG","HOG","BBH","BGH","FFF","VGF","VFO","GHF","OVG","OBG","VGG","FGG"});
        var seen=new HashSet<uint>();var globals=new Dictionary<string,uint>();int found=0;
        while(node>0x10000 && node<0x80000000 && seen.Count<30000 && seen.Add(node)) {
            uint key=ReadU32(node+0x14);
            if(key<0x10000 || key>=0x80000000) throw new IOException("Invalid global key at node "+node.ToString("x")+" key "+key.ToString("x"));
            byte[] nameBytes=Read(key,64);int end=Array.IndexOf(nameBytes,(byte)0);
            if(end<0) throw new IOException("Unterminated global name");
            string name=Encoding.ASCII.GetString(nameBytes,0,end);
            if(globals.ContainsKey(name)) {
                Emit(new {event_name="duplicate_global_name",name=name,node=node.ToString("x"),previous=globals[name].ToString("x")});
                if(wanted.Contains(name)) throw new IOException("Ambiguous required global: "+name);
            } else globals.Add(name,node);
            if(wanted.Contains(name)) {
                uint value=ReadU32(node+0x20);
                Emit(new {event_name="lod_global_snapshot",name=name,node=node.ToString("x"),type=ReadU32(node+0x1c),array=ReadU32(node+0x18),value=value.ToString("x"),pointed_bytes=TryReadHex(value,32)});found++;
            }
            node=ReadU32(node+step+4);
        }
        Emit(new {event_name="lod_globals_inspected",vm=vm.ToString("x"),table=table.ToString("x"),step=step,visited=seen.Count,selected=found,terminal=node.ToString("x")});
        return globals;
    }
    static void WriteU32(uint address,uint value) {byte[] data=BitConverter.GetBytes(value);for(int i=0;i<4;i++) Write(address+(uint)i,data[i]);}
    static void RebindLodGlobals(Dictionary<string,uint> globals) {
        // Experimental bootstrap only. Does not relocate arbitrary game objects,
        // unit pointers, frame caches, callbacks, or other map allocations.
        string[] names={"OBVO","OBCO","OBBO","HOOO","HOHO","HOGO","HOFO","HOVO","HOCO","HHHO","HHGO","HHFO","HHVO","HHCO","HHBO","HGHO","HGGO","HGFO","HGVO","HGCO","HGBO","FGF","FFF","VOF","VGF","OGCO","OGBO","HFOO","OFHO","OFGO","HOBO","HHOO","GHCO","OFOO","FHOO","FHGO","HGOO","VOGO","FHHO","VOCO","CHVV","CHCV","VOVO"};
        uint oldArena=ReadU32(globals["OBVO"]+0x20);
        foreach(string name in names) {
            uint value=ReadU32(globals[name]+0x20);
            if(ReadU32(globals[name]+0x1c)!=4 || value<oldArena || value-oldArena>=50000) throw new IOException("Arena global mismatch: "+name);
        }
        foreach(string name in new string[]{"BOO","BGO"}) {
            uint obj=ReadU32(globals[name]+0x20);
            if(ReadU32(obj+8)!=0) throw new IOException("Expected empty forged array");
        }
        uint flags=ReadU32(globals["VFO"]+0x20);
        if(ReadU32(flags+8)!=26) throw new IOException("Unexpected trampoline flag count");
        IntPtr memory=VirtualAllocEx(child.process,IntPtr.Zero,new UIntPtr(50000),0x3000,0x40);
        Check(memory!=IntPtr.Zero);uint arena=unchecked((uint)memory.ToInt32());
        restoredArena=arena;
        foreach(string name in names) {
            uint value=ReadU32(globals[name]+0x20),replacement=arena+(value-oldArena);
            WriteU32(globals[name]+0x20,replacement);
            Emit(new {event_name="experimental_arena_global_relocated",name=name,old_value=value.ToString("x"),new_value=replacement.ToString("x")});
        }
        uint flagData=ReadU32(flags+12);
        for(uint i=0;i<26;i++) WriteU32(flagData+4*i,0);
        foreach(string name in new string[]{"BVH","BBH","BGH","FHF","OCG","HOG"}) WriteU32(globals[name]+0x20,0);
        foreach(string name in new string[]{"BOO","BGO"}) {
            uint obj=ReadU32(globals[name]+0x20);
            WriteU32(obj+4,0xffffffff);WriteU32(obj+8,0xffffffff);WriteU32(obj+12,0);
        }
        // LoD's init-only OVGBO(true) replaces the engine's own call to 0x4299e0
        // at 0x42fcd5 with "ret 4" (its 0.1s timer calls it instead). CCV and the
        // saved original bytes survive Load; the code patch itself does not.
        uint bov=ReadU32(globals["BOV"]+0x20);
        if(ReadU32(globals["CCV"]+0x20)!=0) {
            if(bov!=0x6f42fcd4 || ReadU32(bov)!=ReadU32(globals["BHV"]+0x20) || ReadU32(bov+4)!=ReadU32(globals["BGV"]+0x20)) throw new IOException("OVGBO patch site mismatch");
            WriteU32(bov,ReadU32(globals["BFV"]+0x20));WriteU32(bov+4,ReadU32(globals["BVV"]+0x20));
            Emit(new {event_name="experimental_lod_code_patch_reapplied",site=bov.ToString("x"),bytes=TryReadHex(bov,8)});
        }
        Emit(new {event_name="experimental_lod_bootstrap_rebound",old_arena=oldArena.ToString("x"),new_arena=arena.ToString("x"),warning="Other cached pointers and map patches remain unhandled; no reconnect claim"});
    }
    static void Write(uint address,byte value) {IntPtr n; Check(WriteProcessMemory(child.process,Ptr(address),new byte[]{value},1,out n)); if(n.ToInt32()!=1) throw new IOException("Short native write"); Check(FlushInstructionCache(child.process,Ptr(address),1));}
    static string FileName(IntPtr handle) {var b=new StringBuilder(1024); return GetFinalPathNameByHandle(handle,b,1024,0)>0?b.ToString():"";}
    static string Sha(string path) {using(var f=File.OpenRead(path)) using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(f)).Replace("-","").ToLowerInvariant();}
    static int Main(string[] args) {
        if(args.Length<2) { Console.WriteLine("CloseTrace.exe GAME_DIRECTORY JOURNAL [seconds] [--replay-probe] [RESTORE_MARKER]"); return 2; }
        if(IntPtr.Size!=4) throw new Exception("Compile this diagnostic as x86");
        if(Process.GetProcessesByName("war3").Length!=0) throw new Exception("Close existing Warcraft first");
        string game=Path.GetFullPath(args[0]);
        bool rebindProbe=args.Length>3 && args[3]=="--load-rebind-probe";
        bool loadMemoryProbe=args.Length>3 && (args[3]=="--load-memory-probe" || rebindProbe);
        bool timerTrace=loadMemoryProbe || (args.Length>3 && args[3]=="--fresh-timer-trace");
        bool vmProbe=args.Length>3 && args[3]=="--vm-probe"; int vmSamples=0;
        // Game-menu Save button predicates (function 0x3500a0); observation only.
        var menuSites=new Dictionary<uint,string>{{0x3500f2,"after_2f8fc0_enable"},{0x350115,"after_2f9020_disable"},{0x35014b,"player_state_270"},{0x350186,"after_53f160_disable"},{0x3501b4,"after_53ef80_keep"},{0x53efa0,"slot_record_2e0"},{0x53efd9,"slot_entry_3c"}};
        bool menuProbe=args.Length>3 && args[3]=="--menu-probe"; uint watchAddress=0; int watchHits=0;
        // Load probes take an optional SAVE_NAME SHA256 pair (default: measured LabProbeD).
        string fixture=loadMemoryProbe && args.Length>5?args[4]:"LabProbeD",fixtureSha=loadMemoryProbe && args.Length>5?args[5]:"adc0cbc6b834378027816a165f73515d5de13d05329d382db8c9fb7f4128dc7f";
        if(loadMemoryProbe && Sha(Path.Combine(game,@"Save\Multiplayer\"+fixture+".w3z"))!=fixtureSha) throw new Exception("Load probe requires a measured save fixture");
        string restoreMarker=args.Length>4 && !loadMemoryProbe?Path.GetFullPath(args[4]):null;
        if(restoreMarker!=null && File.Exists(restoreMarker)) throw new Exception("Restore marker must not already exist");
        if(Sha(Path.Combine(game,"game.dll"))!="6d21bd9a0f9fbc8446f455c9e89ac994fed68174426fe608fcb9baefd4dec53c") throw new Exception("Unsupported game.dll hash");
        log=new StreamWriter(new FileStream(args[1],FileMode.CreateNew,FileAccess.Write,FileShare.Read));
        var threads=new Dictionary<uint,IntPtr>(); var breaks=new Dictionary<uint,byte>(); var steps=new Dictionary<uint,uint>();
        var saveSites=new Dictionary<uint,string>{{0x3bbee0,"JASS_SaveGame"},{0x3bbe60,"JASS_LoadGame"},{0x3af8d0,"save_callee_candidate"},{0x3a4c70,"load_callee_candidate"},{0x443860,"save_file_reader_candidate"}};
        uint[] sites={0x6d9cca,0x6d9e93,0x6da65c,0x6da7dc,0x6dbd91,0x6dbdce,0x6dbe72,0x6dec7c,0x6e13a8,0x6e144b,0x6e14b4,0x6e17e9,0x6e1ae0,0x6e3e3e};
        IntPtr startup=Marshal.AllocHGlobal(68), ev=Marshal.AllocHGlobal(96), context=Marshal.AllocHGlobal(716);
        Marshal.Copy(new byte[68],0,startup,68); Marshal.WriteInt32(startup,68);
        bool alive=false, initialBreak=false, probeApplied=false, restoreRequested=false; uint gameBase=0; int memoryCalls=0;
        try {
            string exe=Path.Combine(game,"war3.exe");
            Check(CreateProcess(exe,new StringBuilder("\""+exe+"\""),IntPtr.Zero,IntPtr.Zero,false,2,IntPtr.Zero,game,startup,out child)); alive=true;
            Emit(new {event_name="debug_started",pid=child.pid,utc=DateTime.UtcNow.ToString("o")});
            var watch=Stopwatch.StartNew(); int seconds=args.Length>2?int.Parse(args[2]):240;
            while(watch.Elapsed.TotalSeconds<seconds && alive) {
                if(probeApplied && !restoreRequested && restoreMarker!=null && File.Exists(restoreMarker)) {
                    Check(DebugBreakProcess(child.process)); restoreRequested=true;
                }
                if(!WaitForDebugEvent(ev,250)) {int error=Marshal.GetLastWin32Error(); if(error==121) continue; throw new Win32Exception(error);}
                uint kind=U(ev,0),pid=U(ev,4),tid=U(ev,8),status=0x10002;
                if(kind==3) {threads[tid]=Ptr(U(ev,20)); if(U(ev,12)!=0) CloseHandle(Ptr(U(ev,12)));}
                if(kind==2) threads[tid]=Ptr(U(ev,12));
                if(kind==4) threads.Remove(tid);
                if(kind==5) {Emit(new {event_name="process_exit",exit_code=U(ev,12)});alive=false;}
                if(kind==6) {
                    IntPtr file=Ptr(U(ev,12)); string path=FileName(file); uint address=U(ev,16);
                    if(file!=IntPtr.Zero) CloseHandle(file);
                    if(path.EndsWith("\\game.dll",StringComparison.OrdinalIgnoreCase)) {
                        gameBase=address;
                        foreach(uint rva in sites) {
                            uint site=gameBase+rva; byte[] bytes=Read(site,6);
                            if(bytes[0]!=0xff || bytes[1]!=0x15 || BitConverter.ToUInt32(bytes,2)!=gameBase+0x86d86c) throw new Exception("Unexpected closesocket call bytes at "+site.ToString("x"));
                            breaks[site]=bytes[0]; Write(site,0xcc);
                        }
                        foreach(uint rva in new uint[]{0x6da2fd,0x6da754}) {
                            byte[] expected=rva==0x6da2fd?new byte[]{0xff,0xd2}:new byte[]{0x85,0xc0};
                            byte[] actual=Read(gameBase+rva,2);
                            if(actual[0]!=expected[0] || actual[1]!=expected[1]) throw new Exception("Unexpected parser probe instruction");
                            breaks[gameBase+rva]=actual[0]; Write(gameBase+rva,0xcc);
                        }
                        if(args.Length>3 && (args[3]=="--save-trace" || args[3]=="--save-array-probe" || loadMemoryProbe)) {
                            foreach(var site in saveSites) {
                                byte[] expected=(site.Key==0x3bbee0 || site.Key==0x3bbe60)?new byte[]{0x81,0xec,8,1,0,0}:new byte[]{0x6a,0xff,0x68};
                                byte[] actual=Read(gameBase+site.Key,expected.Length);
                                for(int i=0;i<expected.Length;i++) if(actual[i]!=expected[i]) throw new Exception("Save/load probe bytes differ");
                                breaks[gameBase+site.Key]=actual[0]; Write(gameBase+site.Key,0xcc);
                            }
                        }
                        if(timerTrace) {
                            // Trace the first engine call reached by the rebuilt map
                            // trampoline; this adds observation, not a fault bypass.
                            byte[] timerEntry=Read(gameBase+0x4299e0,7);
                            byte[] timerExpected={0xf6,0x81,0x90,0x02,0x00,0x00,0x02};
                            for(int i=0;i<timerExpected.Length;i++) if(timerEntry[i]!=timerExpected[i]) throw new Exception("Timer entry mismatch");
                            breaks[gameBase+0x4299e0]=timerEntry[0];Write(gameBase+0x4299e0,0xcc);
                        }
                        if(menuProbe) {
                            foreach(uint rva in menuSites.Keys) {byte b=Read(gameBase+rva,1)[0]; breaks[gameBase+rva]=b; Write(gameBase+rva,0xcc);}
                        }
                        if(vmProbe) {
                            // Observation only: compare the dispatcher's JASS VM with
                            // LoD's GFOC(id) chain [[[[CGH]+0x14]+0x90]+4*id].
                            byte[] dispatch=Read(gameBase+0x45d181,3);
                            if(dispatch[0]!=0x8b || dispatch[1]!=0x52 || dispatch[2]!=0x1c) throw new Exception("Native dispatcher mismatch");
                            breaks[gameBase+0x45d181]=dispatch[0];Write(gameBase+0x45d181,0xcc);
                        }
                        if(loadMemoryProbe) {
                            byte[] dispatch=Read(gameBase+0x45d181,3);
                            if(dispatch[0]!=0x8b || dispatch[1]!=0x52 || dispatch[2]!=0x1c) throw new Exception("Native dispatcher mismatch");
                            breaks[gameBase+0x45d181]=dispatch[0];Write(gameBase+0x45d181,0xcc);
                            // Reproduce only the two native stubs installed by LoD's
                            // HCOC. This is fixture-specific process-memory research,
                            // not an implementation of all map hooks or heap relocation.
                            foreach(uint rva in new uint[]{0x2dd050,0x2ddc10}) {
                                byte[] replacement=rva==0x2dd050 ? new byte[]{0x8b,0x44,0x24,0x04,0x8b,0x00,0xc3,0x90} : new byte[]{0x55,0x8b,0x6c,0x24,0x0c,0x8b,0x44,0x24,0x08,0x89,0x28,0x5d,0xc3,0x90};
                                byte[] original=Read(gameBase+rva,replacement.Length);
                                byte[] prefix={0x8b,0x0d,0x70,0x4e,0xab,0x6f};
                                if(gameBase!=0x6f000000) throw new Exception("Load probe requires preferred module base");
                                for(int i=0;i<prefix.Length;i++) if(original[i]!=prefix[i]) throw new Exception("Memory-native entry mismatch");
                                for(int i=0;i<replacement.Length;i++) Write(gameBase+rva+(uint)i,replacement[i]);
                                breaks[gameBase+rva]=replacement[0];Write(gameBase+rva,0xcc);
                                Emit(new {event_name="experimental_lod_memory_native",rva=rva.ToString("x"),original=BitConverter.ToString(original).Replace("-",""),replacement=BitConverter.ToString(replacement).Replace("-","")});
                            }
                        }
                        if(args.Length>3 && args[3]=="--save-array-probe") {
                            byte[] actual=Read(gameBase+0x429386,6);
                            byte[] expected={0x8b,0x7d,0x04,0x57,0x8b,0xd9};
                            for(int i=0;i<expected.Length;i++) if(actual[i]!=expected[i]) throw new Exception("Array serializer probe bytes differ");
                            breaks[gameBase+0x429389]=0x57;Write(gameBase+0x429389,0xcc);
                            Emit(new {event_name="experimental_array_save_probe_armed",warning="Writes empty payload for virtual memory arrays; load compatibility unproven"});
                        }
                        if(args.Length>3 && args[3]=="--replay-probe") {
                            byte[] expected={0x0f,0x85,0x7e,0xfe,0xff,0xff};
                            byte[] actual=Read(gameBase+0x67e704,6);
                            for(int i=0;i<6;i++) if(actual[i]!=expected[i]) throw new Exception("Historical echo probe byte mismatch");
                            // Recovery experiment: allow historical local actions to
                            // reach simulation when no matching locally sent action exists.
                            // Packet CRC and simulation synchronization are unchanged.
                            Write(gameBase+0x67e704,0x90); Write(gameBase+0x67e705,0xe9);
                            probeApplied=true;
                            Emit(new {event_name="experimental_historical_echo_probe",rva="67e704",original="0f857efeffff",replacement="90e97efeffff",restore_marker=restoreMarker});
                        }
                        Emit(new {event_name="trace_armed",game_base=gameBase.ToString("x"),count=breaks.Count});
                    }
                }
                if(kind==1) {
                    uint code=U(ev,12),address=U(ev,24); status=0x80010001;
                    if(code==0x80000003 && breaks.ContainsKey(address)) {
                        Marshal.Copy(new byte[716],0,context,716); Marshal.WriteInt32(context,0x10007);
                        Check(GetThreadContext(threads[tid],context)); uint sp=U(context,196);
                        uint rva=address-gameBase;
                        if(timerTrace && rva==0x4299e0) {
                            uint obj=U(context,172);
                            uint currentState=ReadU32(gameBase+0xab65f4);
                            // LoD's OVGFO takes the CGameState from the first slot of
                            // InstanceGenerator<CGameState> (0xab6ea4). After Load that
                            // slot is the destroyed pre-load object on the free list;
                            // the engine's own reference is CGameWar3+0x1c (getter 0x3a8060).
                            uint live=currentState==0?0:ReadU32(currentState+0x1c);
                            bool stale=rebindProbe && live!=0 && obj!=live && obj==ReadU32(gameBase+0xab6eb4)
                                && ReadU32(live)==gameBase+0x94f6e4 && ReadU32(obj)!=gameBase+0x94f6e4;
                            if(stale) Marshal.WriteInt32(context,172,unchecked((int)live));
                            if(timerEvents++<8 || (stale && gameStateRebinds%200==0))
                                Emit(new {event_name="lod_timer_engine_entry",utc=DateTime.UtcNow.ToString("o"),ecx=obj.ToString("x"),edx=U(context,168).ToString("x"),object_bytes=TryReadHex(obj,64),object_flags=TryReadHex(obj+0x280,32),timer_list=TryReadHex(gameBase+0xab6ea4,40),current_state=currentState.ToString("x"),current_state_bytes=TryReadHex(currentState,64),live_game_state=live.ToString("x"),experimental_rebound_to_live=stale,rebinds=gameStateRebinds,trampoline=restoredArena==0?null:TryReadHex(restoredArena+1000,32),stack=TryReadHex(sp,32)});
                            if(stale) gameStateRebinds++;
                        } else if(menuProbe && menuSites.ContainsKey(rva)) {
                            uint eax=U(context,176);
                            Emit(new {event_name="menu_save_predicate",utc=DateTime.UtcNow.ToString("o"),site=menuSites[rva],eax=eax.ToString("x"),player_270=rva==0x35014b?TryReadHex(eax+0x270,4):null,
                                record=rva==0x53efa0?TryReadHex(U(context,160)+eax+0x2d0,0x40):null,game_type=rva==0x53efa0?TryReadHex(eax+0x2288,4):null,
                                entry=rva==0x53efd9?TryReadHex(eax,0x48):null});
                            if(rva==0x53efd9 && watchAddress==0 && ReadU32(eax+0x3c)==0) {
                                // Hardware write watch (DR0, 4 bytes) on the save-lock field of
                                // the local player's entry, on this game thread only.
                                IntPtr dc=Marshal.AllocHGlobal(716); Marshal.Copy(new byte[716],0,dc,716); Marshal.WriteInt32(dc,0x10010);
                                Check(GetThreadContext(threads[tid],dc)); watchAddress=eax+0x3c;
                                Marshal.WriteInt32(dc,4,unchecked((int)watchAddress)); Marshal.WriteInt32(dc,24,0x000D0001);
                                Check(SetThreadContext(threads[tid],dc)); Marshal.FreeHGlobal(dc);
                                Emit(new {event_name="save_lock_watch_armed",address=watchAddress.ToString("x"),tid=tid});
                            }
                        } else if(vmProbe && rva==0x45d181) {
                            if(vmSamples++%2000==0 && vmSamples<20000) {
                                uint frame=U(context,180),vm=ReadU32(frame-12),list=0;
                                try {list=ReadU32(ReadU32(ReadU32(gameBase+0xada848)+0x14)+0x90);} catch(Exception) {}
                                Emit(new {event_name="vm_probe",vm=vm.ToString("x"),gfoc_list=list.ToString("x"),gfoc=list==0?null:TryReadHex(list,24),table=TryReadHex(vm+0x285c,4)});
                            }
                        } else if(loadMemoryProbe && rva==0x45d181) {
                            if(memoryCalls==0 && ReadU32(U(context,168)+0x1c)==gameBase+0x2dd050)
                            {
                                var globals=InspectLodGlobals(U(context,180),gameBase+0x45d1b8,gameBase);
                                if(rebindProbe) RebindLodGlobals(globals);
                            }
                        } else if(loadMemoryProbe && (rva==0x2dd050 || rva==0x2ddc10)) {
                            byte[] parameters=Read(sp,12);uint target=BitConverter.ToUInt32(parameters,4);
                            if(memoryCalls++<128) Emit(new {event_name="lod_memory_native_call",utc=DateTime.UtcNow.ToString("o"),operation=rva==0x2dd050?"read":"write",target=target.ToString("x"),value=BitConverter.ToUInt32(parameters,8).ToString("x"),target_bytes=TryReadHex(target,16),caller=BitConverter.ToUInt32(parameters,0).ToString("x")});
                        } else if(rva==0x429389) {
                            byte[] header=Read(U(context,180),12);
                            uint caller=BitConverter.ToUInt32(Read(sp+16,4),0);
                            if(U(context,156)==0xffffffff && BitConverter.ToUInt32(header,0)==0xffffffff && BitConverter.ToUInt32(header,8)==0 && caller==gameBase+0x459a66) {
                                // Diagnostic only: the map's forged memory arrays cannot
                                // be serialized as 0xffffffff integers at address zero.
                                // Change only the serializer's count register, not the
                                // live array header. Rebinding after load is separate work.
                                Marshal.WriteInt32(context,156,0);
                                Emit(new {event_name="experimental_virtual_array_saved_empty",utc=DateTime.UtcNow.ToString("o"),header_address=U(context,180).ToString("x"),header=BitConverter.ToString(header).Replace("-","")});
                            }
                        } else if(saveSites.ContainsKey(rva)) {
                            Emit(new {event_name="save_load_entry",utc=DateTime.UtcNow.ToString("o"),site=saveSites[rva],rva=rva.ToString("x"),tid=tid,ecx=U(context,172).ToString("x"),edx=U(context,168).ToString("x"),stack=BitConverter.ToString(Read(sp,64)).Replace("-","")});
                        } else if(rva==0x6da2fd) {
                            byte[] stack=Read(sp,28); uint buffer=BitConverter.ToUInt32(stack,16),size=BitConverter.ToUInt32(stack,20);
                            if(size>=4 && size<=65535) {
                                byte[] packet=Read(buffer,(int)Math.Min(size,64));
                                if(packet[0]==0xf7 && packet[1]==0x0c && size>6)
                                    Emit(new {event_name="action_parser_call",utc=DateTime.UtcNow.ToString("o"),callback=U(context,168).ToString("x"),size=size,packet=BitConverter.ToString(packet).Replace("-","")});
                            }
                        } else if(rva==0x6da754) {
                            if(U(context,176)==0) Emit(new {event_name="parser_rejected",utc=DateTime.UtcNow.ToString("o"),stack=BitConverter.ToString(Read(sp,64)).Replace("-","")});
                        } else Emit(new {event_name="closesocket",utc=DateTime.UtcNow.ToString("o"),tid=tid,rva=rva.ToString("x"),esp=sp.ToString("x"),ebp=U(context,180).ToString("x"),ecx=U(context,172).ToString("x"),stack=BitConverter.ToString(Read(sp,128)).Replace("-","")});
                        Write(address,breaks[address]); Marshal.WriteInt32(context,184,unchecked((int)address)); Marshal.WriteInt32(context,192,unchecked((int)(U(context,192)|0x100)));
                        Check(SetThreadContext(threads[tid],context)); steps[tid]=address;status=0x10002;
                    } else if(code==0x80000004 && watchAddress!=0 && !steps.ContainsKey(tid)) {
                        IntPtr dc=Marshal.AllocHGlobal(716); Marshal.Copy(new byte[716],0,dc,716); Marshal.WriteInt32(dc,0x10017);
                        Check(GetThreadContext(threads[tid],dc));
                        uint eip=U(dc,184),sp2=U(dc,196);
                        if(watchHits++<12) Emit(new {event_name="save_lock_write",utc=DateTime.UtcNow.ToString("o"),eip=eip.ToString("x"),rva=(eip-gameBase).ToString("x"),dr6=U(dc,20).ToString("x"),value=TryReadHex(watchAddress,12),stack=TryReadHex(sp2,96)});
                        Marshal.WriteInt32(dc,20,0); Check(SetThreadContext(threads[tid],dc)); Marshal.FreeHGlobal(dc); status=0x10002;
                    } else if(code==0x80000004 && steps.ContainsKey(tid)) {
                        Marshal.Copy(new byte[716],0,context,716); Marshal.WriteInt32(context,0x10007);
                        Check(GetThreadContext(threads[tid],context));
                        Marshal.WriteInt32(context,192,unchecked((int)(U(context,192)&~0x100u)));
                        Check(SetThreadContext(threads[tid],context));
                        Write(steps[tid],0xcc); steps.Remove(tid); status=0x10002;
                    } else if(code==0x80000003 && restoreRequested) {
                        // DebugBreakProcess stops every thread before restoring code.
                        // Never change a running thread's two-byte instruction prefix.
                        byte[] expected={0x90,0xe9,0x7e,0xfe,0xff,0xff};
                        byte[] actual=Read(gameBase+0x67e704,6);
                        for(int i=0;i<6;i++) if(actual[i]!=expected[i]) throw new Exception("Restore probe byte mismatch");
                        Write(gameBase+0x67e704,0x0f); Write(gameBase+0x67e705,0x85);
                        probeApplied=false; restoreRequested=false; status=0x10002;
                        Emit(new {event_name="historical_echo_validation_restored",utc=DateTime.UtcNow.ToString("o")});
                    } else if(code==0x80000003 && !initialBreak) {initialBreak=true;status=0x10002;}
                    else {
                        Emit(new {event_name="exception",code=code.ToString("x"),address=address.ToString("x"),first_chance=U(ev,92)});
                        if(code==0xc0000005 && threads.ContainsKey(tid)) {
                            Marshal.Copy(new byte[716],0,context,716); Marshal.WriteInt32(context,0x10007);
                            Check(GetThreadContext(threads[tid],context));
                            Emit(new {event_name="access_violation_context",utc=DateTime.UtcNow.ToString("o"),tid=tid,
                                operation=U(ev,32),fault_address=U(ev,36).ToString("x"),
                                eax=U(context,176).ToString("x"),ebx=U(context,164).ToString("x"),
                                ecx=U(context,172).ToString("x"),edx=U(context,168).ToString("x"),
                                esi=U(context,160).ToString("x"),edi=U(context,156).ToString("x"),
                                ebp=U(context,180).ToString("x"),esp=U(context,196).ToString("x"),
                                instruction=TryReadHex(address,24),stack=TryReadHex(U(context,196),256),
                                ebp_memory=TryReadHex(U(context,180),32)});
                        }
                    }
                }
                Check(ContinueDebugEvent(pid,tid,status));
            }
            return 0;
        } catch(Exception ex) {Emit(new {event_name="trace_error",detail=ex.ToString()}); return 1;}
        finally {
            if(alive) TerminateProcess(child.process,0);
            if(child.thread!=IntPtr.Zero) CloseHandle(child.thread); if(child.process!=IntPtr.Zero) CloseHandle(child.process);
            Marshal.FreeHGlobal(startup);Marshal.FreeHGlobal(ev);Marshal.FreeHGlobal(context);log.Dispose();
        }
    }
}
