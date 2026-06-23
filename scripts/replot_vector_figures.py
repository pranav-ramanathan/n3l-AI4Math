#!/usr/bin/env python3
"""Regenerate sourced paper figures as vector PDFs.

This deliberately avoids raster tracing. Every generated figure is drawn from
coordinates or CSV data recovered from source artifacts.
"""

from __future__ import annotations

import ast
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "figures"
RESEARCH = ROOT.parent
SCIML_EXPERIMENTS = RESEARCH / "neurIPS" / "NeurIPS_Paper" / "experiments"

SCIML_ALPHA_CSV = SCIML_EXPERIMENTS / "data" / "hyperparam_labels.csv"
SCIML_N18_SOLUTION = (
    SCIML_EXPERIMENTS
    / "solutions"
    / "18"
    / "sol_metal_v3_20260214_110801_traj19.txt"
)
CP_SAT_N10_LOG = (
    SCIML_EXPERIMENTS
    / "baselines"
    / "results"
    / "logs_g2_full_bounded"
    / "cpsat_n10_direct_seed1.log"
)
CP_SAT_N19_SYM_LOG = (
    SCIML_EXPERIMENTS
    / "baselines"
    / "results"
    / "logs_g2_full_bounded"
    / "cpsat_n19_sym_seed1.log"
)

