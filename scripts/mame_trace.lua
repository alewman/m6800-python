-- m6800-python: MAME 0.285 instruction-trace script for a 6800-family CPU.
--
-- Run via scripts/mame_trace.sh; see docs/mame-oracle.md for what it produces
-- and for the gotchas this script works around.
--
-- Environment:
--   M6800_TRACE_TAG   device tag to trace, e.g. ":maincpu" or ":soundcpu"
--                     (default ":maincpu")
--   M6800_TRACE_FILE  MAME disassembly trace file name (default "cpu.trace")
--   M6800_PRESS       "PORT:FIELD:FRAME:HOLD[;...]" -- hold inputs for HOLD frames
--                     starting at frame FRAME.  Needed when the traced CPU is
--                     a sound CPU that idles until the main board talks to it
--                     and the main board itself is waiting for a switch, as
--                     Williams's fresh-CMOS ROMs wait for Advance.
--
-- Prints the state names the chosen device exposes and the 6800 vector table,
-- then traces every instruction.  The register log goes to error.log in the
-- current working directory (MAME's -log output), one line per instruction:
--   pc a b x s cc wai totalcycles   (hex, hex, hex, hex, hex, hex, hex, dec)
-- logerror prints the values *before* the instruction at pc executes.

local tag  = os.getenv("M6800_TRACE_TAG")  or ":maincpu"
local file = os.getenv("M6800_TRACE_FILE") or "cpu.trace"

local cpu = manager.machine.devices[tag]
if cpu == nil then
	print("TAGS: no device at " .. tag .. "; the machine has:")
	for t, _ in pairs(manager.machine.devices) do print("  " .. t) end
	manager.machine:exit()
	return
end

print("DEVICE: " .. tag .. " = " .. cpu.name)

local names = {}
for k, _ in pairs(cpu.state) do names[#names + 1] = k end
table.sort(names)
print("STATE NAMES: " .. table.concat(names, " "))

-- The vector table lives at the top of the map.  $FFF8-$FFFE are the four
-- 6800 vectors; $FFF0-$FFF6 are the 6801/6803 on-chip peripheral vectors and
-- read as ordinary ROM on a plain 6800.
local mem = cpu.spaces["program"]
local labels = {
	[0xFFF0] = "SCI", [0xFFF2] = "TOF", [0xFFF4] = "OCF", [0xFFF6] = "ICF",
	[0xFFF8] = "IRQ", [0xFFFA] = "SWI", [0xFFFC] = "NMI", [0xFFFE] = "RESET",
}
local vec = {}
for a = 0xFFF0, 0xFFFE, 2 do
	vec[#vec + 1] = string.format("%s:%04X=%04X", labels[a], a, mem:read_u16(a))
end
print("VECTORS: " .. table.concat(vec, " "))

-- Optional: hold one input for a while, to get the machine past a wait loop.
local press = os.getenv("M6800_PRESS")
if press and press ~= "" then
	local schedule = {}
	for spec in press:gmatch("[^;]+") do
		local port, field, at, hold = spec:match("^([^:]+):([^:]+):(%d+):(%d+)$")
		schedule[#schedule + 1] = {
			name = port .. ":" .. field,
			button = manager.machine.ioport.ports[":" .. port].fields[field],
			at = tonumber(at),
			hold = tonumber(hold),
		}
	end
	local frames = 0
	emu.register_frame_done(function()
		frames = frames + 1
		for _, item in ipairs(schedule) do
			if frames == item.at then
				item.button:set_value(1)
				print("PRESS: " .. item.name .. " down at frame " .. frames)
			elseif frames == item.at + item.hold then
				item.button:set_value(0)
				print("PRESS: " .. item.name .. " up at frame " .. frames)
			end
		end
	end)
end

local dbg = manager.machine.debugger
dbg.visible_cpu = cpu
dbg:command('trace ' .. file .. ',,noloop,{logerror "%X %X %X %X %X %X %X %d\\n",curpc,a,b,x,s,cc,wai,totalcycles}')
dbg:command("go")
