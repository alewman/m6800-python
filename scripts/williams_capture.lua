-- m6800-python: capture a Williams sound board's inputs and outputs from MAME
-- 0.285, for scripts/williams_sound.py (milestone 4).
--
--   mame robotron -autoboot_script scripts/williams_capture.lua ...
--   (see scripts/williams_sound.py for the whole command line)
--
-- Writes WILLIAMS_CAPTURE_FILE (default williams.capture), one event per line,
-- with MAME's machine time in seconds:
--   C <time> <value>        a sound command reaching the sound PIA's port B
--                           (value = main PIA port B output | $C0, as
--                           williams_m.cpp's snd_cmd_w delivers it; CB1 goes
--                           high unless the value is $FF)
--   W <time> <offset> <value>  a sound-CPU write to its PIA ($0400-$0403 or
--                           the $8400 mirror), offset 0-3
--   E <time>                the end of the run
--
-- The main board's PIA 1 (port B = the sound command) sits at $C80C-$C80F on
-- the 6809.  Its port B output is tracked here from the writes: offset 2 is
-- the data or the DDR, as CRB bit 2 selects, and offset 3 is CRB; MAME sends
-- (output AND DDR) on every data write and every DDR change
-- (6821pia.cpp, get_out_b_value / send_to_out_b_func).
--
-- M6800_PRESS works as in mame_trace.lua: "PORT:FIELD:FRAME:HOLD[;...]".

local out = io.open(os.getenv("WILLIAMS_CAPTURE_FILE") or "williams.capture", "w")
local main = manager.machine.devices[":maincpu"].spaces["program"]
local sound = manager.machine.devices[":soundcpu"].spaces["program"]
local function now() return manager.machine.time:as_double() end

local crb, ddrb, outb = 0, 0, 0
local function send()
	out:write(string.format("C %.9f %d\n", now(), (outb & ddrb) | 0xC0))
end
-- Global, not local: a tap is removed when its handle is garbage-collected.
WILLIAMS_TAPS = {}
local taps = WILLIAMS_TAPS
taps[#taps + 1] = main:install_write_tap(0xC80E, 0xC80F, "sndcmd", function(offset, data, mask)
	if offset == 0xC80F then
		crb = data
	elseif crb & 0x04 ~= 0 then
		outb = data
		send()
	else
		local changed = data ~= ddrb
		ddrb = data
		if changed then send() end
	end
	return data
end)
for _, base in ipairs({0x0400, 0x8400}) do
	taps[#taps + 1] = sound:install_write_tap(base, base + 3, "soundpia" .. base, function(offset, data, mask)
		out:write(string.format("W %.9f %d %d\n", now(), offset - base, data))
		return data
	end)
end

local press = os.getenv("M6800_PRESS")
if press and press ~= "" then
	local schedule = {}
	for spec in press:gmatch("[^;]+") do
		local port, field, at, hold = spec:match("^([^:]+):([^:]+):(%d+):(%d+)$")
		schedule[#schedule + 1] = {
			button = manager.machine.ioport.ports[":" .. port].fields[field],
			at = tonumber(at), hold = tonumber(hold), name = port .. ":" .. field,
		}
	end
	local frames = 0
	emu.register_frame_done(function()
		frames = frames + 1
		for _, item in ipairs(schedule) do
			if frames == item.at then item.button:set_value(1) end
			if frames == item.at + item.hold then item.button:set_value(0) end
		end
	end)
end
emu.register_stop(function()
	out:write(string.format("E %.9f\n", now()))  -- when MAME stopped
	out:close()
end)
print("CAPTURE: taps installed")
