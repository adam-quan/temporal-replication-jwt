#!/usr/bin/env python3
"""Generates docs/architecture.svg - the architecture diagram for this stack.

Laid out by hand rather than by a graph tool: the interesting relationships here
are geometric (two mirrored clusters with a replication link between them, one
identity provider underneath both), and every auto-layout attempt buried that
under crossing edges.

Run via ./scripts/render-diagram.sh, which also produces the PNG.
"""

W, H = 1900, 1030

# ---------------------------------------------------------------- palette
INK        = "#1f2933"
MUTED      = "#5b6672"
FAINT      = "#8a94a3"
RED        = "#b3403f"   # replication - JWT from the TokenProvider
RED_DK     = "#8c2f2e"
BLUE       = "#3f6fae"   # cluster-a, and client traffic into it
BLUE_DK    = "#2f5487"
GREEN      = "#3f8a3f"   # cluster-b, and client traffic into it
GREEN_DK   = "#2f6b2f"
AMBER      = "#d18b1f"   # token issuance / verification
AMBER_DK   = "#9a6510"
ROSE       = "#b07b7b"   # no credential checked
GREY       = "#8a94a3"

FONT = "DejaVu Sans, Helvetica, Arial, sans-serif"
MONO = "DejaVu Sans Mono, Menlo, monospace"

out = []
def add(s): out.append(s)

def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def panel(x, y, w, h, stroke, fill, rx=14, sw=2.0, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

def text(x, y, t, size=11, fill=INK, weight="normal", anchor="start",
         family=FONT, opacity=1.0):
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'fill="{fill}" font-weight="{weight}" text-anchor="{anchor}" '
        f'opacity="{opacity}">{esc(t)}</text>')

def box(x, y, w, h, title, lines=(), stroke=FAINT, fill="#ffffff", rx=9,
        sw=1.3, dash=None, title_size=11.5, line_size=9, title_fill=INK,
        line_fill=MUTED, mono_lines=()):
    """A labelled node. `lines` render under the title; `mono_lines` after them."""
    panel(x, y, w, h, stroke, fill, rx=rx, sw=sw, dash=dash)
    cx = x + w / 2
    n = len(lines) + len(mono_lines)
    ty = y + h / 2 - (n * (line_size + 2.5)) / 2 + title_size / 2 + 1
    text(cx, ty, title, size=title_size, weight="bold", anchor="middle", fill=title_fill)
    yy = ty
    for ln in lines:
        yy += line_size + 2.5
        text(cx, yy, ln, size=line_size, fill=line_fill, anchor="middle")
    for ln in mono_lines:
        yy += line_size + 2.5
        text(cx, yy, ln, size=line_size - 0.5, fill=line_fill, anchor="middle", family=MONO)

def path(pts, stroke, sw=1.5, dash=None, marker="end", opacity=1.0):
    """Orthogonal polyline through pts, with an arrowhead at one or both ends."""
    d = "M " + " L ".join(f"{px} {py}" for px, py in pts)
    da = f' stroke-dasharray="{dash}"' if dash else ""
    m = ""
    if marker in ("end", "both"):
        m += f' marker-end="url(#arrow-{stroke.lstrip("#")})"'
    if marker in ("start", "both"):
        m += f' marker-start="url(#arrowrev-{stroke.lstrip("#")})"'
    add(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw}" '
        f'stroke-linejoin="round" stroke-linecap="round"{da}{m} opacity="{opacity}"/>')

def elabel(x, y, lines, fill, size=8.6, anchor="middle", bg=True):
    """Edge label with a soft background so it stays readable over a line."""
    wmax = max(len(l) for l in lines) * size * 0.55 + 8
    hgt = len(lines) * (size + 2) + 4
    if bg:
        add(f'<rect x="{x - wmax/2 if anchor=="middle" else x - 4}" y="{y - size - 2}" '
            f'width="{wmax}" height="{hgt}" rx="3" fill="#ffffff" opacity="0.86"/>')
    for i, l in enumerate(lines):
        text(x, y + i * (size + 2), l, size=size, fill=fill, anchor=anchor)

# ================================================================= header
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

# arrowheads, one per colour
add("<defs>")
for c in (RED, BLUE, GREEN, AMBER, ROSE, GREY, FAINT):
    cid = c.lstrip("#")
    add(f'<marker id="arrow-{cid}" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{c}"/></marker>')
    add(f'<marker id="arrowrev-{cid}" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="6.5" markerHeight="6.5" orient="auto">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{c}"/></marker>')
add("</defs>")

