import zipfile

import qrcode
import qrcode.image.svg

from skills.sandbox import WORKSPACE, _safe_path

UNIT_CONVERSIONS = {
    ("m", "ft"): lambda v: v * 3.28084,
    ("ft", "m"): lambda v: v / 3.28084,
    ("km", "mi"): lambda v: v * 0.621371,
    ("mi", "km"): lambda v: v / 0.621371,
    ("cm", "in"): lambda v: v / 2.54,
    ("in", "cm"): lambda v: v * 2.54,
    ("kg", "lb"): lambda v: v * 2.20462,
    ("lb", "kg"): lambda v: v / 2.20462,
    ("g", "oz"): lambda v: v * 0.035274,
    ("oz", "g"): lambda v: v / 0.035274,
}


def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units: length (m/ft/km/mi/cm/in), weight
    (kg/lb/g/oz), temperature (c/f/k). Case-insensitive.
    """
    f, t = from_unit.lower(), to_unit.lower()

    if f in ("c", "f", "k") and t in ("c", "f", "k"):
        celsius = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[f]
        result = {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[t]
        return f"{value} {from_unit} = {round(result, 4)} {to_unit}"

    fn = UNIT_CONVERSIONS.get((f, t))
    if fn is None:
        return f"error: no conversion available for {from_unit} -> {to_unit}"
    return f"{value} {from_unit} = {round(fn(value), 4)} {to_unit}"


def zip_files(paths: list[str], output_path: str) -> str:
    """Zip one or more files/directories in the sandbox workspace into a single archive."""
    out = _safe_path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            src = _safe_path(p)
            if src.is_file():
                zf.write(src, src.relative_to(WORKSPACE))
                count += 1
            elif src.is_dir():
                for f in src.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(WORKSPACE))
                        count += 1
            else:
                return f"error: does not exist: {p}"
    return f"wrote {count} file(s) to {out.relative_to(WORKSPACE)}"


def unzip_file(zip_path: str, output_dir: str = ".") -> str:
    """Extract a zip archive in the sandbox workspace into a directory."""
    src = _safe_path(zip_path)
    if not src.is_file():
        return f"error: not a file: {zip_path}"
    dest = _safe_path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zf:
        names = zf.namelist()
        zf.extractall(dest)
    return f"extracted {len(names)} file(s) to {dest.relative_to(WORKSPACE)}"


def generate_qr_code(data: str, output_path: str) -> str:
    """Generate a QR code (SVG, fully offline -- no network call) for the given
    text/URL and save it in the sandbox workspace.
    """
    out = _safe_path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgImage)
    img.save(str(out))
    return f"wrote QR code to {out.relative_to(WORKSPACE)}"


def register(mcp):
    mcp.tool()(convert_units)
    mcp.tool()(zip_files)
    mcp.tool()(unzip_file)
    mcp.tool()(generate_qr_code)
