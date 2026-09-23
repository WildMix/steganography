# Steganography Master Blueprint

## Section 1: Scientific Foundations & Statistical Imperceptibility

### 1.1 Scope, result, and strength of the claims

This document specifies one complete, implementable system for embedding encrypted byte strings in native, losslessly transported, 8-bit grayscale images. Its core is a relative-wavelet distortion model, binary syndrome-trellis coding, randomized unit changes, and a fixed-size authenticated payload. It also explains the alternatives needed to understand that design: spatial and transform embedding, model-based costs, generative models, distribution-preserving sampling, and modern steganalysis.

There is no established universal algorithm that both changes an arbitrary supplied photograph to carry a nonzero payload and guarantees statistical indistinguishability from every possible cover source. Consequently, this blueprint does not assert such a guarantee. Its guarantees are exact payload recovery after successful embedding over a lossless channel, specified distortion optimization, and cryptographic protection under stated assumptions. Its statistical resistance remains a measurable, source-dependent hypothesis.

The proposed composition is an engineering design, not a demonstrated scientific optimum. The treatment covers the principal research directions and their limitations; it does not claim literal completeness over all publications or unpublished attacks. The default operating parameters below are reproducible experimental settings, not experimentally established safe settings. No steganalysis benchmark of this complete composition is claimed here.

Three different claims must remain separate:

| Claim | What would justify it | What this design supplies |
|---|---|---|
| Confidentiality and payload integrity | A secure cryptographic construction and correct implementation | Standard primitives with separated keys and authenticated framing |
| Low statistical detectability against specified detectors | Independent experiments on representative cover sources | A testable embedding design and an evaluation protocol |
| Statistical indistinguishability against every detector | A bound on the full observable distributions | Definitions and conditional theorems; no such bound for this photographic embedding algorithm |

### 1.2 Threat model and notation

Let $C$ be a random cover image, $M$ the secret byte string, $K$ the shared secret, $R$ fresh sender randomness, and $S=E(C,M,K;R)$ the resulting stego image. Let $Z$ denote everything the observer legitimately knows: acquisition pipeline, dimensions, image history, publishing context, codec, user behavior, and previous observations.

The passive observer knows the algorithm and can collect training examples, train new detectors, estimate embedding probabilities, and pool multiple images. The observer does not know $K$, does not have the exact original cover, and cannot alter transport in the correctness claim. An observer possessing the original can ordinarily detect any modification by comparison. Active transformations are considered separately; they can destroy this payload.

Define $P_C=P(C\mid Z)$ and $P_S=P(S\mid Z)$ on the same space. For practical evaluation the space must include observable file structure and delivery context, not only decoded pixels. A decoded-pixel experiment alone cannot certify the whole file or traffic channel.

Probabilities average over explicitly specified cover, message, key, and randomness distributions. Averaging over freshly generated keys for each image does not establish security when one real key is reused. Both experiments are needed.

### 1.3 Statistical security, distinguishing advantage, and relative entropy

For a detector $A$ that outputs 1 for stego, define

$$
\operatorname{Adv}_A=\left|\Pr[A(S)=1]-\Pr[A(C)=1]\right|.
$$

The total variation distance is

$$
\operatorname{TV}(P_C,P_S)=\frac12\sum_x|P_C(x)-P_S(x)|
=\sup_A\operatorname{Adv}_A.
$$

The integral form applies to continuous variables. In this document, statistical $\epsilon$-security means $\operatorname{TV}(P_C,P_S)\leq\epsilon$. Under equal priors, the best possible average classification error is

$$
P_E^*=\frac12\left(1-\operatorname{TV}(P_C,P_S)\right).
$$

Thus $P_E^*=0.5$ means identical distributions, and $P_E^*=0$ means perfect distinguishability. The observed error of a particular detector is an upper bound on the optimal error, not a certificate that no stronger detector exists.

Using natural logarithms, define

$$
D_{\mathrm{KL}}(P_C\parallel P_S)
=\sum_x P_C(x)\ln\frac{P_C(x)}{P_S(x)}.
$$

A relative-entropy requirement $D_{\mathrm{KL}}(P_C\parallel P_S)\leq\delta$ implies

$$
\operatorname{TV}(P_C,P_S)\leq\sqrt{\delta/2},\qquad
P_E^*\geq\frac12\left(1-\sqrt{\delta/2}\right),
$$

with the latter lower bound clipped at zero. For example, $\delta\leq 0.0002$ would imply advantage at most $0.01$ and optimal equal-prior error at least $0.495$. This is a conditional numerical illustration, not an estimate for the proposed encoder.

KL divergence is asymmetric. If one distribution assigns zero probability to an event possible under the other, the relevant direction can be infinite. Neither finite image samples nor a small number of hand-designed statistics establishes a small full-image KL divergence. A learned discriminator, estimated divergence, or good visual quality is not an exact substitute.

Computational security instead restricts $A$ to efficient algorithms and allows a negligible advantage in a security parameter. A short computational secret and a pseudorandom generator do not provide an information-theoretic one-time pad. This distinction matters especially when uniform payloads are used in generative proofs.

### 1.4 Why a universal photograph guarantee is impossible

Consider a cover source supported on exactly one image $c_0$, and suppose the decoder correctly recovers every uniformly distributed $m$-bit payload. For a fixed key, the unchanged image can decode to only one message. Hence

$$
\Pr[S=c_0]\leq 2^{-m},\qquad
\operatorname{TV}(\delta_{c_0},P_S)\geq1-2^{-m}.
$$

The same bound holds after averaging over an independent secret key. The observer simply tests whether the image is $c_0$. This counterexample rules out a universal claim over arbitrary supplied covers and arbitrary cover distributions. Useful guarantees require assumptions about source entropy, observer knowledge, permitted distortion, and the communication channel.

### 1.5 Spatial, DCT, and wavelet artifacts

| Domain or operation | Statistical effect | Design consequence |
|---|---|---|
| Direct LSB replacement | Equalizes adjacent even/odd histogram bins and changes neighborhood parity relationships | Encrypting bits or shuffling locations does not eliminate the effect |
| Randomized $\pm1$ matching | Avoids the particular pair-equalization mechanism but smooths histograms and perturbs residual dependencies | Needs content adaptation and coding; still detectable in principle |
| Quantized JPEG DCT coefficients | Alters magnitude/sign distributions, block-phase statistics, zeros, and dependencies among modes | Work on original quantized coefficients; account for quantization tables and shrinkage |
| Floating-point DWT coefficients | Reconstruction and integer rounding can change many pixels and destroy coefficient decisions | Define quantization and exact inverse behavior before claiming recoverability |
| Integer wavelet coefficients | Integer inversion can be exact, but changes propagate through synthesis filters and may exceed sample bounds | Evaluate the reconstructed pixels and dependencies across subbands |
| Learned latent variables | Can change the joint latent prior, decoder output distribution, and generation fingerprints | Distribution matching and reliable inversion are separate requirements |

For LSB replacement, let $a$ and $b$ be expected counts of values $2j$ and $2j+1$. If a fraction $r$ of samples in this pair is overwritten by fair bits independently of value, then

$$
a'=(1-r/2)a+(r/2)b,\quad
b'=(r/2)a+(1-r/2)b,\quad a'-b'=(1-r)(a-b).
$$

This is the characteristic pair equalization exploited by chi-square-style tests. Adaptive selection changes the simple global formula but does not make parity overwriting harmless.

For symmetric unit changes with a constant probability $p$ of changing an interior-valued sample,

$$
P_S(v)=(1-p)P_C(v)+\frac p2P_C(v-1)+\frac p2P_C(v+1).
$$

Thus the histogram changes by a discrete second derivative. Boundary rules and content-dependent $p$ add further structure. Preserving a first-order histogram alone also leaves higher-order residual co-occurrences, local conditional distributions, and processing-history signatures available to detectors.

