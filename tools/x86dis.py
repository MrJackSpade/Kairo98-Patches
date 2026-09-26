import sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
f, a, b = sys.argv[1], int(sys.argv[2],16), int(sys.argv[3],16)
d = open(f,"rb").read()
md = Cs(CS_ARCH_X86, CS_MODE_16)
for i in md.disasm(d[a:b], a+0x100):
    print("%04x: %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
