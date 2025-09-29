#!/usr/bin/env python3

import time
import os
from pathlib import Path

def test_doctr_ocr():
    try:
        from doctr.io import DocumentFile
        from doctr.models import ocr_predictor

        image_path = Path(__file__).parent / "test_image.jpg"

        if not image_path.exists():
            print(f"Error: Test image not found at {image_path}")
            return

        print("=" * 80)
        print("docTR OCR Performance Test")
        print("=" * 80)
        print(f"Test Image: {image_path}")
        print("-" * 80)

        print("\n[1/3] Loading docTR model...")
        model_start = time.time()
        model = ocr_predictor(pretrained=True)
        model_time = time.time() - model_start
        print(f"Model loading time: {model_time:.2f} seconds")

        print("\n[2/3] Loading image...")
        load_start = time.time()
        doc = DocumentFile.from_images(str(image_path))
        load_time = time.time() - load_start
        print(f"Image loading time: {load_time:.2f} seconds")

        print("\n[3/3] Performing OCR...")
        ocr_start = time.time()
        result = model(doc)
        ocr_time = time.time() - ocr_start
        print(f"OCR processing time: {ocr_time:.2f} seconds")

        print("\n" + "=" * 80)
        print("Extracted Text:")
        print("=" * 80)

        text_lines = []
        for page in result.pages:
            for block in page.blocks:
                for line in block.lines:
                    line_text = " ".join([word.value for word in line.words])
                    text_lines.append(line_text)
                    print(line_text)

        full_text = "\n".join(text_lines)

        print("\n" + "=" * 80)
        print("Performance Summary:")
        print("=" * 80)
        print(f"Model loading time:    {model_time:.2f}s")
        print(f"Image loading time:    {load_time:.2f}s")
        print(f"OCR processing time:   {ocr_time:.2f}s")
        print(f"Total time:            {model_time + load_time + ocr_time:.2f}s")
        print(f"Characters extracted:  {len(full_text)}")
        print(f"Lines extracted:       {len(text_lines)}")
        print("=" * 80)

        output_file = Path(__file__).parent / "doctr_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"\nOutput saved to: {output_file}")

        return {
            "model_time": model_time,
            "load_time": load_time,
            "ocr_time": ocr_time,
            "total_time": model_time + load_time + ocr_time,
            "text_length": len(full_text),
            "lines_count": len(text_lines)
        }

    except ImportError as e:
        print(f"Error: docTR is not installed. Please install it with:")
        print(f"  pip install python-doctr")
        print(f"\nDetailed error: {e}")
    except Exception as e:
        print(f"Error during OCR processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_doctr_ocr()