text(W/2, 46, "Temporal cross-cluster replication secured with Keycloak JWTs",
     size=22, weight="bold", anchor="middle")
text(W/2, 74, "Two clusters, one realm. TLS on every connection; no client certificates — the JWT identifies the caller.",
     size=12.5, fill=MUTED, anchor="middle")

# ================================================================= actors
box(600, 100, 200, 72, "Browser", ["operator"], stroke="#7d8794",
    fill="#eef2f7", rx=30)
box(1100, 100, 200, 72, "Temporal CLI / SDK", ["admin-tools container"],
    stroke="#7d8794", fill="#eef2f7", rx=30)

# ================================================================ legend
LX, LY, LW, LH = 1500, 44, 370, 142
panel(LX, LY, LW, LH, "#c2c7d0", "#fbfbfc", rx=10, sw=1.3)
text(LX + 16, LY + 24, "What identifies the caller", size=11.5, weight="bold")
for i, (c, lbl) in enumerate([
        (RED,   "replication — JWT from the TokenProvider"),
        (BLUE,  "client traffic — JWT from a person or app"),
        (AMBER, "token issuance / verification (HTTP)"),
        (ROSE,  "no credential checked (internal frontend)"),
        (GREY,  "datastore / metrics")]):
    yy = LY + 46 + i * 21
    add(f'<line x1="{LX+18}" y1="{yy}" x2="{LX+52}" y2="{yy}" stroke="{c}" stroke-width="3.4"/>')
    text(LX + 62, yy + 4, lbl, size=9.6, fill=MUTED)

# ============================================================== clusters
CTOP, CBOT = 230, 755
AX, AW = 40, 780      # cluster-a panel
BX, BW = 1080, 780    # cluster-b panel

def cluster(px, pw, name, sub, accent, tint, srv_tint, inner_left):
    """Draws one cluster panel. inner_left=True puts the frontend on the panel's
    left edge (cluster-b), False on its right edge (cluster-a) — so the two
    frontends always face each other across the corridor."""
    panel(px, CTOP, pw, CBOT - CTOP, accent, tint, rx=16, sw=2.2)
    cx = px + pw / 2
    text(cx, CTOP + 28, name, size=15, weight="bold", anchor="middle", fill=accent)
    text(cx, CTOP + 45, sub, size=9.5, anchor="middle", fill=MUTED)

    ui_x = px + 30 if not inner_left else px + pw - 260
    box(ui_x, 275, 230, 60, "Web UI", [sub_ui], stroke=accent,
        fill=srv_tint, sw=1.5)

    sp_x, sp_w = px + 30, pw - 60
    panel(sp_x, 355, sp_w, 265, accent, "#ffffff", rx=12, sw=1.4)
    text(cx, 377, "Temporal Server", size=11, weight="bold", anchor="middle", fill=MUTED)

    if inner_left:
        fe_x, other_x = px + 50, px + 390
    else:
        fe_x, other_x = px + 430, px + 50
    return fe_x, other_x, ui_x

# ---- cluster-a
sub_ui = "temporal-ui · :8080"
fe_a_x, out_a_x, ui_a_x = cluster(AX, AW, "cluster-a",
                                  "failover version 1 · master of itself",
                                  BLUE, "#eff5fb", "#dce9f7", inner_left=False)
box(out_a_x, 395, 340, 80, "internal-frontend :7236",
    ["TLS — grants system admin", "to every caller, unconditionally"],
    stroke=ROSE, fill="#f6ecec", sw=1.4, dash="5 3")
box(fe_a_x, 395, 300, 80, "frontend :7233",
    ["TLS — default claim mapper", "+ authorizer — JWT required"],
    stroke=BLUE, fill="#cfe0f4", sw=1.9)
box(out_a_x, 495, 340, 75, "history · matching · worker",
    [":7234 · :7235 — internode TLS"], stroke=BLUE, fill="#f4f7fb", sw=1.3)
box(fe_a_x, 495, 300, 75, "TokenProvider (plugin)",
    ["temporal.WithTokenProvider"], stroke=RED, fill="#f7dcdc", sw=1.9)
box(AX + 30, 650, 350, 65, "PostgreSQL",
    [":5432 — history, cluster_metadata"], stroke=GREY, fill="#eef1f5")
box(AX + 410, 650, 340, 65, "Elasticsearch", [":9200 — visibility"],
    stroke=GREY, fill="#eef1f5")

# ---- cluster-b
sub_ui = "temporal-b-ui · :8081"
fe_b_x, out_b_x, ui_b_x = cluster(BX, BW, "cluster-b",
                                  "failover version 2 · master of itself",
                                  GREEN, "#f1f7f1", "#dcefdc", inner_left=True)
