#!/usr/bin/env python3
"""Generates docs/tokenprovider-context.svg - the TokenProvider in context.

A component view rather than a sequence: what constructs the plugin, what
contract it satisfies, what consumes it, what it depends on, and what it
deliberately has nothing to do with. docs/tokenprovider.py covers the
step-by-step mechanism instead.

Run via ./scripts/render-diagram.sh.
"""

W, H = 1900, 1020

INK, MUTED, FAINT = "#1f2933", "#5b6672", "#8a94a3"
RED, RED_DK   = "#b3403f", "#8c2f2e"
BLUE, BLUE_DK = "#3f6fae", "#2f5487"
GREEN, GRN_DK = "#3f8a3f", "#2f6b2f"
AMBER, AMB_DK = "#d18b1f", "#9a6510"
PURP, PURP_DK = "#7a5ea8", "#5c4682"
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

def zone(x, y, w, h, label, stroke, fill):
    panel(x, y, w, h, stroke, fill, rx=16, sw=1.8, dash="7 4")
    text(x + 16, y + 22, label, size=10.5, weight="bold", fill=stroke)

def node(x, y, w, h, title, body=(), mono=(), stroke=FAINT, fill="#ffffff",
         sw=1.4, title_size=11.5, dash=None):
    panel(x, y, w, h, stroke, fill, rx=9, sw=sw, dash=dash)
    text(x + 14, y + 24, title, size=title_size, weight="bold")
    yy = y + 24
    for ln in body:
        yy += 14
        text(x + 14, yy, ln, size=9.4, fill=MUTED)
    for ln in mono:
        yy += 13
        text(x + 14, yy, ln, size=8.8, fill=MUTED, family=MONO)

def arrow(pts, stroke, sw=2.0, dash=None):
    d = "M " + " L ".join(f"{px} {py}" for px, py in pts)
    da = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw}" '
        f'stroke-linejoin="round" stroke-linecap="round"{da} '
        f'marker-end="url(#a-{stroke.lstrip("#")})"/>')

def rel(x, y, verb, detail=None, fill=INK, anchor="middle"):
    """The name of a relationship, set on a white pad so it reads over a line."""
    lines = [verb] + ([detail] if detail else [])
    wmax = max(len(l) for l in lines) * 5.6 + 14
    add(f'<rect x="{x - wmax/2 if anchor=="middle" else x - 6}" y="{y - 13}" '
        f'width="{wmax}" height="{len(lines)*13 + 7}" rx="4" fill="#ffffff" opacity="0.93"/>')
    text(x, y, verb, size=10, weight="bold", fill=fill, anchor=anchor)
    if detail:
        text(x, y + 13, detail, size=8.8, fill=MUTED, anchor=anchor, family=MONO)

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
add("<defs>")
for c in (RED, BLUE, GREEN, AMBER, PURP, GREY, FAINT):
    cid = c.lstrip("#")
    add(f'<marker id="a-{cid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" '
        f'markerHeight="6.5" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{c}"/></marker>')
add("</defs>")

text(W/2, 46, "The TokenProvider plugin in context", size=23, weight="bold", anchor="middle")
text(W/2, 74, "One object, five relationships: something builds it, an interface constrains it, "
              "the RPC layer consumes it, an IdP supplies it, and a peer cluster trusts what it produces.",
     size=12.5, fill=MUTED, anchor="middle")

# ============================================================== the hub
HX, HY, HW, HH = 660, 415, 560, 230
panel(HX, HY, HW, HH, RED, "#fdf2f2", rx=14, sw=3.0)
text(HX + HW/2, HY + 34, "TokenProvider", size=19, weight="bold", fill=RED_DK, anchor="middle")
text(HX + HW/2, HY + 53, "server/tokenprovider.go — compiled into the server binary",
     size=9.6, fill=MUTED, anchor="middle")

panel(HX + 24, HY + 66, HW - 48, 46, RED, "#ffffff", rx=8, sw=1.4)
text(HX + HW/2, HY + 85, "implements  auth.TokenProvider", size=10.5, weight="bold",
     fill=RED_DK, anchor="middle")
text(HX + HW/2, HY + 101, "GetToken(ctx, rpcAddress) (string, error)", size=9.2,
     fill=MUTED, anchor="middle", family=MONO)

text(HX + 28, HY + 136, "It owns the whole token lifecycle:", size=9.6, fill=MUTED)
for i, ln in enumerate(["caches until refreshSkew before expiry",
                        "collapses concurrent refreshes into one request",
                        "one instance shared by every remote cluster"]):
    text(HX + 40, HY + 154 + i * 15, "•  " + ln, size=9.4, fill=MUTED)
text(HX + 28, HY + 209, "rpcAddress is passed but unused — the peers share one identity.",
     size=8.8, fill=FAINT)

# ====================================================== 1. built by (top)
zone(660, 130, 560, 235, "BUILT BY — the custom server binary", BLUE, "#f7fafd")
node(686, 162, 508, 78, "server/main.go", stroke=BLUE, fill="#ffffff", sw=1.6,
     body=["Upstream cmd/server/main.go plus one option."],
     mono=["tp, err := newOIDCTokenProviderFromEnv(logger)",
           "if tp != nil { opts = append(opts, WithTokenProvider(tp)) }"])
node(686, 254, 508, 96, "temporal.NewServer  →  fx graph", stroke=BLUE, fill="#ffffff", sw=1.6,
     body=["Refuses to boot on a contradictory configuration:"],
     mono=["require=true + no provider   → error",
           "provider + no remoteClusters → error"])
