# Stegolab

An executable implementation of `steganography_master_blueprint.md`, plus an experimental sign-balancing extension and a reproducible statistical-resistance benchmark. Everything stays local. This is research software; successful extraction and low measured detector AUC do not establish universal undetectability.

Reading guide: [commands](#embed-and-extract), [analyze without embedding](#analyze-without-embedding), [timed progress logs](#timed-progress-logs), [basic concepts](#what-the-algorithm-actually-does), [input restrictions](#why-this-version-restricts-its-inputs), [sender walkthrough](#sender-the-embedding-process), [experimental sign balancing](#7-experimental-conditional-residual-sign-balancing), [receiver walkthrough](#receiver-extraction-without-the-original-image), [measured resistance](#what-the-experiments-demonstrated), [automatic-rate runtime measurements](#does-automatic-rate-reduce-execution-time), [exact-output acceleration](#exact-output-native-acceleration), and [experiment reproduction](#reproduce-the-experiments).

For a visual explanation, open [the interactive animation](animation/index.html) in a browser. Its 17 chapters follow `HELLO` from bytes into pixels and back, with playback controls, interactive equations, and a verified example from the real encoder. It works offline without installation; see [animation controls and reproduction](animation/README.md).

## Install and verify

Python 3.11 or newer and GCC's `g++` are required. The implementation uses a small C++ shared library for exact syndrome-trellis optimization and Python for authenticated encryption, image processing, and experiments. Windows builds also batch the existing HMAC streams, pixel shuffles, and matrix generation in native code using the system cryptographic provider; the wire format and resulting pixels are unchanged. Other platforms retain the Python implementations of these primitives.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[research,test]"
.\.venv\Scripts\python.exe scripts/build_native.py
.\.venv\Scripts\python.exe -m pytest -q
```

On Linux, substitute `.venv/bin/python`. The build script selects a `.so` instead of a Windows DLL. No model or dataset is downloaded during ordinary installation or use.

## Embed and extract

Use a single-frame, 8-bit grayscale PNG, without alpha or a palette. It must contain between 262,144 and 16,777,216 pixels and have sides between 256 and 8192 pixels. The implementation rejects implicit conversions. Keep a private original and transmit the stego losslessly; resizing, JPEG recompression, and color conversion can destroy the payload.

The CLI supports two distinct payload modes. Supplying `--key` requires the same private 32-byte key at both ends and selects the existing authenticated-encryption mode. Omitting `--key` at both ends selects the unencrypted public plaintext mode. The mode is selected out of band by the presence of the option; using different modes for embed and extract cannot work.

```powershell
# Confidential, authenticated mode: keep this key private and give it to both endpoints.
.\.venv\Scripts\stegolab.exe keygen private.key
.\.venv\Scripts\stegolab.exe embed cover.png --message secret.txt --key private.key --output encrypted_stego.png --rate 0.05 --strategy balanced
.\.venv\Scripts\stegolab.exe extract encrypted_stego.png --key private.key --output encrypted_recovered.txt --rate 0.05

# Unencrypted plaintext mode: deliberately omit --key from both commands.
.\.venv\Scripts\stegolab.exe embed cover.png --message secret.txt --output plain_stego.png --rate 0.05 --strategy balanced
.\.venv\Scripts\stegolab.exe extract plain_stego.png --output plain_recovered.txt --rate 0.05
```

Before computing image costs or changing pixels, `embed` prints the payload's original byte count, its stored byte count after optional compression, and three size measures. **Net bpp** is `8 × original message bytes / image pixels`; **stored net bpp** uses the compressed size when compression helps; **gross bpp** is the fixed embedded frame size, including salt, framing, padding, and authentication overhead, divided by image pixels. **Capacity used** is `stored bytes / maximum stored bytes × 100%` (the keyed maximum is `floor(image pixels × rate / 8) − 66`). Thus a highly compressible message can have original net bpp above gross bpp yet still fit. The stage-based progress bar is printed to stderr; it marks completed stages, **not elapsed time or a reliable time estimate**. The console contains readable logs only; optional machine-readable JSON is saved with `--output-logs FILE`, never printed to stdout. An oversized message reports its percentage and fails before cost-map computation or image output creation; an image can still fail later if too many positions are unusable.

The same preflight logs the **suggested minimum gross rate** that fits the stored bytes and the **chosen gross rate**. Use `--rate auto` with `analyze` or `embed` to choose the minimum size-fitting budget automatically; both rates are also included in the optional JSON file. The suggestion is `max(0.0025, 8 × (stored bytes + 66) / image pixels)` for keyed mode, subject to the supported maximum of 0.2 bpp. It is a byte-capacity minimum, not a promise that the image's usable pixels or statistical resistance are sufficient. **CLI rates are decimals**, normally with eight decimal places, such as `0.00262452`. Copy the logged chosen rate (or JSON `rate` when exporting logs) into `extract --rate`. Extraction cannot use `--rate auto`, because it does not know the sender's message size before decoding.

Internally, exact arithmetic is retained. Decimal rate strings are rounded upward only if doing so preserves the same whole-byte frame budget; exceptional manually supplied rates get additional decimal places if necessary. This prevents rounding down from removing a required byte, or rounding up from changing the layout. Legacy fractional rate inputs remain accepted, but are no longer printed as fractions by the CLI. **Chosen/suggested rate** is the copyable profile setting; **actual gross bpp** is `8 × allocated frame bytes / pixels`, rounded for display. The latter can be slightly smaller because only whole bytes are allocated: do not substitute the displayed actual gross bpp for the reported chosen rate when extracting. The Python API retains exact rate strings for compatibility.

The no-key mode provides **no confidentiality**: anyone who knows the public format can recover the message without a secret. Its public pseudorandom layout, salt, padding, and reversible whitening are not encryption. A CRC detects ordinary accidental payload corruption; it is not a cryptographic authentication tag and cannot prove who created the message or prevent deliberate changes. For confidential messages, always supply a private key to both commands. The `--message` argument names a file whose raw bytes are embedded; encode text as UTF-8 yourself if you need UTF-8 bytes, and extraction writes those bytes back unchanged.

It also cannot promise stealth against someone who knows this public format: that observer can run the no-key extractor as a presence test. In the exploratory public-mode probe, it recovered all 120 tested stego messages while rejecting all 40 ordinary covers tested. Image-only detector AUCs near 0.5 do not negate this direct attack. The random salt is encoded in publicly decodable image positions, so increasing salt entropy cannot fix it. See `RESULTS.md` for the measurements and their limits.

The encrypted example selects the validation-chosen research candidate: balanced embedding at 0.05 gross bits per pixel, including salt, authenticated framing, padding, and tag. Check `RESULTS.md` for the independent confirmation and limitations. API and CLI defaults retain the blueprint's baseline strategy, so specify `--strategy balanced` to use the experimental extension. At 512 by 512 pixels, the maximum stored message is 1,572 bytes with encryption, or 1,584 bytes in no-key mode, before possible compression gains. Protected regions can still make a cover unusable. The CLI refuses to overwrite any existing output.

For the experimental sign-balancing encoder, pass `--strategy balanced` when embedding. Extraction is unchanged because all payload parities remain unchanged. For a lower-rate profile, pass the same `--rate`, such as `0.01`, to both embedding and extraction. Rate selection is out of band and is not inferred from an unauthenticated header. At 512 by 512, 0.01 bpp allows 261 stored bytes; 0.005 bpp allows 97.

```python
from stegolab.system import Profile, encrypt_and_embed, extract_and_decrypt

# Encrypted mode: key must be 32 random bytes held privately by both endpoints.
stego_png = encrypt_and_embed(cover_png, secret_bytes, key, Profile("0.05"), strategy="balanced")
assert extract_and_decrypt(stego_png, key, Profile("0.05")) == secret_bytes

# No-key mode: omit the key explicitly at both endpoints. The message is not secret.
public_stego_png = encrypt_and_embed(cover_png, secret_bytes, None, Profile("0.05"), strategy="balanced")
assert extract_and_decrypt(public_stego_png, None, Profile("0.05")) == secret_bytes
```

Both paths use operating-system randomness for the per-image salt and frame padding. In encrypted mode, the production path combines it with the private key. The no-key mode deliberately substitutes a fixed, publicly specified layout seed; it provides interoperability, not secrecy. Deterministic randomness and the explicitly public benchmark key must never protect real messages. The bounded in-process caches retain key-dependent mappings; this implementation does not claim secure memory erasure or resistance to local memory inspection.

The measured detectors are key-blind and are not given corresponding original covers. Knowing the original image permits direct comparison; knowing the shared key permits authenticated extraction as a presence test. The public benchmark dataset/key is therefore not a secure live channel against a lookup-capable or key-informed observer.

## Analyze without embedding

Use the same image, message, key, rate and strategy options as `embed`, without `--output`:

```powershell
# Compare the selected frame with the minimum size-fitting frame.
.\.venv\Scripts\stegolab.exe analyze cover.png --message secret.txt --key private.key --rate 0.05 --strategy balanced

# Inspect the frame that automatic rate selection would use.
.\.venv\Scripts\stegolab.exe analyze cover.png --message secret.txt --key private.key --rate auto --strategy balanced
```

`analyze` validates and decodes the PNG, checks the key length, tries the same raw DEFLATE compression as embedding, and calculates the frame with the **same shared planner**. It reports original/stored message bytes, net bpp, chosen and suggested rates, actual gross bpp, capacity usage, free space and any deficit. The byte breakdown includes the salt, header, stored message, padding and authentication tag. The 18-byte header is one version byte, one compression-flag byte, eight bytes for the original length and eight for the stored length. In keyed mode, the header, message and padding are encrypted together; the separate 32-byte salt and 16-byte tag bring fixed overhead to 66 bytes. The fixed 12-byte zero nonce occupies **no frame bytes**. Neither the shared key nor the associated data is embedded.

For an uncompressed five-byte `HELLO` message and a 512 × 512 image:

| Component | Chosen `0.05000000` bpp | Suggested `0.00250000` bpp | Suggested minus chosen |
|---|---:|---:|---:|
| Salt | 32 bytes | 32 bytes | 0 |
| Header | 18 bytes | 18 bytes | 0 |
| Stored message | 5 bytes | 5 bytes | 0 |
| Random padding | 1,567 bytes | 10 bytes | −1,557 bytes |
| Authentication tag | 16 bytes | 16 bytes | 0 |
| Complete allocated frame | 1,638 bytes | 81 bytes | −1,557 bytes |

The padding is the unused **message capacity within the selected frame**, not unused capacity throughout the image. A fixed-rate analysis always shows both columns; `auto` shows the selected minimum frame once. If the chosen rate is too low, padding is displayed as zero and the deficit is explicitly reported: that is an infeasible frame, not a promise that the component sizes fit. A suggested rate above `0.20000000` is explicitly unsupported. Analysis of a valid but infeasible configuration completes successfully, with JSON `fits_by_size: false`; invalid files, keys or explicit rates produce a CLI error. Embedding still rejects an infeasible configuration before computing costs or creating an output.

Analysis does **not** generate salt/padding, derive keys, encrypt, build pixel permutations or codes, compute adaptive costs, or modify an image. By default it writes no files; `--output-logs` writes only the explicitly requested JSON report. Analysis cannot predict changed-pixel counts, PSNR, detector AUC, or whether wet pixels and trellis constraints make a size-fitting frame impossible. `--strategy` is validated and reported but is not executed. Omitting `--key` analyzes the existing public format instead: 32-byte salt + 18-byte header + stored message + 4-byte CRC + padding, with **no authentication tag or confidentiality**.

All user-facing details are in readable stderr logs, including mode, capacity/frame breakdown, decimal rates, step timings, and output paths and sizes where applicable. Stdout is empty. To save the same information in a machine-readable form, add **`--output-logs FILE`** to any command (`analyze`, `embed`, `extract`, or `keygen`). Analysis reports include `chosen` and `suggested` frame dictionaries, decimal `rate`/`suggested_rate` strings, `fits_by_size`, `seconds`, and `timings`. For example:

```powershell
.\.venv\Scripts\stegolab.exe analyze cover.png --message secret.txt --key private.key --rate auto --output-logs analysis.json
$analysis = Get-Content -Raw analysis.json | ConvertFrom-Json
$analysis.chosen.padding_bytes
$analysis.rate
```

JSON reports never replace or suppress the readable console log. Report files use exclusive creation: existing files are not overwritten, and `--output-logs` cannot name the same destination as `--output`. The report destination is reserved before processing begins. Runtime failures also save their error and completed/failed stage timings when a report file has been opened successfully; argument/preflight errors do not create a report. No secret message contents or key bytes are logged. Scripts that previously parsed stdout must now request and read a report file.

## Timed progress logs

`analyze`, `embed`, `extract`, and `keygen` report each stage as it starts, its elapsed seconds when it finishes, and a final total. Completed timing lines remain visible in interactive terminals and redirected logs. Steps have descriptive titles such as “Computing adaptive costs from wavelet residuals” and “Rebuild bootstrap parity matrix and recover the 32-byte salt”, with no walkthrough-number prefixes. The methods are explained in [EMBEDDING_WALKTHROUGH.md](EMBEDDING_WALKTHROUGH.md), but logs stand on their own.

- **Analyze:** input reading, PNG validation, compression/frame planning, comparison/reporting.
- **Embed:** those preparation steps, bootstrap key derivation and shuffling, wavelet costs/wet pixels, salt/body keys, frame/padding, authenticated encryption, whitening, body shuffling, separate bootstrap/body matrix construction, trellis optimization, actual pixel changes and parity checks, optional sign balancing, image statistics, PNG serialization, full extraction self-check, and output writing.
- **Extract:** input reading and PNG validation, context/root key, bootstrap positions/matrix and salt recovery, body keys/positions/matrix and syndrome recovery, undoing whitening, authenticated decryption, header/length validation, removal of padding, optional decompression, and output writing. It never needs a cover image or cost map. No-key mode substitutes public frame/CRC checks for authenticated decryption.
- **Keygen:** secure random-byte generation and exclusive output writing.

The bar indicates progress through stages, **not percentage of execution time or an ETA**. Timings use a monotonic clock. The final total covers the CLI workflow, including input/output, readable reporting and the embedding self-check, but excludes Python startup/imports, argument parsing, and final optional JSON serialization/writing. Per-stage measurements are sequential, not overlapping; small reporting overhead can make their sum slightly smaller than the total. Very short stages can display `0.000 s`; exported JSON retains their unrounded durations. The embedding self-check is one aggregate stage, not a second nested set of extraction timings. Runtime failures identify the failed stage and elapsed total without claiming 100% completion. Logs do not print message contents, key material, salt values or ciphertext.

The additions are covered by CLI/API tests for keyed/public framing, compression, infeasible configurations, no-write/no-crypto analysis, copyable decimal rates at byte boundaries, per-stage timing, analyze → embed → extract recovery, readable-only console output, and optional JSON report safety. The complete suite passed **85 tests** after these changes. They do not change the cipher, wire layout, cost model, trellis optimizer or sign-balancing rules. An additional compatibility check reproduced **12 preserved real-photograph experiment outputs byte-for-byte**, including their non-timing embedding statistics: photograph 1883, three message types, fixed/auto rates and baseline/balanced strategies from `artifacts/runtime_exact/20260926/comparison`. All 12 also extracted correctly with their newly displayed decimal rates; the archived inputs and outputs were only read, never overwritten.

## What the algorithm actually does

A **cover** is the original image. A **stego** is the output image carrying a message. The **payload** is the information the decoder must recover, including cryptographic overhead, not just the user's text. A message can contain arbitrary bytes: the encoder does not interpret text encodings or store the message's filename.

In this implementation, a grayscale pixel is an integer from 0 to 255: 0 is black and 255 is white. The encoder either leaves a pixel alone or changes its value by exactly one. It does not append the secret file to the PNG, put it in metadata, or generate a replacement picture. The secret is represented by mathematical relationships among the even/odd values of existing pixels.

Two problems are solved separately:

- **Cryptography:** keep the message unreadable without the shared key and reject a recovered payload that fails authentication.
- **Steganography:** choose image modifications that are difficult for an observer to distinguish from ordinary image content. Encryption alone does not solve this problem: encrypted bits can still leave detectable image artifacts.

The implemented choices are:

| Component | Purpose | Status in this project |
|---|---|---|
| Raw DEFLATE compression | Fit compressible messages into the available space | Existing compression method |
| ChaCha20-Poly1305 authenticated encryption | Message confidentiality and integrity | Existing cryptographic primitive used in keyed mode |
| Versioned plaintext frame and CRC-32 | Detect accidental corruption in an unencrypted payload | Added for no-key mode; CRC is not cryptographic authentication |
| HMAC-SHA256 key derivation, streams, and keyed shuffles | Reconstruct synchronized positions and codes without transmitting them separately | Blueprint's specified composition of existing techniques |
| Relative-wavelet modification costs | Prefer changes with a small modeled effect on local image residuals | Adaptive distortion approach from the blueprint |
| Binary syndrome-trellis coding, or STC | Find a minimum-cost parity pattern carrying the required bits | Existing coding method, implemented here in C++ |
| Randomized legal `-1`/`+1` changes | Realize the selected parity changes as pixel values | Baseline strategy |
| Conditional residual sign balancing | Reconsider modification directions to reduce selected statistical discrepancies | Experimental extension developed for this project |

The last row is the project's proposed improvement. It is not a newly invented cipher or a replacement for STC. Its precise objective and optimizer were developed here; no claim is made that sign optimization or this combination is unprecedented in the literature.

The encoder is **spatial-domain**: it changes pixel samples. Wavelet filters analyze the image to price those changes; they are not the storage location of the message. No JPEG coefficient embedding, GAN, VAE, diffusion model, or learned latent-space encoder is implemented. The neural network in this repository is a detector used during evaluation, not part of embedding or extraction.

## Why this version restricts its inputs

Single-frame, 8-bit grayscale PNG was the profile selected in the blueprint, not a restriction in the original broad project request and not a fundamental limit of steganography.

- **Grayscale:** the current cost arrays, parity code, and experiments operate on one brightness channel. RGB/RGBA support would need explicitly defined channel handling and evaluation of cross-channel artifacts. A grayscale-looking file can still be encoded as RGB, RGBA, or a palette and will be rejected.
- **8-bit samples:** all implemented sample bounds and unit-change rules assume integers from 0 through 255. A 16-bit grayscale image is a different profile.
- **Single frame:** only one image raster is encoded. Animation, frame ordering, and relationships between frames are not handled.
- **PNG:** the output must preserve the exact integer samples. PNG provides a lossless container for this implementation; this does not imply that PNG is the only possible steganographic carrier.
- **Dimension limits:** each side must be between 256 and 8192 pixels, and the total must be between 262,144 and 16,777,216 pixels. These are implementation/profile bounds, not a security theorem. Large accepted images can still exhaust available memory.

There is deliberately no automatic conversion. Turning a color photograph into grayscale visibly changes the cover and changes its source characteristics. Such conversion can make a file technically acceptable, but is not equivalent to supporting the original color image and does not inherit the benchmark's resistance results.

## Keyed and no-key modes

Mode is selected by whether `--key` is supplied, and the receiver must make the same choice. The library exposes the same choice as `key` versus `None`:

| Mode | Sender and receiver | Body protection | Intended use |
|---|---|---|---|
| Keyed (existing behavior) | Both supply the same private 32-byte key | ChaCha20-Poly1305 encrypts the frame and authenticates it | Confidential payloads with cryptographic integrity |
| No-key plaintext (new) | Both omit `--key` or pass `None` | No encryption or secret key; public layout and reversible whitening carry a CRC-checked frame | Plaintext messages that need no confidentiality |

The no-key mode does not provide the old security properties for free: a public layout seed cannot provide secrecy or cryptographic authentication. The CRC detects many accidental errors, but anyone can alter the message and recompute it. Existing encrypted data must be extracted with its key; plaintext data must be extracted without a key. Modes are not automatically detected or interchangeable.

## Sender: the embedding process

The following steps explain the data dependencies. The implementation computes cover costs early, before constructing the selected frame; neither computation depends on the other's intermediate values.

```text
message bytes -> compression -> versioned mode-specific frame
                                                            |
key or public layout + salt -> derived keys -> body whitening ---+
                                                            v
cover pixels -> modification costs -> two STC embeddings: salt and message body
                                                            |
                                                   legal unit changes
                                                            |
                                            optional sign balancing
                                                            |
                                         lossless PNG + extraction self-check
```

### 1. Validate inputs and calculate the real message capacity

The sender needs a supported image and message bytes. In keyed mode it also needs the same private 32-byte random key the receiver will use. `keygen` creates that key using operating-system randomness. The key file contains binary bytes, not a password, a hexadecimal string, or text. Password-based key derivation and key exchange are not implemented. No-key mode uses a public layout derivation, not a secret key.

Let `N = width * height` be the number of pixels and `r` the requested gross rate in bits per pixel, or **bpp**. One byte contains eight bits. The total embedded byte budget is

$$B = \left\lfloor \frac{N r}{8} \right\rfloor.$$

The floor means round down to a whole number of bytes. The actual gross rate is therefore `8*B/N`, which may be slightly below the requested rate. `Profile` accepts rates from 0.0025 through 0.2 and requires `B >= 66`; accepting a rate does not certify its statistical resistance or embedding feasibility.

The budget is divided as follows:

| Part | Bytes | What it contains |
|---|---:|---|
| Bootstrap salt | 32 | Recovered first; initializes this message's body layout |
| Body target | `B - 32` | Keyed ciphertext and AEAD tag, or whitened plaintext frame, CRC, and padding |
| Keyed frame before encryption | `B - 48` | 18-byte header, stored message, and padding; receives a 16-byte AEAD tag |
| AEAD tag (keyed mode only) | 16 | Authenticates the encrypted frame and associated data |
| Total | `B` | Salt plus the fixed-length body target in either mode |

In keyed mode, the maximum **stored** message is `B - 66` bytes: subtract the 32-byte salt, 16-byte authentication tag, and 18-byte inner header. In no-key mode, it is `B - 54` bytes: subtract the salt, header, and four-byte CRC. Compression may let a longer original message fit. The original message is additionally capped at 16 MiB before compression.

For a 512-by-512 cover at 0.05 bpp:

```text
N                             = 262,144 pixels
B = floor(N * 0.05 / 8)        = 1,638 bytes
salt                          =    32 bytes = 256 embedded bits
encrypted frame               = 1,590 bytes
authentication tag            =    16 bytes
encrypted body plus tag       = 1,606 bytes = 12,848 embedded bits
maximum stored message        = 1,572 bytes
total embedded information    = 13,104 bits
```

These are information bits, not the number of pixels changed. Coding can satisfy many parity equations with substantially fewer modifications. Conversely, nominal byte capacity does not guarantee that a particular image has enough usable pixels.

### 2. Compress, frame, and prepare the selected payload mode

The encoder tries raw DEFLATE compression at level 6, without a zlib wrapper. It uses the compressed bytes only if they are strictly shorter than the original bytes; otherwise it stores the original bytes. Already compressed or random data will usually not benefit.

It constructs the plaintext frame in this exact order:

| Field | Size | Meaning |
|---|---:|---|
| Version | 1 byte | `1` for keyed encryption; `2` for no-key plaintext |
| Compression flag | 1 byte | `0` for original bytes, `1` for raw DEFLATE |
| Original length | 8 bytes | Length before compression |
| Stored length | 8 bytes | Length after the compression decision |
| Stored data | Variable | The message representation |
| Random padding | Remaining space | Fills the keyed frame to `B - 48` bytes before encryption; in plaintext mode it fills the `B - 32` byte body after header, data, and CRC |

Both lengths are unsigned integers in **big-endian** order: the most significant byte comes first. Neither header is a visible PNG marker. In keyed mode, the header and random padding are encrypted and authenticated. In no-key mode, the header is public once extracted; the CRC covers the header and stored data, and random padding fills the rest of the fixed-length frame.

The rate fixes the frame size. A ten-byte message and a thousand-byte message use the same embedded bit budget when they fit the same image/profile. Compression helps a message fit, but does not lower the embedding budget at a fixed rate: the sender fills every unused byte of the selected frame with random padding. This fills **the capacity allocated by the selected rate**, not every pixel or the image's maximum possible capacity. Padding looks random (and is encrypted in keyed mode), but its bits still have to be encoded as parity constraints; they are not free to embed. More constraints generally require more pixel changes. The encoder considers positions spread across the image at either rate, while the gross bpp controls how many target bits it must encode.

For a 512-by-512 image carrying an incompressible 32-byte message in keyed mode:

| Chosen rate | Total embedded frame | Random keyed-frame padding | Gross target bits |
|---|---:|---:|---:|
| `0.05` bpp | 1,638 bytes | 1,540 bytes | 13,104 bits |
| `auto` (reported as `0.00299073` bpp) | 98 bytes | 0 bytes | 784 bits |

Both frames include the same 32-byte message, 18-byte header, 16-byte authentication tag, and 32-byte salt. At `0.05`, padding expands the inner encrypted frame to the chosen budget; at `auto`, the byte budget just fits those fields and the message. Thus `--rate auto` reduces the embedded frame and its padding, rather than making padding less detectable. It chooses the smallest *byte-fitting* rate supported by the profile, not a statistically optimal rate or a guarantee that every cover can embed. The receiver must be given the exact selected rate. An explicit lower rate has the same capacity effect if it fits the message.

#### How the different keys are obtained

**Key derivation** means deterministically obtaining purpose-specific keys from the shared key, rather than using the exact same bytes for every operation. The receiver can repeat it. **HMAC-SHA256** is the keyed hash operation used here; it returns 32 bytes. A **salt** is fresh random input to derivation, not an additional password and not something that must remain secret.

The exact schedule in `primitives.py` and `system.py` can be summarized as follows. `||` means concatenate bytes, `BE32`/`BE64` mean unsigned big-endian encodings, and quoted strings are ASCII. `HMAC(key, data)` puts the key first. `0x00` and `0x01` each denote one byte.

```text
ctx  = "STEG-BP/1" || BE32(width) || BE32(height) || BE64(B) || byte(10)
if key is supplied:
    layout_key = shared_key
else:
    layout_key = SHA256("STEG-BP/1/public-plaintext-layout")
root = HMAC(SHA256("STEG-BP/1/root"), layout_key)
D(k, label) = HMAC(k, label || 0x00 || ctx || 0x01)

split_key     = D(root, "split")
head_code_key = D(root, "head-code")

salt          = 32 fresh random bytes
message_root  = HMAC(salt, root)
aead_key      = D(message_root, "aead")
whitening_key = D(message_root, "whiten")
body_perm_key = D(message_root, "body-perm")
body_code_key = D(message_root, "body-code")
sign_key      = D(message_root, "sign")
```

The context binds these operations to the profile, dimensions, byte budget, and trellis height `10`. Distinct labels separate purposes. In keyed mode the split and bootstrap code depend on the shared key and context; in no-key mode anyone can calculate the same root from the published seed. Neither mode can use the salt for bootstrap positions because the receiver must recover it first.

In keyed mode only, ChaCha20-Poly1305 encrypts the full frame and produces a 16-byte authentication tag. **Authenticated encryption with associated data**, or **AEAD**, both encrypts a plaintext and authenticates additional bytes without encrypting those additional bytes. The associated data in that mode is

```text
"STEG-BP/1/aad" || 0x00 || ctx || salt
```

The keyed implementation uses a twelve-byte all-zero **nonce**, an encryption input that must not repeat with the same AEAD key. This construction relies on a fresh 32-byte salt deriving a fresh AEAD key for each message. It is not permission to reuse a zero nonce under a fixed encryption key. Repeating a salt with the same master key and context repeats the derived key and breaks that discipline. The production path uses `secrets.token_bytes`; deterministic experiment randomness must never be substituted for real secrets. No-key mode does not call AEAD.

The keyed ciphertext and tag are XORed with a separate pseudorandom byte stream. In no-key mode, the unencrypted frame takes this whitening step directly. **XOR** combines bits with the rule `0 XOR 0 = 1 XOR 1 = 0` and `0 XOR 1 = 1 XOR 0 = 1`; applying the same stream twice restores the input. This reversible step is called **whitening**. In no-key mode the stream is public and reversible by anyone: whitening provides no secrecy or cryptographic authentication. In keyed mode it is retained from the blueprint, not presented as additional proven security over AEAD or as a way to make pixel modifications invisible.

The reusable stream mechanism concatenates 32-byte blocks:

```text
block(counter) = HMAC(stream_key, "STEG-BP/1/stream" || 0x00 || BE64(counter))
counter = 0, 1, 2, ...
```

The resulting salt and whitened body are converted to bits, most significant bit first within each byte. Encryption protects what those bits mean; the next steps determine how the bits are represented by pixels.

### 3. Reserve reproducible positions for the salt and body

The image is flattened in row-major order: scan each row from left to right, then proceed to the next row. Pixel positions are numbered `0` through `N - 1`.

Using `split_key`, the encoder applies a **Fisher-Yates shuffle**, which repeatedly swaps an element with a selected earlier element. Draws come from the keyed stream above. When mapping a 64-bit draw to a smaller range, rejection sampling discards the small excess range that would otherwise introduce modulo bias. This is a reproducible pseudorandom permutation, not a sorting of pixels by texture.

The first `floor(N/8)` shuffled positions form the bootstrap pool. The remaining positions form the body pool. The two pools are disjoint, so embedding the body cannot overwrite the salt. A further shuffle of the body pool uses `body_perm_key`, which varies with the salt.

These are pools of candidate positions, not lists of pixels that will all be changed. STC leaves most candidates unchanged. Even protected pixels remain in the shared ordering; they are forbidden to change by their costs rather than removed from the matrix. This matters because the receiver must reconstruct positions without seeing the original cover or its texture map.

The bootstrap stores the salt as 256 parity equations across its pool. It does not put the salt into the first 32 PNG bytes or directly overwrite 256 selected pixel bits. The receiver knows the bootstrap positions and code before it knows the salt; after recovering the salt, it can reconstruct the body positions and code. This resolves the otherwise circular problem of needing the salt to find the salt.

For a reused key and identical dimensions/budget, bootstrap positions and the bootstrap matrix repeat. Fresh salts vary body ordering and body codes; they do not make every part of the layout fresh. Repeated-image and reused-key analysis remain limitations of the measurements.

### 4. Compute a modification cost for every pixel

A **cost** is an encoder's numerical estimate of how undesirable a change would be. It is not a measured detection probability. The code assigns separate costs to decrementing and incrementing each pixel.

A **residual** is the output of a filter that suppresses slowly varying brightness and emphasizes differences or other local structure. For intuition, the difference between neighboring pixel values is a simple residual: a flat region gives small values, while irregular texture often gives larger values. The implemented cost model uses more elaborate directional filters instead of that simple difference alone.

`costs.py` contains fixed 16-tap low-pass and high-pass filters. A **tap** is a filter coefficient multiplying one neighboring sample. Three separable two-dimensional filters combine vertical and horizontal low/high filters as `(low, high)`, `(high, low)`, and `(high, high)`. "Separable" means applying one one-dimensional filter vertically and another horizontally instead of directly multiplying by a full two-dimensional kernel.

All residual maps retain the original resolution. Boundaries use reflected samples. The implementation fixes the even-length filter alignment explicitly; changing that alignment changes the costs. The exact coefficients and alignment are in [costs.py](src/stegolab/costs.py), rather than an unspecified library-default wavelet transform.

Let `C` be the original pixel vector, `A_k` the linear operation for filter `k`, and `R_k = A_k C` its residual image. Let `A[k,p,i]` denote how much residual position `p` changes when pixel `i` increases by one. The raw cost for a legal interior pixel is

$$\rho_i = \sum_{k=1}^{3}\sum_p \frac{|A[k,p,i]|}{1 + |R_k[p]|}.$$

The numerator measures the unit change's influence on each affected residual. The denominator makes that influence less expensive where existing residual activity is large. The added `1` avoids division by zero. The sums include only positions affected by the filter support, which is the neighborhood touched by its nonzero coefficients.

This is a relative-wavelet distortion model: it prices a change relative to pre-existing local activity. It does not simply select the strongest edges. A clean edge can remain predictable in another direction; the sum over directional filters can still penalize changes there. Costs are computed from the original cover once, not recomputed after each STC decision.

To make the trellis's cost arithmetic integer-valued, the implementation uses

$$w_i = \max\left(1,\left\lfloor 10^6\rho_i + 0.5\right\rfloor\right).$$

A **wet** pixel is one the encoder is forbidden to change; a **dry** pixel permits at least one direction. The implementation uses the sentinel `2^32 - 1` for a forbidden direction, interpreted as infinite cost inside the optimizer. The following rules apply:

- All pixels in the 16-pixel-wide outer border are wet in both directions.
- A pixel whose reflected 5-by-5 neighborhood has population variance at most `1` is wet in both directions. Variance is the mean squared departure from the neighborhood mean, measured in squared grayscale levels.
- A value of `0` cannot be decremented; a value of `255` cannot be incremented.
- Other legal directions receive `w_i`. Away from the sample bounds, the `-1` and `+1` costs are equal.

The flatness check is computed from integer window sums: if `s1` is the sum of the 25 samples and `s2` the sum of their squares, the pixel is protected when `25*s2 - s1*s1 <= 625`. This is exactly the variance-at-most-one criterion. Moderately smooth regions are not all forbidden: they receive the residual-based finite costs above.

For the binary parity optimizer, the cost of flipping a pixel's parity is the cheaper of its legal direction costs. A perfectly flat cover can therefore fail even when the byte-budget calculation says the message fits. Reserving more wet pixels is not automatically more secure; it also concentrates changes elsewhere and can make a requested codeword impossible.

### 5. Encode bits through syndrome-trellis coding

The **least significant bit**, or **LSB**, of an integer is its even/odd bit: `value & 1` is `0` for even and `1` for odd. It is also called the pixel's **parity**. Adding or subtracting one flips parity; leaving the pixel alone preserves it.

The encoder does not set one pixel's LSB equal to each payload bit. Instead, it constructs a binary **parity-check matrix** `H`. Each row specifies a group of pixel parities to XOR together. A `1` includes a position in that row's XOR; a `0` excludes it. The vector of row results is the **syndrome**, and that is where the message bits reside.

For one pool, let `n` be its number of positions, `m` its number of target bits, `x` the original parity vector, `y` the chosen output parity vector, and `t` the target bits. The encoder solves

$$\underset{y\in\{0,1\}^{n}}{\operatorname{minimize}}\quad
\sum_{i=0}^{n-1} w_i\,\mathbf{1}[y_i\ne x_i]
\qquad\text{subject to}\qquad Hy=t\pmod 2.$$

The indicator `1[condition]` is one when its condition holds and zero otherwise. Arithmetic modulo two means addition is XOR. Wet positions must keep `y_i = x_i`. Many parity vectors can satisfy the same syndrome, which gives the optimizer freedom to select a low-cost one.

#### A small worked example

This three-pixel example illustrates matrix embedding; it is not the production matrix or a supported image size.

```text
Original pixel values:   [100, 120, 140]
Original parities x:     [  0,   0,   0]
Parity-change costs:    [  8,   1,   2]

H = [1 0 1]     Target t = [1]
    [0 1 1]                [0]
```

The target asks for `y0 XOR y2 = 1` and `y1 XOR y2 = 0`. There are two valid parity vectors:

- `[1, 0, 0]`: change only the first pixel, costing `8`.
- `[0, 1, 1]`: change the second and third pixels, costing `1 + 2 = 3`.

The second option is cheaper even though it changes more pixels. One legal output is `[100, 119, 141]`. The receiver reads its parities `[0, 1, 1]` and computes the two XORs to recover `[1, 0]`. It does not need the original values or the change costs.

This explains both why coding is not simple bit overwriting and why minimum modeled distortion is not always the same as the fewest changed pixels.

#### How the real matrix and trellis work

The production matrix has `m` rows and `n` columns, but the full dense array is never allocated. Its structure is **banded**: each column affects at most ten consecutive syndrome rows. In block `j`, column indices run from `floor(j*n/m)` through `floor((j+1)*n/m)-1`. That block starts at syndrome row `j`.

For each column, an HMAC of its row and column indices under the stage's code key creates a ten-bit mask. The lowest and highest bits are forced on, then bits beyond the final syndrome row are removed. Bit `b` of a mask specifies whether this column contributes to syndrome row `j+b`. Both endpoints regenerate these masks identically. The bootstrap uses `head_code_key`; the body uses `body_code_key`.

A **trellis** is a compact record of possible partial parity states as the encoder walks through columns. With height ten, there are at most `2^10 = 1,024` states. The native dynamic-programming optimizer:

1. Starts with the all-zero partial syndrome at cost zero; other states are initially unreachable.
2. Considers output parity `0` and `1` for each column. Keeping the original parity costs zero; changing it costs that pixel's parity-change cost. Choosing `1` XORs the column mask into the partial syndrome.
3. Retains the cheaper path into each state. Exact cost ties prefer the output-`0` transition.
4. At the end of each column block, discards states whose lowest bit disagrees with the next target bit, then shifts the active syndrome window by one row.
5. Ends in the zero state after the last target row and follows saved decisions backward to reconstruct the chosen parity vector.

Costs accumulate in 64-bit integers; traceback decisions are bit-packed. The result is an exact optimum for this finite matrix and its integer additive costs, not a proof of the globally least detectable image or the information-theoretically best code. Runtime grows roughly as `n * 2^10`; traceback uses roughly `n * 2^10` bits per stage, plus working arrays. For the 512-by-512 example, the body stage alone needs about 28 MiB of traceback. Larger images can require substantial resources.

The encoder runs this process twice: once for the 256 salt bits and once for the whitened body bits. It rejects a pool with fewer dry positions than target bits as an admission policy. Even passing that count check does not guarantee that the requested syndrome is reachable with the banded matrix and wet constraints. Unreachable syndromes and resource exhaustion are reported as failures, not silently worked around by changing the rate.

Despite being a coding method, this STC is not a repair mechanism for corrupted transport. Extraction evaluates the syndrome; it does not reconstruct the original pixel values or correct arbitrary image edits.

### 6. Turn chosen parity changes into actual pixel changes

Where STC chose `y_i = x_i`, the pixel is left alone. Where it chose the opposite parity, the encoder selects a legal unit change:

- At value `0`, use `+1`; at value `255`, use `-1`.
- If direction costs differ, use the cheaper legal direction.
- For equal costs, choose `-1` or `+1` using a bit from the separate `sign_key` stream. The same stream cursor continues from the bootstrap stage into the body stage.

For example, changing cover value `120` to either `119` or `121` satisfies a required odd parity. The baseline makes an independently pseudorandom direction choice when costs tie. It verifies that each stage's modified pixels yield the requested syndrome.

With `--strategy baseline`, these are the final pixel values before serialization. With `--strategy balanced`, the next step uses the remaining freedom in modification direction.

### 7. Experimental conditional residual sign balancing

This is the method developed for this project. Its hypothesis is: after STC has chosen sensible locations to modify, the remaining choice between `-1` and `+1` can be used to reduce certain statistical artifacts without sacrificing payload or adding changed pixels.

#### Why directions can change without destroying the message

For original value `120`, `119` and `121` have the same odd parity. Replacing a baseline modification `120 -> 121` with `120 -> 119` changes the current stego by two levels but still leaves it only one level away from the original. Every parity equation remains unchanged.

Let `T` be the fixed set of changed positions and `s_i` their modification signs. The candidate image is

$$S_i(s)=C_i+s_i\mathbf{1}[i\in T],\qquad s_i\in\{-1,+1\}.$$

The optimizer freezes `T` and permits only sign reversals. Pixels originally at 0 or 255 retain their only legal direction. It never adds changes at protected pixels or moves a modification elsewhere.

For this implementation, the operation preserves:

- Every pixel parity, hence both embedded syndromes and the complete payload.
- The changed-pixel set and the number of changes.
- The absolute change of one at every changed pixel.
- The additive distortion cost, because both directions have equal cost at pixels eligible for a sign reversal.
- The squared pixel error and therefore PSNR, the peak-signal-to-noise ratio used to summarize that error. This does not imply that every other visual metric, such as SSIM, is unchanged.

#### What statistical discrepancy is minimized

The cost model above selected **where** to change pixels. Balancing now assesses the actual joint effect of those changes on several residual histograms. A **histogram** counts how many residuals fall in each value bin; it is not a complete model of the image distribution.

First, compute the cover's local 5-by-5 variance and freeze four activity groups: variance below `16`, from `16` up to `64`, from `64` up to `256`, and at least `256`. This is the **conditional** part of the method: histogram counts are kept separately for different texture levels, instead of allowing changes in a smooth area to be canceled statistically by changes in a textured area. The group of each residual center is defined by the original cover, not recomputed from the evolving stego.

Next, apply eight small integer filters to both cover and stego. For a sample at row `a`, column `b`, the filters measure horizontal and vertical first differences, horizontal and vertical second differences, two diagonal first differences, a four-neighbor Laplacian, and a nine-tap residual. The last two kernels, applied around the center sample, are:

```text
Four-neighbor:       Nine-tap:
 0   1   0          -1   2  -1
 1  -4   1           2  -4   2
 0   1   0          -1   2  -1
```

For example, the horizontal first difference is `C[a,b+1] - C[a,b]`; the horizontal second difference is `C[a,b-1] - 2*C[a,b] + C[a,b+1]`. These filters are deliberately separate from the 16-tap wavelet filters used for embedding costs. Histogram centers exclude the outer two rows and columns; all modifiable pixels are already farther from the boundary because of the 16-pixel wet border.

For each filter and activity group, form histograms at three **quantization** steps, `q = 1, 2, 4`. Quantization divides a residual by `q` and rounds to an integer, grouping nearby values. Here the rule is

$$Q_q(v)=\operatorname{clip}\left(\operatorname{sign}(v)
\left\lfloor\frac{|v|+q/2}{q}\right\rfloor,-8,8\right).$$

`sign(v)` is `-1`, `0`, or `+1`; `clip` limits the result to the indicated range. Halfway cases round away from zero. Each histogram has 17 bins, labeled `-8` through `8`, with large magnitudes collected into the endpoint bins. There are `8 * 4 * 3 * 17 = 1,632` counts altogether.

Let `j` identify one filter/group/quantization/bin combination, `c_j` its count in the cover, and `d_j` the current stego count minus the cover count. The objective is

$$J=\sum_j\frac{d_j^2}{c_j+32}.$$

Smaller `J` means closer agreement with these specific cover histograms. The denominator accounts for the original bin population; the added `32` limits the weight of empty or rare bins. It is a fixed design parameter, not a learned probability or a confidence bound. `J` is neither KL divergence nor a detector AUC.

#### How the optimizer searches

Starting from baseline signs, it visits eligible changed pixels in raster order, alternating forward and backward scans for at most six passes. For each pixel, it considers reversing its sign. A sign `s_i` would change the current stego sample by `-2*s_i`.

Only a few nearby residuals depend on that pixel. The implementation calculates their old and new bins and accumulates a proposed count increment `u_j` for each affected histogram bin. Contributions landing in the same bin are combined before evaluating the objective change:

$$\Delta J=\sum_{j:u_j\ne0}\frac{2d_j u_j+u_j^2}{c_j+32}.$$

This is obtained by expanding `(d_j + u_j)^2 - d_j^2`, so it evaluates the same objective without rebuilding every histogram for every trial. The code accepts a reversal only when `Delta J < -1e-12`, then updates the affected residuals and counts. A complete pass accepting no reversals ends the search early. The small negative tolerance avoids accepting numerical near-ties.

This is a **greedy local search**: each accepted step improves the current objective, but the method does not prove that the final sign configuration is the global minimum. If the six-pass limit is reached, further improving reversals may still exist. A pixel can be reversed more than once across passes, so the reported `balance_flips` counts accepted reversal operations, not necessarily distinct pixels.

```text
baseline = embed_salt_and_encrypted_body_with_STC(cover)
changed_positions = positions_where(baseline != cover)
current = copy(baseline)
groups, cover_counts = statistics_of_original_cover(cover)
state = residuals_and_histogram_differences(current, cover_counts, groups)

for pass in 0..5:
    reversals = 0
    for pixel in alternating_raster_order(changed_positions, pass):
        if cover[pixel] is 0 or 255:
            continue
        proposal = histogram_increments_if_sign_is_reversed(pixel, state)
        if exact_objective_increment(proposal, state) < -1e-12:
            reverse_sign_relative_to_cover(pixel)
            update_state(proposal)
            reversals += 1
    if reversals == 0:
        break

verify_that_every_pixel_parity_is_unchanged()
```

Balancing does not consult a trained detector, retrain a network, change the payload, or lower its rate. Only the sender needs the original cover and its activity groups. The receiver does not undo balancing and does not need to know which strategy was used.

#### Why a better objective is not automatically better security

Matching these counts leaves many properties unconstrained, including relationships between neighboring residuals, distant pixels, and repeated images. Greedy sign decisions may introduce new dependencies or scan-order patterns. A detector can exploit something the objective ignores. The independent benchmark therefore compares both strategies at the same rate, with the same messages, random inputs, and changed-pixel sets. It does not count a lower `J` or unchanged PSNR as resistance evidence.

### 8. Serialize and verify the finished output

The result is saved as a grayscale PNG using compression level 6 with optimization disabled. PNG compression changes file bytes but preserves pixel samples. No secret-bearing metadata or plaintext message marker is added. Arbitrary ancillary metadata from the original is not preserved, and the serializer does not promise to reproduce every camera or editor's file fingerprint.

Before returning the PNG, the public embedding API decodes its own output, checks exact pixel equality with the intended stego, and performs full extraction using the selected mode. The recovered message must exactly match the input bytes. The keyed path checks the AEAD tag; the no-key path checks the frame CRC. The CLI writes the output only after this succeeds and uses exclusive creation to refuse overwriting an existing file.

This proves a particular output round-trips correctly under the implemented profile; it does not test its statistical invisibility. The benchmark sends cover controls through the same serializer so that an obvious difference in serializer choice does not stand in for detecting pixel changes. Real deployment still needs to consider metadata and file-source fingerprints.

## Receiver: extraction without the original image

The receiver supplies the stego PNG, the same rate/profile, and either the same shared key (keyed mode) or no key (no-key mode). It does not need the original cover, cost map, message length, sender's modification signs, or `--strategy`.

1. Strictly decode the PNG and calculate `N`, `B`, and `ctx` from its dimensions and the supplied rate.
2. Derive the root, split key, and bootstrap code key. Reconstruct the bootstrap pool and the rules defining its matrix.
3. Read the even/odd bits at bootstrap positions and evaluate its parity equations. Pack the resulting 256 bits into the 32-byte salt.
4. Derive the salt-dependent keys, shuffle the body pool, and reconstruct the rules defining the body matrix.
5. Evaluate the body's parity equations to recover `8*(B-32)` bits. Pack them into the whitened ciphertext-and-tag bytes.
6. XOR with the same whitening stream. In keyed mode, authenticate and decrypt with ChaCha20-Poly1305, the same nonce, and associated data. In no-key mode, these bytes are the unencrypted frame.
7. In keyed mode, check the authenticated version, compression flag, lengths, and bounds. In no-key mode, check version `2`, the bounds, and CRC-32 over the header and stored data. The CRC detects accidental damage; it cannot authenticate a sender or stop deliberate forgery. Discard padding using the stored length.
8. Return the raw bytes, or decompress raw DEFLATE with a bound based on the original length. Require the exact expected length and a complete stream without trailing compressed data.

The crucial identity is `H * parity(stego) = target`. Extraction evaluates that identity directly; it does not search for changed pixels. Recomputing costs from a modified image is unnecessary and could give different results, which is why costs never determine the receiver's position ordering.

On an updated Windows build, standalone extraction generates only columns whose observed parity is one and immediately accumulates their contributions; it does not allocate the full column array. This evaluates the **same** matrix equations. Older builds use the full array, and embedding's built-in self-check reuses its already computed arrays. See [Native extraction acceleration](#native-extraction-acceleration) for the exact mechanism, measurements and limitations.

In keyed mode, an ordinary image, wrong key, wrong rate/profile, or sufficiently damaged payload normally ends in `No valid authenticated payload`. In no-key mode, the corresponding error is `No valid plaintext payload`. There is no reliable unauthenticated "message present" marker. Anyone who knows the no-key format can try extracting the payload; anyone with the shared key can use successful keyed extraction as a presence test.

In keyed mode, authentication covers the recovered frame and associated context, not every image pixel or every PNG metadata byte. In no-key mode, the CRC covers only the frame header and stored data. Some image edits can preserve all extracted parity equations and leave the message valid. Conversely, a visually harmless recompression, resize, rotation, or color conversion may destroy those equations. This is not robust watermarking or complete-image authentication.

## What the experiments demonstrated

The full saved evidence is in [RESULTS.md](RESULTS.md). It measures the **keyed encrypted mode** on native 512-by-512 grayscale images, using 1,200 training covers, 400 validation covers, and 1,000 held-out test covers. Related images identified by exact and approximate hashes were grouped before splitting. The selected `balanced` strategy at 0.05 gross bpp successfully embedded in 998 test covers and rejected two; every admitted baseline and balanced sample was serialized, extracted, and authenticated. The no-key plaintext mode was added separately and has not been benchmarked; those resistance measurements do not apply to it.

A **steganalyzer** is a detector that tries to distinguish ordinary covers from stegos. The experiments used two standalone image statistics, two trained residual-feature classifiers, and a compact residual convolutional neural network, or **CNN**. Residual features include counts of neighboring residual combinations, not just the individual-value histograms optimized by balancing. This gives the test detectors information outside the balancing objective, but does not make them exhaustive adversaries.

**ROC-AUC** summarizes how well a detector ranks stegos above covers across decision thresholds: 0.5 corresponds to chance ranking, 1 to perfect ranking in the chosen direction, and a reliably low value can be exploited by reversing that direction. AUC is not the probability that one particular image will be detected. Score directions and decision thresholds were chosen on validation, not on the final test.

The agreed empirical gate requires each detector's paired source-group bootstrap 95% AUC interval to lie inside `[0.45, 0.55]`. Bootstrapping here means repeatedly resampling image groups with their corresponding cover/stego predictions kept together to estimate sampling uncertainty. These intervals concern the fitted detector and sampled source; they do not include uncertainty over all possible training procedures, keys, or cover sources.

| Held-out detector | Baseline AUC | Balanced AUC | Balanced 95% interval |
|---|---:|---:|---|
| Adjacent-bin chi-square statistic | 0.5023 | 0.5022 | [0.5013, 0.5038] |
| RS-like regularity statistic | 0.5012 | 0.5008 | [0.4998, 0.5023] |
| Residual subspace ensemble | 0.5218 | 0.5130 | [0.5103, 0.5163] |
| Residual Extra Trees | 0.5112 | 0.5091 | [0.4985, 0.5204] |
| Compact residual CNN | Not run for baseline | 0.5023 | [0.5012, 0.5041] |

Both sender strategies passed the classical gate. The balanced candidate also passed the separate neural check. This was an improvement experiment, not a case where the baseline first failed and balancing magically made it undetectable.

The same-rate paired comparison supports a reduction in residual-ensemble AUC of `0.0088`, with a balanced-minus-baseline interval of `[-0.0125, -0.0055]`. The Extra Trees difference interval includes zero, so an improvement for that detector is not established. No paired neural baseline comparison was performed. At 0.01 bpp on validation, balancing also did not uniformly improve detector scores; lowering rate is a separate capacity trade-off.

A separate keyed `--rate auto` experiment reused the same 32-byte messages and held-out image split. On the 998 covers accepted by both rates, the independently trained compact CNNs scored AUC `0.501286` at `0.05` bpp and `0.500001` at the auto rate. Mean changed pixels fell from about `2,343` to `107`. The paired AUC difference was `-0.001285` (95% source-group bootstrap interval `[-0.001793, -0.001113]`). This is a small measured reduction for these saved CNNs, not proof that the minimum rate is always safest: both scores are near chance, the interval excludes retraining and model-family uncertainty, and changing the rate also changes the rate-dependent embedding schedule. See [RESULTS.md](RESULTS.md) for the complete comparison and limitations.

The deliberately detectable positive control used random LSB replacement at 0.4 bpp. Its held-out ensemble, Extra Trees, and CNN AUCs were approximately `0.9892`, `0.9981`, and `0.9964`. These confirm basic detector functionality, not sufficient sensitivity to every subtle low-rate signal. The CNN is a small CPU-trained model, not a full SRNet reproduction. A 95% interval entirely above 0.5 still indicates a detectable signal even if it meets the provisional 0.55 bound.

For the accepted 0.05-bpp test covers, the mean number of changed pixels was about 2,343, or 0.894% of the image, and mean PSNR was 68.64 dB. For unit changes, if `K` pixels change, mean squared error is `K/N` and

$$\operatorname{PSNR}=10\log_{10}\left(\frac{255^2}{K/N}\right).$$

PSNR measures pixel-level fidelity, not statistical security; sign balancing leaves it identical to the baseline. The mean balancing objective decreased from about `178.104` to `19.237`, but its units have no direct interpretation as a probability of detection.

Nothing here establishes universal indistinguishability, security against a known original cover, immunity to stronger detectors, color-image resistance, or safe repeated use across arbitrary sources. Preserve the frozen measurements when extending the algorithm and use independent data for new confirmation.

## Does automatic rate reduce execution time?

These measurements were recorded **before the native primitive acceleration** described in the next section. They remain the historical comparison of choosing `auto` versus `0.05`; the [original-versus-optimized comparison](#exact-output-native-acceleration) measures the later implementation speedup separately.

**Measured result: a modest saving for small messages, and no consistent saving for the larger message tested.** Reducing the complete frame from 1,638 to 81 bytes did not make embedding twenty times faster: the `HELLO` benchmark saved about 5% of complete CLI runtime. The frame describes how many bits must be represented, while much of the implementation's work still depends on the number of image pixels.

The run on 2026-09-26 used three real BOSSbase photographs (`1883`, `4000`, `8872`), the first three covers in the existing training manifest. Their native 512-by-512 grayscale rasters were losslessly encoded as PNG before timing. Each message was tested on each photograph five times at each rate: **90 measured CLI executions**, using keyed mode and `--strategy balanced`. None of these three messages became smaller after compression. Each pair used the same cover and message; rate order alternated, workload order was shuffled, and production salt/padding randomness remained enabled. Two initial CLI warm-ups were excluded. Execution was sequential on Windows 11 x64, Python 3.14.5, an Intel Family 6 Model 154 processor with 16 logical CPUs, with numerical-library thread limits set to one.

The timer surrounded a fresh `python -m stegolab.cli embed` subprocess. It includes process startup, imports, input reads, all embedding stages, PNG encoding, built-in decode/extract/authenticate verification, output writing, and process exit. CLI output was captured through pipes. Filesystem caches were warm; this was an ordinary workstation run, not an isolated latency benchmark.

| Message (original = stored bytes) | Auto requested bpp | Frame bytes, fixed → auto | Median CLI seconds, 0.05 | Median CLI seconds, auto | Median paired time saving | Auto faster pairs |
|---|---:|---:|---:|---:|---:|---:|
| `HELLO` (5) | 0.0025 | 1,638 → 81 | 2.543 | 2.404 | 5.25% | 14 / 15 |
| Incompressible binary (32) | `0.00299073` | 1,638 → 98 | 2.486 | 2.409 | 4.17% | 13 / 15 |
| Incompressible binary (1,024) | `0.03326417` | 1,638 → 1,090 | 2.515 | 2.527 | −0.29% | 6 / 15 |

Paired saving is calculated as `100 × (fixed time − auto time) / fixed time` for each matched execution pair, then summarized by its median; it is not the percentage calculated from the two separately reported median times. Negative values mean auto took longer. No observations were removed: individual paired savings ranged from −27.0% to +7.3% for `HELLO`, −7.8% to +20.9% for 32 bytes, and −6.2% to +6.3% for 1,024 bytes. In particular, auto is not guaranteed to win on every invocation, and the 1,024-byte timings do not demonstrate a useful speed advantage.

### Which stages account for the time?

A separate **36-call API profile** measured `encrypt_and_embed`, including its PNG serialization and authenticated self-check: three photographs, three repeats, two rates, and both `baseline` and `balanced` strategies. Imports and filesystem I/O were outside this timer. Layout and matrix caches were cleared before every call, but reuse during that call's self-verification remained enabled, as in normal embedding. Timers wrapped whole functions without instrumenting the inner loops, and nested spans were excluded to avoid counting the same work twice.

The following are **mean stage times** for `HELLO` with `balanced`, from nine calls per rate. They describe this separate API profile, not subdivisions of the CLI medians above.

| Stage | 0.05 bpp, milliseconds | Auto, milliseconds |
|---|---:|---:|
| Bootstrap and body pixel shuffles | 613.0 | 616.6 |
| Parity-matrix construction | 744.2 | 726.0 |
| Adaptive image cost map | 60.2 | 60.5 |
| Bootstrap syndrome-trellis optimization | 44.7 | 43.3 |
| Body syndrome-trellis optimization | 365.1 | 289.0 |
| Modification-sign balancing | 57.2 | 46.5 |
| Remaining work: PNG, verification, framing, cryptography, etc. | 25.3 | 24.8 |
| **Complete API call** | **1,909.7** | **1,806.7** |

The same API experiment without sign balancing (`baseline`) also showed a modest reduction: median total time went from 1.833 to 1.737 seconds, with a 5.00% median paired saving. Therefore the observed improvement was not solely the result of changing fewer modification signs.

The code explains the limited gain:

- Both rates compute costs across the full image and shuffle the same number of pixel positions. Matrix construction still generates a column for every position. Shuffling and matrix construction alone consumed about 71% of the fixed-rate balanced API time.
- Trellis height remains 10, so the native encoder still loops over 1,024 states for each pixel column. The dominant loop is proportional to `N × 2^10`, not just the number of embedded bits. Fewer target bits reduce row-constraint operations, but do not reduce the number of columns or eliminate the image-wide scan.
- Sign balancing has fewer modified pixels to consider, but still initializes residual statistics over the full image. PNG processing and CLI startup also remain necessary.
- Encryption, whitening, and padding process fewer bytes, but those small buffers were not the dominant expense. Automatic selection additionally performs an extra compression trial to determine the fitting rate.

For this implementation and these inputs, use `auto` to avoid unnecessary embedded padding and reduce modifications; treat the measured runtime reduction as a small additional benefit. The timings cover three 512-by-512 photographs on one machine, not every image size or workload. They do not add new steganalysis evidence.

All 126 measured embedding operations passed their built-in round-trip check. Six additional fresh-process CLI extractions, covering all three message sizes at both rates, recovered byte-identical messages. The reproducible driver is [scripts/benchmark_auto_rate.py](scripts/benchmark_auto_rate.py). Per-run timings, stage spans, failures, input/output hashes, software versions, source/native-binary hashes, subprocess logs, and generated PNGs are preserved under [artifacts/runtime_auto/20260926](artifacts/runtime_auto/20260926), including [summary.json](artifacts/runtime_auto/20260926/summary.json) and [records.jsonl](artifacts/runtime_auto/20260926/records.jsonl). These local artifacts are ignored by Git; the measurements above remain in this README.

To repeat the measurement with a new timestamped output directory:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_auto_rate.py --covers 3 --repeats 5 --profile-repeats 3
```

Every completed observation is checkpointed immediately. To continue an interrupted run, supply its printed directory with `--output <directory> --resume` and the same cover/repeat settings. An existing directory is otherwise refused, so rerunning the benchmark does not replace the saved measurements.

## Exact-output native acceleration

The optimized Windows implementation substantially reduces runtime while preserving the same embedding output for the same image, message, key, salt, and padding. It retains the full-image computation: unchanged pixel parities still contribute to the syndrome equations, and the best positions to modify are only known after optimization. Simply selecting a smaller pixel pool would change those equations or the candidate solutions.

The measured bottleneck was the overhead of executing HMAC and shuffle loops in Python. The optional native backend now batches three existing operations:

- Generate exactly the same `HMAC-SHA256(key, label || counter)` stream blocks, including their original byte ordering and counter boundaries.
- Perform exactly the same Fisher–Yates swaps and rejection sampling, consuming the same stream bytes in the same order.
- Generate exactly the same HMAC-derived parity columns, with the same row/column numbers, forced mask bits, and truncated final rows.

Hashing uses Windows' [reusable CNG HMAC contexts](https://learn.microsoft.com/en-us/windows/win32/seccng/creating-a-hash-with-cng), so keyed setup is reused within each batch. No new hash or random generator was designed. Shared-key derivation, salt/padding generation, ChaCha20-Poly1305, nonce/AAD handling, cost computation, the STC optimizer and its tie-breaking, and modification-sign balancing are unchanged. Existing receivers remain compatible. The native code is in [primitives.cpp](src/stegolab/native/primitives.cpp), with dispatch and the original Python fallback in [primitives.py](src/stegolab/primitives.py).

### Exactness and measured speed

Before editing the implementation, the original Python package and native DLL were preserved. **36 real-photograph cases** compared that independent snapshot with the optimized package in fresh processes: three BOSSbase photographs, three message types (`HELLO`, 1,024 incompressible bytes, and compressible text), two rates (`0.05` and `auto`), and both `baseline` and `balanced` strategies. Each case supplied identical research-only randomness to both versions. Every comparison matched the complete PNG bytes, pixel bytes, plaintext frame, ciphertext/tag bytes, associated data, derived encryption-key digest, and non-timing embedding statistics. Every generated image also passed authenticated extraction. Normal CLI use continues to generate fresh randomness, so two ordinary invocations are not expected to produce the same PNG.

A separate timing comparison ran **72 complete CLI executions**, pairing the preserved original package with the optimized package. Each table row contains nine pairs: the same three photographs with three repetitions each, using `--strategy balanced`. Both versions ran sequentially in alternating order, with fresh production randomness. Timing includes process startup/imports, input/output, embedding, PNG serialization, and the authenticated self-check, as in the earlier benchmark. These are paired measurements from the same run, not a comparison against the earlier table's historical timings.

| Message | Rate option | Original median CLI seconds | Optimized median CLI seconds | Median paired time saving | Optimized faster pairs |
|---|---|---:|---:|---:|---:|
| `HELLO` | `0.05` | 2.681 | 1.340 | 49.55% | 8 / 9 |
| `HELLO` | `auto` | 2.804 | 1.355 | 55.08% | 9 / 9 |
| 1,024 binary bytes | `0.05` | 2.778 | 1.300 | 53.18% | 8 / 9 |
| 1,024 binary bytes | `auto` | 2.939 | 1.543 | 51.01% | 9 / 9 |

Thus complete execution was roughly twice as fast on this Windows workstation, with the same embedding algorithm. Percentages are medians of paired savings, not ratios of the separately summarized median times. No outliers were removed: savings ranged from −27.91% to +64.80% across all 36 pairs, and the optimized version was faster in 34 pairs. The machine was not isolated from background activity; these measurements do not promise a particular latency on every invocation or platform.

The full suite passed **47 tests**, including independent standard-library HMAC comparisons, empty/short/long keys, fragmented streams and counter boundaries, exact permutations and matrix columns, and byte-identical PNGs with cross-backend extraction. Compatibility checks also cover the public feature. These checks preserve the existing image-format and statistical-security behavior; they do not assert any stronger security claim or constitute a new detector experiment.

The updated DLL has been built locally. After pulling these source changes elsewhere, rebuild it with:

```powershell
.\.venv\Scripts\python.exe scripts/build_native.py
```

Windows uses the new backend automatically when the updated library is available. Older libraries and other platforms continue to use the Python primitives. Setting the diagnostic environment variable `STEGOLAB_NATIVE_PRIMITIVES=0` also selects the Python path; it does not change the format or cryptographic algorithms.

The original snapshot is preserved under `artifacts/runtime_exact/20260926/reference`. [Comparison results](artifacts/runtime_exact/20260926/comparison/summary.json), per-case encrypted-frame reports, exact PNG pairs, logs, and implementation hashes are saved under `artifacts/runtime_exact/20260926/comparison`. The [comparison driver](scripts/benchmark_exact_optimization.py) checkpoints after each completed case or timing pair. To repeat against that snapshot in a new directory:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_exact_optimization.py --reference artifacts/runtime_exact/20260926/reference --output artifacts/runtime_exact/repeat
```

Use `--resume` with the same paths to continue an interrupted comparison. The preserved snapshot and measurement artifacts are local files ignored by Git; the source changes, tests, and result tables above can be versioned.

## Native extraction acceleration

The `extract` command and `extract_and_decrypt` API now use an extraction-only Windows fast path. The shared-key mode remains the main workflow; the optional public mode also benefits. No CLI arguments, key files, stego images or rate profiles need converting.

### What is skipped, and why the result is identical

Let `y[i]` be pixel `i`'s parity (zero for an even value, one for an odd value) **after placing pixels in the existing keyed pool order**. Let `H[:, i]` be its parity-matrix column. Extraction computes over binary arithmetic:

$$
s = H y = \bigoplus_{i:y_i=1} H_{:,i}.
$$

Here, multiplication by zero gives an all-zero column; adding binary columns means XOR, with no carry. Consequently a pixel with parity zero makes no contribution. For example, for parities `[0, 1, 0, 1]`, the answer is column 1 XOR column 3: columns 0 and 2 never need generating. These are **current pixel parities**, not the locations changed by the sender; the receiver does not know the latter.

Previously, the native receiver generated all `n` column HMACs, stored `n` 16-bit masks, then skipped zero-parity contributions inside `stc_extract`. The new `wire_extract` routine:

1. Initializes the same reusable CNG HMAC context and an all-zero `m`-bit syndrome represented by `m` bytes.
2. Traverses precisely the same row blocks and pixel indices.
3. Reads each parity first. If it is zero, it does not hash that column.
4. For parity one, computes the unchanged HMAC input: `STEG-BP/1/column`, its terminating zero byte, the 4-byte big-endian row index and the 8-byte big-endian column index.
5. Applies the existing height mask, forced bits and final-row truncation, then immediately XORs those bits into the syndrome. It never retains a full array of column masks.

Each column hash is independently addressed by row/index. It does **not** consume a sequential random stream, so skipping a column cannot shift subsequent values. The existing stream generation and Fisher-Yates shuffling still consume all their original draws. Bootstrap salt recovery, body recovery, bit order, whitening, ChaCha20-Poly1305 authentication/decryption, framing and bounded decompression are unchanged. This is an exact computation shortcut, not a new steganographic construction or a claim of improved detector resistance. No new CNN experiment is needed to test a receiver-only change that never alters the image.

### Dispatch, memory and remaining work

- A newly built Windows DLL exposes `wire_extract`; Python detects this additional export without changing the existing backend or wire-format version. An older DLL lacking the export, a non-Windows installation, or a disabled fast path uses the original matrix-based extraction. Actual native errors propagate rather than silently falling back.
- **Embedding still needs all columns:** its optimizer must evaluate possible parity changes. The post-serialization extraction self-check explicitly reuses the two cached matrices that embedding just generated, avoiding new HMAC work. Standalone extraction uses the fused path; it neither fills nor automatically consults the column cache. Python callers deliberately repeating the same extraction can opt into the existing cached path with the diagnostic switch below.
- For a pool of `n` pixels with `k` odd values, column hashing falls from `n` HMAC calls to exactly `k`. It is roughly halved only when odd/even pixels are roughly balanced. An all-odd pool saves no hashes; an all-even pool needs none.
- Avoided column-array allocation is exactly `2*n` bytes per pool, or `2*N` bytes across bootstrap and body. At 2,860,800 pixels this is 5,721,600 bytes (about 5.46 MiB). This is an allocation calculation, **not** a measurement of total process memory reduction.
- PNG decoding, all-pixel parity reads, keyed position shuffles, position caches, framing and authentication still run. Complexity remains linear in the pixel count; this does not make extraction proportional only to message length. A smaller `--rate` does not proportionally shrink those image-wide costs.
- The browser receiver's HMAC-state reuse already had an equivalent in this native backend: reusable CNG contexts. The additional improvement here is parity-first hashing plus fused syndrome accumulation, not another cryptographic change.

### Measured native extraction performance

A paired comparison used the immediately preceding native implementation, **not** the much slower original Python hashing backend. There were 36 pairs (72 timed CLI processes): 30 keyed-mode pairs and six public-feature pairs. Three 512-by-512 photographs and one 1920-by-1490 photograph were used, with three repetitions per configuration. Small keyed `HELLO` rows combine all three small photographs (nine pairs); other rows have three pairs. Every output matched the original message byte-for-byte. The photographs had 49.95% to 50.81% odd pixels, so approximately half the column hashes were skipped.

Processes ran sequentially in alternating before/after order, with fresh in-process caches, warm filesystem caches and one untimed warm-up per implementation. These are normal workstation timings, not isolated-machine measurements. No observations were removed. The two timing boundaries are deliberately distinguished:

- **Workflow:** the CLI's normal total timer, including image/key reads, PNG decoding, layout reconstruction, extraction, authentication/decompression, readable logging and message output. It excludes interpreter startup/imports and final JSON-log serialization.
- **Whole CLI:** an external timer covering process startup/imports, that complete workflow, final JSON-log writing and process exit. Both implementations exported the same kinds of logs.

| Input / mode / message | Rate option | Pairs | Median workflow seconds, before → after | Median paired workflow saving | Median whole-CLI seconds, before → after | Median paired whole-CLI saving |
|---|---|---:|---:|---:|---:|---:|
| 512×512 / keyed / `HELLO` | `auto` | 9 | 0.1029 → 0.0889 | 20.62% | 0.8849 → 0.9398 | 0.92% |
| 512×512 / keyed / `HELLO` | `0.05000000` | 9 | 0.0979 → 0.0750 | 25.30% | 0.8275 → 0.8775 | 3.10% |
| 1920×1490 / keyed / `HELLO` | `auto` | 3 | 1.2167 → 0.9619 | 21.84% | 1.9838 → 2.1408 | -4.09% |
| 1920×1490 / keyed / `HELLO` | `0.05000000` | 3 | 1.1060 → 1.1134 | 0.67% | 2.1650 → 2.5644 | 4.17% |
| 512×512 / keyed / 1,024 binary bytes | `auto` | 3 | 0.0917 → 0.0715 | 22.01% | 0.8315 → 0.8542 | 0.59% |
| 512×512 / keyed / 30,000 compressible bytes | `auto` | 3 | 0.1117 → 0.0847 | 30.47% | 0.8522 → 0.9159 | -0.44% |
| 512×512 / public feature / `HELLO` | `auto` | 3 | 0.0922 → 0.0781 | 11.41% | 0.9349 → 0.8215 | 2.81% |
| 1920×1490 / public feature / `HELLO` | `auto` | 3 | 0.9852 → 0.9087 | 17.69% | 1.7542 → 1.8408 | 5.33% |

`auto` chooses `0.00250000` for these `HELLO` cases. It is the sender's choice; each extraction received that case's actual rate. The other auto messages use their own size-fitting rates. Percentages are the medians of **paired** savings, not the percentage difference between independently summarized medians. This can produce a positive paired saving even when the marginal median after-time is higher; the raw ordered pairs remain available for inspection.

Across all 36 pairs, bootstrap-plus-body syndrome recovery was faster in **36/36**, with a **48.45% median paired time saving** (range 15.28% to 71.88%). Whole extraction workflow time improved in 31/36 pairs, with a 21.93% median paired saving. Whole-CLI time improved in only 21/36 pairs, with a **0.76% median paired saving** and a range of -39.66% to +24.82%. Startup and background variability masked much of the saved work. This run therefore supports retaining the faster, lower-allocation extraction kernel, but **does not demonstrate a reliable substantial reduction in end-to-end CLI latency**. In particular, it does not reproduce the browser receiver's overall speedup or prove that large-image CLI execution is consistently faster. These descriptive timings are not confidence intervals or universal speed guarantees.

The full suite passed **175 tests** after this change. Checks include independent matrix/syndrome reconstruction at all supported trellis heights, all-zero/all-one/mixed parities, uneven blocks and truncated rows, short/long HMAC keys, invalid inputs, legacy/disabled-backend fallbacks, native-error propagation, keyed/public round trips, unchanged PNG bytes across primitive backends, authentication failure cases and explicit reuse of embedding's cached matrices. [The saved test report](artifacts/runtime_extract/20260926/tests.xml) is separate from the statistical-resistance experiments; no detector results were changed.

### Build, disable and reproduce

The updated DLL has been rebuilt locally. Other checkouts must rebuild from source; compiled native files are ignored by Git:

```powershell
.\.venv\Scripts\python.exe scripts/build_native.py
.\.venv\Scripts\stegolab.exe extract stego.png --key private.key --rate 0.00250000 --output recovered.bin
```

Use the actual decimal rate reported by embedding. Extraction still cannot infer it or accept `--rate auto`.

To compare against full-column extraction while retaining the other native accelerations:

```powershell
$env:STEGOLAB_NATIVE_EXTRACT = "0"
# Run an extract command with a NEW output filename.
Remove-Item Env:STEGOLAB_NATIVE_EXTRACT
```

Removing that variable restores automatic fast-path selection. `STEGOLAB_NATIVE_PRIMITIVES=0` disables **all** optional native primitives, including this one; it is a different, slower reference configuration.

The pre-change package and DLL are preserved under `artifacts/runtime_extract/20260926/reference`, separately from the older embedding-optimization snapshot. The [benchmark driver](scripts/benchmark_native_extraction.py) compares fresh CLI processes, validates every recovered message byte-for-byte and saves each individual run plus each completed pair. Raw console output, stage timings, source/DLL hashes, input copies and checksums are preserved with the [summary](artifacts/runtime_extract/20260926/comparison/summary.json).

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_native_extraction.py --reference artifacts/runtime_extract/20260926/reference --output artifacts/runtime_extract/repeat
```

The default fixtures are the preserved `artifacts/runtime_exact/20260926/comparison` images and the local `atene_gray.png` photograph. Use `--fixtures` and `--large-cover` to specify their locations. These images, baseline snapshot and output artifacts are local, ignored by Git and must be backed up separately. Research keys and deterministic embedding randomness in this driver are public test data, never production secrets. Use `--resume` with the same output directory to continue; changed source/DLL/input hashes are rejected to avoid silently mixing configurations.

## Common failures and practical limits

| Symptom | What it means |
|---|---|
| `Only single-frame grayscale PNG is supported` | The decoded file is not mode `L`, or has multiple frames. An RGB/RGBA or palette PNG is not supported even if it looks gray. |
| `PNG dimensions exceed limits` | One side or the total pixel count is outside the profile bounds. |
| `Shared key must contain exactly 32 random bytes` | The input is not the expected binary key representation. Correct length alone does not make a predictable key secure. |
| `Payload requires ...; capacity is ...` | The shorter of the original/compressed message exceeds the selected mode's capacity (`B - 66` keyed; `B - 54` no-key). |
| `Insufficient dry pixels` or an unreachable syndrome | Wet constraints and the fixed code prevent embedding on that cover at that rate. Do not interpret nominal byte capacity as guaranteed feasibility. |
| `Native traceback exceeds the resource limit` | The trellis cannot allocate or support the needed traceback. A checkpointed low-memory encoder is not implemented. |
| `No valid authenticated payload` | Extraction could not authenticate the recovered message; wrong key/profile, no message, or damage are possible causes. |
| `No valid plaintext payload` | No-key extraction failed its frame checks; there may be no no-key message, the rate may be wrong, or the image may be damaged. CRC is not tamper protection. |
| `Output already exists; choose a new file` | The CLI refuses to replace any existing output, including an original cover or key. |

Do not share the original cover alongside its stego when relying on an unknown-cover threat model: direct comparison reveals changes. Do not use the public experiment key for actual communication. Preserve the stego pixels exactly during transport, and agree on the rate separately. The tool does not exchange keys, securely erase process memory, preserve arbitrary metadata, or decide whether a real-world cover source is appropriate.

## Where each step lives in the code

| File | Responsibility |
|---|---|
| [cli.py](src/stegolab/cli.py) | Commands, binary file inputs, error reporting, and no-overwrite output handling |
| [system.py](src/stegolab/system.py) | Profile, both frame formats, keyed encryption/no-key CRC, the two embedding stages, PNG self-check, and extraction |
| [primitives.py](src/stegolab/primitives.py) | Byte formats, keyed/public layout roots, HMAC streams, derivation, shuffles, matrix masks, fused-extraction dispatch and bit order |
| [primitives.cpp](src/stegolab/native/primitives.cpp) | Windows CNG batches and parity-first, matrix-free syndrome extraction |
| [costs.py](src/stegolab/costs.py) | Directional residual costs, integer weights, and wet constraints |
| [coding.py](src/stegolab/coding.py) | Validated Python interface to the native trellis |
| [balance.py](src/stegolab/balance.py) | Cover activity groups and the sign-balancing interface |
| [stc.cpp](src/stegolab/native/stc.cpp) | Exact finite-code optimizer, syndrome extraction, and incremental sign balancing |
| [DESIGN_EXTENSION.md](DESIGN_EXTENSION.md) | Focused mathematical specification of the experimental extension |

Correctness tests include tiny trellises checked against exhaustive enumeration, bit/stream compatibility, filter alignment, authenticated round trips, failure handling, unchanged balancing parities and change sets, and an independent recomputation of the balancing objective. They test implementation correctness separately from empirical resistance.

## Reproduce the experiments

The completed measurements and checkpoints already exist locally. The commands below are for intentionally reproducing a research run, not prerequisites for embedding a message. Training commands can replace model artifacts, so preserve the existing `artifacts/` directory or run in a separate project copy if you want to retain the frozen experiment unchanged. Reading this README or using `stegolab embed` does not rerun the benchmark.

```powershell
.\.venv\Scripts\python.exe scripts/fetch_dataset.py
.\.venv\Scripts\python.exe scripts/experiment.py prepare
.\.venv\Scripts\python.exe scripts/experiment.py generate --part development --rate 0.05 --workers 6
.\.venv\Scripts\python.exe scripts/experiment.py evaluate --variant baseline_0p05
.\.venv\Scripts\python.exe scripts/experiment.py evaluate --variant balanced_0p05
.\.venv\Scripts\python.exe scripts/experiment.py evaluate --variant control
```

Use separately generated lower-rate development candidates when needed. The complete decision rules are in `EXPERIMENT_PROTOCOL.md`. Do not choose an encoder by repeatedly inspecting the final test partition.

After selecting a candidate on classical validation, fit its neural detector and check the neural validation gate before scoring any final holdout. The following commands reproduce the recorded candidate; stop before final evaluation if a validation gate fails:

```powershell
.\.venv\Scripts\python.exe scripts/train_deep.py --variant control --epochs 9 --threads 4 --validate-every 3 --save-validation-checkpoints
.\.venv\Scripts\python.exe scripts/train_deep.py --variant balanced_0p05 --epochs 15 --threads 4 --validate-every 3 --init artifacts/deep/control/epoch_006.pt
.\.venv\Scripts\python.exe scripts/experiment.py generate --part test --rate 0.05 --workers 6
.\.venv\Scripts\python.exe scripts/experiment.py evaluate --variant baseline_0p05 --final
.\.venv\Scripts\python.exe scripts/experiment.py evaluate --variant balanced_0p05 --final
.\.venv\Scripts\python.exe scripts/experiment.py evaluate --variant control --final
.\.venv\Scripts\python.exe scripts/train_deep.py --variant balanced_0p05 --final --threads 4
.\.venv\Scripts\python.exe scripts/train_deep.py --variant control --final --threads 4
.\.venv\Scripts\python.exe scripts/compare_same_rate.py
.\.venv\Scripts\python.exe scripts/report_results.py
.\.venv\Scripts\python.exe scripts/record_environment.py
```

Substitute the selected rate and strategy consistently. The public source archive is about 1.7 GB; extracted images and generated experiment artifacts require several additional GB. Dataset files, checkpoints, and generated samples remain under `data/` and `artifacts/` and are excluded from version control.

The recorded candidate was initialized from the control's epoch-6 checkpoint during its nine-epoch schedule. The exact seed checkpoint is preserved as `artifacts/deep/balanced_0p05/control_initialization.pt`, with its hash in `artifacts/selection.json`; use that path to replay from the existing artifacts. The commands above retain epoch 6 when recreating the run from scratch. Training the control for only six epochs is not equivalent because it changes the learning-rate schedule. Do not retrain or overwrite a frozen detector merely to improve a score on the final holdout.

The benchmark counts rejected covers, includes them in the innocent population, and reports both operational and accepted-cover conditional results. Confidence intervals resample image groups with cover/stego labels kept together. A positive control checks detector functionality; it cannot prove sensitivity to all low-rate signals. The compact CPU-trained CNN is not a full SRNet reproduction. Neural training caches development rasters in about 0.8 GiB to avoid repeated small-file reads; pass `--no-cache` on memory-constrained machines. Caching does not change pixels, augmentation, or the data split.

See `RESULTS.md` and the underlying JSON artifacts for completed measurements and remaining limitations. A file's visual appearance or PSNR is never treated as a statistical-security test.