A transform does not itself confer secrecy. For a common invertible mapping $T$, full-distribution divergence is unchanged: $D_{\mathrm{KL}}(P\parallel Q)=D_{\mathrm{KL}}(T_\#P\parallel T_\#Q)$. A lossy mapping may decrease distinguishability by data processing, but can also erase the message. Its effects on extraction and on the ordinary cover source must both be evaluated.

### 1.6 Adaptive embedding costs

For sample $i$ and change $d\in\{-1,0,+1\}$, let $\rho_i(d)$ be its modeled impact. Set $\rho_i(0)=0$ and define the additive surrogate

$$
D(C,S)=\sum_i\rho_i(S_i-C_i).
$$

Low costs should identify statistical uncertainty: stochastic texture, unpredictable residuals, or suitable acquisition noise. A strong but clean edge can be predictable along its direction; high gradient magnitude alone is insufficient. Highly regular patterns are also not necessarily good carriers.

An infinite cost means a forbidden change, often called a wet element. Use it for invalid sample values, protected regions, or an explicitly defined smoothness exclusion. In general, smooth areas receive large finite costs; banning every moderately smooth pixel can concentrate changes, reduce coding feasibility, and create selection artifacts. The concrete profile below forbids a narrowly defined class of nearly flat regions and image borders, and uses finite costs elsewhere.

Costs are an encoder model. They are not probabilities of being detected, and reducing them is not a theorem about the true distribution. Additivity neglects interacting changes. For example,

$$
\left|\sum_i A_{pi}\Delta_i\right|
\leq \sum_i|A_{pi}|\,|\Delta_i|
$$

shows why an additive residual cost can upper-bound a relative residual difference yet lose cancellation and dependency information. Optimizing the exact surrogate more aggressively can even make a particular source easier to detect.

### 1.7 Three useful cost-design principles

**Relative directional residuals.** UNIWARD-style methods measure a modification relative to existing high-pass activity. With linear residual operators $A_k$,

$$
R_k=A_kC,\qquad
\rho_i=\sum_k\sum_p\frac{|(A_k)_{pi}|}{\sigma+|R_k(p)|}.
$$

Directional filters penalize a region predictable in any direction. S-UNIWARD applies this idea to spatial sample changes; JPEG variants evaluate the pixel-domain effect of a coefficient change through the same residual model. The filter support, boundary extension, and stabilizer are substantive parameters.

**Smoothed inverse activity.** A HILL-style cost can be written as

$$
\rho^{H}=L_{15}*\left(\frac{1}{L_3*|C*H_0|+\eta}\right),\qquad
H_0=\begin{bmatrix}-1&2&-1\\2&-4&2\\-1&2&-1\end{bmatrix},
$$

where $L_s$ is a normalized $s\times s$ averaging filter. High-pass activity identifies uncertainty; the averaging operations distribute low costs over textured neighborhoods. Very small $\eta$ needs careful numerical handling. This is an alternative cost model, not a mandatory multiplicative factor in the selected encoder.

**Local statistical detectability.** MiPOD-style reasoning estimates residual variance and minimizes an approximation to detector power. To illustrate the principle independently, approximate one cover residual by $N(0,v_i)$ and a changed residual by $N(0,v_i+p_i)$, where $p_i$ is the probability of a symmetric unit change. Then

$$
D_{\mathrm{KL}}\big(N(0,v_i)\parallel N(0,v_i+p_i)\big)
=\frac12\left[\ln(1+p_i/v_i)+\frac{v_i}{v_i+p_i}-1\right]
\approx\frac{p_i^2}{4v_i^2}.
$$

This explains why an uncertain residual can tolerate more changes. The approximation is not exact for a quantized mixture or correlated photographic pixels. With per-direction probability $\beta_i$, $p_i=2\beta_i$; a common local detectability objective is proportional to $\sum_i\beta_i^2/v_i^2$. Costs derived from such probabilities depend on payload and on the variance estimator.

The selected design uses the first family. The other two are experimental baselines. An arbitrary combination of all three has no established dominance and is not silently presented as a consensus optimum.

### 1.8 Payload-distortion bounds and the role of coding

For independent binary change decisions with positive cost $r_i$, entropy-constrained distortion minimization yields

$$
p_i(\lambda)=\frac{1}{1+\exp(\lambda r_i)},\quad
\sum_i h_2(p_i)=m,\quad
D_{\mathrm{bin}}^*(m)=\sum_i r_ip_i,
$$

where $h_2(p)=-p\log_2p-(1-p)\log_2(1-p)$ and wet elements have $p_i=0$. This is the independent-symbol entropy relaxation for carrying $m$ uniform bits, not a complete finite-length steganographic security bound.

For a genuinely ternary encoder,

$$
\pi_i(d)=\frac{\exp[-\lambda\rho_i(d)]}{\sum_{a\in\{-1,0,+1\}}\exp[-\lambda\rho_i(a)]},\qquad
\sum_i H(\pi_i)=m.
$$

A multilayer construction can exploit the larger alphabet. A binary parity encoder followed by a random choice of modification sign does not encode additional information in that sign. Its appropriate efficiency comparison is the binary bound. This blueprint deliberately specifies that simpler, auditable binary construction and does not claim ternary-optimal capacity.

A modification simulator that samples $\pi_i$ is useful for research but is not a message encoder. Actual coding must constrain the output to the syndrome representing the requested bits. STC minimizes cost within such a constraint and extracts by parity checks; it is not an error-correcting channel code.

### 1.9 Generative alternatives and their precise limitations

**GANs.** A generator, message decoder, and discriminator can be trained jointly with image fidelity, extraction, and adversarial losses. Some architectures modify an existing cover; others generate a carrier. Fooling a finite discriminator family does not establish distribution equality. A high-capacity encoder can create weak but systematic artifacts missed during training and learned by an independent steganalyzer.

**VAEs.** A decoder maps a latent prior into an image distribution; an encoder estimates a posterior. The aggregate latent distribution of real images generally differs from the chosen prior, and the encoder is not normally an exact inverse. Quantization, reconstruction error, and correlated latent coordinates matter. Using a VAE to compress a secret image is different from preserving the distribution of the carrier.

**Invertible flows.** A bijection offers exact mathematical inversion before finite-precision storage. The learned image distribution can still differ from the real cover source. Quantizing a generated image may invalidate exact inversion. An optimization step applied to a latent vector changes its distribution unless a separate invariance argument applies.

**Diffusion.** Secret symbols can select conditional Gaussian regions of initial or intermediate randomness. Distribution-preserving sampling can protect the generator output distribution under specified assumptions. Numerical inversion, image quantization, and VAE decoding can nevertheless cause bit errors. Improvements made only at the receiver do not change the transmitted distribution, but they do not prove perfect recovery either. Robustness, exact recovery, and distribution preservation require separate evidence.

Here is the elementary distribution-preserving construction. For $b$ independent uniform bits interpreted as an integer $J\in\{0,\ldots,2^b-1\}$ and independent $U\sim\mathrm{Uniform}(0,1)$,

$$
V=\frac{J+U}{2^b},\qquad Z=\Phi^{-1}(V).
$$

Then $V$ is uniform and $Z$ is standard normal. A decoder with exact $Z$ obtains $J=\lfloor2^b\Phi(Z)\rfloor$. The full vector has the desired joint prior only when all relevant variables have the required joint independence. Repeating bits, adding publicly structured redundancy, truncating tails, or fixing quantiles can violate that property despite correct marginal histograms. Computational whitening gives a computational claim, not literal information-theoretic equality.

Let $G$ include all generation steps, conditioning, randomness, quantization, and serialization. If $Z_s$ has exactly the ordinary latent law and all other inputs have exactly their ordinary joint law, then

$$
G_\#P_{Z_s}=G_\#P_Z=P_G.
$$

This proves equality to ordinary output of that generator. It does not prove equality to a photographic source $P_C$. In particular,

$$
\operatorname{TV}(P_S,P_C)
\leq\operatorname{TV}(P_S,P_G)+\operatorname{TV}(P_G,P_C).
$$

Prompt selection, sampler settings, generation software, and export behavior are part of the generator source. A detector trained on photographs versus generated stego images confounds generation with embedding; a detector trained only on photographs may also miss latent-specific artifacts. Appropriate tests include ordinary generations with matched settings and detectors operating on estimated diffusion noise.

The same principle generalizes to a joint coupling $\gamma(m,x)$ with the required message and cover marginals. The output marginal is exactly the target cover distribution. Minimizing joint entropy can maximize mutual information for fixed marginals, but extracting a complete message from one output requires additional decodability conditions. Sampling the true conditional image source efficiently and recovering the message from a quantized file are central obstacles.

Distribution-preserving generative communication is therefore attractive when ordinary traffic already comes from a specific generator. It is not selected for an API whose first input is a particular existing cover photograph and whose receiver must recover exact bytes without model inversion.

## Section 2: Complete System Architecture

### 2.1 Selected profile and channel contract

The single normative profile is `STEG-BP/1`:

| Parameter | Exact setting |
|---|---|
| Input and output | Single-frame PNG; unsigned 8-bit grayscale; no alpha or palette |
| Sample interpretation | Decode stored samples directly; no gamma correction, resizing, or color conversion |
| Dimensions | Each side from 256 to 8192; $262144\leq N=WH\leq16777216$ |
| Candidate gross payload | $B=\lfloor N/160\rfloor$ bytes, including the bootstrap salt and authentication tag |
| Bootstrap allocation | $n_H=\lfloor N/8\rfloor$ keyed, dispersed pixel positions |
| Bootstrap payload | Fresh 32-byte salt; 256 syndrome bits |
| Body allocation | The other $n_B=N-n_H$ positions, permuted again using the salt |
| Body payload | $B-32$ bytes; $m_B=8(B-32)$ syndrome bits |
| STC state height | $h=10$, hence at most 1024 states |
| Changes | At most one $+1$ or $-1$ change to each selected sample |
| Cost model | Relative directional residual costs defined below |
| Forbidden regions | A 16-pixel border and nearly flat $5\times5$ neighborhoods defined below |
| Shared secret | Exactly 32 uniformly random bytes |
| AEAD | ChaCha20-Poly1305; complete 16-byte tag |
| Key derivation | HKDF with HMAC-SHA-256 |
| Compression | Raw DEFLATE if it shortens the payload; otherwise raw bytes |
| Maximum decoded message | 16 MiB, enforced before decompression |
| Error handling | Local embedding failure or one generic extraction failure; never unauthenticated plaintext |

The gross rate approaches 0.05 bits per pixel. This numerical setting is a test profile, not a safe-capacity assertion. Changing the rate, dimensions policy, matrix construction, domain, or wet mask creates a different profile that both endpoints must agree on and that must be evaluated separately.

The input must belong to a source that normally publishes such grayscale PNGs. Converting an arbitrary JPEG or color image solely to make it fit this profile can create a strong source mismatch. The protocol does not perform that conversion.

The serializer must follow the ordinary source's PNG behavior: ancillary chunks, chunk ordering, compression policy, and software markers must not introduce an embedding-specific fingerprint. Innocent control images must pass through the same ordinary serializer. The protocol inserts no secret-bearing metadata or plaintext magic marker. Pixel correctness does not require byte-for-byte preservation of the compressed PNG stream.

### 2.2 End-to-end flow

```text
Sender:
native grayscale cover ──► strict decode ──► residual costs + wet mask
                                               │
secret bytes ──► optional compression ──► fixed padded frame
                                               │
fresh salt + shared key ──► independent keys ──► AEAD + whitening
          │                                    │
          └──► bootstrap syndrome               └──► body syndrome
                         │                             │
                         └─────► two disjoint STCs ◄────┘
                                        │
                               signed unit changes
                                        │
                               lossless encode + verify

Receiver:
stego PNG ──► strict decode ──► bootstrap parity checks ──► salt
                                                               │
shared key + salt ──► body permutation + matrix + cryptographic keys
                                        │
                              body parity checks
                                        │
                       unwhiten ──► verify AEAD ──► parse
                                        │
                              bounded decompression
                                        │
                                  exact secret bytes
```

Costs and wet masks are sender-only information. The decoder never recomputes texture rankings or tries to infer which pixels changed. Both stages retain all allocated positions in their matrices, including wet positions. This prevents a common synchronization failure caused by deleting content-dependent positions from the decoder's coordinate system.

### 2.3 Payload layout and fixed capacity

Let $Q=B-32$ be the length of the whitened encrypted body, and $L=Q-16=B-48$ the plaintext-frame length. The plaintext frame is:

| Offset | Length | Meaning |
|---|---:|---|
| 0 | 1 byte | Internal format version: `0x01` |
| 1 | 1 byte | Compression flag: `0x00` raw, `0x01` raw DEFLATE |
| 2 | 8 bytes | Original message length, unsigned big-endian |
| 10 | 8 bytes | Stored data length, unsigned big-endian |
| 18 | Stored length | Raw or compressed message bytes |
| Remaining | $L-18-\text{stored length}$ | Independent random padding |

The maximum stored payload is $B-66$ bytes. Compression can increase the recoverable original size, but never changes the fixed embedded length. Empty payloads are valid. Text, if desired, is encoded to bytes by the caller with an agreed encoding; the core protocol handles arbitrary bytes.

For a $512\times512$ image, $B=1638$, $Q=1606$, $L=1590$, and at most 1572 stored message bytes fit. There are 13104 total embedded syndrome bits. For a $1024\times1024$ image, at most 6487 stored bytes fit. These are framing capacities; wet constraints can still make embedding fail.

Fixed padding conceals the actual message length within a dimension-dependent capacity class. It also consumes the full class for short messages. Do not claim that compressing a short message reduces distortion in this fixed-rate profile; compression only helps it fit. An alternate lower-rate profile could reduce distortion, but is not negotiated through this payload.

### 2.4 Keys, randomness, and domain separation

All strings below are ASCII; `||` denotes byte concatenation. `U8`, `U32`, and `U64` encode unsigned integers in big-endian order. Define

```text
CTX = ASCII("STEG-BP/1") || U32(W) || U32(H) || U64(B) || U8(10)
ROOT = HKDF-Extract(
    salt = SHA256(ASCII("STEG-BP/1/root")),
    IKM  = SharedKey)

Derive(PRK, label) = HKDF-Expand(
    PRK, ASCII(label) || 0x00 || CTX, 32)

K_split = Derive(ROOT, "split")
K_head  = Derive(ROOT, "head-code")

salt = CSPRNG(32)
MSG = HKDF-Extract(salt = salt, IKM = ROOT)
K_enc   = Derive(MSG, "aead")
K_white = Derive(MSG, "whiten")
K_perm  = Derive(MSG, "body-perm")
K_code  = Derive(MSG, "body-code")
K_sign  = Derive(MSG, "sign")

AAD   = ASCII("STEG-BP/1/aad") || 0x00 || CTX || salt
nonce = 12 zero bytes
```

HKDF-Extract is HMAC with `salt` as key and `IKM` as input. For the requested 32-byte expansion, HKDF-Expand is one HMAC block over `info || 0x01`. Use vetted cryptographic implementations. `CSPRNG` must be backed by the operating system; timestamps and ordinary simulation PRNGs are unsuitable.

The AEAD nonce is constant only because each fresh salt derives a fresh message encryption key. Never encrypt two frames under the same derived key. For $q$ independent salts, the salt collision probability is at most $q(q-1)/2^{257}$; cryptographic reduction terms and derived-key collisions also belong in a full security bound. Retain a local salt-usage record when practical, and fail on a known repeat. Retries must use a new salt and must never publish multiple variants of the same cover.

AES-256-GCM could occupy the same architectural role with its own profile and nonce discipline; it is not an additional cipher layer. Passwords are outside this 32-byte random-key interface. A password extension needs a memory-hard derivation policy and independently specified parameters; hashing a password once is not an acceptable substitute.

### 2.5 Whitening and deterministic pseudorandom streams

Authenticated encryption protects secrecy and authenticity, but its generic definition does not guarantee that every serialized tag is indistinguishable from fair bits. To make the payload-randomization assumption explicit, independently whiten the entire AEAD ciphertext and tag:

$$
T=\operatorname{AEAD.Encrypt}(K_{enc},0^{96},F,AAD),\qquad
W=T\oplus\operatorname{Stream}(K_{white},|T|).
$$

For any stream key $k$, define the byte stream as the concatenation, starting with counter zero, of

$$
\operatorname{HMAC\!\!\!-SHA256}\left(k,\operatorname{ASCII}(\texttt{"STEG-BP/1/stream"})\parallel\texttt{00}\parallel U64(j)\right).
$$

Take a prefix of the desired length and reject counter overflow. Each purpose has its own derived key and its own stream cursor. The sign stream uses `K_sign`; the two permutation streams use `K_split` and `K_perm`. A permutation key may reproduce its same stream to regenerate a mapping. A whitening key must not encrypt multiple bodies.

Whitening is reversible preprocessing, not a substitute for AEAD. It makes the body computationally pseudorandom under the key-derivation and PRF assumptions. Pseudorandom syndrome bits do not imply natural-looking image noise.

### 2.6 Keyed permutations and the bootstrap problem

Generate an unbiased permutation of the row-major index list $[0,\ldots,N-1]$ using `K_split`. Its first $n_H$ entries form the ordered header list $I_H$; its remaining entries form a base body list. Apply a second permutation to that base list with `K_perm`, producing $I_B$.

The header therefore has positions and a matrix derivable before its salt is known. After extracting the salt, the receiver can derive the body's fresh permutation, matrix, and cryptographic keys. There is no circular dependency on an encrypted length or hidden nonce. The two pixel lists are disjoint.

Generate each bounded random integer by rejection sampling on 64-bit unsigned values. For a bound $a$, let $T=2^{64}-(2^{64}\bmod a)$; discard values $u\geq T$ and return $u\bmod a$. Using `% a` without rejection creates a bias. The shuffle and stream byte order are specified in Section 3.

Header position patterns repeat for a reused key and matching dimensions. This is a limitation, not a security feature. The salt refreshes only the body's mapping. Evaluation must include many images under a fixed key and bootstrap-only detectors. Rotation policies must not be mistaken for a proof of resistance to pooled analysis.

### 2.7 Exact residual operator and cost map

Use the following 16-tap low-pass sequence, with its order exactly as written:

```text
l = [
 -0.00011747678412476953,  0.0006754494064505693,
 -0.00039174037337694705, -0.004870352993451574,
  0.008746094047405777,    0.013981027917398282,
 -0.044088253930794755,   -0.017369301001807547,
  0.12874742662047847,     0.0004724845739132828,
 -0.2840155429615824,     -0.015829105256349306,
  0.5853546836542067,      0.6756307362972898,
  0.3128715909144659,      0.05441584224310401
]
g[j] = (-1)^(j+1) * l[15-j],  for j = 0,...,15
F1 = outer(l, g)
F2 = outer(g, l)
F3 = outer(g, g)
```

For dimension length $d$, symmetric extension repeats the edge sample. Compute $t=a\bmod 2d$ in $[0,2d)$, then

$$
\operatorname{reflect}(a,d)=\begin{cases}t&t<d\\2d-1-t&t\geq d.\end{cases}
$$

The residuals are correlations with anchor 7, not an unspecified library convolution:

$$
R_k(r,c)=\sum_{u=0}^{15}\sum_{v=0}^{15}F_k(u,v)
C\big(\operatorname{reflect}(r+u-7,H),\operatorname{reflect}(c+v-7,W)\big).
$$

For each eligible interior pixel $(a,b)$, calculate

$$
\rho_{a,b}=\sum_{k=1}^{3}\sum_{u=0}^{15}\sum_{v=0}^{15}
\frac{|F_k(u,v)|}{1+|R_k(a-u+7,b-v+7)|}.
$$

The 16-pixel wet border ensures that every residual index in this formula is inside the image and that no mirrored copy of the changed sample contributes at a boundary. This is an explicit specialization of the operator-column cost in Section 1.7. It can be evaluated efficiently with separable filtering and correctly reversed kernels; a library's default even-filter alignment must not be assumed correct.

For smoothness, use the original image's $5\times5$ neighborhood and integer sums:

$$
V_{a,b}=25\sum_{j\in\mathcal N_{a,b}}C_j^2-
\left(\sum_{j\in\mathcal N_{a,b}}C_j\right)^2.
$$

The population variance is $V_{a,b}/625$. If $V_{a,b}\leq625$, both modifications are forbidden. This is a chosen policy threshold of one squared gray level, not a universal boundary between secure and insecure locations.

Quantize each finite residual cost before coding:

$$
r_i=\max\left(1,\left\lfloor10^6\rho_i+\tfrac12\right\rfloor\right).
$$

For other pixels set the actual directional coding costs $\rho_i(+1)=\rho_i(-1)=r_i$. Set $\rho_i(-1)=+\infty$ when $C_i=0$ and $\rho_i(+1)=+\infty$ when $C_i=255$. Here the raw residual scalar $\rho_i$ and the directional cost function $\rho_i(d)$ have distinct roles. Never clip, wrap, or modify a wet pixel. There is always zero cost for keeping the original value.

The raw cost is at most $3(\sum_j|l_j|)^2<13.837$. Thus every finite integer cost is below 13837000 and every accumulated score is below $2.322\times10^{14}$ at the largest admitted image size. These integer sums are exactly representable in binary64, whose integer precision extends to $2^{53}$. Use positive infinity only as an unreachable-state sentinel. The dynamic program is exactly optimal for these quantized costs; it need not choose the exact same minimizer as an unquantized real-valued objective.

Compute all costs once from the original cover, before either embedding stage. Use binary64 arithmetic for the cost model and integer arithmetic for smoothness. If required arithmetic yields a nonfinite value unexpectedly, reject the cover. Sender arithmetic affects which solution is chosen, but decoder interoperability does not depend on reproducing the costs.

### 2.8 Binary syndrome coding and directional changes

For an ordered list of $n$ pixels, define cover parity $x_i=C_{I_i}\bmod2$. Let $H\in\mathbb F_2^{m\times n}$ be the shared banded parity-check matrix and $b\in\mathbb F_2^m$ the target bits. Solve

$$
y^*=\arg\min_{y\in\{0,1\}^n:Hy=b}\sum_i c_i(y_i),
\qquad
c_i(z)=\begin{cases}0&z=x_i\\r_i&z\ne x_i,\end{cases}
$$

where $r_i=\min(\rho_i(-1),\rho_i(+1))$. When $r_i=+\infty$, the parity cannot change. An equivalent change-vector formulation is $He=b\oplus Hx$, $y=x\oplus e$.

For $y_i=x_i$, keep the sample. Otherwise choose an allowed sign of minimum cost; choose between equal-cost signs with an independent pseudorandom sign bit. Interior changes are therefore not directed by the sample's parity. The receiver needs only $y$ and $H$, and computes $b=Hy$.

The banded matrix and exact dynamic program are fully defined next. They minimize the specified additive objective for that matrix; finite height and matrix quality determine coding loss. Near-bound performance must be measured. The mere choice `h=10` does not prove a particular efficiency gap.

### 2.9 Feasibility, admission, and operational boundaries

For each stage, the number of dry positions must at least equal its number of message bits. This count is necessary for general full-rate syndrome reachability but not sufficient. The dry-column submatrix must have adequate rank, and a particular syndrome must be reachable. The trellis's finite final path is the definitive check used by this encoder.

Do not silently relax wet constraints, shorten the authenticated tag, raise the rate, change codecs, or use direct LSB replacement after a failure. Return a local embedding failure. Do not repeatedly search salts or covers against a particular detector and report the resulting conditional population as if it were the original source.

Cover rejection is itself a selection process. The distribution of successfully transmitted covers can differ from ordinary traffic. Track failure rates and train detectors against the final accepted population. A deployed source and rate need empirical validation before any claim of low detectability.

The lossless contract excludes resizing, lossy recompression, cropping, denoising, rotation, color conversion, and altered sample depth. STC does not repair such damage. A separate channel code would increase embedded length and require a new profile and fresh statistical evaluation. Robust watermarking and statistically covert communication have different objectives.

## Section 3: The Complete Algorithm Specification

### 3.1 Conventions and primitive interfaces

All pixel, vector, and byte indices start at zero. A pixel index $i$ means row $\lfloor i/W\rfloor$, column $i\bmod W$. Array slices exclude their upper endpoint. Matrix arithmetic is over $\mathbb F_2$; real-valued costs use ordinary addition and comparison. `XOR`, `AND`, `OR`, `<<`, and `>>` are bitwise operations on nonnegative integers. In pseudocode, `^` in mathematical expressions denotes exponentiation, not a language-dependent XOR.

`Bits(bytes)` emits each byte's most significant bit first. `Bytes(bits)` reverses that mapping and requires a multiple of eight bits. For a trellis column mask, bit zero instead means the current syndrome row; this intentional distinction is explicit in matrix construction.

`StrictDecodePNG` validates the PNG structure and dimensions before allocating its full raster, rejects unsupported modes, bounds decompression, and returns the exact stored 8-bit samples. `EncodeLikeOrdinarySource` is the channel's ordinary lossless serializer, without an embedding-specific marker. Cryptographic calls use a maintained implementation of the named primitives; this document specifies their inputs and serialization rather than substituting new cryptographic primitives.

`FAIL` means a local failure result. The caller must not expose detailed parsing, authentication, or decompression failures to a remote adversary. The API returns either a complete result or failure; it never returns partial plaintext.

### 3.2 Permutation and stream pseudocode

```text
NewStream(key):
    return a cursor over successive blocks
        HMAC_SHA256(key, ASCII("STEG-BP/1/stream") || 0x00 || U64(j))
    for j = 0, 1, 2, ...
    consume bytes in digest order; reject counter overflow

UniformBelow(stream, a):
    require 1 <= a <= 2^64
    threshold = 2^64 - (2^64 mod a)       # use a wider integer if needed
    repeat:
        u = unsigned_big_endian(stream.take(8))
    until u < threshold
    return u mod a

Permute(input_list, key):
    result = copy(input_list)
    stream = NewStream(key)
    for i from len(result)-1 down to 1:
        j = UniformBelow(stream, i+1)
        swap(result[i], result[j])
    return result

SplitPositions(N, K_split):
    order = Permute([0, 1, ..., N-1], K_split)
    n_H = floor(N/8)
    return order[0:n_H], order[n_H:N]
```

The body applies `Permute` to the returned base list itself. Do not accidentally interpret that operation as permuting the header, sorting the body list, or shuffling the whole image a second time.

### 3.3 Complete parity-check matrix construction

The construction below is a fully specified banded syndrome code. It uses keyed column diversity instead of an unspecified external matrix table. Its distortion performance is not assumed to equal that of every tuned STC implementation.

For $m$ syndrome bits and $n\geq m$ carrier positions, define group boundaries

$$
t_j=\left\lfloor\frac{jn}{m}\right\rfloor,\quad j=0,\ldots,m.
$$

Group $j$ contains columns $i=t_j,\ldots,t_{j+1}-1$. Generate its column mask as follows:

```text
ColumnMask(code_key, j, i, m, h):
    digest = HMAC_SHA256(
        code_key,
        ASCII("STEG-BP/1/column") || 0x00 || U32(j) || U64(i))
    v = unsigned_big_endian(digest[0:2]) AND ((1 << h) - 1)
    v = v OR 1 OR (1 << (h-1))
    active = min(h, m-j)
    return v AND ((1 << active) - 1)
```

For $0\leq k<\min(h,m-j)$, set

$$
H_{j+k,i}=(v_i\mathbin{\gg}k)\mathbin{\&}1,
$$

with every other entry zero. Do not wrap rows at the bottom or append additional message bits. Truncating masks at $m$ is the termination convention.

Every group is nonempty and every column includes its current row. Choosing one column from each group gives a lower triangular $m\times m$ submatrix with diagonal ones. Thus the unrestricted matrix has full row rank. Removing wet columns can destroy that property. The encoder keeps wet columns in place and forbids their changes.

No dense $m\times n$ matrix needs to be allocated. Store or regenerate the $h$-bit masks and group boundaries. The key is part of the protocol, but matrix secrecy is not assumed to provide encryption or statistical security.

### 3.4 Exact STC dynamic program

The state is an $h$-bit mask containing accumulated contributions to the current and next $h-1$ syndrome rows. Before the first column, only state zero is reachable. At the end of group $j$, the current row is complete: keep states whose low bit equals $b_j$, then shift right by one.

For column $i$ with mask $v_i$, the update for destination state $s$ is

$$
V_{new}(s)=\min\left\{V(s)+c_i(0),\;V(s\oplus v_i)+c_i(1)\right\}.
$$

Store which output parity achieved the minimum. Break a finite tie by choosing parity zero. If both candidates are infinite, the state remains unreachable. Avoid the undefined numerical operation $0\times\infty$: calculate `c_i(z)` using a branch.

```text
STCEmbed(x, change_cost, b, code_key, h):
    n = len(x); m = len(b)
    require 1 <= m <= n and h == 10
    V = array(2^h, +infinity)
    V[0] = 0
    trace = storage for one chosen parity per column and destination state

    for j = 0,...,m-1:
        begin = floor(j*n/m)
        end   = floor((j+1)*n/m)
        for i = begin,...,end-1:
            v = ColumnMask(code_key, j, i, m, h)
            c0 = 0 if x[i] == 0 else change_cost[i]
            c1 = 0 if x[i] == 1 else change_cost[i]
            for s = 0,...,2^h-1:
                a = V[s]       + c0
                d = V[s XOR v] + c1
                if a <= d:
                    Vnew[s] = a; trace[i,s] = 0
                else:
                    Vnew[s] = d; trace[i,s] = 1
            V = Vnew

        Vnext = array(2^h, +infinity)
        for s = 0,...,2^h-1:
            if (s AND 1) == b[j]:
                Vnext[s >> 1] = V[s]
        V = Vnext

    if V[0] is not finite: FAIL
    optimum = V[0]
    y = array(n)
    s = 0
    for j from m-1 down to 0:
        s = (s << 1) OR b[j]      # reverse the completed-row shift
        begin = floor(j*n/m)
        end   = floor((j+1)*n/m)
        for i from end-1 down to begin:
            v = ColumnMask(code_key, j, i, m, h)
            y[i] = trace[i,s]
            if y[i] == 1: s = s XOR v
    assert s == 0
    assert STCExtract(y, m, code_key, h) == b
    return y, optimum

STCExtract(y, m, code_key, h):
    n = len(y)
    require 1 <= m <= n and h == 10
    b = zeros(m)
    for j = 0,...,m-1:
        for i = floor(j*n/m),...,floor((j+1)*n/m)-1:
            if y[i] == 1:
                v = ColumnMask(code_key, j, i, m, h)
                for k = 0,...,min(h,m-j)-1:
                    b[j+k] = b[j+k] XOR ((v >> k) AND 1)
    return b
```

The score recursion is $O(n2^h)$, extraction is $O(nh)$ or better with bit-packed row operations, and full traceback needs $n2^h$ bits if packed. Score storage needs $O(2^h)$ floating-point values. At the maximum permitted dimensions, full traceback is large; use checkpointing rather than an object per state or path.

For exact low-memory traceback, save score arrays at selected group boundaries roughly every 4096 columns. During backward reconstruction, replay each checkpoint interval from its saved score array, retain only that interval's parity decisions, trace it backward, and continue with the resulting boundary state. This changes memory and runtime, not the optimum. Budget resources explicitly; a valid dimension bound is not a runtime guarantee.

### 3.5 Cost computation and conversion to sample changes

```text
ComputeCosts(C):
    R[1], R[2], R[3] = the correlations defined in Section 2.7
    minus = array(N, +infinity)
    plus  = array(N, +infinity)
    for each pixel i with coordinates (a,b):
        if a < 16 or a >= H-16 or b < 16 or b >= W-16:
            continue
        s1 = sum of the 25 original samples in its 5x5 neighborhood
        s2 = sum of their squares, using a sufficiently wide integer
        if 25*s2 - s1*s1 <= 625:
            continue
        rho = 0
        for k in 1,2,3:
            for u,v in 0,...,15:
                rho += abs(F[k][u,v]) / (1 + abs(R[k][a-u+7,b-v+7]))
        require rho > 0 and finite(rho)
        integer_cost = max(1, floor(1000000*rho + 0.5))
        if C[i] > 0:   minus[i] = integer_cost
        if C[i] < 255: plus[i]  = integer_cost
    return minus, plus

EmbedStage(C, S, positions, bits, code_key, minus, plus, sign_stream):
    x = [C[i] AND 1 for i in positions]
    costs = [min(minus[i], plus[i]) for i in positions]
    if number_of_finite(costs) < len(bits): FAIL
    y, distortion = STCEmbed(x, costs, bits, code_key, 10)

    for k = 0,...,len(positions)-1:
        i = positions[k]
        if y[k] == x[k]: continue
        if minus[i] < plus[i]: d = -1
        else if plus[i] < minus[i]: d = +1
        else:
            require finite(minus[i])
            # Consume one whole stream byte per tie; use its low bit.
            d = +1 if (sign_stream.take(1)[0] AND 1) == 1 else -1
        require 0 <= C[i]+d <= 255
        S[i] = C[i]+d

    assert [S[i] AND 1 for i in positions] == y
    return distortion
```

The input `C` remains immutable; `S` is a separate copy shared by the two disjoint stages. Use the same `sign_stream` cursor across header then body. Both sign directions of every nonboundary dry pixel have equal costs in this profile. Boundary samples have only their legal direction available.

### 3.6 Complete sender pseudocode

```text
EncryptAndEmbed(CoverImage, SecretMessage, SharedKey) -> StegoImage:
    require SharedKey is exactly 32 random-key bytes
    require SecretMessage is a byte string of length <= 16*1024*1024
    C, source_container = StrictDecodePNG(CoverImage)
    W, H = dimensions(C)
    require 256 <= W,H <= 8192
    N = W*H
    require 262144 <= N <= 16777216

    B = floor(N/160)
    Q = B-32
    L = Q-16
    require L >= 18
    CTX, ROOT, K_split, K_head = derive as in Section 2.4
    I_H, I_base = SplitPositions(N, K_split)
    minus, plus = ComputeCosts(C)

    compressed = RawDEFLATE(SecretMessage)
    if len(compressed) < len(SecretMessage):
        flag = 1; data = compressed
    else:
        flag = 0; data = SecretMessage
    if len(data) > L-18: FAIL

    salt = CSPRNG(32)
    reserve this salt against known reuse before encryption
    MSG, K_enc, K_white, K_perm, K_code, K_sign, AAD = derive as specified
    F = 0x01 || U8(flag) || U64(len(SecretMessage)) || U64(len(data))
        || data || CSPRNG(L-18-len(data))
    assert len(F) == L
    T = ChaCha20Poly1305.Encrypt(K_enc, 12 zero bytes, F, AAD)
    # Library result must serialize ciphertext first, then the full tag.
    assert len(T) == Q
    white_stream = NewStream(K_white)
    payload = T XOR white_stream.take(Q)

    I_B = Permute(I_base, K_perm)
    S = copy(C)
    signs = NewStream(K_sign)
    D_H = EmbedStage(C, S, I_H, Bits(salt), K_head, minus, plus, signs)
    D_B = EmbedStage(C, S, I_B, Bits(payload), K_code, minus, plus, signs)
    # Either failure aborts the operation; never publish a partial S.

    assert all(abs(S[i]-C[i]) <= 1 for i = 0,...,N-1)
    assert all(S[i] == C[i] for every fully wet i)
    assert STCExtract([S[i] AND 1 for i in I_H], 256, K_head, 10)
           == Bits(salt)
    assert STCExtract([S[i] AND 1 for i in I_B], 8*Q, K_code, 10)
           == Bits(payload)

    output = EncodeLikeOrdinarySource(S, source_container)
    decoded_output, _ = StrictDecodePNG(output)
    assert decoded_output == S
    assert ExtractAndDecrypt(output, SharedKey) == SecretMessage
    return output
```

Raw DEFLATE has no zlib wrapper, gzip header, dictionary, or concatenated members. A sender may use any valid compressor producing that stream format; bit-for-bit compressor output is not needed for decoder interoperability. Compare actual byte lengths before choosing it. Compression must not combine attacker-controlled data with a separate hidden secret through an observable adaptive length oracle.

The final self-check is part of correctness verification and does not estimate detectability. For exact sender-output reproducibility, supply fixed randomness only in a test harness. Production uses fresh operating-system randomness.

### 3.7 Complete receiver pseudocode

```text
ExtractAndDecrypt(StegoImage, SharedKey) -> SecretMessage:
    require SharedKey is exactly 32 bytes
    S, _ = StrictDecodePNG(StegoImage)
    W, H = dimensions(S)
    require 256 <= W,H <= 8192
    N = W*H
    require 262144 <= N <= 16777216

    B = floor(N/160)
    Q = B-32
    L = Q-16
    require L >= 18
    CTX, ROOT, K_split, K_head = derive as in Section 2.4
    I_H, I_base = SplitPositions(N, K_split)

    header_bits = STCExtract([S[i] AND 1 for i in I_H], 256, K_head, 10)
    salt = Bytes(header_bits)
    MSG, K_enc, K_white, K_perm, K_code, K_sign, AAD = derive as specified
    I_B = Permute(I_base, K_perm)
    body_bits = STCExtract([S[i] AND 1 for i in I_B], 8*Q, K_code, 10)
    payload = Bytes(body_bits)
    white_stream = NewStream(K_white)
    T = payload XOR white_stream.take(Q)

    F = ChaCha20Poly1305.Decrypt(K_enc, 12 zero bytes, T, AAD)
    # Authentication must complete before any frame parsing/decompression.
    if authentication fails: FAIL
    require len(F) == L
    require F[0] == 0x01 and F[1] in {0x00,0x01}
    flag = F[1]
    original_length = read_U64(F[2:10])
    stored_length   = read_U64(F[10:18])
    require original_length <= 16*1024*1024
    require stored_length <= L-18
    data = F[18:18+stored_length]

    if flag == 0:
        require stored_length == original_length
        message = data
    else:
        message = RawINFLATE_Bounded(data, output_limit=original_length)
        require a complete stream reached its end
        require every byte of data was consumed
        require no dictionary, extra member, or trailing compressed data
        require len(message) == original_length

    # The remainder of F is authenticated padding; its values are ignored.
    return message
```

An ordinary cover or a wrong key normally reaches authentication failure. The random-looking bootstrap is not an authenticity check. Associated data binds the salt, profile, and dimensions; it does not authenticate every cover pixel or every PNG metadata byte. Some image changes can preserve both extracted syndromes, so this design must not be described as complete image authentication.

Replay protection is not provided by AEAD alone. An application requiring it must remember successfully received salts or authenticated application identifiers. It should not expose different remote responses for replay, malformed images, bad tags, and decompression errors.

### 3.8 Numerical entropy-bound diagnostic

The following diagnostic is used to measure coding efficiency, not to perform embedding or certify secrecy. Compute it separately for header and body using their actual cost arrays and message lengths.

```text
BinaryBound(costs, m):
    dry = finite positive entries of costs
    if m > len(dry): FAIL
    if m == len(dry): return 0.5 * sum(dry)
    if m == 0: return 0

    entropy(lambda):
        total = 0
        for r in dry:
            a = lambda*r
            e = exp(-a)           # underflow to zero is acceptable
            p = e/(1+e)          # avoids overflow in exp(+a)
            if p > 0:
                total += -p*log2(p) - (1-p)*log2(1-p)
        return total

    lo = 0; hi = 1
    while entropy(hi) > m:
        hi = 2*hi
        require finite(hi)
    repeat 80 times:
        mid = (lo+hi)/2
        if entropy(mid) > m: lo = mid
        else: hi = mid
    lambda = (lo+hi)/2
    return sum(r * exp(-lambda*r)/(1+exp(-lambda*r)) for r in dry)
```

Use stable `log1p` forms near zero when implementing the entropy expression. For a fixed cover and full-row-rank dry channel, average optimized STC distortion across many independent uniform messages before comparing with the entropy lower bound. A particular message can require zero changes and lie below that expectation bound. Report the distribution of finite-code costs and failures; do not compute a misleading single-message “coding loss.”

### 3.9 Executable small-instance coding oracle

The following Python block is a self-contained correctness oracle for the banded matrix, its trellis, termination, wet constraints, and bit order. It uses only the standard library. It is intentionally restricted to tiny exhaustive instances and is not the high-performance image encoder. `h` is varied here to exercise edge cases; the image profile fixes it at 10. The test uses deterministic simulation randomness only for reproducibility.

<!-- BEGIN_EXECUTABLE_STC_ORACLE -->
```python
import hashlib
import hmac
import itertools
import math
import random


def masks(n, m, height, key):
    out = []
    groups = []
    for row in range(m):
        begin, end = row * n // m, (row + 1) * n // m
        groups.append((begin, end))
        for col in range(begin, end):
            msg = (b"STEG-BP/1/column\x00" + row.to_bytes(4, "big")
                   + col.to_bytes(8, "big"))
            raw = int.from_bytes(hmac.new(key, msg, hashlib.sha256).digest()[:2], "big")
            value = (raw & ((1 << height) - 1)) | 1 | (1 << (height - 1))
            out.append(value & ((1 << min(height, m - row)) - 1))
    return out, groups


def syndrome(y, m, columns, groups):
    result = [0] * m
    for row, (begin, end) in enumerate(groups):
        for col in range(begin, end):
            if y[col]:
                value = columns[col]
                for bit in range(value.bit_length()):
                    result[row + bit] ^= (value >> bit) & 1
    return result


def trellis(x, costs, target, height, columns, groups):
    count = 1 << height
    score = [math.inf] * count
    score[0] = 0
    trace = []
    for row, (begin, end) in enumerate(groups):
        for col in range(begin, end):
            c0 = 0 if x[col] == 0 else costs[col]
            c1 = 0 if x[col] == 1 else costs[col]
            nxt = [math.inf] * count
            chosen = bytearray(count)
            for state in range(count):
                a = score[state] + c0
                b = score[state ^ columns[col]] + c1
                if a <= b:
                    nxt[state] = a
                else:
                    nxt[state] = b
                    chosen[state] = 1
            trace.append(chosen)
            score = nxt
        nxt = [math.inf] * count
        for state in range(count):
            if (state & 1) == target[row]:
                nxt[state >> 1] = score[state]
        score = nxt
    if not math.isfinite(score[0]):
        return None, math.inf
    answer = [0] * len(x)
    state = 0
    for row in range(len(target) - 1, -1, -1):
        state = (state << 1) | target[row]
        begin, end = groups[row]
        for col in range(end - 1, begin - 1, -1):
            answer[col] = trace[col][state]
            if answer[col]:
                state ^= columns[col]
    assert state == 0
    return answer, score[0]


def bits(data):
    return [(byte >> shift) & 1 for byte in data for shift in range(7, -1, -1)]


def octets(vector):
    assert len(vector) % 8 == 0
    return bytes(sum(vector[i + k] << (7 - k) for k in range(8))
                 for i in range(0, len(vector), 8))


def run_oracle():
    rng = random.Random(57391)
    key = bytes(range(32))
    checked = 0
    for n in range(1, 9):
        for m in range(1, n + 1):
            for height in (1, 2, 3, 10):
                columns, groups = masks(n, m, height, key)
                # Full-row-rank test: every syndrome must occur without wet restrictions.
                possible = {tuple(syndrome(y, m, columns, groups))
                            for y in itertools.product((0, 1), repeat=n)}
                assert len(possible) == 1 << m
                x = [rng.randrange(2) for _ in range(n)]
                for costs in (
                    [1] * n,
                    [rng.randrange(1, 10) for _ in range(n)],
                    [math.inf if rng.randrange(3) == 0 else rng.randrange(1, 10)
                     for _ in range(n)],
                    [math.inf] * n,
                ):
                    table = {}
                    for y in itertools.product((0, 1), repeat=n):
                        distance = sum(costs[i] for i in range(n) if y[i] != x[i])
                        s = tuple(syndrome(y, m, columns, groups))
                        table[s] = min(table.get(s, math.inf), distance)
                    for target in itertools.product((0, 1), repeat=m):
                        answer, optimum = trellis(x, costs, target, height, columns, groups)
                        expected = table.get(target, math.inf)
                        assert optimum == expected
                        if answer is not None:
                            assert tuple(syndrome(answer, m, columns, groups)) == target
                            assert sum(costs[i] for i in range(n) if answer[i] != x[i]) == optimum
                            assert all(answer[i] == x[i] for i in range(n)
                                       if math.isinf(costs[i]))
                        else:
                            assert math.isinf(expected)
                        checked += 1
    sample = bytes(range(256))
    assert octets(bits(sample)) == sample
    for value in range(256):
        for change in (-1, 1):
            if 0 <= value + change <= 255:
                assert ((value + change) & 1) == ((value & 1) ^ 1)
    print(f"PASS: {checked} exhaustive syndrome/cost cases; bit order and unit changes")


if __name__ == "__main__":
    run_oracle()
```
<!-- END_EXECUTABLE_STC_ORACLE -->

### 3.10 Required integration verification

Verification performed for this document: the embedded oracle passed all 16064 exhaustive syndrome/cost cases, including unreachable wet configurations, plus the bit-order and unit-change checks. The framing arithmetic and the finite-score bound were also checked. No complete image encoder, cryptographic integration, or steganalysis benchmark was executed.

The coding oracle cannot certify a PNG codec, cryptographic library, numerical cost implementation, or statistical security. A production implementation must additionally verify:

1. Successful exact round trips for empty messages, all byte values, incompressible data, compressible data, and the largest fitting frame.
2. Correct bootstrap and body extraction with independently implemented sender and receiver, including fixed-randomness interoperability vectors.
3. Rejection of oversized messages, unsupported image modes, malformed PNGs, and all-wet covers; preservation of the immutable cover on failure.
4. Failure on a wrong key, changed salt syndrome, modified ciphertext/tag syndrome, and inconsistent authenticated dimensions.
5. Bounded decompression, strict stream termination, integer-overflow checks, and no plaintext release before authentication.
6. Exact mask generation, permutation regeneration, stream counters, byte order, and library AEAD ciphertext/tag order.
7. Direct-versus-optimized agreement for cost calculations, including impulse tests at the interior boundary and every wet-region edge.
8. Every modified sample differs by exactly one, no forbidden direction occurs, and no pixel is assigned to both coding stages.
9. Lossless serialization preserves every stego sample and follows the ordinary source's file-container behavior.
10. The actual code's resource limits and checkpointed traceback agree with the full dynamic program on manageable instances.

These are correctness requirements. Statistical experiments in Section 4 are separate and remain necessary even if every round-trip check passes.

## Section 4: Security Analysis & Steganalysis Evasion

### 4.1 Exact correctness and optimization guarantees

**Syndrome optimality.** After processing any trellis column, each finite score is the minimum cost of a partial parity sequence inducing its state and satisfying all previously completed rows. This holds initially because only the empty path has cost zero. The two candidate transitions enumerate the two possible output parities. Taking their minimum preserves the invariant. At a row boundary, subsequent columns cannot affect that completed row, so pruning the wrong low bit is exact. Truncated tail columns leave state zero after the final row. Backtracking therefore returns a minimum-cost feasible parity sequence or reports infeasibility.

This proof applies to the specified finite banded matrix and fixed additive costs. It does not establish the globally best code, the globally smallest nonadditive residual change, or the statistically least detectable image.

**Recovery.** On sender success, the two disjoint stages satisfy

$$
H_H\operatorname{parity}(S_{I_H})=\operatorname{Bits}(salt),\qquad
H_B\operatorname{parity}(S_{I_B})=\operatorname{Bits}(W).
$$

Lossless transport preserves both parity vectors. The receiver reconstructs the first matrix and positions from the key and dimensions, recovers the salt, derives the same body parameters, and recovers $W$. XOR whitening is its own inverse; authenticated decryption returns exactly the sender's frame. Validated raw data or bounded lossless decompression then returns exactly $M$. Hence

$$
\operatorname{ExtractAndDecrypt}(\operatorname{EncryptAndEmbed}(C,M,K),K)=M
$$

for every successful encoding, correct primitive implementation, and lossless sample channel. The original cover and cost map are absent from this identity's receiver inputs.

### 4.2 Cryptographic guarantees and their limits

Assume the 256-bit key is unpredictable, HKDF and the keyed streams have their required pseudorandomness properties, AEAD is secure under unique per-message keys, and side channels do not expose secrets. Message confidentiality and integrity then reduce to those assumptions, plus correct frame parsing and the collision probabilities of the key schedule.

The independent whitening stream permits a standard computational hybrid: replace its keyed pseudorandom bytes by independent uniform bytes. In that hybrid, the whitened body is uniform regardless of the encrypted frame and tag. Replacing derived subkeys by independent keys incurs the key-derivation reduction terms. This supports the encoder's computationally random-body assumption; it does not make the cover distribution uniform or prove that random modifications resemble sensor noise.

Do not summarize forgery resistance as exactly $2^{-128}$ for every adversarial setting. A random complete-tag guess has that ideal probability, while real AEAD bounds also depend on lengths, verification attempts, primitive advantages, and key usage. Preserve the full tag and constant-time verification.

The salt is authenticated by the body's associated data, although not separately authenticated before body extraction. Corruption of it changes the derived body mapping and keys, normally leading to authentication failure. All pre-authentication work is bounded by public image dimensions.

This profile does not provide forward secrecy after master-key compromise, public-key establishment, anonymity, deniable transcript generation, or authenticity of the complete image. A receiver with the key can deliberately test for a valid payload. Offline key guessing is also possible using the tag; this is why a low-entropy password is not accepted as the shared key.

### 4.3 What can be justified about classical tests

**Chi-square and histogram attacks.** The algorithm avoids direct assignment of parity through `pixel = (pixel & ~1) | bit`. For a parity change it chooses a cost-minimizing legal $+1$ or $-1$ move, with randomized ties. The pair-equalization derivation for uniform LSB replacement therefore does not directly describe the encoder. However, the unit-change histogram convolution in Section 1.5 still applies approximately in homogeneous regions, and an observer can learn its adaptive counterpart. There is no theorem that all chi-square or histogram tests fail.

**RS-style regularity analysis.** These tests compare a local discrimination function before and after controlled parity flips. A typical function is a sum of neighboring absolute differences. Group classifications and their asymmetries change when embedding perturbs local smoothness. Avoiding nearly flat regions and using low-cost changes can reduce some of those effects, but does not preserve every group classification or invalidate every estimator. Fit test calibration to the actual adaptive algorithm rather than treating a failed uniform-LSB estimator as a security proof.

**Sample-pair and local transition tests.** Changing adjacent samples can alter pair frequencies even when a global histogram looks normal. Keyed permutation randomizes the relationship between code positions and image positions; it does not erase the statistical impact at the physical pixel locations. Inspect horizontal, vertical, and diagonal transitions and selection-conditioned versions of these tests.

**Residual rich models.** Quantized high-pass residual co-occurrences capture dependencies suppressed by visual image content. Weighted wavelet costs reduce a surrogate for changes in some such residuals, but the observer can combine other filters, quantizers, co-occurrence orders, and local classifiers. Preserving a limited feature vector cannot prove preservation of the joint image law.

The scientifically defensible claim is that adaptive coding is designed to reduce conspicuous modifications and is worth measuring against these attacks. The claim that it necessarily evades them is unsupported.

### 4.4 Deep steganalysis and the missing universal proof

SRNet-style architectures retain high-resolution processing early so that a weak embedding residual is not removed by pooling. Xu-Net-style designs emphasize high-pass preprocessing and residual nonlinearities. ResNet and EfficientNet variants can learn useful forensic features when their preprocessing, resolution, and training protocol match the domain. Strong JPEG results from a classification backbone do not automatically imply strong performance on spatial grayscale embedding.

Residual transformers, multi-scale networks, and ensembles expand the detector family further. A detector may condition on estimated modification probabilities, image size, processing history, or acquisition source. Experiments must include retraining on the actual encoder rather than only applying a frozen pretrained checkpoint.

For any fixed classifier score $f$, a bound such as

$$
|f(S)-f(C)|\leq L\|S-C\|
$$

would require a justified Lipschitz constant in the chosen norm and a meaningful decision margin. Even then it only describes that particular score around that particular cover. It does not bound the performance of a newly trained detector on the two populations.

The only direct classifier-independent guarantee here is conditional: if the full cover and stego distributions satisfy the KL or TV bound in Section 1.3, every measurable detector, including a deep network, obeys the corresponding advantage bound. The selected cost function and STC do not prove that premise. Therefore a mathematical proof of universal deep-network evasion cannot honestly be supplied for this pipeline.

Adversarial tuning against one or several detectors can improve results on them while increasing artifacts exploitable by others. It also introduces a selection distribution if the sender keeps only favorable candidates. Gradient-based or classifier-guided postprocessing is excluded from the normative encoder. Any proposed extension needs independent adaptive evaluation.

### 4.5 Higher-order correlations, selection channels, and side information

Costs derived from the cover are a selection channel: they influence where changes occur. The observer can estimate the same content structure from the stego and train a selection-aware detector. The secret permutation does not hide the fact that changes tend to occur in particular textures or that a border is untouched.

The chosen wet border, smoothness threshold, fixed header split, random matrix distribution, and sign-selection rule all create potential fingerprints. They are part of the method under test. In particular, a cover near the smoothness threshold can move across it after embedding; this does not break extraction because the receiver does not recompute the mask, but it can affect steganalysis.

Color images add dependencies between channels and the acquisition mosaic. A naïve extension applying the grayscale algorithm independently to RGB channels can violate those dependencies. It is outside this profile. A color extension requires joint costs, channel-aware detection, and a new source model.

Side information such as a high-bit-depth precover or precompression image may improve coefficient decisions by exposing quantization uncertainty. It only helps when that information actually exists and matches the final ordinary source. It cannot be reconstructed by assuming every decoded JPEG pixel is an independent original observation.

Nonadditive models can introduce interaction terms,

$$
D_{joint}(\Delta)=\sum_i\rho_i(\Delta_i)
+\sum_{(i,j)\in\mathcal E}\psi_{ij}(\Delta_i,\Delta_j),
$$

or use a normalized distribution proportional to $\exp[-\lambda D_{joint}(\Delta)]$. Such formulations can model dependencies that an additive STC ignores. They introduce a harder optimization problem and require calibrated interaction functions. A lower interaction objective is still not an automatic reduction in true detectability.

One can preserve extractability during a binary postprocessing move $v$ by requiring $Hv=0$, because $H(y\oplus v)=Hy$. This algebra alone says nothing about legal sample values, the cost of the new image, or statistical security. It is a research direction, not an extra step in the specified algorithm.

### 4.6 Capacity, visual fidelity, and detection probability

Define three distinct rates:

$$
\alpha_{gross}=\frac{8B}{N},\qquad
\alpha_{useful}=\frac{8|M|}{N},\qquad
q=\frac{\#\{i:S_i\ne C_i\}}{N}.
$$

`Useful` rate can exceed stored-data rate when the message compresses; report both original and stored lengths. Header, tag, frame fields, and padding are part of the gross embedding load. For JPEG experiments, bits per nonzero AC coefficient and bits per image pixel are different normalizations and must not be interchanged.

For this unit-change grayscale encoder,

$$
\operatorname{MSE}=\frac1N\sum_i(S_i-C_i)^2=q,\qquad
\operatorname{PSNR}=10\log_{10}\frac{255^2}{q}.
$$

If $q=0$, PSNR is infinite. Examples calculated from the formula are:

| Fraction of changed samples $q$ | PSNR in dB | Security interpretation |
|---:|---:|---|
| 0.001 | 78.13 | Very small visual error; detectability unknown |
| 0.005 | 71.14 | Very small visual error; detectability unknown |
| 0.010 | 68.13 | Very small visual error; detectability unknown |
| 0.050 | 61.14 | Small unit-valued error; detectability unknown |

Even changing every pixel by one gives about 48.13 dB. High PSNR is therefore a weak steganographic security criterion.

For uniform binary costs and the ideal independent-symbol relaxation, $\alpha=h_2(q)$ describes the entropy-distortion curve. For ternary information-bearing signs, the corresponding symmetric expression is $\alpha=h_2(q)+q$. Adaptive heterogeneous costs, wet pixels, header/body partitioning, finite-length coding, and framing change actual efficiency. Do not use the ternary curve to advertise the binary profile.

SSIM can complement PSNR as a perceptual diagnostic. With local weighted means, variances, and covariance,

$$
\operatorname{SSIM}(C,S)=
\frac{(2\mu_C\mu_S+c_1)(2\sigma_{CS}+c_2)}
{(\mu_C^2+\mu_S^2+c_1)(\sigma_C^2+\sigma_S^2+c_2)}.
$$

For reproducibility, use an $11\times11$ normalized Gaussian window of standard deviation 1.5, population-weighted moments, $c_1=(0.01\cdot255)^2$, $c_2=(0.03\cdot255)^2$, and average over valid window centers. Report these choices. SSIM near one does not imply small KL divergence or high detector error.

For a detector at a fixed threshold, report

$$
P_E=\tfrac12(P_{FA}+P_{MD}),\qquad
P_D=1-P_{MD}.
$$

$P_E$ is an average error under equal priors, not the probability of detecting a particular transmission. At nonuniform prior $\pi$, risk is $(1-\pi)P_{FA}+\pi P_{MD}$. Report ROC-AUC and detection rates at small false-alarm rates as well. Choose thresholds on validation data and lock them before testing; do not optimize them on the reported test set.

Increasing gross payload usually requires more or more expensive changes. The resulting detection trade-off depends on source and detector; no universal function $P_E(\alpha,\operatorname{PSNR})$ exists. This blueprint supplies no fabricated numerical detection rate for its unbenchmarked composition.

### 4.7 Image size, repeated transmissions, and pooled detection

For independent observations, relative entropy adds:

$$
D_{\mathrm{KL}}(P_C^{\otimes t}\parallel P_S^{\otimes t})
=tD_{\mathrm{KL}}(P_C\parallel P_S).
$$

Small per-image deviations can therefore accumulate over many transmissions. For dependent observations, use the chain rule over conditional distributions; key reuse and repeated scenes can invalidate an independent-image calculation.

A local small-change model often has divergence proportional to $Np^2$. Keeping that quantity bounded requires $p=O(N^{-1/2})$, giving $O(\sqrt N)$ changes. Translating changes into message bits depends on coding efficiency; for an ideal sparse binary entropy expression, $Nh_2(p)$ can include an additional logarithmic factor. Square-root-style capacity statements must specify their channel and coding assumptions. They are not a universal exact bits-per-image formula.

The practical implication is that a fixed 0.05 bpp setting cannot be assumed equally covert across resolutions or arbitrarily many images. Evaluate each admitted size class and transmission population. Reusing an exact cover, publishing both cover and stego, or publishing multiple stego variants of one cover enables much stronger comparison attacks.

### 4.8 Scientific evaluation protocol

An evaluation must test the final serialized, accepted output of the actual message encoder. A simulator without salt, framing, finite STC loss, rejection, and PNG behavior is not a substitute.

**Sources and partitions.** Collect representative native grayscale sources with known processing pipelines. Include diverse real textures, low-noise regions, exposure levels, sensor sources, and sizes. Split by camera or source, capture session, and scene where possible. Keep every cover and all its stego variants in one partition. Near-duplicate scenes and crops must not cross training and testing.

**Control populations.** Compare ordinary output against the complete stego pipeline. Also compare reserialized innocent images against untouched source files to expose serializer fingerprints. Include a control using the final cover-selection policy without embedding, so that admission artifacts can be separated experimentally from pixel changes.

**Detector families.** Include histogram and RS-style tests, residual co-occurrence classifiers, a selection-aware variant, SRNet-style residual learning, Xu-Net-style preprocessing, and suitably adapted residual or efficient convolutional networks. Include a residual transformer or another independent modern architecture where training resources permit. Retrain on the actual algorithm, its fixed wet rules, and its image sizes. For generative comparisons, include matched generator controls and latent-noise detectors.

**Training discipline.** Use independent seeds, sensible validation-based hyperparameter selection, and separate held-out evaluation. Include matched-source tests, mismatched-source tests, and adaptation after supplying the adversary examples from the deployment source. Poor cross-source generalization is not a security guarantee because the observer may adapt.

**Payload and key experiments.** Evaluate the selected profile as written. For research sweeps, instantiate separately agreed rates such as 0.01, 0.025, 0.05, 0.1, and 0.2 bpp, keeping their real overheads explicit. Do not silently switch rates per image. Test many images per key, many keys, multiple random salts, bootstrap-only embedding, body-only embedding, and the joint result. Multiple variants of one test image are correlated samples.

**Ablations.** Compare the relative-wavelet cost with HILL-style and local-model costs using matched coding and gross lengths. Compare STC against random-location unit changes at the same message size, and compare the actual finite code against its entropy relaxation. Evaluate the wet-mask policy and header fraction as distinct experimental choices. Do not declare a hybrid superior without these controls.

**Primary measurements.** Record useful and gross payload, modifications, modeled distortion, coding failures, exact extraction success, wall-clock time, memory, PSNR, SSIM, ROC-AUC, $P_E$, and detection rates at declared false-alarm rates. Measure transmitted file properties and pooled-key detection as well as per-image pixels.

**Uncertainty.** Use confidence intervals and resampling at the independent cover/source unit. Account for repeated seeds, related scenes, and multiple model selection. For a rough independent-error calculation, an accuracy near 0.5 has standard error approximately $0.5/\sqrt n$. Distinguishing 0.50 from 0.51 therefore needs many independent test units; ordinary intervals from a small image set are uninformative. Use an explicit equivalence margin rather than interpreting failure to reject as equality.

At a false-alarm target of $10^{-3}$, a thousand innocent images is inadequate for a precise assessment. With zero false alarms in $n$ independent controls, a rough 95% upper bound is $3/n$. The same zero-event bound can describe extraction failures under the tested lossless conditions; it cannot bound untested detector families.

**Release criterion.** Define the tolerated advantage, false-alarm operating points, source coverage, and failure budget before experimentation. Freeze the encoder and threshold choices, then evaluate on unseen sources and adaptive detectors. Passing establishes only the declared empirical claim. A deployment with no such completed experiment remains an unvalidated candidate even if its code is correct.

### 4.9 Research directions that could improve the profile

Several improvements are plausible but are not silently included in the specification:

| Direction | Potential benefit | Additional obligation |
|---|---|---|
| Tuned matrices or greater STC height | Lower coding loss | Measure time, memory, wet failures, and detectability at the same gross length |
| Multilayer nonbinary coding | Use sign choices to carry information more efficiently | Specify both layers, conditional costs, and exact decoder synchronization |
| Source-calibrated costs | Better fit to acquisition uncertainty | Independent sources and detectors must verify the gain |
| Nonadditive interactions | Better preserve joint residual behavior | Solve the new constrained problem and check for overfitting |
| Native JPEG coefficient embedding | Match a JPEG publishing source | Specify coefficient access, quantization tables, zero handling, and coefficient-stable transport |
| High-bit-depth precover information | Exploit real quantization uncertainty | Demonstrate availability and compatibility with the ordinary output pipeline |
| Distribution-preserving generation | Stronger security relative to a defined generator | Match the full generator distribution and quantify extraction errors after serialization |
| Receiver-only latent optimization | Improve extraction from generated media | Establish error rates and resource bounds; do not infer sender security from decoder success |

A minimax research objective can formalize the aspiration:

$$
\min_E\ \sup_{A\in\mathcal A}\operatorname{Adv}_A(P_C,P_{E(C,M,K)})
\quad\text{subject to}\quad
\Pr[D(E(C,M,K),K)\ne M]\leq\eta,
\quad |M|\geq m_0,
\quad D_{visual}(C,S)\leq d_0.
$$

The observer family $\mathcal A$, source population, computational budgets, and transmission model must be explicit. Optimizing against a finite learned ensemble approximates this problem; it does not solve the supremum over all detectors. A newly effective detector changes the empirical frontier without contradicting correct encryption or syndrome decoding.

### 4.10 Final implementation contract

The specified pipeline is one interoperable experimental design: native grayscale PNG, fixed authenticated framing, fresh salt-derived keys, independent whitening, synchronized two-stage permutations, directional residual costs, explicit wet constraints, a fully specified banded code, signed unit modifications, and lossless verification.

Its formal claims are successful lossless recovery and exact finite-code optimization of the stated additive objective. Its cryptographic claims are conditional on the standard primitive assumptions and correct key use. Its statistical claim is deliberately limited to a design rationale awaiting the prescribed source-specific, adaptive evaluation. Universal imperceptibility, equality to the true photographic distribution, and immunity to future steganalysis are not established by this blueprint.
