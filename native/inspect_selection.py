"""Read-only, hash-pinned disassembly of the local selection command paths."""
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runtime/tooldeps"))
import capstone
import pefile

path = ROOT / "runtime/package-v1/Game/game.dll"
data = path.read_bytes()
if hashlib.sha256(data).hexdigest() != "6d21bd9a0f9fbc8446f455c9e89ac994fed68174426fe608fcb9baefd4dec53c":
    raise ValueError("Unsupported binary: offsets have only been checked for the pinned local file")
pe = pefile.PE(data=data)
dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
regions = [("selection constructor", 0x2c8e50, 0x44),
           ("selection sender", 0x2cc350, 0x80),
           ("selection command serializer and enqueue caller", 0x2ca010, 0xb8),
           ("selection decoder dispatch", 0x540fd0, 0x130),
           ("selection field deserializer", 0x554320, 0x2a),
           ("incoming action validation and own sent-command queue", 0x67e3d0, 0x3e0)]
lines = [f"SHA256 {hashlib.sha256(data).hexdigest()}",
         "Addresses below are static preferred addresses, not a patch specification."]
for label, rva, size in regions:
    lines.append(f"\n{label} (RVA {rva:x})")
    for ins in dis.disasm(pe.get_data(rva, size), pe.OPTIONAL_HEADER.ImageBase + rva):
        lines.append(f"{ins.address:08x}  {ins.bytes.hex():20} {ins.mnemonic} {ins.op_str}")
output = ROOT / "runtime/native/selection-disassembly.txt"
output.write_text("\n".join(lines))
print(output)