arrow([(940, 350), (940, HY)], BLUE, sw=2.4)
rel(940, 385, "provides", "auth.TokenProvider", BLUE_DK)

# =================================================== 2. configured by (left)
zone(50, 130, 540, 340, "CONFIGURED BY", PURP, "#faf8fd")
node(76, 162, 488, 116, "Environment  ·  docker-compose.yml",
     stroke=PURP, fill="#ffffff", sw=1.5,
     body=["Absent TOKEN_URL ⇒ no provider at all."],
     mono=["TEMPORAL_XDC_OIDC_TOKEN_URL", "TEMPORAL_XDC_OIDC_CLIENT_ID",
           "TEMPORAL_XDC_OIDC_CLIENT_SECRET", "…_SCOPE  …_AUDIENCE  …_REFRESH_SKEW"])
node(76, 292, 488, 152, "Server config  ·  config.yaml",
     stroke=PURP, fill="#ffffff", sw=1.5,
     body=["Two keys the plugin cannot work without —",
           "neither of them names it:"],
     mono=["global.authorization.remoteClusterAuth.require",
           "  ⇒ an empty token fails the RPC",
           "global.tls.remoteClusters.<peer-host>.rootCaFiles",
           "  ⇒ marks the remote as TLS-enabled"])
arrow([(590, 300), (HX, 300), (HX, HY + 20)], PURP, sw=2.2)
rel(628, 292, "shapes", None, PURP_DK, anchor="start")

# ================================================== 3. consumed by (right)
zone(1290, 130, 560, 400, "CONSUMED BY — the RPC layer", GREEN, "#f4faf4")
node(1316, 162, 508, 92, "rpc.RPCFactory", stroke=GREEN, fill="#ffffff", sw=1.6,
     body=["Holds the provider and builds every connection", "this cluster opens to a remote cluster."],
     mono=["CreateRemoteFrontendGRPCConnection(rpcAddress)"])
node(1316, 268, 508, 108, "auth.TokenCredentials", stroke=GREEN, fill="#ffffff", sw=1.6,
     body=["A gRPC PerRPCCredentials wrapper. Caches nothing —", "that is the provider's job."],
     mono=["RequireTransportSecurity() = true", "  ⇒ a plaintext dial can carry no token"])
node(1316, 390, 508, 116, "gRPC ClientConn → peer frontend",
     stroke=GREEN, fill="#ffffff", sw=1.6,
     body=["GetRequestMetadata runs on every single RPC,", "so GetToken is on the hot path."],
     mono=["authorization: Bearer <JWT>"])
arrow([(1220, HY + 60), (1290, HY + 60)], GREEN, sw=2.4)
rel(1255, HY + 44, "calls", "per RPC", GRN_DK)

# =================================================== 4. mints from (centre)
zone(660, 720, 560, 250, "MINTS FROM", AMBER, "#fff8ec")
node(686, 752, 508, 190, "Keycloak  ·  temporal-replication",
     stroke=AMBER, fill="#ffffff", sw=1.6,
     body=["A service account — replication has no user behind it,",
           "so the grant is client_credentials.",
           "",
           "The access token carries the one claim the peer's",
           "authorizer looks for:"],
     mono=['permissions: ["temporal-system:admin"]'])
arrow([(HX + 90, HY + HH), (HX + 90, 720)], AMBER, sw=2.2)
rel(HX + 90, 690, "requests", "client_credentials", AMB_DK)
arrow([(HX + 430, 720), (HX + 430, HY + HH)], AMBER, sw=2.2, dash="5 3")
rel(HX + 430, 690, "returns", "access_token, expires_in", AMB_DK)

# ================================================= 5. trusted by (right)
zone(1290, 720, 560, 250, "TRUSTED BY", RED, "#fdf7f7")
node(1316, 752, 508, 190, "The peer cluster's public frontend",
     stroke=RED, fill="#ffffff", sw=1.6,
     body=["Verifies the signature against the same realm's JWKS,",
           "maps permissions onto roles, and admits the stream.",
           "",
           "This is the only listener that reads tokens — which is",
           "why replication is pointed here and not at :7236."],
     mono=["StreamWorkflowReplicationMessages → allowed"])
arrow([(1570, 530), (1570, 720)], RED, sw=2.8)
rel(1570, 620, "carries the token to", "gRPC over TLS", RED_DK)

# ============================================== boundary: what it is not
node(50, 720, 540, 250, "NOT this plugin's job", stroke=FAINT, fill="#fafbfc",
     sw=1.5, dash="6 4", title_size=12,
     body=["Inbound JWT verification — that is jwtKeyProvider plus the",
           "default claim mapper, a separate path with its own config.",
           "",
           "The internal frontend (:7236) — it checks no credential at",
           "all, so no token would ever be consulted there.",
           "",
           "Client traffic from people, the CLI and SDKs — those callers",
           "bring their own tokens; the provider is only ever used for",
           "connections this cluster originates to a peer."])

text(40, H - 26, "Component relationships as wired in this repo; the step-by-step mechanism is in "
                 "docs/tokenprovider.png, and the whole stack in docs/architecture.png.",
     size=9.4, fill=FAINT)

add("</svg>")

import pathlib
p = pathlib.Path(__file__).with_name("tokenprovider-context.svg")
p.write_text("\n".join(out), encoding="utf-8")
print(f"wrote {p} ({p.stat().st_size} bytes)")
