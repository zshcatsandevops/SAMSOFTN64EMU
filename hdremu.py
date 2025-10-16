#!/usr/bin/env python3
"""
EMU64 Rel-Edition (600×400 Compact GUI)
Combines core CPU emulation + test harness inside a Tkinter shell.

© 2025 FlamesCo & Samsoft
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import struct, time, threading

# ============================================================
# Core: Memory + CPU
# ============================================================
class N64Memory:
    def __init__(self):
        self.rdram = bytearray(8 * 1024 * 1024)
        self.rom = bytearray(64 * 1024 * 1024)

    def virtual_to_physical(self, address):
        address &= 0xFFFFFFFF
        if 0x80000000 <= address <= 0x9FFFFFFF or 0xA0000000 <= address <= 0xBFFFFFFF:
            return address & 0x1FFFFFFF
        return address

    def read32(self, address):
        p = self.virtual_to_physical(address)
        if p + 3 < len(self.rdram):
            return struct.unpack('>I', self.rdram[p:p+4])[0]
        return 0

    def write32(self, address, value):
        p = self.virtual_to_physical(address)
        if p + 3 < len(self.rdram):
            self.rdram[p:p+4] = struct.pack('>I', value & 0xFFFFFFFF)


class MIPSR4300i:
    def __init__(self, mem):
        self.gpr = [0]*32
        self.pc = 0xA4000040
        self.next_pc = self.pc+4
        self.hi = self.lo = 0
        self.memory = mem
        self.cycles = 0

    def reset(self):
        self.gpr = [0]*32
        self.pc = 0xA4000040
        self.next_pc = self.pc + 4
        self.hi = self.lo = 0
        self.cycles = 0

    def fetch(self):
        try: return self.memory.read32(self.pc)
        except: return 0

    def decode_execute(self, ins):
        op = (ins>>26)&0x3F
        rs=(ins>>21)&0x1F; rt=(ins>>16)&0x1F; rd=(ins>>11)&0x1F
        sh=(ins>>6)&0x1F; fn=ins&0x3F; imm=ins&0xFFFF; tgt=ins&0x3FFFFFF
        imm_se = imm|0xFFFFFFFFFFFF0000 if imm&0x8000 else imm
        self.gpr[0]=0
        if op==0x00: self._special(rs,rt,rd,sh,fn)
        elif op==0x02: self.next_pc=(self.pc&0xF0000000)|(tgt<<2)
        elif op==0x03: self.gpr[31]=self.pc+8; self.next_pc=(self.pc&0xF0000000)|(tgt<<2)
        elif op==0x04 and self.gpr[rs]==self.gpr[rt]: self.next_pc=self.pc+4+(imm_se<<2)
        elif op==0x05 and self.gpr[rs]!=self.gpr[rt]: self.next_pc=self.pc+4+(imm_se<<2)
        elif op==0x08 or op==0x09: self.gpr[rt]=(self.gpr[rs]+imm_se)&0xFFFFFFFFFFFFFFFF
        elif op==0x0C: self.gpr[rt]=self.gpr[rs]&imm
        elif op==0x0D: self.gpr[rt]=self.gpr[rs]|imm
        elif op==0x0F: self.gpr[rt]=(imm<<16)&0xFFFFFFFFFFFFFFFF
        elif op==0x23: self.gpr[rt]=self.memory.read32(self.gpr[rs]+imm_se)
        elif op==0x2B: self.memory.write32(self.gpr[rs]+imm_se,self.gpr[rt])
        self.gpr[0]=0; self.cycles+=1

    def _special(self,rs,rt,rd,sh,fn):
        if fn==0x00: self.gpr[rd]=(self.gpr[rt]<<sh)&0xFFFFFFFFFFFFFFFF
        elif fn==0x02: self.gpr[rd]=(self.gpr[rt]>>sh)&0xFFFFFFFFFFFFFFFF
        elif fn==0x08: self.next_pc=self.gpr[rs]
        elif fn==0x09: self.gpr[rd]=self.pc+8; self.next_pc=self.gpr[rs]
        elif fn==0x12: self.gpr[rd]=self.lo
        elif fn==0x18: r=self.gpr[rs]*self.gpr[rt]; self.lo=r&0xFFFFFFFF; self.hi=(r>>32)&0xFFFFFFFF
        elif fn==0x20 or fn==0x21: self.gpr[rd]=(self.gpr[rs]+self.gpr[rt])&0xFFFFFFFFFFFFFFFF
        elif fn==0x22 or fn==0x23: self.gpr[rd]=(self.gpr[rs]-self.gpr[rt])&0xFFFFFFFFFFFFFFFF
        elif fn==0x24: self.gpr[rd]=self.gpr[rs]&self.gpr[rt]
        elif fn==0x25: self.gpr[rd]=self.gpr[rs]|self.gpr[rt]

    def step(self):
        ins=self.fetch(); self.decode_execute(ins)
        self.pc=self.next_pc; self.next_pc=self.pc+4


# ============================================================
# GUI: Compact 600×400 Interface
# ============================================================
class EMU64RelGUI:
    def __init__(self, root):
        self.root=root
        self.root.title("EMU64 Rel-Edition (600×400)")
        self.root.geometry("600x400")
        self.root.resizable(False,False)
        self.mem=N64Memory()
        self.cpu=MIPSR4300i(self.mem)

        self.text=scrolledtext.ScrolledText(root,width=70,height=22,bg="#111",fg="#0f0",
                                            insertbackground="#0f0",font=("Consolas",10))
        self.text.pack(fill=tk.BOTH,expand=True,padx=4,pady=4)

        bar=ttk.Frame(root); bar.pack(fill=tk.X)
        ttk.Button(bar,text="Reset",command=self.reset_cpu).pack(side=tk.LEFT,padx=3)
        ttk.Button(bar,text="Step",command=self.step_once).pack(side=tk.LEFT,padx=3)
        ttk.Button(bar,text="Run Tests",command=self.run_tests).pack(side=tk.LEFT,padx=3)

        self.print_line("EMU64 Rel-Edition initialized.")
        self.print_line("Ready. Click [Run Tests] to validate CPU core.")

    def print_line(self,txt): self.text.insert(tk.END,txt+"\n"); self.text.see(tk.END)
    def reset_cpu(self): self.cpu.reset(); self.print_line("CPU Reset.")

    def step_once(self):
        self.cpu.step()
        self.print_line(f"Stepped to PC=0x{self.cpu.pc:08X}, Cycles={self.cpu.cycles}")

    # Merge of test_emu64.py condensed for GUI
    def run_tests(self):
        c=self.cpu; m=self.mem; c.reset()
        self.print_line("Running MIPS test suite…")
        try:
            # ADDI
            c.decode_execute(0x20010064); assert c.gpr[1]==100
            # ORI
            c.decode_execute(0x3402FF00); assert c.gpr[2]==0xFF00
            # ADD
            c.decode_execute(0x00221820); assert c.gpr[3]==100+0xFF00
            # SUB
            c.decode_execute(0x00412022); assert c.gpr[4]==0xFF00-100
            # AND
            c.gpr[1]=0xF0F0; c.gpr[2]=0xFF00
            c.decode_execute(0x00412824); assert c.gpr[5]==(0xF0F0&0xFF00)
            # LUI
            c.decode_execute(0x3C061234); assert c.gpr[6]==0x12340000
            # MULT/MFLO
            c.gpr[1]=100; c.gpr[2]=200; c.decode_execute(0x00220018)
            c.decode_execute(0x00001812); assert c.gpr[3]==20000
            self.print_line("✅ All CPU tests passed.")
        except AssertionError as e:
            self.print_line("❌ Test failed: "+str(e))
        self.print_line(f"Cycles executed: {c.cycles}")

# ============================================================
def main():
    root=tk.Tk()
    EMU64RelGUI(root)
    root.mainloop()

if __name__=="__main__":
    main()
