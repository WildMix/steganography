/* Dependency-free, local-file-friendly visual companion. No private data is read. */
"use strict";
(() => {
  const F = window.STEGO_FIXTURE;
  const C = { ink: "#edf0e8", muted: "#9faeb0", mint: "#9ce6be", gold: "#ecc57f", purple: "#b7aff5", coral: "#ef9e85", panel: "#192628", line: "#354749", dark: "#101719" };
  const $ = id => document.getElementById(id);
  const esc = value => String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const clamp = (v, low = 0, high = 1) => Math.max(low, Math.min(high, v));
  const ease = t => { t = clamp(t); return t * t * (3 - 2 * t); };
  const mix = (a, b, t) => a + (b - a) * ease(t);
  const fmt = n => Number(n).toLocaleString("en-US");
  const bin = n => n.toString(2).padStart(8, "0");
  const bytes = hex => hex.match(/../g) || [];
  const txt = (x, y, text, size = 18, color = C.ink, anchor = "start", cls = "", extra = "") => `<text x="${x}" y="${y}" fill="${color}" font-size="${size}" text-anchor="${anchor}" class="${cls}" ${extra}>${esc(text)}</text>`;
  const box = (x, y, w, h, fill = C.panel, stroke = C.line, r = 10, extra = "") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" ${extra}/>`;
  const line = (x1, y1, x2, y2, color = C.line, width = 2, extra = "") => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${width}" ${extra}/>`;
  const circle = (x, y, r, fill = C.mint, extra = "") => `<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}" ${extra}/>`;
  const label = (x, y, text, color = C.muted, anchor = "start") => txt(x, y, text, 12, color, anchor, "mono", 'letter-spacing="1.4"');
  const arrow = (x1, y1, x2, y2, color = C.mint, width = 2) => line(x1, y1, x2, y2, color, width, 'marker-end="url(#arrow)"');
  const pill = (x, y, w, text, color = C.mint) => box(x, y, w, 30, `${color}10`, `${color}50`, 15) + txt(x + w / 2, y + 20, text, 12, color, "middle", "mono");
  const group = (content, opacity = 1, transform = "") => `<g opacity="${clamp(opacity)}" transform="${transform}">${content}</g>`;
  const image = (name, x, y, size, extra = "") => `<image href="assets/${name}.png" x="${x}" y="${y}" width="${size}" height="${size}" ${extra}/>`;
  const rule = (y = 488) => line(50, y, 850, y);
  const footer = (text, sub = "") => rule() + txt(450, 521, text, 19, C.ink, "middle") + (sub ? txt(450, 546, sub, 12, C.muted, "middle") : "");
  const defs = `<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10Z" fill="context-stroke"/></marker><pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".7" fill="#73958c" opacity=".14"/></pattern></defs><rect width="900" height="560" fill="url(#dots)"/>`;
  const locked = (x, y, scale = 1, color = C.gold) => `<g transform="translate(${x} ${y}) scale(${scale})"><path d="M10 23V13a13 13 0 0 1 26 0v10" fill="none" stroke="${color}" stroke-width="3"/><rect x="3" y="22" width="40" height="31" rx="7" fill="${C.dark}" stroke="${color}" stroke-width="2"/><circle cx="23" cy="35" r="3" fill="${color}"/><path d="M23 36v7" stroke="${color}" stroke-width="2"/></g>`;
  const chips = (hex, x, y, cols, color, count = Infinity, cell = 38) => bytes(hex).slice(0, count).map((b, i) => box(x + i % cols * cell, y + Math.floor(i / cols) * cell, cell - 5, cell - 5, `${color}0d`, `${color}35`, 4) + txt(x + i % cols * cell + (cell - 5) / 2, y + Math.floor(i / cols) * cell + cell * .6, b, 14, color, "middle", "mono")).join("");
  const initialLab = () => ({ pixels: null, rate: "auto", parity: 100, overlay: null, compare: 50, sign: null, reveal: false });
  let lab = initialLab();

  const chapters = [
    {
      title: "One picture. Two stories.", phase: "THE IDEA", section: 0, duration: 21,
      intro: "A picture can look ordinary while carrying a message. Here, that message is just five letters: HELLO.",
      beats: ["Start with a grayscale picture: a grid of brightness numbers.", "Carefully change a few of those numbers by just one.", "A receiver with the shared key reads relationships between them."],
      takeaway: "The secret travels in the pixels themselves.",
      note: "A generated teaching landscape, embedded and recovered using the real encoder.",
      technical: `<p>A grayscale pixel is an integer from 0 (black) to 255 (white). The cover has 512 × 512 = 262,144 pixels. The encoder decodes the PNG, changes selected samples by ±1, and writes a lossless PNG. It does not append a file or hide text in PNG metadata.</p><p>This demonstration uses keyed mode and a shared symmetric 32-byte key. The animation’s key is a public teaching value, not a private keypair. The separate public, unencrypted mode is outside this walkthrough.</p>`,
      draw(p) {
        const t = ease(p / .6);
        return label(65, 45, "SENDER") + label(835, 45, "RECEIVER", C.muted, "end")
          + box(241, 80, 338, 338, C.dark, C.line, 5) + image(p > .53 ? "stego" : "cover", 250, 89, 320)
          + label(410, 445, "512 × 512 GRAYSCALE PIXELS", C.muted, "middle")
          + box(45, 183, 170, 99, C.dark, `${C.gold}70`) + label(65, 210, "THE MESSAGE", C.gold)
          + txt(130, 252, "HELLO", 37, C.gold, "middle", "serif")
          + arrow(215, 233, 241, 233, C.gold)
          + group(circle(mix(216, 560, p / .48), 235, 6, C.gold), 1 - ease((p - .44) / .1))
          + group(arrow(587, 233, 645, 233) + box(661, 185, 190, 100, C.dark, `${C.mint}70`)
            + label(756, 213, "RECOVERED", C.mint, "middle") + txt(756, 253, "HELLO", 37, C.mint, "middle", "serif"), t)
          + group(F.changes.map(([x, y], i) => circle(250 + x / 512 * 320, 89 + y / 512 * 320, 1.8, C.mint)).join(""), .5 * ease((p - .27) / .15) * (1 - ease((p - .7) / .15)))
          + footer("Change a few pixels. Preserve the picture.", "The receiver does not need the original image.");
      }
    },
    {
      title: "First, letters become numbers.", phase: "PREPARE THE MESSAGE", section: 0, duration: 21,
      intro: "Computers store text as bytes. Each byte holds eight tiny yes/no values, called bits.",
      beats: ["HELLO becomes five bytes: 48 45 4c 4c 4f in hexadecimal.", "Each pair of hex digits is a shorter way to write eight bits.", "Compression is tried first. For HELLO it makes the data longer, so the original five bytes are kept."],
      takeaway: "Five letters → five bytes → 40 message bits.",
      note: "Exact UTF-8 bytes, with no newline. Raw DEFLATE compression is kept only when smaller.",
      technical: `<p>The input is a file’s exact bytes. The encoder tries raw DEFLATE at level 6 before encryption. <code>HELLO</code> compresses to 7 bytes, so its stored representation is the original 5 bytes and the compression flag is 0. Both original and stored lengths are recorded.</p><p>Hexadecimal is base 16. H = decimal 72 = hex 48 = binary 01001000. Bits are packed most significant first. Other UTF-8 characters can require multiple bytes.</p>`,
      draw(p) {
        let s = label(50, 46, "THE SAME MESSAGE, THREE WAYS");
        ["H", "E", "L", "L", "O"].forEach((c, i) => {
          const x = 76 + i * 157;
          s += box(x, 91, 130, 260, C.dark, C.line, 9) + txt(x + 65, 156, c, 52, C.gold, "middle", "serif")
            + arrow(x + 65, 181, x + 65, 215, C.line)
            + group(txt(x + 65, 253, c.charCodeAt(0).toString(16), 35, C.mint, "middle", "mono"), ease(p / .22))
            + group(txt(x + 65, 315, bin(c.charCodeAt(0)), 16, C.muted, "middle", "mono"), ease((p - .15) / .22));
        });
        return s + group(pill(215, 399, 195, "ORIGINAL · 5 BYTES", C.mint) + txt(448, 420, "<", 22, C.muted, "middle")
          + pill(482, 399, 215, "COMPRESSED · 7 BYTES", C.coral), ease((p - .45) / .15))
          + footer("Keep the smaller version: 5 bytes.", "Compression flag = 0. Nothing needs decompressing later.");
      }
    },
    {
      title: "Choose the size of the parcel.", phase: "PREPARE THE MESSAGE", section: 0, duration: 27,
      intro: "The rate sets a total byte budget. The message shares that budget with instructions, security data, and padding.",
      beats: ["HELLO needs 5 message bytes plus 66 bytes of fixed overhead: 71 bytes.", "Auto cannot go below 0.0025 bits per pixel. Here, that allocates 81 whole bytes.", "The extra 10 bytes become padding. These also have to be encoded."],
      takeaway: "Byte budget, encoded bits, and changed pixels are different quantities.",
      note: "This is a byte allocation. It is not the number or percentage of pixels changed.",
      technical: `<div class="formula">B = floor(N × r / 8)<br>auto = max(0.0025, 8 × (5 + 66) / 262,144)<br>B = floor(81.92) = 81 bytes = 648 target bits</div><p>Overhead: salt 32 + header 18 + authentication tag 16 = 66 bytes. The 81-byte allocation leaves 15 bytes for stored data; HELLO uses 5, leaving 10 padding bytes. The actual byte-rounded gross rate is 648 / 262,144 ≈ 0.00247192 bpp, although the selected profile is 0.0025.</p><p>At fixed 0.05 bpp the same message allocates 1,638 bytes, with 1,567 padding bytes and 13,104 target bits. Padding still imposes parity constraints. Lowering the rate generally reduces needed changes; an image’s usable pixels and coding constraints can still prevent embedding.</p>`,
      controls: () => `<span class="lab-label">Compare the allocation</span><button data-action="rate" data-value="auto" aria-pressed="${lab.rate === "auto"}">Auto · 0.0025</button><button data-action="rate" data-value="fixed" aria-pressed="${lab.rate === "fixed"}">Fixed · 0.05</button>`,
      draw(p) {
        const fixed = lab.rate === "fixed", total = fixed ? 1638 : 81, padding = total - 71;
        const parts = [[32, C.purple, "Salt", "32"], [18, C.muted, "Header", "18"], [5, C.gold, "HELLO", "5"], [padding, C.coral, "Padding", fmt(padding)], [16, C.mint, "Tag", "16"]];
        let x = 60, s = label(50, 45, fixed ? "FIXED RATE / SAME FIVE LETTERS" : "AUTO / LOWEST SUPPORTED RATE")
          + txt(65, 125, fmt(total), 66, C.ink, "start", "serif") + txt(fixed ? 235 : 156, 123, "bytes in the complete budget", 20, C.muted)
          + label(66, 161, fixed ? "floor(262,144 × 0.05 ÷ 8)" : "floor(262,144 × 0.0025 ÷ 8)");
        for (const [n, color] of parts) { const w = n / total * 780; s += box(x, 215, Math.max(1, w - 2), 76, color, "none", 2); x += w; }
        parts.forEach(([n, color, name, value], i) => {
          const xx = 65 + i * 159;
          s += circle(xx + 4, 346, 4, color) + txt(xx + 17, 352, name, 16, color)
            + txt(xx + 17, 389, `${value} B`, 24, C.ink, "start", "mono");
        });
        return s + footer(`${fmt(total * 8)} target bits across 262,144 available pixels.`, fixed ? "More padding means more target bits, even though HELLO is unchanged." : "Auto still leaves 10 bytes of padding because the minimum rate applies.");
      }
    },
    {
      title: "Give the message an envelope.", phase: "PREPARE THE MESSAGE", section: 0, duration: 21,
      intro: "The receiver needs to know what the bytes mean and where the message stops.",
      beats: ["An 18-byte header records the format, compression flag, and both lengths.", "The five HELLO bytes come next, followed by ten padding bytes.", "Together they form a 33-byte frame. This entire frame will be encrypted."],
      takeaway: "The stored-length field tells the receiver what to keep and what to discard.",
      note: "The padding values are the walkthrough’s public demonstration sequence; real padding is random.",
      technical: `<div class="formula">01 | 00 | 00 00 00 00 00 00 00 05 | 00 00 00 00 00 00 00 05<br>48 45 4c 4c 4f<br>40 41 42 43 44 45 46 47 48 49</div><p>The header is <code>&gt;BBQQ</code>: version (1 byte), compression flag (1), original length (8), stored length (8). Lengths are unsigned, big-endian integers. Header 18 + message 5 + padding 10 = 33 bytes before encryption. The salt and authentication tag are outside this plaintext frame.</p><p>At a fixed image size and rate, padding equalizes the size of fitting messages. With auto, the selected rate may vary with message length, so this is not universal length hiding.</p>`,
      draw(p) {
        return label(50, 45, "INSIDE THE ENCRYPTED ENVELOPE")
          + box(50, 79, 800, 337, C.dark, C.line)
          + label(80, 112, "18 BYTES · HEADER", C.muted)
          + chips(F.frame.slice(0, 36), 80, 132, 18, C.muted, 18, 41)
          + txt(94, 195, "v1", 12, C.muted, "middle") + txt(135, 195, "raw", 12, C.muted, "middle")
          + txt(320, 195, "original length = 5", 14, C.muted, "middle") + txt(647, 195, "stored length = 5", 14, C.muted, "middle")
          + group(label(80, 244, "5 BYTES · MESSAGE", C.gold) + chips("48454c4c4f", 80, 263, 5, C.gold, 5, 45)
            + txt(332, 292, "H E L L O", 23, C.gold, "start", "mono"), ease(p / .22))
          + group(label(80, 343, "10 BYTES · PADDING", C.coral) + chips(F.padding, 80, 359, 10, C.coral, 10, 41), ease((p - .23) / .2))
          + pill(622, 343, 196, "18 + 5 + 10 = 33 B", C.ink)
          + footer("A 33-byte envelope for a 5-byte message.", "The length fields are encrypted too.");
      }
    },
    {
      title: "One secret. Separate jobs.", phase: "PROTECT THE PARCEL", section: 1, duration: 27,
      intro: "Both people share the same secret key. The program turns it into different working keys for different tasks.",
      beats: ["The shared key and image context locate the salt’s first-stage pixel pool.", "A fresh 32-byte salt is mixed in to make this embedding’s working keys.", "These keys handle encryption, whitening, the body shuffle, equations, and change directions."],
      takeaway: "Find the salt first. Then derive the keys needed to read the body.",
      note: "The salt is not a password. It changes the derived keys; it need not be secret.",
      technical: `<p>The public context contains <code>STEG-BP/1</code>, width 512, height 512, total byte budget 81, and trellis height 10. HMAC-SHA256 deterministically expands the shared key with separate purpose labels.</p><div class="formula">root = HMAC(SHA256("STEG-BP/1/root"), shared_key)<br>derive(parent, label, context) = HMAC(parent, label || 00 || context || 01)<br>message_root = HMAC(salt, root)</div><p><code>split</code> and <code>head-code</code> are derived from root without salt, avoiding a circular dependency. After salt, <code>aead</code>, <code>whiten</code>, <code>body-perm</code>, <code>body-code</code>, and <code>sign</code> come from message_root. No working key is transmitted. Both endpoints reproduce them.</p>`,
      draw(p) {
        let s = label(50, 44, "THE KEY SCHEDULE / REPEATABLE ON BOTH SIDES")
          + box(54, 175, 203, 110, C.dark, `${C.gold}60`) + locked(76, 191, .72)
          + txt(134, 216, "Shared key", 20, C.gold) + txt(134, 244, "+ context", 16, C.muted)
          + arrow(257, 205, 336, 122, C.gold) + box(349, 72, 273, 89, C.dark, `${C.purple}60`)
          + txt(485, 106, "Locate + read the salt", 20, C.purple, "middle") + txt(485, 136, "No salt needed yet", 15, C.muted, "middle")
          + arrow(257, 250, 336, 296, C.gold) + box(350, 255, 273, 86, C.dark, `${C.mint}70`)
          + txt(486, 290, "Mix in the fresh salt", 21, C.mint, "middle") + txt(486, 319, "32 bytes → new working keys", 15, C.muted, "middle")
          + group(arrow(486, 169, 486, 244, C.purple) + pill(508, 190, 114, "SALT", C.purple), ease(p / .3));
        const names = ["Encrypt", "Whiten", "Shuffle", "Equations", "±1 ties"];
        names.forEach((name, i) => { s += group(arrow(623, 299, 691, 106 + i * 77, C.line)
          + box(702, 80 + i * 77, 147, 51, C.dark, `${C.mint}50`) + txt(776, 112 + i * 77, name, 17, C.mint, "middle"), ease((p - .18 - i * .055) / .16)); });
        return s + footer("The same inputs recreate the same keys.", "Fresh production salt makes separate embeddings derive different working keys.");
      }
    },
    {
      title: "Seal it, and add a check.", phase: "PROTECT THE PARCEL", section: 1, duration: 23,
      intro: "Authenticated encryption scrambles the whole envelope and adds a way to reject an invalid payload.",
      beats: ["The 33-byte frame becomes 33 unreadable ciphertext bytes.", "A 16-byte authentication tag lets the receiver verify the payload and its context.", "The encrypted body now occupies 49 bytes. The secret key is never put in the picture."],
      takeaway: "Encryption hides the contents. Authentication checks what was recovered.",
      note: "These ciphertext and tag bytes were computed by ChaCha20-Poly1305 for the public teaching inputs.",
      technical: `<p>ChaCha20-Poly1305 encrypts the entire 33-byte frame and appends a 16-byte tag. Associated data is <code>STEG-BP/1/aad || 00 || context || salt</code>. It binds the payload to the expected dimensions, byte budget, format, and salt.</p><p>The nonce is 12 zero bytes. The implementation relies on a fresh random salt to derive a fresh encryption key for each embedding. Repeating the salt with the same shared key and context repeats the key/nonce pair and is unsafe. The counting values shown here are deliberately only for teaching.</p><p>The tag detects invalid recovered data under the expected key/context; it does not repair it or authenticate every pixel of the picture.</p>`,
      draw(p) {
        const reveal = ease((p - .15) / .3), encrypted = bytes(F.encrypted);
        let s = label(50, 45, "CHACHA20-POLY1305 / AUTHENTICATED ENCRYPTION")
          + box(52, 95, 235, 303, C.dark, C.line) + label(78, 132, "PLAINTEXT FRAME", C.gold)
          + txt(168, 208, "HELLO", 42, C.gold, "middle", "serif") + txt(168, 250, "+ header + padding", 17, C.muted, "middle")
          + pill(105, 322, 126, "33 BYTES", C.gold)
          + arrow(303, 245, 387, 245, C.gold) + locked(320, 175, .9)
          + box(409, 95, 437, 303, C.dark, `${C.mint}60`) + label(436, 132, "CIPHERTEXT", C.mint)
          + group(chips(encrypted.slice(0, 33).join(""), 436, 151, 11, C.mint, 33, 34), reveal)
          + group(label(436, 294, "AUTHENTICATION TAG · 16 BYTES", C.purple)
            + chips(encrypted.slice(33).join(""), 436, 312, 11, C.purple, 16, 34), ease((p - .46) / .2));
        return s + footer("33 bytes of ciphertext + 16 bytes of tag = 49 bytes.", "An incorrect key or invalid payload causes authentication to fail.");
      }
    },
    {
      title: "Add a reversible mask.", phase: "PROTECT THE PARCEL", section: 1, duration: 23,
      intro: "The code applies one more layer called whitening. It mixes the encrypted body with a repeatable stream of bits.",
      beats: ["The XOR rule is simple: matching bits give 0; different bits give 1.", "The 49 encrypted bytes are XORed with 49 mask bytes. Length stays the same.", "Apply the same mask again and the encrypted bytes come back."],
      takeaway: "Whitening is reversible. It is not what guarantees the picture is undetectable.",
      note: "The first byte is shown in full. All 49 bytes are masked in the same way.",
      technical: `<p>A stream of HMAC-SHA256 blocks is generated with the <code>whiten</code> key and the label <code>STEG-BP/1/stream || 00</code>, followed by an 8-byte big-endian counter. The first 49 bytes are used.</p><div class="formula">embedded body = (ciphertext || tag) XOR mask<br>(embedded body XOR mask) = ciphertext || tag</div><p>Authenticated encryption already produces pseudorandom-looking ciphertext. Whitening is an additional reversible format layer. The targets are now 32 salt bytes (256 bits) and 49 body bytes (392 bits): 648 bits in total.</p>`,
      controls: () => `<button data-action="unmask" aria-pressed="${lab.reveal}">${lab.reveal ? "Show masking" : "Apply the mask again"}</button>`,
      draw(p) {
        const a = parseInt(F.encrypted.slice(0, 2), 16), b = parseInt(F.whitening.slice(0, 2), 16), out = a ^ b;
        const rows = [[lab.reveal ? out : a, lab.reveal ? "Embedded byte" : "Encrypted byte", C.gold], [b, "Whitening mask", C.purple], [lab.reveal ? a : out, lab.reveal ? "Recovered byte" : "Embedded byte", C.mint]];
        let s = label(50, 45, "XOR / SAME = 0, DIFFERENT = 1");
        rows.forEach(([value, name, color], r) => {
          const y = 119 + r * 105;
          s += txt(58, y + 37, name, 18, color);
          bin(value).split("").forEach((bit, i) => { s += group(box(265 + i * 65, y, 53, 59, `${color}10`, `${color}60`, 6)
            + txt(291.5 + i * 65, y + 41, bit, 32, color, "middle", "mono"), r === 2 ? ease((p - i * .026) / .2) : 1); });
        });
        return s + txt(223, 262, "⊕", 29, C.purple, "middle") + line(251, 311, 784, 311)
          + pill(287, 432, 322, "256 SALT BITS + 392 BODY BITS", C.ink)
          + footer("648 target bits are ready to enter the picture.", "Those bits will be represented by equations over pixel values.");
      }
    },
    {
      title: "Scatter two pools of pixels.", phase: "CHOOSE THE PIXELS", section: 2, duration: 23,
      intro: "A key-driven shuffle rearranges the pixel indices. It gives both people the same reading order.",
      beats: ["The first one-eighth of shuffled positions carry the salt: the bootstrap pool.", "The other seven-eighths carry the body, shuffled again using a salt-derived key.", "Both pools are spread throughout the image. Belonging to a pool does not mean a pixel changes."],
      takeaway: "The key recreates an invisible reading order, not a visible rectangle.",
      note: "Dots sample 1,024 actual pool memberships across the 512 × 512 teaching image.",
      technical: `<p>Pixels flatten in row order. A deterministic Fisher–Yates permutation, driven by the split key, divides all 262,144 indices into 32,768 bootstrap and 229,376 body positions. The body receives another permutation using <code>body-perm</code>.</p><p>Unsigned 64-bit random draws use rejection sampling before taking a modulus to avoid bias. The bootstrap code carries 256 salt bits; the body code carries 392 bits. Wet/protected pixels remain in their pools and equations; only changing them is forbidden.</p>`,
      draw(p) {
        let s = label(50, 45, "ONE IMAGE / TWO INTERLEAVED POOLS") + image("cover", 53, 91, 350, 'opacity=".25"');
        F.poolSample.forEach((head, i) => {
          const x = i % 32, y = Math.floor(i / 32), moved = ease((p - .05) / .4);
          const initialHead = i < 128;
          s += box(54 + x * 10.9, 92 + y * 10.9, 7.6, 7.6, moved > ((i * 73 % 1024) / 1024) ? (head ? C.purple : C.mint) : (initialHead ? C.purple : C.mint), "none", 1, 'opacity=".85"');
        });
        return s + box(463, 103, 374, 133, C.dark, `${C.purple}70`) + label(488, 134, "BOOTSTRAP / SALT", C.purple)
          + txt(488, 183, "32,768", 39, C.purple, "start", "mono") + txt(691, 181, "positions", 16, C.muted)
          + txt(488, 215, "→ 256 target bits", 19, C.ink)
          + box(463, 267, 374, 133, C.dark, `${C.mint}70`) + label(488, 298, "BODY / ENCRYPTED PARCEL", C.mint)
          + txt(488, 347, "229,376", 39, C.mint, "start", "mono") + txt(713, 345, "positions", 16, C.muted)
          + txt(488, 379, "→ 392 target bits", 19, C.ink)
          + footer("All positions are assigned. Most values stay exactly the same.", "The receiver recreates the order from the key, context, and recovered salt.");
      }
    },
    {
      title: "Put a price on each change.", phase: "CHOOSE THE PIXELS", section: 2, duration: 25,
      intro: "Some places tolerate a tiny change better than others. The encoder gives each possible change a cost.",
      beats: ["Filters measure local detail. Changing a busy region is often cheaper under this model.", "Smooth 5 × 5 neighborhoods and the outer 16-pixel border are protected.", "A value can never go below 0 or above 255. The optimizer respects all these restrictions."],
      takeaway: "Cost estimates the modeled disturbance; it is not a detection probability.",
      note: "Actual encoder cost map: mint = lower cost, amber = higher cost, dark = protected.",
      technical: `<p>Three 16-tap wavelet filter pairs compute residuals. Each residual magnitude is weighted by <code>1 / (1 + |residual|)</code>, spread back over the filter footprint, then summed. Raw costs are rounded to integer millionths: <code>max(1, floor(raw × 1,000,000 + 0.5))</code>.</p><p>The outer 16-pixel border and neighborhoods with 5 × 5 variance ≤ 1 are wet (unchangeable). Decreasing 0 and increasing 255 are forbidden individually. Minus/plus costs are otherwise equal in this model. Protected pixels still participate in parity equations with fixed values.</p><p>For clarity the film explains costs after framing; the actual code computes cover costs before encrypting the body.</p>`,
      draw(p) {
        const t = ease((p - .12) / .35);
        return label(50, 45, "THE SAME IMAGE / TWO VIEWS") + image("cover", 55, 95, 345)
          + image("cover", 495, 95, 345) + image("costs", 495, 95, 345, `opacity="${t}"`)
          + box(495, 95, 345, 345, "none", C.muted, 0) + box(506, 106, 323, 323, "none", C.muted, 0, 'stroke-dasharray="4 4"')
          + label(228, 466, "BRIGHTNESS", C.muted, "middle") + label(668, 466, "PRICE OF A ±1 CHANGE", C.muted, "middle")
          + arrow(415, 266, 477, 266, C.muted)
          + footer("Prefer cheaper changes. Never alter protected pixels.", `${fmt(F.wetCount)} positions are protected in this particular teaching cover.`);
      }
    },
    {
      title: "Even or odd becomes a bit.", phase: "CHOOSE THE PIXELS", section: 2, duration: 22,
      intro: "The code reads one simple property of each pixel’s brightness: is the number even or odd?",
      beats: ["Even numbers represent parity 0. Odd numbers represent parity 1.", "Moving one brightness level in either direction flips that parity.", "First choose the needed parity. Then choose whether the pixel goes up or down."],
      takeaway: "100 → 99 and 100 → 101 both encode the same odd parity.",
      note: "Try the controls. A one-level brightness change always flips even ↔ odd.",
      technical: `<p>Parity is <code>pixel_value &amp; 1</code>. The optimizer chooses final parities using the smaller legal minus/plus cost. Afterward the encoder realizes each parity change by ±1, preferring the cheaper direction and using its sign stream on ties.</p><p>This is a numerical brightness change of one, even when several binary digits change (127 → 128). The receiver reads parity only and does not need the original value or change direction.</p>`,
      controls: () => `<button data-action="parity" data-value="99" aria-pressed="${lab.parity === 99}">−1 → 99</button><button data-action="parity" data-value="100" aria-pressed="${lab.parity === 100}">Original · 100</button><button data-action="parity" data-value="101" aria-pressed="${lab.parity === 101}">+1 → 101</button>`,
      draw(p) {
        const v = lab.parity, odd = v & 1;
        let s = label(50, 45, "THE BRIGHTNESS NUMBER HAS AN EVEN / ODD LABEL");
        [99, 100, 101].forEach((value, i) => {
          const x = 92 + i * 259, selected = value === v, col = value & 1 ? C.gold : C.mint;
          s += box(x, 112, 199, 284, selected ? `${col}12` : C.dark, selected ? col : C.line, 12)
            + box(x + 48, 139, 103, 72, `rgb(${value} ${value} ${value})`, "none", 4)
            + txt(x + 99, 276, value, 51, selected ? col : C.muted, "middle", "mono")
            + pill(x + 28, 323, 143, `${value & 1 ? "ODD" : "EVEN"} · BIT ${value & 1}`, col);
        });
        return s + arrow(337, 242, 308, 242, C.gold) + arrow(566, 242, 598, 242, C.gold)
          + footer(`Selected brightness ${v} → parity ${odd}.`, "The two odd alternatives have the same effect on the embedded equations.");
      }
    },
    {
      title: "Hide bits in relationships.", phase: "CHOOSE THE PIXELS", section: 2, duration: 32,
      intro: "This is the central idea. A message bit is the answer to an equation over several pixel parities.",
      beats: ["Our four pixels initially give answers [0, 1]. We need [1, 0].", "Flipping pixel 0 fixes both equations at cost 8.", "Flipping pixels 1 and 2 also works, but costs only 1 + 2 = 3. That is the cheapest solution."],
      takeaway: "The best solution minimizes weighted cost, not simply the number of changes.",
      note: "Exact four-pixel teaching example from the walkthrough. Click pixel buttons to try your own solution.",
      technical: `<div class="formula">H = [[1, 1, 0, 0], [1, 0, 1, 1]]<br>original pixels = [100, 102, 103, 106]<br>original parities = [0, 0, 1, 0]<br>change costs = [8, 1, 2, 5]<br>required answers = [1, 0]</div><p>Equation A = p0 XOR p1. Equation B = p0 XOR p2 XOR p3. XOR is addition modulo 2: an odd number of 1s gives 1, an even number gives 0. Flipping [1, 2] gives [0, 1, 0, 0], with total cost 3. Flipping [0] costs 8; [1, 3] costs 6; [0, 2, 3] costs 15. These are all four valid solutions among the 16 possible flip patterns.</p><p>This small hand-calculable matrix teaches the principle. The real encoder generates a much larger structured matrix from a code key.</p>`,
      controls: () => [0, 1, 2, 3].map(i => `<button data-action="pixel" data-value="${i}" aria-pressed="${!!lab.pixels?.[i]}">Flip pixel ${i}</button>`).join("") + `<button data-action="cheapest">Show cheapest</button><button data-action="reset-pixels">Reset</button>`,
      draw(p) {
        const flips = lab.pixels || (p < .28 ? [0, 0, 0, 0] : p < .57 ? [1, 0, 0, 0] : [0, 1, 1, 0]);
        const values = [100, 102, 103, 106].map((v, i) => v + (flips[i] ? (i === 2 ? -1 : 1) : 0));
        const parity = values.map(v => v & 1), target = [parity[0] ^ parity[1], parity[0] ^ parity[2] ^ parity[3]];
        const cost = flips.reduce((sum, f, i) => sum + f * [8, 1, 2, 5][i], 0), valid = target[0] === 1 && target[1] === 0;
        let s = label(50, 42, "FOUR PIXELS / TWO EQUATIONS / TARGET [1, 0]");
        [[0, 1], [0, 2, 3]].forEach((indices, row) => indices.forEach(i => { const x = 134 + i * 210; s += `<path d="M${x} 237 C${x} ${270 + row * 40},${262 + row * 397} 280,${262 + row * 397} 310" fill="none" stroke="${row ? C.purple : C.mint}" stroke-width="2" opacity=".4"/>`; }));
        values.forEach((v, i) => {
          const x = 49 + i * 210, color = flips[i] ? C.gold : C.muted;
          s += box(x, 84, 170, 153, C.dark, color, 9) + label(x + 85, 112, `PIXEL ${i}`, color, "middle")
            + txt(x + 85, 156, v, 33, C.ink, "middle", "mono") + txt(x + 85, 188, `parity ${parity[i]}`, 19, color, "middle", "mono")
            + txt(x + 85, 220, `flip cost ${[8, 1, 2, 5][i]}`, 13, C.muted, "middle");
        });
        const eq = [`${parity[0]} ⊕ ${parity[1]}`, `${parity[0]} ⊕ ${parity[2]} ⊕ ${parity[3]}`];
        target.forEach((v, i) => {
          const x = 77 + i * 400, ok = v === [1, 0][i], color = i ? C.purple : C.mint;
          s += box(x, 311, 370, 111, C.dark, `${color}70`) + label(x + 19, 338, `EQUATION ${i ? "B" : "A"}`, color)
            + txt(x + 24, 388, `${eq[i]} = ${v}`, 27, C.ink, "start", "mono") + pill(x + 233, 322, 114, `NEED ${[1, 0][i]} ${ok ? "✓" : "×"}`, ok ? C.mint : C.coral);
        });
        return s + footer(`${valid ? "Both equations match" : "Equations do not match yet"} · total change cost ${cost}`, valid && cost === 3 ? "Two cheap changes beat one expensive change. This is the minimum." : valid ? "Valid, but a cheaper solution exists: flip pixels 1 and 2." : "Try flipping a pixel and watch every equation it participates in.");
      }
    },
    {
      title: "Keep the cheapest route.", phase: "FIND AND APPLY THE CHANGES", section: 3, duration: 28,
      intro: "Trying every full image would be impossible. A trellis saves work by merging choices that reach the same partial result.",
      beats: ["At each pixel, consider final parity 0 or 1. Keeping the old parity is free; flipping pays its cost.", "When two routes reach the same partial equation answers, keep only the cheaper route.", "Reject completed equations that miss their target. Trace back the winning choices."],
      takeaway: "Keep the best route to each state; discard the more expensive duplicates.",
      note: "A four-state teaching trellis for the small example. The real encoder uses up to 1,024 states.",
      technical: `<p>STC means syndrome-trellis coding. The syndrome is the vector of equation answers, <code>H y</code>. The native code finds the exact minimum integer change cost for its generated matrix, subject to <code>H y = target (mod 2)</code> and wet constraints.</p><p>Real trellis height 10 gives 2¹⁰ = 1,024 states for active partial equations. After a row’s column group, only states matching that target bit survive; the completed equation is removed from the state. Groups overlap across equations. Traceback reconstructs the chosen parities. The toy drawing retains both equations throughout, to make the merging visible.</p><p>The search runs separately for salt and body. Protected pixels remain in equations but cannot flip. An unreachable target rejects embedding. Optimality is for this finite matrix and cost model, not for every possible detector.</p>`,
      draw(p) {
        const xs = [0, 0, 1, 0], costs = [8, 1, 2, 5], masks = [3, 1, 2, 2];
        const levels = [[0, Infinity, Infinity, Infinity]], edges = [];
        for (let i = 0; i < 4; i++) {
          const next = [Infinity, Infinity, Infinity, Infinity];
          levels[i].forEach((c, st) => { if (Number.isFinite(c)) for (let bit = 0; bit <= 1; bit++) {
            const dest = st ^ (bit ? masks[i] : 0), score = c + (bit !== xs[i] ? costs[i] : 0);
            edges.push({ i, st, dest, bit, score }); next[dest] = Math.min(next[dest], score);
          } }); levels.push(next);
        }
        const progress = clamp(p / .7) * 4, win = [0, 0, 1, 1, 1];
        let s = label(50, 41, "A STATE = THE PARTIAL ANSWERS TO THE EQUATIONS") + label(50, 73, "NUMBERS IN CIRCLES = LOWEST COST SO FAR", C.muted)
          + txt(860, 94, "ANSWERS", 10, C.muted, "middle", "mono");
        edges.forEach(({ i, st, dest, bit, score }) => {
          const highlight = p > .73 && st === win[i] && dest === win[i + 1] && bit === [0, 1, 0, 0][i];
          const x1 = 88 + i * 179, y1 = 133 + st * 84, x2 = x1 + 179, y2 = 133 + dest * 84;
          const a = ease(progress - i), discarded = score > levels[i + 1][dest];
          s += line(x1, y1, mix(x1, x2, a), mix(y1, y2, a), highlight ? C.mint : discarded ? C.coral : C.line, highlight ? 4 : 1.5, `opacity="${highlight ? 1 : discarded ? .18 : .65}"`);
        });
        levels.forEach((level, i) => {
          s += label(88 + i * 179, 449, i ? `PIXEL ${i - 1}` : "START", C.muted, "middle");
          level.forEach((cost, state) => { const visible = Number.isFinite(cost) && (i === 0 || progress > i - 1), best = p > .73 && state === win[i];
            s += circle(88 + i * 179, 133 + state * 84, 23, best ? C.mint : C.dark, `stroke="${best ? C.mint : C.line}" stroke-width="2"`)
              + txt(88 + i * 179, 140 + state * 84, visible ? cost : "·", 18, best ? C.dark : C.ink, "middle", "mono");
            if (i === 4) s += txt(860, 139 + state * 84, `[${state & 1},${state >> 1}]`, 14, state === 1 ? C.mint : C.muted, "middle", "mono")
              + (state === 1 ? txt(860, 244, "TARGET", 10, C.mint, "middle", "mono") : "");
          });
        });
        return s + footer(p > .73 ? "Winning final parities: [0, 1, 0, 0] · total cost 3" : "Many possible routes. Only the cheapest per state survives.", "Real image: 10 active equation bits → up to 1,024 states.");
      }
    },
    {
      title: "Turn the answer into pixels.", phase: "FIND AND APPLY THE CHANGES", section: 3, duration: 24,
      intro: "The optimizer has chosen the final parities. Now the encoder makes the corresponding brightness changes.",
      beats: ["If the desired parity already matches, leave the pixel alone.", "Otherwise choose a legal +1 or −1 change, using costs and key-driven tie-breaking.", "In this real example, 72 pixels change. The salt and body equations are checked afterward."],
      takeaway: "648 target bits do not mean 648 modified pixels.",
      note: "Actual change locations. Dots are enlarged to make single-pixel changes visible.",
      technical: `<p>This generated image has ${F.info.changed_pixels} changed pixels: ${F.headChanges} in the bootstrap pool and ${F.info.changed_pixels - F.headChanges} in the body pool. That is ${(100 * F.info.changed_pixels / 262144).toFixed(4)}% of the image. Every numerical change is exactly ±1. The count depends on the cover, key, randomness, cost map, and rate.</p><p>For each parity flip the code chooses the lower-cost legal direction. Equal costs are resolved using low bits of the sign-key stream. The salt and body syndromes are independently recomputed and checked after embedding.</p><p>The observed 72-pixel count is data from this fixture, not a general promise for HELLO or for the rate 0.0025.</p>`,
      controls: () => `<button data-action="overlay" aria-pressed="${lab.overlay}">${lab.overlay ? "Hide enlarged markers" : "Show all enlarged markers"}</button>`,
      draw(p) {
        const count = lab.overlay === null ? Math.floor(ease(p / .72) * F.changes.length) : lab.overlay ? F.changes.length : 0;
        let s = label(50, 44, "THE REAL EXAMPLE / 648 TARGET BITS") + image("stego", 62, 80, 384);
        F.changes.slice(0, count).forEach(([x, y, before, after, head]) => { s += circle(62 + x * .75, 80 + y * .75, 3.1, head ? C.purple : C.mint); });
        s += txt(658, 174, count, 88, C.mint, "middle", "serif") + txt(658, 211, "changed pixels", 22, C.ink, "middle")
          + txt(658, 244, "out of 262,144", 18, C.muted, "middle")
          + line(502, 275, 816, 275) + txt(658, 320, "Each change: +1 or −1", 20, C.ink, "middle")
          + pill(517, 354, 279, "SALT + BODY EQUATIONS ✓", C.mint)
          + label(658, 417, "72 IS A MEASURED RESULT", C.muted, "middle");
        return s + footer("The message lives in collective relationships.", "Protected pixels are unchanged, and the complete payload is recoverable.");
      }
    },
    {
      title: "Polish the change directions.", phase: "FIND AND APPLY THE CHANGES", section: 3, duration: 25,
      intro: "The balanced strategy makes one final adjustment. It may reverse a change’s direction while keeping its encoded bit.",
      beats: ["An original 100 could end at 101 or 99. Both are odd and differ from the cover by one.", "Histograms count local image patterns. A reversal is kept only if its score brings those counts closer to the original.", "The same pixels remain modified, and every parity stays fixed. The message survives unchanged."],
      takeaway: "Balancing changes directions, never the payload’s parities or the set of changed pixels.",
      note: "Pixel 100 is illustrative. The before/after scores are measured on the actual teaching image.",
      technical: `<p>Eight residual filters are grouped by four cover-texture categories, quantized at steps 1, 2, and 4, and clipped into 17 bins (−8 through +8).</p><div class="formula">J = Σ (stego_histogram − cover_histogram)² / (cover_histogram + 32)</div><p>For each eligible changed pixel the optimizer tries reversing its sign. It accepts only a strict reduction in J. Up to six passes alternate traversal direction; a pass with no improvement ends the search.</p><p>The fixture records ${F.info.balance_flips} accepted reversals across passes, not necessarily that many distinct pixels. J moves from ${F.info.balance_objective_before.toFixed(6)} to ${F.info.balance_objective_after.toFixed(6)}. A lower score improves this chosen statistic; detector resistance must be measured separately.</p>`,
      controls: () => `<button data-action="sign" aria-pressed="${lab.sign}">Reverse the illustrative change</button>`,
      draw(p) {
        const switched = lab.sign ?? p > .38, before = F.info.balance_objective_before, after = F.info.balance_objective_after;
        return label(50, 44, "BALANCED STRATEGY / KEEP THE SAME PARITIES")
          + box(50, 89, 390, 346, C.dark, C.line) + label(245, 126, "ONE ALREADY-SELECTED PIXEL", C.muted, "middle")
          + txt(159, 216, "100", 51, C.muted, "middle", "mono") + arrow(222, 201, 277, 201, C.gold)
          + txt(353, 216, switched ? "99" : "101", 51, C.gold, "middle", "mono")
          + txt(158, 251, "original", 17, C.muted, "middle") + txt(350, 251, switched ? "−1 change" : "+1 change", 17, C.gold, "middle")
          + pill(94, 316, 302, "99 AND 101 BOTH HAVE PARITY 1", C.mint)
          + box(469, 89, 380, 346, C.dark, C.line) + label(495, 126, "MEASURED HISTOGRAM MISMATCH", C.muted)
          + txt(495, 186, "Before", 17, C.muted) + box(495, 201, 320, 38, `${C.coral}65`, "none", 4)
          + txt(795, 227, before.toFixed(3), 21, C.ink, "end", "mono")
          + txt(495, 283, "After balancing", 17, C.mint) + box(495, 298, mix(320, 320 * after / before, p / .7), 38, `${C.mint}90`, "none", 4)
          + txt(795, 324, after.toFixed(3), 21, C.ink, "end", "mono")
          + txt(659, 387, "Lower score is better for this model", 15, C.muted, "middle")
          + footer("Same 72 changed locations. Same 648 target bits.", "Improving this score does not prove statistical undetectability.");
      }
    },
    {
      title: "Save the picture. Check the message.", phase: "RECOVER THE MESSAGE", section: 4, duration: 23,
      intro: "The sender saves a PNG, reopens it, and runs the complete extraction before accepting the result.",
      beats: ["Lossless PNG storage preserves every modified brightness value.", "The saved pixels must match the intended pixels, and extraction must return exactly HELLO.", "Send the image. The receiver must also know the shared key and the selected rate: 0.0025."],
      takeaway: "The receiver needs the picture, the shared key, and the numeric rate.",
      note: "Drag to compare the actual original and stego pixels. The difference is deliberately subtle.",
      technical: `<p>The verification decodes the serialized PNG and checks exact equality with the intended stego array, then runs full extraction and compares the message bytes. The fixture passes both checks.</p><p>The receiver must use the same selected rate (0.0025 here) and compatible format/trellis profile. It cannot use auto because the message length is still inside the encrypted frame. It needs neither the original cover, the cost map, a list of changes, nor the balanced option.</p><p>PNG compression is lossless storage and is distinct from compression of the message. JPEG conversion, resizing, or changing pixel values can destroy the payload. STC here is not a general damage-repair code.</p>`,
      controls: () => `<label for="compare">Original / stego <input id="compare" type="range" min="0" max="100" value="${lab.compare}" aria-label="Original and stego comparison divider"></label>`,
      draw(p) {
        const divider = 81 + 350 * lab.compare / 100;
        return label(50, 44, "LOSSLESS PNG / VERIFIED BEFORE SENDING")
          + `<defs><clipPath id="compare-clip"><rect x="81" y="85" width="${350 * lab.compare / 100}" height="350"/></clipPath></defs>`
          + image("stego", 81, 85, 350) + image("cover", 81, 85, 350, 'clip-path="url(#compare-clip)"')
          + line(divider, 85, divider, 435, C.mint, 2) + circle(divider, 260, 15, C.mint)
          + txt(divider, 266, "↔", 19, C.dark, "middle") + label(82, 465, "ORIGINAL", C.muted) + label(431, 465, "STEGO", C.mint, "end")
          + box(485, 105, 334, 298, C.dark, C.line) + label(511, 143, "WHAT THE RECEIVER NEEDS", C.mint)
          + txt(514, 201, "01   Stego PNG", 23, C.ink) + txt(514, 265, "02   Shared key", 23, C.gold)
          + txt(514, 329, "03   Rate 0.0025", 23, C.purple)
          + footer("The saved PNG recovers exactly HELLO.", "No original cover is needed at the receiving end.");
      }
    },
    {
      title: "Read the relationships back.", phase: "RECOVER THE MESSAGE", section: 4, duration: 28,
      intro: "The receiver rebuilds the same reading order and equations, then evaluates them on the image it received.",
      beats: ["First, use the shared key and context to read the 256 salt bits.", "Use that salt to recreate the body keys and read the 392 body bits.", "There is no search for cheap changes during extraction. Just evaluate the equations."],
      takeaway: "Reading equations does not require knowing which pixels were changed.",
      note: "The small equations below recover [1, 0] directly from the final toy pixels.",
      technical: `<p>The receiver recomputes the 81-byte budget, bootstrap permutation, and bootstrap matrix from the shared key and image context. It evaluates <code>H_head × y_head (mod 2)</code>, then packs 256 bits most significant first into 32 salt bytes.</p><p>It derives the message-specific keys, regenerates the body permutation/matrix, and evaluates <code>H_body × y_body (mod 2)</code> to recover 392 bits (49 bytes). The original image and sender’s costs are not inputs. The minimum-cost optimization is sender-only.</p><p>This recovers the message-bearing bits, not the original cover image. Many different covers could produce an image satisfying the same equations.</p>`,
      draw(p) {
        const t1 = ease(p / .25), t2 = ease((p - .28) / .25);
        return label(50, 45, "EXTRACTION / EVALUATE, DO NOT OPTIMIZE")
          + image("stego", 54, 95, 220) + label(164, 342, "RECEIVED PNG", C.muted, "middle")
          + arrow(293, 161, 358, 161, C.purple)
          + group(box(380, 98, 444, 109, C.dark, `${C.purple}70`) + label(405, 128, "1. BOOTSTRAP EQUATIONS", C.purple)
            + txt(405, 175, "256 bits → 32-byte salt", 26, C.ink), t1)
          + group(arrow(602, 213, 602, 256, C.purple) + label(620, 241, "DERIVE BODY KEYS", C.muted), t1)
          + group(box(380, 268, 444, 106, C.dark, `${C.mint}70`) + label(405, 298, "2. BODY EQUATIONS", C.mint)
            + txt(405, 345, "392 bits → 49-byte body", 26, C.ink), t2)
          + pill(81, 409, 738, "TOY PIXELS [100, 103, 102, 106] → PARITIES [0, 1, 0, 0]", C.ink)
          + footer("0 ⊕ 1 = 1     and     0 ⊕ 0 ⊕ 0 = 0", "The receiver gets [1, 0] without knowing the original pixels.");
      }
    },
    {
      title: "Open the envelope. HELLO again.", phase: "RECOVER THE MESSAGE", section: 4, duration: 27,
      intro: "The body is recovered, but the message is still protected. Now reverse the layers in order.",
      beats: ["Apply the whitening mask again. Authenticate and decrypt the 49-byte body.", "Read the 18-byte header. Keep its five message bytes and discard ten padding bytes.", "The compression flag is 0, so no decompression is needed. The result is exactly HELLO."],
      takeaway: "A few tiny changes, a shared key, and the same equations bring the message back.",
      note: "Verified recovered bytes: 48 45 4c 4c 4f. An invalid authenticated payload is rejected.",
      technical: `<p>The extracted 49-byte body is XORed with the regenerated whitening stream. ChaCha20-Poly1305 verifies and decrypts with the same encryption key, zero nonce, and associated data. Invalid authentication causes rejection.</p><p>The recovered frame must have the expected version, a valid compression flag, and valid bounded lengths. Exactly five bytes after the header are retained. With flag 0, their length must match the declared original length. With flag 1, raw DEFLATE decompression also validates length, end-of-stream, and absence of trailing data.</p><div class="formula">Recovered: 48 45 4c 4c 4f → HELLO<br>PNG pixel equality: PASS<br>Salt + body syndromes: PASS<br>Exact recovered message: PASS</div><p>Encryption protects the contents. Adaptive coding and sign balancing aim to limit image disturbance. Neither a convincing appearance nor successful extraction establishes universal undetectability.</p>`,
      draw(p) {
        const reveal = ease((p - .3) / .45);
        let s = label(50, 44, "UNDO THE LAYERS / KEEP ONLY THE MESSAGE");
        const items = [["49 B", "Undo whitening", C.purple], ["33 B", "Verify + decrypt", C.mint], ["5 B", "Read length = 5", C.gold]];
        items.forEach(([n, name, col], i) => {
          const x = 54 + i * 284;
          s += group(box(x, 88, 226, 112, C.dark, `${col}70`) + txt(x + 113, 134, n, 33, col, "middle", "mono")
            + txt(x + 113, 172, name, 18, C.ink, "middle"), ease((p - i * .08) / .17));
          if (i < 2) s += arrow(x + 235, 145, x + 270, 145, C.line);
        });
        return s + group(txt(450, 360, "HELLO", 113, C.gold, "middle", "serif", 'letter-spacing="12"')
          + txt(450, 408, "48   45   4c   4c   4f", 23, C.muted, "middle", "mono"), reveal)
          + footer("The exact same five bytes. The story has come full circle.", "262,144 pixels · 648 target bits · 72 changed pixels in this verified example.");
      }
    }
  ];

  const sections = ["Prepare", "Protect", "Choose", "Embed", "Recover"];
  let duration = 0;
  chapters.forEach(ch => { ch.start = duration; duration += ch.duration; });
  let position = 0, current = -1, playing = false, speed = 1, lastFrame = null, lastDraw = -Infinity, lastBeat = -1;
  const motionPreference = matchMedia("(prefers-reduced-motion: reduce)");
  let reduceMotion = motionPreference.matches;
  motionPreference.addEventListener("change", e => { reduceMotion = e.matches; render(true); });
  $("seek").max = duration;
  $("chapter-list").innerHTML = chapters.map((ch, i) => `<button data-chapter="${i}"><span>${String(i + 1).padStart(2, "0")}</span>${esc(ch.title)}</button>`).join("");
  $("timeline-segments").innerHTML = chapters.map(ch => `<span style="flex:${ch.duration}"></span>`).join("");
  $("phase-tabs").innerHTML = sections.map((name, i) => `<button data-section="${i}"><span>0${i + 1}</span>${name.toUpperCase()}</button>`).join("");
  $("transcript-content").innerHTML = chapters.map((ch, i) => `<article><h3><span class="transcript-number">${String(i + 1).padStart(2, "0")}</span>${esc(ch.title)}</h3><p>${esc(ch.intro)}</p><p>${ch.beats.map(esc).join(" ")}</p><p><strong>${esc(ch.takeaway)}</strong></p></article>`).join("");
  const clock = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
  const getChapter = value => Math.min(chapters.length - 1, chapters.findIndex(ch => value < ch.start + ch.duration) < 0 ? chapters.length - 1 : chapters.findIndex(ch => value < ch.start + ch.duration));
  function renderControls() { $("interaction").innerHTML = chapters[current].controls?.() || ""; }
  function render(force = false) {
    const index = getChapter(position), changed = index !== current;
    if (changed) {
      current = index; lastBeat = -1; lab = initialLab();
      const ch = chapters[index];
      $("chapter-number").textContent = `CHAPTER ${String(index + 1).padStart(2, "0")} / ${chapters.length}`;
      $("chapter-title").textContent = ch.title; $("chapter-intro").textContent = ch.intro;
      $("beats").innerHTML = ch.beats.map(beat => `<li>${esc(beat)}</li>`).join("");
      $("takeaway").textContent = ch.takeaway; $("visual-note").textContent = ch.note;
      $("phase").textContent = ch.phase; $("technical-content").innerHTML = ch.technical;
      $("visual-title").textContent = ch.title; $("visual-desc").textContent = `${ch.intro} ${ch.beats.join(" ")} ${ch.note}`;
      $("announcer").textContent = `Chapter ${index + 1}: ${ch.title}`;
      document.querySelectorAll("[data-chapter]").forEach((b, i) => { if (i === index) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current"); });
      document.querySelectorAll("[data-section]").forEach((b, i) => { b.classList.toggle("active", i === ch.section); if (i === ch.section) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current"); });
      $("prev").disabled = index === 0; $("next").disabled = index === chapters.length - 1;
      renderControls();
      try { history.replaceState(null, "", `#chapter=${index + 1}`); } catch { /* File viewers may restrict history. */ }
    }
    const ch = chapters[current], p = clamp((position - ch.start) / ch.duration);
    const beat = Math.min(2, Math.floor(p * 3));
    if (beat !== lastBeat) { [...$("beats").children].forEach((li, i) => li.classList.toggle("active", i === beat)); lastBeat = beat; }
    const visualProgress = reduceMotion ? 1 : p;
    $("drawing").innerHTML = defs + ch.draw(visualProgress);
    if (current === 10) {
      const flips = lab.pixels || (visualProgress < .28 ? [0, 0, 0, 0] : visualProgress < .57 ? [1, 0, 0, 0] : [0, 1, 1, 0]);
      document.querySelectorAll('[data-action="pixel"]').forEach((b, i) => b.setAttribute('aria-pressed', String(!!flips[i])));
    }
    $("time").textContent = `${clock(position)} / ${clock(duration)}`;
    $("seek").value = position;
    $("seek").setAttribute("aria-valuetext", `${clock(position)}, chapter ${current + 1}: ${ch.title}`);
  }
  function setPlaying(value) {
    playing = value;
    if (playing && current >= 0) { lab = initialLab(); renderControls(); render(true); }
    $("play-label").textContent = playing ? "Pause" : position >= duration ? "Play again" : position === 0 ? "Play the story" : "Continue";
    $("play-icon").textContent = playing ? "Ⅱ" : "▶";
    $("play").setAttribute("aria-label", playing ? "Pause animation" : "Play animation");
    lastFrame = null;
  }
  function jump(index, keepPlaying = false) {
    position = chapters[clamp(index, 0, chapters.length - 1)].start;
    if (!keepPlaying) setPlaying(false);
    current = -1;
    render(true);
  }
  function pauseForInteraction() { setPlaying(false); }
  $("play").addEventListener("click", () => { if (position >= duration) { position = 0; render(true); } setPlaying(!playing); });
  $("prev").addEventListener("click", () => jump(current - 1));
  $("next").addEventListener("click", () => jump(current + 1));
  $("replay").addEventListener("click", () => { jump(current); setPlaying(true); });
  $("speed").addEventListener("change", e => { speed = Number(e.target.value); });
  $("seek").addEventListener("input", e => { position = Number(e.target.value); setPlaying(false); render(true); });
  $("chapters-toggle").addEventListener("click", () => {
    const open = $("chapter-list").hidden;
    $("chapter-list").hidden = !open; $("chapters-toggle").setAttribute("aria-expanded", String(open));
  });
  $("chapter-list").addEventListener("click", e => { const b = e.target.closest("[data-chapter]"); if (b) jump(Number(b.dataset.chapter)); });
  $("phase-tabs").addEventListener("click", e => { const b = e.target.closest("[data-section]"); if (b) jump(chapters.findIndex(ch => ch.section === Number(b.dataset.section))); });
  $("interaction").addEventListener("click", e => {
    const b = e.target.closest("[data-action]"); if (!b) return;
    pauseForInteraction();
    const { action, value } = b.dataset;
    if (action === "rate") lab.rate = value;
    if (action === "parity") lab.parity = Number(value);
    if (action === "pixel") {
      if (!lab.pixels) { const p = reduceMotion ? 1 : (position - chapters[current].start) / chapters[current].duration; lab.pixels = p < .28 ? [0, 0, 0, 0] : p < .57 ? [1, 0, 0, 0] : [0, 1, 1, 0]; }
      lab.pixels[Number(value)] ^= 1;
    }
    if (action === "cheapest") lab.pixels = [0, 1, 1, 0];
    if (action === "reset-pixels") lab.pixels = [0, 0, 0, 0];
    if (action === "overlay") lab.overlay = !lab.overlay;
    if (action === "unmask") lab.reveal = !lab.reveal;
    if (action === "sign") lab.sign = !(lab.sign ?? (reduceMotion || (position - chapters[current].start) / chapters[current].duration > .38));
    render(true);
    // Preserve keyboard focus while refreshing the control labels/states.
    renderControls();
    const replacement = $("interaction").querySelector(`[data-action="${action}"]${value !== undefined ? `[data-value="${value}"]` : ""}`);
    replacement?.focus({ preventScroll: true });
  });
  $("interaction").addEventListener("input", e => { if (e.target.id === "compare") { pauseForInteraction(); lab.compare = Number(e.target.value); render(true); } });
  document.addEventListener("keydown", e => {
    if (e.altKey || e.ctrlKey || e.metaKey || e.target.closest("input, select, textarea, button, summary, a, [contenteditable]")) return;
    if (e.code === "Space") { e.preventDefault(); $("play").click(); }
    if (e.code === "ArrowRight") { e.preventDefault(); jump(current + 1); }
    if (e.code === "ArrowLeft") { e.preventDefault(); jump(current - 1); }
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) setPlaying(false); });
  const fromHash = () => { const match = location.hash.match(/^#chapter=(\d+)$/); if (match) jump(Number(match[1]) - 1); };
  window.addEventListener("hashchange", fromHash);
  // Preload local assets so chapter transitions never need a network request.
  ["cover", "stego", "costs"].forEach(name => { const img = new Image(); img.src = `assets/${name}.png`; });
  fromHash(); render(true);
  function frame(now) {
    if (playing && lastFrame !== null) {
      position = Math.min(duration, position + Math.min((now - lastFrame) / 1000, .25) * speed);
      if (now - lastDraw >= 1000 / 24 || position >= duration) { render(); lastDraw = now; }
      if (position >= duration) setPlaying(false);
    }
    lastFrame = now;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