box(fe_b_x, 395, 300, 80, "frontend :7233",
    ["TLS — default claim mapper", "+ authorizer — JWT required"],
    stroke=GREEN, fill="#d3ecd3", sw=1.9)
box(out_b_x, 395, 340, 80, "internal-frontend :7236",
    ["TLS — grants system admin", "to every caller, unconditionally"],
    stroke=ROSE, fill="#f6ecec", sw=1.4, dash="5 3")
box(fe_b_x, 495, 300, 75, "TokenProvider (plugin)",
    ["temporal.WithTokenProvider"], stroke=RED, fill="#f7dcdc", sw=1.9)
box(out_b_x, 495, 340, 75, "history · matching · worker",
    [":7234 · :7235 — internode TLS"], stroke=GREEN, fill="#f5faf5", sw=1.3)
box(BX + 30, 650, 340, 65, "Elasticsearch", [":9200 — visibility"],
    stroke=GREY, fill="#eef1f5")
box(BX + 400, 650, 350, 65, "PostgreSQL",
    [":5432 — history, cluster_metadata"], stroke=GREY, fill="#eef1f5")

text(AX + 30 + 175, 742, "host :7233 → localhost:7233", size=9, fill=FAINT, anchor="middle")
text(BX + 400 + 175, 742, "host :7233 → localhost:8233", size=9, fill=FAINT, anchor="middle")

# ======================================================= replication link
FE_A_R, FE_B_L, FE_MID = fe_a_x + 300, fe_b_x, 435
path([(FE_A_R + 60, FE_MID), (FE_A_R, FE_MID)], RED, sw=3.2)
path([(FE_B_L - 60, FE_MID), (FE_B_L, FE_MID)], RED, sw=3.2)
panel(830, 380, 240, 112, RED, "#fdf2f2", rx=10, sw=2.0)
text(950, 402, "cross-cluster", size=11, weight="bold", anchor="middle", fill=RED_DK)
text(950, 417, "replication", size=11, weight="bold", anchor="middle", fill=RED_DK)
text(950, 437, "gRPC over TLS", size=9.5, anchor="middle", fill=RED_DK)
text(950, 455, "authorization:", size=8.6, anchor="middle", fill=RED_DK, family=MONO)
text(950, 466, "Bearer <JWT>", size=8.6, anchor="middle", fill=RED_DK, family=MONO)
text(950, 483, "bidirectional", size=8.6, anchor="middle", fill=FAINT)

# TokenProvider feeds each frontend's outbound dial
path([(fe_a_x + 150, 495), (fe_a_x + 150, 477)], RED, sw=1.6, dash="4 3")
elabel(fe_a_x + 150, 490, ["token for outbound RPC"], RED_DK, size=8.4)
path([(fe_b_x + 150, 495), (fe_b_x + 150, 477)], RED, sw=1.6, dash="4 3")
elabel(fe_b_x + 150, 490, ["token for outbound RPC"], RED_DK, size=8.4)

# ========================================================= client traffic
path([(640, 172), (640, 196), (185, 196), (185, 275)], BLUE, sw=1.7)
elabel(300, 190, ["HTTP :8080"], BLUE_DK)
path([(760, 172), (760, 205), (1715, 205), (1715, 275)], GREEN, sw=1.7)
elabel(1180, 199, ["HTTP :8081"], GREEN_DK)

path([(300, 305), (560, 305), (560, 395)], BLUE, sw=2.1)
elabel(430, 299, ["gRPC/TLS + JWT"], BLUE_DK)
path([(1600, 305), (1350, 305), (1350, 395)], GREEN, sw=2.1)
elabel(1470, 299, ["gRPC/TLS + JWT"], GREEN_DK)

path([(1140, 172), (1140, 222), (680, 222), (680, 395)], BLUE, sw=2.1)
elabel(880, 216, ["gRPC/TLS + JWT"], BLUE_DK)
path([(1260, 172), (1260, 252), (1230, 252), (1230, 395)], GREEN, sw=2.1)
elabel(1330, 246, ["gRPC/TLS + JWT"], GREEN_DK)

# ================================================= intra-cluster + stores
path([(out_a_x + 170, 495), (out_a_x + 170, 477)], ROSE, sw=1.4, dash="5 3")
elabel(out_a_x + 170, 490, ["system workers — no credential"], "#8a5a5a", size=8.4)
path([(out_b_x + 170, 495), (out_b_x + 170, 477)], ROSE, sw=1.4, dash="5 3")
elabel(out_b_x + 170, 490, ["system workers — no credential"], "#8a5a5a", size=8.4)

