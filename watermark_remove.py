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
	Remove watermarks while preserving legitimate content:
	- Detect and drop marked-content blocks with /Artifact or /Watermark
	- Detect low-opacity ExtGState usage and drop likely watermark blocks
	- Skip Form XObject draws under low opacity that look like watermarks
	- Filter watermark annotations only (keep other annotations)
	"""
	from pikepdf import parse_content_stream, unparse_content_stream, Name
	with pikepdf.open(str(input_path)) as pdf:
		for page in pdf.pages:
			resources = page.get("/Resources", pikepdf.Dictionary())
			low_alpha_names = collect_low_alpha_extgstates(resources)
			filter_watermark_annotations(page)
			try:
				instructions = parse_content_stream(page)
			except Exception as e:
				print(f"Warning: parse failed on {input_path.name}: {e}")
				continue
			filtered = filter_instructions(page, instructions, resources, low_alpha_names)
			try:
				new_bytes = unparse_content_stream(filtered)
				page["/Contents"] = pdf.make_stream(new_bytes)
			except Exception as e:
				print(f"Warning: rebuild failed on {input_path.name}: {e}")
		pdf.save(str(output_path))


def collect_low_alpha_extgstates(resources: pikepdf.Dictionary, alpha_threshold: float = 0.45) -> set:
	"""Return names of ExtGState entries with low fill/stroke alpha."""
	low_alpha = set()
	eg = resources.get("/ExtGState", pikepdf.Dictionary())
	if not isinstance(eg, pikepdf.Dictionary):
		return low_alpha
	for name, obj in eg.items():
		try:
			d = pikepdf.Dictionary(obj)
			ca = float(d.get("/ca", 1))  # fill alpha
			CA = float(d.get("/CA", ca))  # stroke alpha
			if min(ca, CA) <= alpha_threshold:
				low_alpha.add(str(name))
		except Exception:
			continue
	return low_alpha


def filter_watermark_annotations(page: pikepdf.Page) -> None:
	"""Remove only watermark-like annotations and keep others."""
	annots = page.get("/Annots", None)
	if not annots:
		return
	keywords = {"watermark", "confidential", "draft", "sample", "copy", "duplicate"}
	new_arr = pikepdf.Array()
	for annot in annots:
		try:
			a = pikepdf.Dictionary(annot)
			subtype = str(a.get("/Subtype", ""))
			contents = str(a.get("/Contents", "")).lower()
			nm = str(a.get("/NM", "")).lower()
			if "/Watermark" in subtype:
				continue
			if "/Stamp" in subtype and any(k in contents or k in nm for k in keywords):
				continue
			new_arr.append(annot)
		except Exception:
			new_arr.append(annot)
	if len(new_arr) > 0:
		page["/Annots"] = new_arr
	else:
		if "/Annots" in page:
			del page["/Annots"]


def filter_instructions(page: pikepdf.Page, instructions, resources: pikepdf.Dictionary, low_alpha_names: set):
	"""Heuristically remove instructions likely to be watermarks while preserving content."""
	from pikepdf import Name

	# Build XObject map for quick lookup
	xobjects = resources.get("/XObject", pikepdf.Dictionary())

	class Block:
		def __init__(self):
			self.instructions = []
			self.uses_low_alpha = False
			self.marked_watermark_depth = 0
			self.has_large_text = False
			self.saw_form_do = False
			self.last_font_size = 0.0
			self.last_tm_scale = 0.0
			self.rotation_like = False

	def is_large_text(font_size: float, tm_scale: float) -> bool:
		try:
			return (font_size is not None and float(font_size) >= 36) or (tm_scale is not None and float(tm_scale) >= 36)
		except Exception:
			return False

	def tm_scale_from_operands(ops) -> float:
		try:
			# Tm: a b c d e f; scale approximated by max(|a|, |d|)
			if len(ops) >= 4:
				a = float(ops[0]); b = float(ops[1]); c = float(ops[2]); d = float(ops[3])
				return max(abs(a), abs(d))
		except Exception:
			return 0.0
		return 0.0

	def tm_rotated(ops) -> bool:
		try:
			if len(ops) >= 4:
				b = abs(float(ops[1])); c = abs(float(ops[2]))
				return b > 0.1 or c > 0.1
		except Exception:
			return False
		return False

	stack = [Block()]
	skipping_text_till_ET = False

	for ins in instructions:
		op = ins.operator
		ops = ins.operands

		# Handle marked content indicative of watermark
		if op in ("BMC", "BDC"):
			is_artifact = False
			try:
				if len(ops) >= 1:
					prop = ops[0]
					if isinstance(prop, Name) and str(prop) in {"/Artifact", "/Watermark"}:
						is_artifact = True
				if not is_artifact and len(ops) >= 2 and hasattr(ops[1], 'get'):
					d = pikepdf.Dictionary(ops[1])
					subtype = str(d.get("/Subtype", ""))
					if "/Watermark" in subtype or "/Artifact" in subtype:
						is_artifact = True
			except Exception:
				is_artifact = is_artifact
			if is_artifact:
				stack[-1].marked_watermark_depth += 1
				# Do not append this marker; skip entire block till EMC
				continue
			# If not artifact, keep
			stack[-1].instructions.append(ins)
			continue

		if op == "EMC":
			if stack[-1].marked_watermark_depth > 0:
				stack[-1].marked_watermark_depth -= 1
				# Skip this EMC that closes watermark
				continue
			stack[-1].instructions.append(ins)
			continue

		# Inside marked watermark content: skip
		if stack[-1].marked_watermark_depth > 0:
			continue

		if op == "q":
			# Start new block
			stack.append(Block())
			stack[-1].instructions.append(ins)
			continue

		if op == "Q":
			# Close current block and decide keep/drop
			if len(stack) == 1:
				# Unbalanced, keep defensively
				stack[-1].instructions.append(ins)
				continue
			block = stack.pop()
			# Heuristic decision
			drop = block.uses_low_alpha and (block.has_large_text or block.saw_form_do)
			if not drop:
				# keep block with its Q
				stack[-1].instructions.extend(block.instructions)
				stack[-1].instructions.append(ins)
			else:
				# drop entire block
				pass
			continue

		if op == "gs":
			try:
				if len(ops) >= 1:
					gsname = str(ops[0])
					low = gsname in low_alpha_names
					if low:
						stack[-1].uses_low_alpha = True
			except Exception:
				pass
			stack[-1].instructions.append(ins)
			continue

		# Track text state
		if op == "Tf" and len(ops) >= 2:
			try:
				stack[-1].last_font_size = float(ops[1])
			except Exception:
				pass
			stack[-1].instructions.append(ins)
			continue

		if op == "Tm" and len(ops) >= 6:
			scale = tm_scale_from_operands(ops)
			stack[-1].last_tm_scale = scale
			if tm_rotated(ops):
				stack[-1].rotation_like = True
			stack[-1].instructions.append(ins)
			continue

		if op == "BT":
			if stack[-1].uses_low_alpha:
				skipping_text_till_ET = True
				# do not include BT; we'll skip the text block as watermark
				continue
			stack[-1].instructions.append(ins)
			continue

		if op == "ET":
			if skipping_text_till_ET:
				skipping_text_till_ET = False
				# do not include ET either
				continue
			stack[-1].instructions.append(ins)
			continue

		# Skip text drawing ops if we are in low-alpha text block
		if skipping_text_till_ET and op in ("Tj", "TJ", "Tf", "Td", "Tm", "Tr", "Ts", "Tw", "Tz", "TL"):
			continue

		# Record potential watermark via large text
		if op in ("Tj", "TJ"):
			if is_large_text(stack[-1].last_font_size, stack[-1].last_tm_scale):
				stack[-1].has_large_text = True
			stack[-1].instructions.append(ins)
			continue

		# Handle XObject draws
		if op == "Do" and len(ops) >= 1:
			xname = ops[0]
			try:
				xobj = xobjects.get(xname, None)
				is_form = False
				if xobj is not None:
					d = pikepdf.Dictionary(xobj)
					is_form = str(d.get("/Subtype", "")) == "/Form"
				if stack[-1].uses_low_alpha and is_form:
					# Likely watermark form under low opacity – drop
					stack[-1].saw_form_do = True
					continue
			except Exception:
				pass
			stack[-1].instructions.append(ins)
			continue

		# Default: keep
		stack[-1].instructions.append(ins)

	# Close any remaining nested blocks conservatively (keep them)
	while len(stack) > 1:
		block = stack.pop()
		stack[-1].instructions.extend(block.instructions)

	return stack[0].instructions


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
