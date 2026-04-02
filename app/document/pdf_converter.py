import os
import subprocess


def convert(docx_path: str, job_id: str, output_dir: str) -> str:
    _ = job_id
    result = subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", output_dir, docx_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")

    pdf_filename = os.path.basename(docx_path).replace(".docx", ".pdf")
    pdf_path = os.path.join(output_dir, pdf_filename)
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found after conversion: {pdf_path}")
    return pdf_path
