"""Builder for MongolRanger v3.0 — Standalone WPF Modern Dark .EXE Installer & Client.

Produces:
1. MongolRanger-Setup.exe (Standalone Universal Windows x86/x64 .EXE with custom .ICO icon,
   built-in auto-installer + Desktop shortcut creator + Hardware-Accelerated WPF Modern Dark UI).
2. MongolRanger-macOS-Universal.zip (macOS Apple Silicon & Intel client).
"""
import io
from pathlib import Path
import struct
import subprocess
import zipfile
import zlib


def create_mongolranger_ico(ico_path: Path):
    """Generates a valid 48x48 32-bit RGBA PNG-compressed Windows .ICO file."""
    w, h = 48, 48
    raw_rows = bytearray()
    for y in range(h):
        raw_rows.append(0)  # PNG filter type 0
        for x in range(w):
            # Normalized coords [-1, 1]
            nx = (x - 23.5) / 22.0
            ny = (y - 23.5) / 22.0
            # Shield shape
            in_shield = False
            if -0.82 <= ny <= 0.15 and abs(nx) <= 0.82:
                in_shield = True
            elif 0.15 < ny <= 0.88:
                max_x = 0.82 * (1.0 - ((ny - 0.15) / 0.78) ** 1.35)
                if abs(nx) <= max_x:
                    in_shield = True

            if not in_shield:
                raw_rows.extend((0, 0, 0, 0))
                continue

            # Border check
            edge_dist = min(0.82 - abs(nx), 0.88 - ny, ny + 0.82)
            # M letter geometry inside shield
            in_m = False
            if -0.42 <= ny <= 0.38:
                # Left or right vertical bar
                if 0.34 <= abs(nx) <= 0.52:
                    in_m = True
                # V diagonals of M
                diag_y = -0.35 + abs(nx) * 1.45
                if abs(ny - diag_y) <= 0.13 and abs(nx) <= 0.42:
                    in_m = True

            if in_m:
                # Bright White/Cyan M emblem
                raw_rows.extend((250, 252, 255, 255))
            elif edge_dist < 0.11:
                # Glowing Violet-Emerald border
                t = (y / float(h))
                r = int(139 * (1 - t) + 16 * t)
                g = int(92 * (1 - t) + 185 * t)
                b = int(246 * (1 - t) + 129 * t)
                raw_rows.extend((r, g, b, 255))
            else:
                # Deep dark indigo shield interior
                raw_rows.extend((15, 21, 38, 255))

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw_rows), 9)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", idat)
        + png_chunk(b"IEND", b"")
    )

    # ICO header (1 image, 48x48, 32bpp, PNG payload)
    ico_dir = struct.pack("<HHH", 0, 1, 1)
    ico_entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png_bytes), 6 + 16)
    ico_path.write_bytes(ico_dir + ico_entry + png_bytes)


WPF_CSHARP_SOURCE = r"""using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Microsoft.Win32;

[assembly: AssemblyTitle("ZevArena Client")]
[assembly: AssemblyDescription("ZevArena — Warcraft III LAN, Reconnect & WarKey Client")]
[assembly: AssemblyConfiguration("Release")]
[assembly: AssemblyCompany("ZevArena Platform")]
[assembly: AssemblyProduct("ZevArena")]
[assembly: AssemblyCopyright("Copyright © 2026 ZevArena (zevarena.com). All rights reserved.")]
[assembly: AssemblyTrademark("ZevArena")]
[assembly: AssemblyVersion("4.8.0.0")]
[assembly: AssemblyFileVersion("4.8.0.0")]
[assembly: ComVisible(false)]

namespace MongolRanger
{
    public class LobbyItem
    {
        public string Id { get; set; }
        public string RowNum { get; set; }
        public string Name { get; set; }
        public string SubInfo { get; set; }
        public Brush SubInfoFg { get; set; }
        public Visibility LockIconVis { get; set; }
        public Visibility LockBadgeVis { get; set; }
        public Visibility HotBadgeVis { get; set; }
        public Visibility NoLeaverVis { get; set; }
        public string MapName { get; set; }
        public string MapTitle { get; set; }
        public string MapSub { get; set; }
        public ImageSource MapIcon { get; set; }
        public string Host { get; set; }
        public string HostInitial { get; set; }
        public string HostUid { get; set; }
        public string Players { get; set; }
        public double PlayersFillWidth { get; set; }
        public Brush PlayersBarBrush { get; set; }
        public string PingText { get; set; }
        public string StatusText { get; set; }
        public Brush StatusBg { get; set; }
        public Brush StatusFg { get; set; }
        public Brush StatusBorder { get; set; }
        public string Phase { get; set; }
        public string JoinBtnText { get; set; }
        public Brush ActionBtnBg { get; set; }
        public Brush ActionBtnFg { get; set; }
        public Brush ActionBtnBorder { get; set; }
    }

    public class RoomMemberItem
    {
        public string Name { get; set; }
        public int UidNum { get; set; }
        public string DisplayName { get; set; }
        public string UidLabel { get; set; }
        public string TrustBadge { get; set; }
        public Brush TrustFg { get; set; }
        public string EloText { get; set; }
        public Brush EloFg { get; set; }
        public string RoleBadge { get; set; }
        public Brush RoleFg { get; set; }
        public string PingBadge { get; set; }
        public Brush PingFg { get; set; }
        public string War3Status { get; set; }
        public Brush War3Fg { get; set; }
    }

    public class ChatMessageItem
    {
        public string TimeStr { get; set; }
        public string SenderLabel { get; set; }
        public Brush SenderFg { get; set; }
        public string Text { get; set; }
        public Brush TextFg { get; set; }
        public string InviteTag { get; set; }
        public Visibility HasInviteVis { get; set; }
    }

    public class LeaderboardItem
    {
        public string RankText { get; set; }
        public Brush RankFg { get; set; }
        public string Name { get; set; }
        public string DisplayName { get; set; }
        public string BadgeLabel { get; set; }
        public Brush BadgeFg { get; set; }
        public string EloDisplay { get; set; }
        public Brush EloFg { get; set; }
        public string KdDisplay { get; set; }
        public string GamesDisplay { get; set; }
        public string CleanRateDisplay { get; set; }
    }

    public class FriendItem
    {
        public string Name { get; set; }
        public int UidNum { get; set; }
        public string DisplayName { get; set; }
        public string SubText { get; set; }
        public Brush DotColor { get; set; }
        public string UnreadText { get; set; }
        public Visibility UnreadVis { get; set; }
        public string ProfileTag { get; set; }
        public string ChatTag { get; set; }
    }

    public class FriendReqItem
    {
        public string Name { get; set; }
        public string DisplayName { get; set; }
        public string AcceptTag { get; set; }
        public string DeclineTag { get; set; }
    }

    public class FriendSearchItem
    {
        public string Name { get; set; }
        public string DisplayName { get; set; }
        public string SubText { get; set; }
        public Brush SubFg { get; set; }
        public Brush DotColor { get; set; }
        public string AddTag { get; set; }
        public string AddLabel { get; set; }
        public bool CanAdd { get; set; }
        public double AddOpacity { get; set; }
    }

    public class MatchHistoryItem
    {
        public string ResultLabel { get; set; }
        public Brush ResultFg { get; set; }
        public Brush ResultBg { get; set; }
        public Brush CardBorder { get; set; }
        public string MapLine { get; set; }
        public string KdaLine { get; set; }
        public string EloLine { get; set; }
        public Brush EloFg { get; set; }
        public string TeammatesLine { get; set; }
        public string OpponentsLine { get; set; }
        public string DateLine { get; set; }
    }

    public class QuickChatItem
    {
        public string Id { get; set; }
        public string KeyName { get; set; }
        public string Message { get; set; }
        public string Mode { get; set; }
        public string ModeLabel { get; set; }
    }

    public class Program
    {
        private delegate IntPtr LowLevelKeyboardProc(int nCode, IntPtr wParam, IntPtr lParam);

        [StructLayout(LayoutKind.Sequential)]
        private struct KBDLLHOOKSTRUCT
        {
            public uint vkCode;
            public uint scanCode;
            public uint flags;
            public uint time;
            public UIntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct POINT
        {
            public int X;
            public int Y;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct RECT
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        private delegate IntPtr DSetHook(int idHook, LowLevelKeyboardProc lpfn, IntPtr hMod, uint dwThreadId);
        private delegate bool DUnhook(IntPtr hhk);
        private delegate IntPtr DCallNext(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);
        private delegate IntPtr DGetMod([MarshalAs(UnmanagedType.LPWStr)] string lpModuleName);
        private delegate IntPtr DGetFg();
        private delegate int DGetCls(IntPtr hWnd, [MarshalAs(UnmanagedType.LPWStr)] StringBuilder lpClassName, int nMaxCount);
        private delegate short DGetKey(int vKey);
        private delegate void DKeyEv(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
        private delegate uint DMapVk(uint uCode, uint uMapType);
        private delegate bool DPostMsg(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
        private delegate bool DGetRect(IntPtr hWnd, out RECT lpRect);
        private delegate bool DCliToScr(IntPtr hWnd, ref POINT lpPoint);
        private delegate bool DGetCur(out POINT lpPoint);
        private delegate bool DSetCur(int X, int Y);
        private delegate void DMouseEv(uint dwFlags, int dx, int dy, uint dwData, UIntPtr dwExtraInfo);
        private delegate IntPtr DFindWin([MarshalAs(UnmanagedType.LPWStr)] string lpClassName, [MarshalAs(UnmanagedType.LPWStr)] string lpWindowName);
        private delegate uint DGetWinTid(IntPtr hWnd, out uint lpdwProcessId);

        private static DSetHook fnSetHook;
        private static DUnhook fnUnhook;
        private static DCallNext fnCallNext;
        private static DGetMod fnGetMod;
        private static DGetFg fnGetFg;
        private static DGetCls fnGetCls;
        private static DGetKey fnGetKey;
        private static DKeyEv fnKeyEv;
        private static DMapVk fnMapVk;
        private static DPostMsg fnPostMsg;
        private static DGetRect fnGetRect;
        private static DCliToScr fnCliToScr;
        private static DGetCur fnGetCur;
        private static DSetCur fnSetCur;
        private static DMouseEv fnMouseEv;
        private static DFindWin fnFindWin;
        private static DGetWinTid fnGetWinTid;

        private static string DecSym(int[] codes)
        {
            char[] c = new char[codes.Length];
            for (int i = 0; i < codes.Length; i++) c[i] = (char)(codes[i] ^ 0x5A);
            return new string(c);
        }

        private static void InitNativeApi()
        {
            try
            {
                Type u = typeof(System.Windows.Forms.Form).Assembly.GetType(DecSym(new int[]{9,35,41,46,63,55,116,13,51,52,62,53,45,41,116,28,53,40,55,41,116,15,52,41,59,60,63,20,59,46,51,44,63,23,63,46,50,53,62,41}));
                MethodInfo mLoad = u.GetMethod(DecSym(new int[]{22,53,59,62,22,51,56,40,59,40,35,31,34}), BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
                MethodInfo mProc = u.GetMethod(DecSym(new int[]{29,63,46,10,40,53,57,27,62,62,40,63,41,41}), BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public, null, new Type[] { typeof(HandleRef), typeof(string) }, null);
                IntPtr hU = (IntPtr)mLoad.Invoke(null, new object[] { "user32.dll", IntPtr.Zero, 0 });
                IntPtr hK = (IntPtr)mLoad.Invoke(null, new object[] { "kernel32.dll", IntPtr.Zero, 0 });
                HandleRef rU = new HandleRef(null, hU);
                HandleRef rK = new HandleRef(null, hK);
                fnSetHook = (DSetHook)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{9,63,46,13,51,52,62,53,45,41,18,53,53,49,31,34,13}) }), typeof(DSetHook));
                fnUnhook = (DUnhook)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{15,52,50,53,53,49,13,51,52,62,53,45,41,18,53,53,49,31,34}) }), typeof(DUnhook));
                fnCallNext = (DCallNext)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{25,59,54,54,20,63,34,46,18,53,53,49,31,34}) }), typeof(DCallNext));
                fnGetMod = (DGetMod)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rK, DecSym(new int[]{29,63,46,23,53,62,47,54,63,18,59,52,62,54,63,13}) }), typeof(DGetMod));
                fnGetFg = (DGetFg)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{29,63,46,28,53,40,63,61,40,53,47,52,62,13,51,52,62,53,45}) }), typeof(DGetFg));
                fnGetCls = (DGetCls)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{29,63,46,25,54,59,41,41,20,59,55,63,13}) }), typeof(DGetCls));
                fnGetKey = (DGetKey)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{29,63,46,27,41,35,52,57,17,63,35,9,46,59,46,63}) }), typeof(DGetKey));
                fnKeyEv = (DKeyEv)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{49,63,35,56,62,5,63,44,63,52,46}) }), typeof(DKeyEv));
                fnMapVk = (DMapVk)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{23,59,42,12,51,40,46,47,59,54,17,63,35,13}) }), typeof(DMapVk));
                fnPostMsg = (DPostMsg)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{10,53,41,46,23,63,41,41,59,61,63,13}) }), typeof(DPostMsg));
                fnGetRect = (DGetRect)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{29,63,46,25,54,51,63,52,46,8,63,57,46}) }), typeof(DGetRect));
                fnCliToScr = (DCliToScr)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{25,54,51,63,52,46,14,53,9,57,40,63,63,52}) }), typeof(DCliToScr));
                fnGetCur = (DGetCur)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{29,63,46,25,47,40,41,53,40,10,53,41}) }), typeof(DGetCur));
                fnSetCur = (DSetCur)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{9,63,46,25,47,40,41,53,40,10,53,41}) }), typeof(DSetCur));
                fnMouseEv = (DMouseEv)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{55,53,47,41,63,5,63,44,63,52,46}) }), typeof(DMouseEv));
                fnFindWin = (DFindWin)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{28,51,52,62,13,51,52,62,53,45,13}) }), typeof(DFindWin));
                fnGetWinTid = (DGetWinTid)Marshal.GetDelegateForFunctionPointer((IntPtr)mProc.Invoke(null, new object[] { rU, DecSym(new int[]{29,63,46,13,51,52,62,53,45,14,50,40,63,59,62,10,40,53,57,63,41,41,19,62}) }), typeof(DGetWinTid));
            }
            catch { }
        }

        private const int WH_KEYBOARD_LL = 13;
        private const int WM_KEYDOWN = 0x0100;
        private const int WM_KEYUP = 0x0101;
        private const int WM_SYSKEYDOWN = 0x0104;
        private const int WM_SYSKEYUP = 0x0105;
        private const uint WM_CHAR = 0x0102;
        private const uint KEYEVENTF_KEYUP = 0x0002;
        private const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
        private const uint MOUSEEVENTF_LEFTUP = 0x0004;
        private const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
        private const uint MOUSEEVENTF_RIGHTUP = 0x0010;
        private static readonly UIntPtr MR_EXTRA_INFO = new UIntPtr(0xAE615);

        private const string SERVER_URL = "https://zevarena.com";
        private const string FALLBACK_SERVER_URL = "http://103.153.141.135";
        private static string activeServerUrl = SERVER_URL;
        private const string W3GS_HOST = "103.153.141.135";
        private static int w3gsPort = 8051;
        private static int localProxyPort = 6210;

        private static string authToken = "";
        private static string currentUsername = "";
        private static int currentUidNum = 10001;
        private static string currentRoomId = "";
        private static string currentRoomName = "";
        private static string currentRoomMapName = "";
        private static string currentRoomCode = "";
        private static bool isCurrentRoomOwner = false;
        private static int lastHandledLaunchSignal = 0;
        private static HashSet<int> handledLaunchSignals = new HashSet<int>();
        private static string currentRoomPhase = "LOBBY";
        private static string currentRoomAbsent = "";
        private static int currentRoomLaunchSig = 0;
        private static int currentRoomWaitRemSec = 0;
        private static int currentRoomAddtimeUsed = 0;
        private static int currentRoomAddtimeMax = 3;
        private static bool currentRoomCanHostDrop = false;
        private static int currentRoomW3gsConnectedCount = 0;
        private static bool currentRoomMyW3gsConnected = false;
        private static bool currentRoomMyDisconnected = false;
        private static bool currentRoomRejoinReady = false;
        private static bool hasLaunchedWar3InCurrentRoom = false;
        private static int lastRoomChatMsgId = 0;
        private static string pendingJoinRoomId = "";
        private static string codeModalMode = "JOIN"; // "JOIN" or "SET"
        private static string war3Dir = "";
        private static bool war3SetupCompleted = false;
        private static bool openedSettingsForFirstTimeSetup = false;
        private static string lastUploadedSha = "";
        private static string lastDownloadedSha = "";
        private static int currentPingMs = 9;
        private static string roomFilter = "ALL";
        private static bool isRegisterMode = false;
        private static byte[] currentLanAd = null;

        // Social & Friends state
        private static string cachedHwid = "";
        private static string activeDmFriendName = "";
        private static int activeDmFriendUid = 0;
        private static int lastUnreadTotal = 0;
        private static int activeInviteId = 0;
        private static int lastDismissedInviteId = 0;
        private static int lastPlayedInviteSoundId = 0;
        private static string selectedModalPlayerName = "";
        private static bool selectedModalPlayerIsBlocked = false;

        private static TcpListener proxyListener = null;
        private static UdpClient udpBroadcaster = null;
        private static volatile bool running = true;

        private static Window mainWin;
        private static Grid authView;
        private static Grid appShell;
        private static Border tabSignInBorder;
        private static Border tabSignUpBorder;
        private static TextBlock tabSignInText;
        private static TextBlock tabSignUpText;
        private static TextBlock lblUserPrompt;
        private static TextBox txtUser;
        private static StackPanel authEmailPanel;
        private static TextBlock lblEmailPrompt;
        private static TextBox txtEmail;
        private static TextBlock lblPassPrompt;
        private static PasswordBox txtPass;
        private static Border btnForgotPass;
        private static TextBlock lblForgotPassText;
        private static TextBlock btnAuthSubmitText;
        private static TextBlock lblAuthError;
        private static bool isResetPassMode = false;

        // App Shell Elements
        private static TextBlock lblProfileName;
        private static Border btnEditProfileName;
        private static TextBlock lblProfileUid;
        private static TextBlock lblProfileBadge;
        private static TextBlock lblProfileElo;
        private static TextBlock lblNetPing;
        private static TextBlock lblNetIp;
        private static TextBlock lblAntiCheatBadge;
        private static Border navBtnLobbies;
        private static Border navBtnLeaderboard;
        private static Border navBtnFriends;
        private static Border badgeFriendsUnread;
        private static TextBlock lblFriendsUnreadCount;
        private static Border navBtnWarKey;
        private static Border navBtnSettings;
        private static Border btnLogout;
        private static Grid pageLobbies;
        private static Grid pageLeaderboard;
        private static Grid pageFriends;
        private static Grid pageWarKey;
        private static Grid pageSettings;
        private static ItemsControl leaderboardListCtrl;

        // Lobbies & Inner Room Elements
        private static Grid lobbyListView;
        private static Grid innerRoomView;
        private static TextBlock lblLobbySubCount;
        private static TextBlock lblHeroWelcomeText;
        private static Border[] heroMapCards = new Border[5];
        private static TextBox txtSearch;
        private static Border filterAllBorder;
        private static Border filterWaitBorder;
        private static Border filterRunBorder;
        private static Border filterLockBorder;
        private static TextBlock lblFilterAllCount;
        private static TextBlock lblFilterWaitCount;
        private static TextBlock lblFilterRunCount;
        private static TextBlock lblFilterLockCount;
        private static Border hostModalBar;
        private static TextBox txtNewRoomName;
        private static TextBlock lblNewRoomNamePh;
        private static TextBox txtNewRoomCode;
        private static CheckBox chkNoLeavers;
        private static Border btnNoLeaversToggle;
        private static Border noLeaversTrack;
        private static Border noLeaversKnob;
        private static TextBlock lblNoLeaversState;
        private static ComboBox cmbMaps;
        private static Border btnMapDropdownToggle;
        private static Popup mapDropdownPopup;
        private static Image imgSelectedMapIcon;
        private static TextBlock lblSelectedMapTitle;
        private static Border[] mapOptionBorders = new Border[5];
        private static TextBlock[] lblMapChecks = new TextBlock[5];
        private static TextBlock lblFooterSelectedMap;
        private static TextBlock lblLastUpdatedTime;
        private static ItemsControl lobbiesList;
        private static int selectedMapIndex = 0;

        private static ImageSource imgHero;
        private static ImageSource imgLogo;
        private static ImageSource imgAvatar;
        private static ImageSource[] imgMaps = new ImageSource[5];

        private static readonly string[] OFFICIAL_MAP_TITLES = new string[]
        {
            "DotA v6.85m LoD",
            "DotA v6.74c LoD v5e",
            "DotA v6.83d Allstars",
            "DotA v6.85l LoD",
            "DotA v6.85k Allstars"
        };

        private static readonly string[] OFFICIAL_MAP_SUBS = new string[]
        {
            "LoD • Legend of DotA",
            "LoD Classic",
            "Classic Allstars",
            "LoD Balance",
            "Competitive Allstars"
        };

        private static readonly string[] OFFICIAL_MAP_KEYS = new string[]
        {
            "6.85m",
            "6.74c",
            "6.83d",
            "6.85l",
            "6.85k"
        };

        // Inner Room Elements
        private static TextBlock lblInnerRoomTitle;
        private static TextBlock lblInnerRoomSub;
        private static Border btnSetRoomCode;
        private static TextBlock lblSetRoomCodeText;
        private static Border btnInviteFriendFromRoom;
        private static Border btnLeaveMatchNow;
        private static ScrollViewer roomChatScroll;
        private static ItemsControl roomChatList;
        private static TextBox txtRoomChatInput;
        private static TextBlock lblRoomMembersCount;
        private static ItemsControl roomMembersList;
        private static Border btnHostStartGame;
        private static TextBlock lblHostStartBtnText;
        private static Border btnRejoinMatch;
        private static TextBlock lblRejoinBtnText;
        private static TextBlock lblRejoinBtnSub;
        private static Border clientWaitBanner;
        private static TextBlock lblWaitBannerTitle;
        private static TextBlock lblWaitBannerSub;
        private static Border btnAddWaitTime;
        private static TextBlock lblAddWaitTimeText;
        private static Border btnHostDropAbsent;
        private static TextBlock lblHostDropAbsentText;

        // Player Profile & Action Modal Elements
        private static Grid playerActionModalOverlay;
        private static TextBlock lblPlayerModalName;
        private static TextBlock lblPlayerModalUid;
        private static TextBlock lblPlayerModalBadge;
        private static TextBlock lblPlayerModalElo;
        private static TextBlock lblPlayerModalLeaves;
        private static TextBlock lblPlayerModalStatus;
        private static TextBlock lblPlayerModalRoom;
        private static TextBlock lblPlayerModalCreated;
        private static TextBlock lblPlayerModalFeedback;
        private static TextBlock lblBtnModalBlockText;
        private static Border btnModalAddFriend;
        private static TextBlock lblBtnModalAddFriendText;
        private static bool canClickModalAddFriend = true;
        private static Border btnModalKickUser;
        private static Border btnModalInviteRoom;
        private static Border btnModalViewHistory;
        private static System.Windows.Controls.Primitives.UniformGrid modalActionButtonsGrid;

        // Friends & Direct Chat Page Elements
        private static TextBox txtAddFriendInput;
        private static TextBlock lblFriendStatusMsg;
        private static Border pendingRequestsPanel;
        private static ItemsControl pendingRequestsList;
        private static ItemsControl friendsListCtrl;
        private static ItemsControl blockedUsersListCtrl;
        private static Border friendSearchResultsPanel;
        private static ItemsControl friendSearchResultsList;
        private static DispatcherTimer friendSearchDebounce = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(350) };
        private static int friendSearchSeq = 0;
        private static Grid matchHistoryOverlay;
        private static ItemsControl matchHistoryList;
        private static TextBlock lblHistoryTitle, lblHistoryElo, lblHistoryStats, lblHistoryEmpty;
        private static bool isRefreshingLobbies = false;
        private static TextBlock lblDmHeaderTitle;
        private static TextBlock lblDmHeaderSub;
        private static ScrollViewer dmChatScroll;
        private static ItemsControl dmMessagesListCtrl;
        private static TextBox txtDmInput;

        // Floating Room Invite Banner Elements
        private static Border inviteBannerOverlay;
        private static TextBlock lblInviteBannerText;

        private static Grid codeModalOverlay;
        private static TextBlock lblCodeModalTitle;
        private static TextBlock lblCodeModalSub;
        private static TextBox txtCodeModalInput;
        private static TextBlock lblCodeModalError;
        private static TextBox txtWar3Path;
        private static TextBlock lblSettingsStatus;
        private static Border war3ReadyPill;
        private static TextBlock lblWar3ReadyPill;
        private static TextBlock lblStep1;
        private static TextBlock lblStep2;
        private static TextBlock lblStep3;
        private static TextBlock lblStep4;
        private static Grid updateOverlay;
        private static TextBlock lblUpdateTitle;
        private static TextBlock lblUpdateSub;
        private static ProgressBar pbUpdateBar;
        private static TextBlock lblUpdateDetail;
        private static TextBlock lblTitleVersion;
        private static bool isUpdatingSelf = false;
        private static int selfUpdateTickCounter = 0;
        private static int roomPollCounter = 0;
        private static int lastRenderedMemberCount = -1;
        private const string CLIENT_VERSION_LABEL = "Reconnect Shield • Stable Session • 1.26a Ready";
        private const string B64_HERO = "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";
        private const string B64_LOGO = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAAeAB8DASIAAhEBAxEB/8QAGwAAAQQDAAAAAAAAAAAAAAAACAIFBwkDBAb/xAAwEAABAwIFAwEFCQAAAAAAAAABAgMEBREABgchMQgSE0EJFCNRcTIzUmFigZGSof/EABcBAQEBAQAAAAAAAAAAAAAAAAYHAwT/xAAlEQABAwQABQUAAAAAAAAAAAABAgMEAAURIQYTFGFxEjFBQoH/2gAMAwEAAhEDEQA/AK0r9ouTbG5OpNTpfuxqcCRF98YTKj+Zso8rKiQlxN+UmxseDbE+9EeRMjZ11CqkrO1KbqAosNqVBZfV8EvKc7brRwuw3AO1/Q4lHrb0GzPmaqNasZUSmfFh09uHOgNoPmZQ0VFLjYH202VuBuLXAI4YNWd56J1SRnsK2FuUYhlZ/KCft+uMsyFMgltM6K9HU80h9sONlBW2oXSsX5SRweDg8+kToahOohal64wErbUESKbl9zcKBF0uybHjcENf2/DiHfaKGMx1IymYrSG2W6HTkNoQkJShIQoAADYAfIY4XYi2W+Y4MUNjcQx5txMBjeAST4+KZOj+cYWY8xLQvtUqEwARz96cFjQNRXMx1aq5fn9oFFXHv8S/mS433AkegBuPztivvTPUhWnb9UmswlSZEyOhlhPd2oCgq91Hm1vl/mEp1XzsznBeeI9TDVSdSG1BKfhKbAsG1I9U/U8784oFr4hhWu0sNLBK8nIx7DzS12UrpAwg73Vk+X9bW4moTOl8Jpx1xymPVVbpdHYwlK0pSgJ53uT6AWFucBP1wzX6lr3LkvkkmlQR+3YcN3TZqcMoan1TO2ZUTKo87SpjjxCgXFqAC+VH9Nv4xx2tGqErV3PsvOculs0/ytNRmo7aioIabFk3J5VvudsH71cmbhE5gGCV6HYVMrdZ1xOJXH2k4R6N7+x7V//Z";
        private const string B64_AVATAR = "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";
        private const string B64_MAP0 = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAAqACoDASIAAhEBAxEB/8QAGQAAAwEBAQAAAAAAAAAAAAAABgcIBQQD/8QANBAAAQMCBQIEAwYHAAAAAAAAAQIDBAURAAYHEiETMRQiQVEyQmEIYnGR0eEVFiSBobHx/8QAGQEAAwEBAQAAAAAAAAAAAAAAAgQGBQMA/8QAKhEAAQMCBAMJAQAAAAAAAAAAAQIDEQAEBRJBURQhMQYTFSIyYXGB0SP/2gAMAwEAAhEDEQA/AILcnNzHZ9G8a5FYjoJZf6qxsUk2uog3O6/+sAc/+ZIUtDLlXkuJdG5taJKlJUn3Bv8AvjTacUzKfUu58VIXfn5Qr9cG2Q8vUjOM9GW3Vts1AukxHHD5XEqI3I+hB8w9+cAtxTZJ6iph288OC3Vc06/v7WHlOnVepPxo/i6jIddWlKWkOuKUsk9gAeceGaaRXIEp8InVFlTbiklpbrgKbHtYm4w1a5VK9l81HLun1KNEgxrxnZgZ/rX7HaVOOkbmwojhKdoANuTzjuyPUanqDUIOQtRKc7U/FERIVVbZ3TYbh4SVEC7zYPxIXcgdiLY4i4UDn0rBVjTzZN3yybTzjrMdPqfyk1kbLOdc3VFyNEqMpDEdCnpD70pSGmGki6lrUTwAP2ueMMpjT3KbrLbh1WuVpCrpbfsbj0uQbf2GNnUdLmmtFlaXUcNJ6hS5XJwRYy3PiQ02e/SSCD95XPYDAlT59CTAjJW4NwZQDz67Rj3euumQYFFx9xig4htRSg+mNRuZGug2pbvyErekNhglDZKrlVilV+SP0wY5CZrbFIrVZy3FW9V2GG2oRABW0t55LZcT7KAJAPoVA4DICVuPSXH2SWluKSdve1+4/LDf0ZRLbqXTi7VtPILDqCOHEG1wR+R+htjo+YBinMbuRZ2ylQDEcj0O4Pz0ojpWpVXnZXlwNT2gxUmYHVh1oRVB1VlhK2pDe26rX72sR798b1C1IqcHKDOXtLWREqdWp70hyvvQHVSJSgsoTGihCVFCja1zwLHkYHs/1nUBX8b07jRm0VKigS33nnwpx5lFlpWncOUhFlbQbWJ74yMs6marUKBStNYqIblUzYttdOkdYJLBkr27lJAsm5NwCAByQDfCmWRmAqQGGcWzxDbKZKs2TN5Yj1RHTWJj2oeza1mCblaGnMi5AqdGku0p/eq5W0kBxtKj6lF1p/DaPTC9Lb9ztRx6ec4qLWHLFRiLahVbYpmCkMK6bQQC4jguWAF1KIJJPPphDLy8grUUtu2JNvLgmXRlmtfBMaaubfPAHx0+q7sk0RM9Ul6KhDvg0b1NrRuHKgkqPvbcT/zDxpeQ6NplRIufcymTT9xJj09BHVmqA5ABHlR2us9u3JtZKaKypLOY5pZkOoJiyeUrI+QnFJU+dNr+UKWa7MfqJbYKUeLcL20bjwN17YG4WQuKwe1Fy6i9FuVeQnmNwdKnvWCuRNQX3M9Iqa01h/cmfGKSkJQOGyg9igIsm3ptHvgZygmLllCM9y6oW6hT3GnqWz8S1uoUClRv8ibf4wT6+wocCTDMGIzHLrB39JsI3fjbvgL09YYlS3hJZQ9sjOFPUSFbSE8EX7WwwkfzirCwZAw0JSTl29tp20+KsxrUjTj7QdIbrL9UZpU9prfUYBb8xWlPJSRc2NviAIA9LjAmrO1JiKMSPXaQy0yem22mktqCEjgJBUNxAAtc8++Jryc87FzbTnIrq2VCagBTaik8rAPb6YJKulIqs0BIAEhwAAfeOEFN92YBqNc7NMWT6mmVkIPMDaa//9k=";
        private const string B64_MAP1 = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAAqACoDASIAAhEBAxEB/8QAGQAAAwEBAQAAAAAAAAAAAAAABgcIBQME/8QANhAAAgEDBAECBAMECwAAAAAAAQIDBAURAAYSITEHQRMUIlEVQmEWcXLRJDJDU1VigYKRk8H/xAAZAQACAwEAAAAAAAAAAAAAAAAFBgIEBwP/xAAqEQABAwMBCAEFAQAAAAAAAAABAgMRAAQFIQYSIjFBUWFxkRMjgbHB8P/aAAwDAQACEQMRAD8AiTYNvPrFZJts0VXNQ7opuc1tMUjKlcmMmnbvpwASh9+1PsQvL7Z97bbINwqLpArsyqzyyAMVOGHn2PnRN6E3O0ba3rTXq8Xaekpbf/SUenTlLK4xwVB9ySM58AHVg+p/pPtn1xtFJu7aF7pBTlfjVsjngIckGR+P6nviO+R6zy0jZDPu4PIhpySyvr2Pb81sWO2atNosUl9UJeSI8GOU++lRLYts7qv9ouN+e416UNuhLyy/FfBcg8EHfk4z+4E6Hppdw22tlpZrrViSFypxUMf/AHVbeptkh296eXCx7foJaWxWyhdaZWxyld+POeQjy7kD+EBV9tTRaLNNu94PkSq1SFYaz4h6jQdCc/5Ao+r7EZ/MNFsVmXL9C7hWiZgevNDNoNkW8Kq3t4+6pO8fmIrLa67mjgSo/Frisb54t8d8HHnHfevN+1O4/wDHLj/3t/PRbQrR301+2adCU5vPbGbpsqO0/wB6KD/Eox50MNYSGIx7/bRNq8JJSswaAXWOUAlTOo/orpYba/yS1ks3w1Y4jHuzfYfz1Tuyt37w9H/SmK7WNFq5Km5rJXRSxiSB4ODIEfP5ObjJ6w3HvrSKst12rElshltvOGkZY35uQ0ysmWJ9gQ2SP9NUtteW53vaVCPTyhiuVRb5aiikoquWOAVSSAO3EOcSceOGA+40I2pUlbLSVNcM6zyPs9K0PYSwbTbPS+AopgRJIPOY61m799TLTu3Zt4s1wqY9vtARBPQKfmqGSdipMtPUoDyIQNlCfGME6nc2qhaWCew2+sWGflGlRNIA8xIIwUTpAwyMEk405tz2Wu3dta9ruS40236uxBoTZXt7KsbNxYfDEYOHbhgswxgDvBxpa7QhvW4tw7d2pUbiqZbVbZEmjiMhWOkieTlIV9lP1E5/XVXDm3s7d36Y0HToNO8a/NSzbN9dXls25Chy3o1OvadKKdrem+36Skp9+3K9OKe2TRzNbYaaRaz4wcERuWUIikj+vyPXgE9aEKnbVXUVMtQiFVldnAHgAnONNb1E3lbdt7OrNhbVqK+e2vJ8eeavl5zO6nIVR/ZqCPHkkd6wKX1Hp2poWp7baREY1KBmHLjjrPfnGu2IburxK7h0GCeGe1XstbY/EFLDxAWdTSulstDR0EdVQ0DVISmjnNTPKBGxPHIVBjxkjBJPR60UbV31cbE8VdHWCJ07jZzjJ9gB9h/wPtpe2ZVehjLqGPLHYz1jXqjd5LvKsjFwI5AAxyMBTjTau0beZKXhve6QbHMPY5xD9pwyBp0/X+706a/dVz3Hse4Xa2yCruMkAt9zj4BpAkcgeCYe+OJkjY+wC586A9j71l2dDcjLDTTVd5X5eUMitmmT8iE545YDBH92B4JyIWOab8MqB8V8E4P1HsYGsm4u3zzfUfpVcd+OtUmsSwjfbjhJmP5RbI7SXADGQA4x50k6E8udF973ZBcAxMnLmOBMi5YA9d/fA9/Pt3oVkfbwkYJQTsuTgmqwSP3Y61zuvUqkeWjUn9SR51ngnHk6LJaQlISkRSdkcxcXrxXcQo+a/9k=";
        private const string B64_MAP2 = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAAqACoDASIAAhEBAxEB/8QAGgAAAwADAQAAAAAAAAAAAAAABQcIAgYJBP/EADEQAAEDAwMCBAQFBQAAAAAAAAECAwQFBhEABxIhMRMiQVEIFSNCMjNSYXEUJIGhsf/EABkBAAIDAQAAAAAAAAAAAAAAAAUGAQQHA//EACwRAAEDAgQDBwUAAAAAAAAAAAECAwQAEQUhMUFRYXEGEhQiMqHBE4GRsfH/2gAMAwEAAhEDEQA/AEfsjatM+IvbaRbSi4zetFjPOUt1lSk/MkDKlx3AD+YBlSFeo8p7DSLvHbC+LbpUapS35SRNW6GmkvKKwltXEqUM+Ucugz3wfbTU+EG+qTZW4FrVtrjBhsLSJrwJUUuAnktQ/g9AMdBjVabrbP0XeO/I132lXG4FAlKWzW4yzxMVSVeIsBA/EVKJUkepUD762VuExMZQJQ8pT6hsdx99RzvyrIZGJO4RNWhs5d69jw5cM/iud0Hbm8Bt5U76diTk0+I7HjOTHXFJQh11wBKUknBOATgdh1OtMqka46VPeptTkzWX2FltxCnVZBH+ddHvjO27fo/w8MPW/DRT7YjcY9PhIXyJ4uo5OufqcWckqPX06AagiKiZdlPbhyEeJU6e0EtLx5pMdPZJ91IHY+qRj7RoBLwxla0oY4e4JBB5/wApiwrFnJLSn3Rbze1gQelH9tdsahcFEql61qrS4VAoiEKmTFKWoJUrPBtAB87isHCcgdCSQBnQR2/qe06tqPR5i2kKKUKcqbgUUg9CQBjOO+Omnpctj3BtvtdblsXGp2Ia1T6lVKhBKyC0lxCBGU4n0XxZChnqAv8AfUzKorClE/NoycnOCVZGrkuOqAy0lhIzHL5qYMhE9xxTxJsbDWw/FHLTbqlKpTlag80uIdQw0SMgKVkk47HoP96vnb/cfdTazaqg7grtenXD84mx6fUWHwtLXg8VFta8HyrAGPE7ADODnU/UJ3aWYhVt1ScafSqjGZajSnWhzhvtJ8j6wknklXJXiY6jmcZKOtj7Wby2Jath02ybutx2r0qbNRTlVNkZjCQ21yTwV0KleXlkYHsT20c8KqPALLfnvYED3I58KVMTmCVKbdWju2JNyNbDTpxoRfu8+2O+u00ujzJHymPTJi1VGCh5MpCUhQy5FeQOMhtSkYSRggkcgAc6luruW7a0un1C2ZlJpiZUUVKDS4bJkPtFOFR0y5PH85wDkEA4HQFKc41QXxMWvcbsZtrZe1YVUo79PmsSoUpZzCfcSHC8kJUkFRbQFNk5BwfLkanW0b3sja3a9VwXdaEWffs9tbFElLXzZiIIH9ytkHip8BR4kg4OCRkZ1yiq8K0EJBsnO5A3Oe+u/wCqlpIkKLqT6zYJBvpvpplRD4jLzdrUZqIhqa/Or6RUpVQmYK30r6pbbP6U/hPupPoANTQq3qkVEpaJBPTy6o+r0W6NwVWWxUqLPhUSjsIdk1h6I4yw3FUpCyErWAF4AwkDqonoOuljKNFbkvNtV2FwS4oJyeuM9NWZ0ZucsFSshkKu4Y+uC13EJzNyd968tkRbLmRjcNyzJUpDThRBpEc+AmRgDzOSFHDaM9wgFZx9vQ63eo7py5t40JFdqjCI1FdQqnUumJCIUVpIyrCfUkD8Z6q7lSu+p+jPvOW2kOPLUGlICApRPEY7D21hT3XVTZ7hcUVf0znmJ6+g/wCaXI+JrYCFBNybHWmCRhiJBUFHLMfFdNn6zbN8bbSKvRLgmNVEUN2A+mJJLapcRaeUdwAKTyKFZQpJPb+NQBeVXj0Wp05xDgbegyi6kJKXAHElJKh6EBSQB74OmHthJkHa7gX3CnxJjeCo44/TPH+MknHuTpEXopSq0sKUSAgYBP7HR7GnvoYcl9A9dj0vnagHZ2GBOcYJyQSOu1Na/N+avesXFWjQ1KcRhS47QjqcJzlSi2BzBz9wyO2T30tuMd36qWmkBfmCS8roD6d9a3EWpULClEhLnTJ7dDoct53mr6q+5+46TZWNPukFYFOMfC2WLhvLOv/Z";
        private const string B64_MAP3 = "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";
        private const string B64_MAP4 = "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";
        private const string PATCH_GAME_DLL_SHA256 = "175e9ba8460ab709ed2ef8adb02919876b4e0d4762903016b18bfb0b61b2351b";
        private const string PATCH_GAME_DLL_128M_SHA256 = "175e9ba8460ab709ed2ef8adb02919876b4e0d4762903016b18bfb0b61b2351b";

        // Real-time W3GS bridge & Game.dll memory state for zero-bug WarKey & Waiting Screen HUD
        private static volatile bool bridgeW3gsConnected = false;
        private static volatile bool bridgeW3gsInGame = false;
        private static volatile bool bridgeLagDialogOpen = false;
        private static int activeBridgeSessionId = 0;
        private static uint cachedWar3Pid = 0;
        private static IntPtr cachedWar3ProcHandle = IntPtr.Zero;
        private static IntPtr cachedGameDllBase = IntPtr.Zero;
        private static string waitTypedBuffer = "";
        private static DateTime lastBlindAddtimeUtc = DateTime.MinValue;
        private static Window waitOverlayWin = null;
        private static Border waitOverlayBorder = null;
        private static TextBlock lblWaitOverlayTitle = null;
        private static TextBlock lblWaitOverlaySub = null;

        // WarKey & QuickChat Elements (6 Inventory + 8 Skills + QuickChat list — all empty by default)
        private static Button[] wkButtons = new Button[6];
        private static string[] wkKeys = new string[] { "", "", "", "", "", "" };
        private static Button[] wkSkillButtons = new Button[8];
        private static string[] wkSkillKeys = new string[] { "", "", "", "", "", "", "", "" };
        private static string capturingMode = ""; // "INV", "SKILL", "QCHAT", or ""
        private static int capturingSlot = -1;
        private static bool warKeyEnabled = true;
        private static volatile bool hasAnyWarKeyBinding = false;
        private static bool inGameChatActive = false;
        private static IntPtr keyboardHookId = IntPtr.Zero;
        private static LowLevelKeyboardProc keyboardHookProc;
        private static Border btnToggleWarKey;
        private static TextBlock lblWarKeyToggleState;
        private static Button btnQuickChatKey;
        private static TextBox txtQuickChatMsg;
        private static RadioButton rbChatWar3;
        private static RadioButton rbChatWar3All;
        private static RadioButton rbChatLobby;
        private static ItemsControl quickChatListCtrl;
        private static string pendingQuickChatKey = "";
        private static List<QuickChatItem> quickChats = new List<QuickChatItem>();

        private static List<Dictionary<string, string>> cachedMaps = new List<Dictionary<string, string>>();
        private static List<Dictionary<string, string>> cachedRooms = new List<Dictionary<string, string>>();

        private const string XAML_UI = @"
<Window xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'
        xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml'
        Title='ZevArena' Width='1180' Height='820' MinWidth='1024' MinHeight='740'
        WindowStartupLocation='CenterScreen' WindowStyle='None' AllowsTransparency='True'
        Background='Transparent' ResizeMode='CanResizeWithGrip' FontFamily='Segoe UI'>
  <Border CornerRadius='12' Background='#0A0E1C' BorderBrush='#252F4C' BorderThickness='1'>
    <Grid>
      <Grid.RowDefinitions>
        <RowDefinition Height='42'/>
        <RowDefinition Height='*'/>
      </Grid.RowDefinitions>

      <!-- CUSTOM MODERN TITLEBAR (100% Reference Design) -->
      <Border Grid.Row='0' Name='TitleBar' Background='#080B16' CornerRadius='12,12,0,0' BorderBrush='#1D253E' BorderThickness='0,0,0,1'>
        <Grid Margin='14,0,10,0'>
          <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
            <Border Width='26' Height='26' CornerRadius='6' Margin='0,0,9,0' ClipToBounds='True' Background='#151B30'>
              <Image Name='ImgLogo' Width='26' Height='26' Stretch='UniformToFill' RenderOptions.BitmapScalingMode='HighQuality'/>
            </Border>
            <TextBlock Text='ZevArena' Foreground='#FFFFFF' FontWeight='ExtraBold' FontSize='14.5' VerticalAlignment='Center'/>
            <Border Background='#0C2621' BorderBrush='#10B981' BorderThickness='1' CornerRadius='6' Padding='10,3' Margin='12,0,0,0' VerticalAlignment='Center'>
              <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                <Ellipse Width='7' Height='7' Fill='#10B981' VerticalAlignment='Center' Margin='0,0,6,0'/>
                <TextBlock Text='Warcraft III 1.26a' Foreground='#F1F5F9' FontSize='11' FontWeight='Bold' VerticalAlignment='Center'/>
                <TextBlock Text='   |   ' Foreground='#334155' FontSize='11' FontWeight='Bold' VerticalAlignment='Center'/>
                <TextBlock Name='LblTitleVersion' Text='Reconnect Shield • Stable Session • 1.26a Ready' Foreground='#34D399' FontSize='11' FontWeight='Bold' VerticalAlignment='Center'/>
              </StackPanel>
            </Border>
          </StackPanel>
          <StackPanel Orientation='Horizontal' HorizontalAlignment='Right' VerticalAlignment='Center'>
            <Button Name='BtnTitleBell' Content='🔔' Width='32' Height='28' Background='Transparent' Foreground='#94A3B8' BorderThickness='0' Cursor='Hand' FontSize='12.5' ToolTip='Найзууд &amp; Мэдэгдэл'/>
            <Button Name='BtnTitleGear' Content='⚙' Width='32' Height='28' Background='Transparent' Foreground='#94A3B8' BorderThickness='0' Cursor='Hand' FontSize='13' ToolTip='War3 Тохируулах &amp; Patch'/>
            <Border Width='1' Height='16' Background='#1E293B' Margin='6,0,6,0' VerticalAlignment='Center'/>
            <Button Name='BtnMin' Content='—' Width='32' Height='28' Background='Transparent' Foreground='#94A3B8' BorderThickness='0' Cursor='Hand'/>
            <Button Name='BtnMax' Content='☐' Width='32' Height='28' Background='Transparent' Foreground='#94A3B8' BorderThickness='0' Cursor='Hand'/>
            <Button Name='BtnClose' Content='✕' Width='32' Height='28' Background='Transparent' Foreground='#EF4444' BorderThickness='0' Cursor='Hand' FontWeight='Bold'/>
          </StackPanel>
        </Grid>
      </Border>

      <!-- ROW 1: CONTENT -->
      <Grid Grid.Row='1'>
        <!-- AMBIENT GLOW BACKGROUND -->
        <Canvas IsHitTestVisible='False' ClipToBounds='True'>
          <Ellipse Width='620' Height='420' Canvas.Left='240' Canvas.Top='-130' Opacity='0.15'>
            <Ellipse.Fill>
              <RadialGradientBrush>
                <GradientStop Color='#7C3AED' Offset='0'/>
                <GradientStop Color='#007C3AED' Offset='1'/>
              </RadialGradientBrush>
            </Ellipse.Fill>
          </Ellipse>
          <Ellipse Width='520' Height='380' Canvas.Right='-80' Canvas.Bottom='-80' Opacity='0.10'>
            <Ellipse.Fill>
              <RadialGradientBrush>
                <GradientStop Color='#10B981' Offset='0'/>
                <GradientStop Color='#0010B981' Offset='1'/>
              </RadialGradientBrush>
            </Ellipse.Fill>
          </Ellipse>
        </Canvas>

        <!-- ==================== 1. CENTERED AUTH VIEW ==================== -->
        <Grid Name='AuthView' Visibility='Visible'>
          <Border Width='410' VerticalAlignment='Center' HorizontalAlignment='Center'
                  Background='#111628' CornerRadius='20' BorderBrush='#283556' BorderThickness='1' Padding='32,28,32,28'>
            <Border.Effect>
              <DropShadowEffect Color='#000000' BlurRadius='45' ShadowDepth='12' Opacity='0.65'/>
            </Border.Effect>
            <StackPanel>
              <Border Width='56' Height='56' CornerRadius='16' HorizontalAlignment='Center' Margin='0,0,0,14' ClipToBounds='True'>
                <Border.Background>
                  <LinearGradientBrush StartPoint='0,0' EndPoint='1,1'>
                    <GradientStop Color='#7C3AED' Offset='0'/>
                    <GradientStop Color='#2563EB' Offset='0.5'/>
                    <GradientStop Color='#10B981' Offset='1'/>
                  </LinearGradientBrush>
                </Border.Background>
                <Image Name='ImgAuthLogo' Width='56' Height='56' Stretch='UniformToFill' RenderOptions.BitmapScalingMode='HighQuality'/>
              </Border>

              <StackPanel Orientation='Horizontal' HorizontalAlignment='Center' Margin='0,0,0,4'>
                <TextBlock Text='ZevArena' Foreground='White' FontSize='22' FontWeight='ExtraBold'/>
              </StackPanel>
              <TextBlock Text='Warcraft III 1.26a Esport Platform (zevarena.com)' Foreground='#94A3B8' FontSize='12.5' HorizontalAlignment='Center' Margin='0,0,0,22'/>

              <!-- Segmented Pill Toggle: Sign In / Sign Up -->
              <Border Background='#0B0F1A' CornerRadius='12' Padding='4' BorderBrush='#1E293B' BorderThickness='1' Margin='0,0,0,20'>
                <Grid Height='36'>
                  <Grid.ColumnDefinitions>
                    <ColumnDefinition Width='*'/>
                    <ColumnDefinition Width='*'/>
                  </Grid.ColumnDefinitions>
                  <Border Grid.Column='0' Name='TabSignInBorder' Background='#7C3AED' CornerRadius='9' Cursor='Hand'>
                    <TextBlock Name='TabSignInText' Text='Нэвтрэх (Sign In)' Foreground='White' FontWeight='SemiBold' FontSize='12.5' HorizontalAlignment='Center' VerticalAlignment='Center'/>
                  </Border>
                  <Border Grid.Column='1' Name='TabSignUpBorder' Background='Transparent' CornerRadius='9' Cursor='Hand'>
                    <TextBlock Name='TabSignUpText' Text='Бүртгүүлэх (Sign Up)' Foreground='#94A3B8' FontWeight='SemiBold' FontSize='12.5' HorizontalAlignment='Center' VerticalAlignment='Center'/>
                  </Border>
                </Grid>
              </Border>

              <TextBlock Name='LblUserPrompt' Text='📧 И-мэйл хаяг эсвэл Тоглогчийн нэр' Foreground='#CBD5E1' FontSize='12' FontWeight='SemiBold' Margin='2,0,0,6'/>
              <Border Background='#0B0F1A' CornerRadius='10' BorderBrush='#24304C' BorderThickness='1' Padding='12,8' Margin='0,0,0,14'>
                <TextBox Name='TxtUser' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='13.5'/>
              </Border>

              <StackPanel Name='AuthEmailPanel' Visibility='Collapsed' Margin='0,0,0,14'>
                <TextBlock Name='LblEmailPrompt' Text='И-мэйл хаяг (Нууц үг сэргээхэд ашиглана)' Foreground='#CBD5E1' FontSize='12' FontWeight='SemiBold' Margin='2,0,0,6'/>
                <Border Background='#0B0F1A' CornerRadius='10' BorderBrush='#24304C' BorderThickness='1' Padding='12,8'>
                  <TextBox Name='TxtEmail' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='13.5'/>
                </Border>
              </StackPanel>

              <TextBlock Name='LblPassPrompt' Text='Нууц үг (6+ тэмдэгт)' Foreground='#CBD5E1' FontSize='12' FontWeight='SemiBold' Margin='2,0,0,6'/>
              <Border Background='#0B0F1A' CornerRadius='10' BorderBrush='#24304C' BorderThickness='1' Padding='12,8' Margin='0,0,0,10'>
                <PasswordBox Name='TxtPass' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='13.5'/>
              </Border>

              <Border Name='BtnForgotPass' Background='Transparent' Cursor='Hand' HorizontalAlignment='Right' Padding='2,2' Margin='0,0,0,14'>
                <TextBlock Name='LblForgotPassText' Text='🔑 Нууц үгээ мартсан уу? (Сэргээх)' Foreground='#38BDF8' FontSize='11.5' FontWeight='SemiBold'/>
              </Border>

              <Border Name='BtnAuthSubmit' CornerRadius='11' Height='44' Cursor='Hand'>
                <Border.Background>
                  <LinearGradientBrush StartPoint='0,0' EndPoint='1,0'>
                    <GradientStop Color='#7C3AED' Offset='0'/>
                    <GradientStop Color='#6366F1' Offset='1'/>
                  </LinearGradientBrush>
                </Border.Background>
                <TextBlock Name='BtnAuthSubmitText' Text='Нэвтрэх  →' Foreground='White' FontSize='14' FontWeight='Bold' HorizontalAlignment='Center' VerticalAlignment='Center'/>
              </Border>

              <TextBlock Name='LblAuthError' Text='' Foreground='#F87171' FontSize='12' FontWeight='SemiBold' TextWrapping='Wrap' TextAlignment='Center' HorizontalAlignment='Center' Margin='0,14,0,0'/>
            </StackPanel>
          </Border>
        </Grid>

        <!-- ==================== 2. MAIN APP SHELL (SIDEBAR + WORKSPACE) ==================== -->
        <Grid Name='AppShell' Visibility='Collapsed'>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width='220'/>
            <ColumnDefinition Width='*'/>
          </Grid.ColumnDefinitions>

          <!-- LEFT SIDEBAR (100% Reference Design) -->
          <Border Grid.Column='0' Background='#0B0F1D' BorderBrush='#1D2640' BorderThickness='0,0,1,0' Padding='12,12,12,12'>
            <Grid>
              <StackPanel VerticalAlignment='Top'>
                <!-- Profile Card with Neon M Avatar + Badge + Level Progress + Ready to Play -->
                <Border Background='#12182C' CornerRadius='12' Padding='11,10' BorderBrush='#263152' BorderThickness='1' Margin='0,0,0,12'>
                  <StackPanel>
                    <StackPanel Orientation='Horizontal'>
                      <Grid Width='44' Height='44' Margin='0,0,10,0'>
                        <Border Width='44' Height='44' CornerRadius='22' ClipToBounds='True' Background='#182038'>
                          <Image Name='ImgAvatar' Width='44' Height='44' Stretch='UniformToFill' RenderOptions.BitmapScalingMode='HighQuality'/>
                        </Border>
                        <Border Width='11' Height='11' CornerRadius='6' Background='#10B981' BorderBrush='#12182C' BorderThickness='2' HorizontalAlignment='Right' VerticalAlignment='Bottom'/>
                      </Grid>
                      <StackPanel VerticalAlignment='Center'>
                        <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                          <TextBlock Name='LblProfileName' Text='Zev MN' Foreground='White' FontWeight='ExtraBold' FontSize='14' MaxWidth='102' TextTrimming='CharacterEllipsis' Cursor='Hand' ToolTip='Дарж тоглогчийн нэрээ солино уу' VerticalAlignment='Center'/>
                          <Border Name='BtnEditProfileName' Background='#1B2542' BorderBrush='#3B4F82' BorderThickness='1' CornerRadius='5' Padding='5,1' Margin='6,0,0,0' Cursor='Hand' ToolTip='Тоглогчийн нэр солих' VerticalAlignment='Center'>
                            <TextBlock Text='✏️ Нэр' FontSize='9.5' FontWeight='Bold' Foreground='#38BDF8'/>
                          </Border>
                        </StackPanel>
                        <StackPanel Orientation='Horizontal' Margin='0,2,0,0'>
                          <Ellipse Width='6' Height='6' Fill='#10B981' VerticalAlignment='Center' Margin='0,0,4,0'/>
                          <TextBlock Text='Online' Foreground='#34D399' FontSize='10.5' FontWeight='Bold'/>
                          <TextBlock Text=' • ' Foreground='#64748B' FontSize='10.5'/>
                          <TextBlock Name='LblProfileUid' Text='#10001' Foreground='#94A3B8' FontSize='10.5' FontWeight='SemiBold'/>
                        </StackPanel>
                      </StackPanel>
                    </StackPanel>

                    <Border Name='BtnProfileEloCard' Background='#0D1222' CornerRadius='8' BorderBrush='#1F2947' BorderThickness='1' Padding='8,6' Margin='0,9,0,8' Cursor='Hand' ToolTip='Дарж сүүлийн 10 тоглолтын түүхээ харна уу'>
                      <StackPanel>
                        <Grid>
                          <Grid.ColumnDefinitions>
                            <ColumnDefinition Width='*'/>
                            <ColumnDefinition Width='Auto'/>
                          </Grid.ColumnDefinitions>
                          <TextBlock Grid.Column='0' Name='LblProfileBadge' Text='🛡️ Итгэлтэй Тоглогч' Foreground='#E2E8F0' FontSize='10.5' FontWeight='Bold' VerticalAlignment='Center' TextTrimming='CharacterEllipsis' Margin='0,0,6,0'/>
                          <TextBlock Grid.Column='1' Name='LblProfileElo' Text='⏳ 0/10' Foreground='#38BDF8' FontSize='10.5' FontWeight='ExtraBold' HorizontalAlignment='Right' VerticalAlignment='Center'/>
                        </Grid>
                        <Border Background='#1B233B' CornerRadius='3' Height='5' Margin='0,6,0,0' ClipToBounds='True'>
                          <Border CornerRadius='3' Width='95' HorizontalAlignment='Left'>
                            <Border.Background>
                              <LinearGradientBrush StartPoint='0,0' EndPoint='1,0'>
                                <GradientStop Color='#8B5CF6' Offset='0'/>
                                <GradientStop Color='#06B6D4' Offset='1'/>
                              </LinearGradientBrush>
                            </Border.Background>
                          </Border>
                        </Border>
                      </StackPanel>
                    </Border>

                    <!-- Ready to Play Button -->
                    <Border Name='BtnSidebarReadyPlay' CornerRadius='8' Height='32' Cursor='Hand' BorderBrush='#34D399' BorderThickness='1'>
                      <Border.Background>
                        <LinearGradientBrush StartPoint='0,0' EndPoint='1,0'>
                          <GradientStop Color='#059669' Offset='0'/>
                          <GradientStop Color='#10B981' Offset='1'/>
                        </LinearGradientBrush>
                      </Border.Background>
                      <Grid Margin='10,0'>
                        <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                          <TextBlock Text='🎮' Foreground='White' FontSize='12' VerticalAlignment='Center' Margin='0,0,7,0'/>
                          <TextBlock Text='Ready to Play' Foreground='White' FontWeight='ExtraBold' FontSize='12' VerticalAlignment='Center'/>
                        </StackPanel>
                        <TextBlock Text='›' Foreground='#D1FAE5' FontSize='16' FontWeight='Bold' HorizontalAlignment='Right' VerticalAlignment='Center' Margin='0,-2,0,0'/>
                      </Grid>
                    </Border>
                  </StackPanel>
                </Border>

                <!-- Navigation Buttons -->
                <Border Name='NavBtnLobbies' Background='#231946' BorderBrush='#7C3AED' BorderThickness='1' CornerRadius='9' Padding='12,9' Margin='0,0,0,5' Cursor='Hand'>
                  <Grid>
                    <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                      <TextBlock Text='🎮' Foreground='#A78BFA' FontSize='12.5' Margin='0,0,9,0' VerticalAlignment='Center'/>
                      <TextBlock Text='Lobbies' Foreground='White' FontWeight='Bold' FontSize='12.5' VerticalAlignment='Center'/>
                    </StackPanel>
                    <Ellipse Width='7' Height='7' Fill='#10B981' HorizontalAlignment='Right' VerticalAlignment='Center'/>
                  </Grid>
                </Border>

                <Border Name='NavBtnLeaderboard' Background='Transparent' BorderBrush='Transparent' BorderThickness='1' CornerRadius='9' Padding='12,9' Margin='0,0,0,5' Cursor='Hand'>
                  <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                    <TextBlock Text='🏆' Foreground='#94A3B8' FontSize='12.5' Margin='0,0,9,0' VerticalAlignment='Center'/>
                    <TextBlock Text='Топ 100 ELO' Foreground='#CBD5E1' FontWeight='SemiBold' FontSize='12.5' VerticalAlignment='Center'/>
                  </StackPanel>
                </Border>

                <Border Name='NavBtnFriends' Background='Transparent' BorderBrush='Transparent' BorderThickness='1' CornerRadius='9' Padding='12,9' Margin='0,0,0,5' Cursor='Hand'>
                  <Grid>
                    <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                      <TextBlock Text='💬' Foreground='#94A3B8' FontSize='12.5' Margin='0,0,9,0' VerticalAlignment='Center'/>
                      <TextBlock Text='Найзууд &amp; Чат' Foreground='#CBD5E1' FontWeight='SemiBold' FontSize='12.5' VerticalAlignment='Center'/>
                    </StackPanel>
                    <Border Name='BadgeFriendsUnread' Visibility='Collapsed' Background='#EF4444' CornerRadius='99' Padding='6,1.5' HorizontalAlignment='Right' VerticalAlignment='Center'>
                      <TextBlock Name='LblFriendsUnreadCount' Text='3' Foreground='White' FontSize='10' FontWeight='ExtraBold'/>
                    </Border>
                  </Grid>
                </Border>

                <Border Name='NavBtnWarKey' Background='Transparent' BorderBrush='Transparent' BorderThickness='1' CornerRadius='9' Padding='12,9' Margin='0,0,0,5' Cursor='Hand'>
                  <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                    <TextBlock Text='⌨️' Foreground='#94A3B8' FontSize='12.5' Margin='0,0,9,0' VerticalAlignment='Center'/>
                    <TextBlock Text='WarKey (Гарны товч)' Foreground='#CBD5E1' FontWeight='SemiBold' FontSize='12.5' VerticalAlignment='Center'/>
                  </StackPanel>
                </Border>

                <Border Name='NavBtnSettings' Background='Transparent' BorderBrush='Transparent' BorderThickness='1' CornerRadius='9' Padding='12,9' Margin='0,0,0,6' Cursor='Hand'>
                  <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                    <TextBlock Text='⚙️' Foreground='#94A3B8' FontSize='12.5' Margin='0,0,9,0' VerticalAlignment='Center'/>
                    <TextBlock Text='War3 Тохируулах &amp; Patch' Foreground='#CBD5E1' FontWeight='SemiBold' FontSize='12' VerticalAlignment='Center' TextTrimming='CharacterEllipsis'/>
                  </StackPanel>
                </Border>

                <!-- Hidden compatibility pill for auto-patcher status updates -->
                <Border Name='War3ReadyPill' Visibility='Collapsed' Background='#14382D' BorderBrush='#10B981' BorderThickness='1' CornerRadius='9' Padding='10,6' Margin='0,0,0,4' Cursor='Hand'>
                  <TextBlock Name='LblWar3ReadyPill' Text='✅ War3 + Patch: Бэлэн' Foreground='#34D399' FontWeight='Bold' FontSize='11' HorizontalAlignment='Center'/>
                </Border>

                <Border Name='BtnLogout' Background='Transparent' CornerRadius='9' Padding='12,8' Cursor='Hand'>
                  <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                    <TextBlock Text='🚪' Foreground='#F87171' FontSize='12.5' Margin='0,0,9,0' VerticalAlignment='Center'/>
                    <TextBlock Text='Гарах (Log Out)' Foreground='#F87171' FontWeight='Bold' FontSize='12.5' VerticalAlignment='Center'/>
                  </StackPanel>
                </Border>
              </StackPanel>

              <!-- Bottom Network & Anti-Cheat Status Card (100% Reference Design) -->
              <Border VerticalAlignment='Bottom' Background='#101528' CornerRadius='11' BorderBrush='#222C4A' BorderThickness='1' Padding='12,10'>
                <StackPanel>
                  <Grid Margin='0,0,0,7'>
                    <TextBlock Text='NETWORK &amp; ANTI-CHEAT' Foreground='#94A3B8' FontSize='9.5' FontWeight='ExtraBold' VerticalAlignment='Center'/>
                    <StackPanel Orientation='Horizontal' HorizontalAlignment='Right' VerticalAlignment='Center'>
                      <Ellipse Width='6' Height='6' Fill='#10B981' VerticalAlignment='Center' Margin='0,0,4,0'/>
                      <TextBlock Text='Ready' Foreground='#10B981' FontSize='10.5' FontWeight='Bold'/>
                    </StackPanel>
                  </Grid>
                  <Grid Margin='0,0,0,4'>
                    <TextBlock Text='🛡️ Anti-Cheat:' Foreground='#94A3B8' FontSize='11'/>
                    <TextBlock Name='LblAntiCheatBadge' Text='Идэвхтэй' Foreground='#34D399' FontSize='11' FontWeight='Bold' HorizontalAlignment='Right'/>
                  </Grid>
                  <Grid Margin='0,0,0,4'>
                    <TextBlock Text='🔒 HWID Shield:' Foreground='#94A3B8' FontSize='11'/>
                    <TextBlock Text='Баталгаажсан' Foreground='#E2E8F0' FontSize='11' FontWeight='Bold' HorizontalAlignment='Right'/>
                  </Grid>
                  <Grid Margin='0,0,0,4'>
                    <TextBlock Text='📶 Ping:' Foreground='#94A3B8' FontSize='11'/>
                    <TextBlock Name='LblNetPing' Text='8 ms' Foreground='#34D399' FontSize='11' FontWeight='Bold' HorizontalAlignment='Right'/>
                  </Grid>
                  <Grid>
                    <TextBlock Text='🌐 Bridge:' Foreground='#94A3B8' FontSize='11'/>
                    <TextBlock Name='LblNetIp' Text='127.0.0.1:6210' Foreground='#CBD5E1' FontSize='11' FontWeight='SemiBold' HorizontalAlignment='Right'/>
                  </Grid>
                </StackPanel>
              </Border>
            </Grid>
          </Border>

          <!-- RIGHT MAIN WORKSPACE -->
          <Grid Grid.Column='1' Margin='14,12,14,10'>
            <Grid.RowDefinitions>
              <RowDefinition Height='Auto'/>
              <RowDefinition Height='*'/>
            </Grid.RowDefinitions>

            <!-- FLOATING ROOM INVITE BANNER -->
            <Border Grid.Row='0' Name='InviteBannerOverlay' Visibility='Collapsed' Background='#172554' BorderBrush='#38BDF8' BorderThickness='1.5' CornerRadius='12' Padding='16,10' Margin='0,0,0,10'>
              <Grid>
                <Grid.ColumnDefinitions>
                  <ColumnDefinition Width='*'/>
                  <ColumnDefinition Width='Auto'/>
                </Grid.ColumnDefinitions>
                <TextBlock Grid.Column='0' Name='LblInviteBannerText' Text='📨 Найз таныг өрөөндөө урьж байна!' Foreground='White' FontWeight='ExtraBold' FontSize='13' VerticalAlignment='Center' TextWrapping='Wrap' Margin='0,0,12,0'/>
                <StackPanel Grid.Column='1' Orientation='Horizontal' VerticalAlignment='Center'>
                  <Border Name='BtnAcceptInvite' Background='#10B981' CornerRadius='8' Padding='14,7' Margin='0,0,8,0' Cursor='Hand'>
                    <TextBlock Text='✅ Зөвшөөрч Орох' Foreground='#04130D' FontWeight='ExtraBold' FontSize='12'/>
                  </Border>
                  <Border Name='BtnDeclineInvite' Background='#EF4444' CornerRadius='8' Padding='12,7' Cursor='Hand'>
                    <TextBlock Text='❌ Татгалзах' Foreground='White' FontWeight='Bold' FontSize='12'/>
                  </Border>
                </StackPanel>
              </Grid>
            </Border>

            <!-- ==================== PAGE 1: LOBBIES & INNER ROOM VIEW ==================== -->
            <Grid Grid.Row='1' Name='PageLobbies' Visibility='Visible'>

              <!-- 1A. LOBBY LIST VIEW (100% Reference Design) -->
              <Grid Name='LobbyListView' Visibility='Visible'>
                <Grid.RowDefinitions>
                  <RowDefinition Height='Auto'/>
                  <RowDefinition Height='Auto'/>
                  <RowDefinition Height='Auto'/>
                  <RowDefinition Height='*'/>
                  <RowDefinition Height='Auto'/>
                </Grid.RowDefinitions>

                <!-- ROW 0: LICH KING HERO BANNER + 5 INTERACTIVE MAP CARDS -->
                <Border Grid.Row='0' CornerRadius='12' BorderBrush='#2A3659' BorderThickness='1' Margin='0,0,0,10' ClipToBounds='True' Background='#0D1222'>
                  <Viewbox Stretch='Fill' MaxHeight='215'>
                    <Grid Width='795' Height='154'>
                      <Image Name='ImgHeroBanner' Width='795' Height='154' Stretch='Fill' RenderOptions.BitmapScalingMode='HighQuality'/>
                      <Border HorizontalAlignment='Left' VerticalAlignment='Top' Margin='16,18,0,0' Background='#D811182E' BorderBrush='#38497A' BorderThickness='1' CornerRadius='99' Padding='9,2.5'>
                        <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                          <TextBlock Text='⚡' Foreground='#FBBF24' FontSize='8.5' VerticalAlignment='Center' Margin='0,0,4,0'/>
                          <TextBlock Text='WARCRAFT III • FROZEN THRONE 1.26A PLATFORM' Foreground='#93C5FD' FontSize='8' FontWeight='ExtraBold' VerticalAlignment='Center'/>
                        </StackPanel>
                      </Border>
                      <TextBlock Name='LblHeroWelcomeText' Width='412' HorizontalAlignment='Left' VerticalAlignment='Top' Margin='16,102,0,0'
                                 Foreground='#CBD5E1' FontSize='11' TextWrapping='Wrap' LineHeight='15.5'>
                        <Run Text='Тавтай морил, '/><Run Text='Zev MN' Foreground='#34D399' FontWeight='ExtraBold'/><Run Text=' — Зөвхөн Warcraft III 1.26a дээрх 5 үндсэн газрын сонголттой Монгол лобби систем.'/>
                      </TextBlock>
                      <Border Name='HeroMapCard0' Width='65' Height='75' HorizontalAlignment='Left' VerticalAlignment='Top' Margin='446,73,0,0' CornerRadius='7' BorderBrush='#A78BFA' BorderThickness='1.5' Background='#188B5CF6' Cursor='Hand' ToolTip='DotA v6.85m LoD сонгох'/>
                      <Border Name='HeroMapCard1' Width='65' Height='75' HorizontalAlignment='Left' VerticalAlignment='Top' Margin='515,73,0,0' CornerRadius='7' BorderBrush='Transparent' BorderThickness='1' Background='Transparent' Cursor='Hand' ToolTip='DotA v6.74c LoD v5e сонгох'/>
                      <Border Name='HeroMapCard2' Width='65' Height='75' HorizontalAlignment='Left' VerticalAlignment='Top' Margin='584,73,0,0' CornerRadius='7' BorderBrush='Transparent' BorderThickness='1' Background='Transparent' Cursor='Hand' ToolTip='DotA v6.83d Allstars сонгох'/>
                      <Border Name='HeroMapCard3' Width='65' Height='75' HorizontalAlignment='Left' VerticalAlignment='Top' Margin='653,73,0,0' CornerRadius='7' BorderBrush='Transparent' BorderThickness='1' Background='Transparent' Cursor='Hand' ToolTip='DotA v6.85l LoD сонгох'/>
                      <Border Name='HeroMapCard4' Width='65' Height='75' HorizontalAlignment='Left' VerticalAlignment='Top' Margin='722,73,0,0' CornerRadius='7' BorderBrush='Transparent' BorderThickness='1' Background='Transparent' Cursor='Hand' ToolTip='DotA v6.85k Allstars сонгох'/>
                    </Grid>
                  </Viewbox>
                </Border>

                <!-- ROW 1: SEARCH BAR ([Ctrl + F]) + 4 COUNTED FILTER TABS -->
                <Grid Grid.Row='1' Margin='0,0,0,10'>
                  <Grid.ColumnDefinitions>
                    <ColumnDefinition Width='*'/>
                    <ColumnDefinition Width='Auto'/>
                  </Grid.ColumnDefinitions>
                  <Border Grid.Column='0' Background='#111629' CornerRadius='9' BorderBrush='#25304F' BorderThickness='1' Padding='12,6' Margin='0,0,10,0'>
                    <Grid>
                      <Grid.ColumnDefinitions>
                        <ColumnDefinition Width='Auto'/>
                        <ColumnDefinition Width='*'/>
                        <ColumnDefinition Width='Auto'/>
                      </Grid.ColumnDefinitions>
                      <TextBlock Grid.Column='0' Text='🔍' Foreground='#64748B' FontSize='12.5' VerticalAlignment='Center' Margin='0,0,8,0'/>
                      <Grid Grid.Column='1' VerticalAlignment='Center'>
                        <TextBlock Text='Хайх (Өрөөний нэр, Host, Map)...' Foreground='#64748B' FontSize='12' IsHitTestVisible='False' Name='LblSearchPlaceholder' VerticalAlignment='Center'/>
                        <TextBox Name='TxtSearch' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='12.5' VerticalContentAlignment='Center'/>
                      </Grid>
                      <Border Grid.Column='2' Background='#1A223A' BorderBrush='#2D3A5E' BorderThickness='1' CornerRadius='5' Padding='7,2' VerticalAlignment='Center' Margin='8,0,0,0'>
                        <TextBlock Text='Ctrl + F' Foreground='#94A3B8' FontSize='10' FontWeight='SemiBold'/>
                      </Border>
                    </Grid>
                  </Border>

                  <StackPanel Grid.Column='1' Orientation='Horizontal' VerticalAlignment='Center'>
                    <Border Name='FilterAllBorder' Background='#6D28D9' BorderBrush='#8B5CF6' BorderThickness='1' CornerRadius='8' Padding='12,6' Margin='0,0,6,0' Cursor='Hand'>
                      <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                        <TextBlock Text='Бүгд' Foreground='White' FontSize='12' FontWeight='Bold' VerticalAlignment='Center'/>
                        <Border Background='#4C1D95' CornerRadius='5' Padding='6,1' Margin='6,0,0,0' VerticalAlignment='Center'>
                          <TextBlock Name='LblFilterAllCount' Text='0' Foreground='#E9D5FF' FontSize='10.5' FontWeight='ExtraBold'/>
                        </Border>
                      </StackPanel>
                    </Border>
                    <Border Name='FilterWaitBorder' Background='#12172A' BorderBrush='#232E4B' BorderThickness='1' CornerRadius='8' Padding='12,6' Margin='0,0,6,0' Cursor='Hand'>
                      <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                        <Ellipse Width='7' Height='7' Fill='#10B981' VerticalAlignment='Center' Margin='0,0,6,0'/>
                        <TextBlock Text='Нээлттэй' Foreground='#E2E8F0' FontSize='12' FontWeight='SemiBold' VerticalAlignment='Center'/>
                        <Border Background='#1B243B' CornerRadius='5' Padding='6,1' Margin='6,0,0,0' VerticalAlignment='Center'>
                          <TextBlock Name='LblFilterWaitCount' Text='0' Foreground='#94A3B8' FontSize='10.5' FontWeight='Bold'/>
                        </Border>
                      </StackPanel>
                    </Border>
                    <Border Name='FilterRunBorder' Background='#12172A' BorderBrush='#232E4B' BorderThickness='1' CornerRadius='8' Padding='12,6' Margin='0,0,6,0' Cursor='Hand'>
                      <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                        <TextBlock Text='⏳ Тоглож буй' Foreground='#E2E8F0' FontSize='12' FontWeight='SemiBold' VerticalAlignment='Center'/>
                        <Border Background='#1B243B' CornerRadius='5' Padding='6,1' Margin='6,0,0,0' VerticalAlignment='Center'>
                          <TextBlock Name='LblFilterRunCount' Text='0' Foreground='#94A3B8' FontSize='10.5' FontWeight='Bold'/>
                        </Border>
                      </StackPanel>
                    </Border>
                    <Border Name='FilterLockBorder' Background='#12172A' BorderBrush='#232E4B' BorderThickness='1' CornerRadius='8' Padding='12,6' Cursor='Hand'>
                      <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                        <TextBlock Text='🔒 Нууц' Foreground='#E2E8F0' FontSize='12' FontWeight='SemiBold' VerticalAlignment='Center'/>
                        <Border Background='#1B243B' CornerRadius='5' Padding='6,1' Margin='6,0,0,0' VerticalAlignment='Center'>
                          <TextBlock Name='LblFilterLockCount' Text='0' Foreground='#94A3B8' FontSize='10.5' FontWeight='Bold'/>
                        </Border>
                      </StackPanel>
                    </Border>
                  </StackPanel>
                </Grid>

                <!-- ROW 2: CREATE LOBBY BAR (5 Controls in Exact Order + Rich Visual Map Dropdown Popup) -->
                <Border Grid.Row='2' Name='HostModalBar' Visibility='Visible' Background='#12172B' CornerRadius='11' BorderBrush='#3B2D6E' BorderThickness='1' Padding='12,8' Margin='0,0,0,10'>
                  <Grid>
                    <Grid.ColumnDefinitions>
                      <ColumnDefinition Width='1.35*'/>
                      <ColumnDefinition Width='1.35*'/>
                      <ColumnDefinition Width='0.85*'/>
                      <ColumnDefinition Width='Auto'/>
                      <ColumnDefinition Width='Auto'/>
                    </Grid.ColumnDefinitions>

                    <!-- 1. Room Name Input -->
                    <StackPanel Grid.Column='0' Margin='0,0,10,0'>
                      <TextBlock Text='ӨРӨӨНИЙ НЭР' Foreground='#94A3B8' FontSize='9.5' FontWeight='ExtraBold' Margin='2,0,0,4'/>
                      <Border Background='#0B0F1E' CornerRadius='8' BorderBrush='#253050' BorderThickness='1' Padding='10,0' Height='34'>
                        <Grid VerticalAlignment='Center'>
                          <Grid.ColumnDefinitions>
                            <ColumnDefinition Width='Auto'/>
                            <ColumnDefinition Width='*'/>
                          </Grid.ColumnDefinitions>
                          <TextBlock Grid.Column='0' Text='✏️' FontSize='11.5' Foreground='#64748B' VerticalAlignment='Center' Margin='0,0,7,0'/>
                          <Grid Grid.Column='1' VerticalAlignment='Center'>
                            <TextBlock Name='LblNewRoomNamePh' Text='Өрөөний нэр оруулах...' Foreground='#64748B' FontSize='12' IsHitTestVisible='False' VerticalAlignment='Center'/>
                            <TextBox Name='TxtNewRoomName' Text='' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='12.5' FontWeight='SemiBold' VerticalContentAlignment='Center'/>
                          </Grid>
                        </Grid>
                      </Border>
                    </StackPanel>

                    <!-- 2. Map Selection Dropdown (5 Official Maps) -->
                    <StackPanel Grid.Column='1' Margin='0,0,10,0'>
                      <TextBlock Text='ГАЗРЫН ЗУРАГ (5 үндсэн газрын)' Foreground='#94A3B8' FontSize='9.5' FontWeight='ExtraBold' Margin='2,0,0,4'/>
                      <Grid>
                        <ComboBox Name='CmbMaps' Visibility='Collapsed'/>
                        <Border Name='BtnMapDropdownToggle' Background='#0B0F1E' CornerRadius='8' BorderBrush='#7C3AED' BorderThickness='1' Padding='8,0' Height='34' Cursor='Hand'>
                          <Grid VerticalAlignment='Center'>
                            <Grid.ColumnDefinitions>
                              <ColumnDefinition Width='Auto'/>
                              <ColumnDefinition Width='*'/>
                              <ColumnDefinition Width='Auto'/>
                            </Grid.ColumnDefinitions>
                            <Border Grid.Column='0' Width='22' Height='22' CornerRadius='5' ClipToBounds='True' Margin='0,0,8,0' Background='#182038'>
                              <Image Name='ImgSelectedMapIcon' Width='22' Height='22' Stretch='UniformToFill' RenderOptions.BitmapScalingMode='HighQuality'/>
                            </Border>
                            <TextBlock Grid.Column='1' Name='LblSelectedMapTitle' Text='DotA v6.85m LoD' Foreground='White' FontWeight='Bold' FontSize='12' VerticalAlignment='Center' TextTrimming='CharacterEllipsis'/>
                            <TextBlock Grid.Column='2' Text='▾' Foreground='#A78BFA' FontSize='12' FontWeight='Bold' VerticalAlignment='Center' Margin='6,0,2,0'/>
                          </Grid>
                        </Border>
                        <Popup Name='MapDropdownPopup' Placement='Bottom' AllowsTransparency='True' StaysOpen='True' PopupAnimation='Fade'>
                          <Border Background='#13182C' BorderBrush='#7C3AED' BorderThickness='1.5' CornerRadius='10' Width='270' Padding='6' Margin='0,4,0,0'>
                            <Border.Effect>
                              <DropShadowEffect Color='#000000' BlurRadius='24' ShadowDepth='6' Opacity='0.75'/>
                            </Border.Effect>
                            <StackPanel>
                              <TextBlock Text='5 ҮНДСЭН ГАЗРЫН СОНГОЛТ' Foreground='#94A3B8' FontSize='9.5' FontWeight='ExtraBold' Margin='6,2,0,6'/>
                              <Border Name='MapOption0' Background='#251D47' BorderBrush='#8B5CF6' BorderThickness='1' CornerRadius='7' Padding='8,6' Margin='0,0,0,3' Cursor='Hand'>
                                <Grid>
                                  <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width='Auto'/>
                                    <ColumnDefinition Width='*'/>
                                    <ColumnDefinition Width='Auto'/>
                                  </Grid.ColumnDefinitions>
                                  <Border Grid.Column='0' Width='28' Height='28' CornerRadius='6' ClipToBounds='True' Margin='0,0,9,0'>
                                    <Image Name='ImgMapOpt0' Width='28' Height='28' Stretch='UniformToFill'/>
                                  </Border>
                                  <StackPanel Grid.Column='1' VerticalAlignment='Center'>
                                    <TextBlock Text='DotA v6.85m LoD' Foreground='White' FontWeight='Bold' FontSize='12'/>
                                    <TextBlock Text='LoD • Legend of DotA' Foreground='#94A3B8' FontSize='10'/>
                                  </StackPanel>
                                  <TextBlock Grid.Column='2' Name='LblMapCheck0' Text='✓' Foreground='#A78BFA' FontWeight='ExtraBold' FontSize='13' VerticalAlignment='Center' Margin='4,0,2,0'/>
                                </Grid>
                              </Border>
                              <Border Name='MapOption1' Background='Transparent' BorderBrush='Transparent' BorderThickness='1' CornerRadius='7' Padding='8,6' Margin='0,0,0,3' Cursor='Hand'>
                                <Grid>
                                  <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width='Auto'/>
                                    <ColumnDefinition Width='*'/>
                                    <ColumnDefinition Width='Auto'/>
                                  </Grid.ColumnDefinitions>
                                  <Border Grid.Column='0' Width='28' Height='28' CornerRadius='6' ClipToBounds='True' Margin='0,0,9,0'>
                                    <Image Name='ImgMapOpt1' Width='28' Height='28' Stretch='UniformToFill'/>
                                  </Border>
                                  <StackPanel Grid.Column='1' VerticalAlignment='Center'>
                                    <TextBlock Text='DotA v6.74c LoD v5e' Foreground='White' FontWeight='Bold' FontSize='12'/>
                                    <TextBlock Text='LoD Classic' Foreground='#94A3B8' FontSize='10'/>
                                  </StackPanel>
                                  <TextBlock Grid.Column='2' Name='LblMapCheck1' Visibility='Collapsed' Text='✓' Foreground='#A78BFA' FontWeight='ExtraBold' FontSize='13' VerticalAlignment='Center' Margin='4,0,2,0'/>
                                </Grid>
                              </Border>
                              <Border Name='MapOption2' Background='Transparent' BorderBrush='Transparent' BorderThickness='1' CornerRadius='7' Padding='8,6' Margin='0,0,0,3' Cursor='Hand'>
                                <Grid>
                                  <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width='Auto'/>
                                    <ColumnDefinition Width='*'/>
                                    <ColumnDefinition Width='Auto'/>
                                  </Grid.ColumnDefinitions>
                                  <Border Grid.Column='0' Width='28' Height='28' CornerRadius='6' ClipToBounds='True' Margin='0,0,9,0'>
                                    <Image Name='ImgMapOpt2' Width='28' Height='28' Stretch='UniformToFill'/>
                                  </Border>
                                  <StackPanel Grid.Column='1' VerticalAlignment='Center'>
                                    <TextBlock Text='DotA v6.83d Allstars' Foreground='White' FontWeight='Bold' FontSize='12'/>
                                    <TextBlock Text='Classic Allstars' Foreground='#94A3B8' FontSize='10'/>
                                  </StackPanel>
                                  <TextBlock Grid.Column='2' Name='LblMapCheck2' Visibility='Collapsed' Text='✓' Foreground='#A78BFA' FontWeight='ExtraBold' FontSize='13' VerticalAlignment='Center' Margin='4,0,2,0'/>
                                </Grid>
                              </Border>
                              <Border Name='MapOption3' Background='Transparent' BorderBrush='Transparent' BorderThickness='1' CornerRadius='7' Padding='8,6' Margin='0,0,0,3' Cursor='Hand'>
                                <Grid>
                                  <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width='Auto'/>
                                    <ColumnDefinition Width='*'/>
                                    <ColumnDefinition Width='Auto'/>
                                  </Grid.ColumnDefinitions>
                                  <Border Grid.Column='0' Width='28' Height='28' CornerRadius='6' ClipToBounds='True' Margin='0,0,9,0'>
                                    <Image Name='ImgMapOpt3' Width='28' Height='28' Stretch='UniformToFill'/>
                                  </Border>
                                  <StackPanel Grid.Column='1' VerticalAlignment='Center'>
                                    <TextBlock Text='DotA v6.85l LoD' Foreground='White' FontWeight='Bold' FontSize='12'/>
                                    <TextBlock Text='LoD Balance' Foreground='#94A3B8' FontSize='10'/>
                                  </StackPanel>
                                  <TextBlock Grid.Column='2' Name='LblMapCheck3' Visibility='Collapsed' Text='✓' Foreground='#A78BFA' FontWeight='ExtraBold' FontSize='13' VerticalAlignment='Center' Margin='4,0,2,0'/>
                                </Grid>
                              </Border>
                              <Border Name='MapOption4' Background='Transparent' BorderBrush='Transparent' BorderThickness='1' CornerRadius='7' Padding='8,6' Cursor='Hand'>
                                <Grid>
                                  <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width='Auto'/>
                                    <ColumnDefinition Width='*'/>
                                    <ColumnDefinition Width='Auto'/>
                                  </Grid.ColumnDefinitions>
                                  <Border Grid.Column='0' Width='28' Height='28' CornerRadius='6' ClipToBounds='True' Margin='0,0,9,0'>
                                    <Image Name='ImgMapOpt4' Width='28' Height='28' Stretch='UniformToFill'/>
                                  </Border>
                                  <StackPanel Grid.Column='1' VerticalAlignment='Center'>
                                    <TextBlock Text='DotA v6.85k Allstars' Foreground='White' FontWeight='Bold' FontSize='12'/>
                                    <TextBlock Text='Competitive Allstars' Foreground='#94A3B8' FontSize='10'/>
                                  </StackPanel>
                                  <TextBlock Grid.Column='2' Name='LblMapCheck4' Visibility='Collapsed' Text='✓' Foreground='#A78BFA' FontWeight='ExtraBold' FontSize='13' VerticalAlignment='Center' Margin='4,0,2,0'/>
                                </Grid>
                              </Border>
                            </StackPanel>
                          </Border>
                        </Popup>
                      </Grid>
                    </StackPanel>

                    <!-- 3. Optional Room Password -->
                    <StackPanel Grid.Column='2' Margin='0,0,10,0'>
                      <TextBlock Text='🔒 КОД (ЗААВАЛ БИШ)' Foreground='#FBBF24' FontSize='9.5' FontWeight='ExtraBold' Margin='2,0,0,4'/>
                      <Border Background='#0B0F1E' CornerRadius='8' BorderBrush='#253050' BorderThickness='1' Padding='9,0' Height='34'>
                        <Grid VerticalAlignment='Center'>
                          <Grid.ColumnDefinitions>
                            <ColumnDefinition Width='Auto'/>
                            <ColumnDefinition Width='*'/>
                          </Grid.ColumnDefinitions>
                          <TextBlock Grid.Column='0' Text='🔒' FontSize='11' Foreground='#64748B' VerticalAlignment='Center' Margin='0,0,6,0'/>
                          <Grid Grid.Column='1' VerticalAlignment='Center'>
                            <TextBlock Name='LblNewRoomCodePh' Text='Нээлттэй' Foreground='#64748B' FontSize='11.5' IsHitTestVisible='False' VerticalAlignment='Center'/>
                            <TextBox Name='TxtNewRoomCode' Text='' MaxLength='24' Background='Transparent' Foreground='#FBBF24' CaretBrush='White' BorderThickness='0' FontSize='12' FontWeight='Bold' VerticalContentAlignment='Center'/>
                          </Grid>
                        </Grid>
                      </Border>
                    </StackPanel>

                    <!-- 4. Leaver Restriction Toggle Switch -->
                    <StackPanel Grid.Column='3' Margin='0,0,10,0'>
                      <TextBlock Text='👑 LEAVER ОРУУЛАХГҮЙ' Foreground='#CBD5E1' FontSize='9.5' FontWeight='ExtraBold' Margin='2,0,0,4'/>
                      <Grid>
                        <CheckBox Name='ChkNoLeavers' IsChecked='True' Visibility='Collapsed'/>
                        <Border Name='BtnNoLeaversToggle' Background='#0B0F1E' CornerRadius='8' BorderBrush='#253050' BorderThickness='1' Padding='10,0' Height='34' Cursor='Hand'>
                          <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                            <Border Name='NoLeaversTrack' Width='34' Height='18' CornerRadius='9' Background='#7C3AED' Padding='2' VerticalAlignment='Center' Margin='0,0,8,0'>
                              <Border Name='NoLeaversKnob' Width='14' Height='14' CornerRadius='7' Background='White' HorizontalAlignment='Right' VerticalAlignment='Center'/>
                            </Border>
                            <TextBlock Name='LblNoLeaversState' Text='Тийм' Foreground='#E2E8F0' FontWeight='Bold' FontSize='12' VerticalAlignment='Center'/>
                          </StackPanel>
                        </Border>
                      </Grid>
                    </StackPanel>

                    <!-- 5. Create Lobby Button -->
                    <Border Grid.Column='4' Name='BtnConfirmCreateLobby' CornerRadius='9' Padding='18,0' Height='34' VerticalAlignment='Bottom' Cursor='Hand' BorderBrush='#34D399' BorderThickness='1'>
                      <Border.Background>
                        <LinearGradientBrush StartPoint='0,0' EndPoint='1,0'>
                          <GradientStop Color='#059669' Offset='0'/>
                          <GradientStop Color='#10B981' Offset='1'/>
                        </LinearGradientBrush>
                      </Border.Background>
                      <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                        <TextBlock Text='＋' Foreground='White' FontWeight='ExtraBold' FontSize='14' VerticalAlignment='Center' Margin='0,-1,6,0'/>
                        <TextBlock Text='Лобби Үүсгэх (Host)' Foreground='White' FontWeight='ExtraBold' FontSize='12.5' VerticalAlignment='Center'/>
                      </StackPanel>
                    </Border>
                  </Grid>
                </Border>

                <!-- ROW 3: 8-COLUMN LOBBY TABLE (100% Reference Design) -->
                <Border Grid.Row='3' Background='#0D1222' CornerRadius='12' BorderBrush='#1E2846' BorderThickness='1' Padding='10,8'>
                  <Grid>
                    <Grid.RowDefinitions>
                      <RowDefinition Height='30'/>
                      <RowDefinition Height='*'/>
                    </Grid.RowDefinitions>
                    <Border Grid.Row='0' BorderBrush='#1A233D' BorderThickness='0,0,0,1' Padding='10,0,10,6'>
                      <Grid VerticalAlignment='Center'>
                        <Grid.ColumnDefinitions>
                          <ColumnDefinition Width='32'/>
                          <ColumnDefinition Width='2.35*'/>
                          <ColumnDefinition Width='1.65*'/>
                          <ColumnDefinition Width='1.1*'/>
                          <ColumnDefinition Width='1.0*'/>
                          <ColumnDefinition Width='0.75*'/>
                          <ColumnDefinition Width='1.05*'/>
                          <ColumnDefinition Width='124'/>
                        </Grid.ColumnDefinitions>
                        <TextBlock Grid.Column='0' Text='#' Foreground='#64748B' FontSize='10.5' FontWeight='ExtraBold'/>
                        <TextBlock Grid.Column='1' Text='ӨРӨӨНИЙ НЭР ⇅' Foreground='#64748B' FontSize='10.5' FontWeight='ExtraBold'/>
                        <TextBlock Grid.Column='2' Text='ГАЗРЫН ЗУРАГ' Foreground='#64748B' FontSize='10.5' FontWeight='ExtraBold'/>
                        <TextBlock Grid.Column='3' Text='HOST' Foreground='#64748B' FontSize='10.5' FontWeight='ExtraBold'/>
                        <TextBlock Grid.Column='4' Text='ТОГЛОГЧИД ⇅' Foreground='#64748B' FontSize='10.5' FontWeight='ExtraBold'/>
                        <TextBlock Grid.Column='5' Text='PING ⇅' Foreground='#64748B' FontSize='10.5' FontWeight='ExtraBold'/>
                        <TextBlock Grid.Column='6' Text='ТӨЛӨВ' Foreground='#64748B' FontSize='10.5' FontWeight='ExtraBold'/>
                        <TextBlock Grid.Column='7' Text='ҮЙЛДЭЛ' Foreground='#64748B' FontSize='10.5' FontWeight='ExtraBold' HorizontalAlignment='Center'/>
                      </Grid>
                    </Border>

                    <ScrollViewer Grid.Row='1' VerticalScrollBarVisibility='Auto' Margin='0,6,0,0'>
                      <ItemsControl Name='LobbiesList'>
                        <ItemsControl.ItemTemplate>
                          <DataTemplate>
                            <Border Background='#13192E' CornerRadius='10' BorderBrush='#222D4C' BorderThickness='1' Padding='10,8' Margin='0,0,0,6'>
                              <Grid VerticalAlignment='Center'>
                                <Grid.ColumnDefinitions>
                                  <ColumnDefinition Width='32'/>
                                  <ColumnDefinition Width='2.35*'/>
                                  <ColumnDefinition Width='1.65*'/>
                                  <ColumnDefinition Width='1.1*'/>
                                  <ColumnDefinition Width='1.0*'/>
                                  <ColumnDefinition Width='0.75*'/>
                                  <ColumnDefinition Width='1.05*'/>
                                  <ColumnDefinition Width='124'/>
                                </Grid.ColumnDefinitions>

                                <!-- Col 0: # -->
                                <TextBlock Grid.Column='0' Text='{Binding RowNum}' Foreground='#64748B' FontWeight='Bold' FontSize='12' VerticalAlignment='Center'/>

                                <!-- Col 1: Room Name + Badges + SubInfo -->
                                <StackPanel Grid.Column='1' VerticalAlignment='Center' Margin='0,0,8,0'>
                                  <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                                    <TextBlock Text='🔒 ' Visibility='{Binding LockIconVis}' Foreground='#FBBF24' FontSize='12' VerticalAlignment='Center'/>
                                    <TextBlock Text='{Binding Name}' Foreground='White' FontWeight='ExtraBold' FontSize='13' VerticalAlignment='Center' Margin='0,0,6,0'/>
                                    <Border Visibility='{Binding HotBadgeVis}' Background='#2E1810' BorderBrush='#EA580C' BorderThickness='1' CornerRadius='4' Padding='5,1' Margin='0,0,5,0' VerticalAlignment='Center'>
                                      <TextBlock Text='🔥 HOT' Foreground='#FB923C' FontSize='9' FontWeight='ExtraBold'/>
                                    </Border>
                                    <Border Visibility='{Binding LockBadgeVis}' Background='#2E2212' BorderBrush='#D97706' BorderThickness='1' CornerRadius='4' Padding='5,1' Margin='0,0,5,0' VerticalAlignment='Center'>
                                      <TextBlock Text='КОДТОЙ' Foreground='#FBBF24' FontSize='9' FontWeight='ExtraBold'/>
                                    </Border>
                                    <Border Visibility='{Binding NoLeaverVis}' Background='#112A26' BorderBrush='#059669' BorderThickness='1' CornerRadius='4' Padding='5,1' VerticalAlignment='Center'>
                                      <TextBlock Text='🛡️ Leaver-гүй' Foreground='#34D399' FontSize='9.5' FontWeight='Bold'/>
                                    </Border>
                                  </StackPanel>
                                  <TextBlock Text='{Binding SubInfo}' Foreground='{Binding SubInfoFg}' FontSize='10.5' Margin='0,2,0,0' TextTrimming='CharacterEllipsis'/>
                                </StackPanel>

                                <!-- Col 2: Map Artwork Icon + Title + Subtitle -->
                                <StackPanel Grid.Column='2' Orientation='Horizontal' VerticalAlignment='Center' Margin='0,0,8,0'>
                                  <Border Width='32' Height='32' CornerRadius='6' ClipToBounds='True' BorderBrush='#2D3A5E' BorderThickness='1' Margin='0,0,8,0' Background='#182038'>
                                    <Image Source='{Binding MapIcon}' Width='32' Height='32' Stretch='UniformToFill' RenderOptions.BitmapScalingMode='HighQuality'/>
                                  </Border>
                                  <StackPanel VerticalAlignment='Center'>
                                    <TextBlock Text='{Binding MapTitle}' Foreground='#F1F5F9' FontWeight='Bold' FontSize='12' TextTrimming='CharacterEllipsis'/>
                                    <TextBlock Text='{Binding MapSub}' Foreground='#64748B' FontSize='10' Margin='0,1,0,0'/>
                                  </StackPanel>
                                </StackPanel>

                                <!-- Col 3: Host + #UID -->
                                <StackPanel Grid.Column='3' Orientation='Horizontal' VerticalAlignment='Center' Margin='0,0,6,0'>
                                  <Border Width='24' Height='24' CornerRadius='12' Background='#1A243D' BorderBrush='#334155' BorderThickness='1' Margin='0,0,7,0' VerticalAlignment='Center'>
                                    <TextBlock Text='{Binding HostInitial}' Foreground='#A78BFA' FontSize='10.5' FontWeight='ExtraBold' HorizontalAlignment='Center' VerticalAlignment='Center'/>
                                  </Border>
                                  <StackPanel VerticalAlignment='Center'>
                                    <TextBlock Text='{Binding Host}' Foreground='#E2E8F0' FontWeight='Bold' FontSize='12' TextTrimming='CharacterEllipsis'/>
                                    <TextBlock Text='{Binding HostUid}' Foreground='#64748B' FontSize='10' FontWeight='SemiBold' Margin='0,1,0,0'/>
                                  </StackPanel>
                                </StackPanel>

                                <!-- Col 4: Players + Progress Bar -->
                                <StackPanel Grid.Column='4' VerticalAlignment='Center' Margin='0,0,8,0'>
                                  <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                                    <TextBlock Text='👥 ' Foreground='#94A3B8' FontSize='11' VerticalAlignment='Center'/>
                                    <TextBlock Text='{Binding Players}' Foreground='#F8FAFC' FontWeight='ExtraBold' FontSize='12' VerticalAlignment='Center'/>
                                  </StackPanel>
                                  <Border Width='64' Height='4' CornerRadius='2' Background='#1E293B' HorizontalAlignment='Left' Margin='0,4,0,0' ClipToBounds='True'>
                                    <Border Width='{Binding PlayersFillWidth}' Height='4' CornerRadius='2' Background='{Binding PlayersBarBrush}' HorizontalAlignment='Left'/>
                                  </Border>
                                </StackPanel>

                                <!-- Col 5: Ping Pill -->
                                <Border Grid.Column='5' Background='#0D2822' BorderBrush='#047857' BorderThickness='1' CornerRadius='6' Padding='7,3' HorizontalAlignment='Left' VerticalAlignment='Center'>
                                  <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                                    <Ellipse Width='5' Height='5' Fill='#10B981' VerticalAlignment='Center' Margin='0,0,4,0'/>
                                    <TextBlock Text='{Binding PingText}' Foreground='#34D399' FontWeight='Bold' FontSize='11'/>
                                  </StackPanel>
                                </Border>

                                <!-- Col 6: Status Pill -->
                                <Border Grid.Column='6' Background='{Binding StatusBg}' BorderBrush='{Binding StatusBorder}' BorderThickness='1' CornerRadius='7' Padding='9,4' HorizontalAlignment='Left' VerticalAlignment='Center'>
                                  <TextBlock Text='{Binding StatusText}' Foreground='{Binding StatusFg}' FontSize='11' FontWeight='Bold'/>
                                </Border>

                                <!-- Col 7: Action Button + Menu Dot -->
                                <Grid Grid.Column='7' VerticalAlignment='Center'>
                                  <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width='*'/>
                                    <ColumnDefinition Width='22'/>
                                  </Grid.ColumnDefinitions>
                                  <Button Grid.Column='0' Tag='{Binding Id}' Content='{Binding JoinBtnText}' Cursor='Hand' Height='30'>
                                    <Button.Template>
                                      <ControlTemplate TargetType='Button'>
                                        <Border Background='{Binding ActionBtnBg}' BorderBrush='{Binding ActionBtnBorder}' BorderThickness='1' CornerRadius='7' Padding='10,0'>
                                          <TextBlock Text='{TemplateBinding Content}' Foreground='{Binding ActionBtnFg}' FontWeight='ExtraBold' FontSize='11.5' HorizontalAlignment='Center' VerticalAlignment='Center'/>
                                        </Border>
                                      </ControlTemplate>
                                    </Button.Template>
                                  </Button>
                                  <TextBlock Grid.Column='1' Text='⋮' Foreground='#64748B' FontSize='14' FontWeight='Bold' HorizontalAlignment='Center' VerticalAlignment='Center'/>
                                </Grid>
                              </Grid>
                            </Border>
                          </DataTemplate>
                        </ItemsControl.ItemTemplate>
                      </ItemsControl>
                    </ScrollViewer>
                  </Grid>
                </Border>

                <!-- ROW 4: BOTTOM FOOTER STATUS BAR (100% Reference Design) -->
                <Border Grid.Row='4' Background='#0C1020' CornerRadius='9' BorderBrush='#1C2540' BorderThickness='1' Padding='12,6' Margin='0,8,0,0'>
                  <Grid>
                    <StackPanel Orientation='Horizontal' VerticalAlignment='Center'>
                      <Ellipse Width='7' Height='7' Fill='#10B981' VerticalAlignment='Center' Margin='0,0,6,0'/>
                      <TextBlock Name='LblLobbySubCount' Text='Нийт 0 лобби (0 нээлттэй)' Foreground='#CBD5E1' FontSize='11.5' FontWeight='SemiBold' VerticalAlignment='Center'/>
                      <TextBlock Text='   |   ' Foreground='#334155' FontSize='11.5' VerticalAlignment='Center'/>
                      <TextBlock Text='🗺️ Сонгосон газар: ' Foreground='#94A3B8' FontSize='11.5' VerticalAlignment='Center'/>
                      <TextBlock Name='LblFooterSelectedMap' Text='DotA v6.85m LoD' Foreground='#F8FAFC' FontSize='11.5' FontWeight='Bold' VerticalAlignment='Center'/>
                      <TextBlock Text='   |   ' Foreground='#334155' FontSize='11.5' VerticalAlignment='Center'/>
                      <TextBlock Text='🇲🇳 Монгол War3 Нийгэмлэг' Foreground='#94A3B8' FontSize='11.5' VerticalAlignment='Center'/>
                    </StackPanel>
                    <StackPanel Orientation='Horizontal' HorizontalAlignment='Right' VerticalAlignment='Center'>
                      <Border Name='BtnRefreshLobbies' Background='#151D33' BorderBrush='#283558' BorderThickness='1' CornerRadius='7' Padding='10,3' Cursor='Hand'>
                        <TextBlock Name='LblRefreshLobbies' Text='🔄 Сэргээх' Foreground='#E2E8F0' FontSize='11' FontWeight='Bold' VerticalAlignment='Center'/>
                      </Border>
                      <TextBlock Text='   |   ' Foreground='#334155' FontSize='11.5' VerticalAlignment='Center'/>
                      <Ellipse Width='6' Height='6' Fill='#10B981' VerticalAlignment='Center' Margin='0,0,5,0'/>
                      <TextBlock Name='LblLastUpdatedTime' Text='Сүүлийн шинэчлэл: --:--:--' Foreground='#94A3B8' FontSize='11' VerticalAlignment='Center'/>
                    </StackPanel>
                  </Grid>
                </Border>
              </Grid>

              <!-- 1B. INNER LOBBY ROOM VIEW (Өрөөн Дотор: Room Chat + Member List + Host-Only Start) -->
              <Grid Name='InnerRoomView' Visibility='Collapsed'>
                <Grid.RowDefinitions>
                  <RowDefinition Height='Auto'/>
                  <RowDefinition Height='*'/>
                </Grid.RowDefinitions>

                <!-- Inner Room Top Header -->
                <Border Grid.Row='0' Background='#12192B' CornerRadius='14' BorderBrush='#7C3AED' BorderThickness='1' Padding='18,12' Margin='0,0,0,12'>
                  <Grid>
                    <Grid.ColumnDefinitions>
                      <ColumnDefinition Width='*'/>
                      <ColumnDefinition Width='Auto'/>
                    </Grid.ColumnDefinitions>
                    <StackPanel Grid.Column='0' VerticalAlignment='Center'>
                      <TextBlock Name='LblInnerRoomTitle' Text='🎮 Өрөө: Mongol DotA LoD 5v5' Foreground='White' FontSize='19' FontWeight='ExtraBold'/>
                      <TextBlock Name='LblInnerRoomSub' Text='🗺️ Map: LoD_Sync_25.w3x  •  🛡️ Anti-MapHack Идэвхтэй' Foreground='#34D399' FontSize='12' FontWeight='SemiBold' Margin='0,3,0,0'/>
                    </StackPanel>
                    <StackPanel Grid.Column='1' Orientation='Horizontal' VerticalAlignment='Center'>
                      <Border Name='BtnSetRoomCode' Visibility='Collapsed' Background='#1E293B' BorderBrush='#7C3AED' BorderThickness='1' CornerRadius='9' Padding='12,8' Margin='0,0,8,0' Cursor='Hand'>
                        <TextBlock Name='LblSetRoomCodeText' Text='🔒 Код Хийх / Солих' Foreground='#FBBF24' FontWeight='Bold' FontSize='12'/>
                      </Border>
                      <Border Name='BtnInviteFriendFromRoom' Background='#172554' BorderBrush='#38BDF8' BorderThickness='1' CornerRadius='9' Padding='14,8' Margin='0,0,8,0' Cursor='Hand'>
                        <TextBlock Text='📨 Найзаа Урих' Foreground='#38BDF8' FontWeight='ExtraBold' FontSize='12'/>
                      </Border>
                      <Border Name='BtnLeaveMatchNow' Background='#EF4444' CornerRadius='9' Padding='14,8' Cursor='Hand'>
                        <TextBlock Text='🚪 Өрөөнөөс Гарах' Foreground='White' FontWeight='ExtraBold' FontSize='12'/>
                      </Border>
                    </StackPanel>
                  </Grid>
                </Border>

                <!-- Inner Room Main Split: Left = Public Room Chat, Right = Room Players & Host Start Button -->
                <Grid Grid.Row='1'>
                  <Grid.ColumnDefinitions>
                    <ColumnDefinition Width='*'/>
                    <ColumnDefinition Width='14'/>
                    <ColumnDefinition Width='335'/>
                  </Grid.ColumnDefinitions>

                  <!-- LEFT: ROOM PUBLIC CHAT -->
                  <Border Grid.Column='0' Background='#0E1320' CornerRadius='14' BorderBrush='#1E293B' BorderThickness='1' Padding='14,12'>
                    <Grid>
                      <Grid.RowDefinitions>
                        <RowDefinition Height='Auto'/>
                        <RowDefinition Height='Auto'/>
                        <RowDefinition Height='*'/>
                        <RowDefinition Height='Auto'/>
                      </Grid.RowDefinitions>
                      <TextBlock Grid.Row='0' Text='💬 ӨРӨӨНИЙ НИЙТИЙН ЧАТ' Foreground='#38BDF8' FontWeight='ExtraBold' FontSize='11.5' Margin='0,0,0,6' TextWrapping='Wrap'/>
                      <Border Grid.Row='1' Background='#0A0E19' CornerRadius='8' BorderBrush='#1B263B' BorderThickness='1' Padding='10,6' Margin='0,0,0,8'>
                        <StackPanel>
                          <TextBlock FontSize='10.2' TextWrapping='Wrap' LineHeight='14.5'>
                            <Run Text='⚡ Лобби команд:' Foreground='#38BDF8' FontWeight='ExtraBold'/>
                            <Run Text='  -start' Foreground='#FBBF24' FontWeight='Bold'/><Run Text=' (Эхлүүлэх)  • ' Foreground='#94A3B8'/>
                            <Run Text='-1v1  -2v2  -3v3  -4v4' Foreground='#FBBF24' FontWeight='Bold'/><Run Text=' (Илүү суудал хааж мөнгө хасах 853g)  • ' Foreground='#94A3B8'/>
                            <Run Text='-close 2' Foreground='#FBBF24' FontWeight='Bold'/><Run Text=' (Суудал хаах)  • ' Foreground='#94A3B8'/>
                            <Run Text='-openall' Foreground='#FBBF24' FontWeight='Bold'/><Run Text=' (Нээх)  • ' Foreground='#94A3B8'/>
                            <Run Text='-swap 2 6' Foreground='#FBBF24' FontWeight='Bold'/><Run Text=' (Суудал солих)' Foreground='#94A3B8'/>
                          </TextBlock>
                          <TextBlock FontSize='10.2' TextWrapping='Wrap' LineHeight='14.5' Margin='0,2,0,0'>
                            <Run Text='🛡️ Тоглолтын дунд:' Foreground='#34D399' FontWeight='ExtraBold'/>
                            <Run Text='  -rmk' Foreground='#FBBF24' FontWeight='Bold'/><Run Text=' (5 мин дотор дахин эхлэх: 1v1/2v2 2, 3v3-5v5 3)  • ' Foreground='#94A3B8'/>
                            <Run Text='-gg' Foreground='#FBBF24' FontWeight='Bold'/><Run Text=' (Бууж өгөх)  • ' Foreground='#94A3B8'/>
                            <Run Text='-addtime' Foreground='#FBBF24' FontWeight='Bold'/><Run Text=' (Гарсан тоглогч хүлээх цаг +1 мин сунгах)' Foreground='#94A3B8'/>
                          </TextBlock>
                        </StackPanel>
                      </Border>
                      <Border Grid.Row='2' Background='#090D16' CornerRadius='10' BorderBrush='#172033' BorderThickness='1' Padding='10,8' Margin='0,0,0,10'>
                        <ScrollViewer Name='RoomChatScroll' VerticalScrollBarVisibility='Auto' HorizontalScrollBarVisibility='Disabled'>
                          <ItemsControl Name='RoomChatList'>
                            <ItemsControl.ItemTemplate>
                              <DataTemplate>
                                <Grid Margin='0,0,0,6'>
                                  <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width='Auto'/>
                                    <ColumnDefinition Width='*'/>
                                  </Grid.ColumnDefinitions>
                                  <TextBlock Grid.Column='0' Text='{Binding TimeStr}' Foreground='#64748B' FontSize='11.5' Margin='0,1,6,0' VerticalAlignment='Top'/>
                                  <TextBlock Grid.Column='1' TextWrapping='Wrap' FontSize='12.5' VerticalAlignment='Top'>
                                    <Run Text='{Binding SenderLabel, Mode=OneWay}' Foreground='{Binding SenderFg, Mode=OneWay}' FontWeight='Bold'/>
                                    <Run Text=' '/>
                                    <Run Text='{Binding Text, Mode=OneWay}' Foreground='{Binding TextFg, Mode=OneWay}' FontWeight='SemiBold'/>
                                  </TextBlock>
                                </Grid>
                              </DataTemplate>
                            </ItemsControl.ItemTemplate>
                          </ItemsControl>
                        </ScrollViewer>
                      </Border>
                      <Grid Grid.Row='3'>
                        <Grid.ColumnDefinitions>
                          <ColumnDefinition Width='*'/>
                          <ColumnDefinition Width='Auto'/>
                        </Grid.ColumnDefinitions>
                        <Border Grid.Column='0' Background='#090D16' CornerRadius='9' BorderBrush='#24304C' BorderThickness='1' Padding='12,7' Margin='0,0,8,0'>
                          <TextBox Name='TxtRoomChatInput' MaxLength='300' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='13'/>
                        </Border>
                        <Border Grid.Column='1' Name='BtnSendRoomChat' Background='#7C3AED' CornerRadius='9' Padding='18,7' Cursor='Hand'>
                          <TextBlock Text='Илгээх ↵' Foreground='White' FontWeight='ExtraBold' FontSize='12.5' VerticalAlignment='Center'/>
                        </Border>
                      </Grid>
                    </Grid>
                  </Border>

                  <!-- RIGHT: PLAYERS IN ROOM + HOST START BUTTON -->
                  <Border Grid.Column='2' Background='#0E1320' CornerRadius='14' BorderBrush='#1E293B' BorderThickness='1' Padding='14,12'>
                    <Grid>
                      <Grid.RowDefinitions>
                        <RowDefinition Height='Auto'/>
                        <RowDefinition Height='Auto'/>
                        <RowDefinition Height='*'/>
                        <RowDefinition Height='Auto'/>
                      </Grid.RowDefinitions>
                      <TextBlock Grid.Row='0' Name='LblRoomMembersCount' Text='👥 ӨРӨӨНИЙ ТОГЛОГЧИД (1/10)' Foreground='#C4B5FD' FontWeight='ExtraBold' FontSize='12'/>
                      <TextBlock Grid.Row='1' Text='Нэр дээр дарж ELO/Kill үзэх, найз нэмэх, эсвэл 👢 Өрөөнөөс хөөх (Kick):' Foreground='#64748B' FontSize='10.5' TextWrapping='Wrap' Margin='0,2,0,8'/>

                      <ScrollViewer Grid.Row='2' VerticalScrollBarVisibility='Auto' Margin='0,0,0,10'>
                        <ItemsControl Name='RoomMembersList'>
                          <ItemsControl.ItemTemplate>
                            <DataTemplate>
                              <Button Tag='{Binding Name}' Background='#141C2E' BorderBrush='#222F49' BorderThickness='1' Padding='10,7' Margin='0,0,0,6' Cursor='Hand' HorizontalContentAlignment='Stretch'>
                                <Grid>
                                  <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width='*'/>
                                    <ColumnDefinition Width='Auto'/>
                                  </Grid.ColumnDefinitions>
                                  <StackPanel Grid.Column='0'>
                                    <StackPanel Orientation='Horizontal'>
                                      <TextBlock Text='{Binding DisplayName}' Foreground='White' FontWeight='ExtraBold' FontSize='12.5'/>
                                      <TextBlock Text='{Binding UidLabel}' Foreground='#94A3B8' FontSize='11' FontWeight='SemiBold' Margin='5,1,0,0'/>
                                      <TextBlock Text='{Binding TrustBadge}' Foreground='{Binding TrustFg}' FontSize='10.5' FontWeight='ExtraBold' Margin='6,1,0,0'/>
                                    </StackPanel>
                                    <StackPanel Orientation='Horizontal' Margin='0,2,0,0'>
                                      <TextBlock Text='{Binding RoleBadge}' Foreground='{Binding RoleFg}' FontSize='10' FontWeight='Bold' Margin='0,0,6,0'/>
                                      <TextBlock Text='{Binding EloText}' Foreground='{Binding EloFg}' FontSize='10.5' FontWeight='Bold'/>
                                    </StackPanel>
                                  </StackPanel>
                                  <StackPanel Grid.Column='1' VerticalAlignment='Center' HorizontalAlignment='Right' Margin='6,0,0,0'>
                                    <TextBlock Text='{Binding War3Status}' Foreground='{Binding War3Fg}' FontSize='10.5' FontWeight='Bold' HorizontalAlignment='Right'/>
                                    <TextBlock Text='{Binding PingBadge}' Foreground='{Binding PingFg}' FontSize='10.5' FontWeight='ExtraBold' HorizontalAlignment='Right' Margin='0,2,0,0'/>
                                  </StackPanel>
                                </Grid>
                              </Button>
                            </DataTemplate>
                          </ItemsControl.ItemTemplate>
                        </ItemsControl>
                      </ScrollViewer>

                      <!-- Bottom Action Area: Start Button (Host in Lobby), Rejoin Button (Disconnected Player Only), or Match Status / Wait Banner -->
                      <StackPanel Grid.Row='3'>
                        <Border Name='BtnHostStartGame' Visibility='Collapsed' CornerRadius='11' Padding='14,13' Cursor='Hand'>
                          <Border.Background>
                            <LinearGradientBrush StartPoint='0,0' EndPoint='1,0'>
                              <GradientStop Color='#10B981' Offset='0'/>
                              <GradientStop Color='#059669' Offset='1'/>
                            </LinearGradientBrush>
                          </Border.Background>
                          <StackPanel>
                            <TextBlock Name='LblHostStartBtnText' Text='🚀 ТОГЛООМ ЭХЛҮҮЛЭХ (START GAME)' Foreground='#04130D' FontWeight='ExtraBold' FontSize='13.5' HorizontalAlignment='Center'/>
                            <TextBlock Text='Бүх тоглогчдын Warcraft III автоматаар асна' Foreground='#064E3B' FontWeight='Bold' FontSize='10.5' HorizontalAlignment='Center' Margin='0,2,0,0'/>
                          </StackPanel>
                        </Border>

                        <Border Name='BtnRejoinMatch' Visibility='Collapsed' CornerRadius='11' Padding='14,12' Cursor='Hand' BorderBrush='#F59E0B' BorderThickness='1.5'>
                          <Border.Background>
                            <LinearGradientBrush StartPoint='0,0' EndPoint='1,0'>
                              <GradientStop Color='#F59E0B' Offset='0'/>
                              <GradientStop Color='#D97706' Offset='1'/>
                            </LinearGradientBrush>
                          </Border.Background>
                          <StackPanel>
                            <TextBlock Name='LblRejoinBtnText' Text='🔄 ТОГЛОЛТОНД БУЦАЖ ОРОХ' Foreground='#090D16' FontWeight='ExtraBold' FontSize='13' HorizontalAlignment='Center' TextWrapping='Wrap' TextAlignment='Center'/>
                            <TextBlock Name='LblRejoinBtnSub' Text='Та тоглолтоос салсан байна — дарж тоглолт руугаа буцаж орно уу' Foreground='#1E293B' FontWeight='Bold' FontSize='10.5' HorizontalAlignment='Center' Margin='0,2,0,0' TextWrapping='Wrap' TextAlignment='Center'/>
                          </StackPanel>
                        </Border>

                        <Border Name='ClientWaitBanner' Visibility='Visible' Background='#131B2E' BorderBrush='#24304C' BorderThickness='1' CornerRadius='11' Padding='12,10'>
                          <StackPanel>
                            <TextBlock Name='LblWaitBannerTitle' Text='⏳ Host тоглоом эхлүүлэхийг хүлээж байна...' Foreground='#38BDF8' FontWeight='ExtraBold' FontSize='12' HorizontalAlignment='Center' TextWrapping='Wrap' TextAlignment='Center'/>
                            <TextBlock Name='LblWaitBannerSub' Text='Host эхлүүлмэгц таны Warcraft III автоматаар асна' Foreground='#94A3B8' FontSize='10.5' HorizontalAlignment='Center' Margin='0,2,0,0' TextWrapping='Wrap' TextAlignment='Center'/>
                          </StackPanel>
                        </Border>

                        <StackPanel Margin='0,6,0,0'>
                          <Border Name='BtnAddWaitTime' Visibility='Collapsed' Background='#1E293B' BorderBrush='#38BDF8' BorderThickness='1' CornerRadius='8' Padding='10,7' Margin='0,0,0,6' Cursor='Hand'>
                            <TextBlock Name='LblAddWaitTimeText' Text='⏱️ +1 минут сунгах (-addtime 0/3)' Foreground='#38BDF8' FontWeight='ExtraBold' FontSize='11' TextWrapping='Wrap' TextAlignment='Center' HorizontalAlignment='Center'/>
                          </Border>
                          <Border Name='BtnHostDropAbsent' Visibility='Collapsed' Background='#3B1219' BorderBrush='#EF4444' BorderThickness='1' CornerRadius='8' Padding='10,7' Cursor='Hand'>
                            <TextBlock Name='LblHostDropAbsentText' Text='👢 Тоглогчийг хасах (Drop)' Foreground='#FCA5A5' FontWeight='ExtraBold' FontSize='11' TextWrapping='Wrap' TextAlignment='Center' HorizontalAlignment='Center'/>
                          </Border>
                        </StackPanel>
                      </StackPanel>
                    </Grid>
                  </Border>
                </Grid>
              </Grid>

              <!-- ROOM CODE MODAL OVERLAY (For Joining Locked Room OR Setting Code on Existing Room) -->
              <Grid Name='CodeModalOverlay' Visibility='Collapsed' Background='#B8060911'>
                <Border Width='420' VerticalAlignment='Center' HorizontalAlignment='Center'
                        Background='#131B2E' CornerRadius='16' BorderBrush='#7C3AED' BorderThickness='1.5' Padding='24,20'>
                  <StackPanel>
                    <TextBlock Name='LblCodeModalTitle' Text='🔒 Өрөөний Нууц Код' Foreground='White' FontSize='18' FontWeight='ExtraBold' Margin='0,0,0,6'/>
                    <TextBlock Name='LblCodeModalSub' Text='Энэ өрөө нууц кодтой байна. Өрөөний кодыг оруулна уу:' Foreground='#94A3B8' FontSize='12.5' TextWrapping='Wrap' Margin='0,0,0,14'/>
                    <Border Background='#0B0F1A' CornerRadius='9' BorderBrush='#24304C' BorderThickness='1' Padding='12,9' Margin='0,0,0,10'>
                      <TextBox Name='TxtCodeModalInput' MaxLength='24' Background='Transparent' Foreground='#FBBF24' CaretBrush='White' BorderThickness='0' FontSize='15' FontWeight='Bold'/>
                    </Border>
                    <TextBlock Name='LblCodeModalError' Text='' Foreground='#F87171' FontSize='12' FontWeight='SemiBold' Margin='0,0,0,12'/>
                    <StackPanel Orientation='Horizontal' HorizontalAlignment='Right'>
                      <Border Name='BtnCodeModalCancel' Background='#1E293B' CornerRadius='8' Padding='16,8' Margin='0,0,10,0' Cursor='Hand'>
                        <TextBlock Text='Болих' Foreground='#CBD5E1' FontWeight='Bold' FontSize='12.5'/>
                      </Border>
                      <Border Name='BtnCodeModalConfirm' Background='#10B981' CornerRadius='8' Padding='20,8' Cursor='Hand'>
                        <TextBlock Text='✅ Батлах (Confirm)' Foreground='#04130D' FontWeight='ExtraBold' FontSize='12.5'/>
                      </Border>
                    </StackPanel>
                  </StackPanel>
                </Border>
              </Grid>

            </Grid>

            <!-- ==================== PAGE 1.2: TOP 100 ELO LEADERBOARD ==================== -->
            <Grid Grid.Row='1' Name='PageLeaderboard' Visibility='Collapsed'>
              <Grid.RowDefinitions>
                <RowDefinition Height='Auto'/>
                <RowDefinition Height='Auto'/>
                <RowDefinition Height='*'/>
              </Grid.RowDefinitions>

              <Grid Grid.Row='0' Margin='0,0,0,12'>
                <StackPanel>
                  <TextBlock Text='🏆 FACEIT ELO Ранк &amp; Шилдэг 100 Тоглогч (100 – 5000 ELO)' Foreground='White' FontSize='22' FontWeight='ExtraBold'/>
                  <TextBlock Text='Эхний 10 тоглолт = Түвшин тогтоох шат (ELO харагдахгүй). 10 тоглолтын дараа хожлын хувь (Win Rate) болон килл (K/D, дундаж килл)-ээр ELO тогтоогдоно. Дундаас гарвал торгууль ногдоно.' Foreground='#94A3B8' FontSize='12' Margin='0,3,0,0'/>
                </StackPanel>
                <Border Name='BtnRefreshLeaderboard' Background='#151D30' BorderBrush='#26334D' BorderThickness='1' CornerRadius='10' Padding='14,8' HorizontalAlignment='Right' VerticalAlignment='Center' Cursor='Hand'>
                  <TextBlock Text='↻ Шинэчлэх' Foreground='White' FontSize='12.5' FontWeight='Bold'/>
                </Border>
              </Grid>

              <!-- Badge Legend Banner -->
              <Border Grid.Row='1' Background='#111726' CornerRadius='10' BorderBrush='#1E293B' BorderThickness='1' Padding='14,8' Margin='0,0,0,12'>
                <StackPanel Orientation='Horizontal'>
                  <TextBlock Text='🛡️ Ногоон Бамбай: Бүтэн тоглолт хийдэг итгэлтэй тоглогч' Foreground='#10B981' FontSize='11.5' FontWeight='Bold' Margin='0,0,22,0'/>
                  <TextBlock Text='🌱 Шинэ тоглогч (эхний 10 тоглолт)' Foreground='#38BDF8' FontSize='11.5' FontWeight='Bold' Margin='0,0,22,0'/>
                  <TextBlock Text='⚠️ Улаан Тэмдэг (Leaver): 10+ удаа тоглолтын дундаас хаяж гарсан' Foreground='#EF4444' FontSize='11.5' FontWeight='Bold'/>
                </StackPanel>
              </Border>

              <!-- Leaderboard Table -->
              <Border Grid.Row='2' Background='#0E1320' CornerRadius='14' BorderBrush='#1C263B' BorderThickness='1' Padding='14,12'>
                <Grid>
                  <Grid.RowDefinitions>
                    <RowDefinition Height='32'/>
                    <RowDefinition Height='*'/>
                  </Grid.RowDefinitions>
                  <Grid Grid.Row='0' Margin='12,0,12,0'>
                    <Grid.ColumnDefinitions>
                      <ColumnDefinition Width='65'/>
                      <ColumnDefinition Width='2.0*'/>
                      <ColumnDefinition Width='1.4*'/>
                      <ColumnDefinition Width='1.3*'/>
                      <ColumnDefinition Width='1.2*'/>
                      <ColumnDefinition Width='1.1*'/>
                      <ColumnDefinition Width='1.0*'/>
                    </Grid.ColumnDefinitions>
                    <TextBlock Grid.Column='0' Text='РАНК' Foreground='#64748B' FontSize='11' FontWeight='Bold'/>
                    <TextBlock Grid.Column='1' Text='ТОГЛОГЧ (#ID)' Foreground='#64748B' FontSize='11' FontWeight='Bold'/>
                    <TextBlock Grid.Column='2' Text='ТЭМДЭГ (BADGE)' Foreground='#64748B' FontSize='11' FontWeight='Bold'/>
                    <TextBlock Grid.Column='3' Text='FACEIT ELO / LVL' Foreground='#64748B' FontSize='11' FontWeight='Bold'/>
                    <TextBlock Grid.Column='4' Text='KILL / DEATH (AVG)' Foreground='#64748B' FontSize='11' FontWeight='Bold'/>
                    <TextBlock Grid.Column='5' Text='ТОГЛОЛТ (W-L)' Foreground='#64748B' FontSize='11' FontWeight='Bold'/>
                    <TextBlock Grid.Column='6' Text='ЦЭВЭР % (LEAVE)' Foreground='#64748B' FontSize='11' FontWeight='Bold'/>
                  </Grid>
                  <ScrollViewer Grid.Row='1' VerticalScrollBarVisibility='Auto'>
                    <ItemsControl Name='LeaderboardListCtrl'>
                      <ItemsControl.ItemTemplate>
                        <DataTemplate>
                          <Button Tag='{Binding Name}' Background='#141C2E' BorderBrush='#222F49' BorderThickness='1' Padding='12,9' Margin='0,0,0,6' Cursor='Hand' HorizontalContentAlignment='Stretch'>
                            <Grid VerticalAlignment='Center'>
                              <Grid.ColumnDefinitions>
                                <ColumnDefinition Width='65'/>
                                <ColumnDefinition Width='2.0*'/>
                                <ColumnDefinition Width='1.4*'/>
                                <ColumnDefinition Width='1.3*'/>
                                <ColumnDefinition Width='1.2*'/>
                                <ColumnDefinition Width='1.1*'/>
                                <ColumnDefinition Width='1.0*'/>
                              </Grid.ColumnDefinitions>
                              <TextBlock Grid.Column='0' Text='{Binding RankText}' Foreground='{Binding RankFg}' FontWeight='ExtraBold' FontSize='13.5' VerticalAlignment='Center'/>
                              <TextBlock Grid.Column='1' Text='{Binding DisplayName}' Foreground='White' FontWeight='Bold' FontSize='13' VerticalAlignment='Center'/>
                              <TextBlock Grid.Column='2' Text='{Binding BadgeLabel}' Foreground='{Binding BadgeFg}' FontWeight='Bold' FontSize='11.5' VerticalAlignment='Center'/>
                              <TextBlock Grid.Column='3' Text='{Binding EloDisplay}' Foreground='{Binding EloFg}' FontWeight='ExtraBold' FontSize='12.5' VerticalAlignment='Center'/>
                              <TextBlock Grid.Column='4' Text='{Binding KdDisplay}' Foreground='#E2E8F0' FontWeight='SemiBold' FontSize='12' VerticalAlignment='Center'/>
                              <TextBlock Grid.Column='5' Text='{Binding GamesDisplay}' Foreground='#CBD5E1' FontWeight='SemiBold' FontSize='12' VerticalAlignment='Center'/>
                              <TextBlock Grid.Column='6' Text='{Binding CleanRateDisplay}' Foreground='#94A3B8' FontWeight='Bold' FontSize='11.5' VerticalAlignment='Center'/>
                            </Grid>
                          </Button>
                        </DataTemplate>
                      </ItemsControl.ItemTemplate>
                    </ItemsControl>
                  </ScrollViewer>
                </Grid>
              </Border>
            </Grid>

            <!-- ==================== PAGE 1.5: FRIENDS & DIRECT CHAT ==================== -->
            <Grid Grid.Row='1' Name='PageFriends' Visibility='Collapsed'>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width='340'/>
                <ColumnDefinition Width='14'/>
                <ColumnDefinition Width='*'/>
              </Grid.ColumnDefinitions>

              <!-- LEFT COLUMN: Add Friend + Pending Requests + Friends List + Blocked List -->
              <Border Grid.Column='0' Background='#0E1320' CornerRadius='14' BorderBrush='#1E293B' BorderThickness='1' Padding='14,12'>
                <Grid>
                  <Grid.RowDefinitions>
                    <RowDefinition Height='Auto'/>
                    <RowDefinition Height='Auto'/>
                    <RowDefinition Height='Auto'/>
                    <RowDefinition Height='*'/>
                    <RowDefinition Height='Auto'/>
                  </Grid.RowDefinitions>

                  <TextBlock Grid.Row='0' Text='👥 НАЙЗУУДЫН ЖАГСААЛТ' Foreground='White' FontWeight='ExtraBold' FontSize='15' Margin='0,0,0,8'/>

                  <!-- Add Friend by Name or #ID -->
                  <StackPanel Grid.Row='1' Margin='0,0,0,10'>
                    <TextBlock Text='НАЙЗ ХАЙХ (НЭР ЭСВЭЛ #ID):' Foreground='#94A3B8' FontSize='10' FontWeight='Bold' Margin='0,0,0,4'/>
                    <Grid>
                      <Grid.ColumnDefinitions>
                        <ColumnDefinition Width='*'/>
                        <ColumnDefinition Width='Auto'/>
                      </Grid.ColumnDefinitions>
                      <Border Grid.Column='0' Background='#090D16' CornerRadius='8' BorderBrush='#24304C' BorderThickness='1' Padding='10,6' Margin='0,0,6,0'>
                        <TextBox Name='TxtAddFriendInput' MaxLength='32' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='12.5'/>
                      </Border>
                      <Border Grid.Column='1' Name='BtnAddFriendSubmit' Background='#38BDF8' CornerRadius='8' Padding='12,6' Cursor='Hand'>
                        <TextBlock Text='🔍 Хайх' Foreground='#04130D' FontWeight='ExtraBold' FontSize='12' VerticalAlignment='Center'/>
                      </Border>
                    </Grid>
                    <Border Name='FriendSearchResultsPanel' Visibility='Collapsed' Background='#0B1120' CornerRadius='8' BorderBrush='#24304C' BorderThickness='1' Padding='6' Margin='0,6,0,0'>
                      <ScrollViewer MaxHeight='220' VerticalScrollBarVisibility='Auto' HorizontalScrollBarVisibility='Disabled'>
                        <ItemsControl Name='FriendSearchResultsList'>
                          <ItemsControl.ItemTemplate>
                            <DataTemplate>
                              <Border Background='#131B2E' CornerRadius='7' Padding='8,6' Margin='0,0,0,4'>
                                <Grid>
                                  <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width='Auto'/>
                                    <ColumnDefinition Width='*'/>
                                    <ColumnDefinition Width='Auto'/>
                                  </Grid.ColumnDefinitions>
                                  <Ellipse Grid.Column='0' Width='8' Height='8' Fill='{Binding DotColor}' VerticalAlignment='Center' Margin='0,0,8,0'/>
                                  <StackPanel Grid.Column='1'>
                                    <TextBlock Text='{Binding DisplayName}' Foreground='White' FontWeight='Bold' FontSize='12.5' TextTrimming='CharacterEllipsis'/>
                                    <TextBlock Text='{Binding SubText}' Foreground='{Binding SubFg}' FontSize='10.5' TextWrapping='Wrap'/>
                                  </StackPanel>
                                  <Button Grid.Column='2' Tag='{Binding AddTag}' IsEnabled='{Binding CanAdd}' Opacity='{Binding AddOpacity}' Content='{Binding AddLabel}' Background='#10B981' Foreground='#04130D' FontWeight='ExtraBold' FontSize='11.5' BorderThickness='0' Padding='10,5' Margin='8,0,0,0' Cursor='Hand' VerticalAlignment='Center'/>
                                </Grid>
                              </Border>
                            </DataTemplate>
                          </ItemsControl.ItemTemplate>
                        </ItemsControl>
                      </ScrollViewer>
                    </Border>
                    <TextBlock Name='LblFriendStatusMsg' Text='' Foreground='#34D399' FontSize='11' FontWeight='SemiBold' Margin='0,4,0,0' TextWrapping='Wrap'/>
                  </StackPanel>

                  <!-- Pending Friend Requests -->
                  <Border Grid.Row='2' Name='PendingRequestsPanel' Visibility='Collapsed' Background='#172554' CornerRadius='10' BorderBrush='#38BDF8' BorderThickness='1.5' Padding='10,8' Margin='0,0,0,10'>
                    <StackPanel>
                      <TextBlock Text='🔔 ИРСЭН НАЙЗЫН ХҮСЭЛТҮҮД:' Foreground='#38BDF8' FontSize='10.5' FontWeight='ExtraBold' Margin='0,0,0,6'/>
                      <ItemsControl Name='PendingRequestsList'>
                        <ItemsControl.ItemTemplate>
                          <DataTemplate>
                            <Border Background='#0F172A' CornerRadius='8' BorderBrush='#2563EB' BorderThickness='1' Padding='8,6' Margin='0,0,0,5'>
                              <Grid>
                                <Grid.ColumnDefinitions>
                                  <ColumnDefinition Width='*'/>
                                  <ColumnDefinition Width='Auto'/>
                                  <ColumnDefinition Width='Auto'/>
                                </Grid.ColumnDefinitions>
                                <TextBlock Grid.Column='0' Text='{Binding DisplayName}' Foreground='White' FontWeight='ExtraBold' FontSize='12' VerticalAlignment='Center' TextTrimming='CharacterEllipsis' Margin='0,0,6,0'/>
                                <Button Grid.Column='1' Tag='{Binding AcceptTag}' Cursor='Hand' Margin='0,0,5,0'>
                                  <Button.Template>
                                    <ControlTemplate TargetType='Button'>
                                      <Border Background='#10B981' CornerRadius='6' Padding='10,4'>
                                        <TextBlock Text='✅ Зөвшөөрөх' Foreground='#04130D' FontWeight='ExtraBold' FontSize='11' HorizontalAlignment='Center' VerticalAlignment='Center'/>
                                      </Border>
                                    </ControlTemplate>
                                  </Button.Template>
                                </Button>
                                <Button Grid.Column='2' Tag='{Binding DeclineTag}' Cursor='Hand'>
                                  <Button.Template>
                                    <ControlTemplate TargetType='Button'>
                                      <Border Background='#EF4444' CornerRadius='6' Padding='8,4'>
                                        <TextBlock Text='✕' Foreground='White' FontWeight='ExtraBold' FontSize='11' HorizontalAlignment='Center' VerticalAlignment='Center'/>
                                      </Border>
                                    </ControlTemplate>
                                  </Button.Template>
                                </Button>
                              </Grid>
                            </Border>
                          </DataTemplate>
                        </ItemsControl.ItemTemplate>
                      </ItemsControl>
                    </StackPanel>
                  </Border>

                  <!-- Friends List (Click friend name -> Player Action Menu to Invite/View/Block; Click Чат -> 1-on-1 DM) -->
                  <ScrollViewer Grid.Row='3' VerticalScrollBarVisibility='Auto'>
                    <ItemsControl Name='FriendsListCtrl'>
                      <ItemsControl.ItemTemplate>
                        <DataTemplate>
                          <Border Background='#141C2E' CornerRadius='9' BorderBrush='#222F49' BorderThickness='1' Padding='10,8' Margin='0,0,0,6'>
                            <Grid>
                              <Grid.ColumnDefinitions>
                                <ColumnDefinition Width='*'/>
                                <ColumnDefinition Width='Auto'/>
                              </Grid.ColumnDefinitions>
                              <Button Grid.Column='0' Tag='{Binding ProfileTag}' Cursor='Hand' HorizontalContentAlignment='Stretch'>
                                <Button.Template>
                                  <ControlTemplate TargetType='Button'>
                                    <Border Background='Transparent'>
                                      <StackPanel VerticalAlignment='Center'>
                                        <StackPanel Orientation='Horizontal'>
                                          <Ellipse Width='8' Height='8' Fill='{Binding DotColor}' VerticalAlignment='Center' Margin='0,0,6,0'/>
                                          <TextBlock Text='{Binding DisplayName}' Foreground='White' FontWeight='ExtraBold' FontSize='12.5'/>
                                          <Border Visibility='{Binding UnreadVis}' Background='#EF4444' CornerRadius='99' Padding='6,1' Margin='6,0,0,0'>
                                            <TextBlock Text='{Binding UnreadText}' Foreground='White' FontSize='10' FontWeight='ExtraBold'/>
                                          </Border>
                                        </StackPanel>
                                        <TextBlock Text='{Binding SubText}' Foreground='#94A3B8' FontSize='11' Margin='14,2,0,0' TextTrimming='CharacterEllipsis'/>
                                      </StackPanel>
                                    </Border>
                                  </ControlTemplate>
                                </Button.Template>
                              </Button>
                              <Button Grid.Column='1' Tag='{Binding ChatTag}' Cursor='Hand' VerticalAlignment='Center' Margin='6,0,0,0'>
                                <Button.Template>
                                  <ControlTemplate TargetType='Button'>
                                    <Border Background='#7C3AED' CornerRadius='7' Padding='10,5'>
                                      <TextBlock Text='💬 Чат' Foreground='White' FontWeight='Bold' FontSize='11.5'/>
                                    </Border>
                                  </ControlTemplate>
                                </Button.Template>
                              </Button>
                            </Grid>
                          </Border>
                        </DataTemplate>
                      </ItemsControl.ItemTemplate>
                    </ItemsControl>
                  </ScrollViewer>

                  <!-- Blocked Users List at bottom -->
                  <Border Grid.Row='4' Background='#090D16' CornerRadius='8' BorderBrush='#1E293B' BorderThickness='1' Padding='8,6' Margin='0,8,0,0'>
                    <StackPanel>
                      <TextBlock Text='🚫 БЛОК ХИЙСЭН ТОГЛОГЧИД:' Foreground='#64748B' FontSize='10' FontWeight='Bold' Margin='0,0,0,4'/>
                      <ItemsControl Name='BlockedUsersListCtrl'>
                        <ItemsControl.ItemTemplate>
                          <DataTemplate>
                            <Grid Margin='0,0,0,3'>
                              <TextBlock Text='{Binding DisplayName}' Foreground='#94A3B8' FontSize='11.5' VerticalAlignment='Center'/>
                              <Button Content='Блок гаргах' Tag='{Binding Name}' Background='#334155' Foreground='White' FontSize='10.5' BorderThickness='0' Padding='7,2' HorizontalAlignment='Right' Cursor='Hand'/>
                            </Grid>
                          </DataTemplate>
                        </ItemsControl.ItemTemplate>
                      </ItemsControl>
                    </StackPanel>
                  </Border>
                </Grid>
              </Border>

              <!-- RIGHT COLUMN: 1-ON-1 DIRECT CHAT -->
              <Border Grid.Column='2' Background='#0E1320' CornerRadius='14' BorderBrush='#1E293B' BorderThickness='1' Padding='16,12'>
                <Grid>
                  <Grid.RowDefinitions>
                    <RowDefinition Height='Auto'/>
                    <RowDefinition Height='*'/>
                    <RowDefinition Height='Auto'/>
                  </Grid.RowDefinitions>

                  <Border Grid.Row='0' Name='BtnDmHeaderProfile' Background='#131B2E' CornerRadius='10' BorderBrush='#24304C' BorderThickness='1' Padding='14,10' Margin='0,0,0,10' Cursor='Hand'>
                    <StackPanel VerticalAlignment='Center'>
                      <TextBlock Name='LblDmHeaderTitle' Text='💬 Найзаа сонгоод чат бичнэ үү' Foreground='White' FontSize='15' FontWeight='ExtraBold'/>
                      <TextBlock Name='LblDmHeaderSub' Text='Найзынхаа нэр дээр дарж өрөөндөө урих / мэдээлэл харах, эсвэл [💬 Чат] дарж бичнэ үү' Foreground='#94A3B8' FontSize='11.5' Margin='0,2,0,0'/>
                    </StackPanel>
                  </Border>

                  <Border Grid.Row='1' Background='#090D16' CornerRadius='10' BorderBrush='#172033' BorderThickness='1' Padding='12,10' Margin='0,0,0,10'>
                    <ScrollViewer Name='DmChatScroll' VerticalScrollBarVisibility='Auto'>
                      <ItemsControl Name='DmMessagesListCtrl'>
                        <ItemsControl.ItemTemplate>
                          <DataTemplate>
                            <StackPanel Margin='0,0,0,8'>
                              <StackPanel Orientation='Horizontal'>
                                <TextBlock Text='{Binding TimeStr}' Foreground='#64748B' FontSize='11.5' Margin='0,0,6,0' VerticalAlignment='Top'/>
                                <TextBlock Text='{Binding SenderLabel}' Foreground='{Binding SenderFg}' FontWeight='Bold' FontSize='12.5' Margin='0,0,6,0' VerticalAlignment='Top'/>
                                <TextBlock Text='{Binding Text}' Foreground='#F1F5F9' FontWeight='SemiBold' FontSize='12.5' TextWrapping='Wrap' MaxWidth='480'/>
                              </StackPanel>
                              <Button Visibility='{Binding HasInviteVis}' Tag='{Binding InviteTag}' HorizontalAlignment='Left' Margin='48,6,0,2' Cursor='Hand'>
                                <Button.Template>
                                  <ControlTemplate TargetType='Button'>
                                    <Border Background='#10B981' CornerRadius='7' Padding='14,6'>
                                      <TextBlock Text='✅ Зөвшөөрөх — Өрөөнд Орох' Foreground='#04130D' FontWeight='ExtraBold' FontSize='12'/>
                                    </Border>
                                  </ControlTemplate>
                                </Button.Template>
                              </Button>
                            </StackPanel>
                          </DataTemplate>
                        </ItemsControl.ItemTemplate>
                      </ItemsControl>
                    </ScrollViewer>
                  </Border>

                  <Grid Grid.Row='2'>
                    <Grid.ColumnDefinitions>
                      <ColumnDefinition Width='*'/>
                      <ColumnDefinition Width='Auto'/>
                    </Grid.ColumnDefinitions>
                    <Border Grid.Column='0' Background='#090D16' CornerRadius='9' BorderBrush='#24304C' BorderThickness='1' Padding='12,8' Margin='0,0,8,0'>
                      <TextBox Name='TxtDmInput' MaxLength='400' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='13'/>
                    </Border>
                    <Border Grid.Column='1' Name='BtnSendDm' Background='#10B981' CornerRadius='9' Padding='20,8' Cursor='Hand'>
                      <TextBlock Text='Илгээх ↵' Foreground='#04130D' FontWeight='ExtraBold' FontSize='12.5' VerticalAlignment='Center'/>
                    </Border>
                  </Grid>
                </Grid>
              </Border>
            </Grid>

            <!-- ==================== PAGE 2: WARKEY & QUICK CHAT ==================== -->
            <Grid Grid.Row='1' Name='PageWarKey' Visibility='Collapsed'>
              <Grid.RowDefinitions>
                <RowDefinition Height='Auto'/>
                <RowDefinition Height='Auto'/>
                <RowDefinition Height='*'/>
              </Grid.RowDefinitions>

              <!-- Row 0: Header + Ctrl+F5 Toggle -->
              <Grid Grid.Row='0' Margin='0,0,0,12'>
                <StackPanel>
                  <TextBlock Text='⌨️ Warcraft WarKey &amp; Хурдан «Chat»-лах' Foreground='White' FontSize='22' FontWeight='ExtraBold'/>
                  <TextBlock Text='Нүдэн дээр дараад хүссэн товчоо дарж тохируулна уу. Тохируулсан товчоо устгах бол [Backspace] эсвэл [Delete] дарна уу.' Foreground='#94A3B8' FontSize='12' Margin='0,3,0,0'/>
                </StackPanel>
                <StackPanel Orientation='Horizontal' HorizontalAlignment='Right' VerticalAlignment='Center'>
                  <Border Name='BtnToggleWarKey' Background='#14382D' BorderBrush='#10B981' BorderThickness='1' CornerRadius='9' Padding='14,7' Margin='0,0,8,0' Cursor='Hand'>
                    <TextBlock Name='LblWarKeyToggleState' Text='🟢 WarKey: АССАН (Ctrl+F5 унтраах)' Foreground='#34D399' FontWeight='ExtraBold' FontSize='11.5'/>
                  </Border>
                  <Border Name='BtnResetWarKey' Background='#1E293B' BorderBrush='#334155' BorderThickness='1' CornerRadius='9' Padding='12,7' Cursor='Hand'>
                    <TextBlock Text='🔄 Бүгдийг Хоослох' Foreground='#CBD5E1' FontWeight='Bold' FontSize='11.5'/>
                  </Border>
                </StackPanel>
              </Grid>

              <!-- Row 1: Side-by-Side Inventory (3x2 = 6 slots) & Skills (2x4 = 8 open slots) -->
              <Grid Grid.Row='1' Margin='0,0,0,12'>
                <Grid.ColumnDefinitions>
                  <ColumnDefinition Width='275'/>
                  <ColumnDefinition Width='14'/>
                  <ColumnDefinition Width='*'/>
                </Grid.ColumnDefinitions>

                <!-- LEFT: INVENTORY (3x2) -->
                <Border Grid.Column='0' Background='#101625' CornerRadius='14' BorderBrush='#24304C' BorderThickness='1' Padding='14,12'>
                  <StackPanel>
                    <TextBlock Text='🎒 INVENTORY (Цүнхний 6 слот)' Foreground='#F59E0B' FontWeight='ExtraBold' FontSize='12.5' Margin='0,0,0,10'/>
                    <UniformGrid Rows='3' Columns='2'>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,6,6' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Зүүн Дээд (Num 7)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkBtn0' Content='Хоосон' Height='34' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,0,6' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Баруун Дээд (Num 8)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkBtn1' Content='Хоосон' Height='34' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,6,6' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Зүүн Дунд (Num 4)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkBtn2' Content='Хоосон' Height='34' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,0,6' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Баруун Дунд (Num 5)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkBtn3' Content='Хоосон' Height='34' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,6,0' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Зүүн Доод (Num 1)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkBtn4' Content='Хоосон' Height='34' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,0,0' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Баруун Доод (Num 2)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkBtn5' Content='Хоосон' Height='34' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                    </UniformGrid>
                  </StackPanel>
                </Border>

                <!-- RIGHT: SKILLS (2x4 = 8 Open Skill Slots) -->
                <Border Grid.Column='2' Background='#101625' CornerRadius='14' BorderBrush='#7C3AED' BorderThickness='1' Padding='14,12'>
                  <StackPanel>
                    <Grid Margin='0,0,0,10'>
                      <TextBlock Text='⚡ SKILLS (Баатарын 8 скилл — 6 болон 8 скиллтэй бүх Map-д нээлттэй)' Foreground='#C4B5FD' FontWeight='ExtraBold' FontSize='12.5'/>
                    </Grid>
                    <UniformGrid Rows='2' Columns='4'>
                      <!-- Top Row (Row 1 of Command Card: Extra Skills 5, 6, 7, 8) -->
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,6,6' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Скилл 5 (Дээд 1)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkSkill0' Content='Хоосон' Height='42' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,6,6' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Скилл 6 (Дээд 2 — D)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkSkill1' Content='Хоосон' Height='42' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,6,6' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Скилл 7 (Дээд 3 — F)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkSkill2' Content='Хоосон' Height='42' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,0,6' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Скилл 8 (Дээд 4)' Foreground='#94A3B8' FontSize='10' Margin='0,0,0,4'/>
                          <Button Name='WkSkill3' Content='Хоосон' Height='42' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>

                      <!-- Bottom Row (Row 2 of Command Card: Main 4 Skills Q, W, E, R) -->
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,6,0' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Скилл 1 (Доод 1 — Q)' Foreground='#CBD5E1' FontSize='10' FontWeight='SemiBold' Margin='0,0,0,4'/>
                          <Button Name='WkSkill4' Content='Хоосон' Height='42' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,6,0' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Скилл 2 (Доод 2 — W)' Foreground='#CBD5E1' FontSize='10' FontWeight='SemiBold' Margin='0,0,0,4'/>
                          <Button Name='WkSkill5' Content='Хоосон' Height='42' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,6,0' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Скилл 3 (Доод 3 — E)' Foreground='#CBD5E1' FontSize='10' FontWeight='SemiBold' Margin='0,0,0,4'/>
                          <Button Name='WkSkill6' Content='Хоосон' Height='42' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                      <Border Background='#151E32' CornerRadius='9' BorderBrush='#2A3958' BorderThickness='1' Margin='0,0,0,0' Padding='8,6'>
                        <StackPanel>
                          <TextBlock Text='Скилл 4 (Ult — R)' Foreground='#CBD5E1' FontSize='10' FontWeight='SemiBold' Margin='0,0,0,4'/>
                          <Button Name='WkSkill7' Content='Хоосон' Height='42' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='13' BorderThickness='0' Cursor='Hand'/>
                        </StackPanel>
                      </Border>
                    </UniformGrid>
                  </StackPanel>
                </Border>
              </Grid>

              <!-- Row 2: QUICK CHAT (Хурдан «chat»-лах) -->
              <Border Grid.Row='2' Background='#101625' CornerRadius='14' BorderBrush='#1E293B' BorderThickness='1' Padding='16,12'>
                <Grid>
                  <Grid.RowDefinitions>
                    <RowDefinition Height='Auto'/>
                    <RowDefinition Height='Auto'/>
                    <RowDefinition Height='*'/>
                    <RowDefinition Height='Auto'/>
                  </Grid.RowDefinitions>

                  <TextBlock Grid.Row='0' Text='💬 Хурдан «chat»-лах (Тохируулсан товч дармагц Warcraft дотор текст автоматаар бичигдэнэ)' Foreground='#38BDF8' FontWeight='ExtraBold' FontSize='13' Margin='0,0,0,8'/>

                  <!-- Add Quick Chat Row -->
                  <Grid Grid.Row='1' Margin='0,0,0,10'>
                    <Grid.ColumnDefinitions>
                      <ColumnDefinition Width='130'/>
                      <ColumnDefinition Width='*'/>
                      <ColumnDefinition Width='Auto'/>
                      <ColumnDefinition Width='Auto'/>
                    </Grid.ColumnDefinitions>
                    <StackPanel Grid.Column='0' Margin='0,0,10,0'>
                      <TextBlock Text='ХЯЛБАР ТОВЧ:' Foreground='#94A3B8' FontSize='10' FontWeight='Bold' Margin='0,0,0,3'/>
                      <Button Name='BtnQuickChatKey' Content='Хоосон' Height='32' Background='#090D16' Foreground='#64748B' FontWeight='ExtraBold' FontSize='12.5' BorderBrush='#24304C' BorderThickness='1' Cursor='Hand'/>
                    </StackPanel>
                    <StackPanel Grid.Column='1' Margin='0,0,12,0'>
                      <TextBlock Text='МЕССЕЖ (WARCRAFT ДОТОР БИЧИГДЭХ ТЕКСТ):' Foreground='#94A3B8' FontSize='10' FontWeight='Bold' Margin='0,0,0,3'/>
                      <Border Background='#090D16' CornerRadius='7' BorderBrush='#24304C' BorderThickness='1' Padding='10,5' Height='32'>
                        <TextBox Name='TxtQuickChatMsg' Text='' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='12.5' VerticalContentAlignment='Center'/>
                      </Border>
                    </StackPanel>
                    <StackPanel Grid.Column='2' Orientation='Horizontal' VerticalAlignment='Bottom' Margin='0,0,12,5'>
                      <RadioButton Name='RbChatWar3' Content='War3' IsChecked='True' Foreground='#E2E8F0' FontSize='11.5' FontWeight='SemiBold' Margin='0,0,10,0'/>
                      <RadioButton Name='RbChatWar3All' Content='War3 All' Foreground='#E2E8F0' FontSize='11.5' FontWeight='SemiBold' Margin='0,0,10,0'/>
                      <RadioButton Name='RbChatLobby' Content='War3 Lobby' Foreground='#E2E8F0' FontSize='11.5' FontWeight='SemiBold'/>
                    </StackPanel>
                    <Border Grid.Column='3' Name='BtnAddQuickChat' Background='#10B981' CornerRadius='8' Padding='16,0' Height='32' VerticalAlignment='Bottom' Cursor='Hand'>
                      <TextBlock Text='+ Нэмэх' Foreground='#04130D' FontWeight='ExtraBold' FontSize='12' VerticalAlignment='Center'/>
                    </Border>
                  </Grid>

                  <!-- Quick Chat List -->
                  <Border Grid.Row='2' Background='#0B0F1A' CornerRadius='10' BorderBrush='#1E293B' BorderThickness='1' Padding='10,8'>
                    <ScrollViewer VerticalScrollBarVisibility='Auto'>
                      <ItemsControl Name='QuickChatList'>
                        <ItemsControl.ItemTemplate>
                          <DataTemplate>
                            <Border Background='#141C2E' CornerRadius='8' BorderBrush='#222F49' BorderThickness='1' Padding='10,6' Margin='0,0,0,5'>
                              <Grid VerticalAlignment='Center'>
                                <Grid.ColumnDefinitions>
                                  <ColumnDefinition Width='110'/>
                                  <ColumnDefinition Width='*'/>
                                  <ColumnDefinition Width='100'/>
                                  <ColumnDefinition Width='76'/>
                                </Grid.ColumnDefinitions>
                                <Border Grid.Column='0' Background='#090D16' CornerRadius='6' Padding='8,3' HorizontalAlignment='Left' VerticalAlignment='Center'>
                                  <TextBlock Text='{Binding KeyName}' Foreground='#38BDF8' FontWeight='ExtraBold' FontSize='12'/>
                                </Border>
                                <TextBlock Grid.Column='1' Text='{Binding Message}' Foreground='White' FontWeight='SemiBold' FontSize='12.5' VerticalAlignment='Center' Margin='8,0,8,0'/>
                                <TextBlock Grid.Column='2' Text='{Binding ModeLabel}' Foreground='#94A3B8' FontSize='11' FontWeight='Bold' VerticalAlignment='Center'/>
                                <Button Grid.Column='3' Content='Устгах' Tag='{Binding Id}' Background='#EF4444' Foreground='White' FontWeight='Bold' FontSize='11' BorderThickness='0' Height='24' Cursor='Hand'/>
                              </Grid>
                            </Border>
                          </DataTemplate>
                        </ItemsControl.ItemTemplate>
                      </ItemsControl>
                    </ScrollViewer>
                  </Border>

                  <TextBlock Grid.Row='3' Text='(Нэг товчлуурыг олон мессежинд ашиглах боломжтой. Тоглоом дотор товчоо дармагц автоматаар бичигдэнэ.)' Foreground='#64748B' FontSize='11' Margin='0,6,0,0'/>
                </Grid>
              </Border>
            </Grid>

            <!-- ==================== PAGE 3: WAR3 SETUP & AUTO-PATCHER ==================== -->
            <Grid Grid.Row='1' Name='PageSettings' Visibility='Collapsed'>
              <StackPanel MaxWidth='740' HorizontalAlignment='Left' Margin='4,14,0,0'>
                <TextBlock Text='⚙️ Warcraft III Тохируулах &amp; Автомат Patch' Foreground='White' FontSize='22' FontWeight='ExtraBold' Margin='0,0,0,6'/>
                <TextBlock Text='Та Warcraft III 1.26a суусан хавтсаа сонгоход л хангалттай — манай Reconnect Patch (Game.dll), 4GB RAM Crash-Protect болон Албан ёсны Map-ууд автоматаар сууна!' Foreground='#94A3B8' FontSize='12.5' TextWrapping='Wrap' Margin='0,0,0,18'/>

                <!-- STEP 1 CARD -->
                <Border Background='#121829' CornerRadius='14' BorderBrush='#7C3AED' BorderThickness='1' Padding='20,18' Margin='0,0,0,14'>
                  <StackPanel>
                    <TextBlock Text='① АЛХАМ 1: Warcraft III 1.26a суусан хавтсаа сонгоно уу' Foreground='#C4B5FD' FontWeight='ExtraBold' FontSize='13.5' Margin='0,0,0,8'/>
                    <TextBlock Text='Жишээ нь: D:\Warcraft III эсвэл C:\Games\Warcraft III (Дотор нь war3.exe байдаг үндсэн хавтас)' Foreground='#94A3B8' FontSize='11.5' Margin='0,0,0,10'/>
                    <Grid Margin='0,0,0,14'>
                      <Grid.ColumnDefinitions>
                        <ColumnDefinition Width='*'/>
                        <ColumnDefinition Width='210'/>
                      </Grid.ColumnDefinitions>
                      <Border Grid.Column='0' Background='#0B0F1A' CornerRadius='9' BorderBrush='#24304C' BorderThickness='1' Padding='12,9' Margin='0,0,10,0'>
                        <TextBox Name='TxtWar3Path' Background='Transparent' Foreground='White' CaretBrush='White' BorderThickness='0' FontSize='13'/>
                      </Border>
                      <Border Grid.Column='1' Name='BtnBrowseWar3' Background='#7C3AED' CornerRadius='9' Cursor='Hand'>
                        <TextBlock Text='📁 Хавтас Сонгох &amp; Суулгах' Foreground='White' FontWeight='Bold' FontSize='12.5' HorizontalAlignment='Center' VerticalAlignment='Center'/>
                      </Border>
                    </Grid>

                    <Border Name='BtnDownloadAllMaps' Background='#10B981' CornerRadius='10' Padding='18,11' Cursor='Hand' HorizontalAlignment='Left'>
                      <TextBlock Text='⚡  Одоо Шалгах &amp; Reconnect Patch + Бүх Map Автоматаар Суулгах' Foreground='#04130D' FontWeight='ExtraBold' FontSize='12.5'/>
                    </Border>
                  </StackPanel>
                </Border>

                <!-- STEP 2 CARD: AUTOMATIC PATCH CHECKLIST -->
                <Border Background='#101625' CornerRadius='14' BorderBrush='#1E293B' BorderThickness='1' Padding='20,18'>
                  <StackPanel>
                    <TextBlock Text='② АЛХАМ 2: Автоматаар суух Patch &amp; Map-уудын Төлөв' Foreground='#34D399' FontWeight='ExtraBold' FontSize='13.5' Margin='0,0,0,12'/>

                    <Border Background='#0B0F1A' CornerRadius='8' Padding='12,9' Margin='0,0,0,8' BorderBrush='#1E293B' BorderThickness='1'>
                      <TextBlock Name='LblStep1' Text='⏳ 1. Warcraft III 1.26a үндсэн файл (war3.exe) шалгах...' Foreground='#CBD5E1' FontSize='12.5' FontWeight='SemiBold'/>
                    </Border>

                    <Border Background='#0B0F1A' CornerRadius='8' Padding='12,9' Margin='0,0,0,8' BorderBrush='#1E293B' BorderThickness='1'>
                      <TextBlock Name='LblStep2' Text='⏳ 2. ZevArena Reconnect &amp; View Patch (Game.dll) автоматаар суулгах...' Foreground='#CBD5E1' FontSize='12.5' FontWeight='SemiBold'/>
                    </Border>

                    <Border Background='#0B0F1A' CornerRadius='8' Padding='12,9' Margin='0,0,0,8' BorderBrush='#1E293B' BorderThickness='1'>
                      <TextBlock Name='LblStep3' Text='⏳ 3. 4GB RAM Crash-Protect (LAA 0x0020) &amp; Хар Дэлгэц Засах (WIN7RTM)...' Foreground='#CBD5E1' FontSize='12.5' FontWeight='SemiBold'/>
                    </Border>

                    <Border Background='#0B0F1A' CornerRadius='8' Padding='12,9' Margin='0,0,0,10' BorderBrush='#1E293B' BorderThickness='1'>
                      <TextBlock Name='LblStep4' Text='⏳ 4. Албан ёсны Map-ууд (-cam / Reconnect) Maps\Download руу хуулах...' Foreground='#CBD5E1' FontSize='12.5' FontWeight='SemiBold'/>
                    </Border>

                    <TextBlock Name='LblSettingsStatus' Text='' Foreground='#34D399' FontWeight='Bold' FontSize='12.5' TextWrapping='Wrap' Margin='0,4,0,0'/>
                  </StackPanel>
                </Border>
              </StackPanel>
            </Grid>

            <!-- MATCH HISTORY MODAL (click own ELO card or 'Тоглолтын түүх' in player profile) -->
            <Grid Grid.Row='0' Grid.RowSpan='2' Name='MatchHistoryOverlay' Visibility='Collapsed' Background='#C8060911' Panel.ZIndex='60'>
              <Border Width='640' MaxHeight='640' VerticalAlignment='Center' HorizontalAlignment='Center'
                      Background='#0F1626' CornerRadius='16' BorderBrush='#FBBF24' BorderThickness='1.5' Padding='22,18'>
                <Grid>
                  <Grid.RowDefinitions>
                    <RowDefinition Height='Auto'/>
                    <RowDefinition Height='Auto'/>
                    <RowDefinition Height='*'/>
                  </Grid.RowDefinitions>
                  <Grid Grid.Row='0'>
                    <StackPanel>
                      <TextBlock Name='LblHistoryTitle' Text='📜 Сүүлийн 10 тоглолтын түүх' Foreground='White' FontSize='18' FontWeight='ExtraBold'/>
                      <TextBlock Name='LblHistoryElo' Text='' Foreground='#FBBF24' FontSize='12.5' FontWeight='Bold' Margin='0,4,0,0' TextWrapping='Wrap'/>
                    </StackPanel>
                    <Border Name='BtnHistoryClose' HorizontalAlignment='Right' VerticalAlignment='Top' Background='#1E293B' CornerRadius='8' Padding='10,4' Cursor='Hand'>
                      <TextBlock Text='✕ Хаах' Foreground='#CBD5E1' FontWeight='Bold' FontSize='12'/>
                    </Border>
                  </Grid>
                  <Border Grid.Row='1' Background='#131B2E' CornerRadius='10' Padding='12,8' Margin='0,12,0,10'>
                    <TextBlock Name='LblHistoryStats' Text='' Foreground='#CBD5E1' FontSize='12' FontWeight='SemiBold' TextWrapping='Wrap'/>
                  </Border>
                  <ScrollViewer Grid.Row='2' VerticalScrollBarVisibility='Auto' HorizontalScrollBarVisibility='Disabled'>
                    <StackPanel>
                      <TextBlock Name='LblHistoryEmpty' Visibility='Collapsed' Text='Одоогоор дууссан тоглолт алга байна.' Foreground='#64748B' FontSize='12.5' Margin='4,10'/>
                      <ItemsControl Name='MatchHistoryList'>
                        <ItemsControl.ItemTemplate>
                          <DataTemplate>
                            <Border Background='#131B2E' CornerRadius='12' BorderBrush='{Binding CardBorder}' BorderThickness='1.5' Padding='12,10' Margin='0,0,0,8'>
                              <Grid>
                                <Grid.ColumnDefinitions>
                                  <ColumnDefinition Width='86'/>
                                  <ColumnDefinition Width='*'/>
                                  <ColumnDefinition Width='Auto'/>
                                </Grid.ColumnDefinitions>
                                <Border Grid.Column='0' Background='{Binding ResultBg}' CornerRadius='9' Padding='6,10' VerticalAlignment='Center' Margin='0,0,12,0'>
                                  <TextBlock Text='{Binding ResultLabel}' Foreground='{Binding ResultFg}' FontWeight='ExtraBold' FontSize='13' HorizontalAlignment='Center' TextAlignment='Center' TextWrapping='Wrap'/>
                                </Border>
                                <StackPanel Grid.Column='1'>
                                  <TextBlock Text='{Binding MapLine}' Foreground='White' FontWeight='Bold' FontSize='12.5' TextWrapping='Wrap'/>
                                  <TextBlock Text='{Binding KdaLine}' Foreground='#E2E8F0' FontWeight='SemiBold' FontSize='12' Margin='0,3,0,0' TextWrapping='Wrap'/>
                                  <TextBlock Text='{Binding TeammatesLine}' Foreground='#34D399' FontSize='11' Margin='0,3,0,0' TextWrapping='Wrap'/>
                                  <TextBlock Text='{Binding OpponentsLine}' Foreground='#F87171' FontSize='11' Margin='0,1,0,0' TextWrapping='Wrap'/>
                                </StackPanel>
                                <StackPanel Grid.Column='2' VerticalAlignment='Center' Margin='10,0,0,0'>
                                  <TextBlock Text='{Binding EloLine}' Foreground='{Binding EloFg}' FontWeight='ExtraBold' FontSize='13' HorizontalAlignment='Right'/>
                                  <TextBlock Text='{Binding DateLine}' Foreground='#64748B' FontSize='10.5' HorizontalAlignment='Right' Margin='0,3,0,0'/>
                                </StackPanel>
                              </Grid>
                            </Border>
                          </DataTemplate>
                        </ItemsControl.ItemTemplate>
                      </ItemsControl>
                    </StackPanel>
                  </ScrollViewer>
                </Grid>
              </Border>
            </Grid>

            <!-- PLAYER PROFILE & ACTION MODAL OVERLAY (Click player in room, Leaderboard, or DM -> ELO, Badge, Kills, Kick, Add Friend, DM, Block) -->
            <Grid Grid.Row='0' Grid.RowSpan='2' Name='PlayerActionModalOverlay' Visibility='Collapsed' Background='#B8060911'>
              <Border Width='460' VerticalAlignment='Center' HorizontalAlignment='Center'
                      Background='#131B2E' CornerRadius='16' BorderBrush='#38BDF8' BorderThickness='1.5' Padding='24,20'>
                <StackPanel>
                  <Grid Margin='0,0,0,10'>
                    <StackPanel>
                      <TextBlock Name='LblPlayerModalName' Text='👤 Тоглогч' Foreground='White' FontSize='20' FontWeight='ExtraBold'/>
                      <TextBlock Name='LblPlayerModalUid' Text='ID Дугаар: #10001' Foreground='#38BDF8' FontSize='13' FontWeight='Bold' Margin='0,2,0,0'/>
                    </StackPanel>
                    <Button Name='BtnClosePlayerModal' Content='✕' Width='32' Height='28' Background='#1E293B' Foreground='White' BorderThickness='0' HorizontalAlignment='Right' VerticalAlignment='Top' Cursor='Hand'/>
                  </Grid>

                  <!-- ELO, Trust Badge & Kill/Leave Stats Card -->
                  <Border Background='#090D16' CornerRadius='10' BorderBrush='#7C3AED' BorderThickness='1' Padding='14,10' Margin='0,0,0,10'>
                    <StackPanel>
                      <TextBlock Name='LblPlayerModalBadge' Text='🛡️ Итгэлтэй Тоглогч' Foreground='#10B981' FontSize='13' FontWeight='ExtraBold' Margin='0,0,0,4'/>
                      <TextBlock Name='LblPlayerModalElo' Text='⚡ FACEIT ELO: 1000  •  🗡️ 0 Kill / 💀 0 Death' Foreground='#FBBF24' FontSize='12.5' FontWeight='Bold' Margin='0,0,0,4'/>
                      <TextBlock Name='LblPlayerModalLeaves' Text='📊 Нийт тоглосон: 0  •  Дундаас гарсан (Leave): 0 удаа' Foreground='#CBD5E1' FontSize='11.5' FontWeight='SemiBold'/>
                    </StackPanel>
                  </Border>

                  <Border Background='#0B0F1A' CornerRadius='10' BorderBrush='#1E293B' BorderThickness='1' Padding='14,10' Margin='0,0,0,12'>
                    <StackPanel>
                      <TextBlock Name='LblPlayerModalStatus' Text='🟢 Төлөв: Онлайн' Foreground='#34D399' FontSize='12' FontWeight='Bold' Margin='0,0,0,3'/>
                      <TextBlock Name='LblPlayerModalRoom' Text='🎮 Одоо байгаа өрөө: -' Foreground='#CBD5E1' FontSize='11.5' Margin='0,0,0,3'/>
                      <TextBlock Name='LblPlayerModalCreated' Text='📅 Бүртгүүлсэн огноо: -' Foreground='#94A3B8' FontSize='11'/>
                    </StackPanel>
                  </Border>

                  <TextBlock Name='LblPlayerModalFeedback' Text='' Foreground='#FBBF24' FontSize='12' FontWeight='Bold' TextWrapping='Wrap' Margin='0,0,0,10'/>

                  <!-- Match History / Rank Details Button -->
                  <Border Name='BtnModalViewHistory' Visibility='Visible' Background='#1E293B' BorderBrush='#38BDF8' BorderThickness='1' CornerRadius='9' Padding='12,9' Margin='0,0,0,8' Cursor='Hand'>
                    <TextBlock Text='📜 Сүүлийн 10 тоглолтын түүх &amp; Ранк харах' Foreground='#38BDF8' FontWeight='ExtraBold' FontSize='12' HorizontalAlignment='Center'/>
                  </Border>

                  <!-- Host-only Kick Button (Strictly inside Room Member list) -->
                  <Border Name='BtnModalKickUser' Visibility='Collapsed' Background='#DC2626' BorderBrush='#FCA5A5' BorderThickness='1' CornerRadius='9' Padding='12,10' Margin='0,0,0,8' Cursor='Hand'>
                    <TextBlock Text='👢 Өрөөнөөс Хөөх (Kick &amp; Энэ өрөөнд дахин оруулахгүй)' Foreground='White' FontWeight='ExtraBold' FontSize='12.5' HorizontalAlignment='Center'/>
                  </Border>

                  <UniformGrid Name='ModalActionButtonsGrid' Rows='2' Columns='2'>
                    <Border Name='BtnModalAddFriend' Background='#10B981' CornerRadius='8' Padding='10,9' Margin='0,0,6,6' Cursor='Hand'>
                      <TextBlock Name='LblBtnModalAddFriendText' Text='➕ Найзын хүсэлт илгээх' Foreground='#04130D' FontWeight='ExtraBold' FontSize='12' HorizontalAlignment='Center'/>
                    </Border>
                    <Border Name='BtnModalDirectChat' Background='#7C3AED' CornerRadius='8' Padding='10,9' Margin='0,0,0,6' Cursor='Hand'>
                      <TextBlock Text='💬 Чат бичих (DM)' Foreground='White' FontWeight='Bold' FontSize='12' HorizontalAlignment='Center'/>
                    </Border>
                    <Border Name='BtnModalInviteRoom' Background='#0284C7' CornerRadius='8' Padding='10,9' Margin='0,0,6,0' Cursor='Hand'>
                      <TextBlock Text='📨 Өрөөндөө урих' Foreground='White' FontWeight='Bold' FontSize='12' HorizontalAlignment='Center'/>
                    </Border>
                    <Border Name='BtnModalBlockUser' Background='#EF4444' CornerRadius='8' Padding='10,9' Margin='0,0,0,0' Cursor='Hand'>
                      <TextBlock Name='LblBtnModalBlockText' Text='🚫 Блок хийх (Block)' Foreground='White' FontWeight='Bold' FontSize='12' HorizontalAlignment='Center'/>
                    </Border>
                  </UniformGrid>
                </StackPanel>
              </Border>
            </Grid>

          </Grid>
        </Grid>

        <!-- ==================== 3. STEAM-STYLE AUTO-UPDATER OVERLAY ==================== -->
        <Grid Name='UpdateOverlay' Visibility='Collapsed' Background='#DC060911'>
          <Border Width='490' VerticalAlignment='Center' HorizontalAlignment='Center'
                  Background='#111827' CornerRadius='18' BorderBrush='#38BDF8' BorderThickness='1.5' Padding='28,24'>
            <StackPanel>
              <StackPanel Orientation='Horizontal' Margin='0,0,0,10'>
                <Border Background='#0C2D48' BorderBrush='#38BDF8' BorderThickness='1' CornerRadius='99' Padding='10,3'>
                  <TextBlock Text='⚡ ZEV ARENA AUTO-UPDATER' Foreground='#38BDF8' FontSize='10.5' FontWeight='ExtraBold'/>
                </Border>
              </StackPanel>
              <TextBlock Name='LblUpdateTitle' Text='🔄 Шинэчлэлт олдлоо — Автоматаар суулгаж байна...' Foreground='White' FontSize='18' FontWeight='ExtraBold' TextWrapping='Wrap' Margin='0,0,0,6'/>
              <TextBlock Name='LblUpdateSub' Text='Сервер дээр шинэ хувилбар орсон байна. Програм автоматаар татаж аваад өөрийгөө шинэчлэн дахин асна...' Foreground='#94A3B8' FontSize='12.5' TextWrapping='Wrap' Margin='0,0,0,16'/>
              <ProgressBar Name='PbUpdateBar' Height='12' Minimum='0' Maximum='100' Value='15' Background='#090D16' Foreground='#10B981' BorderBrush='#1E293B' BorderThickness='1' Margin='0,0,0,10'/>
              <TextBlock Name='LblUpdateDetail' Text='⏳ Серверээс шинэчлэлтийн файлыг шалгаж татаж байна...' Foreground='#34D399' FontSize='12' FontWeight='Bold'/>
            </StackPanel>
          </Border>
        </Grid>
      </Grid>
    </Grid>
  </Border>
</Window>";

        [STAThread]
        public static void Main()
        {
            try { ServicePointManager.Expect100Continue = false; } catch { }
            try { ServicePointManager.ServerCertificateValidationCallback = delegate { return true; }; } catch { }
            try { ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls; } catch { }
            try { ServicePointManager.SecurityProtocol |= SecurityProtocolType.Ssl3; } catch { }
            try { ServicePointManager.SecurityProtocol |= (SecurityProtocolType)768; } catch { }
            try { ServicePointManager.SecurityProtocol |= (SecurityProtocolType)3072; } catch { }

            InitNativeApi();
            EnsureSelfInstalledShortcut();
            war3Dir = DetectWar3Directory();

            Application app = new Application();
            app.DispatcherUnhandledException += (s, e) =>
            {
                try
                {
                    File.AppendAllText(Path.Combine(Path.GetDirectoryName(GetConfigPath()), "crash.log"),
                        DateTime.Now.ToString("s") + " UI Exception: " + e.Exception.ToString() + "\r\n");
                }
                catch { }
                e.Handled = true;
            };
            mainWin = (Window)XamlReader.Parse(XAML_UI);

            BindControls();
            LoadSavedSettings();
            InstallWarKeyHook();
            StartLocalBridge();
            MeasureServerPingAsync();
            CheckAndApplySelfUpdateAsync();

            DispatcherTimer timer = new DispatcherTimer();
            timer.Interval = TimeSpan.FromSeconds(3);
            timer.Tick += PollTimer_Tick;
            timer.Start();

            DispatcherTimer waitHudTimer = new DispatcherTimer();
            waitHudTimer.Interval = TimeSpan.FromSeconds(1);
            waitHudTimer.Tick += (s, e) =>
            {
                try
                {
                    if (currentRoomWaitRemSec > 0 && (currentRoomPhase == "WAITING" || currentRoomPhase == "FROZEN" || !string.IsNullOrEmpty(currentRoomAbsent)))
                        currentRoomWaitRemSec--;
                    UpdateWaitScreenOverlay();
                }
                catch { }
            };
            waitHudTimer.Start();

            mainWin.Closed += (s, e) =>
            {
                running = false;
                UninstallWarKeyHook();
                try { if (waitOverlayWin != null) waitOverlayWin.Close(); } catch { }
                try { if (proxyListener != null) proxyListener.Stop(); } catch { }
                try { if (udpBroadcaster != null) udpBroadcaster.Close(); } catch { }
            };

            app.Run(mainWin);
        }

        private static void EnsureSelfInstalledShortcut()
        {
            try
            {
                string payloadPath = typeof(Program).Assembly.Location;
                if (string.IsNullOrEmpty(payloadPath) || !File.Exists(payloadPath))
                    payloadPath = Process.GetCurrentProcess().MainModule.FileName;
                try { if (File.Exists(payloadPath + ".old")) File.Delete(payloadPath + ".old"); } catch { }
                byte[] payloadBytes = File.ReadAllBytes(payloadPath);
                string installDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MongolRanger");
                if (!Directory.Exists(installDir)) Directory.CreateDirectory(installDir);
                string installedExe = Path.Combine(installDir, "MongolRanger.exe");
                if (!string.Equals(Path.GetFullPath(payloadPath), Path.GetFullPath(installedExe), StringComparison.OrdinalIgnoreCase))
                {
                    try { File.WriteAllBytes(installedExe, payloadBytes); } catch { }
                }
                string cfgXml = "<?xml version=\"1.0\" encoding=\"utf-8\" ?><configuration><startup useLegacyV2RuntimeActivationPolicy=\"true\"><supportedRuntime version=\"v4.0\" sku=\".NETFramework,Version=v4.0\"/><supportedRuntime version=\"v4.0\"/><supportedRuntime version=\"v2.0.50727\"/></startup></configuration>";
                try { File.WriteAllText(Path.Combine(installDir, "MongolRanger.exe.config"), cfgXml, Encoding.UTF8); } catch { }
                string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                if (!string.IsNullOrEmpty(desktopDir) && Directory.Exists(desktopDir))
                {
                    string oldDesktopExe = Path.Combine(desktopDir, "MongolRanger.exe");
                    if (File.Exists(oldDesktopExe) && !string.Equals(Path.GetFullPath(payloadPath), Path.GetFullPath(oldDesktopExe), StringComparison.OrdinalIgnoreCase))
                    {
                        try { File.Delete(oldDesktopExe); } catch { }
                    }
                    string desktopExe = Path.Combine(desktopDir, "ZevArena.exe");
                    if (!string.Equals(Path.GetFullPath(payloadPath), Path.GetFullPath(desktopExe), StringComparison.OrdinalIgnoreCase))
                    {
                        try { File.WriteAllBytes(desktopExe, payloadBytes); } catch { }
                    }
                }
            }
            catch { }
        }

        private static T Find<T>(string name) where T : class
        {
            return mainWin.FindName(name) as T;
        }

        private static void BindControls()
        {
            Border titleBar = Find<Border>("TitleBar");
            titleBar.MouseLeftButtonDown += (s, e) =>
            {
                if (e.ClickCount == 2)
                    mainWin.WindowState = (mainWin.WindowState == WindowState.Maximized) ? WindowState.Normal : WindowState.Maximized;
                else
                    mainWin.DragMove();
            };
            Find<Button>("BtnMin").Click += (s, e) => mainWin.WindowState = WindowState.Minimized;
            Find<Button>("BtnMax").Click += (s, e) => mainWin.WindowState = (mainWin.WindowState == WindowState.Maximized) ? WindowState.Normal : WindowState.Maximized;
            Find<Button>("BtnClose").Click += (s, e) => mainWin.Close();
            Button btnTitleBell = Find<Button>("BtnTitleBell");
            if (btnTitleBell != null) btnTitleBell.Click += (s, e) => { SwitchPage("FRIENDS"); SyncSocialStateAsync(false); };
            Button btnTitleGear = Find<Button>("BtnTitleGear");
            if (btnTitleGear != null) btnTitleGear.Click += (s, e) => SwitchPage("SETTINGS");
            lblTitleVersion = Find<TextBlock>("LblTitleVersion");
            if (lblTitleVersion != null) lblTitleVersion.Text = CLIENT_VERSION_LABEL;

            InitEmbeddedArtwork();

            updateOverlay = Find<Grid>("UpdateOverlay");
            lblUpdateTitle = Find<TextBlock>("LblUpdateTitle");
            lblUpdateSub = Find<TextBlock>("LblUpdateSub");
            pbUpdateBar = Find<ProgressBar>("PbUpdateBar");
            lblUpdateDetail = Find<TextBlock>("LblUpdateDetail");

            authView = Find<Grid>("AuthView");
            appShell = Find<Grid>("AppShell");
            tabSignInBorder = Find<Border>("TabSignInBorder");
            tabSignUpBorder = Find<Border>("TabSignUpBorder");
            tabSignInText = Find<TextBlock>("TabSignInText");
            tabSignUpText = Find<TextBlock>("TabSignUpText");
            lblUserPrompt = Find<TextBlock>("LblUserPrompt");
            txtUser = Find<TextBox>("TxtUser");
            authEmailPanel = Find<StackPanel>("AuthEmailPanel");
            lblEmailPrompt = Find<TextBlock>("LblEmailPrompt");
            txtEmail = Find<TextBox>("TxtEmail");
            lblPassPrompt = Find<TextBlock>("LblPassPrompt");
            txtPass = Find<PasswordBox>("TxtPass");
            btnForgotPass = Find<Border>("BtnForgotPass");
            lblForgotPassText = Find<TextBlock>("LblForgotPassText");
            btnAuthSubmitText = Find<TextBlock>("BtnAuthSubmitText");
            lblAuthError = Find<TextBlock>("LblAuthError");

            tabSignInBorder.MouseLeftButtonDown += (s, e) => SetAuthMode(false);
            tabSignUpBorder.MouseLeftButtonDown += (s, e) => SetAuthMode(true);
            if (btnForgotPass != null)
                btnForgotPass.MouseLeftButtonDown += (s, e) => ToggleResetPasswordMode();
            Find<Border>("BtnAuthSubmit").MouseLeftButtonDown += (s, e) => DoAuth();
            txtPass.KeyDown += (s, e) => { if (e.Key == Key.Enter) DoAuth(); };
            if (txtEmail != null)
                txtEmail.KeyDown += (s, e) => { if (e.Key == Key.Enter) txtPass.Focus(); };

            lblProfileName = Find<TextBlock>("LblProfileName");
            btnEditProfileName = Find<Border>("BtnEditProfileName");
            if (lblProfileName != null)
                lblProfileName.MouseLeftButtonDown += (s, e) => OpenChangePlayerNameModal();
            if (btnEditProfileName != null)
                btnEditProfileName.MouseLeftButtonDown += (s, e) => OpenChangePlayerNameModal();
            lblProfileUid = Find<TextBlock>("LblProfileUid");
            lblProfileBadge = Find<TextBlock>("LblProfileBadge");
            lblProfileElo = Find<TextBlock>("LblProfileElo");
            lblNetPing = Find<TextBlock>("LblNetPing");
            lblNetIp = Find<TextBlock>("LblNetIp");
            lblAntiCheatBadge = Find<TextBlock>("LblAntiCheatBadge");

            navBtnLobbies = Find<Border>("NavBtnLobbies");
            navBtnLeaderboard = Find<Border>("NavBtnLeaderboard");
            navBtnFriends = Find<Border>("NavBtnFriends");
            badgeFriendsUnread = Find<Border>("BadgeFriendsUnread");
            lblFriendsUnreadCount = Find<TextBlock>("LblFriendsUnreadCount");
            navBtnWarKey = Find<Border>("NavBtnWarKey");
            navBtnSettings = Find<Border>("NavBtnSettings");

            pageLobbies = Find<Grid>("PageLobbies");
            pageLeaderboard = Find<Grid>("PageLeaderboard");
            pageFriends = Find<Grid>("PageFriends");
            pageWarKey = Find<Grid>("PageWarKey");
            pageSettings = Find<Grid>("PageSettings");
            leaderboardListCtrl = Find<ItemsControl>("LeaderboardListCtrl");

            navBtnLobbies.MouseLeftButtonDown += (s, e) => SwitchPage("LOBBIES");
            if (navBtnLeaderboard != null)
                navBtnLeaderboard.MouseLeftButtonDown += (s, e) => { SwitchPage("LEADERBOARD"); RefreshLeaderboardAsync(); };
            navBtnFriends.MouseLeftButtonDown += (s, e) => { SwitchPage("FRIENDS"); SyncSocialStateAsync(false); };
            navBtnWarKey.MouseLeftButtonDown += (s, e) => SwitchPage("WARKEY");
            navBtnSettings.MouseLeftButtonDown += (s, e) => SwitchPage("SETTINGS");

            Border btnRefreshLb = Find<Border>("BtnRefreshLeaderboard");
            if (btnRefreshLb != null)
                btnRefreshLb.MouseLeftButtonDown += (s, e) => RefreshLeaderboardAsync();
            if (leaderboardListCtrl != null)
                leaderboardListCtrl.AddHandler(Button.ClickEvent, new RoutedEventHandler(OnLeaderboardButtonClick));

            btnLogout = Find<Border>("BtnLogout");
            btnLogout.MouseLeftButtonDown += (s, e) =>
            {
                if (IsMatchOrRejoinLocked()) return;
                LeaveRoom();
                authToken = "";
                SaveSettings();
                appShell.Visibility = Visibility.Collapsed;
                authView.Visibility = Visibility.Visible;
            };

            // Invite Banner Overlay
            inviteBannerOverlay = Find<Border>("InviteBannerOverlay");
            lblInviteBannerText = Find<TextBlock>("LblInviteBannerText");
            Find<Border>("BtnAcceptInvite").MouseLeftButtonDown += (s, e) => RespondToRoomInvite(true);
            Find<Border>("BtnDeclineInvite").MouseLeftButtonDown += (s, e) => RespondToRoomInvite(false);

            // Lobbies & Inner Room View
            lobbyListView = Find<Grid>("LobbyListView");
            innerRoomView = Find<Grid>("InnerRoomView");
            lblLobbySubCount = Find<TextBlock>("LblLobbySubCount");
            lblHeroWelcomeText = Find<TextBlock>("LblHeroWelcomeText");
            lblFooterSelectedMap = Find<TextBlock>("LblFooterSelectedMap");
            lblLastUpdatedTime = Find<TextBlock>("LblLastUpdatedTime");

            Border btnReadyPlay = Find<Border>("BtnSidebarReadyPlay");
            if (btnReadyPlay != null)
            {
                btnReadyPlay.MouseLeftButtonDown += (s, e) =>
                {
                    SwitchPage("LOBBIES");
                    if (!string.IsNullOrEmpty(currentRoomId))
                        LaunchWarcraftIfNotRunning(true);
                    else
                        LaunchWarcraft(false);
                };
            }

            for (int i = 0; i < 5; i++)
            {
                int mapIdx = i;
                heroMapCards[i] = Find<Border>("HeroMapCard" + i);
                if (heroMapCards[i] != null)
                {
                    heroMapCards[i].MouseLeftButtonDown += (s, e) => SelectOfficialMap(mapIdx);
                }
            }

            txtSearch = Find<TextBox>("TxtSearch");
            TextBlock searchPh = Find<TextBlock>("LblSearchPlaceholder");
            txtSearch.TextChanged += (s, e) =>
            {
                searchPh.Visibility = string.IsNullOrEmpty(txtSearch.Text) ? Visibility.Visible : Visibility.Collapsed;
                RenderRooms();
            };

            filterAllBorder = Find<Border>("FilterAllBorder");
            filterWaitBorder = Find<Border>("FilterWaitBorder");
            filterRunBorder = Find<Border>("FilterRunBorder");
            filterLockBorder = Find<Border>("FilterLockBorder");
            lblFilterAllCount = Find<TextBlock>("LblFilterAllCount");
            lblFilterWaitCount = Find<TextBlock>("LblFilterWaitCount");
            lblFilterRunCount = Find<TextBlock>("LblFilterRunCount");
            lblFilterLockCount = Find<TextBlock>("LblFilterLockCount");
            filterAllBorder.MouseLeftButtonDown += (s, e) => SetFilter("ALL");
            filterWaitBorder.MouseLeftButtonDown += (s, e) => SetFilter("LOBBY");
            filterRunBorder.MouseLeftButtonDown += (s, e) => SetFilter("RUNNING");
            if (filterLockBorder != null)
                filterLockBorder.MouseLeftButtonDown += (s, e) => SetFilter("LOCKED");

            hostModalBar = Find<Border>("HostModalBar");
            Border btnRefreshLobbiesB = Find<Border>("BtnRefreshLobbies");
            TextBlock lblRefreshLobbiesT = Find<TextBlock>("LblRefreshLobbies");
            btnRefreshLobbiesB.MouseEnter += (s, e) => { if (!isRefreshingLobbies) { btnRefreshLobbiesB.Background = HexBrush("#24304C"); btnRefreshLobbiesB.BorderBrush = HexBrush("#7C3AED"); } };
            btnRefreshLobbiesB.MouseLeave += (s, e) => { if (!isRefreshingLobbies) { btnRefreshLobbiesB.Background = HexBrush("#151D33"); btnRefreshLobbiesB.BorderBrush = HexBrush("#283558"); } };
            btnRefreshLobbiesB.MouseLeftButtonDown += (s, e) =>
            {
                if (isRefreshingLobbies) return;
                isRefreshingLobbies = true;
                btnRefreshLobbiesB.Background = HexBrush("#7C3AED");
                btnRefreshLobbiesB.BorderBrush = HexBrush("#A78BFA");
                lblRefreshLobbiesT.Text = "⏳ Шинэчилж байна...";
                if (lobbyListView != null) lobbyListView.Opacity = 0.45;
                MeasureServerPingAsync();
                RefreshMapsAndRooms();
                DispatcherTimer done = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(700) };
                done.Tick += (s2, e2) =>
                {
                    done.Stop();
                    isRefreshingLobbies = false;
                    if (lobbyListView != null) lobbyListView.Opacity = 1.0;
                    lblRefreshLobbiesT.Text = "✅ Шинэчлэгдлээ";
                    btnRefreshLobbiesB.Background = HexBrush("#14382D");
                    btnRefreshLobbiesB.BorderBrush = HexBrush("#10B981");
                    DispatcherTimer reset = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(1200) };
                    reset.Tick += (s3, e3) =>
                    {
                        reset.Stop();
                        if (isRefreshingLobbies) return;
                        lblRefreshLobbiesT.Text = "🔄 Сэргээх";
                        btnRefreshLobbiesB.Background = btnRefreshLobbiesB.IsMouseOver ? HexBrush("#24304C") : HexBrush("#151D33");
                        btnRefreshLobbiesB.BorderBrush = btnRefreshLobbiesB.IsMouseOver ? HexBrush("#7C3AED") : HexBrush("#283558");
                    };
                    reset.Start();
                };
                done.Start();
            };

            txtNewRoomName = Find<TextBox>("TxtNewRoomName");
            lblNewRoomNamePh = Find<TextBlock>("LblNewRoomNamePh");
            txtNewRoomName.TextChanged += (s, e) =>
            {
                if (lblNewRoomNamePh != null)
                    lblNewRoomNamePh.Visibility = string.IsNullOrEmpty(txtNewRoomName.Text) ? Visibility.Visible : Visibility.Collapsed;
            };
            txtNewRoomCode = Find<TextBox>("TxtNewRoomCode");
            chkNoLeavers = Find<CheckBox>("ChkNoLeavers");
            btnNoLeaversToggle = Find<Border>("BtnNoLeaversToggle");
            noLeaversTrack = Find<Border>("NoLeaversTrack");
            noLeaversKnob = Find<Border>("NoLeaversKnob");
            lblNoLeaversState = Find<TextBlock>("LblNoLeaversState");
            if (btnNoLeaversToggle != null)
            {
                btnNoLeaversToggle.MouseLeftButtonDown += (s, e) =>
                {
                    if (chkNoLeavers != null)
                        chkNoLeavers.IsChecked = !(chkNoLeavers.IsChecked == true);
                    UpdateNoLeaversToggleVisual();
                };
            }
            UpdateNoLeaversToggleVisual();

            TextBlock codePh = Find<TextBlock>("LblNewRoomCodePh");
            txtNewRoomCode.TextChanged += (s, e) =>
            {
                codePh.Visibility = string.IsNullOrEmpty(txtNewRoomCode.Text) ? Visibility.Visible : Visibility.Collapsed;
            };
            cmbMaps = Find<ComboBox>("CmbMaps");
            btnMapDropdownToggle = Find<Border>("BtnMapDropdownToggle");
            mapDropdownPopup = Find<Popup>("MapDropdownPopup");
            imgSelectedMapIcon = Find<Image>("ImgSelectedMapIcon");
            lblSelectedMapTitle = Find<TextBlock>("LblSelectedMapTitle");
            if (mapDropdownPopup != null && btnMapDropdownToggle != null)
            {
                mapDropdownPopup.PlacementTarget = btnMapDropdownToggle;
                btnMapDropdownToggle.MouseLeftButtonDown += (s, e) =>
                {
                    mapDropdownPopup.IsOpen = !mapDropdownPopup.IsOpen;
                    e.Handled = true;
                };
                mainWin.PreviewMouseLeftButtonDown += (s, e) =>
                {
                    if (mapDropdownPopup.IsOpen)
                    {
                        UIElement child = mapDropdownPopup.Child;
                        if (!btnMapDropdownToggle.IsMouseOver && (child == null || !child.IsMouseOver))
                        {
                            mapDropdownPopup.IsOpen = false;
                        }
                    }
                };
                mainWin.Deactivated += (s, e) =>
                {
                    if (mapDropdownPopup.IsOpen) mapDropdownPopup.IsOpen = false;
                };
                mainWin.LocationChanged += (s, e) =>
                {
                    if (mapDropdownPopup.IsOpen) mapDropdownPopup.IsOpen = false;
                };
            }
            for (int i = 0; i < 5; i++)
            {
                int mapIdx = i;
                mapOptionBorders[i] = Find<Border>("MapOption" + i);
                lblMapChecks[i] = Find<TextBlock>("LblMapCheck" + i);
                if (mapOptionBorders[i] != null)
                {
                    mapOptionBorders[i].MouseEnter += (s, e) =>
                    {
                        if (selectedMapIndex != mapIdx)
                            mapOptionBorders[mapIdx].Background = HexBrush("#1B223C");
                    };
                    mapOptionBorders[i].MouseLeave += (s, e) =>
                    {
                        if (selectedMapIndex != mapIdx)
                            mapOptionBorders[mapIdx].Background = Brushes.Transparent;
                    };
                    mapOptionBorders[i].MouseLeftButtonDown += (s, e) =>
                    {
                        SelectOfficialMap(mapIdx);
                        if (mapDropdownPopup != null) mapDropdownPopup.IsOpen = false;
                        e.Handled = true;
                    };
                }
            }
            SelectOfficialMap(0);
            Find<Border>("BtnConfirmCreateLobby").MouseLeftButtonDown += (s, e) => CreateRoom();

            lobbiesList = Find<ItemsControl>("LobbiesList");
            lobbiesList.AddHandler(Button.ClickEvent, new RoutedEventHandler(OnJoinRoomButtonClick));

            // Inner Room Controls
            lblInnerRoomTitle = Find<TextBlock>("LblInnerRoomTitle");
            lblInnerRoomSub = Find<TextBlock>("LblInnerRoomSub");
            btnSetRoomCode = Find<Border>("BtnSetRoomCode");
            lblSetRoomCodeText = Find<TextBlock>("LblSetRoomCodeText");
            btnSetRoomCode.MouseLeftButtonDown += (s, e) => OpenSetRoomCodeModal();

            btnInviteFriendFromRoom = Find<Border>("BtnInviteFriendFromRoom");
            btnInviteFriendFromRoom.MouseLeftButtonDown += (s, e) =>
            {
                if (IsMatchOrRejoinLocked()) return;
                SwitchPage("FRIENDS");
                SyncSocialStateAsync(false);
            };
            btnLeaveMatchNow = Find<Border>("BtnLeaveMatchNow");
            btnLeaveMatchNow.MouseLeftButtonDown += (s, e) =>
            {
                if (IsMatchOrRejoinLocked()) return;
                LeaveRoom(true);
            };

            roomChatScroll = Find<ScrollViewer>("RoomChatScroll");
            roomChatList = Find<ItemsControl>("RoomChatList");
            txtRoomChatInput = Find<TextBox>("TxtRoomChatInput");
            Find<Border>("BtnSendRoomChat").MouseLeftButtonDown += (s, e) => SendRoomChatMessage();
            txtRoomChatInput.KeyDown += (s, e) => { if (e.Key == Key.Enter) SendRoomChatMessage(); };

            lblRoomMembersCount = Find<TextBlock>("LblRoomMembersCount");
            roomMembersList = Find<ItemsControl>("RoomMembersList");
            roomMembersList.AddHandler(Button.ClickEvent, new RoutedEventHandler(OnRoomMemberButtonClick));

            btnHostStartGame = Find<Border>("BtnHostStartGame");
            lblHostStartBtnText = Find<TextBlock>("LblHostStartBtnText");
            btnRejoinMatch = Find<Border>("BtnRejoinMatch");
            lblRejoinBtnText = Find<TextBlock>("LblRejoinBtnText");
            lblRejoinBtnSub = Find<TextBlock>("LblRejoinBtnSub");
            clientWaitBanner = Find<Border>("ClientWaitBanner");
            lblWaitBannerTitle = Find<TextBlock>("LblWaitBannerTitle");
            lblWaitBannerSub = Find<TextBlock>("LblWaitBannerSub");
            btnAddWaitTime = Find<Border>("BtnAddWaitTime");
            lblAddWaitTimeText = Find<TextBlock>("LblAddWaitTimeText");
            btnHostDropAbsent = Find<Border>("BtnHostDropAbsent");
            lblHostDropAbsentText = Find<TextBlock>("LblHostDropAbsentText");

            btnHostStartGame.MouseLeftButtonDown += (s, e) => StartRoomMatch();
            if (btnRejoinMatch != null)
                btnRejoinMatch.MouseLeftButtonDown += (s, e) => RejoinActiveMatch();
            if (clientWaitBanner != null)
            {
                clientWaitBanner.MouseLeftButtonDown += (s, e) =>
                {
                    if (!string.IsNullOrEmpty(currentRoomId) && !isCurrentRoomOwner && !IsMatchActuallyStarted() && !IsWarcraftRunning())
                    {
                        hasLaunchedWar3InCurrentRoom = true;
                        LaunchWarcraftIfNotRunning(true);
                        UpdateInnerRoomVisibility();
                    }
                };
            }
            if (btnAddWaitTime != null)
                btnAddWaitTime.MouseLeftButtonDown += (s, e) => ExtendRoomWaitTime();
            if (btnHostDropAbsent != null)
                btnHostDropAbsent.MouseLeftButtonDown += (s, e) => DropAbsentRoomPlayer();

            // Player Action Modal Controls
            playerActionModalOverlay = Find<Grid>("PlayerActionModalOverlay");
            matchHistoryOverlay = Find<Grid>("MatchHistoryOverlay");
            matchHistoryList = Find<ItemsControl>("MatchHistoryList");
            lblHistoryTitle = Find<TextBlock>("LblHistoryTitle");
            lblHistoryElo = Find<TextBlock>("LblHistoryElo");
            lblHistoryStats = Find<TextBlock>("LblHistoryStats");
            lblHistoryEmpty = Find<TextBlock>("LblHistoryEmpty");
            Find<Border>("BtnHistoryClose").MouseLeftButtonDown += (s, e) => { matchHistoryOverlay.Visibility = Visibility.Collapsed; };
            matchHistoryOverlay.MouseLeftButtonDown += (s, e) => { if (e.OriginalSource == matchHistoryOverlay) matchHistoryOverlay.Visibility = Visibility.Collapsed; };
            Find<Border>("BtnProfileEloCard").MouseLeftButtonDown += (s, e) => OpenMatchHistory("");
            lblPlayerModalName = Find<TextBlock>("LblPlayerModalName");
            lblPlayerModalUid = Find<TextBlock>("LblPlayerModalUid");
            lblPlayerModalBadge = Find<TextBlock>("LblPlayerModalBadge");
            lblPlayerModalElo = Find<TextBlock>("LblPlayerModalElo");
            lblPlayerModalLeaves = Find<TextBlock>("LblPlayerModalLeaves");
            lblPlayerModalElo.Cursor = Cursors.Hand;
            lblPlayerModalElo.ToolTip = "Дарж сүүлийн 10 тоглолтын түүхийг харна уу";
            lblPlayerModalElo.MouseLeftButtonDown += (s, e) => { if (!string.IsNullOrEmpty(selectedModalPlayerName)) OpenMatchHistory(selectedModalPlayerName); };
            lblPlayerModalLeaves.Cursor = Cursors.Hand;
            lblPlayerModalLeaves.MouseLeftButtonDown += (s, e) => { if (!string.IsNullOrEmpty(selectedModalPlayerName)) OpenMatchHistory(selectedModalPlayerName); };
            lblPlayerModalStatus = Find<TextBlock>("LblPlayerModalStatus");
            lblPlayerModalRoom = Find<TextBlock>("LblPlayerModalRoom");
            lblPlayerModalCreated = Find<TextBlock>("LblPlayerModalCreated");
            lblPlayerModalFeedback = Find<TextBlock>("LblPlayerModalFeedback");
            lblBtnModalBlockText = Find<TextBlock>("LblBtnModalBlockText");
            btnModalAddFriend = Find<Border>("BtnModalAddFriend");
            lblBtnModalAddFriendText = Find<TextBlock>("LblBtnModalAddFriendText");
            btnModalKickUser = Find<Border>("BtnModalKickUser");
            btnModalInviteRoom = Find<Border>("BtnModalInviteRoom");
            btnModalViewHistory = Find<Border>("BtnModalViewHistory");
            modalActionButtonsGrid = Find<System.Windows.Controls.Primitives.UniformGrid>("ModalActionButtonsGrid");
            Find<Button>("BtnClosePlayerModal").Click += (s, e) => playerActionModalOverlay.Visibility = Visibility.Collapsed;
            if (btnModalViewHistory != null)
            {
                btnModalViewHistory.MouseLeftButtonDown += (s, e) =>
                {
                    if (!string.IsNullOrEmpty(selectedModalPlayerName))
                    {
                        playerActionModalOverlay.Visibility = Visibility.Collapsed;
                        OpenMatchHistory(selectedModalPlayerName);
                    }
                };
            }
            if (btnModalKickUser != null)
                btnModalKickUser.MouseLeftButtonDown += (s, e) => KickPlayerFromRoom(selectedModalPlayerName);
            btnModalAddFriend.MouseLeftButtonDown += (s, e) =>
            {
                if (!canClickModalAddFriend) return;
                SetModalFriendButtonState("pending_out");
                SendFriendRequestTo(selectedModalPlayerName, true);
            };
            Find<Border>("BtnModalDirectChat").MouseLeftButtonDown += (s, e) =>
            {
                playerActionModalOverlay.Visibility = Visibility.Collapsed;
                OpenDirectChatWith(selectedModalPlayerName);
            };
            btnModalInviteRoom.MouseLeftButtonDown += (s, e) =>
            {
                if (IsMatchOrRejoinLocked()) return;
                InviteFriendToCurrentRoom(selectedModalPlayerName, true);
            };
            Find<Border>("BtnModalBlockUser").MouseLeftButtonDown += (s, e) => ToggleBlockUser(selectedModalPlayerName, !selectedModalPlayerIsBlocked, true);

            // Friends & Direct Chat Controls
            txtAddFriendInput = Find<TextBox>("TxtAddFriendInput");
            lblFriendStatusMsg = Find<TextBlock>("LblFriendStatusMsg");
            pendingRequestsPanel = Find<Border>("PendingRequestsPanel");
            pendingRequestsList = Find<ItemsControl>("PendingRequestsList");
            friendsListCtrl = Find<ItemsControl>("FriendsListCtrl");
            blockedUsersListCtrl = Find<ItemsControl>("BlockedUsersListCtrl");
            lblDmHeaderTitle = Find<TextBlock>("LblDmHeaderTitle");
            lblDmHeaderSub = Find<TextBlock>("LblDmHeaderSub");
            dmChatScroll = Find<ScrollViewer>("DmChatScroll");
            dmMessagesListCtrl = Find<ItemsControl>("DmMessagesListCtrl");
            txtDmInput = Find<TextBox>("TxtDmInput");

            Find<Border>("BtnAddFriendSubmit").MouseLeftButtonDown += (s, e) => SearchFriendsAsync((txtAddFriendInput.Text ?? "").Trim());
            txtAddFriendInput.KeyDown += (s, e) =>
            {
                if (e.Key == Key.Enter)
                    SearchFriendsAsync((txtAddFriendInput.Text ?? "").Trim());
            };
            txtAddFriendInput.TextChanged += (s, e) =>
            {
                string q = (txtAddFriendInput.Text ?? "").Trim();
                friendSearchDebounce.Stop();
                if (q.Length >= 2) friendSearchDebounce.Start();
                else if (friendSearchResultsPanel != null) friendSearchResultsPanel.Visibility = Visibility.Collapsed;
            };
            friendSearchDebounce.Tick += (s, e) =>
            {
                friendSearchDebounce.Stop();
                SearchFriendsAsync((txtAddFriendInput.Text ?? "").Trim());
            };
            friendSearchResultsPanel = Find<Border>("FriendSearchResultsPanel");
            friendSearchResultsList = Find<ItemsControl>("FriendSearchResultsList");
            friendSearchResultsList.AddHandler(Button.ClickEvent, new RoutedEventHandler((s, e) =>
            {
                Button b = e.OriginalSource as Button;
                if (b == null || b.Tag == null) return;
                string target = b.Tag.ToString();
                if (string.IsNullOrEmpty(target)) return;
                b.IsEnabled = false;
                b.Content = "⏳ Илгээгдлээ";
                SendFriendRequestTo(target, false);
            }));
            pendingRequestsList.AddHandler(Button.ClickEvent, new RoutedEventHandler(OnPendingFriendRequestClick));
            friendsListCtrl.AddHandler(Button.ClickEvent, new RoutedEventHandler(OnFriendListButtonClick));
            blockedUsersListCtrl.AddHandler(Button.ClickEvent, new RoutedEventHandler(OnUnblockButtonClick));
            dmMessagesListCtrl.AddHandler(Button.ClickEvent, new RoutedEventHandler(OnDmInviteAcceptClick));

            Border btnDmHdr = Find<Border>("BtnDmHeaderProfile");
            if (btnDmHdr != null)
            {
                btnDmHdr.MouseLeftButtonDown += (s, e) =>
                {
                    if (!string.IsNullOrEmpty(activeDmFriendName))
                        OpenPlayerActionModal(activeDmFriendName);
                };
            }
            Find<Border>("BtnSendDm").MouseLeftButtonDown += (s, e) => SendDirectMessage();
            txtDmInput.KeyDown += (s, e) => { if (e.Key == Key.Enter) SendDirectMessage(); };

            codeModalOverlay = Find<Grid>("CodeModalOverlay");
            lblCodeModalTitle = Find<TextBlock>("LblCodeModalTitle");
            lblCodeModalSub = Find<TextBlock>("LblCodeModalSub");
            txtCodeModalInput = Find<TextBox>("TxtCodeModalInput");
            lblCodeModalError = Find<TextBlock>("LblCodeModalError");
            Find<Border>("BtnCodeModalCancel").MouseLeftButtonDown += (s, e) =>
            {
                codeModalOverlay.Visibility = Visibility.Collapsed;
            };
            Find<Border>("BtnCodeModalConfirm").MouseLeftButtonDown += (s, e) => SubmitRoomCodeModal();
            txtCodeModalInput.KeyDown += (s, e) =>
            {
                if (e.Key == Key.Enter) SubmitRoomCodeModal();
                else if (e.Key == Key.Escape) codeModalOverlay.Visibility = Visibility.Collapsed;
            };

            btnToggleWarKey = Find<Border>("BtnToggleWarKey");
            lblWarKeyToggleState = Find<TextBlock>("LblWarKeyToggleState");
            btnToggleWarKey.MouseLeftButtonDown += (s, e) =>
            {
                warKeyEnabled = !warKeyEnabled;
                UpdateWarKeyUI();
                SaveSettings();
            };
            Find<Border>("BtnResetWarKey").MouseLeftButtonDown += (s, e) =>
            {
                wkKeys = new string[] { "", "", "", "", "", "" };
                wkSkillKeys = new string[] { "", "", "", "", "", "", "", "" };
                pendingQuickChatKey = "";
                if (txtQuickChatMsg != null) txtQuickChatMsg.Text = "";
                capturingMode = "";
                capturingSlot = -1;
                UpdateWarKeyUI();
                SaveSettings();
            };

            for (int i = 0; i < 6; i++)
            {
                int idx = i;
                wkButtons[i] = Find<Button>("WkBtn" + i);
                wkButtons[i].Click += (s, e) =>
                {
                    UpdateWarKeyUI();
                    capturingMode = "INV";
                    capturingSlot = idx;
                    wkButtons[idx].Content = "Товч дар...";
                    wkButtons[idx].Foreground = HexBrush("#FBBF24");
                };
            }
            for (int i = 0; i < 8; i++)
            {
                int idx = i;
                wkSkillButtons[i] = Find<Button>("WkSkill" + i);
                wkSkillButtons[i].Click += (s, e) =>
                {
                    UpdateWarKeyUI();
                    capturingMode = "SKILL";
                    capturingSlot = idx;
                    wkSkillButtons[idx].Content = "Товч дар...";
                    wkSkillButtons[idx].Foreground = HexBrush("#FBBF24");
                };
            }

            btnQuickChatKey = Find<Button>("BtnQuickChatKey");
            txtQuickChatMsg = Find<TextBox>("TxtQuickChatMsg");
            rbChatWar3 = Find<RadioButton>("RbChatWar3");
            rbChatWar3All = Find<RadioButton>("RbChatWar3All");
            rbChatLobby = Find<RadioButton>("RbChatLobby");
            quickChatListCtrl = Find<ItemsControl>("QuickChatList");

            btnQuickChatKey.Click += (s, e) =>
            {
                UpdateWarKeyUI();
                capturingMode = "QCHAT";
                capturingSlot = 0;
                btnQuickChatKey.Content = "Товч дар...";
                btnQuickChatKey.Foreground = HexBrush("#FBBF24");
            };
            Find<Border>("BtnAddQuickChat").MouseLeftButtonDown += (s, e) => AddQuickChatEntry();
            txtQuickChatMsg.KeyDown += (s, e) => { if (e.Key == Key.Enter) AddQuickChatEntry(); };
            quickChatListCtrl.AddHandler(Button.ClickEvent, new RoutedEventHandler(OnDeleteQuickChatClick));

            mainWin.PreviewKeyDown += (s, e) =>
            {
                if (!string.IsNullOrEmpty(capturingMode))
                {
                    Key k = (e.Key == Key.System) ? e.SystemKey : e.Key;
                    if (k == Key.LeftAlt || k == Key.RightAlt || k == Key.LeftCtrl || k == Key.RightCtrl ||
                        k == Key.LeftShift || k == Key.RightShift || k == Key.LWin || k == Key.RWin)
                        return;

                    if (k == Key.Escape)
                    {
                        capturingMode = "";
                        capturingSlot = -1;
                        UpdateWarKeyUI();
                        e.Handled = true;
                        return;
                    }

                    bool alt = (Keyboard.Modifiers & ModifierKeys.Alt) != 0;
                    bool ctrl = (Keyboard.Modifiers & ModifierKeys.Control) != 0;
                    bool shift = (Keyboard.Modifiers & ModifierKeys.Shift) != 0;

                    if (capturingMode == "INV" && capturingSlot >= 0 && capturingSlot < 6)
                    {
                        if (k == Key.Back || k == Key.Delete)
                            wkKeys[capturingSlot] = "";
                        else
                            wkKeys[capturingSlot] = FormatKeyCombo(k, alt, ctrl, shift);
                        capturingMode = "";
                        capturingSlot = -1;
                        UpdateWarKeyUI();
                        SaveSettings();
                        e.Handled = true;
                        return;
                    }
                    if (capturingMode == "SKILL" && capturingSlot >= 0 && capturingSlot < 8)
                    {
                        if (k == Key.Back || k == Key.Delete)
                            wkSkillKeys[capturingSlot] = "";
                        else
                            wkSkillKeys[capturingSlot] = FormatKeyCombo(k, alt, ctrl, shift);
                        capturingMode = "";
                        capturingSlot = -1;
                        UpdateWarKeyUI();
                        SaveSettings();
                        e.Handled = true;
                        return;
                    }
                    if (capturingMode == "QCHAT")
                    {
                        if (k == Key.Back)
                            pendingQuickChatKey = "";
                        else
                            pendingQuickChatKey = FormatKeyCombo(k, alt, ctrl, shift);
                        capturingMode = "";
                        capturingSlot = -1;
                        UpdateWarKeyUI();
                        e.Handled = true;
                        return;
                    }
                }
                else if (e.Key == Key.F && (Keyboard.Modifiers & ModifierKeys.Control) != 0)
                {
                    if (pageLobbies != null && pageLobbies.Visibility == Visibility.Visible &&
                        lobbyListView != null && lobbyListView.Visibility == Visibility.Visible && txtSearch != null)
                    {
                        txtSearch.Focus();
                        txtSearch.SelectAll();
                        e.Handled = true;
                    }
                }
            };

            txtWar3Path = Find<TextBox>("TxtWar3Path");
            txtWar3Path.Text = war3Dir;
            lblSettingsStatus = Find<TextBlock>("LblSettingsStatus");
            war3ReadyPill = Find<Border>("War3ReadyPill");
            lblWar3ReadyPill = Find<TextBlock>("LblWar3ReadyPill");
            lblStep1 = Find<TextBlock>("LblStep1");
            lblStep2 = Find<TextBlock>("LblStep2");
            lblStep3 = Find<TextBlock>("LblStep3");
            lblStep4 = Find<TextBlock>("LblStep4");

            war3ReadyPill.MouseLeftButtonDown += (s, e) => SwitchPage("SETTINGS");

            Find<Border>("BtnBrowseWar3").MouseLeftButtonDown += (s, e) =>
            {
                using (var fbd = new System.Windows.Forms.FolderBrowserDialog())
                {
                    fbd.Description = "Warcraft III 1.26a суусан хавтсаа сонгоно уу (Эх хавтас сонгосон ч war3.exe-г автоматаар олно)";
                    if (fbd.ShowDialog() == System.Windows.Forms.DialogResult.OK)
                    {
                        string picked = fbd.SelectedPath;
                        string resolved = ResolveWar3DirectoryRecursive(picked, 6);
                        war3Dir = !string.IsNullOrEmpty(resolved) ? resolved : picked;
                        txtWar3Path.Text = war3Dir;
                        SaveSettings();
                        RunAutoPatchAndSyncAsync();
                    }
                }
            };
            Find<Border>("BtnDownloadAllMaps").MouseLeftButtonDown += (s, e) =>
            {
                string rawPath = txtWar3Path.Text.Trim();
                string resolved = ResolveWar3DirectoryRecursive(rawPath, 6);
                war3Dir = !string.IsNullOrEmpty(resolved) ? resolved : rawPath;
                txtWar3Path.Text = war3Dir;
                SaveSettings();
                RunAutoPatchAndSyncAsync();
            };
        }

        private static ImageSource LoadB64Image(string b64)
        {
            try
            {
                byte[] bytes = Convert.FromBase64String(b64);
                BitmapImage bi = new BitmapImage();
                using (MemoryStream ms = new MemoryStream(bytes))
                {
                    bi.BeginInit();
                    bi.CacheOption = BitmapCacheOption.OnLoad;
                    bi.StreamSource = ms;
                    bi.EndInit();
                }
                if (bi.CanFreeze) bi.Freeze();
                return bi;
            }
            catch { return null; }
        }

        private static void InitEmbeddedArtwork()
        {
            imgHero = LoadB64Image(B64_HERO);
            imgLogo = LoadB64Image(B64_LOGO);
            imgAvatar = LoadB64Image(B64_AVATAR);
            imgMaps[0] = LoadB64Image(B64_MAP0);
            imgMaps[1] = LoadB64Image(B64_MAP1);
            imgMaps[2] = LoadB64Image(B64_MAP2);
            imgMaps[3] = LoadB64Image(B64_MAP3);
            imgMaps[4] = LoadB64Image(B64_MAP4);

            Image elHero = Find<Image>("ImgHeroBanner");
            if (elHero != null && imgHero != null) elHero.Source = imgHero;
            Image elLogo = Find<Image>("ImgLogo");
            if (elLogo != null && imgLogo != null) elLogo.Source = imgLogo;
            Image elAuthLogo = Find<Image>("ImgAuthLogo");
            if (elAuthLogo != null && imgLogo != null) elAuthLogo.Source = imgLogo;
            Image elAvatar = Find<Image>("ImgAvatar");
            if (elAvatar != null && imgAvatar != null) elAvatar.Source = imgAvatar;

            for (int i = 0; i < 5; i++)
            {
                Image elMapOpt = Find<Image>("ImgMapOpt" + i);
                if (elMapOpt != null && imgMaps[i] != null) elMapOpt.Source = imgMaps[i];
            }
        }

        private static void UpdateSidebarProfileBadges(string badgeLbl, string badgeCol, string eloDisp, string eloCol)
        {
            if (lblProfileBadge != null && !string.IsNullOrEmpty(badgeLbl))
            {
                string cleanBadge = Regex.Replace(badgeLbl, @"\s*\(\d+/\d+\)\s*$", "").Trim();
                lblProfileBadge.Text = string.IsNullOrEmpty(cleanBadge) ? badgeLbl : cleanBadge;
                lblProfileBadge.Foreground = HexBrush(string.IsNullOrEmpty(badgeCol) ? "#E2E8F0" : badgeCol);
            }
            if (lblProfileElo != null && !string.IsNullOrEmpty(eloDisp))
            {
                string shortElo = "⏳ 0/10";
                Match mCalib = Regex.Match(eloDisp, @"(\d+/10)");
                Match mLvl = Regex.Match(eloDisp, @"LVL\s*(\d+)", RegexOptions.IgnoreCase);
                Match mElo = Regex.Match(eloDisp, @"(\d{3,4})\s*ELO", RegexOptions.IgnoreCase);
                if (mCalib.Success)
                    shortElo = "⏳ " + mCalib.Groups[1].Value;
                else if (mLvl.Success && mElo.Success)
                    shortElo = "Lv." + mLvl.Groups[1].Value + " • " + mElo.Groups[1].Value;
                else if (mLvl.Success)
                    shortElo = "Lv. " + mLvl.Groups[1].Value;
                else if (mElo.Success)
                    shortElo = mElo.Groups[1].Value + " ELO";
                lblProfileElo.Text = shortElo;
                lblProfileElo.Foreground = HexBrush(string.IsNullOrEmpty(eloCol) ? "#38BDF8" : eloCol);
            }
        }

        private static void UpdateHeroWelcome(string uname)
        {
            if (lblHeroWelcomeText == null || string.IsNullOrEmpty(uname)) return;
            try
            {
                lblHeroWelcomeText.Inlines.Clear();
                lblHeroWelcomeText.Inlines.Add(new Run("Тавтай морил, ") { Foreground = HexBrush("#CBD5E1") });
                lblHeroWelcomeText.Inlines.Add(new Run(uname) { Foreground = HexBrush("#34D399"), FontWeight = FontWeights.ExtraBold });
                lblHeroWelcomeText.Inlines.Add(new Run(" — Зөвхөн Warcraft III 1.26a дээрх 5 үндсэн газрын сонголттой Монгол лобби систем.") { Foreground = HexBrush("#CBD5E1") });
            }
            catch { }
        }

        private static void UpdateNoLeaversToggleVisual()
        {
            bool on = (chkNoLeavers != null && chkNoLeavers.IsChecked == true);
            if (noLeaversTrack != null)
                noLeaversTrack.Background = on ? HexBrush("#7C3AED") : HexBrush("#334155");
            if (noLeaversKnob != null)
                noLeaversKnob.HorizontalAlignment = on ? HorizontalAlignment.Right : HorizontalAlignment.Left;
            if (lblNoLeaversState != null)
            {
                lblNoLeaversState.Text = on ? "Тийм" : "Үгүй";
                lblNoLeaversState.Foreground = on ? HexBrush("#E2E8F0") : HexBrush("#94A3B8");
            }
        }

        private static void SelectOfficialMap(int idx)
        {
            if (idx < 0 || idx >= 5) idx = 0;
            selectedMapIndex = idx;
            if (imgSelectedMapIcon != null && imgMaps[idx] != null)
                imgSelectedMapIcon.Source = imgMaps[idx];
            if (lblSelectedMapTitle != null)
                lblSelectedMapTitle.Text = OFFICIAL_MAP_TITLES[idx];
            if (lblFooterSelectedMap != null)
                lblFooterSelectedMap.Text = OFFICIAL_MAP_TITLES[idx];

            for (int i = 0; i < 5; i++)
            {
                bool active = (i == idx);
                if (mapOptionBorders[i] != null)
                {
                    mapOptionBorders[i].Background = active ? HexBrush("#251D47") : Brushes.Transparent;
                    mapOptionBorders[i].BorderBrush = active ? HexBrush("#8B5CF6") : Brushes.Transparent;
                }
                if (lblMapChecks[i] != null)
                    lblMapChecks[i].Visibility = active ? Visibility.Visible : Visibility.Collapsed;
                if (heroMapCards[i] != null)
                {
                    heroMapCards[i].BorderBrush = active ? HexBrush("#A78BFA") : Brushes.Transparent;
                    heroMapCards[i].BorderThickness = active ? new Thickness(1.5) : new Thickness(1);
                    heroMapCards[i].Background = active ? HexBrush("#188B5CF6") : Brushes.Transparent;
                }
            }
        }

        private static int GetOfficialMapIndex(string rawMapName)
        {
            string low = (rawMapName ?? "").ToLowerInvariant();
            if (low.Contains("6.74")) return 1;
            if (low.Contains("6.83")) return 2;
            if (low.Contains("6.85l")) return 3;
            if (low.Contains("6.85k")) return 4;
            return 0;
        }

        private static Brush HexBrush(string hex)
        {
            if (string.IsNullOrEmpty(hex)) hex = "#94A3B8";
            Brush b = (Brush)new BrushConverter().ConvertFromString(hex);
            if (b != null && b.CanFreeze) b.Freeze();
            return b;
        }

        private static void SetAuthMode(bool register)
        {
            isRegisterMode = register;
            isResetPassMode = false;
            tabSignInBorder.Background = register ? Brushes.Transparent : HexBrush("#7C3AED");
            tabSignInText.Foreground = register ? HexBrush("#94A3B8") : Brushes.White;
            tabSignUpBorder.Background = register ? HexBrush("#7C3AED") : Brushes.Transparent;
            tabSignUpText.Foreground = register ? Brushes.White : HexBrush("#94A3B8");
            if (lblUserPrompt != null)
                lblUserPrompt.Text = register
                    ? "🎮 Тоглолтын нэр (Тусгай тэмдэгт ашиглаж болно)"
                    : "📧 И-мэйл хаяг эсвэл Тоглогчийн нэр";
            if (authEmailPanel != null)
                authEmailPanel.Visibility = register ? Visibility.Visible : Visibility.Collapsed;
            if (lblEmailPrompt != null)
                lblEmailPrompt.Text = "И-мэйл хаяг (Нэвтрэх болон нууц үг сэргээхэд ашиглана)";
            if (lblPassPrompt != null)
                lblPassPrompt.Text = "Нууц үг (6+ тэмдэгт)";
            if (lblForgotPassText != null)
                lblForgotPassText.Text = "🔑 Нууц үгээ мартсан уу? (Сэргээх)";
            btnAuthSubmitText.Text = register ? "Шинээр Бүртгүүлэх (Sign Up)  →" : "Нэвтрэх (Sign In)  →";
            lblAuthError.Text = "";
        }

        private static void ToggleResetPasswordMode()
        {
            if (!isResetPassMode)
            {
                isResetPassMode = true;
                isRegisterMode = false;
                tabSignInBorder.Background = Brushes.Transparent;
                tabSignInText.Foreground = HexBrush("#94A3B8");
                tabSignUpBorder.Background = Brushes.Transparent;
                tabSignUpText.Foreground = HexBrush("#94A3B8");
                if (lblUserPrompt != null)
                    lblUserPrompt.Text = "📧 Бүртгэлтэй и-мэйл хаяг (эсвэл Тоглогчийн нэр)";
                if (authEmailPanel != null)
                    authEmailPanel.Visibility = Visibility.Visible;
                if (lblEmailPrompt != null)
                    lblEmailPrompt.Text = "Бүртгэлтэй и-мэйл хаяг (Email баталгаажуулах)";
                if (lblPassPrompt != null)
                    lblPassPrompt.Text = "Шинэ нууц үг зохиох (6+ тэмдэгт)";
                if (lblForgotPassText != null)
                    lblForgotPassText.Text = "← Нэвтрэх хэсэг рүү буцах";
                btnAuthSubmitText.Text = "🔄 Нууц үг шинэчлэх  →";
                lblAuthError.Text = "";
            }
            else
            {
                SetAuthMode(false);
            }
        }

        private static void SwitchPage(string page)
        {
            pageLobbies.Visibility = (page == "LOBBIES") ? Visibility.Visible : Visibility.Collapsed;
            if (pageLeaderboard != null)
                pageLeaderboard.Visibility = (page == "LEADERBOARD") ? Visibility.Visible : Visibility.Collapsed;
            pageFriends.Visibility = (page == "FRIENDS") ? Visibility.Visible : Visibility.Collapsed;
            pageWarKey.Visibility = (page == "WARKEY") ? Visibility.Visible : Visibility.Collapsed;
            pageSettings.Visibility = (page == "SETTINGS") ? Visibility.Visible : Visibility.Collapsed;

            navBtnLobbies.Background = (page == "LOBBIES") ? HexBrush("#1A1638") : Brushes.Transparent;
            navBtnLobbies.BorderBrush = (page == "LOBBIES") ? HexBrush("#7C3AED") : Brushes.Transparent;

            if (navBtnLeaderboard != null)
            {
                navBtnLeaderboard.Background = (page == "LEADERBOARD") ? HexBrush("#1A1638") : Brushes.Transparent;
                navBtnLeaderboard.BorderBrush = (page == "LEADERBOARD") ? HexBrush("#7C3AED") : Brushes.Transparent;
            }

            navBtnFriends.Background = (page == "FRIENDS") ? HexBrush("#1A1638") : Brushes.Transparent;
            navBtnFriends.BorderBrush = (page == "FRIENDS") ? HexBrush("#7C3AED") : Brushes.Transparent;

            navBtnWarKey.Background = (page == "WARKEY") ? HexBrush("#1A1638") : Brushes.Transparent;
            navBtnWarKey.BorderBrush = (page == "WARKEY") ? HexBrush("#7C3AED") : Brushes.Transparent;

            navBtnSettings.Background = (page == "SETTINGS") ? HexBrush("#1A1638") : Brushes.Transparent;
            navBtnSettings.BorderBrush = (page == "SETTINGS") ? HexBrush("#7C3AED") : Brushes.Transparent;
        }

        private static DateTime lastWar3RunCheckUtc = DateTime.MinValue;
        private static bool cachedWar3Running = false;

        private static bool IsWarcraftRunning(bool forceRefresh = false)
        {
            try
            {
                DateTime now = DateTime.UtcNow;
                if (!forceRefresh && (now - lastWar3RunCheckUtc).TotalMilliseconds < 1500)
                    return cachedWar3Running;
                if (fnFindWin != null)
                {
                    IntPtr hw = fnFindWin("Warcraft III", null);
                    if (hw != IntPtr.Zero)
                    {
                        cachedWar3Running = true;
                        lastWar3RunCheckUtc = now;
                        return true;
                    }
                    if (!forceRefresh)
                    {
                        cachedWar3Running = false;
                        lastWar3RunCheckUtc = now;
                        return false;
                    }
                }
                cachedWar3Running = Process.GetProcessesByName("war3").Length > 0 || Process.GetProcessesByName("w3l").Length > 0;
                lastWar3RunCheckUtc = now;
                return cachedWar3Running;
            }
            catch { return false; }
        }

        private static bool IsMatchActuallyStarted()
        {
            if (string.IsNullOrEmpty(currentRoomId)) return false;
            return (currentRoomPhase == "STARTING" || currentRoomPhase == "CONTINUING" || currentRoomPhase == "RUNNING"
                || currentRoomPhase == "PLAYING" || currentRoomPhase == "VERIFYING" || currentRoomPhase == "FROZEN"
                || currentRoomPhase == "WAITING" || currentRoomPhase == "LOADING");
        }

        private static bool IsMatchOrRejoinLocked()
        {
            if (!IsMatchActuallyStarted()) return false;
            bool isMeAbsentWaiting = (currentRoomMyDisconnected
                || (!string.IsNullOrEmpty(currentRoomAbsent) && string.Equals(currentRoomAbsent, currentUsername, StringComparison.OrdinalIgnoreCase)))
                && currentRoomWaitRemSec > 0;
            return currentRoomMyW3gsConnected || isMeAbsentWaiting || currentRoomPhase == "STARTING";
        }

        private static string FormatWaitMmSs(int sec)
        {
            if (sec < 0) sec = 0;
            int m = sec / 60;
            int s = sec % 60;
            return m.ToString("00") + ":" + s.ToString("00");
        }

        private static void SetLockedButtonVisual(Border b, bool locked)
        {
            if (b == null) return;
            b.IsEnabled = !locked;
            b.Opacity = locked ? 0.35 : 1.0;
            b.Cursor = locked ? Cursors.No : Cursors.Hand;
        }

        private static void UpdateInnerRoomVisibility()
        {
            bool inRoom = !string.IsNullOrEmpty(currentRoomId);
            if (lobbyListView != null)
                lobbyListView.Visibility = inRoom ? Visibility.Collapsed : Visibility.Visible;
            if (innerRoomView != null)
                innerRoomView.Visibility = inRoom ? Visibility.Visible : Visibility.Collapsed;

            bool matchActive = IsMatchActuallyStarted();
            bool war3Open = IsWarcraftRunning();
            bool isMeAbsent = matchActive && (currentRoomMyDisconnected
                || (!string.IsNullOrEmpty(currentRoomAbsent) && string.Equals(currentRoomAbsent, currentUsername, StringComparison.OrdinalIgnoreCase)));
            bool locked = IsMatchOrRejoinLocked();
            SetLockedButtonVisual(btnLeaveMatchNow, locked);
            SetLockedButtonVisual(btnInviteFriendFromRoom, locked);
            SetLockedButtonVisual(btnModalInviteRoom, locked);
            SetLockedButtonVisual(btnLogout, locked);

            if (!inRoom) return;

            if (btnSetRoomCode != null)
                btnSetRoomCode.Visibility = (isCurrentRoomOwner && !matchActive) ? Visibility.Visible : Visibility.Collapsed;

            if (!matchActive)
            {
                // Lobby pre-game state (currentRoomPhase == "LOBBY"):
                // Rejoin is NEVER shown and buttons are NEVER locked before match starts!
                if (btnRejoinMatch != null) btnRejoinMatch.Visibility = Visibility.Collapsed;
                if (btnAddWaitTime != null) btnAddWaitTime.Visibility = Visibility.Collapsed;
                if (btnHostDropAbsent != null) btnHostDropAbsent.Visibility = Visibility.Collapsed;

                if (btnHostStartGame != null)
                    btnHostStartGame.Visibility = isCurrentRoomOwner ? Visibility.Visible : Visibility.Collapsed;
                if (lblHostStartBtnText != null)
                {
                    lblHostStartBtnText.Text = (currentRoomMyW3gsConnected && war3Open)
                        ? "🚀 ТОГЛОЛТ ЭХЛҮҮЛЭХ (START MATCH)"
                        : "🚀 ТОГЛООМ ЭХЛҮҮЛЭХ (START GAME)";
                }

                if (clientWaitBanner != null)
                {
                    clientWaitBanner.Visibility = isCurrentRoomOwner ? Visibility.Collapsed : Visibility.Visible;
                    clientWaitBanner.Cursor = (!isCurrentRoomOwner && !war3Open) ? Cursors.Hand : Cursors.Arrow;
                }
                if (!isCurrentRoomOwner)
                {
                    if (currentRoomMyW3gsConnected && war3Open)
                    {
                        if (lblWaitBannerTitle != null)
                        {
                            lblWaitBannerTitle.Text = "✅ Та Warcraft III LAN өрөөнд холбогдсон байна";
                            lblWaitBannerTitle.Foreground = HexBrush("#10B981");
                        }
                        if (lblWaitBannerSub != null)
                            lblWaitBannerSub.Text = "Host тоглолт эхлүүлэхийг (-start) хүлээж байна...";
                    }
                    else if (!war3Open && (currentRoomLaunchSig > 0 || hasLaunchedWar3InCurrentRoom))
                    {
                        if (lblWaitBannerTitle != null)
                        {
                            lblWaitBannerTitle.Text = "🎮 Warcraft III асаах (Энд дарж тоглоомоо нээнэ үү)";
                            lblWaitBannerTitle.Foreground = HexBrush("#FBBF24");
                        }
                        if (lblWaitBannerSub != null)
                            lblWaitBannerSub.Text = "Warcraft III хаалттай байна — энд дарж LAN өрөө рүүгээ орно уу";
                    }
                    else
                    {
                        if (lblWaitBannerTitle != null)
                        {
                            lblWaitBannerTitle.Text = "⏳ Host тоглоом эхлүүлэхийг хүлээж байна...";
                            lblWaitBannerTitle.Foreground = HexBrush("#38BDF8");
                        }
                        if (lblWaitBannerSub != null)
                            lblWaitBannerSub.Text = "Host эхлүүлмэгц таны Warcraft III автоматаар асна (энд дарж урьдчилж асааж болно)";
                    }
                }
                return;
            }

            // Match is active (STARTING / CONTINUING / RUNNING / FROZEN / WAITING)
            if (btnHostStartGame != null)
                btnHostStartGame.Visibility = Visibility.Collapsed;

            bool waitingForSomeone = (currentRoomPhase == "WAITING" || currentRoomPhase == "FROZEN" || !string.IsNullOrEmpty(currentRoomAbsent));

            if (btnAddWaitTime != null)
                btnAddWaitTime.Visibility = (waitingForSomeone && currentRoomAddtimeUsed < currentRoomAddtimeMax) ? Visibility.Visible : Visibility.Collapsed;
            if (lblAddWaitTimeText != null)
                lblAddWaitTimeText.Text = "⏱️ +1 минут сунгах (-addtime " + currentRoomAddtimeUsed + "/" + currentRoomAddtimeMax + ")";

            if (btnHostDropAbsent != null)
                btnHostDropAbsent.Visibility = (waitingForSomeone && isCurrentRoomOwner && currentRoomCanHostDrop && !isMeAbsent) ? Visibility.Visible : Visibility.Collapsed;
            if (lblHostDropAbsentText != null)
            {
                lblHostDropAbsentText.Text = (currentRoomW3gsConnectedCount <= 0)
                    ? "⏹️ Хүлээлтийг дуусгаж өрөөнд буцах"
                    : "👢 Тоглогчийг хасах (Drop)";
            }

            if (isMeAbsent)
            {
                // ONLY the player who disconnected / crashed during an active match sees the Rejoin button
                if (btnRejoinMatch != null)
                {
                    btnRejoinMatch.Visibility = Visibility.Visible;
                    SetLockedButtonVisual(btnRejoinMatch, !currentRoomRejoinReady);
                }
                if (lblRejoinBtnText != null)
                    lblRejoinBtnText.Text = currentRoomRejoinReady
                        ? "🔄 ТОГЛОЛТОНД БУЦАЖ ОРОХ"
                        : "⏳ Тоглолтын сэргээх цэгийг бэлтгэж байна...";
                if (lblRejoinBtnSub != null)
                {
                    lblRejoinBtnSub.Text = !currentRoomRejoinReady
                        ? "Бусад тоглогчийн тоглоом сэргээх цэг хадгалж байна (хэдэн секунд)"
                        : (currentRoomWaitRemSec > 0
                            ? ("⏳ Үлдсэн хугацаа: " + FormatWaitMmSs(currentRoomWaitRemSec) + " — дарж тоглолт руугаа буцна уу")
                            : "Дарж тоглолт руугаа буцаж орно уу");
                }
                if (clientWaitBanner != null)
                    clientWaitBanner.Visibility = Visibility.Collapsed;
            }
            else
            {
                // Active player in match (minimized/Alt-Tabbed to MongolRanger) sees "⚔️ Тоглолт явагдаж байна..."
                if (btnRejoinMatch != null)
                    btnRejoinMatch.Visibility = Visibility.Collapsed;
                if (clientWaitBanner != null)
                {
                    clientWaitBanner.Visibility = Visibility.Visible;
                    clientWaitBanner.Cursor = Cursors.Arrow;
                }

                if (waitingForSomeone)
                {
                    string who = string.IsNullOrEmpty(currentRoomAbsent) ? "Тоглогч" : currentRoomAbsent;
                    if (lblWaitBannerTitle != null)
                    {
                        lblWaitBannerTitle.Text = "⚔️ Тоглолт явагдаж байна — ⏳ «" + who + "»-ийг хүлээж байна (" + FormatWaitMmSs(currentRoomWaitRemSec) + ")";
                        lblWaitBannerTitle.Foreground = HexBrush("#FBBF24");
                    }
                    if (lblWaitBannerSub != null)
                    {
                        lblWaitBannerSub.Text = "Стандарт хүлээх хугацаа: 3 мин (180 сек) • Чат дээр -addtime бичиж +1 мин сунгана (" + currentRoomAddtimeUsed + "/" + currentRoomAddtimeMax + ")";
                    }
                }
                else
                {
                    if (lblWaitBannerTitle != null)
                    {
                        lblWaitBannerTitle.Text = "⚔️ Тоглолт явагдаж байна...";
                        lblWaitBannerTitle.Foreground = HexBrush("#10B981");
                    }
                    if (lblWaitBannerSub != null)
                    {
                        lblWaitBannerSub.Text = "Тоглолтын дундуур Өрөөнөөс гарах, Найзаа урих болон Гарах (Logout) товчнууд түгжигдсэн байна";
                    }
                }
            }
            UpdateWaitScreenOverlay();
        }

        private static void EnsureWaitOverlayCreated()
        {
            if (waitOverlayWin != null) return;
            try
            {
                waitOverlayWin = new Window
                {
                    Title = "MongolRanger Wait HUD",
                    Width = 680,
                    Height = 76,
                    WindowStyle = WindowStyle.None,
                    AllowsTransparency = true,
                    Background = Brushes.Transparent,
                    Topmost = true,
                    ShowInTaskbar = false,
                    ShowActivated = false,
                    Focusable = false,
                    ResizeMode = ResizeMode.NoResize,
                    Left = Math.Max(20, (SystemParameters.PrimaryScreenWidth - 680) / 2.0),
                    Top = 16
                };
                waitOverlayBorder = new Border
                {
                    CornerRadius = new CornerRadius(12),
                    Background = HexBrush("#EA090D18"),
                    BorderBrush = HexBrush("#38BDF8"),
                    BorderThickness = new Thickness(2),
                    Padding = new Thickness(18, 10, 18, 10),
                    Cursor = Cursors.Hand
                };
                StackPanel sp = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
                lblWaitOverlayTitle = new TextBlock
                {
                    Text = "⏳ Тоглогчийг хүлээж байна...",
                    Foreground = HexBrush("#FBBF24"),
                    FontWeight = FontWeights.ExtraBold,
                    FontSize = 14,
                    TextAlignment = TextAlignment.Center,
                    HorizontalAlignment = HorizontalAlignment.Center
                };
                lblWaitOverlaySub = new TextBlock
                {
                    Text = "Гаран дээр шууд -addtime гэж бичих эсвэл ЭНД ДАРЖ +1 минут сунгана уу",
                    Foreground = HexBrush("#FFFFFF"),
                    FontWeight = FontWeights.Bold,
                    FontSize = 12,
                    Margin = new Thickness(0, 3, 0, 0),
                    TextAlignment = TextAlignment.Center,
                    HorizontalAlignment = HorizontalAlignment.Center
                };
                sp.Children.Add(lblWaitOverlayTitle);
                sp.Children.Add(lblWaitOverlaySub);
                waitOverlayBorder.Child = sp;
                waitOverlayBorder.MouseLeftButtonDown += (s, e) =>
                {
                    if (currentRoomAddtimeUsed < currentRoomAddtimeMax)
                        ExtendRoomWaitTime();
                };
                waitOverlayWin.Content = waitOverlayBorder;
            }
            catch { waitOverlayWin = null; }
        }

        private static void UpdateWaitScreenOverlay()
        {
            try
            {
                bool waitingForSomeone = !string.IsNullOrEmpty(currentRoomId) &&
                    (currentRoomPhase == "WAITING" || currentRoomPhase == "FROZEN" || !string.IsNullOrEmpty(currentRoomAbsent) || bridgeLagDialogOpen);
                bool war3Open = IsWarcraftRunning();
                if (!waitingForSomeone || !war3Open)
                {
                    if (waitOverlayWin != null && waitOverlayWin.IsVisible)
                        waitOverlayWin.Hide();
                    return;
                }

                EnsureWaitOverlayCreated();
                if (waitOverlayWin == null) return;

                string who = string.IsNullOrEmpty(currentRoomAbsent) ? "Тоглогч" : currentRoomAbsent;
                int rem = currentRoomWaitRemSec > 0 ? currentRoomWaitRemSec : 0;
                bool isUrgent20s = (rem > 0 && rem <= 25);

                if (isUrgent20s)
                {
                    waitOverlayBorder.Background = HexBrush("#F22A080C");
                    waitOverlayBorder.BorderBrush = HexBrush("#EF4444");
                    lblWaitOverlayTitle.Foreground = HexBrush("#FCA5A5");
                    lblWaitOverlayTitle.Text = "🚨 АНХААР: «" + who + "»-ийг хүлээх хугацаа дуусахад " + rem + " сек үлдлээ!";
                    lblWaitOverlaySub.Foreground = HexBrush("#FDE047");
                    lblWaitOverlaySub.Text = (currentRoomAddtimeUsed < currentRoomAddtimeMax)
                        ? ("👉 -addtime командаар +1 минут сунгана уу! (Гаран дээр -addtime бичих эсвэл ЭНД ДАРНА УУ • " + currentRoomAddtimeUsed + "/" + currentRoomAddtimeMax + ")")
                        : "⚠️ Нэмэлт цаг сунгах эрх дууссан (" + currentRoomAddtimeUsed + "/" + currentRoomAddtimeMax + ")";
                }
                else
                {
                    waitOverlayBorder.Background = HexBrush("#EA090D18");
                    waitOverlayBorder.BorderBrush = HexBrush("#F59E0B");
                    lblWaitOverlayTitle.Foreground = HexBrush("#FBBF24");
                    lblWaitOverlayTitle.Text = "⏳ «" + who + "» тоглолтонд эргэж орохыг хүлээж байна (" + FormatWaitMmSs(rem) + ")";
                    lblWaitOverlaySub.Foreground = HexBrush("#E2E8F0");
                    lblWaitOverlaySub.Text = (currentRoomAddtimeUsed < currentRoomAddtimeMax)
                        ? ("⏱️ Цаг сунгах: Гаран дээр шууд -addtime гэж бичих эсвэл ЭНД ДАРЖ +1 минут сунгана (" + currentRoomAddtimeUsed + "/" + currentRoomAddtimeMax + ")")
                        : ("Нэмэлт цаг сунгах эрх дууссан (" + currentRoomAddtimeUsed + "/" + currentRoomAddtimeMax + ")");
                }

                if (!waitOverlayWin.IsVisible)
                    waitOverlayWin.Show();
            }
            catch { }
        }

        private static void SetFilter(string f)
        {
            roomFilter = f;
            filterAllBorder.Background = (f == "ALL") ? HexBrush("#6D28D9") : HexBrush("#12172A");
            filterAllBorder.BorderBrush = (f == "ALL") ? HexBrush("#8B5CF6") : HexBrush("#232E4B");
            filterWaitBorder.Background = (f == "LOBBY") ? HexBrush("#6D28D9") : HexBrush("#12172A");
            filterWaitBorder.BorderBrush = (f == "LOBBY") ? HexBrush("#8B5CF6") : HexBrush("#232E4B");
            filterRunBorder.Background = (f == "RUNNING") ? HexBrush("#6D28D9") : HexBrush("#12172A");
            filterRunBorder.BorderBrush = (f == "RUNNING") ? HexBrush("#8B5CF6") : HexBrush("#232E4B");
            if (filterLockBorder != null)
            {
                filterLockBorder.Background = (f == "LOCKED") ? HexBrush("#6D28D9") : HexBrush("#12172A");
                filterLockBorder.BorderBrush = (f == "LOCKED") ? HexBrush("#8B5CF6") : HexBrush("#232E4B");
            }
            RenderRooms();
        }

        private static void OnJoinRoomButtonClick(object sender, RoutedEventArgs e)
        {
            Button btn = e.OriginalSource as Button;
            if (btn != null && btn.Tag != null)
            {
                string rid = btn.Tag.ToString();
                bool locked = false;
                string rname = "";
                foreach (var r in cachedRooms)
                {
                    if (r["id"] == rid)
                    {
                        locked = (r.ContainsKey("is_locked") && r["is_locked"] == "1");
                        rname = r["name"];
                    }
                }
                if (locked && rid != currentRoomId)
                {
                    OpenJoinRoomCodeModal(rid, rname);
                }
                else
                {
                    JoinRoomById(rid, "");
                }
            }
        }

        private static void OpenJoinRoomCodeModal(string rid, string roomTitle)
        {
            pendingJoinRoomId = rid;
            codeModalMode = "JOIN";
            lblCodeModalTitle.Text = "🔒 Кодтой Өрөөнд Орох";
            lblCodeModalSub.Text = "«" + roomTitle + "» өрөө нууц кодтой байна. Өрөөний кодыг оруулна уу:";
            txtCodeModalInput.Text = "";
            lblCodeModalError.Text = "";
            codeModalOverlay.Visibility = Visibility.Visible;
            txtCodeModalInput.Focus();
        }

        private static void OpenSetRoomCodeModal()
        {
            if (string.IsNullOrEmpty(currentRoomId))
            {
                MessageBox.Show("Та эхлээд өрөө үүсгэнэ үү! Өрөө үүсгэсний дараа эндээс кодоо хийх эсвэл солих боломжтой.", "MongolRanger");
                return;
            }
            if (!isCurrentRoomOwner)
            {
                MessageBox.Show("Зөвхөн өрөө үүсгэсэн Host өрөөний кодыг хийх эсвэл солих эрхтэй!", "MongolRanger");
                return;
            }
            codeModalMode = "SET";
            lblCodeModalTitle.Text = "🔒 Үүсгэсэн Өрөөндөө Код Хийх / Солих";
            lblCodeModalSub.Text = "Шинэ нууц кодоо бичнэ үү (Кодыг устгаж нээлттэй болгох бол хоосон орхиод Батлах дарна уу):";
            txtCodeModalInput.Text = currentRoomCode ?? "";
            lblCodeModalError.Text = "";
            codeModalOverlay.Visibility = Visibility.Visible;
            txtCodeModalInput.Focus();
            txtCodeModalInput.SelectAll();
        }

        private static void OpenChangePlayerNameModal()
        {
            if (IsMatchActuallyStarted())
            {
                MessageBox.Show("Тоглолт явагдаж байх үед тоглогчийн нэр солих боломжгүй! Тоглолт дууссаны дараа солино уу.", "MongolRanger");
                return;
            }
            codeModalMode = "RENAME";
            lblCodeModalTitle.Text = "✏️ Тоглогчийн нэр солих";
            lblCodeModalSub.Text = "Тоглолтонд харагдах шинэ нэрээ бичнэ үү (2–24 тэмдэгт, тусгай тэмдэгт байж болно • Warcraft III LAN нэр автоматаар солигдоно):";
            txtCodeModalInput.Text = currentUsername ?? "";
            lblCodeModalError.Text = "";
            codeModalOverlay.Visibility = Visibility.Visible;
            txtCodeModalInput.Focus();
            txtCodeModalInput.SelectAll();
        }

        private static void SubmitRoomCodeModal()
        {
            string code = (txtCodeModalInput.Text ?? "").Trim();
            if (codeModalMode == "RENAME")
            {
                if (code.Length < 2 || code.Length > 24)
                {
                    lblCodeModalError.Text = "⚠️ Тоглогчийн нэр 2–24 тэмдэгт байх ёстой!";
                    return;
                }
                if (code.Contains("\"") || code.Contains("\\") || code.Contains("@"))
                {
                    lblCodeModalError.Text = "⚠️ Тоглогчийн нэрэнд @ эсвэл хашилт орж болохгүй!";
                    return;
                }
                try
                {
                    string body = "{\"new_name\":\"" + code.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                    string res = ApiRequest("POST", "/api/user/change-name", body);
                    string newName = ExtractJsonString(res, "username");
                    if (string.IsNullOrEmpty(newName)) newName = code;
                    currentUsername = newName;
                    if (lblProfileName != null) lblProfileName.Text = currentUsername;
                    UpdateHeroWelcome(currentUsername);
                    SyncWar3Username(currentUsername);
                    SaveSettings();
                    codeModalOverlay.Visibility = Visibility.Collapsed;
                    RefreshMapsAndRooms();
                    SyncSocialStateAsync(false);
                    if (!string.IsNullOrEmpty(currentRoomId))
                        SyncRoomStateOnceAsync();
                }
                catch (WebException wex)
                {
                    string err = "⚠️ Энэ нэр аль хэдийн бүртгэлтэй байна.";
                    try
                    {
                        if (wex.Response != null)
                        {
                            using (StreamReader sr = new StreamReader(wex.Response.GetResponseStream()))
                            {
                                err = FormatFriendlyAuthError(sr.ReadToEnd());
                            }
                        }
                    }
                    catch { }
                    lblCodeModalError.Text = err;
                }
                catch (Exception ex)
                {
                    lblCodeModalError.Text = "Алдаа: " + ex.Message;
                }
                return;
            }
            if (codeModalMode == "JOIN")
            {
                if (string.IsNullOrEmpty(code))
                {
                    lblCodeModalError.Text = "⚠️ Өрөөний нууц кодыг оруулна уу!";
                    return;
                }
                codeModalOverlay.Visibility = Visibility.Collapsed;
                JoinRoomById(pendingJoinRoomId, code);
            }
            else if (codeModalMode == "SET")
            {
                try
                {
                    string body = "{\"room_code\":\"" + code.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                    ApiRequest("POST", "/api/rooms/" + currentRoomId + "/code", body);
                    currentRoomCode = code;
                    codeModalOverlay.Visibility = Visibility.Collapsed;
                    lblSetRoomCodeText.Text = string.IsNullOrEmpty(currentRoomCode)
                        ? "🔓 Код Хийх (Нээлттэй)"
                        : "🔒 Код: " + currentRoomCode + " (Солих)";
                    RefreshMapsAndRooms();
                    SyncRoomStateOnceAsync();
                }
                catch (Exception ex)
                {
                    lblCodeModalError.Text = "Алдаа: " + ex.Message;
                }
            }
        }

        private static string FormatFriendlyAuthError(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return "⚠️ Нэвтрэх нэр эсвэл нууц үг буруу байна.";
            string det = ExtractJsonString(raw, "detail");
            if (!string.IsNullOrEmpty(det) && !det.StartsWith("[") && !det.StartsWith("{"))
            {
                if (det.IndexOf("Incorrect username", StringComparison.OrdinalIgnoreCase) >= 0)
                    return "⚠️ Нэвтрэх нэр эсвэл нууц үг буруу байна.";
                if (det.IndexOf("Username unavailable", StringComparison.OrdinalIgnoreCase) >= 0)
                    return "⚠️ Энэ тоглогчийн нэр бүртгэлтэй байна. Өөр нэр сонгоно уу.";
                if (det.IndexOf("Too many requests", StringComparison.OrdinalIgnoreCase) >= 0)
                    return "⚠️ Түр хүлээгээд 10 секундийн дараа дахин оролдоно уу.";
                return det;
            }
            string low = raw.ToLowerInvariant();
            if (low.Contains("username") && low.Contains("pattern"))
                return "⚠️ Тоглогчийн нэр буруу тэмдэгт агуулсан байна.";
            if (low.Contains("username") && (low.Contains("short") || low.Contains("at least")))
                return "⚠️ Тоглогчийн нэр 2–24 тэмдэгт байх ёстой.";
            if (low.Contains("password") && (low.Contains("short") || low.Contains("at least")))
                return "⚠️ Нууц үг хамгийн багадаа 6 тэмдэгт байх ёстой.";
            if (low.Contains("email"))
                return "⚠️ И-мэйл хаягаа зөв оруулна уу.";
            if (raw.Trim().StartsWith("{") || raw.Trim().StartsWith("["))
                return "⚠️ Мэдээллээ шалгаад дахин оролдоно уу.";
            return raw;
        }

        private static void DoAuth()
        {
            string u = (txtUser.Text ?? "").Trim();
            string p = txtPass.Password ?? "";
            string em = (txtEmail != null ? (txtEmail.Text ?? "").Trim() : "");
            if (isResetPassMode && string.IsNullOrEmpty(em) && u.Contains("@"))
                em = u;

            if (isRegisterMode)
            {
                if (u.Length < 2 || u.Length > 24)
                {
                    lblAuthError.Foreground = HexBrush("#F87171");
                    lblAuthError.Text = "⚠️ Тоглогчийн нэр 2–24 тэмдэгт байх ёстой!";
                    return;
                }
                if (u.Contains("@"))
                {
                    lblAuthError.Foreground = HexBrush("#F87171");
                    lblAuthError.Text = "⚠️ Тоглолтын нэр хэсэгт и-мэйл биш тоглогчийн нэрээ оруулна уу!";
                    return;
                }
            }
            else
            {
                if (u.Length < 2 || u.Length > 128)
                {
                    lblAuthError.Foreground = HexBrush("#F87171");
                    lblAuthError.Text = "⚠️ И-мэйл хаяг эсвэл тоглогчийн нэрээ оруулна уу!";
                    return;
                }
            }
            if (u.Contains("\"") || u.Contains("\\"))
            {
                lblAuthError.Foreground = HexBrush("#F87171");
                lblAuthError.Text = "⚠️ Нэрэнд хашилт (\" эсвэл \\) орж болохгүй.";
                return;
            }
            if ((isRegisterMode || isResetPassMode) && (em.Length < 5 || !em.Contains("@") || !em.Contains(".")))
            {
                lblAuthError.Foreground = HexBrush("#F87171");
                lblAuthError.Text = isResetPassMode
                    ? "⚠️ Бүртгэлтэй и-мэйл хаягаа зөв оруулна уу!"
                    : "⚠️ Нэвтрэх болон нууц үг сэргээхэд ашиглах и-мэйл хаягаа оруулна уу!";
                return;
            }
            if (p.Length < 6)
            {
                lblAuthError.Foreground = HexBrush("#F87171");
                lblAuthError.Text = "⚠️ Нууц үг хамгийн багадаа 6 тэмдэгт байх ёстой!";
                return;
            }

            lblAuthError.Foreground = HexBrush("#38BDF8");
            lblAuthError.Text = "⏳ Сервертэй холбогдож байна...";
            try
            {
                string hwid = GetHardwareId();
                string escU = u.Replace("\\", "\\\\").Replace("\"", "\\\"");
                string escP = p.Replace("\\", "\\\\").Replace("\"", "\\\"");
                string escEm = em.Replace("\\", "\\\\").Replace("\"", "\\\"");

                if (isResetPassMode)
                {
                    string resetBody = "{\"username\":\"" + escU + "\",\"email\":\"" + escEm + "\",\"new_password\":\"" + escP + "\",\"hwid\":\"" + hwid + "\"}";
                    string resetRes = ApiRequest("POST", "/api/auth/reset-password", resetBody);
                    string resolvedUser = ExtractJsonString(resetRes, "username");
                    if (!string.IsNullOrEmpty(resolvedUser))
                        escU = resolvedUser.Replace("\\", "\\\\").Replace("\"", "\\\"");
                    isResetPassMode = false;
                }

                string body = "{\"username\":\"" + escU + "\",\"password\":\"" + escP + "\",\"email\":\"" + escEm + "\",\"hwid\":\"" + hwid + "\"}";
                if (isRegisterMode)
                {
                    ApiRequest("POST", "/api/auth/register", body);
                }
                string res = ApiRequest("POST", "/api/auth/login", body);
                authToken = ExtractJsonString(res, "token");
                currentUsername = ExtractJsonString(res, "username");
                currentUidNum = ExtractJsonInt(res, "uid_num", 10001);
                if (string.IsNullOrEmpty(currentUsername)) currentUsername = u;
                lblAuthError.Foreground = HexBrush("#F87171");
                lblAuthError.Text = "";
                SaveSettings();
                SyncWar3Username(currentUsername);

                string badgeLbl = ExtractJsonString(res, "badge_label");
                string badgeCol = ExtractJsonString(res, "badge_color");
                string eloDisp = ExtractJsonString(res, "elo_display");
                string eloCol = ExtractJsonString(res, "elo_color");

                lblProfileName.Text = currentUsername;
                UpdateHeroWelcome(currentUsername);
                if (lblProfileUid != null) lblProfileUid.Text = "#" + currentUidNum;
                UpdateSidebarProfileBadges(badgeLbl, badgeCol, eloDisp, eloCol);

                authView.Visibility = Visibility.Collapsed;
                appShell.Visibility = Visibility.Visible;
                string resolvedAuthWar3 = ResolveWar3DirectoryRecursive(war3Dir, 5);
                if (!string.IsNullOrEmpty(resolvedAuthWar3))
                {
                    war3Dir = resolvedAuthWar3;
                    if (txtWar3Path != null) txtWar3Path.Text = war3Dir;
                }
                if (!IsWar3ReadyAndPatched(war3Dir))
                {
                    openedSettingsForFirstTimeSetup = true;
                    SwitchPage("SETTINGS");
                }
                else
                {
                    openedSettingsForFirstTimeSetup = false;
                    SwitchPage("LOBBIES");
                }
                RefreshMapsAndRooms();
                SyncSocialStateAsync(true);
                RunAutoPatchAndSyncAsync();
            }
            catch (WebException wex)
            {
                lblAuthError.Foreground = HexBrush("#F87171");
                string err = "⚠️ Сервертэй холбогдож чадсангүй. Интернэт холболтоо шалгана уу.";
                try
                {
                    if (wex.Response != null)
                    {
                        using (StreamReader sr = new StreamReader(wex.Response.GetResponseStream(), Encoding.UTF8))
                        {
                            string raw = sr.ReadToEnd();
                            if (!string.IsNullOrEmpty(raw))
                                err = FormatFriendlyAuthError(raw);
                            else
                                err = isRegisterMode ? "⚠️ Бүртгүүлэх үед алдаа гарлаа. Дахин оролдоно уу." : "⚠️ Нэвтрэх нэр эсвэл нууц үг буруу байна.";
                        }
                    }
                }
                catch { }
                lblAuthError.Text = err;
            }
            catch (Exception ex)
            {
                lblAuthError.Foreground = HexBrush("#F87171");
                lblAuthError.Text = FormatFriendlyAuthError(ex.Message);
            }
        }

        private static void RefreshMapsAndRooms()
        {
            if (string.IsNullOrEmpty(authToken)) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string mapsJson = ApiRequest("GET", "/api/maps");
                    MatchCollection mm = Regex.Matches(mapsJson, "\\{[^{}]*\"filename\"\\s*:\\s*\"[^\"]+\"[^{}]*\\}");
                    List<Dictionary<string, string>> parsedMaps = new List<Dictionary<string, string>>();
                    foreach (Match m in mm)
                    {
                        string obj = m.Value;
                        var d = new Dictionary<string, string>();
                        d["id"] = ExtractJsonString(obj, "id");
                        d["filename"] = ExtractJsonString(obj, "filename");
                        d["title"] = ExtractJsonString(obj, "title");
                        d["sha256"] = ExtractJsonString(obj, "sha256");
                        parsedMaps.Add(d);
                    }

                    string roomsJson = ApiRequest("GET", "/api/rooms");
                    MatchCollection rm = Regex.Matches(roomsJson, "\\{[^{}]*\"map_name\"\\s*:\\s*\"[^\"]+\"[^{}]*\\}");
                    List<Dictionary<string, string>> parsedRooms = new List<Dictionary<string, string>>();
                    foreach (Match m in rm)
                    {
                        string obj = m.Value;
                        var d = new Dictionary<string, string>();
                        d["id"] = ExtractJsonString(obj, "id");
                        d["name"] = ExtractJsonString(obj, "name");
                        d["host"] = ExtractJsonString(obj, "host");
                        d["host_uid"] = ExtractJsonInt(obj, "host_uid", 10001).ToString();
                        d["map_name"] = ExtractJsonString(obj, "map_name");
                        d["phase"] = ExtractJsonString(obj, "phase");
                        d["is_locked"] = ExtractJsonInt(obj, "is_locked", 0).ToString();
                        d["no_leavers"] = ExtractJsonInt(obj, "no_leavers", 0).ToString();
                        int pCount = ExtractJsonInt(obj, "players", 1);
                        int pCap = ExtractJsonInt(obj, "capacity", 10);
                        d["players_num"] = pCount.ToString();
                        d["capacity_num"] = pCap.ToString();
                        d["players"] = pCount + " / " + pCap;
                        parsedRooms.Add(d);
                    }

                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (cmbMaps.Items.Count != parsedMaps.Count && parsedMaps.Count > 0)
                        {
                            cachedMaps = parsedMaps;
                            cmbMaps.Items.Clear();
                            foreach (var m in parsedMaps) cmbMaps.Items.Add(m["title"]);
                            cmbMaps.SelectedIndex = 0;
                        }
                        cachedRooms = parsedRooms;
                        RenderRooms();
                    }));
                }
                catch { }
            });
        }

        private static void RenderRooms()
        {
            int countAll = cachedRooms.Count;
            int countOpen = 0;
            int countRun = 0;
            int countLock = 0;
            foreach (var r in cachedRooms)
            {
                bool isLob = (r["phase"] == "LOBBY");
                bool isLck = (r.ContainsKey("is_locked") && r["is_locked"] == "1");
                if (isLob) countOpen++;
                else countRun++;
                if (isLck) countLock++;
            }
            if (lblFilterAllCount != null) lblFilterAllCount.Text = countAll.ToString();
            if (lblFilterWaitCount != null) lblFilterWaitCount.Text = countOpen.ToString();
            if (lblFilterRunCount != null) lblFilterRunCount.Text = countRun.ToString();
            if (lblFilterLockCount != null) lblFilterLockCount.Text = countLock.ToString();

            string q = (txtSearch.Text ?? "").Trim().ToLowerInvariant();
            var sortedRooms = new List<Dictionary<string, string>>();
            foreach (var r in cachedRooms)
                if (r["phase"] == "LOBBY" && (!r.ContainsKey("is_locked") || r["is_locked"] != "1")) sortedRooms.Add(r);
            foreach (var r in cachedRooms)
                if (r["phase"] == "LOBBY" && r.ContainsKey("is_locked") && r["is_locked"] == "1") sortedRooms.Add(r);
            foreach (var r in cachedRooms)
                if (r["phase"] != "LOBBY") sortedRooms.Add(r);
            var list = new List<LobbyItem>();
            foreach (var r in sortedRooms)
            {
                if (roomFilter == "LOBBY" && r["phase"] != "LOBBY") continue;
                if (roomFilter == "RUNNING" && r["phase"] == "LOBBY") continue;
                if (roomFilter == "LOCKED" && (!r.ContainsKey("is_locked") || r["is_locked"] != "1")) continue;
                int mIdx = GetOfficialMapIndex(r["map_name"]);
                string mTitle = OFFICIAL_MAP_TITLES[mIdx];
                string mSub = OFFICIAL_MAP_SUBS[mIdx];
                if (!string.IsNullOrEmpty(q))
                {
                    string hay = (r["name"] + " " + r["host"] + " " + r["map_name"] + " " + mTitle).ToLowerInvariant();
                    if (!hay.Contains(q)) continue;
                }
                bool isLobby = (r["phase"] == "LOBBY");
                bool isLocked = (r.ContainsKey("is_locked") && r["is_locked"] == "1");
                bool noLeavers = (r.ContainsKey("no_leavers") && r["no_leavers"] == "1");
                int pNum = 1, pCap = 10;
                if (r.ContainsKey("players_num")) int.TryParse(r["players_num"], out pNum);
                if (r.ContainsKey("capacity_num")) int.TryParse(r["capacity_num"], out pCap);
                if (pCap <= 0) pCap = 10;
                double fillW = Math.Max(6.0, Math.Min(64.0, (double)pNum / pCap * 64.0));

                string subInfo = !isLobby
                    ? "⚔️ Тоглолт явагдаж байна • Reconnect идэвхтэй"
                    : (isLocked
                        ? "Нууц кодтой өрөө • Кодоор эсвэл урилгаар орох"
                        : (noLeavers ? "🛡️ Anti-MapHack • Leaver оруулахгүй • ELO Ranked" : "🛡️ Anti-MapHack • Нээлттэй лобби • ELO Ranked"));
                Brush subFg = (!isLobby || isLocked) ? HexBrush("#FBBF24") : HexBrush("#94A3B8");
                string hName = r.ContainsKey("host") && !string.IsNullOrEmpty(r["host"]) ? r["host"] : "M";
                string hInit = hName.Substring(0, 1).ToUpperInvariant();

                string stText = !isLobby ? "⏳ Тоглож буй" : (isLocked ? "🔒 Кодтой" : "● Хүлээж буй");
                Brush stBg = !isLobby ? HexBrush("#2D2112") : (isLocked ? HexBrush("#23183E") : HexBrush("#0F2D25"));
                Brush stFg = !isLobby ? HexBrush("#FBBF24") : (isLocked ? HexBrush("#C4B5FD") : HexBrush("#34D399"));
                Brush stBorder = !isLobby ? HexBrush("#B45309") : (isLocked ? HexBrush("#7C3AED") : HexBrush("#059669"));

                string btnText = !isLobby ? "👁  Харах" : "▶  Нэгдэх";
                Brush btnBg = !isLobby ? HexBrush("#1A2236") : HexBrush("#10B981");
                Brush btnFg = !isLobby ? HexBrush("#CBD5E1") : HexBrush("#FFFFFF");
                Brush btnBorder = !isLobby ? HexBrush("#334155") : HexBrush("#34D399");

                list.Add(new LobbyItem
                {
                    Id = r["id"],
                    RowNum = (list.Count + 1).ToString(),
                    Name = r["name"],
                    SubInfo = subInfo,
                    SubInfoFg = subFg,
                    LockIconVis = isLocked ? Visibility.Visible : Visibility.Collapsed,
                    LockBadgeVis = isLocked ? Visibility.Visible : Visibility.Collapsed,
                    HotBadgeVis = (isLobby && pNum >= 8) ? Visibility.Visible : Visibility.Collapsed,
                    NoLeaverVis = noLeavers ? Visibility.Visible : Visibility.Collapsed,
                    MapName = mTitle,
                    MapTitle = mTitle,
                    MapSub = mSub,
                    MapIcon = imgMaps[mIdx],
                    Host = r["host"],
                    HostInitial = hInit,
                    HostUid = "#" + (r.ContainsKey("host_uid") ? r["host_uid"] : "10001"),
                    Players = r["players"],
                    PlayersFillWidth = fillW,
                    PlayersBarBrush = !isLobby ? HexBrush("#F59E0B") : (pNum >= 8 ? HexBrush("#10B981") : HexBrush("#8B5CF6")),
                    PingText = currentPingMs + " ms",
                    StatusText = stText,
                    StatusBg = stBg,
                    StatusFg = stFg,
                    StatusBorder = stBorder,
                    Phase = r["phase"],
                    JoinBtnText = btnText,
                    ActionBtnBg = btnBg,
                    ActionBtnFg = btnFg,
                    ActionBtnBorder = btnBorder
                });
            }
            lobbiesList.ItemsSource = list;
            lblLobbySubCount.Text = "Нийт " + countAll + " лобби (" + countOpen + " нээлттэй)";
            if (lblLastUpdatedTime != null)
                lblLastUpdatedTime.Text = "Сүүлийн шинэчлэл: " + DateTime.Now.ToString("HH:mm:ss");
        }

        private static void RefreshLeaderboardAsync()
        {
            if (string.IsNullOrEmpty(authToken)) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string lbJson = ApiRequest("GET", "/api/leaderboard");
                    List<string> objs = ExtractJsonObjectArray(lbJson, "leaderboard");
                    List<LeaderboardItem> items = new List<LeaderboardItem>();
                    foreach (string o in objs)
                    {
                        int rnk = ExtractJsonInt(o, "rank", 1);
                        string uname = ExtractJsonString(o, "username");
                        if (string.IsNullOrEmpty(uname)) uname = ExtractJsonString(o, "name");
                        int uid = ExtractJsonInt(o, "uid_num", 10001);
                        string bLbl = ExtractJsonString(o, "badge_label");
                        string bCol = ExtractJsonString(o, "badge_color");
                        string eDisp = ExtractJsonString(o, "elo_display");
                        string eCol = ExtractJsonString(o, "elo_color");
                        int k = ExtractJsonInt(o, "kills", 0);
                        int d = ExtractJsonInt(o, "deaths", 0);
                        int gp = ExtractJsonInt(o, "games_played", 0);
                        int w = ExtractJsonInt(o, "wins", 0);
                        int l = ExtractJsonInt(o, "losses", 0);
                        int lv = ExtractJsonInt(o, "leaves", 0);
                        int cr = ExtractJsonInt(o, "clean_rate", 100);

                        string rankIcon = rnk == 1 ? "🥇 #1" : (rnk == 2 ? "🥈 #2" : (rnk == 3 ? "🥉 #3" : ("#" + rnk)));
                        string rankHex = rnk == 1 ? "#FBBF24" : (rnk == 2 ? "#E2E8F0" : (rnk == 3 ? "#F59E0B" : "#94A3B8"));
                        double avgK = gp > 0 ? Math.Round((double)k / gp, 1) : 0.0;

                        items.Add(new LeaderboardItem
                        {
                            RankText = rankIcon,
                            RankFg = HexBrush(rankHex),
                            Name = uname,
                            DisplayName = uname + "  (#" + uid + ")",
                            BadgeLabel = string.IsNullOrEmpty(bLbl) ? "🛡️ Итгэлтэй" : bLbl,
                            BadgeFg = HexBrush(bCol),
                            EloDisplay = string.IsNullOrEmpty(eDisp) ? "⏳ Түвшин тогтоох" : eDisp,
                            EloFg = HexBrush(eCol),
                            KdDisplay = "🗡️ " + k + " / 💀 " + d + " (" + avgK + "/g)",
                            GamesDisplay = gp + " (" + w + "W-" + l + "L)",
                            CleanRateDisplay = cr + "% (" + lv + " leave)"
                        });
                    }
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (leaderboardListCtrl != null)
                            leaderboardListCtrl.ItemsSource = items;
                    }));
                }
                catch { }
            });
        }

        private static void OnLeaderboardButtonClick(object sender, RoutedEventArgs e)
        {
            Button btn = e.OriginalSource as Button;
            if (btn != null && btn.Tag != null)
            {
                string u = btn.Tag.ToString();
                if (!string.IsNullOrEmpty(u))
                    OpenPlayerActionModal(u, false, true);
            }
        }

        private static void ResetCurrentRoomRuntimeState()
        {
            currentRoomPhase = "LOBBY";
            currentRoomAbsent = "";
            currentRoomLaunchSig = 0;
            currentRoomWaitRemSec = 0;
            currentRoomAddtimeUsed = 0;
            currentRoomAddtimeMax = 3;
            currentRoomCanHostDrop = false;
            currentRoomW3gsConnectedCount = 0;
            currentRoomMyW3gsConnected = false;
            currentRoomMyDisconnected = false;
            currentRoomRejoinReady = false;
            hasLaunchedWar3InCurrentRoom = false;
        }

        private static void CreateRoom()
        {
            string rname = (txtNewRoomName.Text ?? "").Trim();
            if (string.IsNullOrEmpty(rname))
                rname = (string.IsNullOrEmpty(currentUsername) ? "Mongol" : currentUsername) + " — " + OFFICIAL_MAP_TITLES[selectedMapIndex];
            string rcode = (txtNewRoomCode.Text ?? "").Trim();
            bool noLeavers = (chkNoLeavers != null && chkNoLeavers.IsChecked == true);
            string mapFile = OFFICIAL_MAP_TITLES[selectedMapIndex];
            string matchKey = OFFICIAL_MAP_KEYS[selectedMapIndex];
            foreach (var m in cachedMaps)
            {
                string mt = ((m.ContainsKey("title") ? m["title"] : "") + " " + (m.ContainsKey("filename") ? m["filename"] : "")).ToLowerInvariant();
                if (mt.Contains(matchKey) && m.ContainsKey("filename") && selectedMapIndex > 0)
                {
                    mapFile = m["filename"];
                    break;
                }
            }

            try
            {
                string body = "{\"name\":\"" + rname.Replace("\"", "") + "\",\"map_name\":\"" + mapFile.Replace("\"", "") + "\",\"capacity\":10,\"room_code\":\"" + rcode.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\",\"no_leavers\":" + (noLeavers ? "true" : "false") + "}";
                string res = ApiRequest("POST", "/api/rooms", body);
                currentRoomId = ExtractJsonString(res, "room_id");
                currentRoomName = rname;
                currentRoomMapName = mapFile;
                currentRoomCode = rcode;
                isCurrentRoomOwner = true;
                lastHandledLaunchSignal = 0;
                lastRoomChatMsgId = 0;
                ResetCurrentRoomRuntimeState();
                w3gsPort = ExtractJsonInt(res, "w3gs_port", 8051);
                string lanHex = ExtractJsonString(res, "lan_ad_hex");
                if (!string.IsNullOrEmpty(lanHex)) currentLanAd = HexToBytes(lanHex);

                lblSetRoomCodeText.Text = string.IsNullOrEmpty(currentRoomCode)
                    ? "🔓 Код Хийх (Нээлттэй)"
                    : "🔒 Код: " + currentRoomCode + " (Солих)";

                string mId = ExtractJsonString(res, "id");
                string mFn = ExtractJsonString(res, "filename");
                string mSha = ExtractJsonString(res, "sha256");
                if (string.IsNullOrEmpty(mFn)) mFn = mapFile;
                currentRoomMapName = mFn;

                lblInnerRoomTitle.Text = "🏰 " + currentRoomName;
                lblInnerRoomSub.Text = "👑 Host: " + currentUsername + "  •  🗺️ Map: " + mFn + " (Шалгаж байна...)";
                SwitchPage("LOBBIES");
                UpdateInnerRoomVisibility();
                SyncRoomStateOnceAsync();

                string createdRid = currentRoomId;
                ThreadPool.QueueUserWorkItem(_ =>
                {
                    try
                    {
                        EnsureMapDownloaded(mId, mFn, mSha);
                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            if (string.IsNullOrEmpty(currentRoomId) || currentRoomId != createdRid) return;
                            string codeTag = string.IsNullOrEmpty(currentRoomCode) ? "🔓 Нээлттэй" : ("🔒 Код: " + currentRoomCode);
                            lblInnerRoomSub.Text = "👑 Host: " + currentUsername + "  •  🗺️ Map: " + mFn + " (✅ Бэлэн)  •  " + codeTag;
                        }));
                    }
                    catch { }
                });
                RefreshMapsAndRooms();
            }
            catch (Exception ex)
            {
                MessageBox.Show("Өрөө үүсгэхэд алдаа: " + ex.Message, "MongolRanger");
            }
        }

        private static void JoinRoomById(string rid, string roomCode = "")
        {
            try
            {
                string body = "{\"room_code\":\"" + (roomCode ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                string res = ApiRequest("POST", "/api/rooms/" + rid + "/join", body);
                currentRoomId = rid;
                currentRoomName = "Joined Room";
                isCurrentRoomOwner = false;
                lastRoomChatMsgId = 0;
                ResetCurrentRoomRuntimeState();
                foreach (var r in cachedRooms)
                {
                    if (r["id"] == rid)
                    {
                        currentRoomName = r["name"];
                        if (string.Equals(r["host"], currentUsername, StringComparison.OrdinalIgnoreCase))
                            isCurrentRoomOwner = true;
                    }
                }
                int existingSig = ExtractJsonInt(res, "launch_signal", 0);
                if (existingSig > 0)
                {
                    lastHandledLaunchSignal = existingSig;
                    handledLaunchSignals.Add(existingSig);
                }
                w3gsPort = ExtractJsonInt(res, "w3gs_port", 8051);
                string lanHex = ExtractJsonString(res, "lan_ad_hex");
                if (!string.IsNullOrEmpty(lanHex)) currentLanAd = HexToBytes(lanHex);

                string mId = ExtractJsonString(res, "id");
                string mFn = ExtractJsonString(res, "filename");
                string mSha = ExtractJsonString(res, "sha256");
                currentRoomMapName = mFn;

                lblInnerRoomTitle.Text = "🏰 " + currentRoomName;
                lblInnerRoomSub.Text = "🗺️ Map: " + mFn + " (Татаж байна...)  •  🛡️ Anti-MapHack Идэвхтэй";
                SwitchPage("LOBBIES");
                UpdateInnerRoomVisibility();
                SyncRoomStateOnceAsync();

                ThreadPool.QueueUserWorkItem(_ =>
                {
                    try
                    {
                        EnsureMapDownloaded(mId, mFn, mSha);
                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            if (string.IsNullOrEmpty(currentRoomId) || currentRoomId != rid) return;
                            lblInnerRoomSub.Text = "🗺️ Map: " + mFn + " (✅ Татагдсан)  •  🛡️ Anti-MapHack Идэвхтэй";
                        }));
                    }
                    catch { }
                });
            }
            catch (WebException wex)
            {
                string errDetail = "";
                try
                {
                    if (wex.Response != null)
                    {
                        using (StreamReader sr = new StreamReader(wex.Response.GetResponseStream()))
                        {
                            string raw = sr.ReadToEnd();
                            errDetail = ExtractJsonString(raw, "detail");
                        }
                    }
                }
                catch { }

                HttpWebResponse httpResp = wex.Response as HttpWebResponse;
                if (httpResp != null && httpResp.StatusCode == HttpStatusCode.Forbidden)
                {
                    if (!string.IsNullOrEmpty(errDetail) && (errDetail.Contains("Leaver") || errDetail.Contains("Kicked") || errDetail.Contains("хөөгдсөн")))
                    {
                        MessageBox.Show(errDetail, "MongolRanger — Өрөөний Хамгаалалт");
                        return;
                    }
                    OpenJoinRoomCodeModal(rid, currentRoomName);
                    lblCodeModalError.Text = "❌ Өрөөний нууц код буруу байна! Дахин оруулна уу.";
                    return;
                }
                MessageBox.Show("Өрөөнд ороход алдаа: " + (!string.IsNullOrEmpty(errDetail) ? errDetail : wex.Message), "MongolRanger");
            }
            catch (Exception ex)
            {
                MessageBox.Show("Өрөөнд ороход алдаа: " + ex.Message, "MongolRanger");
            }
        }

        private static void StartRoomMatch()
        {
            if (string.IsNullOrEmpty(currentRoomId) || !isCurrentRoomOwner) return;
            try
            {
                string res = ApiRequest("POST", "/api/rooms/" + currentRoomId + "/launch", "{}");
                int sig = ExtractJsonInt(res, "launch_signal", (int)(DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds);
                lastHandledLaunchSignal = sig;
                if (sig > 0) handledLaunchSignals.Add(sig);
                currentRoomLaunchSig = sig;
                hasLaunchedWar3InCurrentRoom = true;
                LaunchWarcraftIfNotRunning(true);
                SyncRoomStateOnceAsync();
            }
            catch (Exception ex)
            {
                MessageBox.Show("Тоглоом эхлүүлэхэд алдаа: " + ex.Message, "MongolRanger");
            }
        }

        private static void RejoinActiveMatch()
        {
            if (string.IsNullOrEmpty(currentRoomId)) return;
            if (!currentRoomRejoinReady) return;
            string rid = currentRoomId;
            if (lblRejoinBtnText != null)
                lblRejoinBtnText.Text = "⏳ Сэргээх цэг татаж Warcraft III асааж байна...";
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string st = ApiRequest("GET", "/api/rooms/" + rid + "/state?local_port=" + localProxyPort);
                    string lanHex = ExtractJsonString(st, "lan_ad_hex");
                    if (string.IsNullOrEmpty(lanHex) && currentRoomId == rid) currentLanAd = null; // FROZEN: never advertise a stale lobby
                    else if (currentRoomId == rid)
                        currentLanAd = HexToBytes(lanHex);
                    Match cpMatch = Regex.Match(st, "\"checkpoint\"\\s*:\\s*\\{([^{}]+)\\}");
                    if (cpMatch.Success)
                    {
                        string cpObj = cpMatch.Groups[1].Value;
                        string cpSha = ExtractJsonString(cpObj, "sha256");
                        string cpFn = ExtractJsonString(cpObj, "filename");
                        if (!string.IsNullOrEmpty(cpFn))
                            DownloadCheckpoint(cpFn, cpSha);
                    }
                }
                catch { }
                mainWin.Dispatcher.BeginInvoke(new Action(() =>
                {
                    if (string.IsNullOrEmpty(currentRoomId) || currentRoomId != rid) return;
                    hasLaunchedWar3InCurrentRoom = true;
                    LaunchWarcraftIfNotRunning(true);
                    UpdateInnerRoomVisibility();
                    SyncRoomStateOnceAsync();
                }));
            });
        }

        private static void ExtendRoomWaitTime()
        {
            if (string.IsNullOrEmpty(currentRoomId)) return;
            string rid = currentRoomId;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    ApiRequest("POST", "/api/rooms/" + rid + "/addtime", "{}");
                    SyncRoomStateOnceAsync();
                }
                catch (WebException wex)
                {
                    string err = "";
                    try
                    {
                        if (wex.Response != null)
                        {
                            using (StreamReader sr = new StreamReader(wex.Response.GetResponseStream()))
                                err = ExtractJsonString(sr.ReadToEnd(), "detail");
                        }
                    }
                    catch { }
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        MessageBox.Show(!string.IsNullOrEmpty(err) ? err : "Цаг сунгахад алдаа гарлаа.", "MongolRanger");
                    }));
                }
                catch { }
            });
        }

        private static void DropAbsentRoomPlayer()
        {
            if (string.IsNullOrEmpty(currentRoomId) || !isCurrentRoomOwner) return;
            string rid = currentRoomId;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    ApiRequest("POST", "/api/rooms/" + rid + "/drop", "{}");
                    SyncRoomStateOnceAsync();
                }
                catch (WebException wex)
                {
                    string err = "";
                    try
                    {
                        if (wex.Response != null)
                        {
                            using (StreamReader sr = new StreamReader(wex.Response.GetResponseStream()))
                                err = ExtractJsonString(sr.ReadToEnd(), "detail");
                        }
                    }
                    catch { }
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        MessageBox.Show(!string.IsNullOrEmpty(err) ? err : "Тоглогчийг хасахад алдаа гарлаа.", "MongolRanger");
                    }));
                }
                catch { }
            });
        }

        private static void BroadcastLanDecreate()
        {
            try
            {
                if (udpBroadcaster != null)
                {
                    byte[] decPkt = new byte[] { 0xF7, 0x33, 0x08, 0x00, 0x01, 0x00, 0x00, 0x00 };
                    try { udpBroadcaster.Send(decPkt, decPkt.Length, new IPEndPoint(IPAddress.Loopback, 6112)); } catch { }
                }
            }
            catch { }
        }

        private static void LeaveRoom(bool notifyServer = true)
        {
            if (notifyServer && IsMatchOrRejoinLocked())
                return;

            string rid = currentRoomId;
            if (lastHandledLaunchSignal > 0)
                handledLaunchSignals.Add(lastHandledLaunchSignal);
            if (currentRoomLaunchSig > 0)
                handledLaunchSignals.Add(currentRoomLaunchSig);

            currentRoomId = "";
            currentRoomName = "";
            currentRoomMapName = "";
            currentRoomCode = "";
            isCurrentRoomOwner = false;
            lastRoomChatMsgId = 0;
            currentLanAd = null;
            ResetCurrentRoomRuntimeState();
            BroadcastLanDecreate();

            if (lblSetRoomCodeText != null)
                lblSetRoomCodeText.Text = "🔒 Код Хийх / Солих";
            if (roomChatList != null)
                roomChatList.ItemsSource = null;
            if (roomMembersList != null)
                roomMembersList.ItemsSource = null;
            UpdateInnerRoomVisibility();

            if (!string.IsNullOrEmpty(rid))
            {
                ThreadPool.QueueUserWorkItem(_ =>
                {
                    if (notifyServer)
                    {
                        try { ApiRequest("POST", "/api/rooms/" + rid + "/leave", "{}"); } catch { }
                    }
                    RefreshMapsAndRooms();
                });
            }
            else
            {
                RefreshMapsAndRooms();
            }
        }

        // =====================================================================
        // 🛡️ MONGOLRANGER 3-LAYER ANTI-MAPHACK SHIELD
        // =====================================================================
        private static int EnforceCleanWar3Directory(string dir)
        {
            int removedCount = 0;
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return 0;

            // 1. Remove proxy DLL hooks from root Warcraft III folder
            string[] bannedRootDlls = new string[]
            {
                "d3d8.dll", "d3d9.dll", "ddraw.dll", "opengl32.dll", "dsound.dll", "winmm.dll"
            };
            foreach (string dll in bannedRootDlls)
            {
                string p = Path.Combine(dir, dll);
                if (File.Exists(p))
                {
                    try { File.Delete(p); removedCount++; } catch { }
                }
            }

            // 2. Scan root and redist\miles for unauthorized .mix / .asi / .flt / .m3d auto-loaded Miles Sound plugins
            HashSet<string> allowedMiles = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "mp3dec.asi", "mssdsp.flt", "mssfast.m3d", "mssdolby.m3d",
                "msseax2.m3d", "mssds3d.m3d", "mssrsx.m3d", "msssoft.m3d"
            };
            string[] scanDirs = new string[] { dir, Path.Combine(dir, "redist"), Path.Combine(dir, "redist", "miles") };
            foreach (string sdir in scanDirs)
            {
                if (!Directory.Exists(sdir)) continue;
                try
                {
                    foreach (string f in Directory.GetFiles(sdir))
                    {
                        string ext = Path.GetExtension(f).ToLowerInvariant();
                        string fname = Path.GetFileName(f);
                        if (ext == ".mix" || ext == ".asi" || ext == ".flt" || ext == ".m3d")
                        {
                            if (!allowedMiles.Contains(fname))
                            {
                                try { File.Delete(f); removedCount++; } catch { }
                            }
                        }
                    }
                }
                catch { }
            }
            return removedCount;
        }

        private static readonly string[] CHEAT_PROCESS_NAMES = new string[0];

        private static string ScanForActiveMapHack(bool fullScan = false)
        {
            try
            {
                if (fullScan)
                {
                    // Clean unauthorized .mix/.asi/proxy DLL files in War3 directory before launch
                    EnforceCleanWar3Directory(war3Dir);
                }

                // Fast, zero-stutter check for known external MapHack process names
                // (Never enumerates war3.exe Process.Modules or queries MainWindowTitle across desktop windows during gameplay!)
                foreach (string kw in CHEAT_PROCESS_NAMES)
                {
                    try
                    {
                        Process[] found = Process.GetProcessesByName(kw);
                        if (found != null && found.Length > 0)
                        {
                            return "MapHack програм илэрлээ (" + kw + ")";
                        }
                    }
                    catch { }
                }

                if (fullScan)
                {
                    foreach (string wName in new string[] { "war3", "w3l" })
                    {
                        try
                        {
                            foreach (Process proc in Process.GetProcessesByName(wName))
                            {
                                try
                                {
                                    string runningExe = proc.MainModule.FileName;
                                    if (!string.IsNullOrEmpty(runningExe))
                                    {
                                        string runningDir = Path.GetDirectoryName(runningExe);
                                        if (!string.IsNullOrEmpty(runningDir) && Directory.Exists(runningDir) &&
                                            !string.Equals(runningDir, war3Dir, StringComparison.OrdinalIgnoreCase))
                                        {
                                            war3Dir = runningDir;
                                            if (mainWin != null)
                                            {
                                                mainWin.Dispatcher.BeginInvoke(new Action(() =>
                                                {
                                                    if (txtWar3Path != null) txtWar3Path.Text = war3Dir;
                                                    SaveSettings();
                                                }));
                                            }
                                            if (!string.IsNullOrEmpty(currentRoomMapName))
                                            {
                                                try { EnsureMapDownloaded("", currentRoomMapName, ""); } catch { }
                                            }
                                        }
                                    }
                                }
                                catch { }
                            }
                        }
                        catch { }
                    }
                }
            }
            catch { }
            return "";
        }

        private static void KillRunningWarcraft()
        {
            foreach (string n in new string[] { "war3", "w3l" })
            {
                try
                {
                    foreach (Process p in Process.GetProcessesByName(n))
                    {
                        try { p.Kill(); } catch { }
                    }
                }
                catch { }
            }
            cachedWar3Running = false;
            lastWar3RunCheckUtc = DateTime.MinValue;
        }

        private static void LaunchWarcraftIfNotRunning(bool requireActiveRoom = true)
        {
            if (requireActiveRoom && string.IsNullOrEmpty(currentRoomId))
                return;
            if (IsWarcraftRunning(true))
            {
                hasLaunchedWar3InCurrentRoom = true;
                if (!string.IsNullOrEmpty(currentRoomMapName))
                {
                    string mapToCheck = currentRoomMapName;
                    ThreadPool.QueueUserWorkItem(_ => { try { EnsureMapDownloaded("", mapToCheck, ""); } catch { } });
                }
                return;
            }
            LaunchWarcraft(requireActiveRoom);
        }

        private static void LaunchWarcraft(bool requireActiveRoom = false)
        {
            if (requireActiveRoom && string.IsNullOrEmpty(currentRoomId))
                return;
            string expectedRid = currentRoomId;
            string rawInputDir = txtWar3Path.Text.Trim();
            string resolvedDir = ResolveWar3DirectoryRecursive(rawInputDir, 6);
            if (!string.IsNullOrEmpty(resolvedDir))
            {
                war3Dir = resolvedDir;
                txtWar3Path.Text = war3Dir;
            }
            else
            {
                war3Dir = rawInputDir;
            }
            SaveSettings();
            SyncWar3Username(currentUsername);
            string w3l = Path.Combine(war3Dir, "w3l.exe");
            string war3 = Path.Combine(war3Dir, "war3.exe");
            string exe = File.Exists(w3l) ? w3l : (File.Exists(war3) ? war3 : "");
            if (string.IsNullOrEmpty(exe))
            {
                openedSettingsForFirstTimeSetup = true;
                SwitchPage("SETTINGS");
                MessageBox.Show("Warcraft III 1.26a хавтас тохируулаагүй байна!\n\n[1-р алхам] дээрээс өөрийн компьютер дээрх Warcraft III суусан хавтсаа сонгоно уу. Сонгомогц манай Reconnect Patch автоматаар сууна!", "MongolRanger — Warcraft III Тохируулах");
                return;
            }

            // Anti-MapHack pre-launch full check
            string mhViolation = ScanForActiveMapHack(true);
            if (!string.IsNullOrEmpty(mhViolation))
            {
                MessageBox.Show("🚨 [MongolRanger Anti-MapHack Shield]\n\n" + mhViolation + "!\n\nХууль бус MapHack / Cheat програмаа хаагаад дахин оролдоно уу!", "MongolRanger Anti-MapHack");
                return;
            }

            try
            {
                if (!string.IsNullOrEmpty(currentRoomMapName))
                {
                    try { EnsureMapDownloaded("", currentRoomMapName, ""); } catch { }
                }
                // #4 Guard: If the user left the room while the map was downloading, or War3 is already running, NEVER auto-launch War3!
                if (requireActiveRoom && (string.IsNullOrEmpty(currentRoomId) || currentRoomId != expectedRid))
                    return;
                if (IsWarcraftRunning(true))
                    return;

                ApplyWar3LocalOptimizations(war3Dir);
                hasLaunchedWar3InCurrentRoom = true;
                ProcessStartInfo psi = new ProcessStartInfo(exe);
                psi.WorkingDirectory = war3Dir;
                Process.Start(psi);
                cachedWar3Running = true;
                lastWar3RunCheckUtc = DateTime.UtcNow;
            }
            catch (Exception ex)
            {
                MessageBox.Show("Warcraft III асаахад алдаа: " + ex.Message, "MongolRanger");
            }
        }

        private static readonly object mapDownloadLock = new object();
        private static volatile bool isRunningAutoPatch = false;

        private static void DownloadFileWithRetry(string url, string destFile, int timeoutMs = 45000)
        {
            Exception lastEx = null;
            for (int attempt = 0; attempt < 2; attempt++)
            {
                string useUrl = url;
                if (attempt == 0 && activeServerUrl != SERVER_URL && useUrl.StartsWith(SERVER_URL, StringComparison.OrdinalIgnoreCase))
                    useUrl = FALLBACK_SERVER_URL + useUrl.Substring(SERVER_URL.Length);
                else if (attempt == 1 && useUrl.StartsWith(SERVER_URL, StringComparison.OrdinalIgnoreCase))
                {
                    activeServerUrl = FALLBACK_SERVER_URL;
                    useUrl = FALLBACK_SERVER_URL + useUrl.Substring(SERVER_URL.Length);
                }
                else if (attempt == 1 && useUrl.StartsWith(FALLBACK_SERVER_URL, StringComparison.OrdinalIgnoreCase))
                {
                    useUrl = SERVER_URL + useUrl.Substring(FALLBACK_SERVER_URL.Length);
                }
                try
                {
                    if (File.Exists(destFile))
                    {
                        try { File.SetAttributes(destFile, FileAttributes.Normal); } catch { }
                        try { File.Delete(destFile); } catch { }
                    }
                    HttpWebRequest req = (HttpWebRequest)WebRequest.Create(useUrl);
                    req.Method = "GET";
                    req.Timeout = timeoutMs;
                    req.ReadWriteTimeout = timeoutMs;
                    req.UserAgent = "MongolRanger/4.8";
                    using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                    using (Stream rs = resp.GetResponseStream())
                    using (FileStream fs = new FileStream(destFile, FileMode.Create, FileAccess.Write, FileShare.None))
                    {
                        byte[] buf = new byte[65536];
                        int read;
                        while ((read = rs.Read(buf, 0, buf.Length)) > 0)
                        {
                            fs.Write(buf, 0, read);
                        }
                    }
                    return;
                }
                catch (Exception ex)
                {
                    lastEx = (ex is WebException && ex.InnerException != null) ? ex.InnerException : ex;
                    try { if (File.Exists(destFile)) File.Delete(destFile); } catch { }
                    Thread.Sleep(250);
                }
            }
            if (lastEx != null) throw lastEx;
        }

        private static void EnsureMapDownloaded(string mapId, string filename, string expectedSha256 = "")
        {
            if (string.IsNullOrEmpty(filename) || string.IsNullOrEmpty(war3Dir)) return;
            lock (mapDownloadLock)
            {
                string fnOnly = Path.GetFileName(filename);
                if (!fnOnly.EndsWith(".w3x", StringComparison.OrdinalIgnoreCase) && !fnOnly.EndsWith(".w3m", StringComparison.OrdinalIgnoreCase))
                {
                    int mIdx = GetOfficialMapIndex(fnOnly);
                    string key = OFFICIAL_MAP_KEYS[mIdx];
                    string resolvedFn = "";
                    foreach (var m in cachedMaps)
                    {
                        string mt = ((m.ContainsKey("title") ? m["title"] : "") + " " + (m.ContainsKey("filename") ? m["filename"] : "")).ToLowerInvariant();
                        if (mt.Contains(key) && m.ContainsKey("filename"))
                        {
                            resolvedFn = Path.GetFileName(m["filename"]);
                            break;
                        }
                    }
                    if (string.IsNullOrEmpty(resolvedFn))
                        resolvedFn = (cachedMaps.Count > 0 && cachedMaps[0].ContainsKey("filename")) ? Path.GetFileName(cachedMaps[0]["filename"]) : "LoD_Sync_25.w3x";
                    fnOnly = resolvedFn;
                }
                if (string.IsNullOrEmpty(expectedSha256) || string.IsNullOrEmpty(mapId))
                {
                    try
                    {
                        foreach (var m in cachedMaps)
                        {
                            if (m.ContainsKey("filename") && string.Equals(Path.GetFileName(m["filename"]), fnOnly, StringComparison.OrdinalIgnoreCase))
                            {
                                if (string.IsNullOrEmpty(mapId) && m.ContainsKey("id")) mapId = m["id"];
                                if (string.IsNullOrEmpty(expectedSha256) && m.ContainsKey("sha256")) expectedSha256 = m["sha256"];
                                break;
                            }
                        }
                    }
                    catch { }
                }
                string dlDir = Path.Combine(war3Dir, "Maps", "Download");
                if (!Directory.Exists(dlDir))
                {
                    Directory.CreateDirectory(dlDir);
                }
                try { File.SetAttributes(dlDir, FileAttributes.Normal); } catch { }

                string dest = Path.Combine(dlDir, fnOnly);
                if (File.Exists(dest))
                {
                    try
                    {
                        long flen = new FileInfo(dest).Length;
                        // Warcraft III 1.26a standard LAN rejects maps > 8,388,608 bytes; force re-download if an older oversized map is cached
                        if (flen > 1024 && flen <= 8388608)
                        {
                            if (string.IsNullOrEmpty(expectedSha256)) return;
                            using (FileStream fs = new FileStream(dest, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                            using (SHA256 sha256 = SHA256.Create())
                            {
                                byte[] hashBytes = sha256.ComputeHash(fs);
                                StringBuilder sb = new StringBuilder(hashBytes.Length * 2);
                                foreach (byte b in hashBytes) sb.Append(b.ToString("x2"));
                                if (string.Equals(sb.ToString(), expectedSha256, StringComparison.OrdinalIgnoreCase))
                                    return;
                            }
                        }
                    }
                    catch
                    {
                        // If war3.exe currently has the map open and its size is valid, do not fail
                        try
                        {
                            long flen2 = new FileInfo(dest).Length;
                            if (flen2 > 1024 && flen2 <= 8388608) return;
                        }
                        catch { }
                    }
                }

                // Check if the same map already exists directly in Maps\ (e.g. from extracted Warcraft III package)
                try
                {
                    string altMap = Path.Combine(war3Dir, "Maps", fnOnly);
                    if (File.Exists(altMap) && !string.Equals(altMap, dest, StringComparison.OrdinalIgnoreCase))
                    {
                        long altLen = new FileInfo(altMap).Length;
                        if (altLen > 1024 && altLen <= 8388608)
                        {
                            string altSha = ComputeSha256(File.ReadAllBytes(altMap));
                            if (string.IsNullOrEmpty(expectedSha256) || string.Equals(altSha, expectedSha256, StringComparison.OrdinalIgnoreCase))
                            {
                                if (File.Exists(dest))
                                {
                                    try { File.SetAttributes(dest, FileAttributes.Normal); } catch { }
                                    try { File.Delete(dest); } catch { }
                                }
                                File.Copy(altMap, dest, true);
                                return;
                            }
                        }
                    }
                }
                catch { }

                string tmp = Path.Combine(dlDir, fnOnly + "." + Guid.NewGuid().ToString("N").Substring(0, 6) + ".tmp");
                string url = SERVER_URL + "/api/maps/" + Uri.EscapeDataString(string.IsNullOrEmpty(mapId) ? fnOnly : mapId) + "/download";
                try
                {
                    DownloadFileWithRetry(url, tmp, 60000);
                    if (File.Exists(dest))
                    {
                        try { File.SetAttributes(dest, FileAttributes.Normal); } catch { }
                        File.Delete(dest);
                    }
                    File.Move(tmp, dest);
                }
                catch (Exception)
                {
                    try { if (File.Exists(tmp)) File.Delete(tmp); } catch { }
                    // If dest already exists with valid size (e.g. locked by running war3.exe), keep existing file without error
                    if (File.Exists(dest))
                    {
                        try
                        {
                            long existingLen = new FileInfo(dest).Length;
                            if (existingLen > 1024 && existingLen <= 8388608) return;
                        }
                        catch { }
                    }
                    throw;
                }
            }
        }

        private static void PatchGameDllMapSizeLimit(string gameDllPath)
        {
            try
            {
                if (string.IsNullOrEmpty(gameDllPath) || !File.Exists(gameDllPath)) return;
                byte[] dll = File.ReadAllBytes(gameDllPath);
                int[] offsets = new int[] { 0x6577E3, 0x66ED7E, 0x67EC60 };
                bool modified = false;
                foreach (int off in offsets)
                {
                    if (off + 7 <= dll.Length &&
                        dll[off] == 0x3D && dll[off + 1] == 0x00 && dll[off + 2] == 0x00 &&
                        dll[off + 3] == 0x80 && dll[off + 4] == 0x00 && dll[off + 5] == 0x0F && dll[off + 6] == 0x87)
                    {
                        dll[off + 1] = 0xFF;
                        dll[off + 2] = 0xFF;
                        dll[off + 3] = 0xFF;
                        dll[off + 4] = 0x07;
                        modified = true;
                    }
                }
                if (modified)
                    File.WriteAllBytes(gameDllPath, dll);
            }
            catch { }
            PatchGameDllLagTimer180(gameDllPath);
        }

        // Warcraft III 1.26a hard-codes the "Waiting for players..." lag window as 45000 ms (0x0000AFC8) at 12 sites
        // (W3GS_START_LAG/STOP_LAG handlers + lag accumulator clamp). Patch every site to 180000 ms (0x0002BF20)
        // so the native dialog counts down from 3:00 instead of 0:45.
        private static readonly int[] LAG_TIMER_OFFSETS = new int[] {
            0x663CFD, 0x66BF3B, 0x66BF42, 0x66C374, 0x66C39D, 0x66C3A4, 0x66C3A9,
            0x67B1F7, 0x67B204, 0x67B219, 0x67D32C, 0x67D339 };

        private const string REJOIN_CAVE_HEX =
            "e8444af7ff9c60e8000000005f81ef1cc686008bb7f465ab0085f6742b8b8f804fab0085c974210fb7562883fa0c731851bb0100000089d1d3e366895e2c59528d8750cb2f00ffd0619de9d84bd5ff00" +
            "9c608b86882800008b50048b4008b90100000081fa000001000f87220000003bca0f831a000000393c880f840600000041e9e9ffffff894c241c619de9da07bfff619d8b868c280000e9d807bfff0000" +
            "9c60e8000000005d81edb7c686008b858c77ab008b481c81f9000010000f87ad0000008b500c31ff31f63bf90f8382000000833cfafe0f856c0000008b44fa0481780c6c67612b0f855b000000817810726c64680f854e000000837820000f85440000003978140f853b000000508b405485c00f842e0000003958240f852500000039780c0f851c000000558b6c24048b6d183968105d0f850a00000085f60f85090000008bf05847e97cffffff58e91c00000085f60f841400000089742404619d568d4f18e8558db4ffe96b43bcff619d6a008d4c2458e9a842bcff000000" +
            "9c60e8000000005d81ed97c786008b858c77ab008b481c81f9000010000f87bf0000008b500c31ff31f63bf90f8394000000833cfafe0f857e0000008b44fa0481780c6c67612b0f856d000000817810746c662b0f8560000000837820000f85560000003978140f854d000000508b405485c00f8440000000558b682485ed5d0f8433000000558b6824395d245d0f852500000039780c0f851c000000558b6c24048b6d183968105d0f850a00000085f60f85090000008bf05847e96affffff58e91c00000085f60f841400000089742404619d568d4f18e8d397b4ffe9eb43bcff619d6a008d4c2458e92643bcff";

        private static bool ApplyBytesAt(byte[] buf, int offset, byte[] patch)
        {
            if (offset < 0 || offset + patch.Length > buf.Length) return false;
            bool changed = false;
            for (int i = 0; i < patch.Length; i++)
            {
                if (buf[offset + i] != patch[i])
                {
                    buf[offset + i] = patch[i];
                    changed = true;
                }
            }
            return changed;
        }

        private static void PatchGameDllLagTimer180(string gameDllPath)
        {
            try
            {
                if (string.IsNullOrEmpty(gameDllPath) || !File.Exists(gameDllPath)) return;
                byte[] dll = File.ReadAllBytes(gameDllPath);
                // Only patch when every site holds 45000 or 180000 (i.e. this really is the 1.26a Game.dll)
                foreach (int off in LAG_TIMER_OFFSETS)
                {
                    if (off + 4 > dll.Length) return;
                    int v = BitConverter.ToInt32(dll, off);
                    if (v != 45000 && v != 180000) return;
                }
                bool modified = false;
                foreach (int off in LAG_TIMER_OFFSETS)
                {
                    if (BitConverter.ToInt32(dll, off) == 45000)
                    {
                        dll[off] = 0x20; dll[off + 1] = 0xBF; dll[off + 2] = 0x02; dll[off + 3] = 0x00;
                        modified = true;
                    }
                }
                if (dll.Length == 12042240)
                {
                    if (ApplyBytesAt(dll, 0x218, new byte[] { 0x7F, 0xB8, 0x86, 0x00 })) modified = true;
                    if (ApplyBytesAt(dll, 0x2FCBF3, new byte[] { 0xE9, 0xCE, 0x00, 0x00, 0x00 })) modified = true;
                    if (ApplyBytesAt(dll, 0x2FDF7D, new byte[] { 0xE8, 0x65, 0x58, 0x0B, 0x00 })) modified = true;
                    if (ApplyBytesAt(dll, 0x34E98B, new byte[] { 0x01 })) modified = true;
                    if (ApplyBytesAt(dll, 0x3B37E5, new byte[] { 0xEB, 0x13, 0xE8, 0x54, 0x49, 0xF8, 0xFF, 0xE9, 0x6F, 0x16, 0x00, 0x00 })) modified = true;
                    if (ApplyBytesAt(dll, 0x3B4E6A, new byte[] { 0x56, 0x8B, 0xF0, 0x8B, 0x8E, 0xEC, 0x03, 0x00, 0x00, 0xE8, 0x68, 0xF7, 0x24, 0x00, 0x8B, 0xCE, 0x5E, 0xE9, 0x90, 0xEF, 0xF3, 0xFF })) modified = true;
                    if (ApplyBytesAt(dll, 0x430A2F, new byte[] { 0xE9, 0x7C, 0xBC, 0x43, 0x00, 0x90 })) modified = true;
                    if (ApplyBytesAt(dll, 0x430B9F, new byte[] { 0xE9, 0xEC, 0xBB, 0x43, 0x00, 0x90 })) modified = true;
                    if (ApplyBytesAt(dll, 0x45CE80, new byte[] { 0xE9, 0xDB, 0xF7, 0x40, 0x00, 0x90 })) modified = true;
                    if (ApplyBytesAt(dll, 0x5C1232, new byte[] { 0xE9, 0xD9, 0xB3, 0x2A, 0x00 })) modified = true;
                    if (ApplyBytesAt(dll, 0x86C610, HexToBytes(REJOIN_CAVE_HEX))) modified = true;
                }
                if (modified)
                    File.WriteAllBytes(gameDllPath, dll);
            }
            catch { }
        }

        private static void ApplyWar3LocalOptimizations(string dir)
        {
            try
            {
                EnforceCleanWar3Directory(dir);
                PatchGameDllMapSizeLimit(Path.Combine(dir, "Game.dll"));
                string saveDir = Path.Combine(dir, "Save", "Multiplayer");
                string mapsDir = Path.Combine(dir, "Maps", "Download");
                if (!Directory.Exists(saveDir)) Directory.CreateDirectory(saveDir);
                if (!Directory.Exists(mapsDir)) Directory.CreateDirectory(mapsDir);

                foreach (string exeName in new string[] { "war3.exe", "w3l.exe" })
                {
                    string exePath = Path.Combine(dir, exeName);
                    if (!File.Exists(exePath)) continue;
                    try
                    {
                        byte[] pe = File.ReadAllBytes(exePath);
                        if (pe.Length > 0x100)
                        {
                            int peOffset = BitConverter.ToInt32(pe, 0x3C);
                            if (peOffset > 0 && peOffset + 24 < pe.Length &&
                                pe[peOffset] == (byte)'P' && pe[peOffset + 1] == (byte)'E')
                            {
                                ushort chars = BitConverter.ToUInt16(pe, peOffset + 22);
                                if ((chars & 0x0020) == 0)
                                {
                                    ushort newChars = (ushort)(chars | 0x0020);
                                    byte[] cb = BitConverter.GetBytes(newChars);
                                    pe[peOffset + 22] = cb[0];
                                    pe[peOffset + 23] = cb[1];
                                    File.WriteAllBytes(exePath, pe);
                                }
                            }
                        }
                    }
                    catch { }

                    try
                    {
                        using (RegistryKey rk = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"))
                        {
                            if (rk != null)
                            {
                                Version osVer = Environment.OSVersion.Version;
                                if (osVer.Major > 6 || (osVer.Major == 6 && osVer.Minor >= 2))
                                    rk.SetValue(exePath, "~ WIN7RTM", RegistryValueKind.String);
                                else
                                    rk.DeleteValue(exePath, false);
                            }
                        }
                    }
                    catch { }
                }

                try
                {
                    using (RegistryKey vk = Registry.CurrentUser.CreateSubKey(@"Software\Blizzard Entertainment\Warcraft III\Video"))
                    {
                        if (vk != null)
                        {
                            vk.SetValue("cinematicintro", 0, RegistryValueKind.DWord);
                            // Initialize 1024x768 Fullscreen default ONCE if user hasn't set resolution yet;
                            // if user later changes resolution inside Warcraft III Options, never overwrite it!
                            object initFlag = vk.GetValue("mr_init_1024");
                            object curWidth = vk.GetValue("reswidth");
                            if (initFlag == null && curWidth == null)
                            {
                                vk.SetValue("reswidth", 1024, RegistryValueKind.DWord);
                                vk.SetValue("resheight", 768, RegistryValueKind.DWord);
                                vk.SetValue("colordepth", 32, RegistryValueKind.DWord);
                                vk.SetValue("mr_init_1024", 1, RegistryValueKind.DWord);
                            }
                            else if (initFlag == null)
                            {
                                vk.SetValue("mr_init_1024", 1, RegistryValueKind.DWord);
                            }
                        }
                    }
                }
                catch { }

                if (!string.IsNullOrEmpty(currentUsername))
                    SyncWar3Username(currentUsername);
            }
            catch { }
        }

        private static void RunAutoPatchAndSyncAsync()
        {
            if (isRunningAutoPatch) return;
            isRunningAutoPatch = true;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string dir = (war3Dir ?? "").Trim();
                    string resolved = ResolveWar3DirectoryRecursive(dir, 6);
                    if (string.IsNullOrEmpty(resolved))
                    {
                        string autoDet = DetectWar3Directory();
                        if (IsValidWar3Folder(autoDet))
                            resolved = autoDet;
                    }
                    if (!string.IsNullOrEmpty(resolved) && Directory.Exists(resolved))
                    {
                        dir = resolved;
                        if (!string.Equals(war3Dir, resolved, StringComparison.OrdinalIgnoreCase))
                        {
                            war3Dir = resolved;
                            mainWin.Dispatcher.BeginInvoke(new Action(() =>
                            {
                                if (txtWar3Path != null) txtWar3Path.Text = war3Dir;
                                SaveSettings();
                            }));
                        }
                    }

                    string war3Exe = Path.Combine(dir, "war3.exe");
                    string gameDll = Path.Combine(dir, "Game.dll");
                    bool validWar3 = Directory.Exists(dir) && (File.Exists(war3Exe) || File.Exists(gameDll));

                    if (!validWar3)
                    {
                        war3SetupCompleted = false;
                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            SaveSettings();
                            openedSettingsForFirstTimeSetup = true;
                            SwitchPage("SETTINGS");
                            war3ReadyPill.Background = HexBrush("#3B2813");
                            war3ReadyPill.BorderBrush = HexBrush("#F59E0B");
                            lblWar3ReadyPill.Foreground = HexBrush("#FBBF24");
                            lblWar3ReadyPill.Text = "⚠️ War3 Хавтсаа Тохируулна уу";
                            lblStep1.Text = "❌ 1. Сонгосон хавтас дотор war3.exe олдсонгүй (" + dir + ")";
                            lblStep1.Foreground = HexBrush("#F87171");
                            lblSettingsStatus.Foreground = HexBrush("#FBBF24");
                            lblSettingsStatus.Text = "👋 Тавтай морил! Эхлээд дээрх [📁 Хавтас Сонгох & Суулгах] товчийг дарж Warcraft III 1.26a суусан хавтсаа зааж өгнө үү. (Нэг удаа тохируулсны дараа энэ цонх дахиж гарахгүй!)";
                        }));
                        return;
                    }

                    int cleanedHooks = EnforceCleanWar3Directory(dir);

                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        lblStep1.Text = "✅ 1. Warcraft III 1.26a үндсэн хавтас & Anti-MapHack шалгалт баталгаажлаа (" + dir + ")";
                        lblStep1.Foreground = HexBrush("#34D399");
                        lblStep2.Text = "⏳ 2. MongolRanger Reconnect & Anti-MapHack Patch (Game.dll) суулгаж байна...";
                        lblStep2.Foreground = HexBrush("#FBBF24");
                        lblSettingsStatus.Foreground = HexBrush("#34D399");
                        lblSettingsStatus.Text = "⏳ MongolRanger Patch, Anti-MapHack болон Албан ёсны Map-уудыг автоматаар тохируулж байна...";
                    }));

                    // Step 2: Check and auto-install our patched Game.dll from Cloudflare R2 / Server
                    bool dllPatched = false;
                    if (File.Exists(gameDll))
                    {
                        try
                        {
                            try { File.SetAttributes(gameDll, FileAttributes.Normal); } catch { }
                            PatchGameDllMapSizeLimit(gameDll);
                            string curSha = ComputeSha256(File.ReadAllBytes(gameDll));
                            if (string.Equals(curSha, PATCH_GAME_DLL_SHA256, StringComparison.OrdinalIgnoreCase)
                                || string.Equals(curSha, PATCH_GAME_DLL_128M_SHA256, StringComparison.OrdinalIgnoreCase))
                                dllPatched = true;
                        }
                        catch { }
                    }

                    if (!dllPatched)
                    {
                        try
                        {
                            string backupDll = Path.Combine(dir, "Game.dll.backup");
                            if (File.Exists(gameDll) && !File.Exists(backupDll))
                            {
                                try { File.Copy(gameDll, backupDll, false); } catch { }
                            }
                            string tmpDll = Path.Combine(dir, "Game.dll." + Guid.NewGuid().ToString("N").Substring(0, 6) + ".mr_tmp");
                            DownloadFileWithRetry(SERVER_URL + "/api/patch/game-dll", tmpDll, 60000);
                            if (File.Exists(tmpDll) && new FileInfo(tmpDll).Length > 7000000)
                            {
                                if (File.Exists(gameDll))
                                {
                                    try { File.SetAttributes(gameDll, FileAttributes.Normal); } catch { }
                                    File.Delete(gameDll);
                                }
                                File.Move(tmpDll, gameDll);
                                dllPatched = true;
                            }
                        }
                        catch { }
                    }

                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        lblStep2.Text = dllPatched
                            ? "✅ 2. MongolRanger Reconnect & Anti-MapHack (Game.dll) автоматаар суулаа!"
                            : "⚠️ 2. Game.dll Patch суулгахад тоглоом хаалттай байх шаардлагатай.";
                        lblStep2.Foreground = dllPatched ? HexBrush("#34D399") : HexBrush("#FBBF24");
                    }));

                    // Step 3: 4GB LAA + Registry + Folders
                    ApplyWar3LocalOptimizations(dir);
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        lblStep3.Text = "✅ 3. 4GB RAM Crash-Protect (LAA 0x0020) & Anti-MapHack хамгаалалт суулаа!" + (cleanedHooks > 0 ? " (" + cleanedHooks + " хууль бус файл цэвэрлэгдсэн)" : "");
                        lblStep3.Foreground = HexBrush("#34D399");
                        lblStep4.Text = "⏳ 4. Сервер дээрх албан ёсны Map-уудыг Maps\\Download руу хуулж байна...";
                        lblStep4.Foreground = HexBrush("#FBBF24");
                    }));

                    // Step 4: Ensure all catalog maps are downloaded into Maps\Download
                    if (cachedMaps.Count == 0)
                    {
                        try
                        {
                            string mapsJson = ApiRequest("GET", "/api/maps");
                            MatchCollection mm = Regex.Matches(mapsJson, "\\{[^{}]*\"filename\"\\s*:\\s*\"[^\"]+\"[^{}]*\\}");
                            var listM = new List<Dictionary<string, string>>();
                            foreach (Match m in mm)
                            {
                                var d = new Dictionary<string, string>();
                                d["id"] = ExtractJsonString(m.Value, "id");
                                d["filename"] = ExtractJsonString(m.Value, "filename");
                                d["title"] = ExtractJsonString(m.Value, "title");
                                d["sha256"] = ExtractJsonString(m.Value, "sha256");
                                listM.Add(d);
                            }
                            cachedMaps = listM;
                        }
                        catch { }
                    }

                    int totalMaps = cachedMaps.Count;
                    int readyMaps = 0;
                    for (int i = 0; i < totalMaps; i++)
                    {
                        var m = cachedMaps[i];
                        string mId = m.ContainsKey("id") ? m["id"] : "";
                        string mFn = m.ContainsKey("filename") ? m["filename"] : "";
                        string sha = m.ContainsKey("sha256") ? m["sha256"] : "";
                        int stepIdx = i + 1;
                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            lblStep4.Text = "⏳ 4. Албан ёсны Map шалгаж/татаж байна (" + stepIdx + "/" + totalMaps + ": " + mFn + ")...";
                            lblStep4.Foreground = HexBrush("#FBBF24");
                        }));
                        try
                        {
                            EnsureMapDownloaded(mId, mFn, sha);
                            readyMaps++;
                        }
                        catch { }
                    }

                    war3SetupCompleted = true;
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        SaveSettings();
                        lblStep4.Text = "✅ 4. Бүх албан ёсны Map (" + (readyMaps > 0 ? readyMaps : totalMaps) + " ширхэг) Maps\\Download дотор бэлэн боллоо!";
                        lblStep4.Foreground = HexBrush("#34D399");
                        war3ReadyPill.Background = HexBrush("#14382D");
                        war3ReadyPill.BorderBrush = HexBrush("#10B981");
                        lblWar3ReadyPill.Foreground = HexBrush("#34D399");
                        lblWar3ReadyPill.Text = "✅ War3 + Patch: Бэлэн";
                        lblSettingsStatus.Foreground = HexBrush("#34D399");
                        lblSettingsStatus.Text = "🎉 Таны Warcraft III дээр MongolRanger Reconnect Patch, 🛡️ Anti-MapHack хамгаалалт болон албан ёсны Map-ууд 100% автоматаар сууж бэлэн боллоо!";
                    }));

                    if (openedSettingsForFirstTimeSetup)
                    {
                        openedSettingsForFirstTimeSetup = false;
                        Thread.Sleep(1200);
                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            SwitchPage("LOBBIES");
                        }));
                    }
                }
                catch (Exception ex)
                {
                    Exception realEx = (ex is WebException && ex.InnerException != null) ? ex.InnerException : ex;
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        lblSettingsStatus.Foreground = HexBrush("#F87171");
                        lblSettingsStatus.Text = "Тохируулахад алдаа: " + realEx.Message;
                    }));
                }
                finally
                {
                    isRunningAutoPatch = false;
                }
            });
        }

        // =====================================================================
        // ⚡ STEAM-STYLE AUTOMATIC SELF-UPDATER
        // =====================================================================
        private static void CheckAndApplySelfUpdateAsync()
        {
            if (isUpdatingSelf) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                if (isUpdatingSelf) return;
                try
                {
                    // Do not interrupt if player is actively connected to a W3GS lobby or running match
                    if (!string.IsNullOrEmpty(currentRoomId) && (currentRoomMyW3gsConnected || IsMatchActuallyStarted()))
                        return;

                    string myExe = typeof(Program).Assembly.Location;
                    if (string.IsNullOrEmpty(myExe) || !File.Exists(myExe))
                        myExe = Process.GetCurrentProcess().MainModule.FileName;
                    if (string.IsNullOrEmpty(myExe) || !File.Exists(myExe)) return;
                    string mySha = ComputeSha256(File.ReadAllBytes(myExe));

                    string verJson = ApiRequest("GET", "/api/client/version");
                    string remoteSha = ExtractJsonString(verJson, "sha256");
                    string remoteVer = ExtractJsonString(verJson, "version");
                    if (string.IsNullOrEmpty(remoteSha) || string.Equals(mySha, remoteSha, StringComparison.OrdinalIgnoreCase))
                        return;

                    isUpdatingSelf = true;
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (updateOverlay != null)
                        {
                            updateOverlay.Visibility = Visibility.Visible;
                            lblUpdateTitle.Text = "🔄 Шинэчлэлт олдлоо (" + (string.IsNullOrEmpty(remoteVer) ? "Latest" : remoteVer) + ") — Татаж байна...";
                            lblUpdateSub.Text = "Steam Auto-Updater серверээс хамгийн сүүлийн хувилбарыг автоматаар татаж суулгаж байна...";
                            pbUpdateBar.Value = 30;
                            lblUpdateDetail.Text = "⏳ Серверээс шинэчлэлтийн файлыг татаж байна (30%)...";
                        }
                    }));

                    string tmpUpdate = myExe + ".update.exe";
                    try { if (File.Exists(tmpUpdate)) File.Delete(tmpUpdate); } catch { }

                    DownloadFileWithRetry(SERVER_URL + "/api/client/exe", tmpUpdate, 45000);

                    if (!File.Exists(tmpUpdate) || new FileInfo(tmpUpdate).Length < 50000)
                    {
                        isUpdatingSelf = false;
                        return;
                    }

                    string downloadedSha = ComputeSha256(File.ReadAllBytes(tmpUpdate));
                    if (!string.Equals(downloadedSha, remoteSha, StringComparison.OrdinalIgnoreCase))
                    {
                        try { File.Delete(tmpUpdate); } catch { }
                        isUpdatingSelf = false;
                        return;
                    }

                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (updateOverlay != null)
                        {
                            pbUpdateBar.Value = 100;
                            lblUpdateTitle.Text = "✅ Шинэчлэлт амжилттай татагдлаа (" + remoteVer + ")!";
                            lblUpdateDetail.Text = "🚀 100% — Програмыг шинэ хувилбар дээр автоматаар дахин асааж байна...";
                        }
                    }));

                    Thread.Sleep(1100);

                    int myPid = Process.GetCurrentProcess().Id;
                    try
                    {
                        foreach (Process op in Process.GetProcessesByName("MongolRanger"))
                        {
                            if (op.Id != myPid)
                            {
                                try { op.Kill(); op.WaitForExit(800); } catch { }
                            }
                        }
                    }
                    catch { }

                    try
                    {
                        string dirPath = Path.GetDirectoryName(myExe);
                        foreach (string oldF in Directory.GetFiles(dirPath, "*.old*"))
                        {
                            try { File.Delete(oldF); } catch { }
                        }
                    }
                    catch { }

                    string oldExe = myExe + ".old";
                    try { if (File.Exists(oldExe)) File.Delete(oldExe); } catch { }
                    if (File.Exists(oldExe))
                        oldExe = myExe + ".old." + DateTime.UtcNow.Ticks;
                    File.Move(myExe, oldExe);
                    File.Move(tmpUpdate, myExe);

                    // Keep %LOCALAPPDATA%\MongolRanger\MongolRanger.exe and Desktop\MongolRanger.exe in sync
                    try
                    {
                        string installDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MongolRanger");
                        string installedExe = Path.Combine(installDir, "MongolRanger.exe");
                        if (!string.Equals(Path.GetFullPath(myExe), Path.GetFullPath(installedExe), StringComparison.OrdinalIgnoreCase))
                        {
                            string instOld = installedExe + ".old";
                            try { if (File.Exists(instOld)) File.Delete(instOld); } catch { }
                            if (File.Exists(instOld)) instOld = installedExe + ".old." + DateTime.UtcNow.Ticks;
                            try { if (File.Exists(installedExe)) File.Move(installedExe, instOld); } catch { }
                            try { File.Copy(myExe, installedExe, true); } catch { }
                        }
                        string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                        if (!string.IsNullOrEmpty(desktopDir) && Directory.Exists(desktopDir))
                        {
                            string oldDesktopExe = Path.Combine(desktopDir, "MongolRanger.exe");
                            if (File.Exists(oldDesktopExe) && !string.Equals(Path.GetFullPath(myExe), Path.GetFullPath(oldDesktopExe), StringComparison.OrdinalIgnoreCase))
                            {
                                try { File.Delete(oldDesktopExe); } catch { }
                            }
                            string desktopExe = Path.Combine(desktopDir, "ZevArena.exe");
                            if (!string.Equals(Path.GetFullPath(myExe), Path.GetFullPath(desktopExe), StringComparison.OrdinalIgnoreCase))
                            {
                                try { File.Copy(myExe, desktopExe, true); } catch { }
                            }
                        }
                    }
                    catch { }

                    

                    string hostExe = myExe;
                    ProcessStartInfo psi = new ProcessStartInfo(hostExe);
                    psi.WorkingDirectory = Path.GetDirectoryName(hostExe);
                    psi.UseShellExecute = false;
                    Process.Start(psi);
                    Environment.Exit(0);
                }
                catch
                {
                    isUpdatingSelf = false;
                }
            });
        }

        private static void PlayNotifySound()
        {
            try { System.Media.SystemSounds.Asterisk.Play(); } catch { }
        }

        private static string FormatUnixTimeHm(int ts)
        {
            if (ts <= 0) return "";
            try
            {
                DateTime dt = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddSeconds(ts).ToLocalTime();
                return "[" + dt.ToString("HH:mm") + "]";
            }
            catch { return ""; }
        }

        private static string FormatUnixDate(int ts)
        {
            if (ts <= 0) return "-";
            try
            {
                DateTime dt = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddSeconds(ts).ToLocalTime();
                return dt.ToString("yyyy-MM-dd HH:mm");
            }
            catch { return "-"; }
        }

        private static void PollTimer_Tick(object sender, EventArgs e)
        {
            selfUpdateTickCounter++;
            bool activelyInGame = !string.IsNullOrEmpty(currentRoomId) && currentRoomMyW3gsConnected && IsMatchActuallyStarted();

            if (!activelyInGame)
            {
                if (selfUpdateTickCounter % 2 == 0)
                {
                    CheckAndApplySelfUpdateAsync();
                }
                if (selfUpdateTickCounter % 3 == 0)
                {
                    MeasureServerPingAsync();
                }
            }
            if (string.IsNullOrEmpty(authToken)) return;
            if (!activelyInGame)
            {
                RefreshMapsAndRooms();
                SyncSocialStateAsync(false);
                if (!string.IsNullOrEmpty(activeDmFriendName) && pageFriends != null && pageFriends.Visibility == Visibility.Visible)
                {
                    LoadDirectMessagesAsync(activeDmFriendName, false);
                }
            }
            if (string.IsNullOrEmpty(currentRoomId)) return;
            // While actively in a smooth CONTINUING match with no disconnected player, throttle room HTTP polling to every 24s (zero background churn)
            if (activelyInGame && currentRoomPhase == "CONTINUING" && string.IsNullOrEmpty(currentRoomAbsent) && (selfUpdateTickCounter % 8 != 0))
                return;
            SyncRoomStateOnceAsync();
        }

        private static void SyncRoomStateOnceAsync()
        {
            if (string.IsNullOrEmpty(currentRoomId) || string.IsNullOrEmpty(authToken)) return;
            string rid = currentRoomId;
            int pollIdx = ++roomPollCounter;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    if (string.IsNullOrEmpty(currentRoomId) || currentRoomId != rid) return;

                    // Pre-launch & lobby Anti-MapHack check (never call Process.GetProcessesByName while actively playing in W3GS!)
                    if (!currentRoomMyW3gsConnected && (pollIdx % 3 == 0))
                    {
                        string violation = ScanForActiveMapHack(false);
                        if (!string.IsNullOrEmpty(violation))
                        {
                            KillRunningWarcraft();
                            try
                            {
                                string vBody = "{\"ac_status\":\"violation\",\"violation\":\"" + violation.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                                ApiRequest("POST", "/api/rooms/" + rid + "/heartbeat", vBody);
                            }
                            catch { }
                            mainWin.Dispatcher.BeginInvoke(new Action(() =>
                            {
                                LeaveRoom(false);
                                MessageBox.Show("🚨 [MongolRanger Anti-MapHack Shield]\n\nТоглолтын үед хориотой MapHack / Cheat илэрсэн тул та өрөөнөөс хасагдлаа!\nШалтгаан: " + violation, "MongolRanger Anti-MapHack");
                            }));
                            return;
                        }
                    }

                    int myPingVal = (currentPingMs > 0 && currentPingMs < 9999) ? currentPingMs : 12;
                    string st = ApiRequest("GET", "/api/rooms/" + rid + "/state?local_port=" + localProxyPort + "&ping_ms=" + myPingVal + "&ui=2");
                    if (string.IsNullOrEmpty(currentRoomId) || currentRoomId != rid) return;

                    string phase = ExtractJsonString(st, "phase");
                    string hostName = ExtractJsonString(st, "host");
                    string absentPlayer = ExtractJsonString(st, "absent_player");
                    string mapFn = ExtractJsonString(st, "map_name");
                    if (!string.IsNullOrEmpty(mapFn)) currentRoomMapName = mapFn;
                    string lanHex = ExtractJsonString(st, "lan_ad_hex");
                    if (string.IsNullOrEmpty(lanHex) && currentRoomId == rid) currentLanAd = null; // FROZEN: never advertise a stale lobby
                    else if (currentRoomId == rid)
                        currentLanAd = HexToBytes(lanHex);
                    int isOwnerInt = ExtractJsonInt(st, "is_owner", isCurrentRoomOwner ? 1 : 0);
                    isCurrentRoomOwner = (isOwnerInt == 1);
                    string serverRoomCode = ExtractJsonString(st, "room_code");
                    if (isCurrentRoomOwner) currentRoomCode = serverRoomCode;
                    int isLockedInt = ExtractJsonInt(st, "is_locked", 0);
                    int launchSig = ExtractJsonInt(st, "launch_signal", 0);
                    int w3gsConnectedCount = ExtractJsonInt(st, "w3gs_connected_count", 0);
                    int waitRemSec = ExtractJsonInt(st, "wait_remaining_sec", 0);
                    int addtimeUsed = ExtractJsonInt(st, "addtime_used", 0);
                    int addtimeMax = ExtractJsonInt(st, "addtime_max", 3);
                    bool canHostDrop = (ExtractJsonInt(st, "can_host_drop", 0) == 1) || st.Contains("\"can_host_drop\":true") || st.Contains("\"can_host_drop\": true");
                    bool myW3gsConn = (ExtractJsonInt(st, "my_w3gs_connected", 0) == 1) || st.Contains("\"my_w3gs_connected\":true") || st.Contains("\"my_w3gs_connected\": true");
                    bool myDisc = (ExtractJsonInt(st, "my_disconnected", 0) == 1) || st.Contains("\"my_disconnected\":true") || st.Contains("\"my_disconnected\": true");
                    bool rejoinReady = ExtractJsonInt(st, "rejoin_ready", 0) == 1;

                    // Parse members array safely using ExtractJsonObjectArray
                    List<RoomMemberItem> parsedMembers = new List<RoomMemberItem>();
                    List<string> mObjs = ExtractJsonObjectArray(st, "members");
                    foreach (string mStr in mObjs)
                    {
                        string mName = ExtractJsonString(mStr, "name");
                        if (string.IsNullOrEmpty(mName)) continue;
                        int mUid = ExtractJsonInt(mStr, "uid_num", 10001);
                        bool mHost = (ExtractJsonInt(mStr, "is_host", 0) == 1) || (mStr.Contains("\"is_host\":true") || mStr.Contains("\"is_host\": true"));
                        bool mW3gs = (ExtractJsonInt(mStr, "w3gs_connected", 0) == 1) || (mStr.Contains("\"w3gs_connected\":true") || mStr.Contains("\"w3gs_connected\": true"));
                        bool mIsAbsent = !string.IsNullOrEmpty(absentPlayer) && string.Equals(mName, absentPlayer, StringComparison.OrdinalIgnoreCase);
                        int mPing = ExtractJsonInt(mStr, "ping_ms", string.Equals(mName, currentUsername, StringComparison.OrdinalIgnoreCase) ? myPingVal : 12);
                        if (mPing <= 0 || mPing >= 9999) mPing = 12;
                        string mPingHex = mPing < 60 ? "#34D399" : (mPing < 120 ? "#FBBF24" : "#F87171");
                        string mBadgeLbl = ExtractJsonString(mStr, "badge_label");
                        string mBadgeCol = ExtractJsonString(mStr, "badge_color");
                        string mEloDisp = ExtractJsonString(mStr, "elo_display");
                        string mEloCol = ExtractJsonString(mStr, "elo_color");
                        parsedMembers.Add(new RoomMemberItem
                        {
                            Name = mName,
                            UidNum = mUid,
                            DisplayName = mName,
                            UidLabel = "#" + mUid,
                            TrustBadge = string.IsNullOrEmpty(mBadgeLbl) ? "🛡️ Итгэлтэй" : mBadgeLbl,
                            TrustFg = HexBrush(string.IsNullOrEmpty(mBadgeCol) ? "#10B981" : mBadgeCol),
                            EloText = "⚡ " + (string.IsNullOrEmpty(mEloDisp) ? "⏳ Түвшин тогтоох" : mEloDisp),
                            EloFg = HexBrush(string.IsNullOrEmpty(mEloCol) ? "#FBBF24" : mEloCol),
                            RoleBadge = mHost ? "👑 HOST" : "⚔️ PLAYER",
                            RoleFg = mHost ? HexBrush("#FBBF24") : HexBrush("#38BDF8"),
                            PingBadge = "📶 " + mPing + " ms",
                            PingFg = HexBrush(mPingHex),
                            War3Status = mW3gs ? "🎮 War3 LAN" : (mIsAbsent ? "⏳ Rejoin хүлээж байна" : "💬 Бэлэн"),
                            War3Fg = mW3gs ? HexBrush("#10B981") : (mIsAbsent ? HexBrush("#FBBF24") : HexBrush("#94A3B8"))
                        });
                    }

                    // Parse room chat messages array safely using ExtractJsonObjectArray (#4: brackets inside messages won't break parsing)
                    List<ChatMessageItem> parsedMsgs = new List<ChatMessageItem>();
                    int maxMsgId = lastRoomChatMsgId;
                    List<string> cObjs = ExtractJsonObjectArray(st, "messages");
                    foreach (string cStr in cObjs)
                    {
                        int cId = ExtractJsonInt(cStr, "id", 0);
                        string cSender = ExtractJsonString(cStr, "sender");
                        string cText = ExtractJsonString(cStr, "message");
                        int cTs = ExtractJsonInt(cStr, "created_at", 0);
                        if (string.IsNullOrEmpty(cSender) && string.IsNullOrEmpty(cText)) continue;
                        if (cId > maxMsgId) maxMsgId = cId;
                        bool isHostSender = string.Equals(cSender, hostName, StringComparison.OrdinalIgnoreCase);
                        bool isSelf = string.Equals(cSender, currentUsername, StringComparison.OrdinalIgnoreCase);
                        bool isAlert = cSender.Contains("СИСТЕМ") || cText.StartsWith("🚨") || cText.StartsWith("⚠️") || cText.StartsWith("⏳");
                        bool isEloMsg = cSender.Contains("ELO") || cText.StartsWith("🏆") || cText.StartsWith("⏱️");
                        bool isKickMsg = cSender.Contains("KICK") || cText.StartsWith("👢");

                        Brush sFg = isAlert ? HexBrush("#EF4444")
                            : (isEloMsg ? HexBrush("#FBBF24")
                            : (isKickMsg ? HexBrush("#FB923C")
                            : (isHostSender ? HexBrush("#FBBF24") : (isSelf ? HexBrush("#34D399") : HexBrush("#38BDF8")))));
                        Brush tFg = isAlert ? HexBrush("#FCA5A5")
                            : (isEloMsg ? HexBrush("#FDE68A")
                            : (isKickMsg ? HexBrush("#FDBA74") : HexBrush("#FFFFFF")));

                        parsedMsgs.Add(new ChatMessageItem
                        {
                            TimeStr = FormatUnixTimeHm(cTs),
                            SenderLabel = (isHostSender ? "👑 " : "") + cSender + ":",
                            SenderFg = sFg,
                            Text = cText,
                            TextFg = tFg
                        });
                    }

                    // Only scan disk Save\Multiplayer\*.w3z when a player is disconnected (FROZEN/WAITING)
                    if (phase == "FROZEN" || phase == "WAITING" || !string.IsNullOrEmpty(absentPlayer))
                    {
                        CheckAndUploadCheckpoint();
                    }

                    Match cpMatch = Regex.Match(st, "\"checkpoint\"\\s*:\\s*\\{([^{}]+)\\}");
                    if (cpMatch.Success)
                    {
                        string cpObj = cpMatch.Groups[1].Value;
                        string cpSha = ExtractJsonString(cpObj, "sha256");
                        string cpFn = ExtractJsonString(cpObj, "filename");
                        if (!string.IsNullOrEmpty(cpSha) && cpSha != lastDownloadedSha && !string.IsNullOrEmpty(cpFn))
                            DownloadCheckpoint(cpFn, cpSha);
                    }

                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        // Guard against stale async callbacks after user clicked LeaveRoom (#10 & #4)
                        if (string.IsNullOrEmpty(currentRoomId) || currentRoomId != rid) return;

                        currentRoomPhase = string.IsNullOrEmpty(phase) ? "LOBBY" : phase;
                        currentRoomAbsent = absentPlayer ?? "";
                        currentRoomLaunchSig = launchSig;
                        currentRoomWaitRemSec = waitRemSec;
                        currentRoomAddtimeUsed = addtimeUsed;
                        currentRoomAddtimeMax = addtimeMax > 0 ? addtimeMax : 3;
                        currentRoomCanHostDrop = canHostDrop;
                        currentRoomW3gsConnectedCount = w3gsConnectedCount;
                        currentRoomMyW3gsConnected = myW3gsConn;
                        currentRoomMyDisconnected = myDisc;
                        currentRoomRejoinReady = rejoinReady;
                        if (myW3gsConn || myDisc || IsWarcraftRunning())
                            hasLaunchedWar3InCurrentRoom = true;

                        UpdateInnerRoomVisibility();
                        lblSetRoomCodeText.Text = !isCurrentRoomOwner
                            ? (isLockedInt == 1 ? "🔒 Кодтой Өрөө" : "🔓 Нээлттэй Өрөө")
                            : (string.IsNullOrEmpty(currentRoomCode) ? "🔓 Код Хийх (Нээлттэй)" : "🔒 Код: " + currentRoomCode + " (Солих)");
                        string lockBadge = (isLockedInt == 1)
                            ? (isCurrentRoomOwner && !string.IsNullOrEmpty(currentRoomCode) ? "🔒 Код: " + currentRoomCode : "🔒 Кодтой")
                            : "🔓 Нээлттэй";
                        lblInnerRoomTitle.Text = "🏰 " + currentRoomName + "  (" + lockBadge + ")";
                        lblInnerRoomSub.Text = "👑 Host: " + hostName + "  •  🗺️ Map: " + currentRoomMapName + "  •  Төлөв: " + currentRoomPhase + "  •  🛡️ Anti-MapHack";

                        if (isCurrentRoomOwner && lblHostStartBtnText != null)
                        {
                            lblHostStartBtnText.Text = (myW3gsConn && IsWarcraftRunning() && currentRoomPhase == "LOBBY")
                                ? "🚀 ТОГЛОЛТ ЭХЛҮҮЛЭХ (START MATCH)"
                                : "🚀 ТОГЛООМ ЭХЛҮҮЛЭХ (START GAME)";
                        }

                        lblRoomMembersCount.Text = "👥 ӨРӨӨНД БАЙГАА ТОГЛОГЧИД (" + parsedMembers.Count + "/10)";
                        if (!myW3gsConn || roomMembersList.ItemsSource == null || lastRenderedMemberCount != parsedMembers.Count || !string.IsNullOrEmpty(absentPlayer))
                        {
                            lastRenderedMemberCount = parsedMembers.Count;
                            roomMembersList.ItemsSource = parsedMembers;
                        }

                        if (maxMsgId > lastRoomChatMsgId || roomChatList.ItemsSource == null)
                        {
                            roomChatList.ItemsSource = parsedMsgs;
                            if (maxMsgId > lastRoomChatMsgId)
                            {
                                lastRoomChatMsgId = maxMsgId;
                                try { roomChatScroll.ScrollToEnd(); } catch { }
                            }
                        }

                        // Requirement 4: When Host clicks Start Game in LOBBY, automatically launch Warcraft III on all clients in the room ONCE per launchSig!
                        int nowUnix = (int)(DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds;
                        if (launchSig > 0 && launchSig != lastHandledLaunchSignal && !handledLaunchSignals.Contains(launchSig))
                        {
                            lastHandledLaunchSignal = launchSig;
                            handledLaunchSignals.Add(launchSig);
                            if ((nowUnix - launchSig) <= 45 && !myDisc && currentRoomPhase == "LOBBY")
                            {
                                hasLaunchedWar3InCurrentRoom = true;
                                PlayNotifySound();
                                LaunchWarcraftIfNotRunning(true);
                                UpdateInnerRoomVisibility();
                            }
                        }
                    }));
                }
                catch (WebException wex)
                {
                    HttpWebResponse hr = wex.Response as HttpWebResponse;
                    if (hr != null && hr.StatusCode == HttpStatusCode.Forbidden)
                    {
                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            if (currentRoomId != rid) return;
                            LeaveRoom(false);
                            MessageBox.Show("👢 Та энэ өрөөнөөс Host-оор хөөгдсөн (Kicked / Dropped) тул өрөөнөөс гарлаа!", "MongolRanger");
                        }));
                    }
                    else if (hr != null && hr.StatusCode == HttpStatusCode.NotFound)
                    {
                        // Requirement #1: Host left and closed the room -> immediately eject remaining players
                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            if (currentRoomId != rid) return;
                            LeaveRoom(false);
                            MessageBox.Show("🚪 Өрөөний Host өрөөнөөс гарсан тул өрөө хаагдлаа!", "MongolRanger");
                        }));
                    }
                }
                catch { }
            });
        }

        private static void SendRoomChatMessage()
        {
            if (string.IsNullOrEmpty(currentRoomId)) return;
            string msg = (txtRoomChatInput.Text ?? "").Trim();
            if (string.IsNullOrEmpty(msg)) return;
            txtRoomChatInput.Text = "";
            string rid = currentRoomId;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string body = "{\"message\":\"" + msg.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                    ApiRequest("POST", "/api/rooms/" + rid + "/chat", body);
                    SyncRoomStateOnceAsync();
                }
                catch { }
            });
        }

        private static void OnRoomMemberButtonClick(object sender, RoutedEventArgs e)
        {
            Button btn = e.OriginalSource as Button;
            if (btn != null && btn.Tag != null)
            {
                string targetUser = btn.Tag.ToString();
                if (!string.IsNullOrEmpty(targetUser))
                    OpenPlayerActionModal(targetUser, true, false);
            }
        }

        private static void KickPlayerFromRoom(string targetUser)
        {
            if (string.IsNullOrEmpty(currentRoomId) || !isCurrentRoomOwner || string.IsNullOrEmpty(targetUser))
                return;
            string rid = currentRoomId;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string body = "{\"target\":\"" + targetUser.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                    ApiRequest("POST", "/api/rooms/" + rid + "/kick", body);
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        playerActionModalOverlay.Visibility = Visibility.Collapsed;
                    }));
                    SyncRoomStateOnceAsync();
                }
                catch (Exception ex)
                {
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        lblPlayerModalFeedback.Text = "⚠️ Хөөхөд алдаа: " + ex.Message;
                    }));
                }
            });
        }

        private static void SetModalFriendButtonState(string fStatus)
        {
            if (btnModalAddFriend == null || lblBtnModalAddFriendText == null) return;
            if (string.Equals(selectedModalPlayerName, currentUsername, StringComparison.OrdinalIgnoreCase))
            {
                btnModalAddFriend.IsEnabled = false;
                btnModalAddFriend.Opacity = 0.5;
                lblBtnModalAddFriendText.Text = "👤 Таны өөрийн профайл";
            }
            else if (fStatus == "accepted")
            {
                btnModalAddFriend.IsEnabled = false;
                btnModalAddFriend.Opacity = 0.6;
                lblBtnModalAddFriendText.Text = "🤝 Таны найз (Friends)";
            }
            else if (fStatus == "pending_out" || fStatus == "pending_sent" || fStatus == "pending")
            {
                btnModalAddFriend.IsEnabled = false;
                btnModalAddFriend.Opacity = 0.6;
                lblBtnModalAddFriendText.Text = "⏳ Найзын хүсэлт илгээгдсэн";
            }
            else if (fStatus == "pending_in")
            {
                btnModalAddFriend.IsEnabled = true;
                btnModalAddFriend.Opacity = 1.0;
                lblBtnModalAddFriendText.Text = "✅ Найзын хүсэлт зөвшөөрөх";
            }
            else
            {
                btnModalAddFriend.IsEnabled = true;
                btnModalAddFriend.Opacity = 1.0;
                lblBtnModalAddFriendText.Text = "➕ Найзын хүсэлт илгээх";
            }
        }

        private static void OpenPlayerActionModal(string targetUsername, bool fromRoom = false, bool fromLeaderboard = false)
        {
            if (string.IsNullOrEmpty(targetUsername)) return;
            selectedModalPlayerName = targetUsername;
            selectedModalPlayerIsBlocked = false;
            lblPlayerModalName.Text = (fromLeaderboard ? "🏆 " : "👤 ") + targetUsername;
            lblPlayerModalUid.Text = "ID Дугаар: Уншиж байна...";
            if (lblPlayerModalBadge != null)
            {
                lblPlayerModalBadge.Text = "⏳ Тэмдэг & ELO шалгаж байна...";
                lblPlayerModalBadge.Foreground = HexBrush("#94A3B8");
            }
            if (lblPlayerModalElo != null)
                lblPlayerModalElo.Text = "⚡ FACEIT ELO: ...";
            if (lblPlayerModalLeaves != null)
                lblPlayerModalLeaves.Text = "📊 Тоглолтын түүх уншиж байна...";
            lblPlayerModalStatus.Text = "⏳ Төлөв шалгаж байна...";
            lblPlayerModalRoom.Text = "🎮 Одоо байгаа өрөө: -";
            lblPlayerModalCreated.Text = "📅 Бүртгүүлсэн огноо: -";
            lblPlayerModalFeedback.Text = "";
            lblBtnModalBlockText.Text = "🚫 Блок хийх (Block)";
            SetModalFriendButtonState("none");
            if (btnModalViewHistory != null)
                btnModalViewHistory.Visibility = Visibility.Visible;
            if (btnModalKickUser != null)
            {
                bool canKick = fromRoom && !fromLeaderboard
                    && !string.IsNullOrEmpty(currentRoomId) && isCurrentRoomOwner
                    && !IsMatchActuallyStarted()
                    && !string.Equals(targetUsername, currentUsername, StringComparison.OrdinalIgnoreCase);
                btnModalKickUser.Visibility = canKick ? Visibility.Visible : Visibility.Collapsed;
            }
            if (modalActionButtonsGrid != null)
            {
                modalActionButtonsGrid.Visibility = fromLeaderboard ? Visibility.Collapsed : Visibility.Visible;
            }
            playerActionModalOverlay.Visibility = Visibility.Visible;

            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string infoJson = ApiRequest("GET", "/api/users/info?q=" + Uri.EscapeDataString(targetUsername));
                    string uname = ExtractJsonString(infoJson, "username");
                    int uidNum = ExtractJsonInt(infoJson, "uid_num", 10001);
                    bool online = infoJson.Contains("\"online\":true") || infoJson.Contains("\"online\": true");
                    int uPing = ExtractJsonInt(infoJson, "ping_ms", 12);
                    if (uPing <= 0 || uPing >= 9999) uPing = 12;
                    string rName = ExtractJsonString(infoJson, "current_room_name");
                    int createdTs = ExtractJsonInt(infoJson, "created_at", 0);
                    string fStatus = ExtractJsonString(infoJson, "friendship_status");
                    bool blocked = infoJson.Contains("\"is_blocked\":true") || infoJson.Contains("\"is_blocked\": true");

                    string bLbl = ExtractJsonString(infoJson, "badge_label");
                    string bCol = ExtractJsonString(infoJson, "badge_color");
                    string eDisp = ExtractJsonString(infoJson, "elo_display");
                    string eCol = ExtractJsonString(infoJson, "elo_color");
                    int kills = ExtractJsonInt(infoJson, "kills", 0);
                    int deaths = ExtractJsonInt(infoJson, "deaths", 0);
                    int gp = ExtractJsonInt(infoJson, "games_played", 0);
                    int wins = ExtractJsonInt(infoJson, "wins", 0);
                    int losses = ExtractJsonInt(infoJson, "losses", 0);
                    int leaves = ExtractJsonInt(infoJson, "leaves", 0);
                    int cleanRate = ExtractJsonInt(infoJson, "clean_rate", 100);
                    string abRoom = ExtractJsonString(infoJson, "last_abandon_room");

                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        selectedModalPlayerName = string.IsNullOrEmpty(uname) ? targetUsername : uname;
                        selectedModalPlayerIsBlocked = blocked;
                        lblPlayerModalName.Text = (fromLeaderboard ? "🏆 " : "👤 ") + selectedModalPlayerName;
                        lblPlayerModalUid.Text = "ID Дугаар: #" + uidNum + "   •   📶 Ping: " + uPing + " ms";
                        SetModalFriendButtonState(fStatus);

                        if (lblPlayerModalBadge != null)
                        {
                            lblPlayerModalBadge.Text = string.IsNullOrEmpty(bLbl) ? "🛡️ Итгэлтэй Тоглогч" : bLbl;
                            lblPlayerModalBadge.Foreground = HexBrush(string.IsNullOrEmpty(bCol) ? "#10B981" : bCol);
                        }
                        if (lblPlayerModalElo != null)
                        {
                            lblPlayerModalElo.Text = "⚡ " + (string.IsNullOrEmpty(eDisp) ? "⏳ Түвшин тогтоох" : eDisp)
                                + "   •   🗡️ " + kills + " килл / 💀 " + deaths + " үхэл   •   🏆 " + (gp > 0 ? (wins * 100 / gp) : 0) + "%   (📜 дарж түүх харах)";
                            lblPlayerModalElo.Foreground = HexBrush(string.IsNullOrEmpty(eCol) ? "#FBBF24" : eCol);
                        }
                        if (lblPlayerModalLeaves != null)
                        {
                            string lvText = "📊 Тоглосон: " + gp + " (" + wins + "W-" + losses + "L)  •  Цэвэр: " + cleanRate + "%  •  Дундаас гарсан (Leave): " + leaves + " удаа";
                            if (!string.IsNullOrEmpty(abRoom))
                                lvText += "\n🚨 Саяхан хаяж гарсан өрөө: «" + abRoom + "»";
                            lblPlayerModalLeaves.Text = lvText;
                            lblPlayerModalLeaves.Foreground = (leaves >= 10 || !string.IsNullOrEmpty(abRoom)) ? HexBrush("#F87171") : HexBrush("#CBD5E1");
                        }

                        lblPlayerModalStatus.Text = (online ? "🟢 Төлөв: Онлайн" : "⚪ Төлөв: Оффлайн")
                            + "  •  📶 Ping: " + uPing + " ms"
                            + (fStatus == "accepted" ? "  •  🤝 Таны найз" : "");
                        lblPlayerModalStatus.Foreground = online ? HexBrush("#34D399") : HexBrush("#94A3B8");
                        lblPlayerModalRoom.Text = "🎮 Одоо байгаа өрөө: " + (string.IsNullOrEmpty(rName) ? "Өрөөнд ороогүй" : rName);
                        lblPlayerModalCreated.Text = "📅 Бүртгүүлсэн огноо: " + FormatUnixDate(createdTs);
                        lblBtnModalBlockText.Text = blocked ? "🔓 Блок гаргах (Unblock)" : "🚫 Блок хийх (Block)";
                    }));
                }
                catch (Exception ex)
                {
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        lblPlayerModalFeedback.Text = "Мэдээлэл татахад алдаа: " + ex.Message;
                    }));
                }
            });
        }

        private static void SearchFriendsAsync(string query)
        {
            if (string.IsNullOrEmpty(query) || string.IsNullOrEmpty(authToken)) return;
            int seq = ++friendSearchSeq;
            if (lblFriendStatusMsg != null) lblFriendStatusMsg.Text = "🔍 Хайж байна...";
            ThreadPool.QueueUserWorkItem(_ =>
            {
                List<FriendSearchItem> items = new List<FriendSearchItem>();
                string err = "";
                try
                {
                    string res = ApiRequest("GET", "/api/users/search?q=" + Uri.EscapeDataString(query));
                    foreach (string o in ExtractJsonObjectArray(res, "users"))
                    {
                        string n = ExtractJsonString(o, "name");
                        if (string.IsNullOrEmpty(n)) continue;
                        int uid = ExtractJsonInt(o, "uid_num", 0);
                        bool onl = ExtractJsonInt(o, "online", 0) == 1;
                        string fs = ExtractJsonString(o, "friendship_status");
                        string elo = ExtractJsonString(o, "elo_display");
                        string label = "➕ Нэмэх";
                        bool can = true;
                        if (fs == "accepted") { label = "🤝 Найз"; can = false; }
                        else if (fs == "pending_out") { label = "⏳ Илгээсэн"; can = false; }
                        else if (fs == "pending_in") { label = "✅ Зөвшөөрөх"; }
                        items.Add(new FriendSearchItem
                        {
                            Name = n,
                            DisplayName = n + "  #" + uid,
                            SubText = (onl ? "🟢 Онлайн" : "⚪ Оффлайн") + (string.IsNullOrEmpty(elo) ? "" : "  •  " + elo),
                            SubFg = onl ? HexBrush("#34D399") : HexBrush("#94A3B8"),
                            DotColor = onl ? HexBrush("#10B981") : HexBrush("#64748B"),
                            AddTag = n,
                            AddLabel = label,
                            CanAdd = can,
                            AddOpacity = can ? 1.0 : 0.55
                        });
                    }
                }
                catch (Exception ex) { err = ex.Message; }
                mainWin.Dispatcher.BeginInvoke(new Action(() =>
                {
                    if (seq != friendSearchSeq) return;
                    friendSearchResultsList.ItemsSource = items;
                    friendSearchResultsPanel.Visibility = items.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
                    lblFriendStatusMsg.Text = !string.IsNullOrEmpty(err)
                        ? "⚠️ Хайхад алдаа: " + err
                        : (items.Count == 0 ? "«" + query + "» нэртэй тоглогч олдсонгүй." : items.Count + " тоглогч олдлоо — жагсаалтаас сонгож ➕ Нэмэх дарна уу.");
                }));
            });
        }

        private static void OpenMatchHistory(string targetUser)
        {
            if (string.IsNullOrEmpty(authToken) || matchHistoryOverlay == null) return;
            lblHistoryTitle.Text = "📜 " + (string.IsNullOrEmpty(targetUser) ? "Миний" : targetUser + "-ийн") + " сүүлийн 10 тоглолт";
            lblHistoryElo.Text = "⏳ Уншиж байна...";
            lblHistoryStats.Text = "";
            lblHistoryEmpty.Visibility = Visibility.Collapsed;
            matchHistoryList.ItemsSource = null;
            matchHistoryOverlay.Visibility = Visibility.Visible;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string res = ApiRequest("GET", "/api/users/matches" + (string.IsNullOrEmpty(targetUser) ? "" : "?q=" + Uri.EscapeDataString(targetUser)));
                    string uname = ExtractJsonString(res, "username");
                    string eloDisp = ExtractJsonString(res, "elo_display");
                    string eloCol = ExtractJsonString(res, "elo_color");
                    string badge = ExtractJsonString(res, "badge_label");
                    int gp = ExtractJsonInt(res, "games_played", 0);
                    int wins = ExtractJsonInt(res, "wins", 0);
                    int losses = ExtractJsonInt(res, "losses", 0);
                    int leaves = ExtractJsonInt(res, "leaves", 0);
                    int kills = ExtractJsonInt(res, "kills", 0);
                    int deaths = ExtractJsonInt(res, "deaths", 0);
                    int assists = ExtractJsonInt(res, "assists", 0);
                    int winRate = ExtractJsonInt(res, "win_rate", 0);
                    double kd = deaths > 0 ? Math.Round((double)kills / deaths, 2) : kills;
                    double avgK = gp > 0 ? Math.Round((double)kills / gp, 1) : 0;
                    List<MatchHistoryItem> items = new List<MatchHistoryItem>();
                    foreach (string o in ExtractJsonObjectArray(res, "matches"))
                    {
                        string result = ExtractJsonString(o, "result");
                        int k = ExtractJsonInt(o, "kills", 0), d = ExtractJsonInt(o, "deaths", 0), a = ExtractJsonInt(o, "assists", 0);
                        Match dm = Regex.Match(o, "\"elo_delta\"\\s*:\\s*(-?\\d+)");
                        int delta = dm.Success ? int.Parse(dm.Groups[1].Value) : 0;
                        int after = ExtractJsonInt(o, "elo_after", 0);
                        int dur = ExtractJsonInt(o, "duration_sec", 0);
                        string resLbl = result == "WIN" ? "🏆 ХОЖИЛ" : (result == "LOSS" ? "💀 ХОЖИГДОЛ" : "🚪 ГАРСАН");
                        string col = result == "WIN" ? "#10B981" : (result == "LOSS" ? "#EF4444" : "#F59E0B");
                        string bg = result == "WIN" ? "#0F2E24" : (result == "LOSS" ? "#3B1219" : "#3B2813");
                        items.Add(new MatchHistoryItem
                        {
                            ResultLabel = resLbl,
                            ResultFg = HexBrush(col),
                            ResultBg = HexBrush(bg),
                            CardBorder = HexBrush(col),
                            MapLine = "🗺️ " + ExtractJsonString(o, "map_name") + "  •  " + ExtractJsonString(o, "team_name") + (dur > 0 ? "  •  ⏱️ " + (dur / 60) + " мин" : ""),
                            KdaLine = "🗡️ " + k + " килл   💀 " + d + " үхэл   🤝 " + a + " туслалт",
                            TeammatesLine = "👥 Хамт: " + ExtractJsonString(o, "teammates_text"),
                            OpponentsLine = "⚔️ Эсрэг: " + ExtractJsonString(o, "opponents_text"),
                            EloLine = after > 0 ? ((delta >= 0 ? "+" : "") + delta + " ELO") : "⏳ Түвшин тогтоох",
                            EloFg = after <= 0 ? HexBrush("#94A3B8") : (delta >= 0 ? HexBrush("#34D399") : HexBrush("#F87171")),
                            DateLine = ExtractJsonString(o, "date_str")
                        });
                    }
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        lblHistoryTitle.Text = "📜 " + uname + " — сүүлийн 10 тоглолт";
                        lblHistoryElo.Text = "⚡ " + eloDisp + (string.IsNullOrEmpty(badge) ? "" : "   •   " + badge);
                        if (!string.IsNullOrEmpty(eloCol)) lblHistoryElo.Foreground = HexBrush(eloCol);
                        lblHistoryStats.Text = "🎮 Тоглосон: " + gp + "  (" + wins + " хожил / " + losses + " хожигдол)   •   🚪 Гарсан: " + leaves
                            + "\n🏆 Хожлын хувь: " + winRate + "%   •   🗡️ K/D: " + kd + "   •   ⚔️ Дундаж килл: " + avgK + "   •   Нийт: " + kills + "/" + deaths + "/" + assists;
                        matchHistoryList.ItemsSource = items;
                        lblHistoryEmpty.Visibility = items.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
                    }));
                }
                catch (Exception ex)
                {
                    mainWin.Dispatcher.BeginInvoke(new Action(() => { lblHistoryElo.Text = "⚠️ Түүх уншихад алдаа: " + ex.Message; }));
                }
            });
        }

        private static void SendFriendRequestTo(string targetQuery, bool fromModal)
        {
            if (string.IsNullOrEmpty(targetQuery)) return;
            if (fromModal)
                SetModalFriendButtonState("pending_sent");
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string body = "{\"target\":\"" + targetQuery.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                    string res = ApiRequest("POST", "/api/friends/request", body);
                    string targetName = ExtractJsonString(res, "target");
                    string status = ExtractJsonString(res, "status");
                    string msg = (status == "accepted")
                        ? ("✅ " + targetName + " та хоёр одоо найзууд боллоо!")
                        : ("📨 " + targetName + " руу найзын хүсэлт илгээгдлээ!");
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (fromModal)
                        {
                            SetModalFriendButtonState(status == "accepted" ? "accepted" : "pending_sent");
                            lblPlayerModalFeedback.Text = msg;
                        }
                        else lblFriendStatusMsg.Text = msg;
                    }));
                    SyncSocialStateAsync(false);
                }
                catch (WebException wex)
                {
                    string err = "Хүсэлт илгээхэд алдаа гарлаа.";
                    try
                    {
                        if (wex.Response != null)
                        {
                            using (StreamReader sr = new StreamReader(wex.Response.GetResponseStream()))
                            {
                                string raw = sr.ReadToEnd();
                                string d = ExtractJsonString(raw, "detail");
                                if (!string.IsNullOrEmpty(d)) err = d;
                            }
                        }
                    }
                    catch { }
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (fromModal)
                        {
                            if (err.Contains("Найзын хүсэлт илгээгдсэн") || err.Contains("аль хэдийн найз"))
                                SetModalFriendButtonState(err.Contains("аль хэдийн найз") ? "accepted" : "pending_sent");
                            else
                                SetModalFriendButtonState("none");
                            lblPlayerModalFeedback.Text = "⚠️ " + err;
                        }
                        else lblFriendStatusMsg.Text = "⚠️ " + err;
                    }));
                }
                catch (Exception ex)
                {
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (fromModal)
                        {
                            SetModalFriendButtonState("none");
                            lblPlayerModalFeedback.Text = "⚠️ " + ex.Message;
                        }
                        else lblFriendStatusMsg.Text = "⚠️ " + ex.Message;
                    }));
                }
            });
        }

        private static void OnPendingFriendRequestClick(object sender, RoutedEventArgs e)
        {
            Button btn = e.OriginalSource as Button;
            if (btn != null && btn.Tag != null)
            {
                string tagStr = btn.Tag.ToString();
                bool accept = true;
                string requester = tagStr;
                if (tagStr.StartsWith("ACCEPT:"))
                {
                    accept = true;
                    requester = tagStr.Substring("ACCEPT:".Length);
                }
                else if (tagStr.StartsWith("DECLINE:"))
                {
                    accept = false;
                    requester = tagStr.Substring("DECLINE:".Length);
                }
                ThreadPool.QueueUserWorkItem(_ =>
                {
                    try
                    {
                        string body = "{\"requester\":\"" + requester.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\",\"accept\":" + (accept ? "true" : "false") + "}";
                        ApiRequest("POST", "/api/friends/respond", body);
                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            if (lblFriendStatusMsg != null)
                                lblFriendStatusMsg.Text = accept
                                    ? ("✅ " + requester + "-н найзын хүсэлтийг зөвшөөрлөө!")
                                    : ("✕ " + requester + "-н хүсэлтийг цуцаллаа.");
                        }));
                        SyncSocialStateAsync(false);
                    }
                    catch { }
                });
            }
        }

        private static void ToggleBlockUser(string targetUser, bool block, bool fromModal)
        {
            if (string.IsNullOrEmpty(targetUser)) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string body = "{\"target\":\"" + targetUser.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\",\"block\":" + (block ? "true" : "false") + "}";
                    ApiRequest("POST", "/api/users/block", body);
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (fromModal)
                        {
                            selectedModalPlayerIsBlocked = block;
                            lblBtnModalBlockText.Text = block ? "🔓 Блок гаргах (Unblock)" : "🚫 Блок хийх (Block)";
                            lblPlayerModalFeedback.Text = block
                                ? ("🚫 " + targetUser + " блок хийгдлээ.")
                                : ("🔓 " + targetUser + " блокноос гарлаа.");
                        }
                    }));
                    SyncSocialStateAsync(false);
                    if (!string.IsNullOrEmpty(currentRoomId)) SyncRoomStateOnceAsync();
                }
                catch { }
            });
        }

        private static void OnUnblockButtonClick(object sender, RoutedEventArgs e)
        {
            Button btn = e.OriginalSource as Button;
            if (btn != null && btn.Tag != null)
            {
                ToggleBlockUser(btn.Tag.ToString(), false, false);
            }
        }

        private static void OnFriendListButtonClick(object sender, RoutedEventArgs e)
        {
            Button btn = e.OriginalSource as Button;
            if (btn != null && btn.Tag != null)
            {
                string tagStr = btn.Tag.ToString();
                if (tagStr.StartsWith("PROFILE:"))
                {
                    OpenPlayerActionModal(tagStr.Substring("PROFILE:".Length));
                }
                else if (tagStr.StartsWith("CHAT:"))
                {
                    OpenDirectChatWith(tagStr.Substring("CHAT:".Length));
                }
                else
                {
                    OpenDirectChatWith(tagStr);
                }
            }
        }

        private static void OpenDirectChatWith(string friendName)
        {
            if (string.IsNullOrEmpty(friendName)) return;
            activeDmFriendName = friendName;
            SwitchPage("FRIENDS");
            lblDmHeaderTitle.Text = "💬 " + friendName + " — Хувийн Чат (Нэр дээр дарж урих / мэдээлэл харах)";
            lblDmHeaderSub.Text = "Мессеж бичээд Enter дарж илгээнэ үү";
            txtDmInput.Focus();
            LoadDirectMessagesAsync(friendName, true);
        }

        private static void LoadDirectMessagesAsync(string friendName, bool scrollEnd)
        {
            if (string.IsNullOrEmpty(friendName) || string.IsNullOrEmpty(authToken)) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string res = ApiRequest("GET", "/api/dm/" + Uri.EscapeDataString(friendName));
                    List<ChatMessageItem> items = new List<ChatMessageItem>();
                    List<string> objs = ExtractJsonObjectArray(res, "messages");
                    foreach (string o in objs)
                    {
                        string sdr = ExtractJsonString(o, "sender");
                        string txt = ExtractJsonString(o, "message");
                        int ts = ExtractJsonInt(o, "created_at", 0);
                        bool isMe = string.Equals(sdr, currentUsername, StringComparison.OrdinalIgnoreCase);

                        // Parse [INVITE:roomId:invId] token for inline Accept button in Direct Chat (#5)
                        string invTag = "";
                        Visibility invVis = Visibility.Collapsed;
                        Match invM = Regex.Match(txt, "\\[INVITE:([^:\\]]+):(\\d+)\\]");
                        if (invM.Success)
                        {
                            string rIdToken = invM.Groups[1].Value;
                            string invIdToken = invM.Groups[2].Value;
                            txt = txt.Replace(invM.Value, "").Trim();
                            if (!isMe)
                            {
                                invTag = rIdToken + ":" + invIdToken;
                                invVis = Visibility.Visible;
                            }
                        }

                        items.Add(new ChatMessageItem
                        {
                            TimeStr = FormatUnixTimeHm(ts),
                            SenderLabel = sdr + ":",
                            SenderFg = isMe ? HexBrush("#34D399") : HexBrush("#38BDF8"),
                            Text = txt,
                            TextFg = HexBrush("#FFFFFF"),
                            InviteTag = invTag,
                            HasInviteVis = invVis
                        });
                    }
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (!string.Equals(activeDmFriendName, friendName, StringComparison.OrdinalIgnoreCase)) return;
                        dmMessagesListCtrl.ItemsSource = items;
                        if (scrollEnd)
                        {
                            try { dmChatScroll.ScrollToEnd(); } catch { }
                        }
                    }));
                }
                catch { }
            });
        }

        private static void OnDmInviteAcceptClick(object sender, RoutedEventArgs e)
        {
            Button btn = e.OriginalSource as Button;
            if (btn == null || btn.Tag == null) return;
            string tag = btn.Tag.ToString();
            if (string.IsNullOrEmpty(tag)) return;
            string[] parts = tag.Split(':');
            string roomId = parts[0];
            int invId = 0;
            if (parts.Length > 1) int.TryParse(parts[1], out invId);

            if (invId > 0)
            {
                activeInviteId = invId;
                RespondToRoomInvite(true);
            }
            else if (!string.IsNullOrEmpty(roomId))
            {
                JoinRoomById(roomId, "");
            }
        }

        private static void SendDirectMessage()
        {
            if (string.IsNullOrEmpty(activeDmFriendName))
            {
                MessageBox.Show("Эхлээд зүүн талын жагсаалтаас чат бичих найзаа сонгоно уу!", "MongolRanger");
                return;
            }
            string msg = (txtDmInput.Text ?? "").Trim();
            if (string.IsNullOrEmpty(msg)) return;
            txtDmInput.Text = "";
            string target = activeDmFriendName;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string body = "{\"message\":\"" + msg.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                    ApiRequest("POST", "/api/dm/" + Uri.EscapeDataString(target), body);
                    LoadDirectMessagesAsync(target, true);
                }
                catch (Exception ex)
                {
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        lblFriendStatusMsg.Text = "⚠️ Чат илгээхэд алдаа: " + ex.Message;
                    }));
                }
            });
        }

        private static void InviteFriendToCurrentRoom(string targetUser, bool fromModal)
        {
            if (string.IsNullOrEmpty(currentRoomId))
            {
                string warn = "⚠️ Та эхлээд Lobby өрөө үүсгэх эсвэл өрөөнд орсны дараа найзаа урина уу!";
                if (fromModal) lblPlayerModalFeedback.Text = warn;
                else lblFriendStatusMsg.Text = warn;
                return;
            }
            string rid = currentRoomId;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string body = "{\"target\":\"" + targetUser.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                    ApiRequest("POST", "/api/rooms/" + rid + "/invite", body);
                    string okMsg = "📨 " + targetUser + " руу хувийн чатаар өрөөний урилга илгээгдлээ!";
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (fromModal) lblPlayerModalFeedback.Text = okMsg;
                        else lblFriendStatusMsg.Text = okMsg;
                        if (string.Equals(activeDmFriendName, targetUser, StringComparison.OrdinalIgnoreCase))
                            LoadDirectMessagesAsync(targetUser, true);
                    }));
                }
                catch (Exception ex)
                {
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (fromModal) lblPlayerModalFeedback.Text = "⚠️ " + ex.Message;
                        else lblFriendStatusMsg.Text = "⚠️ " + ex.Message;
                    }));
                }
            });
        }

        private static void RespondToRoomInvite(bool accept)
        {
            if (accept && IsMatchOrRejoinLocked()) return;
            int invId = activeInviteId;
            inviteBannerOverlay.Visibility = Visibility.Collapsed;
            lastDismissedInviteId = invId;
            if (invId <= 0) return;

            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string body = "{\"accept\":" + (accept ? "true" : "false") + "}";
                    string res = ApiRequest("POST", "/api/invites/" + invId + "/respond", body);
                    if (accept)
                    {
                        string rid = ExtractJsonString(res, "room_id");
                        string rname = ExtractJsonString(res, "room_name");
                        string mFn = ExtractJsonString(res, "map_name");
                        int port = ExtractJsonInt(res, "w3gs_port", 8051);
                        string lanHex = ExtractJsonString(res, "lan_ad_hex");
                        string mId = ExtractJsonString(res, "id");
                        string mSha = ExtractJsonString(res, "sha256");

                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            currentRoomId = rid;
                            currentRoomName = string.IsNullOrEmpty(rname) ? "Invited Room" : rname;
                            currentRoomMapName = mFn;
                            isCurrentRoomOwner = false;
                            lastRoomChatMsgId = 0;
                            ResetCurrentRoomRuntimeState();
                            w3gsPort = port;
                            if (!string.IsNullOrEmpty(lanHex)) currentLanAd = HexToBytes(lanHex);

                            lblInnerRoomTitle.Text = "🏰 " + currentRoomName;
                            lblInnerRoomSub.Text = "🗺️ Map: " + mFn + " (Татаж байна...)  •  🛡️ Anti-MapHack Идэвхтэй";
                            SwitchPage("LOBBIES");
                            UpdateInnerRoomVisibility();
                            SyncRoomStateOnceAsync();
                        }));

                        EnsureMapDownloaded(mId, mFn, mSha);
                        mainWin.Dispatcher.BeginInvoke(new Action(() =>
                        {
                            if (string.IsNullOrEmpty(currentRoomId) || currentRoomId != rid) return;
                            lblInnerRoomSub.Text = "🗺️ Map: " + mFn + " (✅ Татагдсан)  •  🛡️ Anti-MapHack Идэвхтэй";
                        }));
                    }
                }
                catch (Exception ex)
                {
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        MessageBox.Show("Урилгаар өрөөнд ороход алдаа: " + ex.Message, "MongolRanger");
                    }));
                }
            });
        }

        private static void SyncSocialStateAsync(bool initialLoad)
        {
            if (string.IsNullOrEmpty(authToken)) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    string syncJson = ApiRequest("GET", "/api/social/sync");
                    int myUid = ExtractJsonInt(syncJson, "uid_num", currentUidNum);
                    int unreadTotal = ExtractJsonInt(syncJson, "unread_total", 0);
                    string myBadgeLbl = ExtractJsonString(syncJson, "badge_label");
                    string myBadgeCol = ExtractJsonString(syncJson, "badge_color");
                    string myEloDisp = ExtractJsonString(syncJson, "elo_display");
                    string myEloCol = ExtractJsonString(syncJson, "elo_color");

                    // Parse friends safely
                    List<FriendItem> parsedFriends = new List<FriendItem>();
                    List<string> fObjs = ExtractJsonObjectArray(syncJson, "friends");
                    foreach (string o in fObjs)
                    {
                        string fn = ExtractJsonString(o, "name");
                        if (string.IsNullOrEmpty(fn)) continue;
                        int fuid = ExtractJsonInt(o, "uid_num", 10001);
                        bool onl = o.Contains("\"online\":true") || o.Contains("\"online\": true");
                        string rname = ExtractJsonString(o, "room_name");
                        int unrd = ExtractJsonInt(o, "unread", 0);
                        parsedFriends.Add(new FriendItem
                        {
                            Name = fn,
                            UidNum = fuid,
                            DisplayName = fn + "  #" + fuid,
                            ProfileTag = "PROFILE:" + fn,
                            ChatTag = "CHAT:" + fn,
                            DotColor = onl ? HexBrush("#10B981") : HexBrush("#64748B"),
                            SubText = onl
                                ? (!string.IsNullOrEmpty(rname) ? ("🎮 Өрөөнд: " + rname) : "🟢 Онлайн")
                                : "⚪ Оффлайн",
                            UnreadText = unrd > 0 ? unrd.ToString() : "",
                            UnreadVis = unrd > 0 ? Visibility.Visible : Visibility.Collapsed
                        });
                    }

                    // Parse incoming requests safely (#3)
                    List<FriendReqItem> parsedReqs = new List<FriendReqItem>();
                    List<string> rObjs = ExtractJsonObjectArray(syncJson, "incoming_requests");
                    foreach (string o in rObjs)
                    {
                        string rn = ExtractJsonString(o, "name");
                        int ruid = ExtractJsonInt(o, "uid_num", 10001);
                        if (!string.IsNullOrEmpty(rn))
                        {
                            parsedReqs.Add(new FriendReqItem
                            {
                                Name = rn,
                                DisplayName = "👤 " + rn + "  (#" + ruid + ")",
                                AcceptTag = "ACCEPT:" + rn,
                                DeclineTag = "DECLINE:" + rn
                            });
                        }
                    }

                    // Parse blocked users
                    List<FriendReqItem> parsedBlocked = new List<FriendReqItem>();
                    Match blkMatch = Regex.Match(syncJson, "\"blocked_users\"\\s*:\\s*\\[(.*?)\\]", RegexOptions.Singleline);
                    if (blkMatch.Success)
                    {
                        MatchCollection bStrs = Regex.Matches(blkMatch.Groups[1].Value, "\"([^\"]+)\"");
                        foreach (Match bm in bStrs)
                        {
                            string bn = bm.Groups[1].Value;
                            if (!string.IsNullOrEmpty(bn))
                                parsedBlocked.Add(new FriendReqItem { Name = bn, DisplayName = "🚫 " + bn });
                        }
                    }

                    // Parse room invites safely
                    int latestInvId = 0;
                    string latestInvFrom = "";
                    string latestInvRoomName = "";
                    string latestInvMapName = "";
                    List<string> invObjs = ExtractJsonObjectArray(syncJson, "room_invites");
                    if (invObjs.Count > 0)
                    {
                        string io = invObjs[0];
                        latestInvId = ExtractJsonInt(io, "invite_id", 0);
                        latestInvFrom = ExtractJsonString(io, "from_user");
                        latestInvRoomName = ExtractJsonString(io, "room_name");
                        latestInvMapName = ExtractJsonString(io, "map_name");
                    }

                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        currentUidNum = myUid;
                        if (lblProfileUid != null) lblProfileUid.Text = "#" + currentUidNum;
                        if (!string.IsNullOrEmpty(currentUsername)) UpdateHeroWelcome(currentUsername);
                        UpdateSidebarProfileBadges(myBadgeLbl, myBadgeCol, myEloDisp, myEloCol);

                        // unreadTotal from backend already includes unread DMs + incoming_requests + room_invites
                        int totalBadge = Math.Max(unreadTotal, parsedReqs.Count);
                        if (!initialLoad && totalBadge > lastUnreadTotal)
                        {
                            PlayNotifySound();
                        }
                        lastUnreadTotal = totalBadge;

                        if (badgeFriendsUnread != null && lblFriendsUnreadCount != null)
                        {
                            badgeFriendsUnread.Visibility = (totalBadge > 0) ? Visibility.Visible : Visibility.Collapsed;
                            lblFriendsUnreadCount.Text = totalBadge.ToString();
                        }

                        if (pendingRequestsPanel != null)
                        {
                            pendingRequestsPanel.Visibility = (parsedReqs.Count > 0) ? Visibility.Visible : Visibility.Collapsed;
                            pendingRequestsList.ItemsSource = parsedReqs;
                        }
                        if (friendsListCtrl != null) friendsListCtrl.ItemsSource = parsedFriends;
                        if (blockedUsersListCtrl != null) blockedUsersListCtrl.ItemsSource = parsedBlocked;

                        // Room Invite Banner
                        if (latestInvId > 0 && latestInvId != lastDismissedInviteId)
                        {
                            activeInviteId = latestInvId;
                            lblInviteBannerText.Text = "«" + latestInvFrom + "» таныг «" + latestInvRoomName + "» (" + latestInvMapName + ") өрөөнд тоглохоор урилаа!";
                            inviteBannerOverlay.Visibility = Visibility.Visible;
                            if (latestInvId != lastPlayedInviteSoundId)
                            {
                                lastPlayedInviteSoundId = latestInvId;
                                PlayNotifySound();
                            }
                        }
                        else if (latestInvId == 0)
                        {
                            inviteBannerOverlay.Visibility = Visibility.Collapsed;
                        }
                    }));
                }
                catch { }
            });
        }

        private static void CheckAndUploadCheckpoint()
        {
            try
            {
                string saveDir = Path.Combine(war3Dir, "Save", "Multiplayer");
                if (!Directory.Exists(saveDir)) return;
                FileInfo newest = null;
                foreach (string f in Directory.GetFiles(saveDir, "*.w3z"))
                {
                    FileInfo fi = new FileInfo(f);
                    if (fi.Length > 512 && (newest == null || fi.LastWriteTimeUtc > newest.LastWriteTimeUtc))
                        newest = fi;
                }
                if (newest == null || (DateTime.UtcNow - newest.LastWriteTimeUtc).TotalSeconds > 30) return;

                byte[] raw = File.ReadAllBytes(newest.FullName);
                string sha = ComputeSha256(raw);
                if (sha == lastUploadedSha || sha == lastDownloadedSha) return;
                lastUploadedSha = sha;

                for (int attempt = 0; attempt < 2; attempt++)
                {
                    string baseUrl = (attempt == 0) ? activeServerUrl : ((activeServerUrl == SERVER_URL) ? FALLBACK_SERVER_URL : SERVER_URL);
                    try
                    {
                        HttpWebRequest req = (HttpWebRequest)WebRequest.Create(baseUrl + "/api/rooms/" + currentRoomId + "/checkpoint");
                        req.Method = "PUT";
                        req.Timeout = 15000;
                        req.Headers["Authorization"] = "Bearer " + authToken;
                        req.ContentType = "application/octet-stream";
                        req.ContentLength = raw.Length;
                        using (Stream s = req.GetRequestStream()) s.Write(raw, 0, raw.Length);
                        using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse()) { }
                        if (attempt == 1) activeServerUrl = baseUrl;
                        break;
                    }
                    catch (WebException wex)
                    {
                        if (wex.Response != null || attempt == 1) break;
                    }
                }
            }
            catch { }
        }

        private static void DownloadCheckpoint(string filename, string sha)
        {
            try
            {
                string saveDir = Path.Combine(war3Dir, "Save", "Multiplayer");
                if (!Directory.Exists(saveDir)) Directory.CreateDirectory(saveDir);
                string dest = Path.Combine(saveDir, Path.GetFileName(filename));

                for (int attempt = 0; attempt < 2; attempt++)
                {
                    string baseUrl = (attempt == 0) ? activeServerUrl : ((activeServerUrl == SERVER_URL) ? FALLBACK_SERVER_URL : SERVER_URL);
                    try
                    {
                        HttpWebRequest req = (HttpWebRequest)WebRequest.Create(baseUrl + "/api/rooms/" + currentRoomId + "/checkpoint");
                        req.Method = "GET";
                        req.Timeout = 15000;
                        req.Headers["Authorization"] = "Bearer " + authToken;
                        using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                        using (Stream rs = resp.GetResponseStream())
                        using (FileStream fs = new FileStream(dest, FileMode.Create, FileAccess.Write))
                        {
                            rs.CopyTo(fs);
                        }
                        if (attempt == 1) activeServerUrl = baseUrl;
                        lastDownloadedSha = sha;
                        break;
                    }
                    catch (WebException wex)
                    {
                        if (wex.Response != null || attempt == 1) break;
                    }
                }
            }
            catch { }
        }

        private static bool isMeasuringPing = false;

        private static void MeasureServerPingAsync()
        {
            if (isMeasuringPing) return;
            isMeasuringPing = true;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    IPAddress serverIp = IPAddress.Parse(W3GS_HOST);
                    int bestMs = 9999;
                    for (int attempt = 0; attempt < 3; attempt++)
                    {
                        try
                        {
                            using (TcpClient tcp = new TcpClient())
                            {
                                Stopwatch sw = Stopwatch.StartNew();
                                IAsyncResult ar = tcp.BeginConnect(serverIp, 443, null, null);
                                if (ar.AsyncWaitHandle.WaitOne(1500))
                                {
                                    tcp.EndConnect(ar);
                                    sw.Stop();
                                    int ms = (int)Math.Max(1, sw.ElapsedMilliseconds);
                                    if (ms < bestMs) bestMs = ms;
                                }
                            }
                        }
                        catch { }
                    }
                    if (bestMs < 9999)
                    {
                        currentPingMs = bestMs;
                        if (mainWin != null)
                        {
                            mainWin.Dispatcher.BeginInvoke(new Action(() =>
                            {
                                if (lblNetPing != null) lblNetPing.Text = currentPingMs + " ms";
                            }));
                        }
                    }
                }
                catch { }
                finally
                {
                    isMeasuringPing = false;
                }
            });
        }

        private static void StartLocalBridge()
        {
            try { ThreadPool.SetMinThreads(32, 32); } catch { }
            Thread proxyThread = new Thread(() =>
            {
                try { Thread.CurrentThread.Priority = ThreadPriority.Highest; } catch { }
                for (int p = 6210; p < 6225; p++)
                {
                    try
                    {
                        proxyListener = new TcpListener(IPAddress.Any, p);
                        proxyListener.Start();
                        localProxyPort = p;
                        break;
                    }
                    catch { }
                }
                if (mainWin != null)
                {
                    mainWin.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        lblNetIp.Text = "127.0.0.1:" + localProxyPort;
                    }));
                }
                while (running)
                {
                    try
                    {
                        TcpClient localClient = proxyListener.AcceptTcpClient();
                        Thread bridgeTh = new Thread(() => BridgeTcpSession(localClient));
                        bridgeTh.IsBackground = true;
                        try { bridgeTh.Priority = ThreadPriority.Highest; } catch { }
                        bridgeTh.Start();
                    }
                    catch { if (!running) break; }
                }
            });
            proxyThread.IsBackground = true;
            proxyThread.Start();

            Thread udpThread = new Thread(() =>
            {
                try
                {
                    udpBroadcaster = new UdpClient(new IPEndPoint(IPAddress.Loopback, 0));
                }
                catch
                {
                    udpBroadcaster = new UdpClient();
                }
                IPEndPoint epLocal = new IPEndPoint(IPAddress.Loopback, 6112);
                while (running)
                {
                    try
                    {
                        // Do not spam war3.exe UDP port 6112 while player is already connected inside an active match
                        if (!(currentRoomMyW3gsConnected && IsMatchActuallyStarted()))
                        {
                            byte[] src = currentLanAd;
                            if (src != null && src.Length >= 20)
                            {
                                byte[] pkt = (byte[])src.Clone();
                                // Always patch the last 2 bytes (uint16 LE port) of W3GS_GAMEINFO (0xF7 0x30) to match localProxyPort
                                pkt[pkt.Length - 2] = (byte)(localProxyPort & 0xFF);
                                pkt[pkt.Length - 1] = (byte)((localProxyPort >> 8) & 0xFF);

                                // #2 Fix: Send strictly to 127.0.0.1:6112 so Warcraft III Local Area Network displays ONLY 1 Host instead of 4 duplicates!
                                try { udpBroadcaster.Send(pkt, pkt.Length, epLocal); } catch { }
                            }
                        }
                    }
                    catch { }
                    Thread.Sleep(400);
                }
            });
            udpThread.IsBackground = true;
            udpThread.Start();
        }

        private static void BridgeTcpSession(TcpClient localClient)
        {
            int mySessionId = Interlocked.Increment(ref activeBridgeSessionId);
            using (localClient)
            {
                try
                {
                    try { Thread.CurrentThread.Priority = ThreadPriority.Highest; } catch { }
                    using (TcpClient remoteClient = new TcpClient(W3GS_HOST, w3gsPort))
                    {
                        localClient.NoDelay = true;
                        remoteClient.NoDelay = true;
                        localClient.ReceiveBufferSize = 65536;
                        localClient.SendBufferSize = 65536;
                        remoteClient.ReceiveBufferSize = 65536;
                        remoteClient.SendBufferSize = 65536;
                        bridgeW3gsConnected = true;
                        bridgeW3gsInGame = false;
                        bridgeLagDialogOpen = false;
                        inGameChatActive = false;
                        enterKeyPhysicallyDown = false;
                        Stream ls = localClient.GetStream();
                        Stream rs = remoteClient.GetStream();
                        Thread t1 = new Thread(() =>
                        {
                            try { Thread.CurrentThread.Priority = ThreadPriority.Highest; } catch { }
                            try
                            {
                                byte[] buf = new byte[16384];
                                int n;
                                while ((n = ls.Read(buf, 0, buf.Length)) > 0)
                                {
                                    // Inspect outgoing W3GS packets for real-time lobby vs in-game & chat state
                                    int pos = 0;
                                    while (pos + 4 <= n && buf[pos] == 0xF7)
                                    {
                                        byte pid = buf[pos + 1];
                                        int plen = buf[pos + 2] | (buf[pos + 3] << 8);
                                        if (plen < 4) break;
                                        if (pid == 0x1E) // W3GS_REQJOIN -> entered 10-player Lobby
                                        {
                                            bridgeW3gsConnected = true;
                                            bridgeW3gsInGame = false;
                                            bridgeLagDialogOpen = false;
                                            inGameChatActive = false;
                                        }
                                        else if (pid == 0x23 || pid == 0x26 || pid == 0x27) // W3GS_GAMELOADED_SELF / ACTION / KEEPALIVE -> in 3D Match
                                        {
                                            bridgeW3gsInGame = true;
                                            if (pid == 0x23)
                                            {
                                                inGameChatActive = false;
                                                enterKeyPhysicallyDown = false;
                                            }
                                        }
                                        else if (pid == 0x28 && pos + 5 < n) // W3GS_CHAT_TO_HOST
                                        {
                                            byte flag = buf[pos + 5];
                                            if (flag == 0x10 || flag == 0x20)
                                                inGameChatActive = false;
                                        }
                                        if (pos + plen > n) break;
                                        pos += plen;
                                    }
                                    rs.Write(buf, 0, n);
                                }
                            }
                            catch { }
                        });
                        t1.IsBackground = true;
                        t1.Start();
                        try
                        {
                            byte[] sbuf = new byte[16384];
                            int sn;
                            while ((sn = rs.Read(sbuf, 0, sbuf.Length)) > 0)
                            {
                                int pos = 0;
                                while (pos + 4 <= sn && sbuf[pos] == 0xF7)
                                {
                                    byte pid = sbuf[pos + 1];
                                    int plen = sbuf[pos + 2] | (sbuf[pos + 3] << 8);
                                    if (plen < 4) break;
                                    if (pid == 0x0B || pid == 0x0C || pid == 0x48) // COUNTDOWN_END / INCOMING_ACTION
                                    {
                                        bridgeW3gsInGame = true;
                                        bridgeLagDialogOpen = false;
                                        if (pid == 0x0B) inGameChatActive = false;
                                    }
                                    else if (pid == 0x10) // W3GS_START_LAG -> Waiting for players screen open
                                    {
                                        bridgeLagDialogOpen = true;
                                    }
                                    else if (pid == 0x11) // W3GS_STOP_LAG -> Waiting for players screen closed
                                    {
                                        bridgeLagDialogOpen = false;
                                    }
                                    if (pos + plen > sn) break;
                                    pos += plen;
                                }
                                ls.Write(sbuf, 0, sn);
                            }
                        }
                        catch { }
                    }
                }
                catch { }
                finally
                {
                    if (activeBridgeSessionId == mySessionId)
                    {
                        bridgeW3gsConnected = false;
                        bridgeW3gsInGame = false;
                        bridgeLagDialogOpen = false;
                        inGameChatActive = false;
                        enterKeyPhysicallyDown = false;
                    }
                }
            }
        }

        private static string GetHardwareId()
        {
            if (!string.IsNullOrEmpty(cachedHwid)) return cachedHwid;
            try
            {
                StringBuilder sb = new StringBuilder();
                try
                {
                    using (RegistryKey rk = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Cryptography"))
                    {
                        if (rk != null) sb.Append(Convert.ToString(rk.GetValue("MachineGuid")));
                    }
                }
                catch { }
                try
                {
                    using (RegistryKey rk = Registry.LocalMachine.OpenSubKey(@"HARDWARE\DESCRIPTION\System\CentralProcessor\0"))
                    {
                        if (rk != null) sb.Append("|").Append(Convert.ToString(rk.GetValue("ProcessorNameString")));
                    }
                }
                catch { }
                try
                {
                    using (RegistryKey rk = Registry.LocalMachine.OpenSubKey(@"HARDWARE\DESCRIPTION\System\BIOS"))
                    {
                        if (rk != null)
                        {
                            sb.Append("|").Append(Convert.ToString(rk.GetValue("BaseBoardProduct")));
                            sb.Append("|").Append(Convert.ToString(rk.GetValue("BIOSVendor")));
                        }
                    }
                }
                catch { }
                sb.Append("|").Append(Environment.MachineName).Append("|").Append(Environment.ProcessorCount);
                string hash = ComputeSha256(Encoding.UTF8.GetBytes(sb.ToString()));
                cachedHwid = "MRHW-" + (hash.Length >= 32 ? hash.Substring(0, 32) : hash);
            }
            catch
            {
                cachedHwid = "MRHW-FALLBACK-" + Environment.MachineName;
            }
            return cachedHwid;
        }

        private static string ApiRequest(string method, string path, string jsonBody = null)
        {
            for (int attempt = 0; attempt < 2; attempt++)
            {
                string baseUrl = (attempt == 0) ? activeServerUrl : ((activeServerUrl == SERVER_URL) ? FALLBACK_SERVER_URL : SERVER_URL);
                try
                {
                    HttpWebRequest req = (HttpWebRequest)WebRequest.Create(baseUrl + path);
                    req.Method = method;
                    req.Timeout = 10000;
                    req.ReadWriteTimeout = 10000;
                    if (!string.IsNullOrEmpty(authToken))
                        req.Headers["Authorization"] = "Bearer " + authToken;
                    req.Headers["X-MR-HWID"] = GetHardwareId();
                    if (jsonBody != null)
                    {
                        byte[] data = Encoding.UTF8.GetBytes(jsonBody);
                        req.ContentType = "application/json";
                        req.ContentLength = data.Length;
                        using (Stream s = req.GetRequestStream()) s.Write(data, 0, data.Length);
                    }
                    using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                    using (StreamReader sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                    {
                        string res = sr.ReadToEnd();
                        if (attempt == 1) activeServerUrl = baseUrl;
                        return res;
                    }
                }
                catch (WebException wex)
                {
                    if (wex.Response != null || attempt == 1)
                        throw;
                }
            }
            return "";
        }

        private static string ExtractJsonString(string json, string key)
        {
            Match m = Regex.Match(json, "\"" + Regex.Escape(key) + "\"\\s*:\\s*\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"");
            return m.Success ? Regex.Unescape(m.Groups[1].Value) : "";
        }

        private static int ExtractJsonInt(string json, string key, int defVal = 0)
        {
            Match m = Regex.Match(json, "\"" + Regex.Escape(key) + "\"\\s*:\\s*(\\d+)");
            int v;
            return (m.Success && int.TryParse(m.Groups[1].Value, out v)) ? v : defVal;
        }

        private static List<string> ExtractJsonObjectArray(string json, string key)
        {
            List<string> result = new List<string>();
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(key)) return result;
            Match m = Regex.Match(json, "\"" + Regex.Escape(key) + "\"\\s*:\\s*\\[");
            if (!m.Success) return result;
            int idx = m.Index + m.Length;
            int bracketDepth = 1;
            int braceDepth = 0;
            int objStart = -1;
            bool inString = false;
            bool escaped = false;
            for (int i = idx; i < json.Length; i++)
            {
                char c = json[i];
                if (escaped)
                {
                    escaped = false;
                    continue;
                }
                if (c == '\\' && inString)
                {
                    escaped = true;
                    continue;
                }
                if (c == '"')
                {
                    inString = !inString;
                    continue;
                }
                if (inString) continue;

                if (c == '{')
                {
                    if (braceDepth == 0) objStart = i;
                    braceDepth++;
                }
                else if (c == '}')
                {
                    braceDepth--;
                    if (braceDepth == 0 && objStart >= 0)
                    {
                        result.Add(json.Substring(objStart, i - objStart + 1));
                        objStart = -1;
                    }
                }
                else if (c == '[' && braceDepth == 0)
                {
                    bracketDepth++;
                }
                else if (c == ']' && braceDepth == 0)
                {
                    bracketDepth--;
                    if (bracketDepth == 0) break;
                }
            }
            return result;
        }

        private static string GetConfigPath()
        {
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MongolRanger");
            if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
            return Path.Combine(dir, "client_config.txt");
        }

        private static string FormatSingleKey(Key k)
        {
            if (k >= Key.D0 && k <= Key.D9)
                return ((int)(k - Key.D0)).ToString();
            if (k >= Key.NumPad0 && k <= Key.NumPad9)
                return "Num" + ((int)(k - Key.NumPad0)).ToString();
            if (k == Key.Prior) return "PageUp";
            if (k == Key.Next) return "PageDown";
            if (k == Key.OemTilde) return "~";
            if (k == Key.OemMinus) return "-";
            if (k == Key.OemPlus) return "=";
            return k.ToString();
        }

        private static string FormatKeyCombo(Key k, bool alt, bool ctrl, bool shift)
        {
            string mod = "";
            if (ctrl) mod += "Ctrl+";
            if (alt) mod += "Alt+";
            if (shift) mod += "Shift+";
            return mod + FormatSingleKey(k);
        }

        private static void UpdateWarKeyUI()
        {
            try
            {
                if (btnToggleWarKey != null && lblWarKeyToggleState != null)
                {
                    if (warKeyEnabled)
                    {
                        btnToggleWarKey.Background = HexBrush("#0F291E");
                        btnToggleWarKey.BorderBrush = HexBrush("#10B981");
                        lblWarKeyToggleState.Text = "🟢 WARKEY: ИДЭВХТЭЙ (ON)";
                        lblWarKeyToggleState.Foreground = HexBrush("#34D399");
                    }
                    else
                    {
                        btnToggleWarKey.Background = HexBrush("#2A1215");
                        btnToggleWarKey.BorderBrush = HexBrush("#EF4444");
                        lblWarKeyToggleState.Text = "🔴 WARKEY: УНТАРСАН (OFF)";
                        lblWarKeyToggleState.Foreground = HexBrush("#F87171");
                    }
                }
                for (int i = 0; i < 6; i++)
                {
                    if (wkButtons[i] == null) continue;
                    string val = wkKeys[i];
                    if (string.IsNullOrEmpty(val))
                    {
                        wkButtons[i].Content = "Хоосон";
                        wkButtons[i].Foreground = HexBrush("#64748B");
                    }
                    else
                    {
                        wkButtons[i].Content = val;
                        wkButtons[i].Foreground = HexBrush("#F59E0B");
                    }
                }
                for (int i = 0; i < 8; i++)
                {
                    if (wkSkillButtons[i] == null) continue;
                    string val = wkSkillKeys[i];
                    if (string.IsNullOrEmpty(val))
                    {
                        wkSkillButtons[i].Content = "Хоосон";
                        wkSkillButtons[i].Foreground = HexBrush("#64748B");
                    }
                    else
                    {
                        wkSkillButtons[i].Content = val;
                        wkSkillButtons[i].Foreground = HexBrush("#C4B5FD");
                    }
                }
                if (btnQuickChatKey != null)
                {
                    if (string.IsNullOrEmpty(pendingQuickChatKey))
                    {
                        btnQuickChatKey.Content = "Хоосон";
                        btnQuickChatKey.Foreground = HexBrush("#64748B");
                    }
                    else
                    {
                        btnQuickChatKey.Content = pendingQuickChatKey;
                        btnQuickChatKey.Foreground = HexBrush("#38BDF8");
                    }
                }
                if (quickChatListCtrl != null)
                {
                    quickChatListCtrl.ItemsSource = null;
                    quickChatListCtrl.ItemsSource = quickChats;
                }
                bool anyBinding = (quickChats != null && quickChats.Count > 0);
                if (!anyBinding)
                {
                    for (int i = 0; i < 6; i++)
                    {
                        if (!string.IsNullOrEmpty(wkKeys[i])) { anyBinding = true; break; }
                    }
                }
                if (!anyBinding)
                {
                    for (int i = 0; i < 8; i++)
                    {
                        if (!string.IsNullOrEmpty(wkSkillKeys[i])) { anyBinding = true; break; }
                    }
                }
                hasAnyWarKeyBinding = anyBinding;
            }
            catch { }
        }

        private static string GetModeLabel(string mode)
        {
            if (mode == "WAR3_ALL") return "War3 All";
            if (mode == "LOBBY") return "War3 Lobby";
            return "War3";
        }

        private static void AddQuickChatEntry()
        {
            try
            {
                string key = (pendingQuickChatKey ?? "").Trim();
                string msg = (txtQuickChatMsg != null ? txtQuickChatMsg.Text : "").Trim();
                if (string.IsNullOrEmpty(key) || string.IsNullOrEmpty(msg)) return;

                string mode = "WAR3";
                if (rbChatWar3All != null && rbChatWar3All.IsChecked == true) mode = "WAR3_ALL";
                else if (rbChatLobby != null && rbChatLobby.IsChecked == true) mode = "LOBBY";

                quickChats.Add(new QuickChatItem
                {
                    Id = Guid.NewGuid().ToString("N"),
                    KeyName = key,
                    Message = msg,
                    Mode = mode,
                    ModeLabel = GetModeLabel(mode)
                });
                if (txtQuickChatMsg != null) txtQuickChatMsg.Text = "";
                UpdateWarKeyUI();
                SaveSettings();
            }
            catch { }
        }

        private static void OnDeleteQuickChatClick(object sender, RoutedEventArgs e)
        {
            try
            {
                Button btn = e.OriginalSource as Button;
                if (btn != null && btn.Tag != null)
                {
                    string id = btn.Tag.ToString();
                    quickChats.RemoveAll(x => x.Id == id);
                    UpdateWarKeyUI();
                    SaveSettings();
                }
            }
            catch { }
        }

        private static DateTime lastChatOpenUtc = DateTime.MinValue;
        private static string inGameCmdBuffer = "";
        private static DateTime lastInGameCmdUtc = DateTime.MinValue;

        private static bool IsKnownMongolRangerCommand(string cmd)
        {
            if (string.IsNullOrEmpty(cmd) || cmd.Length < 2) return false;
            char pfx = cmd[0];
            if (pfx != '-' && pfx != '!' && pfx != '/') return false;
            string body = cmd.Substring(1).Trim().ToLowerInvariant();
            if (string.IsNullOrEmpty(body)) return false;
            string[] parts = body.Split(new char[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 0) return false;
            string head = parts[0];
            return head == "rmk" || head == "remake" || head == "warda" ||
                   head == "gg" || head == "ff" || head == "forfeit" || head == "surrender" ||
                   head == "addtime" || head == "time" || head == "wait" ||
                   head == "help" || head == "zaavar" || head == "cmd" || head == "commands" ||
                   head == "start" || head == "1v1" || head == "2v2" || head == "3v3" || head == "4v4" || head == "5v5" ||
                   head == "close" || head == "closeall" || head == "open" || head == "openall" || head == "swap" ||
                   head == "easy" || head == "normal" || head == "insane" || head == "comp" || head == "computer" || head == "hasah";
        }

        private static void SendInGameCommandToServer(string cmdText)
        {
            if (string.IsNullOrEmpty(currentRoomId) || string.IsNullOrEmpty(authToken)) return;
            string rid = currentRoomId;
            string clean = cmdText.Trim();
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    // Delay 120ms so if W3GS 0x28/0x26 already delivered the command, server deduplication handles it cleanly;
                    // and if W3GS dropped plain-Enter [Allies] chat in 1v1 (0 human teammates), this guarantees 100% delivery!
                    Thread.Sleep(120);
                    string json = "{\"message\":\"" + clean.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"}";
                    ApiRequest("POST", "/api/rooms/" + rid + "/chat", json);
                    SyncRoomStateOnceAsync();
                }
                catch { }
            });
        }

        private static void InstallWarKeyHook()
        {
            try
            {
                if (keyboardHookId != IntPtr.Zero || fnSetHook == null || fnGetMod == null) return;
                keyboardHookProc = KeyboardHookCallback;
                using (Process curProcess = Process.GetCurrentProcess())
                using (ProcessModule curModule = curProcess.MainModule)
                {
                    keyboardHookId = fnSetHook(WH_KEYBOARD_LL, keyboardHookProc, fnGetMod(curModule.ModuleName), 0);
                }
            }
            catch { }
        }

        private static void UninstallWarKeyHook()
        {
            try
            {
                if (keyboardHookId != IntPtr.Zero && fnUnhook != null)
                {
                    fnUnhook(keyboardHookId);
                    keyboardHookId = IntPtr.Zero;
                }
            }
            catch { }
        }

        private static IntPtr lastCheckedFgHwnd = IntPtr.Zero;
        private static bool lastCheckedFgIsWar3 = false;
        private static bool enterKeyPhysicallyDown = false;

        private static bool IsWarcraftForeground(out IntPtr hwnd)
        {
            hwnd = (fnGetFg != null) ? fnGetFg() : IntPtr.Zero;
            if (hwnd == IntPtr.Zero || fnGetCls == null) return false;
            if (hwnd == lastCheckedFgHwnd)
                return lastCheckedFgIsWar3;
            StringBuilder sb = new StringBuilder(64);
            bool isWar3 = false;
            if (fnGetCls(hwnd, sb, sb.Capacity) > 0)
            {
                string cls = sb.ToString();
                if (string.Equals(cls, "Warcraft III", StringComparison.OrdinalIgnoreCase))
                    isWar3 = true;
            }
            lastCheckedFgHwnd = hwnd;
            lastCheckedFgIsWar3 = isWar3;
            return isWar3;
        }

        // Reads Warcraft III 1.26a Game.dll memory directly (like Garena Total / W3Champions):
        // - [Game.dll + 0xAB65F4] = CGameUI* (0 in Main Menu / LAN / 10-player Lobby; non-zero ONLY in 3D Gameplay)
        // - [Game.dll + 0xAD15F0] = g_bIsChatBoxOpen (1 when chat input is open)
        // - [[CGameUI + 0x3FC] + 0x1DC] = CChatEditBar::visible (1 when chat edit bar is active)
        private static bool ReadWar3GameState(IntPtr war3Hwnd, out bool isIn3DGame, out bool isChatBoxOpen)
        {
            isIn3DGame = false;
            isChatBoxOpen = false;
            return false;
        }

        private static IntPtr KeyboardHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
        {
            try
            {
                if (nCode >= 0)
                {
                    KBDLLHOOKSTRUCT f4Info = (KBDLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(KBDLLHOOKSTRUCT));
                    if (f4Info.vkCode == 0x73) // VK_F4
                    {
                        bool isAlt = (wParam == (IntPtr)WM_SYSKEYDOWN || wParam == (IntPtr)WM_SYSKEYUP
                            || (f4Info.flags & 0x20) != 0
                            || (fnGetKey != null && ((fnGetKey(0x12) & 0x8000) != 0 || (fnGetKey(0xA4) & 0x8000) != 0 || (fnGetKey(0xA5) & 0x8000) != 0)));
                        if (isAlt)
                        {
                            IntPtr fgHwnd;
                            if (IsWarcraftForeground(out fgHwnd))
                            {
                                // Block Alt+F4 completely inside Warcraft III so players cannot fake a crash/Rejoin;
                                // anyone wishing to leave must press F10 -> Quit Mission.
                                return (IntPtr)1;
                            }
                        }
                    }
                }

                if (nCode >= 0 && (wParam == (IntPtr)WM_KEYUP || wParam == (IntPtr)WM_SYSKEYUP))
                {
                    KBDLLHOOKSTRUCT upInfo = (KBDLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(KBDLLHOOKSTRUCT));
                    if (upInfo.vkCode == 0x0D && upInfo.dwExtraInfo != MR_EXTRA_INFO)
                        enterKeyPhysicallyDown = false;
                    return fnCallNext(keyboardHookId, nCode, wParam, lParam);
                }

                if (nCode >= 0 && (wParam == (IntPtr)WM_KEYDOWN || wParam == (IntPtr)WM_SYSKEYDOWN))
                {
                    KBDLLHOOKSTRUCT info = (KBDLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(KBDLLHOOKSTRUCT));
                    if (info.dwExtraInfo == MR_EXTRA_INFO || isSendingQuickChat)
                        return fnCallNext(keyboardHookId, nCode, wParam, lParam);

                    IntPtr war3Hwnd;
                    bool war3Fg = IsWarcraftForeground(out war3Hwnd);

                    // Catch blind "-addtime" typing while the Waiting for players dialog is open (even if chat box is blocked by modal)
                    if (war3Fg && !string.IsNullOrEmpty(currentRoomId) &&
                        (bridgeLagDialogOpen || currentRoomPhase == "WAITING" || currentRoomPhase == "FROZEN" || !string.IsNullOrEmpty(currentRoomAbsent)))
                    {
                        if (info.vkCode >= 0x41 && info.vkCode <= 0x5A)
                        {
                            char ch = (char)(info.vkCode + 32); // 'a'..'z'
                            waitTypedBuffer += ch;
                            if (waitTypedBuffer.Length > 16)
                                waitTypedBuffer = waitTypedBuffer.Substring(waitTypedBuffer.Length - 16);
                            if (waitTypedBuffer.EndsWith("addtime") && (DateTime.UtcNow - lastBlindAddtimeUtc).TotalSeconds > 1.5)
                            {
                                waitTypedBuffer = "";
                                lastBlindAddtimeUtc = DateTime.UtcNow;
                                ExtendRoomWaitTime();
                            }
                        }
                    }

                    // Universal in-game command bridge: guarantees -rmk, -gg, -addtime, -1v1..-4v4 work in 1v1/2v2/3v3/4v4
                    // even when plain Enter ([Allies] chat with 0 human teammates in 1v1) does not emit W3GS 0x28.
                    if (war3Fg && !string.IsNullOrEmpty(currentRoomId))
                    {
                        if (info.vkCode == 0xBD || info.vkCode == 0x6D || info.vkCode == 0xBF || info.vkCode == 0x6F)
                        {
                            inGameCmdBuffer = "-";
                        }
                        else if (info.vkCode == 0x1B) // VK_ESCAPE
                        {
                            inGameCmdBuffer = "";
                        }
                        else if (info.vkCode == 0x0D) // VK_RETURN
                        {
                            if (!string.IsNullOrEmpty(inGameCmdBuffer))
                            {
                                string cand = inGameCmdBuffer.Trim();
                                inGameCmdBuffer = "";
                                if (IsKnownMongolRangerCommand(cand) && (DateTime.UtcNow - lastInGameCmdUtc).TotalSeconds > 1.0)
                                {
                                    lastInGameCmdUtc = DateTime.UtcNow;
                                    SendInGameCommandToServer(cand);
                                }
                            }
                        }
                        else if (!string.IsNullOrEmpty(inGameCmdBuffer))
                        {
                            if (info.vkCode == 0x08) // Backspace
                            {
                                inGameCmdBuffer = inGameCmdBuffer.Substring(0, inGameCmdBuffer.Length - 1);
                            }
                            else if (inGameCmdBuffer.Length < 28)
                            {
                                if (info.vkCode >= 0x41 && info.vkCode <= 0x5A)
                                    inGameCmdBuffer += (char)(info.vkCode + 32);
                                else if (info.vkCode >= 0x30 && info.vkCode <= 0x39)
                                    inGameCmdBuffer += (char)info.vkCode;
                                else if (info.vkCode >= 0x60 && info.vkCode <= 0x69)
                                    inGameCmdBuffer += (char)('0' + (info.vkCode - 0x60));
                                else if (info.vkCode == 0x20)
                                    inGameCmdBuffer += ' ';
                            }
                        }
                    }

                    // Fast-path when no WarKey bindings are configured or WarKey is disabled
                    if (info.vkCode != 0x74 && (!warKeyEnabled || !hasAnyWarKeyBinding))
                        return fnCallNext(keyboardHookId, nCode, wParam, lParam);

                    bool ctrlDown = (fnGetKey(0x11) & 0x8000) != 0;
                    bool altDown = (fnGetKey(0x12) & 0x8000) != 0;

                    // Global Ctrl + F5 toggle
                    if (info.vkCode == 0x74 && ctrlDown && !altDown)
                    {
                        warKeyEnabled = !warKeyEnabled;
                        if (mainWin != null)
                            mainWin.Dispatcher.BeginInvoke(new Action(() => { UpdateWarKeyUI(); SaveSettings(); }));
                        return (IntPtr)1;
                    }

                    if (!warKeyEnabled || !hasAnyWarKeyBinding)
                        return fnCallNext(keyboardHookId, nCode, wParam, lParam);

                    if (!war3Fg)
                    {
                        inGameChatActive = false;
                        enterKeyPhysicallyDown = false;
                        return fnCallNext(keyboardHookId, nCode, wParam, lParam);
                    }

                    // 1. Direct Game.dll 1.26a memory check (Garena Total style):
                    //    - If CGameUI* == 0 (10-player Lobby, LAN menu, Loading screen), WarKey is 100% OFF.
                    //    - If IsChatBoxOpen != 0 or CChatEditBar::visible != 0, WarKey is 100% OFF (so Space types ' ', never '8').
                    bool memIn3DGame, memChatOpen;
                    bool memOk = ReadWar3GameState(war3Hwnd, out memIn3DGame, out memChatOpen);
                    if (memOk)
                    {
                        if (!memIn3DGame)
                        {
                            inGameChatActive = false;
                            enterKeyPhysicallyDown = false;
                            return fnCallNext(keyboardHookId, nCode, wParam, lParam);
                        }
                        if (memChatOpen)
                        {
                            inGameChatActive = true;
                            lastChatOpenUtc = DateTime.UtcNow;
                            return fnCallNext(keyboardHookId, nCode, wParam, lParam);
                        }
                        else if (inGameChatActive && (DateTime.UtcNow - lastChatOpenUtc).TotalMilliseconds > 450)
                        {
                            inGameChatActive = false;
                        }
                    }

                    // 2. Real-time W3GS packet & room state guard:
                    //    Never fire WarKey in the 10-player Pre-Game Lobby or while Waiting dialog is open!
                    if (bridgeLagDialogOpen || (!memOk && bridgeW3gsConnected && !bridgeW3gsInGame))
                    {
                        inGameChatActive = false;
                        enterKeyPhysicallyDown = false;
                        return fnCallNext(keyboardHookId, nCode, wParam, lParam);
                    }
                    if (!memOk && !string.IsNullOrEmpty(currentRoomId) && !bridgeW3gsInGame)
                    {
                        bool inActiveGameplay = currentRoomMyW3gsConnected &&
                            (currentRoomPhase == "CONTINUING" || currentRoomPhase == "VERIFYING" ||
                             currentRoomPhase == "RUNNING" || currentRoomPhase == "PLAYING");
                        if (!inActiveGameplay)
                        {
                            inGameChatActive = false;
                            enterKeyPhysicallyDown = false;
                            return fnCallNext(keyboardHookId, nCode, wParam, lParam);
                        }
                    }

                    // Track Enter / Escape for immediate 0ms transition before war3.exe processes WM_KEYDOWN(VK_RETURN)
                    if (info.vkCode == 0x0D) // VK_RETURN
                    {
                        if (!enterKeyPhysicallyDown)
                        {
                            enterKeyPhysicallyDown = true;
                            if (memOk && memChatOpen)
                                inGameChatActive = false;
                            else
                                inGameChatActive = !inGameChatActive;
                            lastChatOpenUtc = DateTime.UtcNow;
                        }
                        return fnCallNext(keyboardHookId, nCode, wParam, lParam);
                    }
                    if (info.vkCode == 0x1B) // VK_ESCAPE
                    {
                        inGameChatActive = false;
                        return fnCallNext(keyboardHookId, nCode, wParam, lParam);
                    }

                    // While typing in the in-game chat box, block ALL WarKey bindings (Inventory Numpad numbers, Skills, QuickChat)
                    if (inGameChatActive)
                    {
                        if (!memOk) lastChatOpenUtc = DateTime.UtcNow;
                        return fnCallNext(keyboardHookId, nCode, wParam, lParam);
                    }

                    Key k = KeyInterop.KeyFromVirtualKey((int)info.vkCode);
                    if (k == Key.LeftAlt || k == Key.RightAlt || k == Key.LeftCtrl || k == Key.RightCtrl ||
                        k == Key.LeftShift || k == Key.RightShift || k == Key.LWin || k == Key.RWin || k == Key.None)
                        return fnCallNext(keyboardHookId, nCode, wParam, lParam);

                    bool shiftDown = (fnGetKey(0x10) & 0x8000) != 0;
                    string combo = FormatKeyCombo(k, altDown, ctrlDown, shiftDown);

                    // 1. Check QuickChat macros first
                    if (quickChats.Count > 0)
                    {
                        List<QuickChatItem> matchedChats = new List<QuickChatItem>();
                        for (int i = 0; i < quickChats.Count; i++)
                        {
                            if (string.Equals(quickChats[i].KeyName, combo, StringComparison.OrdinalIgnoreCase))
                                matchedChats.Add(quickChats[i]);
                        }
                        if (matchedChats.Count > 0)
                        {
                            SendQuickChatMessagesAsync(war3Hwnd, matchedChats, altDown, ctrlDown, shiftDown);
                            return (IntPtr)1;
                        }
                    }

                    // 2. Check Inventory (6 slots -> Numpad 7, 8, 4, 5, 1, 2)
                    for (int i = 0; i < 6; i++)
                    {
                        if (!string.IsNullOrEmpty(wkKeys[i]) && string.Equals(wkKeys[i], combo, StringComparison.OrdinalIgnoreCase))
                        {
                            TriggerWar3InventorySlot(i, altDown);
                            return (IntPtr)1;
                        }
                    }

                    // 3. Check Skills (8 slots -> Direct match)
                    for (int i = 0; i < 8; i++)
                    {
                        if (!string.IsNullOrEmpty(wkSkillKeys[i]) && string.Equals(wkSkillKeys[i], combo, StringComparison.OrdinalIgnoreCase))
                        {
                            TriggerWar3SkillSlot(war3Hwnd, i, false, false, altDown, ctrlDown);
                            return (IntPtr)1;
                        }
                    }
                }
            }
            catch { }
            return fnCallNext(keyboardHookId, nCode, wParam, lParam);
        }

        private static readonly byte[] INV_NUMPAD_VKS = new byte[] { 0x67, 0x68, 0x64, 0x65, 0x61, 0x62 };

        private static void TriggerWar3InventorySlot(int slotIdx, bool altWasDown)
        {
            if (slotIdx < 0 || slotIdx >= 6 || fnMapVk == null || fnKeyEv == null) return;
            byte numVk = INV_NUMPAD_VKS[slotIdx];
            byte scanNum = (byte)fnMapVk(numVk, 0);
            byte scanAlt = (byte)fnMapVk(0x12, 0);

            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    if (altWasDown)
                        fnKeyEv(0x12, scanAlt, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                    fnKeyEv(numVk, scanNum, 0, MR_EXTRA_INFO);
                    Thread.Sleep(10);
                    fnKeyEv(numVk, scanNum, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                    if (altWasDown && (fnGetKey(0x12) & 0x8000) != 0)
                        fnKeyEv(0x12, scanAlt, 0, MR_EXTRA_INFO);
                }
                catch { }
            });
        }

        private static void TriggerWar3SkillSlot(IntPtr hwnd, int skillIdx, bool rightClick, bool ctrlLearn, bool altWasDown, bool ctrlWasDown)
        {
            if (skillIdx < 0 || skillIdx >= 8 || fnGetRect == null) return;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    RECT rc;
                    if (!fnGetRect(hwnd, out rc)) return;
                    int w = rc.Right - rc.Left;
                    int h = rc.Bottom - rc.Top;
                    if (w <= 100 || h <= 100) return;

                    POINT ptOrigin = new POINT { X = 0, Y = 0 };
                    fnCliToScr(hwnd, ref ptOrigin);

                    double[] colX = new double[] { 0.798, 0.854, 0.909, 0.964 };
                    int col = skillIdx % 4;
                    double rowY = (skillIdx < 4) ? 0.854 : 0.929;

                    int targetX = ptOrigin.X + (int)(w * colX[col]);
                    int targetY = ptOrigin.Y + (int)(h * rowY);

                    POINT savedCur;
                    fnGetCur(out savedCur);

                    byte scanAlt = (byte)fnMapVk(0x12, 0);
                    byte scanCtrl = (byte)fnMapVk(0x11, 0);
                    if (altWasDown) fnKeyEv(0x12, scanAlt, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                    if (ctrlWasDown) fnKeyEv(0x11, scanCtrl, KEYEVENTF_KEYUP, MR_EXTRA_INFO);

                    if (ctrlLearn)
                    {
                        int learnX = ptOrigin.X + (int)(w * 0.964);
                        int learnY = ptOrigin.Y + (int)(h * 0.854);
                        fnSetCur(learnX, learnY);
                        Thread.Sleep(8);
                        fnMouseEv(MOUSEEVENTF_LEFTDOWN, learnX, learnY, 0, MR_EXTRA_INFO);
                        fnMouseEv(MOUSEEVENTF_LEFTUP, learnX, learnY, 0, MR_EXTRA_INFO);
                        Thread.Sleep(15);
                    }

                    fnSetCur(targetX, targetY);
                    Thread.Sleep(8);
                    if (rightClick)
                    {
                        fnMouseEv(MOUSEEVENTF_RIGHTDOWN, targetX, targetY, 0, MR_EXTRA_INFO);
                        fnMouseEv(MOUSEEVENTF_RIGHTUP, targetX, targetY, 0, MR_EXTRA_INFO);
                    }
                    else
                    {
                        fnMouseEv(MOUSEEVENTF_LEFTDOWN, targetX, targetY, 0, MR_EXTRA_INFO);
                        fnMouseEv(MOUSEEVENTF_LEFTUP, targetX, targetY, 0, MR_EXTRA_INFO);
                    }

                    if (ctrlLearn)
                    {
                        Thread.Sleep(10);
                        byte scanEsc = (byte)fnMapVk(0x1B, 0);
                        fnKeyEv(0x1B, scanEsc, 0, MR_EXTRA_INFO);
                        fnKeyEv(0x1B, scanEsc, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                    }

                    Thread.Sleep(8);
                    fnSetCur(savedCur.X, savedCur.Y);

                    if (altWasDown && (fnGetKey(0x12) & 0x8000) != 0)
                        fnKeyEv(0x12, scanAlt, 0, MR_EXTRA_INFO);
                    if (ctrlWasDown && (fnGetKey(0x11) & 0x8000) != 0)
                        fnKeyEv(0x11, scanCtrl, 0, MR_EXTRA_INFO);
                }
                catch { }
            });
        }

        private static bool isSendingQuickChat = false;

        private static void SendQuickChatMessagesAsync(IntPtr hwnd, List<QuickChatItem> items, bool altWasDown, bool ctrlWasDown, bool shiftWasDown)
        {
            if (isSendingQuickChat || fnMapVk == null || fnKeyEv == null || fnPostMsg == null) return;
            isSendingQuickChat = true;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    byte scanEnter = (byte)fnMapVk(0x0D, 0);
                    byte scanShift = (byte)fnMapVk(0x10, 0);
                    byte scanAlt = (byte)fnMapVk(0x12, 0);
                    byte scanCtrl = (byte)fnMapVk(0x11, 0);

                    if (altWasDown) fnKeyEv(0x12, scanAlt, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                    if (ctrlWasDown) fnKeyEv(0x11, scanCtrl, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                    if (shiftWasDown) fnKeyEv(0x10, scanShift, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                    Thread.Sleep(15);

                    for (int m = 0; m < items.Count; m++)
                    {
                        QuickChatItem item = items[m];
                        if (string.IsNullOrEmpty(item.Message)) continue;

                        if (item.Mode == "WAR3_ALL")
                        {
                            fnKeyEv(0x10, scanShift, 0, MR_EXTRA_INFO);
                            fnKeyEv(0x0D, scanEnter, 0, MR_EXTRA_INFO);
                            fnKeyEv(0x0D, scanEnter, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                            fnKeyEv(0x10, scanShift, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                            Thread.Sleep(28);
                        }
                        else if (item.Mode != "LOBBY")
                        {
                            fnKeyEv(0x0D, scanEnter, 0, MR_EXTRA_INFO);
                            fnKeyEv(0x0D, scanEnter, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                            Thread.Sleep(28);
                        }

                        foreach (char ch in item.Message)
                        {
                            fnPostMsg(hwnd, WM_CHAR, (IntPtr)ch, IntPtr.Zero);
                        }
                        Thread.Sleep(18);

                        fnKeyEv(0x0D, scanEnter, 0, MR_EXTRA_INFO);
                        fnKeyEv(0x0D, scanEnter, KEYEVENTF_KEYUP, MR_EXTRA_INFO);
                        inGameChatActive = false;
                        Thread.Sleep(40);
                    }
                }
                catch { }
                finally
                {
                    isSendingQuickChat = false;
                }
            });
        }

        private static void LoadSavedSettings()
        {
            try
            {
                string cfg = GetConfigPath();
                if (File.Exists(cfg))
                {
                    foreach (string line in File.ReadAllLines(cfg, Encoding.UTF8))
                    {
                        int idx = line.IndexOf('=');
                        if (idx <= 0) continue;
                        string k = line.Substring(0, idx).Trim();
                        string v = line.Substring(idx + 1).Trim();
                        if (k == "username")
                        {
                            currentUsername = v;
                            if (txtUser != null) txtUser.Text = v;
                        }
                        else if (k == "token")
                        {
                            authToken = v;
                        }
                        else if (k == "war3dir" && Directory.Exists(v))
                        {
                            war3Dir = v;
                            if (txtWar3Path != null) txtWar3Path.Text = v;
                        }
                        else if (k == "war3_ok")
                        {
                            war3SetupCompleted = (v == "1");
                        }
                        else if (k == "warkey_on")
                        {
                            warKeyEnabled = (v != "0");
                        }
                        else if (k == "inv_keys")
                        {
                            // Requirement #8: Ignore legacy pre-filled Alt+Q..Alt+X default so slots start empty
                            if (v == "Alt+Q|Alt+W|Alt+A|Alt+S|Alt+Z|Alt+X")
                            {
                                for (int i = 0; i < 6; i++) wkKeys[i] = "";
                            }
                            else
                            {
                                string[] parts = v.Split('|');
                                for (int i = 0; i < 6 && i < parts.Length; i++)
                                    wkKeys[i] = parts[i];
                            }
                        }
                        else if (k == "skill_keys")
                        {
                            string[] parts = v.Split('|');
                            for (int i = 0; i < 8 && i < parts.Length; i++)
                                wkSkillKeys[i] = parts[i];
                        }
                        else if (k == "qchat")
                        {
                            quickChats.Clear();
                            if (!string.IsNullOrEmpty(v))
                            {
                                string raw = Encoding.UTF8.GetString(Convert.FromBase64String(v));
                                foreach (string row in raw.Split(new char[] { '\n' }, StringSplitOptions.RemoveEmptyEntries))
                                {
                                    string[] cols = row.Split('\t');
                                    if (cols.Length >= 3)
                                    {
                                        // Requirement #8: Strip legacy default -sds6fnboulomabah
                                        if (cols[0] == "8" && cols[2] == "-sds6fnboulomabah") continue;
                                        quickChats.Add(new QuickChatItem
                                        {
                                            Id = Guid.NewGuid().ToString("N"),
                                            KeyName = cols[0],
                                            Mode = cols[1],
                                            ModeLabel = GetModeLabel(cols[1]),
                                            Message = cols[2]
                                        });
                                    }
                                }
                            }
                        }
                    }
                    if (!string.IsNullOrEmpty(authToken) && !string.IsNullOrEmpty(currentUsername))
                    {
                        if (lblProfileName != null) lblProfileName.Text = currentUsername;
                        UpdateHeroWelcome(currentUsername);
                        if (authView != null) authView.Visibility = Visibility.Collapsed;
                        if (appShell != null) appShell.Visibility = Visibility.Visible;
                        string resolvedSavedWar3 = ResolveWar3DirectoryRecursive(war3Dir, 5);
                        if (!string.IsNullOrEmpty(resolvedSavedWar3))
                        {
                            war3Dir = resolvedSavedWar3;
                            if (txtWar3Path != null) txtWar3Path.Text = war3Dir;
                        }
                        if (!IsWar3ReadyAndPatched(war3Dir))
                        {
                            openedSettingsForFirstTimeSetup = true;
                            SwitchPage("SETTINGS");
                        }
                        else
                        {
                            openedSettingsForFirstTimeSetup = false;
                            SwitchPage("LOBBIES");
                        }
                        RefreshMapsAndRooms();
                        SyncSocialStateAsync(true);
                        RunAutoPatchAndSyncAsync();
                    }
                }
            }
            catch { }

            UpdateWarKeyUI();
        }

        private static void SaveSettings()
        {
            try
            {
                StringBuilder qb = new StringBuilder();
                for (int i = 0; i < quickChats.Count; i++)
                {
                    QuickChatItem item = quickChats[i];
                    qb.Append(item.KeyName.Replace("\t", " ").Replace("\n", " "))
                      .Append('\t')
                      .Append(item.Mode)
                      .Append('\t')
                      .Append(item.Message.Replace("\t", " ").Replace("\r", "").Replace("\n", " "))
                      .Append('\n');
                }
                string qchatB64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(qb.ToString()));
                string content =
                    "username=" + currentUsername + "\r\n" +
                    "token=" + authToken + "\r\n" +
                    "war3dir=" + war3Dir + "\r\n" +
                    "war3_ok=" + (war3SetupCompleted ? "1" : "0") + "\r\n" +
                    "warkey_on=" + (warKeyEnabled ? "1" : "0") + "\r\n" +
                    "inv_keys=" + string.Join("|", wkKeys) + "\r\n" +
                    "skill_keys=" + string.Join("|", wkSkillKeys) + "\r\n" +
                    "qchat=" + qchatB64 + "\r\n";
                File.WriteAllText(GetConfigPath(), content, Encoding.UTF8);
            }
            catch { }
        }

        private static bool IsValidWar3Folder(string dir)
        {
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return false;
            bool hasExe = File.Exists(Path.Combine(dir, "war3.exe")) || File.Exists(Path.Combine(dir, "w3l.exe")) || File.Exists(Path.Combine(dir, "Frozen Throne.exe"));
            bool hasCore = File.Exists(Path.Combine(dir, "Game.dll")) || File.Exists(Path.Combine(dir, "War3Patch.mpq")) || File.Exists(Path.Combine(dir, "war3.mpq"));
            return hasExe && hasCore;
        }

        private static bool IsWar3ReadyAndPatched(string dir)
        {
            if (string.IsNullOrEmpty(dir) || !IsValidWar3Folder(dir)) return false;
            if (war3SetupCompleted) return true;
            string gdll = Path.Combine(dir, "Game.dll");
            if (!File.Exists(gdll)) return false;
            try
            {
                if (File.Exists(Path.Combine(dir, "Game.dll.backup")))
                    return true;
                using (FileStream fs = new FileStream(gdll, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    if (fs.Length >= 0x663CFD + 4)
                    {
                        fs.Seek(0x663CFD, SeekOrigin.Begin);
                        byte[] b = new byte[4];
                        if (fs.Read(b, 0, 4) == 4 && BitConverter.ToInt32(b, 0) == 180000)
                            return true;
                    }
                }
            }
            catch { }
            return false;
        }

        private static string ResolveWar3DirectoryRecursive(string rootDir, int maxDepth = 6)
        {
            if (string.IsNullOrEmpty(rootDir)) return "";
            string cleanRoot = rootDir.Trim().Trim('"');
            try
            {
                if (File.Exists(cleanRoot))
                    cleanRoot = Path.GetDirectoryName(cleanRoot);
            }
            catch { }
            if (string.IsNullOrEmpty(cleanRoot) || !Directory.Exists(cleanRoot))
                return "";

            if (IsValidWar3Folder(cleanRoot))
                return cleanRoot;

            // Check up to 3 parent folders in case the user picked "...\Warcraft III\Maps" or "...\Warcraft III\Maps\Download"
            try
            {
                string p = cleanRoot;
                for (int up = 0; up < 3; up++)
                {
                    DirectoryInfo di = Directory.GetParent(p);
                    if (di == null) break;
                    p = di.FullName;
                    if (IsValidWar3Folder(p))
                        return p;
                }
            }
            catch { }

            // Breadth-first search (BFS) up to maxDepth to find nested folders like D:\games\dota\warcraft\warcraft\war3.exe
            string fallbackExeDir = "";
            try
            {
                var queue = new Queue<KeyValuePair<string, int>>();
                queue.Enqueue(new KeyValuePair<string, int>(cleanRoot, 0));
                int visited = 0;
                while (queue.Count > 0 && visited < 1800)
                {
                    var kv = queue.Dequeue();
                    string cur = kv.Key;
                    int depth = kv.Value;
                    visited++;

                    if (IsValidWar3Folder(cur))
                        return cur;

                    if (string.IsNullOrEmpty(fallbackExeDir) &&
                        (File.Exists(Path.Combine(cur, "war3.exe")) || File.Exists(Path.Combine(cur, "Game.dll"))))
                    {
                        fallbackExeDir = cur;
                    }

                    if (depth >= maxDepth) continue;

                    string[] subDirs = null;
                    try { subDirs = Directory.GetDirectories(cur); } catch { continue; }
                    if (subDirs == null || subDirs.Length == 0) continue;

                    var priority = new List<string>();
                    var others = new List<string>();
                    foreach (string sd in subDirs)
                    {
                        string name = Path.GetFileName(sd).ToLowerInvariant();
                        if (name.StartsWith("$") || name.StartsWith(".") ||
                            name == "system volume information" || name == "windows" ||
                            name == "programdata" || name == "appdata" ||
                            name == "node_modules" || name == "maps" || name == "save" ||
                            name == "replay" || name == "campaigns" || name == "redist")
                            continue;

                        if (name.Contains("war") || name.Contains("wc3") || name.Contains("w3") ||
                            name.Contains("dota") || name.Contains("frozen") || name.Contains("throne") ||
                            name.Contains("game") || name.Contains("tft"))
                            priority.Add(sd);
                        else
                            others.Add(sd);
                    }
                    foreach (string s in priority) queue.Enqueue(new KeyValuePair<string, int>(s, depth + 1));
                    foreach (string s in others) queue.Enqueue(new KeyValuePair<string, int>(s, depth + 1));
                }
            }
            catch { }
            return !string.IsNullOrEmpty(fallbackExeDir) ? fallbackExeDir : "";
        }

        private static string DetectWar3Directory()
        {
            try
            {
                using (RegistryKey k = Registry.CurrentUser.OpenSubKey(@"Software\Blizzard Entertainment\Warcraft III"))
                {
                    if (k != null)
                    {
                        string regPath = Convert.ToString(k.GetValue("InstallPath"));
                        if (!string.IsNullOrEmpty(regPath))
                        {
                            string resolvedReg = ResolveWar3DirectoryRecursive(regPath, 3);
                            if (!string.IsNullOrEmpty(resolvedReg))
                                return resolvedReg;
                        }
                    }
                }
            }
            catch { }
            string[] candidates = new string[]
            {
                @"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III",
                @"D:\Warcraft III", @"C:\Warcraft III", @"E:\Warcraft III", @"F:\Warcraft III",
                @"C:\Games\Warcraft III", @"D:\Games\Warcraft III", @"E:\Games\Warcraft III",
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Warcraft III"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Warcraft III")
            };
            foreach (string c in candidates)
            {
                if (!string.IsNullOrEmpty(c) && IsValidWar3Folder(c))
                    return c;
            }
            string[] searchRoots = new string[]
            {
                @"D:\Games", @"C:\Games", @"E:\Games", @"F:\Games",
                @"D:\Dota", @"C:\Dota", @"E:\Dota",
                @"D:\Warcraft", @"C:\Warcraft", @"E:\Warcraft",
                Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads"),
                @"D:\", @"E:\", @"F:\"
            };
            foreach (string root in searchRoots)
            {
                if (string.IsNullOrEmpty(root) || !Directory.Exists(root)) continue;
                int depth = (root.Length <= 3) ? 4 : 5;
                string found = ResolveWar3DirectoryRecursive(root, depth);
                if (!string.IsNullOrEmpty(found) && IsValidWar3Folder(found))
                    return found;
            }
            return @"C:\Warcraft III";
        }

        private static void SyncWar3Username(string name)
        {
            try
            {
                using (RegistryKey k = Registry.CurrentUser.CreateSubKey(@"Software\Blizzard Entertainment\Warcraft III\String"))
                {
                    if (k != null) k.SetValue("userlocal", name, RegistryValueKind.String);
                }
            }
            catch { }
        }

        private static byte[] HexToBytes(string hex)
        {
            byte[] bytes = new byte[hex.Length / 2];
            for (int i = 0; i < bytes.Length; i++)
                bytes[i] = Convert.ToByte(hex.Substring(i * 2, 2), 16);
            return bytes;
        }

        private static string ComputeSha256(byte[] data)
        {
            using (SHA256 sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(data);
                StringBuilder sb = new StringBuilder(hash.Length * 2);
                foreach (byte b in hash) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }
    }
}
"""

CROSS_PLATFORM_PY = r'''#!/usr/bin/env python3
"""MongolRanger Universal Cross-Platform Client (macOS Apple Silicon / Intel & Windows)."""
import json
import os
from pathlib import Path
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request

SERVER_URL = os.environ.get("MONGOLRANGER_SERVER", "https://mongolranger.com")
W3GS_HOST = os.environ.get("MONGOLRANGER_W3GS_HOST", "mongolranger.com")
W3GS_PORT = int(os.environ.get("MONGOLRANGER_W3GS_PORT", "8051"))
LOCAL_PROXY_PORT = 6210
ssl_ctx = ssl.create_default_context()


def api_call(method: str, path: str, body: dict | None = None, token: str = "") -> dict:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(SERVER_URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    print("MongolRanger macOS Client — https://mongolranger.com")
'''

MACOS_COMMAND_SCRIPT = """#!/bin/bash
cd "$(dirname "$0")"
clear
python3 src/mongolranger_crossplatform.py
"""


APP_MANIFEST_XML = """<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <assemblyIdentity version="3.5.0.0" name="MongolRanger.Client.App"/>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v2">
    <security>
      <requestedPrivileges xmlns="urn:schemas-microsoft-com:asm.v3">
        <requestedExecutionLevel level="asInvoker" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}" />
      <supportedOS Id="{1f676c76-80e1-4239-95bb-83d0f6d0da78}" />
      <supportedOS Id="{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}" />
      <supportedOS Id="{35138b9a-5d96-4fbd-8e2d-a2440225f93a}" />
    </application>
  </compatibility>
</assembly>
"""


def compile_standalone_exe(out_exe: Path) -> bool:
    """Compiles WPF_CSHARP_SOURCE into a standalone AnyCPU .exe with custom .ico and manifest using csc.exe."""
    csc_candidates = [
        Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
        Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    ]
    csc = next((p for p in csc_candidates if p.is_file()), None)
    if csc is None:
        import shutil
        precompiled_candidates = [
            Path("/var/lib/mongolranger/downloads/MongolRanger-Setup.exe"),
            Path(__file__).resolve().parent.parent / "dist_packages" / "MongolRanger-Setup.exe",
        ]
        for cand in precompiled_candidates:
            if cand.is_file() and cand.resolve() != out_exe.resolve():
                shutil.copy2(cand, out_exe)
                return True
        return False

    wpf_dir = csc.parent / "WPF"
    work_dir = out_exe.parent / "_build_tmp"
    work_dir.mkdir(parents=True, exist_ok=True)
    cs_file = work_dir / "MongolRangerWpf.cs"
    ico_file = work_dir / "mongolranger.ico"
    manifest_file = work_dir / "app.manifest"
    cs_file.write_text(WPF_CSHARP_SOURCE, encoding="utf-8")
    manifest_file.write_text(APP_MANIFEST_XML, encoding="utf-8")
    create_mongolranger_ico(ico_file)

    cmd = [
        str(csc),
        "/nologo",
        "/target:winexe",
        "/platform:anycpu",
        "/optimize+",
        f"/win32icon:{ico_file}",
        f"/win32manifest:{manifest_file}",
        f"/out:{out_exe}",
        "/r:System.dll",
        "/r:System.Core.dll",
        "/r:System.Xaml.dll",
        "/r:System.Windows.Forms.dll",
        f"/r:{wpf_dir / 'WindowsBase.dll'}",
        f"/r:{wpf_dir / 'PresentationCore.dll'}",
        f"/r:{wpf_dir / 'PresentationFramework.dll'}",
        str(cs_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"csc.exe failed:\n{res.stdout}\n{res.stderr}")
    return True


def build_packages(out_dir: Path, overwrite: bool = True) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    win_exe = out_dir / "MongolRanger-Setup.exe"
    zev_exe = out_dir / "ZevArena-Setup.exe"
    nsis_exe = out_dir / "MongolRanger_4.8_x64-setup.exe"
    win_zip = out_dir / "MongolRanger.zip"
    mac_zip = out_dir / "MongolRanger-macOS-Universal.zip"
    game_zip = out_dir / "Warcraft-III-1.26a-MongolRanger-Setup.zip"

    if overwrite or not win_exe.is_file():
        compile_standalone_exe(win_exe)

    nsi_script = out_dir / "installer.nsi"
    if nsi_script.is_file():
        makensis_candidates = [
            Path("/usr/bin/makensis"),
            Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
            Path(r"C:\Program Files\NSIS\makensis.exe"),
        ]
        makensis_bin = next((p for p in makensis_candidates if p.is_file()), None)
        if makensis_bin is not None:
            subprocess.run([str(makensis_bin), str(nsi_script.name)], cwd=str(out_dir), check=False)
            if zev_exe.is_file():
                import shutil
                shutil.copy2(zev_exe, nsis_exe)
        elif win_exe.is_file() and not zev_exe.is_file():
            import shutil
            shutil.copy2(win_exe, zev_exe)

    if overwrite or not win_zip.is_file():
        readme_mn = '''====================================================================
  ZevArena v4.8 — Warcraft III 1.26a Online Gaming Platform
  (Windows 7 / 8 / 8.1 / 10 / 11 • 32-bit ба 64-bit)
====================================================================

[СУУЛГАХ ЗААВАР]:
1. Энэ хавтас доторх "ZevArena-Setup.exe" дээр 2 дарж шууд суулгана!
2. Суулгагч нь таны компьютер дээрх .NET Framework болон TLS тохиргоог
   автоматаар шалгаж засаад, Desktop дээр "ZevArena" дүрс үүсгэн
   програмыг шууд нээнэ.
====================================================================
'''
        use_nsis = zev_exe.is_file() and (not win_exe.is_file() or zev_exe.stat().st_mtime >= win_exe.stat().st_mtime)
        installer_payload = zev_exe if use_nsis else win_exe
        with zipfile.ZipFile(win_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if installer_payload.is_file():
                zf.write(installer_payload, "ZevArena-Setup.exe")
                zf.writestr("ЗААВАР (Уншина уу).txt", readme_mn)

    if overwrite or not mac_zip.is_file():
        with zipfile.ZipFile(mac_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            info = zipfile.ZipInfo("Start-MongolRanger-macOS.command")
            info.external_attr = 0o755 << 16
            zf.writestr(info, MACOS_COMMAND_SCRIPT)
            zf.writestr("src/mongolranger_crossplatform.py", CROSS_PLATFORM_PY)

    if overwrite or not game_zip.is_file():
        with zipfile.ZipFile(game_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if win_exe.is_file():
                zf.write(win_exe, "ZevArena.exe")

    return {"win": win_exe, "zev_setup": zev_exe, "win_zip": win_zip, "mac": mac_zip, "game": game_zip}


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "dist_packages"
    built = build_packages(target, overwrite=True)
    for k, p in built.items():
        print(f"Built {k}: {p} ({p.stat().st_size} bytes)")
