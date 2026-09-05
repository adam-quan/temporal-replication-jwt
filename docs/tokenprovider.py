#!/usr/bin/env python3
"""Generates docs/tokenprovider.svg - how the replication TokenProvider works.

Three phases read left to right: the plugin is wired in at boot, consulted on
every outbound cross-cluster RPC, and the token it produces is verified by the
peer. Every assertion here is taken from the server source at
go.temporal.io/server v1.32.0-160.1 and from server/tokenprovider.go.

Run via ./scripts/render-diagram.sh.
"""

W, H = 1960, 1040

INK, MUTED, FAINT = "#1f2933", "#5b6672", "#8a94a3"
RED, RED_DK   = "#b3403f", "#8c2f2e"
BLUE, BLUE_DK = "#3f6fae", "#2f5487"
GREEN, GRN_DK = "#3f8a3f", "#2f6b2f"
AMBER, AMB_DK = "#d18b1f", "#9a6510"
GREY = "#8a94a3"

FONT = "DejaVu Sans, Helvetica, Arial, sans-serif"
MONO = "DejaVu Sans Mono, Menlo, monospace"

out = []
def add(s): out.append(s)
def esc(t): return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def panel(x, y, w, h, stroke, fill, rx=14, sw=2.0, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

def text(x, y, t, size=11, fill=INK, weight="normal", anchor="start", family=FONT):
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" fill="{fill}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{esc(t)}</text>')

def step(n, x, y, w, h, title, body=(), mono=(), stroke=FAINT, fill="#ffffff",
         sw=1.4, dash=None, accent=None):
    """A numbered step box. `body` is prose, `mono` is code/identifiers."""
    panel(x, y, w, h, stroke, fill, rx=10, sw=sw, dash=dash)
    if n is not None:
        c = accent or stroke
        add(f'<circle cx="{x+20}" cy="{y+20}" r="12.5" fill="{c}"/>')
        text(x + 20, y + 24.5, str(n), size=11.5, fill="#ffffff", weight="bold", anchor="middle")
    text(x + (40 if n is not None else 14), y + 25, title, size=11.5, weight="bold")
    yy = y + 25
    for ln in body:
        yy += 14
        text(x + 14, yy, ln, size=9.4, fill=MUTED)
    for ln in mono:
        yy += 13.5
        text(x + 14, yy, ln, size=9, fill=MUTED, family=MONO)

def arrow(pts, stroke, sw=1.8, dash=None, marker="end"):
    d = "M " + " L ".join(f"{px} {py}" for px, py in pts)
    da = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#a-{stroke.lstrip("#")})"' if marker else ""
    add(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw}" '
        f'stroke-linejoin="round" stroke-linecap="round"{da}{m}/>')

def elabel(x, y, lines, fill, size=9, anchor="middle"):
    wmax = max(len(l) for l in lines) * size * 0.56 + 10
    add(f'<rect x="{x - wmax/2 if anchor=="middle" else x-5}" y="{y - size - 3}" '
        f'width="{wmax}" height="{len(lines)*(size+2)+5}" rx="3" fill="#ffffff" opacity="0.9"/>')
    for i, l in enumerate(lines):
        text(x, y + i * (size + 2), l, size=size, fill=fill, anchor=anchor)

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
add("<defs>")
for c in (RED, BLUE, GREEN, AMBER, GREY, FAINT):
    cid = c.lstrip("#")
    add(f'<marker id="a-{cid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" '
        f'markerHeight="6.5" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{c}"/></marker>')
add("</defs>")

text(W/2, 46, "How the replication TokenProvider works", size=23, weight="bold", anchor="middle")
text(W/2, 74, "temporal.WithTokenProvider is a Go server option, not a config key — which is why this stack compiles its own server binary.",
     size=12.5, fill=MUTED, anchor="middle")

