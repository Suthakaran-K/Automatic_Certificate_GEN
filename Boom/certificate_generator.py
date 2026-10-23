from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from datetime import date
import re, uuid

TEMPLATE_FILES = {
    "Participation": "participation.png",
    "First Prize": "first_prize.png",
    "Second Prize": "second_prize.png"
}

# Adjust these settings after checking where text belongs on your original template images.
# Coordinates are proportions from the TOP-left corner (0.0 to 1.0).
TEXT_LAYOUT = {
    "Participation": {"name_y": 0.49, "event_y": 0.61, "award_y": 0.70, "date_y": 0.84},
    "First Prize": {"name_y": 0.49, "event_y": 0.61, "award_y": 0.70, "date_y": 0.84},
    "Second Prize": {"name_y": 0.49, "event_y": 0.61, "award_y": 0.70, "date_y": 0.84},
}

def safe_stem(value):
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    return (value[:50] or "participant")

def draw_centered_fit(pdf, value, x, y, max_width, start_size=30, min_size=12, font="Helvetica-Bold"):
    value = str(value or "")
    size = start_size
    while size > min_size and stringWidth(value, font, size) > max_width:
        size -= 1
    pdf.setFont(font, size)
    pdf.drawCentredString(x, y, value)

def generate_certificate(participant_name, event_name, certificate_type, template_folder, output_folder, issue_date=""):
    if certificate_type not in TEMPLATE_FILES:
        raise ValueError(f"Unsupported certificate type: {certificate_type}")
    template_path = Path(template_folder) / TEMPLATE_FILES[certificate_type]
    if not template_path.is_file():
        raise FileNotFoundError(f"Required template is missing: {TEMPLATE_FILES[certificate_type]}")
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    with Image.open(template_path) as im:
        image = im.convert("RGB")
        width_px, height_px = image.size
        image_reader = ImageReader(image)
        # PDF uses points; preserve image aspect ratio with 1 pixel = 1 point.
        page_w, page_h = float(width_px), float(height_px)
        filename = f"{safe_stem(participant_name)}_{uuid.uuid4().hex[:10]}.pdf"
        output_path = output_folder / filename
        pdf = canvas.Canvas(str(output_path), pagesize=(page_w, page_h), pageCompression=1)
        pdf.drawImage(image_reader, 0, 0, width=page_w, height=page_h)
        layout = TEXT_LAYOUT[certificate_type]
        # Text coordinates are configured from the top, converted to PDF bottom-origin coordinates.
        draw_centered_fit(pdf, participant_name, page_w * 0.5, page_h * (1 - layout["name_y"]),
                          page_w * 0.78, start_size=max(20, page_w * 0.035))
        draw_centered_fit(pdf, event_name, page_w * 0.5, page_h * (1 - layout["event_y"]),
                          page_w * 0.78, start_size=max(14, page_w * 0.022), font="Helvetica")
        draw_centered_fit(pdf, certificate_type, page_w * 0.5, page_h * (1 - layout["award_y"]),
                          page_w * 0.78, start_size=max(14, page_w * 0.02), font="Helvetica-Bold")
        date_text = issue_date or date.today().strftime("%d %B %Y")
        pdf.setFont("Helvetica", max(9, page_w * 0.012))
        pdf.drawCentredString(page_w * 0.5, page_h * (1 - layout["date_y"]), date_text)
        pdf.showPage()
        pdf.save()
    return str(output_path)
