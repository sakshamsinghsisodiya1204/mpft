-- MPFT dissector for Wireshark. Install: copy to ~/.config/wireshark/plugins/ (macOS) and restart,
-- or run: wireshark -X lua_script:wireshark/mpft.lua
local mpft = Proto("mpft", "MPFT Multipath File Transfer")

local type_names = {
  [1] = "HELLO", [2] = "MANIFEST", [3] = "MANIFEST_ACK", [4] = "CHUNK",
  [5] = "ACK", [6] = "NACK", [7] = "DONE", [8] = "ERROR",
}

local f = {
  magic   = ProtoField.string("mpft.magic", "Magic"),
  version = ProtoField.uint8("mpft.version", "Version"),
  type    = ProtoField.uint8("mpft.type", "Type", base.DEC, type_names),
  session = ProtoField.uint32("mpft.session", "Session ID", base.HEX),
  chunk   = ProtoField.uint32("mpft.chunk", "Chunk index"),
  len     = ProtoField.uint32("mpft.len", "Payload length"),
  crc     = ProtoField.uint32("mpft.crc", "Header CRC32", base.HEX),
  payload = ProtoField.bytes("mpft.payload", "Payload"),
  json    = ProtoField.string("mpft.json", "JSON payload"),
}
mpft.fields = { f.magic, f.version, f.type, f.session, f.chunk, f.len, f.crc, f.payload, f.json }

local HEADER_LEN = 20

-- Tells dissect_tcp_pdus how long the PDU starting at `offset` is (it reassembles across TCP segments).
local function pdu_len(tvb, pinfo, offset)
  return HEADER_LEN + tvb(offset + 12, 4):uint()
end

local function dissect_pdu(tvb, pinfo, tree)
  pinfo.cols.protocol = "MPFT"
  local mtype = tvb(3, 1):uint()
  local chunk = tvb(8, 4):uint()
  local plen = tvb(12, 4):uint()
  local name = type_names[mtype] or ("type " .. mtype)

  local t = tree:add(mpft, tvb(), "MPFT " .. name)
  t:add(f.magic, tvb(0, 2))
  t:add(f.version, tvb(2, 1))
  t:add(f.type, tvb(3, 1))
  t:add(f.session, tvb(4, 4))
  t:add(f.chunk, tvb(8, 4))
  t:add(f.len, tvb(12, 4))
  t:add(f.crc, tvb(16, 4))
  if plen > 0 then
    -- MANIFEST, MANIFEST_ACK and ERROR carry text/JSON; CHUNK carries raw file bytes
    if mtype == 2 or mtype == 3 or mtype == 8 then
      t:add(f.json, tvb(HEADER_LEN, plen))
    else
      t:add(f.payload, tvb(HEADER_LEN, plen))
    end
  end

  local info = name
  if mtype == 4 or mtype == 5 or mtype == 6 then info = info .. " chunk=" .. chunk end
  if plen > 0 then info = info .. " len=" .. plen end
  pinfo.cols.info:set(info)
end

function mpft.dissector(tvb, pinfo, tree)
  dissect_tcp_pdus(tvb, tree, HEADER_LEN, pdu_len, dissect_pdu)
end

-- Default ports: receiver 9000 and emulator paths 9201-9220 (see topology.example.json)
local tcp_port = DissectorTable.get("tcp.port")
tcp_port:add(9000, mpft)
for p = 9201, 9220 do tcp_port:add(p, mpft) end

-- Web UI transfers use ephemeral ports, so also recognise MPFT by its header: "MP", version 1, type 1-8.
local function heuristic(tvb, pinfo, tree)
  if tvb:len() < HEADER_LEN or tvb(0, 2):string() ~= "MP" or tvb(2, 1):uint() ~= 1 then return false end
  local t = tvb(3, 1):uint()
  if t < 1 or t > 8 then return false end
  pinfo.conversation = mpft  -- later segments of this connection (mid-chunk) go to us too
  mpft.dissector(tvb, pinfo, tree)
  return true
end
mpft:register_heuristic("tcp", heuristic)