# ============================================================ PHASE 1: boot
PX, PY, PW, PH = 40, 110, 560, 700
panel(PX, PY, PW, PH, BLUE, "#f7fafd", rx=16, sw=2.0)
text(PX + 24, PY + 32, "1 · Boot", size=15, weight="bold", fill=BLUE)
text(PX + 120, PY + 32, "wiring the plugin in — server/main.go", size=10, fill=MUTED)

step(1, PX+24, PY+52, PW-48, 96, "Read the environment", accent=BLUE, stroke=BLUE,
     body=["newOIDCTokenProviderFromEnv(logger)"],
     mono=["TEMPORAL_XDC_OIDC_TOKEN_URL      (required)",
           "TEMPORAL_XDC_OIDC_CLIENT_ID / _CLIENT_SECRET",
           "…_SCOPE  …_AUDIENCE  …_REFRESH_SKEW (30s)"])

step(2, PX+24, PY+164, PW-48, 74, "No token URL → no provider", accent=BLUE, stroke=FAINT,
     body=["Returns a nil provider, and main.go omits the option",
           "entirely. Passing a nil-valued concrete type would still",
           "look non-nil to the server and break every outbound RPC."])

step(3, PX+24, PY+254, PW-48, 62, "Hand it to the server", accent=BLUE, stroke=BLUE, sw=1.9,
     body=["temporal.NewServer( …, temporal.WithTokenProvider(tp) )"],
     mono=["→ auth.TokenProvider, consumed by rpc.RPCFactory"])

# boot guardrails
GX, GY, GW, GH = PX+24, PY+340, PW-48, 176
panel(GX, GY, GW, GH, RED, "#fdf2f2", rx=10, sw=1.8)
text(GX + 14, GY + 24, "Boot-time guardrails", size=11.5, weight="bold", fill=RED_DK)
text(GX + 14, GY + 41, "temporal/fx.go refuses to start rather than replicate insecurely:",
     size=9.2, fill=MUTED)
text(GX + 14, GY + 62, "remoteClusterAuth.require = true, but no provider", size=9.6, weight="bold", fill=RED_DK)
for i, ln in enumerate(['"…require is true but no TokenProvider is',
                        ' configured: use WithTokenProvider"']):
    text(GX + 14, GY + 77 + i*12, ln, size=8.6, fill=MUTED, family=MONO)
text(GX + 14, GY + 116, "provider set, but no remote-cluster TLS", size=9.6, weight="bold", fill=RED_DK)
for i, ln in enumerate(['"…no remote-cluster TLS is configured:',
                        ' supply global.tls.remoteClusters"']):
    text(GX + 14, GY + 131 + i*12, ln, size=8.6, fill=MUTED, family=MONO)
text(GX + 14, GY + 166, "A stock temporalio/server image therefore fails fast here.",
     size=9, fill=RED_DK)

step(None, PX+24, PY+536, PW-48, 60, "Result", stroke=BLUE, fill="#eaf1f9",
     body=["The provider is now held by RPCFactory, which builds every",
           "connection this cluster opens to a remote cluster."])

arrow([(PX+PW/2, PY+148), (PX+PW/2, PY+164)], BLUE)
arrow([(PX+PW/2, PY+238), (PX+PW/2, PY+254)], BLUE)
arrow([(PX+PW/2, PY+316), (PX+PW/2, PY+340)], BLUE)
arrow([(PX+PW/2, PY+516), (PX+PW/2, PY+536)], BLUE)

# ================================================= PHASE 2: per-RPC hot path
QX, QY, QW, QH = 640, 110, 640, 860
panel(QX, QY, QW, QH, RED, "#fdf7f7", rx=16, sw=2.0)
text(QX + 24, QY + 32, "2 · Every outbound cross-cluster RPC", size=15, weight="bold", fill=RED_DK)
text(QX + 24, QY + 50, "common/rpc — CreateRemoteFrontendGRPCConnection(rpcAddress)", size=9.6, fill=MUTED)

step(4, QX+24, QY+66, QW-48, 88, "Pick the remote's TLS config", accent=RED, stroke=RED,
     body=["Keyed by the peer's host name — not its cluster name."],
     mono=["global.tls.remoteClusters[\"temporal-b\"]",
           "rootCaFiles present ⇒ TLS enabled for this remote"])

