/*
 * m6800-python: single-step harness around sim68xx's MC6800 core (rung 5).
 *
 * Linked against the object files of sim68xx (https://github.com/dg1yfe/sim68xx,
 * GPL-2.0) built in third_party/, which this repository does not commit.
 * Reads one case per line on stdin:
 *     pc s x a b cc n addr value ... (n pairs, decimal)
 * runs one instruction with instr_exec(), and prints
 *     pc s x a b cc cycles addr value ... (the same addresses, final values)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "defs.h"
#include "chip.h"
#include "cpu.h"
#include "memory.h"
#include "reg.h"

extern u_int ireg_start;
extern u_char *ram;
int instr_exec(void);

int board_install(void) { return 0; }

int main(void)
{
    static unsigned addr[65536], value[65536];
    unsigned pc, s, x, a, b, cc, n, i;
    mem_init();
    ireg_start = 0x20000;  /* no Altair ACIA: every address is plain memory */
    while (scanf("%u %u %u %u %u %u %u", &pc, &s, &x, &a, &b, &cc, &n) == 7) {
        memset(ram, 0, 65536);
        for (i = 0; i < n; i++) {
            scanf("%u %u", &addr[i], &value[i]);
            ram[addr[i]] = value[i];
        }
        reg_setpc(pc); reg_setsp(s); reg_setix(x);
        reg_setacca(a); reg_setaccb(b); reg_setccr(cc);
        cpu_setncycles(0);
        instr_exec();
        printf("%u %u %u %u %u %u %u", reg_getpc(), reg_getsp(), reg_getix(),
               reg_getacca(), reg_getaccb(), reg_getccr(), cpu_getncycles());
        for (i = 0; i < n; i++) printf(" %u %u", addr[i], ram[addr[i]]);
        putchar('\n');
    }
    return 0;
}