# Fallback source: pranav-ramanathan/N3L_gurobi, results/n_10.txt, main branch.
# The preferred source is the local CP-SAT n=10 log above.
ILP_N10_FALLBACK = [
    (0, 0),
    (0, 9),
    (1, 4),
    (1, 6),
    (2, 5),
    (2, 6),
    (3, 1),
    (3, 2),
    (4, 2),
    (4, 8),
    (5, 1),
    (5, 7),
    (6, 7),
    (6, 8),
    (7, 3),
    (7, 4),
    (8, 3),
    (8, 5),
    (9, 0),
    (9, 9),
]


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PdfCanvas:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height
        self.ops: list[str] = []

    def line_width(self, width: float) -> None:
        self.ops.append(f"{width:.3f} w")

    def stroke_color(self, color: str) -> None:
        r, g, b = hex_to_rgb(color)
        self.ops.append(f"{r:.4f} {g:.4f} {b:.4f} RG")

    def fill_color(self, color: str) -> None:
        r, g, b = hex_to_rgb(color)
        self.ops.append(f"{r:.4f} {g:.4f} {b:.4f} rg")

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.ops.append(f"{x1:.3f} {y1:.3f} m {x2:.3f} {y2:.3f} l S")

    def rect(self, x: float, y: float, w: float, h: float, fill: bool = False) -> None:
        self.ops.append(f"{x:.3f} {y:.3f} {w:.3f} {h:.3f} re {'f' if fill else 'S'}")

    def circle(self, x: float, y: float, r: float, fill: str | None, stroke: str | None, lw: float = 1.0) -> None:
        k = 0.552284749831 * r
        if stroke:
            self.stroke_color(stroke)
        if fill:
            self.fill_color(fill)
        self.line_width(lw)
        self.ops.append(
            " ".join(
                [
                    f"{x + r:.3f} {y:.3f} m",
                    f"{x + r:.3f} {y + k:.3f} {x + k:.3f} {y + r:.3f} {x:.3f} {y + r:.3f} c",
                    f"{x - k:.3f} {y + r:.3f} {x - r:.3f} {y + k:.3f} {x - r:.3f} {y:.3f} c",
                    f"{x - r:.3f} {y - k:.3f} {x - k:.3f} {y - r:.3f} {x:.3f} {y - r:.3f} c",
                    f"{x + k:.3f} {y - r:.3f} {x + r:.3f} {y - k:.3f} {x + r:.3f} {y:.3f} c",
                    "B" if fill and stroke else ("f" if fill else "S"),
                ]
            )
        )

    def polyline(self, points: list[tuple[float, float]], color: str, lw: float = 1.5, dash: str | None = None) -> None:
        if not points:
            return
        self.stroke_color(color)
        self.line_width(lw)
        if dash:
            self.ops.append(f"{dash} 0 d")
        x0, y0 = points[0]
        parts = [f"{x0:.3f} {y0:.3f} m"]
        parts.extend(f"{x:.3f} {y:.3f} l" for x, y in points[1:])
        parts.append("S")
        self.ops.append(" ".join(parts))
        if dash:
            self.ops.append("[] 0 d")

    def text(self, x: float, y: float, text: str, size: float = 10, color: str = "#000000", align: str = "left") -> None:
        self.fill_color(color)
        # Approximate Helvetica text width for simple alignment.
        width = 0.5 * size * len(text)
        if align == "center":
            x -= width / 2
        elif align == "right":
            x -= width
        self.ops.append(f"BT /F1 {size:.2f} Tf {x:.3f} {y:.3f} Td ({pdf_escape(text)}) Tj ET")

    def rotated_text(self, x: float, y: float, text: str, degrees: float, size: float = 10, color: str = "#000000") -> None:
        self.fill_color(color)
        rad = math.radians(degrees)
        c, s = math.cos(rad), math.sin(rad)
        self.ops.append(
            f"BT /F1 {size:.2f} Tf {c:.5f} {s:.5f} {-s:.5f} {c:.5f} {x:.3f} {y:.3f} Tm ({pdf_escape(text)}) Tj ET"
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(self.ops).encode("ascii")

        objects: list[bytes] = []
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width:.3f} {self.height:.3f}] "
            f"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ).encode("ascii")
        objects.append(page)
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objects.append(b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for idx, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out.extend(f"{idx} 0 obj\n".encode("ascii"))
            out.extend(obj)
            out.extend(b"\nendobj\n")
        xref = len(out)
        out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        out.extend(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
        out.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
        )
        path.write_bytes(out)


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def load_cp_sat_n10_points() -> list[tuple[int, int]]:
    if CP_SAT_N10_LOG.exists():
        for line in CP_SAT_N10_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("[("):
                return [tuple(p) for p in ast.literal_eval(line)]
    return ILP_N10_FALLBACK


def load_cp_sat_n19_points() -> list[tuple[int, int]]:
    text = CP_SAT_N19_SYM_LOG.read_text(encoding="utf-8").splitlines()
    for idx, raw in enumerate(text):
        if raw.strip() == "[sym] occupied points in G_n:":
            points = ast.literal_eval(text[idx + 1].strip())
            if len(points) != 38:
                raise ValueError(f"Expected 38 points in {CP_SAT_N19_SYM_LOG}, found {len(points)}")
            return [tuple(p) for p in points]
    raise ValueError(f"Could not parse occupied n=19 points from {CP_SAT_N19_SYM_LOG}")


def load_solution_points(path: Path) -> tuple[int, list[tuple[int, int]]]:
    text = path.read_text(encoding="utf-8")
    n = None
    points: list[tuple[int, int]] = []
    in_coords = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# n="):
            n = int(line.split("=", 1)[1])
        elif line == "# Coordinates (row, col):":
            in_coords = True
        elif in_coords and line.startswith("("):
            row, col = line.strip("()").split(",")
            points.append((int(row) - 1, int(col) - 1))
    if n is None:
        raise ValueError(f"Could not parse n from {path}")
    return n, points


def draw_grid_figure(n: int, points: list[tuple[int, int]], path: Path, fill: str, size: float = 360) -> None:
    margin = 12
    board = size - 2 * margin
    cell = board / n
    canvas = PdfCanvas(size, size)
    canvas.stroke_color("#000000")
    canvas.line_width(0.55 if n > 14 else 0.75)
    for i in range(n + 1):
        pos = margin + i * cell
        canvas.line(margin, pos, margin + board, pos)
        canvas.line(pos, margin, pos, margin + board)
    radius = cell * (0.23 if n > 14 else 0.25)
    for row, col in points:
        x = margin + (col + 0.5) * cell
        y = margin + board - (row + 0.5) * cell
        canvas.circle(x, y, radius, fill=fill, stroke="#000000", lw=0.7 if n > 14 else 0.9)
    canvas.save(path)


def load_alpha_rows(path: Path) -> list[dict[str, float]]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({"n": float(row["n"]), "alpha": float(row["alpha"]), "T": float(row["T"])})
    return rows


def draw_alpha_plot(rows: list[dict[str, float]], path: Path) -> None:
    width, height = 360, 252
    left, right, bottom, top = 52, 50, 42, 20
    plot_w = width - left - right
    plot_h = height - bottom - top
    n_min, n_max = 2, 18
    alpha_min, alpha_max = 0, 20
    t_min, t_max = 0, 40

    def xmap(n: float) -> float:
        return left + (n - n_min) / (n_max - n_min) * plot_w

    def y_alpha(a: float) -> float:
        return bottom + (a - alpha_min) / (alpha_max - alpha_min) * plot_h

    def y_t(t: float) -> float:
        return bottom + (t - t_min) / (t_max - t_min) * plot_h

    canvas = PdfCanvas(width, height)
    # Horizontal grid and axes.
    for yv in [0, 5, 10, 15, 20]:
        y = y_alpha(yv)
        canvas.stroke_color("#e0e0e0")
        canvas.line_width(0.45)
        canvas.line(left, y, left + plot_w, y)
        canvas.fill_color("#000000")
        canvas.text(left - 8, y - 3, str(yv), 8, align="right")
    canvas.stroke_color("#000000")
    canvas.line_width(0.8)
    canvas.line(left, bottom, left + plot_w, bottom)
    canvas.line(left, bottom, left, bottom + plot_h)
    canvas.stroke_color("#aaaaaa")
    canvas.line_width(0.7)
    canvas.line(left + plot_w, bottom, left + plot_w, bottom + plot_h)

    for n in range(2, 19, 2):
        x = xmap(n)
        canvas.stroke_color("#000000")
        canvas.line_width(0.5)
        canvas.line(x, bottom, x, bottom - 3)
        canvas.text(x, bottom - 16, str(n), 8, align="center")
    for tv in [0, 10, 20, 30, 40]:
        y = y_t(tv)
        canvas.stroke_color("#aaaaaa")
        canvas.line_width(0.5)
        canvas.line(left + plot_w, y, left + plot_w + 3, y)
        canvas.text(left + plot_w + 8, y - 3, str(tv), 8, color="#e67e22")

    alpha_pts = [(xmap(r["n"]), y_alpha(r["alpha"])) for r in rows]
    t_pts = [(xmap(r["n"]), y_t(r["T"])) for r in rows]
    canvas.polyline(alpha_pts, "#1f77b4", lw=1.6)
    canvas.polyline(t_pts, "#e67e22", lw=1.3, dash="[4 3]")
    for x, y in alpha_pts:
        canvas.circle(x, y, 2.6, fill="#1f77b4", stroke="#1f77b4", lw=0.5)
    for x, y in t_pts:
        canvas.rect(x - 2.2, y - 2.2, 4.4, 4.4, fill=True)

    canvas.text(left + plot_w / 2, 13, "Grid size n", 9, align="center")
    canvas.rotated_text(14, bottom + plot_h / 2 - 45, "Collinearity penalty alpha", 90, 9)
    canvas.rotated_text(width - 10, bottom + plot_h / 2 - 40, "Integration horizon T", 90, 9, "#e67e22")
    canvas.line(left + plot_w - 60, bottom + plot_h - 10, left + plot_w - 42, bottom + plot_h - 10)
    canvas.circle(left + plot_w - 51, bottom + plot_h - 10, 2.4, fill="#1f77b4", stroke="#1f77b4")
    canvas.text(left + plot_w - 36, bottom + plot_h - 13, "alpha", 8)
    canvas.polyline([(left + plot_w - 60, bottom + plot_h - 24), (left + plot_w - 42, bottom + plot_h - 24)], "#e67e22", 1.1, "[4 3]")
    canvas.rect(left + plot_w - 53, bottom + plot_h - 26, 4, 4, fill=True)
    canvas.text(left + plot_w - 36, bottom + plot_h - 27, "T", 8)
    canvas.save(path)


def main() -> None:
    if not SCIML_ALPHA_CSV.exists():
        raise FileNotFoundError(SCIML_ALPHA_CSV)
    if not SCIML_N18_SOLUTION.exists():
        raise FileNotFoundError(SCIML_N18_SOLUTION)

    n10_points = load_cp_sat_n10_points()
    draw_grid_figure(10, n10_points, FIGURES / "no_three_in_line_n10.pdf", fill="#d62728", size=330)

    alpha_rows = load_alpha_rows(SCIML_ALPHA_CSV)
    draw_alpha_plot(alpha_rows, FIGURES / "sciml_alpha_scaling.pdf")

    n18, n18_points = load_solution_points(SCIML_N18_SOLUTION)
    draw_grid_figure(n18, n18_points, FIGURES / "sciml_solution_n18.pdf", fill="#e67e22", size=360)

    n19_points = load_cp_sat_n19_points()
    draw_grid_figure(19, n19_points, FIGURES / "no_three_in_line_n19.pdf", fill="#d62728", size=360)

    print("Generated vector PDFs:")
    print(f"  {FIGURES / 'no_three_in_line_n10.pdf'}")
    print(f"  {FIGURES / 'sciml_alpha_scaling.pdf'}")
    print(f"  {FIGURES / 'sciml_solution_n18.pdf'}")
    print(f"  {FIGURES / 'no_three_in_line_n19.pdf'}")


if __name__ == "__main__":
    main()
