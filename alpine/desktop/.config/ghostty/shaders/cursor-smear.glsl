// Cursor smear: a short-lived trail from where the cursor was to where it is.
// The trail is a parallelogram between the previous and current cursor cells,
// tinted with the terminal's own cursor colour, fading out over DURATION.
// Ghostty gives cursor rectangles as the top-left corner (-X, +Y) plus size,
// in the same bottom-left pixel space as fragCoord.

const float DURATION = 0.15;

float sdfRectangle(vec2 p, vec2 center, vec2 extent) {
    vec2 d = abs(p - center) - extent;
    return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}

// Signed distance to a convex quadrilateral (v0..v3 in order), winding-safe.
// The running squared distance and sign travel as a pair instead of through
// in/out parameters, which keeps Ghostty's shader translation warning-free.
vec2 segment(vec2 p, vec2 a, vec2 b, vec2 state) {
    vec2 e = b - a;
    vec2 w = p - a;
    vec2 proj = a + e * clamp(dot(w, e) / dot(e, e), 0.0, 1.0);
    float d = min(state.x, dot(p - proj, p - proj));
    float c0 = step(0.0, p.y - a.y);
    float c1 = 1.0 - step(0.0, p.y - b.y);
    float c2 = 1.0 - step(0.0, e.x * w.y - e.y * w.x);
    float inside = c0 * c1 * c2;
    float outside = (1.0 - c0) * (1.0 - c1) * (1.0 - c2);
    float s = state.y * mix(1.0, -1.0, step(0.5, inside + outside));
    return vec2(d, s);
}

float sdfQuad(vec2 p, vec2 v0, vec2 v1, vec2 v2, vec2 v3) {
    vec2 state = vec2(dot(p - v0, p - v0), 1.0);
    state = segment(p, v0, v3, state);
    state = segment(p, v1, v0, state);
    state = segment(p, v2, v1, state);
    state = segment(p, v3, v2, state);
    return state.y * sqrt(state.x);
}

vec2 toClip(vec2 value, float isPosition) {
    return (value * 2.0 - iResolution.xy * isPosition) / iResolution.y;
}

float coverage(float distance) {
    return 1.0 - smoothstep(0.0, toClip(vec2(2.0), 0.0).x, distance);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    fragColor = texture(iChannel0, uv);

    float age = iTime - iTimeCursorChange;
    // Nothing to draw: no move yet, an unfocused pane, or the trail has faded.
    if (iPreviousCursor.z <= 0.0 || iTimeCursorChange <= 0.0 || age > DURATION || iFocus <= 0) {
        return;
    }
    vec4 current = vec4(toClip(iCurrentCursor.xy, 1.0), toClip(iCurrentCursor.zw, 0.0));
    vec4 previous = vec4(toClip(iPreviousCursor.xy, 1.0), toClip(iPreviousCursor.zw, 0.0));
    vec2 p = toClip(fragCoord, 1.0);

    // Choose the two corners that keep the quad convex for this direction of travel.
    float leftToRight = step(previous.x, current.x) * step(current.y, previous.y);
    float rightToLeft = step(current.x, previous.x) * step(previous.y, current.y);
    float start = 1.0 - max(leftToRight, rightToLeft);
    float other = 1.0 - start;
    vec2 v0 = vec2(current.x + current.z * start, current.y - current.w);
    vec2 v1 = vec2(current.x + current.z * other, current.y);
    vec2 v2 = vec2(previous.x + current.z * other, previous.y);
    vec2 v3 = vec2(previous.x + current.z * start, previous.y - previous.w);

    float cursor = sdfRectangle(p, current.xy + vec2(current.z, -current.w) * 0.5, current.zw * 0.5);
    float trail = sdfQuad(p, v0, v1, v2, v3);

    float progress = clamp(age / DURATION, 0.0, 1.0);
    float eased = pow(1.0 - progress, 3.0);
    float travel = distance(current.xy, previous.xy);
    // The tail retreats toward the cursor as the trail ages.
    float fade = 1.0 - smoothstep(travel, cursor, eased * travel);
    float mask = coverage(trail) * fade * step(0.0, cursor);
    vec3 tint = iCurrentCursorColor.rgb;
    fragColor = vec4(mix(fragColor.rgb, tint, mask), max(fragColor.a, mask));
}
