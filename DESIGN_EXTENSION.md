# Conditional residual sign balancing

This is an experimental extension designed and implemented for this project. It is not a claim of research priority, a replacement for authenticated encryption, or a proof of distributional security. The baseline remains available for controlled comparisons.

## The unused degree of freedom

Let the original integer-valued image be `x`, the encoded image be `y`, and the parity-check matrix be `H`. Syndrome extraction uses

$$H(y\bmod 2)=m\quad\text{over }\mathbb F_2.$$

The exact syndrome-trellis optimizer first chooses the change set

$$S=\{i:y_i\ne x_i\}.$$

At an interior-valued changed pixel, both `x_i - 1` and `x_i + 1` have the same parity. Therefore, changing only the sign of a unit modification does not change the syndrome. Define

$$y_i(s)=x_i+s_i\mathbf1_{i\in S},\qquad s_i\in\{-1,+1\}.$$

Keep saturated cover pixels fixed to their only legal direction. All other change locations, border protections, and smooth-region exclusions remain fixed. Since the implemented interior costs are symmetric, sign balancing also preserves the baseline's additive embedding cost. Both the number of changes and PSNR remain exactly unchanged.

## Cover-conditioned objective

Use eight small integer high-pass filters: horizontal and vertical first and second differences, both diagonal first differences, a four-neighbor Laplacian, and a nine-tap second-order residual. Compute the cover's local variance in a 5-by-5 window and assign one of four fixed activity groups, separated at 16, 64, and 256 squared gray levels.

For filter `f`, cover-defined activity group `g`, quantization step `q` in `{1,2,4}`, and bin `b` in `{-8,...,8}`, count the corresponding signed, rounded, clipped residuals:

$$c_j=N_j(x),\qquad d_j(s)=N_j(y(s))-c_j,\qquad j=(f,g,q,b).$$

The objective is

$$J(s)=\sum_j\frac{d_j(s)^2}{c_j+32}.$$

The denominator keeps rare bins from receiving unbounded weight. Activity groups come from the original cover and remain frozen throughout optimization. Only the sender needs these groups or the cover. The receiver remains unchanged.

## Exact incremental optimization

Initialize signs from the baseline encoder. Visit changed pixels in raster order, alternating forward and backward traversal for at most six passes. A sign reversal at pixel `i` changes its stego value by `-2 s_i`. Only residual centers whose filter support contains `i` can change. Accumulate their histogram-count increments `u_j`, including collisions in the same histogram bin, before deciding whether to accept the flip:

$$\Delta J=\sum_{j:u_j\ne0}\frac{2d_j u_j+u_j^2}{c_j+32}.$$

Accept only if `Delta J < -1e-12`; then update the image, affected residuals, and histogram deltas. Stop early if a complete pass accepts no flips. The native implementation does not allocate a full trial image for each candidate.

```text
baseline = exact_syndrome_trellis_embed(cover, encrypted_frame)
change_set = locations(baseline != cover)
state = residual_histograms(cover, baseline)
for pass in 0..5:
    accepted = 0
    for i in alternating_scan(change_set, pass):
        if cover[i] is 0 or 255: continue
        delta = histogram_increments_for_sign_reversal(i, state)
        if objective_increment(delta, state) < -1e-12:
            reverse_unit_change(i)
            update_residuals_and_histograms(delta, state)
            accepted += 1
    if accepted == 0: break
assert final_parities == baseline_parities
assert final_change_set == change_set
assert maximum_absolute_change_from_cover <= 1
assert authenticated_extract(serialized_final_image) == original_message
```

The implementation checks syndrome recovery and the benchmark additionally checks authenticated recovery after PNG serialization for both variants on every admitted cover. These are correctness properties, not statistical-security evidence.

## Why it might help, and why it might fail

Independent random signs can introduce residual-histogram drift even when a good distortion model has selected sensible change locations. The extension attempts to use available sign choices to reduce that drift without extra modifications or payload reduction. This is a falsifiable hypothesis, not an assumption in the acceptance rule.

Matching selected histograms does not match the full image distribution. The optimization can create new dependencies between neighboring signs, over-constrain a statistic that naturally fluctuates, or leave directional artifacts from its scan order. Activity selection is itself observable. Higher-order residual co-occurrences, image-source mismatch, reused-key effects, and a sufficiently trained neural detector remain relevant attacks. Optimizing a smaller surrogate can make a stronger detector's job easier.

Accordingly, the comparison uses identical covers, payload rates, payloads, cryptographic randomness, and changed-pixel sets. It reports the independently trained detectors' results, including a negative result if balancing hurts. Detector features include third-order residual filters and fourth-order co-occurrences that are absent from the optimized histogram objective. Neither an objective decrease nor a high PSNR is counted as a pass.

Lowering payload is a separate intervention. Any improvement from 0.05 to 0.01 gross bpp must be reported as a capacity trade-off, not credited to the sign optimizer. On a 512-by-512 image, the authenticated frame permits 1,572 versus 261 stored message bytes, respectively, before possible compression gains.