step(5, QX+24, QY+170, QW-48, 80, "Attach per-RPC credentials", accent=RED, stroke=RED,
     body=["auth.NewTokenCredentials(authHeaderName, fetch)"],
     mono=["grpc.WithPerRPCCredentials(creds)",
           "RequireTransportSecurity() = true  ⇒ TLS mandatory"])

step(6, QX+24, QY+266, QW-48, 74, "gRPC calls GetRequestMetadata", accent=RED, stroke=RED,
     body=["On every single RPC. TokenCredentials caches nothing —",
           "the provider owns the whole token lifecycle."],
     mono=["fetch(ctx) → tokenProvider.GetToken(ctx, rpcAddress)"])

# --- provider internals
IX, IY, IW, IH = QX+24, QY+362, QW-48, 300
panel(IX, IY, IW, IH, RED, "#ffffff", rx=10, sw=1.9)
text(IX + 14, IY + 24, "Inside GetToken", size=12, weight="bold", fill=RED_DK)
text(IX + 132, IY + 24, "server/tokenprovider.go — mutex-guarded", size=9.2, fill=MUTED)

panel(IX+16, IY+38, IW-32, 52, GREEN, "#f2f8f2", rx=8, sw=1.5)
text(IX+28, IY+58, "Cached and still fresh?", size=10.2, weight="bold", fill=GRN_DK)
text(IX+28, IY+74, "now < expires − refreshSkew   →   return the cached token", size=9, fill=MUTED, family=MONO)

panel(IX+16, IY+100, IW-32, 56, AMBER, "#fff8ec", rx=8, sw=1.5)
text(IX+28, IY+120, "Another goroutine already fetching?", size=10.2, weight="bold", fill=AMB_DK)
text(IX+28, IY+136, "Wait on it, then re-check — replication opens many streams", size=9, fill=MUTED)
text(IX+28, IY+149, "at once, and this collapses them into one token request.", size=9, fill=MUTED)

panel(IX+16, IY+166, IW-32, 118, RED, "#fdf2f2", rx=8, sw=1.5)
text(IX+28, IY+186, "Otherwise mint a new one", size=10.2, weight="bold", fill=RED_DK)
text(IX+28, IY+202, "POST to the token endpoint:", size=9, fill=MUTED)
for i, ln in enumerate(["grant_type=client_credentials",
                        "client_id / client_secret  (+ scope, audience)"]):
    text(IX+28, IY+216+i*12, ln, size=8.6, fill=MUTED, family=MONO)
text(IX+28, IY+252, "Store access_token and expires_in.", size=9, fill=MUTED)
text(IX+28, IY+266, "expires_in missing or ≤ 0 → assume 1 minute: the worst case", size=8.8, fill=MUTED)
text(IX+28, IY+277, "is an extra token request, not a rejected RPC.", size=8.8, fill=MUTED)

step(7, QX+24, QY+676, QW-48, 76, "Empty token + require = true", accent=RED, stroke=RED,
     body=["The RPC is failed rather than sent bare:"],
     mono=["codes.Unauthenticated, \"no auth token available",
           " for outbound remote-cluster RPC\""])

step(8, QX+24, QY+768, QW-48, 64, "Header goes on the wire", accent=RED, stroke=RED, sw=1.9,
     body=[],
     mono=["authorization: Bearer <JWT>", "(header name overridable: global.authorization.authHeaderName)"])

for a, b in ((154, 170), (250, 266), (340, 362), (662, 676), (752, 768)):
    arrow([(QX+QW/2, QY+a), (QX+QW/2, QY+b)], RED)

