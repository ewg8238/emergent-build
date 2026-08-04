# COI Autopilot — Image/AI testing rules
- Accepted image MIME types: image/jpeg, image/png, image/webp only.
- PDFs are rendered to PNG (page 1) via PyMuPDF before sending to the model.
- Resize before base64; no blank/solid images.
- Vision model: openai gpt-5.4 via emergentintegrations.