path([(fe_a_x, 455), (fe_a_x - 20, 455), (fe_a_x - 20, 530), (out_a_x + 340, 530)],
     FAINT, sw=1.3)
path([(fe_b_x + 300, 455), (fe_b_x + 320, 455), (fe_b_x + 320, 530), (out_b_x, 530)],
     FAINT, sw=1.3)

path([(AX + 200, 570), (AX + 200, 650)], GREY, sw=1.3)
elabel(AX + 200, 618, ["TCP 5432"], "#6b7280")
path([(AX + 330, 570), (AX + 330, 632), (AX + 580, 632), (AX + 580, 650)], GREY, sw=1.3)
elabel(AX + 580, 618, ["HTTP 9200"], "#6b7280")
path([(BX + 580, 570), (BX + 580, 650)], GREY, sw=1.3)
elabel(BX + 580, 618, ["TCP 5432"], "#6b7280")
path([(BX + 450, 570), (BX + 450, 632), (BX + 200, 632), (BX + 200, 650)], GREY, sw=1.3)
elabel(BX + 200, 618, ["HTTP 9200"], "#6b7280")

# ========================================================= observability
box(845, 560, 210, 56, "Prometheus", [":9090"], stroke=GREY, fill="#eceef2")
box(845, 640, 210, 56, "Grafana", [":8085"], stroke=GREY, fill="#eceef2")
path([(950, 640), (950, 616)], GREY, sw=1.3)
path([(845, 588), (425, 588), (425, 570)], "#7a9e7a", sw=1.3, dash="2 3")
elabel(660, 582, ["scrape :8002"], "#4f6b4f")
path([(1055, 588), (1475, 588), (1475, 570)], "#7a9e7a", sw=1.3, dash="2 3")
elabel(1240, 582, ["scrape :8003"], "#4f6b4f")

# ============================================================== Keycloak
KX, KY, KW, KH = 440, 800, 940, 178
panel(KX, KY, KW, KH, AMBER, "#fff8ec", rx=16, sw=2.2)
text(KX + 24, KY + 30, "Keycloak", size=15, weight="bold", fill=AMBER_DK)
text(KX + 118, KY + 30, "realm  temporal  ·  :9080  —  one issuer for both clusters",
     size=10, fill=MUTED)
box(KX + 20, KY + 46, 300, 116, "temporal-app",
    ["people, CLI, SDK, Web UI"], stroke="#d19a2e", fill="#fdf0d5",
    mono_lines=["permissions:", "[temporal-system:admin]", "aud:[temporal-app, account]"])
box(KX + 340, KY + 46, 300, 116, "temporal-replication",
    ["service account", "client_credentials grant"], stroke="#d19a2e", fill="#fdf0d5",
    mono_lines=["permissions:", "[temporal-system:admin]"])
box(KX + 660, KY + 46, 260, 116, "JWKS",
    ["public keys the frontends", "verify signatures with"], stroke="#d19a2e",
    fill="#fdf0d5", mono_lines=["/openid-connect/certs"])

# each server: TokenProvider mints, frontend verifies - one lane per cluster
path([(435, 620), (435, 782), (KX + 130, 782), (KX + 130, KY)], AMBER, sw=1.7)
elabel(600, 776, ["POST /token (client_credentials)  ·  GET JWKS"], AMBER_DK, size=8.6)
path([(1465, 620), (1465, 782), (KX + 810, 782), (KX + 810, KY)], AMBER, sw=1.7)
elabel(1300, 776, ["POST /token (client_credentials)  ·  GET JWKS"], AMBER_DK, size=8.6)

# browser front-channel, and each UI's back-channel exchange
path([(600, 136), (20, 136), (20, 866), (KX, 866)], AMBER, sw=1.7)
elabel(150, 858, ["OIDC login — front-channel via localhost:9080"], AMBER_DK)
path([(ui_a_x, 305), (34, 305), (34, 906), (KX, 906)], AMBER, sw=1.5, dash="2 3")
elabel(190, 898, ["discovery + code→token (back-channel)"], AMBER_DK)
path([(ui_b_x + 230, 305), (1880, 305), (1880, 886), (KX + KW, 886)], AMBER, sw=1.5, dash="2 3")
elabel(1640, 878, ["discovery + code→token"], AMBER_DK)

add("</svg>")

import pathlib
p = pathlib.Path(__file__).with_name("architecture.svg")
p.write_text("\n".join(out), encoding="utf-8")
print(f"wrote {p} ({p.stat().st_size} bytes)")
