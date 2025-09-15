# PDF Watermark Remover

## Quick Setup

**Step 1:** Open your computer's command line:

- **Mac**: Search for "Terminal" and open it
- **Windows**: Search for "Command Prompt" and open it

**Step 2:** Navigate to this project folder. Type `cd ` (with a space) then drag this folder into the command window and press Enter.

**Step 3:** Install required software by copying and pasting this command:

```
pip install -r requirements.txt
```

**Step 4:** Install one more tool:

- **Mac users**: Type: `brew install poppler`
- **Windows users**: Download from https://poppler.freedesktop.org/ and install it

**step 5**:

- **Create a folder**: Make a new folder called `pdf_data` in this project folder and put your PDF files with watermarks inside

**step 6**:

- **Run the program**: In the command line, type:

```
python watermark_remove.py
```

- **Get your clean PDFs**: A new folder called `clean_pdf_data` will appear with your watermark-free PDFs
