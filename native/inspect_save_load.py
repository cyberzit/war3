"""Read-only save/load native registration and RTTI reconnaissance, pinned 1.26a."""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runtime/tooldeps"))
import pefile
import capstone

GAME = Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III\game.dll")
data = GAME.read_bytes()
sha = hashlib.sha256(data).hexdigest()
if sha != "6d21bd9a0f9fbc8446f455c9e89ac994fed68174426fe608fcb9baefd4dec53c":
    raise ValueError("Unsupported game.dll; offsets require separate validation")
pe = pefile.PE(data=data)
base = pe.OPTIONAL_HEADER.ImageBase
dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)

def occurrences(needle):
    pos = 0
    while (pos := data.find(needle, pos)) >= 0:
        yield pos
        pos += 1

def va(offset):
    return base + pe.get_rva_from_offset(offset)

results = []
functions = {}
for name in ("SaveGame", "LoadGame", "SaveGameExists", "RenameSaveDirectory",
             "CopySaveGame", "ReloadGame", ".?AVCSaveGame@@"):
    for offset in occurrences(name.encode() + b"\0"):
        if offset and data[offset - 1] not in (0,):
            continue
        address = va(offset)
        refs = []
        for ref in occurrences(struct.pack("<I", address)):
            section = pe.get_section_by_rva(pe.get_rva_from_offset(ref))
            entry = {"rva": hex(va(ref) - base), "section": section.Name.rstrip(b"\0").decode()}
            if (section.Characteristics & 0x20000000 and data[ref-1] == 0xba
                    and data[ref+4] == 0xb9 and data[ref+9] == 0xe8):
                target = struct.unpack_from("<I", data, ref+5)[0] - base
                entry["registered_function_rva"] = hex(target)
                functions.setdefault(name, set()).add(target)
            # A push-imm32 reference is an exact instruction boundary.
            if section.Characteristics & 0x20000000 and data[ref - 1] == 0x68:
                entry["instructions_from_push"] = [
                    f"{i.address-base:08x}: {i.mnemonic} {i.op_str}"
                    for i in dis.disasm(data[ref-1:ref+35], va(ref-1))]
            refs.append(entry)
        results.append({"name": name, "string_rva": hex(address-base), "references": refs})
        if name.startswith(".?AV"):
            descriptor = address-8
            locators = []
            for ref in occurrences(struct.pack("<I", descriptor)):
                if ref < 12 or struct.unpack_from("<I", data, ref-12)[0] != 0:
                    continue
                locator = va(ref-12)
                for vref in occurrences(struct.pack("<I", locator)):
                    entries = struct.unpack_from("<6I", data, vref+4)
                    locators.append({"locator_rva": hex(locator-base),
                                     "candidate_vtable_rva": hex(va(vref+4)-base),
                                     "first_six_entries": [hex(v-base) for v in entries]})
            results[-1]["rtti_candidates"] = locators
out = ROOT / "runtime/native/save-load-discovery.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"source": str(GAME), "sha256": sha,
                          "status": "static candidates; no runtime validation", "symbols": results}, indent=2))
print(out)
for result in results:
    print(json.dumps(result))
lines = ["Static registered entry points; direct call labels have not been inferred."]
for name, targets in functions.items():
    for target in sorted(targets):
        lines.append(f"\n{name} RVA {target:08x}")
        for i in dis.disasm(pe.get_data(target, 256), base+target):
            lines.append(f"{i.address-base:08x}: {i.bytes.hex():20} {i.mnemonic} {i.op_str}")
            if i.mnemonic.startswith("ret"):
                break
(out.parent / "save-load-entrypoints.txt").write_text("\n".join(lines))
regions = [(0x3b28c0, 32), (0x3a4c70, 0x300), (0x3af8d0, 0x240),
           (0x443860, 0x180), (0x4c7340, 0x106), (0x4c7830, 0x200)]
lines = ["Fixed-size disassembly windows, not recovered full function boundaries."]
for rva, size in regions:
    lines.append(f"\nCandidate callee RVA {rva:08x}")
    lines.extend(f"{i.address-base:08x}: {i.mnemonic} {i.op_str}"
                 for i in dis.disasm(pe.get_data(rva, size), base+rva))
(out.parent / "save-load-callees.txt").write_text("\n".join(lines))
