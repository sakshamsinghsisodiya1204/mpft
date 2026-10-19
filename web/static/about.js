MP.views.about = function (root) {
  const h = MP.h, hdr = [["magic", "2", "'MP'"], ["ver", "1", "1"], ["type", "1", "1 to 8"], ["session", "4", "random id"], ["chunk index", "4", ""], ["payload len", "4", ""], ["crc32", "4", "of first 16 bytes"]];
  root.append(h("h1", {}, "About MPFT"),
    h("section", { class: "panel" }, h("h2", {}, "Problem"), h("p", {}, "One TCP connection uses one network path. If that path is slow it limits the transfer, and if it breaks the transfer fails. MPFT splits a file into chunks and sends them over several TCP connections at once, so the transfer uses all paths and survives the loss of one.")),
    h("section", { class: "panel" }, h("h2", {}, "Header (20 bytes, big-endian)"),
    h("pre", {}, "0       2   3   4           8          12          16          20\n+-------+---+---+-----------+-----------+-----------+-----------+\n| 'MP'  |ver|typ| session   | chunk idx | payload   | crc32 of  |\n|       |   |   |           |           | length    | bytes 0-15|\n+-------+---+---+-----------+-----------+-----------+-----------+"),
    MP.table(["Field", "Bytes", "Value"], hdr, [1])),
    h("section", { class: "panel" }, h("h2", {}, "Message types"),
    MP.table(["Type", "Name", "Purpose"], [[1, "HELLO", "A path connects and names the session"], [2, "MANIFEST", "File name, size, per-chunk and whole-file SHA-256 (JSON)"], [3, "MANIFEST_ACK", "Chunks the receiver already holds (resume)"],
      [4, "CHUNK", "One chunk of data"], [5, "ACK", "Chunk verified and written"], [6, "NACK", "Chunk hash did not match, send it again"], [7, "DONE", "Sender is finished; receiver checks the whole file and answers"], [8, "ERROR", "Something went wrong"]], [0])),
    h("section", { class: "panel" }, h("h2", {}, "Work stealing"),
    h("p", {}, "All paths take the next chunk index from one shared queue. A fast path comes back for work sooner and so carries more chunks; a slow path carries fewer. Nothing is assigned in advance. If a path times out, dies or gets a NACK, the chunk goes back on the queue (retries first, up to 5 times with exponential backoff) and another path picks it up.")),
    h("section", { class: "panel" }, h("h2", {}, "Integrity"),
    h("p", {}, "The receiver checks every chunk against the manifest hash before it ACKs, writes it at its offset in a .part file, and checks the whole-file SHA-256 before renaming. The Transfer page shows both checks.")),
    h("section", { class: "panel" }, h("h2", {}, "Emulator and Wireshark"),
    h("p", {}, "A network condition on the Send page puts small TCP proxies between sender and receiver. Each proxy is one path with its own delay, jitter, rate limit, corruption and failure time. The data still travels as real MPFT over real TCP, so a Wireshark capture with wireshark/mpft.lua shows the same messages the trace panel lists.")),
    h("section", { class: "panel" }, h("h2", {}, "Security"),
    h("p", {}, "There is no built-in encryption. Across networks use Tailscale, which encrypts with WireGuard. The page controls this machine, so it only listens on 127.0.0.1.")));
};