# ============================================== Keycloak + receiving cluster
KX, KY, KW, KH = 1320, 300, 600, 190
panel(KX, KY, KW, KH, AMBER, "#fff8ec", rx=14, sw=2.0)
text(KX + 22, KY + 30, "Keycloak", size=14, weight="bold", fill=AMB_DK)
text(KX + 110, KY + 30, "realm temporal · :9080", size=9.6, fill=MUTED)
text(KX + 22, KY + 54, "temporal-replication — a service account, no user behind it.", size=9.6, fill=MUTED)
text(KX + 22, KY + 72, "Returns an access token carrying the one claim that matters:", size=9.6, fill=MUTED)
panel(KX+22, KY+84, KW-44, 46, "#d19a2e", "#fdf0d5", rx=8, sw=1.4)
text(KX+34, KY+104, '"permissions": ["temporal-system:admin"]', size=10, fill=AMB_DK, family=MONO)
text(KX+34, KY+120, 'temporal-system is the reserved cluster-wide scope', size=8.6, fill=MUTED)
text(KX + 22, KY + 152, "Anything less and the peer accepts the connection, validates the", size=9, fill=MUTED)
text(KX + 22, KY + 165, "signature, then denies every replication call — a silent stall.", size=9, fill=MUTED)

RX, RY, RW, RH = 1320, 560, 600, 320
panel(RX, RY, RW, RH, GREEN, "#f4faf4", rx=16, sw=2.0)
text(RX + 24, RY + 32, "3 · The receiving cluster", size=15, weight="bold", fill=GRN_DK)
text(RX + 24, RY + 50, "public frontend :7233 — the only listener that reads tokens", size=9.6, fill=MUTED)

step(9, RX+24, RY+66, RW-48, 74, "Default claim mapper", accent=GREEN, stroke=GREEN,
     body=["Verifies the signature against Keycloak's JWKS,", "then reads the permissions claim."],
     mono=["temporal-system:admin → Claims.System = RoleAdmin"])

step(10, RX+24, RY+156, RW-48, 68, "Default authorizer", accent=GREEN, stroke=GREEN,
     body=["AdminService APIs require RoleAdmin."],
     mono=["StreamWorkflowReplicationMessages → allowed"])

panel(RX+24, RY+240, RW-48, 60, "#b07b7b", "#f6ecec", rx=10, sw=1.5, dash="5 3")
text(RX+38, RY+260, "Why not the internal frontend?", size=10.2, weight="bold", fill="#8a5a5a")
text(RX+38, RY+276, "It hardcodes a claim mapper that grants system admin to every", size=9, fill=MUTED)
text(RX+38, RY+289, "caller — a JWT there would be decorative, never checked.", size=9, fill=MUTED)

arrow([(RX+RW/2, RY+140), (RX+RW/2, RY+156)], GREEN)

# ---- cross-phase arrows
arrow([(PX+PW, PY+400), (QX, PY+400)], BLUE, sw=2.2)
elabel((PX+PW+QX)/2, PY+392, ["provider"], BLUE_DK)

arrow([(IX+IW, 520), (1400, 520), (1400, KY+KH)], AMBER, sw=2.0)
elabel(1330, 512, ["POST /token"], AMB_DK)

arrow([(1600, KY+KH), (1600, 547), (IX+IW, 547)], AMBER, sw=2.0, dash="4 3")
elabel(1420, 541, ["access_token, expires_in"], AMB_DK)

arrow([(QX+QW, QY+800), (RX+RW/2, QY+800), (RX+RW/2, RY+RH)], RED, sw=2.6)
elabel(1520, QY+792, ["gRPC over TLS  ·  authorization: Bearer <JWT>"], RED_DK, size=9.4)

# ---------------------------------------------------------------- footnote
text(40, H-28, "Every claim above is taken from go.temporal.io/server v1.32.0-160.1 "
               "(common/rpc/auth, common/rpc/rpc.go, temporal/fx.go) and server/tokenprovider.go.",
     size=9.4, fill=FAINT)

add("</svg>")

import pathlib
p = pathlib.Path(__file__).with_name("tokenprovider.svg")
p.write_text("\n".join(out), encoding="utf-8")
print(f"wrote {p} ({p.stat().st_size} bytes)")
