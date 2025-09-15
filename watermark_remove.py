import os
import sys
from pathlib import Path

try:
	import pikepdf
except Exception as exc:  # pragma: no cover
	print("Missing dependency: pikepdf. Install with: pip install pikepdf", file=sys.stderr)
	raise

INPUT_DIR = Path(__file__).parent / "pdf_data"
OUTPUT_DIR = Path(__file__).parent / "clean_pdf_data"


def remove_watermarks_from_pdf(input_path: Path, output_path: Path) -> None:
	"""
	Comprehensive watermark removal that handles various watermark types:
	- Text-based watermarks in content streams
	- Image-based watermarks in XObjects
	- Graphics state watermarks with transparency
	- Multiple content stream arrays
	"""
	with pikepdf.open(str(input_path)) as pdf:
		# 1) Remove Optional Content Groups if present
		ocprops = pdf.Root.get("OCProperties", None)
		if ocprops is not None:
			pdf.Root["OCProperties"] = pikepdf.Dictionary()

		# 2) Process each page
		for page in pdf.pages:
			resources = page.get("/Resources", pikepdf.Dictionary())

			# 2a) Remove suspicious XObjects (images/forms that might be watermarks)
			xobjects = resources.get("/XObject", pikepdf.Dictionary())
			if xobjects:
				# Remove ALL XObjects as a more aggressive approach
				# Most legitimate content is in the content stream, not XObjects
				resources["/XObject"] = pikepdf.Dictionary()

			# 2b) Remove all annotations (watermarks often added as annotations)
			if "/Annots" in page:
				del page["/Annots"]

			# 2c) Clean content streams - handle both single streams and arrays
			contents = page.get("/Contents")
			if contents is not None:
				try:
					if isinstance(contents, pikepdf.Array):
						# Multiple content streams - process each one
						new_contents = pikepdf.Array()
						for content_ref in contents:
							cleaned_stream = clean_content_stream(content_ref)
							if cleaned_stream:  # Only add non-empty streams
								new_contents.append(cleaned_stream)
						if new_contents:
							page["/Contents"] = new_contents
						else:
							# If all streams were removed, create minimal content
							page["/Contents"] = create_minimal_content(pdf)
					else:
						# Single content stream
						cleaned_stream = clean_content_stream(contents)
						if cleaned_stream:
							page["/Contents"] = cleaned_stream
						else:
							page["/Contents"] = create_minimal_content(pdf)
				except Exception as e:
					print(f"Warning: Could not clean content stream: {e}")

		# 3) Save optimized PDF
		pdf.save(str(output_path))


def clean_content_stream(content_ref):
	"""Clean individual content stream by removing watermark-related operations"""
	try:
		stream_data = content_ref.read_bytes()
		text_data = stream_data.decode('latin-1', errors='ignore')
		
		# Remove common watermark text patterns (case-insensitive)
		watermark_patterns = [
			'watermark', 'confidential', 'draft', 'copy', 'duplicate', 
			'proprietary', 'internal', 'restricted', 'sample'
		]
		
		lines = text_data.split('\n')
		cleaned_lines = []
		skip_until_restore = False
		
		for line in lines:
			line_lower = line.lower()
			
			# Skip lines containing watermark text
			if any(pattern in line_lower for pattern in watermark_patterns):
				continue
				
			# Skip graphics state operations that might be for watermarks
			if any(op in line for op in ['gs', '/GS', '/ExtGState']):
				# Check if this might be setting transparency for watermarks
				if any(transparency in line_lower for transparency in ['alpha', 'opacity', '0.1', '0.2', '0.3']):
					continue
			
			# Skip text positioning that might be for watermarks (extreme positions)
			if 'Tm' in line or 'Td' in line:
				# Look for suspicious positioning (very low opacity areas or corners)
				nums = [float(x) for x in line.split() if x.replace('.', '').replace('-', '').isdigit()]
				if nums and (any(abs(n) > 1000 for n in nums) or any(0 < abs(n) < 0.5 for n in nums)):
					skip_until_restore = True
					continue
			
			# Skip until we see a graphics restore (Q)
			if skip_until_restore:
				if line.strip() == 'Q':
					skip_until_restore = False
				continue
				
			# Skip marked content operations that might wrap watermarks
			if any(op in line for op in ['BDC', 'BMC']):
				skip_until_restore = True
				continue
			if 'EMC' in line and skip_until_restore:
				skip_until_restore = False
				continue
				
			cleaned_lines.append(line)
		
		cleaned_data = '\n'.join(cleaned_lines).encode('latin-1', errors='ignore')
		
		# Only return if we have substantial content left
		if len(cleaned_data) > 50:  # Arbitrary threshold
			content_ref.write(cleaned_data)
			return content_ref
		return None
		
	except Exception:
		return content_ref  # Return original if cleaning fails


def create_minimal_content(pdf):
	"""Create minimal content stream if all content was removed"""
	minimal_stream = pdf.make_stream(b"% Minimal content stream\n")
	return minimal_stream


def process_all_pdfs() -> int:
	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	if not INPUT_DIR.exists():
		print(f"Input directory not found: {INPUT_DIR}", file=sys.stderr)
		return 1

	pdf_files = [p for p in INPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
	if not pdf_files:
		print("No PDFs found in pdf_data/", file=sys.stderr)
		return 1

	for input_pdf in pdf_files:
		output_pdf = OUTPUT_DIR / input_pdf.name
		try:
			remove_watermarks_from_pdf(input_pdf, output_pdf)
			print(f"Cleaned: {input_pdf.name} -> {output_pdf}")
		except Exception as exc:
			print(f"Failed: {input_pdf.name}: {exc}", file=sys.stderr)
			# If cleaning fails, copy original as fallback
			try:
				with open(input_pdf, "rb") as src, open(output_pdf, "wb") as dst:
					dst.write(src.read())
			except Exception:
				pass
	return 0


if __name__ == "__main__":
	sys.exit(process_all_pdfs())
