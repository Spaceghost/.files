// Warm bloom: bright amber and cream pixels lift their neighbours very slightly,
// so the cursor and highlighted text glow like the panel's amber accents.
// Eight taps on a small ring keep it cheap; text edges stay sharp because
// only the bright fraction above the threshold contributes.

const float RADIUS = 2.5;
const float STRENGTH = 0.14;
const vec3 WARMTH = vec3(1.0, 0.92, 0.72);

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    vec4 base = texture(iChannel0, uv);
    vec2 pixel = 1.0 / iResolution.xy;
    vec3 glow = vec3(0.0);
    for (int i = 0; i < 8; i++) {
        float angle = float(i) * 0.7853981634;
        vec3 tap = texture(iChannel0, uv + vec2(cos(angle), sin(angle)) * RADIUS * pixel).rgb;
        float luminance = dot(tap, vec3(0.299, 0.587, 0.114));
        glow += tap * smoothstep(0.55, 0.95, luminance);
    }
    glow *= 0.125;
    fragColor = vec4(base.rgb + glow * WARMTH * STRENGTH, base.a);
}
