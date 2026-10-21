// Read-only extraction using the installed game's Storm API ordinals.
using System;
using System.IO;
using System.Runtime.InteropServices;
class ExtractMapScript {
    const string Storm = @"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III\Storm.dll";
    [DllImport(Storm, EntryPoint="#266", CharSet=CharSet.Ansi)] static extern bool OpenArchive(string path,uint priority,uint flags,out IntPtr archive);
    [DllImport(Storm, EntryPoint="#268", CharSet=CharSet.Ansi)] static extern bool OpenFile(IntPtr archive,string name,uint scope,out IntPtr file);
    [DllImport(Storm, EntryPoint="#265")] static extern uint Size(IntPtr file,out uint high);
    [DllImport(Storm, EntryPoint="#269")] static extern bool Read(IntPtr file,byte[] buffer,uint length,out uint count,IntPtr overlapped);
    [DllImport(Storm, EntryPoint="#253")] static extern bool CloseFile(IntPtr file);
    [DllImport(Storm, EntryPoint="#252")] static extern bool CloseArchive(IntPtr archive);
    static int Main(string[] args) {
        if(args.Length!=3) {Console.Error.WriteLine("archive internal-name new-output");return 2;}
        IntPtr archive=IntPtr.Zero,file=IntPtr.Zero;
        try {
            if(!OpenArchive(Path.GetFullPath(args[0]),0,0,out archive)) throw new IOException("Open archive failed");
            if(!OpenFile(archive,args[1],0,out file)) throw new IOException("Open member failed");
            uint high;uint size=Size(file,out high);
            if(high!=0 || size>64*1024*1024) throw new IOException("Unexpected member size");
            byte[] bytes=new byte[size];uint count;
            if(!Read(file,bytes,size,out count,IntPtr.Zero) || count!=size) throw new IOException("Incomplete read");
            using(var output=new FileStream(args[2],FileMode.CreateNew,FileAccess.Write)) output.Write(bytes,0,bytes.Length);
            Console.WriteLine("Extracted {0} bytes",size);return 0;
        } finally {if(file!=IntPtr.Zero)CloseFile(file);if(archive!=IntPtr.Zero)CloseArchive(archive);}
    }
}
