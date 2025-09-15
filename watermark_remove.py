import os
import sys
import logging
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from pdf2image import convert_from_path
import tempfile
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('watermark_removal.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class PDFImageWatermarkRemover:
    """Main class for removing watermarks from PDF files using image processing."""
    
    def __init__(self, input_dir="pdf_data", output_dir="clean_pdf_data", work_dir="temp_images", keep_temp=True):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.work_dir = Path(work_dir)
        self.keep_temp = keep_temp
        
        # Create directories if they don't exist
        self.output_dir.mkdir(exist_ok=True)
        self.work_dir.mkdir(exist_ok=True)
        
        logger.info(f"Initialized PDF Image Watermark Remover")
        logger.info(f"Input directory: {self.input_dir}")
        logger.info(f"Output directory: {self.output_dir}")
        logger.info(f"Working directory: {self.work_dir}")
    
    def __del__(self):
        """Cleanup working directory if keep_temp is False."""
        if hasattr(self, 'keep_temp') and not self.keep_temp:
            if hasattr(self, 'work_dir') and self.work_dir.exists():
                shutil.rmtree(self.work_dir, ignore_errors=True)
    
    def create_pdf_folder(self, pdf_name):
        """Create a folder for storing images of a specific PDF."""
        folder_name = pdf_name.replace('.pdf', '').replace(' ', '_')
        pdf_folder = self.work_dir / folder_name
        
        # Create original images folder
        original_folder = pdf_folder / "original"
        processed_folder = pdf_folder / "processed"
        
        original_folder.mkdir(parents=True, exist_ok=True)
        processed_folder.mkdir(parents=True, exist_ok=True)
        
        return original_folder, processed_folder
    
    def pdf_to_images(self, pdf_path, output_folder):
        """Convert PDF to images and save in the specified folder."""
        try:
            logger.info(f"Converting PDF to images: {pdf_path.name}")
            
            # Convert PDF to images with high DPI for better quality
            images = convert_from_path(str(pdf_path), dpi=300, fmt='PNG')
            
            image_paths = []
            for i, image in enumerate(images):
                image_path = output_folder / f"page_{i+1:03d}.png"
                image.save(str(image_path), 'PNG')
                image_paths.append(image_path)
                logger.info(f"Saved page {i+1} as {image_path.name}")
            
            return image_paths
            
        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {str(e)}")
            return []
    
    def remove_watermark_from_image(self, image_path):
       
        try:
            # Read the image EXACTLY like your original code
            img1 = cv2.imread(str(image_path))
            if img1 is None:
                logger.error(f"Could not read image: {image_path}")
                return None
            
            logger.info(f"Processing watermark removal for: {image_path.name}")
            
            # YOUR EXACT ORIGINAL METHOD
            _, thresh = cv2.threshold(img1, 150, 255, cv2.THRESH_BINARY)
            
            # That's it! Just return the thresholded result
            return thresh
            
        except Exception as e:
            logger.error(f"Error removing watermark from {image_path}: {str(e)}")
            return None
    
    
    def process_images_in_folder(self, original_folder, processed_folder):
        """Process all images in the original folder and save to processed folder."""
        try:
            image_files = sorted(list(original_folder.glob("*.png")))
            
            if not image_files:
                logger.warning(f"No images found in {original_folder}")
                return []
            
            processed_images = []
            
            for image_path in image_files:
                logger.info(f"Processing image: {image_path.name}")
                
                # Remove watermark
                processed_img = self.remove_watermark_from_image(image_path)
                
                if processed_img is not None:
                    # Save processed image
                    output_path = processed_folder / image_path.name
                    cv2.imwrite(str(output_path), processed_img)
                    processed_images.append(output_path)
                    logger.info(f"Saved processed image: {output_path.name}")
                else:
                    logger.error(f"Failed to process image: {image_path.name}")
            
            return processed_images
            
        except Exception as e:
            logger.error(f"Error processing images: {str(e)}")
            return []
    
    def images_to_pdf(self, image_paths, output_pdf_path):
        """Convert processed images back to PDF."""
        try:
            if not image_paths:
                logger.error("No images to convert to PDF")
                return False
            
            logger.info(f"Converting {len(image_paths)} images to PDF: {output_pdf_path.name}")
            
            # Sort images by name to maintain page order
            sorted_paths = sorted(image_paths, key=lambda x: x.name)
            
            # Convert OpenCV images to PIL format
            pil_images = []
            
            for img_path in sorted_paths:
                # Read image with OpenCV
                cv_img = cv2.imread(str(img_path))
                if cv_img is not None:
                    # Convert BGR to RGB
                    rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                    # Convert to PIL Image
                    pil_img = Image.fromarray(rgb_img)
                    pil_images.append(pil_img)
            
            if pil_images:
                # Save as PDF
                pil_images[0].save(
                    str(output_pdf_path),
                    "PDF",
                    resolution=300.0,
                    save_all=True,
                    append_images=pil_images[1:]
                )
                logger.info(f"Successfully created PDF: {output_pdf_path.name}")
                return True
            else:
                logger.error("No valid images to convert to PDF")
                return False
                
        except Exception as e:
            logger.error(f"Error converting images to PDF: {str(e)}")
            return False
    
    def process_single_pdf(self, pdf_path):
        """Process a single PDF file through the complete workflow."""
        try:
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                logger.error(f"PDF file does not exist: {pdf_path}")
                return False
            
            logger.info(f"Starting complete workflow for: {pdf_path.name}")
            
            # Step 1: Create folders for this PDF
            original_folder, processed_folder = self.create_pdf_folder(pdf_path.name)
            
            # Step 2: Convert PDF to images
            image_paths = self.pdf_to_images(pdf_path, original_folder)
            if not image_paths:
                logger.error(f"Failed to convert PDF to images: {pdf_path.name}")
                return False
            
            # Step 3: Process images to remove watermarks
            processed_images = self.process_images_in_folder(original_folder, processed_folder)
            if not processed_images:
                logger.error(f"Failed to process images for: {pdf_path.name}")
                return False
            
            # Step 4: Convert processed images back to PDF
            output_pdf_name = f"cleaned_{pdf_path.stem}.pdf"
            output_pdf_path = self.output_dir / output_pdf_name
            
            success = self.images_to_pdf(processed_images, output_pdf_path)
            
            if success:
                logger.info(f"Successfully completed workflow for: {pdf_path.name}")
                logger.info(f"Output saved as: {output_pdf_path.name}")
                return True
            else:
                logger.error(f"Failed to create final PDF for: {pdf_path.name}")
                return False
                
        except Exception as e:
            logger.error(f"Error in complete workflow for {pdf_path}: {str(e)}")
            return False
    
    def process_all_pdfs(self):
        """Process all PDF files in the input directory."""
        if not self.input_dir.exists():
            logger.error(f"Input directory does not exist: {self.input_dir}")
            return
        
        # Find all PDF files (excluding .bak files)
        pdf_files = [f for f in self.input_dir.glob("*.pdf") if not f.name.endswith('.bak')]
        
        if not pdf_files:
            logger.warning(f"No PDF files found in {self.input_dir}")
            return
        
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        successful = 0
        failed = 0
        
        for pdf_file in pdf_files:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing PDF {successful + failed + 1}/{len(pdf_files)}: {pdf_file.name}")
            logger.info(f"{'='*60}")
            
            if self.process_single_pdf(pdf_file):
                successful += 1
            else:
                failed += 1
        
        logger.info(f"\n{'='*60}")
        logger.info(f"PROCESSING COMPLETE!")
        logger.info(f"Success: {successful}, Failed: {failed}")
        logger.info(f"Check '{self.output_dir}' for cleaned PDF files")
        logger.info(f"Check '{self.work_dir}' for intermediate images")
        logger.info(f"{'='*60}")

def main():
    
    # Initialize the remover
    remover = PDFImageWatermarkRemover()
    
    # Process all PDFs
    remover.process_all_pdfs()
    
    print("\nProcessing complete!")
    print("- Check 'clean_pdf_data' folder for final cleaned PDFs")
    print("- Check 'temp_images' folder for intermediate processing images")

if __name__ == "__main__":
    main()